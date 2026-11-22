import base64
from io import BytesIO
import json
import os
import unittest
from unittest.mock import Mock, patch

from flask import Flask
import numpy as np
from PIL import Image
import sqlalchemy as sa

from homilias import channel, cover, prepare, store, worker


def _make_sample_image(width=900, height=600, color=(120, 145, 200), fmt="PNG"):
    img = Image.new("RGB", (width, height), color)
    buf = BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


class CoverPipelineUnitTests(unittest.TestCase):
    def test_normalize_source_image_preserves_aspect_and_handles_rgba(self):
        rgba = Image.new("RGBA", (1200, 800), (140, 100, 60, 180))
        buf = BytesIO()
        rgba.save(buf, format="PNG")
        normalized = cover.normalize_source_image(buf.getvalue(), max_side=600)
        self.assertEqual(cover.detect_image_mimetype(normalized), "image/jpeg")
        with Image.open(BytesIO(normalized)) as out:
            self.assertEqual(out.mode, "RGB")
            self.assertEqual(out.size, (600, 400))

    def test_normalize_source_image_rejects_small_and_invalid_inputs(self):
        tiny = _make_sample_image(80, 80)
        with self.assertRaises(ValueError):
            cover.normalize_source_image(tiny)
        with self.assertRaises(ValueError):
            cover.normalize_source_image(b"not-an-image")
        with self.assertRaises(ValueError):
            cover.normalize_source_image(b"")

    def test_validate_remote_url_blocks_private_and_non_http(self):
        for bad in ("file:///etc/passwd", "ftp://example.com/a.jpg", "http://localhost/a.png", "http://127.0.0.1/a.png"):
            with self.assertRaises(ValueError):
                cover.validate_remote_url(bad)

        with patch("homilias.cover.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("10.0.0.5", 443))]):
            with self.assertRaises(ValueError):
                cover.validate_remote_url("https://internal.example/image.jpg")

        with patch("homilias.cover.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
            self.assertEqual(
                cover.validate_remote_url("https://example.org/painting.jpg"),
                "https://example.org/painting.jpg",
            )

    def test_fetch_image_from_url_downloads_and_normalizes(self):
        raw = _make_sample_image(800, 500, (160, 120, 70), fmt="JPEG")
        resp = Mock(status_code=200, headers={"Content-Type": "image/jpeg"})
        resp.iter_content.return_value = [raw[:200], raw[200:]]
        session = Mock()
        session.get.return_value = resp

        with patch("homilias.cover.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
            data = cover.fetch_image_from_url("https://example.org/renaissance.jpg", session=session)
        with Image.open(BytesIO(data)) as out:
            self.assertEqual(out.size, (800, 500))

    def test_crop_square_respects_focus_and_zoom(self):
        # Esquerda vermelha, direita azul para validar deslocamento horizontal.
        img = Image.new("RGB", (600, 300), (200, 40, 40))
        right = Image.new("RGB", (300, 300), (40, 60, 200))
        img.paste(right, (300, 0))

        left_crop = cover.crop_square(img, crop_x=0.0, crop_y=0.5, zoom=1.0, size=200)
        right_crop = cover.crop_square(img, crop_x=1.0, crop_y=0.5, zoom=1.0, size=200)
        self.assertGreater(left_crop.getpixel((100, 100))[0], 170)
        self.assertGreater(right_crop.getpixel((100, 100))[2], 170)

    def test_color_grade_channel_tames_cold_blue_sky(self):
        sky = Image.new("RGB", (200, 200), (80, 130, 235))
        graded = cover.apply_color_grade(sky, grade="channel")
        orig_arr = np.asarray(sky, dtype=np.float32)
        grad_arr = np.asarray(graded, dtype=np.float32)
        # Canal azul excessivo é suavizado e a cena fica mais quente/harmonizada.
        self.assertLess(grad_arr[..., 2].mean(), orig_arr[..., 2].mean() - 25)
        self.assertGreater(grad_arr[..., 0].mean(), orig_arr[..., 0].mean())

    def test_auto_scrim_adapts_to_bright_vs_dark_top(self):
        bright = Image.new("RGB", (256, 256), (235, 235, 230))
        dark = Image.new("RGB", (256, 256), (25, 24, 18))
        bright_scrim = cover.apply_scrim_and_vignette(bright, layout="top", scrim="auto")
        dark_scrim = cover.apply_scrim_and_vignette(dark, layout="top", scrim="auto")
        # Imagem clara recebe escurecimento substancial no topo; imagem já escura quase não muda.
        bright_drop = cover.measure_band_luminance(bright, 0.0, 0.2) - cover.measure_band_luminance(bright_scrim, 0.0, 0.2)
        dark_drop = abs(cover.measure_band_luminance(dark, 0.0, 0.2) - cover.measure_band_luminance(dark_scrim, 0.0, 0.2))
        self.assertGreater(bright_drop, 0.30)
        self.assertLess(dark_drop, 0.05)

    def test_render_cover_modes_and_layouts(self):
        raw = _make_sample_image(600, 400, (110, 95, 65))
        for layout in ("top", "bottom", "none"):
            cfg = cover.default_cover_config(
                title="Participar da alegria de Deus com fidelidade",
                subtitle="33º Domingo do Tempo Comum",
                grade="channel",
                scrim="auto",
                layout=layout,
            )
            png = cover.render_cover(raw, cfg, size=512)
            self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
            with Image.open(BytesIO(png)) as out:
                self.assertEqual(out.size, (512, 512))

        # Modo 'final' não sobrepõe texto nem scrim
        final_cfg = cover.default_cover_config(title="Ignorado", mode="final", grade="original")
        solid = _make_sample_image(400, 400, (200, 180, 120))
        final_png = cover.render_cover(solid, final_cfg, size=256)
        with Image.open(BytesIO(final_png)) as out:
            self.assertEqual(out.getpixel((128, 30)), (200, 180, 120))


class CoverStageIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = sa.create_engine("sqlite://")
        store.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        with self.engine.begin() as conn:
            self.eid = store.offer(conn, "wamid1", "owner", "phone", "media", "Transcrição de teste")
            store.register_audio(conn, "wamid1", "owner", 1000)
            store.attach_text(conn, "owner", "t1", "33º Domingo do Tempo Comum", 1010)
            store.transition(conn, self.eid, "owner", 1, "offered", "preparing")
            store.save_preview(conn, self._row(conn), b"audio", b"legacy-cover", "Título Spotify", "Descrição")

    def _row(self, conn=None):
        if conn is not None:
            return conn.execute(store.episodes.select().where(store.episodes.c.id == self.eid)).mappings().one()
        with self.engine.connect() as c:
            return c.execute(store.episodes.select().where(store.episodes.c.id == self.eid)).mappings().one()

    def _client(self):
        app = Flask(__name__)
        app.register_blueprint(channel.preview_routes(lambda: self.engine))
        return app.test_client()

    @patch.dict(os.environ, {"HOMILIA_STAGE_TOKEN": "stage-tok", "HOMILIA_OWNER_WA_ID": "owner"})
    def test_upload_external_painting_and_recompose_non_destructively(self):
        client = self._client()
        base = f"/homilias/stage/stage-tok/episode/{self.eid}"

        # Episódio legado sem cover_bg mostra mensagem amigável se tentar recompor antes do Passo 1.
        r_legacy = client.post(
            f"{base}/cover-render",
            data={"version": "1", "state": "preview", "cover_title": "Novo"},
        )
        self.assertEqual(r_legacy.status_code, 303)
        self.assertIn("erro=", r_legacy.headers["Location"])

        # Passo 1: upload de uma pintura renascentista retangular como imagem-base (composed).
        painting = _make_sample_image(1200, 800, (95, 115, 165), fmt="JPEG")
        r_upload = client.post(
            f"{base}/cover-source",
            data={
                "version": "1",
                "state": "preview",
                "cover_mode": "composed",
                "cover_grade": "channel",
                "source_ref": "Caravaggio · Domínio público",
                "cover_file": (BytesIO(painting), "caravaggio.jpg"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(r_upload.status_code, 303)
        self.assertIn("salvo=capa_origem", r_upload.headers["Location"])

        # Asset cover_bg e cover final PNG estão disponíveis no stage.
        r_bg = client.get(f"{base}/cover_bg")
        self.assertEqual(r_bg.status_code, 200)
        self.assertEqual(r_bg.mimetype, "image/jpeg")

        r_cover_1 = client.get(f"{base}/cover")
        self.assertEqual(r_cover_1.status_code, 200)
        self.assertEqual(r_cover_1.mimetype, "image/png")
        first_cover_bytes = r_cover_1.data
        self.assertTrue(first_cover_bytes.startswith(b"\x89PNG\r\n\x1a\n"))

        # Passos 2 e 3: ajusta recorte, posição inferior e título estruturado sem reenviar imagem.
        r_render = client.post(
            f"{base}/cover-render",
            data={
                "version": "1",
                "state": "preview",
                "crop_x": "0.25",
                "crop_y": "0.15",
                "zoom": "1.35",
                "grade": "balanced",
                "scrim": "strong",
                "layout": "bottom",
                "cover_title": "A alegria do encontro",
                "cover_subtitle": "33º Domingo do Tempo Comum",
                "cover_brand": "Nos Passos de Cristo",
                "cover_signature": "Pe. Marcus Vinícius Macedo",
                "source_ref": "Caravaggio · Domínio público",
            },
        )
        self.assertEqual(r_render.status_code, 303)
        self.assertIn("salvo=capa", r_render.headers["Location"])

        second_cover_bytes = client.get(f"{base}/cover").data
        self.assertNotEqual(first_cover_bytes, second_cover_bytes)
        cfg = json.loads(self._row()["cover_config"])
        self.assertEqual(cfg["source"], "upload")
        self.assertEqual(cfg["layout"], "bottom")
        self.assertEqual(cfg["grade"], "balanced")
        self.assertEqual(cfg["title"], "A alegria do encontro")
        self.assertAlmostEqual(cfg["zoom"], 1.35)

        # Página do episódio renderiza o Estúdio da capa com os novos valores.
        html = client.get(base).get_data(as_text=True)
        self.assertIn("A alegria do encontro", html)
        self.assertIn("Caravaggio · Domínio público", html)
        self.assertIn("crop-stage", html)

    @patch.dict(os.environ, {"HOMILIA_STAGE_TOKEN": "stage-tok", "HOMILIA_OWNER_WA_ID": "owner"})
    def test_import_image_from_url_in_final_mode(self):
        client = self._client()
        base = f"/homilias/stage/stage-tok/episode/{self.eid}"
        ready_art = cover.normalize_source_image(_make_sample_image(800, 800, (140, 110, 60)))

        with patch("homilias.cover.fetch_image_from_url", return_value=ready_art) as fetcher:
            resp = client.post(
                f"{base}/cover-source",
                data={
                    "version": "1",
                    "state": "preview",
                    "cover_url": "https://upload.wikimedia.org/example.jpg",
                    "cover_mode": "final",
                    "cover_grade": "original",
                },
            )
        fetcher.assert_called_once_with("https://upload.wikimedia.org/example.jpg")
        self.assertEqual(resp.status_code, 303)
        self.assertIn("salvo=capa_origem", resp.headers["Location"])
        cfg = json.loads(self._row()["cover_config"])
        self.assertEqual(cfg["source"], "url")
        self.assertEqual(cfg["mode"], "final")

    @patch.dict(os.environ, {"HOMILIA_STAGE_TOKEN": "stage-tok", "HOMILIA_OWNER_WA_ID": "owner", "HOMILIA_API_KEY": "k"})
    @patch("homilias.channel.subprocess.Popen")
    def test_regen_cover_bg_action_and_worker(self, popen):
        client = self._client()
        base = f"/homilias/stage/stage-tok/episode/{self.eid}"

        resp = client.post(
            f"{base}/cover-regen-bg",
            data={
                "version": "1",
                "state": "preview",
                "cover_scene": "Mãos partilhando o pão sobre mesa de madeira sob luz dourada.",
            },
        )
        self.assertEqual(resp.status_code, 303)
        self.assertIn("salvo=capa_ia", resp.headers["Location"])
        self.assertEqual(popen.call_args.args[0][-3:], ["regen-cover-bg", "--id", self.eid])

        # Executa o worker regen_cover_bg diretamente com OpenAI mockado.
        with self.engine.begin() as conn:
            conn.connection.driver_connection.create_function("pg_try_advisory_xact_lock", 1, lambda key: 1)
        ai_png = _make_sample_image(512, 512, (88, 72, 42))
        with patch("homilias.cover.requests.post") as post:
            post.return_value.json.return_value = {"data": [{"b64_json": base64.b64encode(ai_png).decode()}]}
            worker.regen_cover_bg(self.engine, self.eid)
            self.assertIn("Mãos partilhando o pão", post.call_args.kwargs["json"]["prompt"])

        cfg = json.loads(self._row()["cover_config"])
        self.assertEqual(cfg["source"], "ai")
        self.assertEqual(cfg["mode"], "composed")
        with self.engine.connect() as conn:
            self.assertTrue(store.asset(conn, self.eid, "cover_bg"))
            self.assertTrue(store.asset(conn, self.eid, "cover").startswith(b"\x89PNG\r\n\x1a\n"))

    @patch.dict(os.environ, {"HOMILIA_API_KEY": "k"})
    def test_prepare_preserves_existing_cover_bg_when_only_text_changes(self):
        # Simula episódio que já possui uma pintura renascentista carregada em cover_bg.
        bg = cover.normalize_source_image(_make_sample_image(900, 600, (120, 90, 50)))
        cfg = cover.default_cover_config(
            title="Título antigo",
            source="upload",
            mode="composed",
            grade="channel",
            layout="bottom",
            source_ref="Rafael · Domínio público",
        )
        with self.engine.begin() as conn:
            store.put_asset(conn, self.eid, "source", b"fake-source")
            store.put_asset(conn, self.eid, "cover_bg", bg)
            conn.execute(store.episodes.update().where(store.episodes.c.id == self.eid).values(
                state="preparing",
                cover_config=cover.dump_cover_config(cfg),
            ))

        ai = Mock()
        ai.chat.completions.create.return_value = Mock(
            choices=[Mock(message=Mock(content=json.dumps({
                "title": "Novo título no Spotify",
                "description": "Nova descrição.",
                "cover_title": "Novo título curto",
                "cover_subtitle": "34º Domingo do Tempo Comum",
                "scene": "Cena qualquer",
                "change_cover": False,
                "change_audio": False,
            })))]
        )
        with patch.object(prepare, "OpenAI", return_value=ai), \
             patch.object(prepare, "episode_transcript", return_value="Transcrição completa"), \
             patch.object(prepare.requests, "post") as img_post:
            prepare.prepare(self.engine, self._row())
            # Não deve chamar API de imagem pois cover_bg já existe e change_cover=False!
            img_post.assert_not_called()

        updated_cfg = json.loads(self._row()["cover_config"])
        self.assertEqual(updated_cfg["source"], "upload")
        self.assertEqual(updated_cfg["layout"], "bottom")
        self.assertEqual(updated_cfg["title"], "Novo título curto")
        self.assertEqual(updated_cfg["subtitle"], "34º Domingo do Tempo Comum")


if __name__ == "__main__":
    unittest.main()

