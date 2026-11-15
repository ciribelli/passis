"""Estado compartilhado pelo webhook e pelo worker. O PostgreSQL arbitra cada transição."""
import secrets
import uuid

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
