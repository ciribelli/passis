"""Estado compartilhado pelo webhook e pelo worker. O PostgreSQL arbitra cada transição."""
import os
import secrets
from functools import lru_cache
import uuid
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

metadata = sa.MetaData()
episodes = sa.Table(
    "homilia_episodes", metadata,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("source_id", sa.Text, unique=True, nullable=False),
    sa.Column("owner", sa.Text, nullable=False),
    sa.Column("phone", sa.Text, nullable=False),
    sa.Column("media", sa.Text, nullable=False),
    sa.Column("transcript", sa.Text, nullable=False),
    sa.Column("state", sa.Text, nullable=False, index=True),
    sa.Column("version", sa.Integer, nullable=False),
    sa.Column("note", sa.Text),
    sa.Column("title", sa.Text),
    sa.Column("description", sa.Text),
    sa.Column("preview", sa.Text, unique=True),
    sa.Column("spotify_id", sa.Text),
    sa.Column("notice", sa.Text),
)
assets = sa.Table(
    "homilia_assets", metadata,
    sa.Column("episode", sa.ForeignKey(episodes.c.id), primary_key=True),
    sa.Column("kind", sa.String(10), primary_key=True),
    sa.Column("data", sa.LargeBinary, nullable=False),
)


# Registro do áudio para associar a mensagem encaminhada em seguida.
incoming = sa.Table(
    "homilia_incoming", metadata,
    sa.Column("source_id", sa.Text, primary_key=True),
    sa.Column("owner", sa.Text, nullable=False, index=True),
    sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("text_id", sa.Text, unique=True),
    sa.Column("source_text", sa.Text),
)


@lru_cache(maxsize=1)
def get_engine():
    """Conexão exclusiva das homilias, inicializada somente quando necessária."""
    url = os.environ["HOMILIA_DATABASE_URL"]
    return sa.create_engine(url, pool_pre_ping=True)


def register_audio(conn, source, owner, timestamp):
    dt = datetime.fromtimestamp(int(timestamp), timezone.utc)
    result = conn.execute(insert(incoming).values(source_id=source, owner=owner, received_at=dt)
                          .on_conflict_do_nothing(index_elements=["source_id"]))
    if not result.rowcount:
        return
    pending = conn.execute(sa.select(incoming).where(
        incoming.c.owner == owner, incoming.c.source_id.like("text:%"),
        incoming.c.received_at >= dt - timedelta(minutes=5),
        incoming.c.received_at <= dt).with_for_update()).mappings().all()
    if len(pending) == 1:
        entry = pending[0]
        # Remover a linha temporária primeiro libera a restrição única de text_id.
        conn.execute(incoming.delete().where(incoming.c.source_id == entry["source_id"]))
        conn.execute(incoming.update().where(incoming.c.source_id == source).values(
            source_text=entry["source_text"], text_id=entry["text_id"]))


def attach_text(conn, owner, message_id, body, timestamp, reply_id=None):
    """Aceita uma resposta explícita ou texto encaminhado até 2 minutos após um áudio."""
    if conn.execute(sa.select(incoming.c.source_id).where(incoming.c.text_id == message_id)).first():
        return "duplicate"
    dt = datetime.fromtimestamp(int(timestamp), timezone.utc)
    query = sa.select(incoming).where(incoming.c.owner == owner, ~incoming.c.source_id.like("text:%"))
    if reply_id:
        query = query.where(incoming.c.source_id == reply_id)
    else:
        query = query.where(incoming.c.received_at <= dt,
                            incoming.c.received_at >= dt - timedelta(minutes=2),
                            incoming.c.source_text.is_(None))
    rows = conn.execute(query.with_for_update()).mappings().all()
    if len(rows) != 1:
        if not rows and not reply_id:
            import re
            if re.search(r"\b(homilia|evangelho|domingo)\b", body, re.IGNORECASE):
                conn.execute(insert(incoming).values(source_id="text:" + message_id,
                    owner=owner, received_at=dt, text_id=message_id, source_text=body)
                    .on_conflict_do_nothing())
                return "waiting_audio"
        return "ambiguous" if len(rows) > 1 else "none"
    source = rows[0]["source_id"]
    # Uma mensagem encaminhada não substitui outra que já foi associada.
    if rows[0]["source_text"] and not reply_id:
        return "none"
    episode = conn.execute(sa.select(episodes).where(episodes.c.source_id == source)
                           .with_for_update()).mappings().first()
    if episode and episode["state"] in ("approved", "publishing", "clicked", "published", "check_spotify"):
        return "closed"
    conn.execute(incoming.update().where(incoming.c.source_id == source)
                 .values(text_id=message_id, source_text=body))
    if episode and episode["state"] == "waiting_text":
        conn.execute(episodes.update().where(episodes.c.id == episode["id"])
                     .values(state="queued", notice=None))
    elif episode and episode["state"] in ("preparing", "preview"):
        conn.execute(episodes.update().where(episodes.c.id == episode["id"]).values(
            state="queued", version=episode["version"] + 1, preview=None, notice=None))
    return "attached"


def source_text(conn, source):
    return conn.execute(sa.select(incoming.c.source_text).where(
        incoming.c.source_id == source)).scalar_one_or_none()


def ready(conn, source, now=None):
    row = conn.execute(sa.select(incoming).where(incoming.c.source_id == source)).mappings().first()
    if not row or row["source_text"]:
        return True
    current = now or datetime.now(timezone.utc)
    received = row["received_at"]
    if received.tzinfo is None:
        received = received.replace(tzinfo=timezone.utc)
    return current >= received + timedelta(minutes=2)


def offer(conn, source, owner, phone, media, transcript):
    eid = uuid.uuid4().hex
    conn.execute(insert(episodes).values(id=eid, source_id=source, owner=owner, phone=phone,
                 media=media, transcript=transcript, state="offered", version=1)
                 .on_conflict_do_nothing(index_elements=["source_id"]))
    return conn.execute(sa.select(episodes.c.id).where(episodes.c.source_id == source)).scalar_one()


def transition(conn, eid, owner, expected_version, before, after, **values):
    return conn.execute(episodes.update().where(
        episodes.c.id == eid, episodes.c.owner == owner, episodes.c.version == expected_version,
        episodes.c.state == before).values(state=after, **values)).rowcount == 1


def put_asset(conn, eid, kind, content):
    stmt = insert(assets).values(episode=eid, kind=kind, data=content)
    conn.execute(stmt.on_conflict_do_update(index_elements=["episode", "kind"],
                                            set_={"data": stmt.excluded.data}))


def asset(conn, eid, kind):
    return conn.execute(sa.select(assets.c.data).where(
        assets.c.episode == eid, assets.c.kind == kind)).scalar_one_or_none()


def save_preview(conn, job, audio, cover, title, description):
    if not transition(conn, job["id"], job["owner"], job["version"], "preparing", "preview",
                      preview=secrets.token_urlsafe(32), title=title, description=description,
                      notice="preview"):
        raise RuntimeError("A edição mudou durante o preparo.")
    put_asset(conn, job["id"], "audio", audio)
    put_asset(conn, job["id"], "cover", cover)
