from datetime import datetime, timezone
import hashlib
import hmac
import io
import os
import re
import unicodedata
import subprocess
import sys
from zoneinfo import ZoneInfo

import requests
import sqlalchemy as sa
from flask import Blueprint, abort, redirect, render_template, request, send_file, url_for

from .store import asset, episodes, incoming, source_text, transition


STATES = {
    "offered": "Aguardando preparo", "queued": "Na fila de preparo",
    "waiting_text": "Aguardando texto", "preparing": "Preparando",
    "preview": "Aguardando aprovação", "approved": "Aprovado para publicar",
    "publishing": "Publicando", "clicked": "Confirmando publicação",
    "published": "Publicado", "check_spotify": "Conferir no Spotify",
    "failed": "Falha no preparo", "cancelled": "Cancelado",
}
TRASHABLE = ("offered", "queued", "waiting_text", "failed", "preview", "approved", "cancelled")
PREPARABLE = ("offered", "queued", "failed", "waiting_text")
PREVIEW_STATES = ("preview", "approved", "publishing", "clicked", "published", "check_spotify")
EDITABLE_STATES = ("offered", "queued", "waiting_text", "failed", "preview", "approved", "cancelled")
MANUAL_PUBLISH_STATES = ("preview", "approved", "check_spotify", "clicked")
STAGE_ACTIONS = ("trash", "prepare", "transcribe", "schedule", "edit", "mark-published")
BR_TZ = ZoneInfo("America/Sao_Paulo")
SPOTIFY_WIZARD_URL = "https://creators.spotify.com/pod/show/04yjeHqDd36rhxnVdEz60l/episode/wizard"


def parse_br_publish_datetime(date_str, time_str=""):
    """Interpreta data no padrão brasileiro DD/MM/AAAA (ou ISO YYYY-MM-DD) com horário HH:MM opcional."""
    raw_date = (date_str or "").strip()
    if not raw_date:
        raise ValueError("Informe a data no formato DD/MM/AAAA.")
    parsed_date = None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            parsed_date = datetime.strptime(raw_date, fmt)
            break
        except ValueError:
            continue
    if not parsed_date:
        raise ValueError("Data inválida. Use o formato DD/MM/AAAA (ex.: 18/10/2026).")

    raw_time = (time_str or "").strip()
    if raw_time:
        try:
            parsed_time = datetime.strptime(raw_time, "%H:%M")
        except ValueError:
            raise ValueError("Horário inválido. Use o formato HH:MM (ex.: 08:00) ou deixe em branco.")
        hour, minute, has_time = parsed_time.hour, parsed_time.minute, True
    else:
        hour, minute, has_time = 8, 0, False

    dt_br = datetime(parsed_date.year, parsed_date.month, parsed_date.day, hour, minute, tzinfo=BR_TZ)
    return dt_br, has_time


def publish_meta(row, now=None):
    """Prepara metadados amigáveis de publicação (Imediata vs. Planejada/Retroativa) para os templates."""
    mode = row.get("publish_mode") or "immediate"
    publish_at = row.get("publish_at")
    has_time = bool(row.get("publish_has_time"))
    if mode == "scheduled" and publish_at:
        if publish_at.tzinfo is None:
            dt_br = publish_at.replace(tzinfo=timezone.utc).astimezone(BR_TZ)
        else:
            dt_br = publish_at.astimezone(BR_TZ)
        current = now or datetime.now(BR_TZ)
        is_past = dt_br.date() < current.date() if not has_time else dt_br < current
        date_br = dt_br.strftime("%d/%m/%Y")
        date_iso = dt_br.strftime("%Y-%m-%d")
        time_br = dt_br.strftime("%H:%M") if has_time else ""
        display = f"{date_br} às {time_br}" if has_time else date_br
        return {
            "mode": "scheduled",
            "is_scheduled": True,
            "is_past": is_past,
            "has_time": has_time,
            "date_br": date_br,
            "date_iso": date_iso,
            "time_br": time_br,
            "display": display,
            "sort_key": dt_br.isoformat(),
        }
    return {
        "mode": "immediate",
        "is_scheduled": False,
        "is_past": False,
        "has_time": False,
        "date_br": "",
        "date_iso": "",
        "time_br": "",
        "display": "Imediata (publicar agora)",
        "sort_key": "",
    }


def extract_spotify_id(raw):
    """Extrai o ID de 22 caracteres de um link ou identificador do Spotify."""
    text = (raw or "").strip()
    if not text:
        return None
    if re.fullmatch(r"[a-zA-Z0-9]{22}", text):
        return text
    match = re.search(r"/episode/([a-zA-Z0-9]{22})", text)
    return match.group(1) if match else None


