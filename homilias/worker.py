import argparse
import logging
import os
import time

from dotenv import load_dotenv
import sqlalchemy as sa

from . import channel, store

log = logging.getLogger(__name__)
jobs = store.episodes


def notify(job):
    eid, version = job["id"], job["version"]
    phone, owner = job["phone"], job["owner"]
    if job["notice"] == "preview":
        url = os.environ["HOMILIA_PUBLIC_URL"].rstrip("/") + "/homilias/p/" + job["preview"]
        body = (f"{job['title']}\n\n{job['description'][:250]}\n\nCapa e áudio · v{version}\n{url}\n"
                f"Para pedir uma mudança, envie: ajustar {eid} v{version} seguido do pedido.")
        channel.buttons(phone, owner, body, [(f"hom:approve:{eid}:{version}", "Aprovar e publicar"),
                                             (f"hom:cancel:{eid}:{version}", "Cancelar edição")])
    elif job["notice"] == "failed":
        channel.buttons(phone, owner, "O preparo da homilia falhou. Se a mídia expirou, reenvie o áudio.",
                        [(f"hom:retry:{eid}:{version}", "Tentar novamente")])
    elif job["notice"] == "published":
        from .spotify import public_url
        channel.message(phone, owner, type="text", text={"body": f"Publicado: {public_url(job['spotify_id'])}"})
    else:
        channel.message(phone, owner, type="text", text={"body":
            f"A edição {eid} v{version} precisa de conferência no Spotify. "
            "A publicação ainda não foi confirmada."})


def process(engine, job):
    eid, owner, version = job["id"], job["owner"], job["version"]
    state = job["state"]

    def move(before, after, **values):
        with engine.begin() as conn:
            return store.transition(conn, eid, owner, version, before, after, **values)

    if state == "queued":
        with engine.begin() as conn:
            text = store.source_text(conn, job["source_id"])
            timed_out = store.ready(conn, job["source_id"])
        if not text:
            if timed_out and move("queued", "waiting_text"):
                channel.message(job["phone"], owner, type="text", text={"body":
                    "Envie o texto do padre respondendo ao áudio encaminhado para eu preparar a homilia."})
            return
    if state == "queued" and move("queued", "preparing"):
        try:
            from .prepare import prepare
            prepare(engine, job)
        except Exception:
            log.exception("Falha no preparo de %s", eid)
            move("preparing", "failed", notice="failed")
    elif state == "approved" and move("approved", "publishing"):
        try:
            from .spotify import publish
            publish(engine, job)
        except Exception:
            log.exception("Falha no Spotify para %s", eid)
            move("publishing", "check_spotify", notice="check")
    elif state == "clicked":
        from .spotify import confirmed
        if confirmed(job["spotify_id"], job["title"]):
            move("clicked", "published", notice="published")
            return
        elif job["notice"] is None:
            move("clicked", "clicked", notice="check")
    if job["notice"] in ("preview", "failed", "published", "check"):
        notify(job)
        with engine.begin() as conn:
            conn.execute(jobs.update().where(jobs.c.id == eid, jobs.c.version == version,
                jobs.c.state == state, jobs.c.notice == job["notice"]).values(notice=
                "waiting" if state == "clicked" else None))


def run(engine, once):
    # Uma única sessão mantém o lock durante o ciclo de vida deste worker.
    # Após uma queda, só repetir preparo; publicação interrompida exige reconciliação.
    with engine.connect() as lock:
        if not lock.scalar(sa.text("SELECT pg_try_advisory_lock(1049837261)")):
            raise SystemExit("Outro worker de homilias já está ativo.")
        lock.commit()
        with engine.begin() as conn:
            conn.execute(jobs.update().where(jobs.c.state == "preparing").values(state="queued"))
            conn.execute(jobs.update().where(jobs.c.state == "publishing")
                         .values(state="check_spotify", notice="check"))
        while True:
            lock.scalar(sa.text("SELECT 1"))
            lock.commit()
            with engine.begin() as conn:
                rows = conn.execute(sa.select(jobs).where(sa.or_(
                    jobs.c.state.in_(["queued", "approved", "clicked"]),
                    jobs.c.notice.in_(["preview", "failed", "published", "check"])
                ), jobs.c.owner == os.environ["HOMILIA_OWNER_WA_ID"])).mappings().all()
            for row in rows:
                try:
                    process(engine, row)
                except Exception:
                    log.exception("Erro ao processar edição %s", row["id"])
            if once:
                break
            time.sleep(30)


def main():
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["init", "login", "run", "once", "resume-draft"])
    parser.add_argument("--id")
    args = parser.parse_args()
    if args.command == "login":
        from .spotify import login
        login()
        return
    engine = sa.create_engine(os.environ["DATABASE_URL_AZURE"], pool_pre_ping=True)
    if args.command == "init":
        store.metadata.create_all(engine)
    elif args.command == "resume-draft":
        # Apenas falhas anteriores ao clique podem retomar pelo mesmo rascunho.
        with engine.begin() as conn:
            n = conn.execute(jobs.update().where(jobs.c.id == args.id,
                jobs.c.owner == os.environ["HOMILIA_OWNER_WA_ID"],
                jobs.c.state == "check_spotify").values(state="approved", notice=None)).rowcount
            if not n:
                raise SystemExit("Nenhuma publicação pré-clique pendente para este ID.")
    else:
        run(engine, args.command == "once")


if __name__ == "__main__":
    main()
