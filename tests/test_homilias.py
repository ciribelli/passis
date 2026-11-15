import hashlib
import hmac
import os
import unittest
from unittest.mock import patch

from flask import Flask
import sqlalchemy as sa

from homilias import channel, store, worker


class EpisodesTest(unittest.TestCase):
    def setUp(self):
        self.engine = sa.create_engine("sqlite://")
        store.metadata.create_all(self.engine)
        self.conn = self.engine.connect()
        self.eid = store.offer(self.conn, "wamid1", "owner", "phone", "media", "transcrição")
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        self.engine.dispose()

    def row(self):
        return self.conn.execute(store.episodes.select()).mappings().one()

    def action(self, verb, version=1, sender="owner"):
        return channel.handle(self.conn, sender, f"hom:{verb}:{self.eid}:{version}", "")

    def preview(self):
        self.action("prepare")
        self.assertTrue(store.transition(self.conn, self.eid, "owner", 1, "queued", "preparing"))
        store.save_preview(self.conn, self.row(), b"final audio", b"image", "Título", "Descrição")

    def test_duplicate_audio_and_reviewer_only(self):
        self.assertEqual(store.offer(self.conn, "wamid1", "owner", "phone", "media", "x"), self.eid)
        self.action("approve")
        self.assertEqual(self.row()["state"], "offered")
        self.preview()
        self.action("approve", sender="other")
        self.assertEqual(self.row()["state"], "preview")
        self.action("approve")
        self.assertIn("já foi usado", self.action("approve"))
        self.assertEqual(self.row()["state"], "approved")

    def test_edit_invalidates_approval_and_link(self):
        self.preview()
        self.assertTrue(self.row()["preview"])
        channel.handle(self.conn, "owner", "", f"ajustar {self.eid} v1 mude a capa")
        self.assertEqual(self.row()["version"], 2)
        self.assertIsNone(self.row()["preview"])
        self.action("approve")
        self.assertEqual(self.row()["state"], "queued")
        store.transition(self.conn, self.eid, "owner", 2, "queued", "preparing")
        store.save_preview(self.conn, self.row(), b"audio", b"cover2", "Novo", "Descrição")
        self.action("approve", 1)
        self.assertEqual(self.row()["state"], "preview")
        self.action("approve", 2)
        self.assertEqual(self.row()["state"], "approved")

    def test_preview_serves_exact_bytes_and_cancel_revokes_access(self):
        self.preview()
        app = Flask(__name__)
        class Database:
            session = self.conn
        app.register_blueprint(channel.preview_routes(Database))
        client = app.test_client()
        url = "/homilias/p/" + self.row()["preview"]
        self.assertIn("Título", client.get(url).get_data(as_text=True))
        self.assertEqual(client.get(url + "/audio").data, b"final audio")
        self.assertEqual(client.get(url + "/cover").data, b"image")
        self.assertEqual(client.post(url).status_code, 405)
        self.action("cancel")
        self.assertEqual(client.get(url + "/audio").status_code, 404)

    def test_homily_and_ordinary_audio(self):
        self.assertTrue(channel.likely_homily("Meus queridos irmãos e amigos em nosso Senhor Jesus Cristo."))
        self.assertFalse(channel.likely_homily("Passis, qual é a previsão do tempo para hoje?"))
        self.assertEqual(channel.legacy_audio_action(self.conn, "owner", f"hom:act:{self.eid}:1"),
                         ("transcrição", "0"))
        self.assertEqual(channel.legacy_audio_action(self.conn, "other", f"hom:memo:{self.eid}:1"),
                         (None, None))

    @patch.dict(os.environ, {"WHATSAPP_APP_SECRET": "test-key"})
    def test_webhook_signature(self):
        signature = "sha256=" + hmac.new(b"test-key", b"payload", hashlib.sha256).hexdigest()
        self.assertTrue(channel.signed(b"payload", signature))
        self.assertFalse(channel.signed(b"other payload", signature))
        self.assertFalse(channel.signed(b"payload", None))

    @patch("homilias.spotify.publish")
    def test_worker_requires_approval_and_never_repeats_uncertain_click(self, publish):
        self.preview()
        self.conn.commit()
        with patch.object(worker, "notify"):
            worker.process(self.engine, self.row())
        publish.assert_not_called()
        self.action("approve")
        self.conn.commit()
        def interrupted(engine, job):
            with engine.begin() as c:
                store.transition(c, self.eid, "owner", 1, "publishing", "clicked", spotify_id="test")
            raise TimeoutError("simulated ambiguous response")
        publish.side_effect = interrupted
        with self.assertLogs(worker.log, level="ERROR"):
            worker.process(self.engine, self.row())
        with patch("homilias.spotify.confirmed", return_value=True):
            worker.process(self.engine, self.row())
        self.assertEqual(self.row()["state"], "published")
        publish.assert_called_once()


if __name__ == "__main__":
    unittest.main()