def launch_prepare(engine, eid, owner):
    """Inicia o preparo em background assim que o episódio tiver áudio e texto associados."""
    with engine.begin() as conn:
        row = conn.execute(
            sa.select(episodes).where(episodes.c.id == eid, episodes.c.owner == owner).with_for_update()
        ).mappings().first()
        if not row or row["state"] not in PREPARABLE:
            return False
        if not source_text(conn, row["source_id"]):
            return False
        version = row["version"]
        if not transition(conn, eid, owner, version, row["state"], "preparing", notice="panel"):
            return False
    try:
        subprocess.Popen(
            [sys.executable, "-m", "homilias.worker", "prepare-panel", "--id", eid, "--version", str(version)],
            start_new_session=True,
        )
        return True
    except OSError:
        with engine.begin() as conn:
            transition(conn, eid, owner, version, "preparing", "queued", notice=None)
        return False


def stage_token():
    """Link privado independente dos tokens de prévia de cada edição."""
    configured = os.getenv("HOMILIA_STAGE_TOKEN")
    if configured:
        return configured
    secret, owner = os.getenv("WHATSAPP_APP_SECRET"), os.getenv("HOMILIA_OWNER_WA_ID")
    if not secret or not owner:
        return None
    return hmac.new(secret.encode(), ("homilias-stage:" + owner).encode(), hashlib.sha256).hexdigest()


def stage_url():
    token = stage_token()
    base = os.getenv("HOMILIA_PUBLIC_URL", "").strip().rstrip("/")
    if not token or not base or not os.getenv("HOMILIA_OWNER_WA_ID"):
        return None
    return base + "/homilias/stage/" + token


def stage_request(phone, sender, body, verified):
    """Atalho determinístico do WhatsApp, sem banco nem chamada ao modelo."""
    normalized = unicodedata.normalize("NFKD", body.casefold())
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    normalized = " ".join(normalized.split()).rstrip(".!?")
    if normalized not in ("painel homilias", "painel de homilias", "painel das homilias",
                          "stage homilias", "painel do podcast"):
        return False
    if not verified or not reviewer(sender):
        abort(403)
    url = stage_url()
    body = ("Painel de homilias · Nos Passos de Cristo\n\n" + url +
            "\n\nTodos os episódios, status e materiais para publicação. Guarde este link privado.") if url else (
            "O painel de homilias ainda precisa de configuração no servidor. "
            "Confira HOMILIA_PUBLIC_URL e as variáveis de acesso ao painel.")
    message(phone, sender, type="text", text={"body": body})
    return True


def signed(body, signature):
    secret = os.getenv("WHATSAPP_APP_SECRET")
    if not secret:
        return False
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest("sha256=" + digest, signature or "")


def reviewer(sender):
    return bool(sender and sender == os.getenv("HOMILIA_OWNER_WA_ID"))


def message(phone, owner, **fields):
    response = requests.post(
        f"https://graph.facebook.com/v20.0/{phone}/messages",
        headers={"Authorization": "Bearer " + os.environ["WHATSAPP_TOKEN"]},
        json={"messaging_product": "whatsapp", "to": owner, **fields}, timeout=25)
    response.raise_for_status()
    return response.json()["messages"][0]["id"]


def buttons(phone, owner, body, options):
    rows = [{"type": "reply", "reply": {"id": key, "title": label}} for key, label in options]
    return message(phone, owner, type="interactive", interactive={
        "type": "button", "body": {"text": body}, "action": {"buttons": rows}})


def handle(conn, sender, action, msg):
    # O remetente e a assinatura do webhook são conferidos antes do dispatch.
    dismiss = re.fullmatch(r"hom:dismiss:([0-9a-f]{32}):1", action)
    if dismiss:
        for before in ("offered", "queued", "preparing", "preview"):
            if transition(conn, dismiss[1], sender, 1, before, "cancelled", preview=None, notice=None):
                return "Edição cancelada."
        return "Essa edição já mudou de estado."
    match = re.fullmatch(r"hom:(prepare|approve|cancel|retry):([0-9a-f]{32}):(\d{1,9})", action)
    if match:
        verb, eid, version = match.groups()
        before, after = {"prepare": ("offered", "queued"), "approve": ("preview", "approved"),
                         "cancel": ("preview", "cancelled"), "retry": ("failed", "queued")}[verb]
        ok = transition(conn, eid, sender, int(version), before, after, notice=None)
        if ok:
            return {"prepare": "Homilia na fila de preparo.", "approve": "Edição aprovada para publicação.",
                    "cancel": "Edição cancelada.", "retry": "Preparo solicitado novamente."}[verb]
        return "Este botão já foi usado ou pertence a outra versão."
    edit = re.fullmatch(r"ajustar ([0-9a-f]{32}) v(\d{1,9})\s+(.+)", msg.strip(), re.S | re.I)
    if edit:
        eid, version, note = edit.groups()
        if transition(conn, eid.lower(), sender, int(version), "preview", "queued",
                      version=int(version) + 1, note=note.strip(), preview=None, notice=None):
            return "Pedido recebido. Você receberá uma nova prévia para aprovar."
        return "Essa prévia já foi encerrada."
    return None


