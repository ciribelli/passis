import hashlib
import hmac
import io
import os
import re

import requests
import sqlalchemy as sa
from flask import Blueprint, abort, render_template, send_file

from .store import asset, episodes, transition


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


def preview_routes(db):
    bp = Blueprint("homilias", __name__, template_folder="templates")

    @bp.get("/homilias/p/<token>")
    @bp.get("/homilias/p/<token>/<kind>")
    def view(token, kind=None):
        row = db.session.execute(sa.select(episodes.c.id, episodes.c.version, episodes.c.title,
            episodes.c.description, episodes.c.transcript).where(episodes.c.preview == token,
            episodes.c.state.in_(["preview", "approved", "publishing", "clicked", "published",
                                  "check_spotify"]))).mappings().first()
        if not row:
            abort(404)
        if kind is None:
            return render_template("homilia.html", job=row, token=token)
        if kind not in ("cover", "audio"):
            abort(404)
        data = asset(db.session, row["id"], kind)
        if not data:
            abort(404)
        return send_file(io.BytesIO(data), mimetype={"cover": "image/png", "audio": "audio/mp4"}[kind],
                         conditional=True)

    @bp.after_request
    def private(response):
        response.headers.update({"Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer",
                                 "X-Robots-Tag": "noindex, nofollow"})
        return response
    return bp


def audio_menu(phone, owner, eid, transcript, automatic=False):
    preparing = "Homilia reconhecida. Estou preparando sua prévia.\n\n" if automatic else ""
    if len(preparing + transcript) > 1024:
        for pos in range(0, len(transcript), 4000):
            message(phone, owner, type="text", text={"body": transcript[pos:pos + 4000]})
        body = "Transcrição enviada acima. O que deseja fazer com este áudio?"
    else:
        body = transcript
    body = preparing + body
    rows = [{"id": f"hom:{verb}:{eid}:1", "title": label} for verb, label in (
        ("prepare", "Preparar homilia"), ("act", "Executar ação"), ("memo", "Memorizar"),
        ("dismiss", "Cancelar ações")) if verb != "prepare" or not automatic]
    return message(phone, owner, type="interactive", interactive={"type": "list",
        "body": {"text": body}, "action": {"button": "Ações do áudio",
        "sections": [{"title": "Áudio recebido", "rows": rows}]}})


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


def likely_homily(transcript):
    """Só antecipar o preparo quando houver abertura e vocabulário compatíveis."""
    import unicodedata
    words = unicodedata.normalize("NFKD", transcript.casefold()).encode("ascii", "ignore").decode()
    opening = re.search(r"\b(homilia|meus (queridos )?irmaos|carissimos irmaos|evangelho de hoje)\b",
                        words[:900])
    gospel = re.search(r"\b(evangelho|ano liturgico|liturgia|jesus cristo|tempo comum)\b", words)
    return bool(opening and gospel)
