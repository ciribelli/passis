import base64
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import wave
from unittest.mock import Mock, patch

from flask import Flask
import imageio_ffmpeg
from PIL import Image
import sqlalchemy as sa

from homilias import channel, prepare, store, transcricao, worker


class TranscriptTests(unittest.TestCase):
    def setUp(self):
        self.engine = sa.create_engine("sqlite://")
        store.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        with self.engine.begin() as conn:
            self.eid = store.offer(conn, "source", "owner", "phone", "media", "")
            store.register_audio(conn, "source", "owner", 10000)
            store.attach_text(conn, "owner", "msg", "Um Deus que convida", 10010)
            conn.execute(store.episodes.update().values(state="preparing"))
            # Existing audio asset allows this test to exercise cover generation separately.
            store.put_asset(conn, self.eid, "audio", b"processed")

    def job(self):
        with self.engine.connect() as conn:
            return conn.execute(store.episodes.select()).mappings().one()

    def client(self):
        app = Flask(__name__)
        app.register_blueprint(channel.preview_routes(lambda: self.engine))
        return app.test_client()

    def test_long_opus_to_cover_and_copyable_preview(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "homilia.ogg"
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-f", "lavfi",
                            "-i", "sine=frequency=440:duration=125", "-c:a", "libopus", str(source)], check=True)
            with self.engine.begin() as conn:
                store.put_asset(conn, self.eid, "source", source.read_bytes())
        parts = ["Primeira parte.", "Um lugar preparado à mesa.", "Última parte. Amém."]
        durations = []

        def recognize(*, file, language, model):
            self.assertEqual(language, "pt")
            with wave.open(file, "rb") as clip:
                durations.append(clip.getnframes() / clip.getframerate())
            return Mock(text=parts[len(durations) - 1])

        ai = Mock()
        ai.audio.transcriptions.create.side_effect = recognize
        scene = "Um lugar preparado à mesa sob luz suave."
        full_text = "\n\n".join(parts)

        def brief(**request):
            material = json.loads(request["messages"][1]["content"])
            self.assertEqual(material["transcricao_para_capa"], full_text)
            self.assertEqual(material["texto_encaminhado_pelo_padre"], "Um Deus que convida")
            content = json.dumps({
                "title": "O convite",
                "description": "Acolher.",
                "cover_title": "O convite à mesa",
                "cover_subtitle": "28º Domingo do Tempo Comum",
                "scene": scene,
            })
            return Mock(choices=[Mock(message=Mock(content=content))])

        ai.chat.completions.create.side_effect = brief
        buf = BytesIO()
        Image.new("RGB", (512, 512), (90, 75, 48)).save(buf, format="PNG")
        png = buf.getvalue()
        with patch.dict(os.environ, HOMILIA_API_KEY="only-homilias"), patch.object(
                prepare, "OpenAI", return_value=ai) as client, patch.object(
                prepare.requests, "post") as image:
            image.return_value.json.return_value = {"data": [{"b64_json": base64.b64encode(png).decode()}]}
            prepare.prepare(self.engine, self.job())
            client.assert_called_once_with(api_key="only-homilias", timeout=180)
            self.assertEqual(image.call_args.kwargs["headers"]["Authorization"], "Bearer only-homilias")
            self.assertIn(scene, image.call_args.kwargs["json"]["prompt"])
            self.assertIn("Não inclua títulos, legendas", image.call_args.kwargs["json"]["prompt"])
        self.assertEqual(len(durations), 3)
        self.assertLess(max(durations), 60)
        self.assertAlmostEqual(sum(durations), 125, places=1)
        row = self.job()
        self.assertEqual(row["transcript"], full_text)
        cfg = json.loads(row["cover_config"])
        self.assertEqual(cfg["title"], "O convite à mesa")
        self.assertEqual(cfg["subtitle"], "28º Domingo do Tempo Comum")
        self.assertEqual(cfg["scene"], scene)
        with self.engine.connect() as conn:
            self.assertTrue(store.asset(conn, self.eid, "cover_bg"))
            self.assertTrue(store.asset(conn, self.eid, "cover").startswith(b"\x89PNG\r\n\x1a\n"))
        view = self.client().get("/homilias/p/" + row["preview"]).get_data(as_text=True)
        self.assertIn('data-copy="episode-transcript"', view)
        self.assertIn(full_text, view)
        ai.audio.transcriptions.create.reset_mock()
        self.assertEqual(transcricao.episode_transcript(self.engine, ai, row, b""), full_text)
        ai.audio.transcriptions.create.assert_not_called()

    @patch.dict(os.environ, HOMILIA_OWNER_WA_ID="owner", HOMILIA_STAGE_TOKEN="secret", HOMILIA_API_KEY="only")
    def test_backfill_preserves_approval_cover_and_version(self):
        with self.engine.begin() as conn:
            conn.execute(store.episodes.update().values(state="approved", version=3, preview="old"))
            store.put_asset(conn, self.eid, "cover", b"old-cover")
            conn.connection.driver_connection.create_function("pg_try_advisory_xact_lock", 1, lambda key: 1)
        client = self.client()
        self.assertNotIn(b'data-copy="episode-transcript"', client.get("/homilias/p/old").data)
        with patch("openai.OpenAI"), patch.object(transcricao, "transcribe", return_value="Paz <e> bem.") as recognize:
            worker.transcribe_preview(self.engine, self.eid)
            worker.transcribe_preview(self.engine, self.eid)
        recognize.assert_called_once()
        row = self.job()
        self.assertEqual((row["state"], row["version"], row["preview"]), ("approved", 3, "old"))
        self.assertEqual(client.get("/homilias/p/old/cover").data, b"old-cover")
        self.assertIn(b"Paz &lt;e&gt; bem.", client.get("/homilias/p/old").data)