def preview_routes(get_engine):
    bp = Blueprint("homilias", __name__, template_folder="templates")

    def check_stage(token):
        expected = stage_token()
        if not expected or not hmac.compare_digest(expected, token) or not os.getenv("HOMILIA_OWNER_WA_ID"):
            abort(404)

    @bp.get("/homilias/stage/<token>")
    def stage(token):
        check_stage(token)
        with get_engine().connect() as conn:
            rows = conn.execute(sa.select(episodes.c.id, episodes.c.title, episodes.c.state,
                episodes.c.version, episodes.c.notice, episodes.c.publish_mode,
                episodes.c.publish_at, episodes.c.publish_has_time, episodes.c.spotify_id,
                incoming.c.received_at, incoming.c.source_text)
                .outerjoin(incoming, episodes.c.source_id == incoming.c.source_id)
                .where(episodes.c.owner == os.environ["HOMILIA_OWNER_WA_ID"], episodes.c.state != "trashed")
                .order_by(episodes.c.title, incoming.c.received_at, episodes.c.id)).mappings().all()
        now = datetime.now(BR_TZ)
        pub_map = {row["id"]: publish_meta(row, now=now) for row in rows}
        return render_template("homilias_stage.html", jobs=rows, pub_map=pub_map, states=STATES,
            stage_token=token, preparable=PREPARABLE, trashable=TRASHABLE, timezone=BR_TZ)

    @bp.post("/homilias/stage/<token>/episode/<eid>/<action>")
    def stage_action(token, eid, action):
        check_stage(token)
        if action not in STAGE_ACTIONS or not re.fullmatch(r"[0-9a-f]{32}", eid):
            abort(404)
        version = request.form.get("version", type=int)
        expected_state = request.form.get("state")
        with get_engine().begin() as conn:
            row = conn.execute(sa.select(episodes).where(episodes.c.id == eid,
                episodes.c.owner == os.environ["HOMILIA_OWNER_WA_ID"]).with_for_update()).mappings().first()
            if not row:
                abort(404)
            if row["state"] != expected_state or row["version"] != version:
                abort(409, "A edição mudou. Atualize o painel.")
            if action == "schedule":
                if expected_state not in EDITABLE_STATES:
                    abort(409, "Esta edição não permite alterar a data de publicação agora.")
                mode = (request.form.get("publish_mode") or "immediate").strip()
                if mode not in ("immediate", "scheduled"):
                    abort(400, "Modo de publicação inválido.")
                if mode == "scheduled":
                    try:
                        dt_br, has_time = parse_br_publish_datetime(
                            request.form.get("publish_date", ""),
                            request.form.get("publish_time", ""),
                        )
                    except ValueError as exc:
                        return redirect(url_for("homilias.stage_episode", token=token, eid=eid, erro=str(exc)), code=303)
                    conn.execute(episodes.update().where(episodes.c.id == eid).values(
                        publish_mode="scheduled", publish_at=dt_br.astimezone(timezone.utc),
                        publish_has_time=has_time))
                else:
                    conn.execute(episodes.update().where(episodes.c.id == eid).values(
                        publish_mode="immediate", publish_at=None, publish_has_time=False))
                return redirect(url_for("homilias.stage_episode", token=token, eid=eid, salvo="publicacao"), code=303)
            if action == "edit":
                if expected_state not in EDITABLE_STATES:
                    abort(409, "Esta edição não permite editar os textos agora.")
                title = (request.form.get("title") or "").strip()
                description = (request.form.get("description") or "").strip()
                if not 0 < len(title) <= 150 or not 0 < len(description) <= 600:
                    return redirect(url_for("homilias.stage_episode", token=token, eid=eid,
                        erro="O título deve ter até 150 caracteres e a descrição até 600 caracteres."), code=303)
                conn.execute(episodes.update().where(episodes.c.id == eid).values(
                    title=title, description=description))
                return redirect(url_for("homilias.stage_episode", token=token, eid=eid, salvo="texto"), code=303)
            if action == "mark-published":
                if expected_state not in MANUAL_PUBLISH_STATES:
                    abort(409, "Esta edição não pode ser marcada como publicada neste estado.")
                spotify_id = extract_spotify_id(request.form.get("spotify_ref", ""))
                updates = {"notice": None}
                if spotify_id:
                    updates["spotify_id"] = spotify_id
                transition(conn, eid, row["owner"], version, expected_state, "published", **updates)
                return redirect(url_for("homilias.stage_episode", token=token, eid=eid, salvo="publicado"), code=303)
            if action == "transcribe":
                if row["state"] not in PREVIEW_STATES:
                    abort(409, "A edição ainda não tem prévia.")
                if not row["transcript"].strip():
                    try:
                        subprocess.Popen([sys.executable, "-m", "homilias.worker", "transcribe-preview",
                                          "--id", eid], start_new_session=True)
                    except OSError:
                        abort(503, "Não foi possível iniciar a transcrição.")
                return redirect(url_for("homilias.stage_episode", token=token, eid=eid,
                                        transcricao="solicitada"), code=303)
            if action == "trash":
                if expected_state not in TRASHABLE:
                    abort(409, "Esta edição não pode ser movida para a lixeira agora.")
                transition(conn, eid, row["owner"], version, expected_state, "trashed",
                           preview=None, notice=None, version=version + 1)
            else:
                retry = expected_state == "preparing" and row["notice"] == "panel"
                if expected_state not in PREPARABLE and not retry:
                    abort(409, "Esta edição não está disponível para preparo.")
                if not source_text(conn, row["source_id"]):
                    abort(409, "Responda ao áudio no WhatsApp com o texto da homilia.")
                # O filho aguarda o commit antes de assumir a edição.
                if not retry:
                    transition(conn, eid, row["owner"], version, expected_state, "preparing", notice="panel")
                try:
                    subprocess.Popen([sys.executable, "-m", "homilias.worker", "prepare-panel",
                                      "--id", eid, "--version", str(version)], start_new_session=True)
                except OSError:
                    abort(503, "Não foi possível iniciar o preparo. Tente novamente.")
        return redirect(url_for("homilias.stage", token=token), code=303)

    @bp.get("/homilias/stage/<token>/episode/<eid>")
    def stage_episode(token, eid):
        check_stage(token)
        with get_engine().connect() as conn:
            row = conn.execute(sa.select(episodes).where(episodes.c.id == eid,
                episodes.c.owner == os.environ["HOMILIA_OWNER_WA_ID"], episodes.c.state != "trashed")).mappings().first()
            if not row:
                abort(404)
            return render_template("homilia.html", job=row, pub=publish_meta(row),
                transcript=row["transcript"], states=STATES, stage_token=token,
                token=row["preview"] if row["state"] in PREVIEW_STATES else None,
                source_text=source_text(conn, row["source_id"]),
                spotify_wizard_url=SPOTIFY_WIZARD_URL,
                editable=row["state"] in EDITABLE_STATES,
                can_mark_published=row["state"] in MANUAL_PUBLISH_STATES)

    @bp.get("/homilias/p/<token>")
    @bp.get("/homilias/p/<token>/<kind>")
    def view(token, kind=None):
        with get_engine().connect() as conn:
            query = sa.select(episodes.c.id, episodes.c.version, episodes.c.title,
                episodes.c.description, episodes.c.source_id, episodes.c.state,
                episodes.c.spotify_id, episodes.c.publish_mode, episodes.c.publish_at,
                episodes.c.publish_has_time)
            if kind is None:
                query = query.add_columns(episodes.c.transcript)
            row = conn.execute(query.where(episodes.c.preview == token,
                episodes.c.state.in_(PREVIEW_STATES))).mappings().first()
            if not row:
                abort(404)
            if kind is None:
                return render_template("homilia.html", job=row, pub=publish_meta(row),
                    transcript=row["transcript"], token=token, states=STATES,
                    panel_token=stage_token(),
                    source_text=source_text(conn, row["source_id"]),
                    spotify_wizard_url=SPOTIFY_WIZARD_URL,
                    editable=False, can_mark_published=False)
            if kind not in ("cover", "audio"):
                abort(404)
            data = asset(conn, row["id"], kind)
            if not data:
                abort(404)
            return send_file(io.BytesIO(data),
                             mimetype={"cover": "image/png", "audio": "audio/mp4"}[kind],
                             as_attachment=request.args.get("download") == "1",
                             download_name=f"homilia-{row['id']}-v{row['version']}-{'capa.png' if kind == 'cover' else 'audio.m4a'}",
                             conditional=True)

    @bp.after_request
    def private(response):
        response.headers.update({"Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer",
                                 "X-Robots-Tag": "noindex, nofollow"})
        return response
    return bp


def is_edit(body):
    return bool(re.match(r"ajustar [0-9a-f]{32} v\d+\s", body, re.I))


def legacy_audio_action(conn, owner, action):
    match = re.fullmatch(r"hom:(act|memo):([0-9a-f]{32}):1", action)
    if not match:
        return None, None
    verb, eid = match.groups()
    transcript = conn.execute(sa.select(episodes.c.transcript).where(
        episodes.c.id == eid, episodes.c.owner == owner)).scalar_one_or_none()
    return (transcript, {"act": "0", "memo": "1"}[verb]) if transcript else (None, None)


