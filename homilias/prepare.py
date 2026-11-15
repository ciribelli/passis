import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import imageio_ffmpeg
import requests
from openai import OpenAI

from . import store

HERE = Path(__file__).parent


def prepare(engine, job):
    eid = job["id"]
    with engine.begin() as conn:
        source_text = store.source_text(conn, job["source_id"])
        original = store.asset(conn, eid, "source")
        previous_audio = store.asset(conn, eid, "audio")
        previous_cover = store.asset(conn, eid, "cover")
    if original is None:
        from send_msg import get_url_wapp_media
        response = requests.get(get_url_wapp_media(job["media"]),
            headers={"Authorization": "Bearer " + os.environ["WHATSAPP_TOKEN"]}, timeout=120)
        response.raise_for_status()
        original = response.content
        with engine.begin() as conn:
            store.put_asset(conn, eid, "source", original)

    client = OpenAI(timeout=180)
    brief = client.chat.completions.create(
        model=os.getenv("HOMILIA_TEXT_MODEL", "gpt-4.1-mini"),
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": (
            "Edite uma homilia de Nos Passos de Cristo, Pe. Marcus Vinícius Macedo. "
            "Use a transcrição somente como fonte. Produza JSON com title (até 150 caracteres), "
            "description (até 600 caracteres, diferente do título), scene (um motivo visual da homilia), "
            "change_cover e change_audio (booleanos), brightness_db (ajuste adicional entre -3 e 3). "
            "O pedido editorial pode solicitar ajustes na capa, textos ou brilho da voz. "
            "Em revisão preserve tudo o que o pedido não altera. Não invente referências litúrgicas." )},
            {"role": "user", "content": json.dumps({
                "transcrição": job["transcript"], "texto_encaminhado_pelo_padre": source_text, "título_anterior": job["title"],
                "descrição_anterior": job["description"], "pedido_editorial": job["note"]},
                ensure_ascii=False)}])
    plan = json.loads(brief.choices[0].message.content)
    title, description = plan["title"].strip(), plan["description"].strip()
    if not 0 < len(title) <= 150 or not 0 < len(description) <= 600:
        raise ValueError("Metadados fora dos limites editoriais.")

    audio = previous_audio
    if not audio or plan.get("change_audio") is True:
        with tempfile.TemporaryDirectory() as d:
            source, wav, out = (Path(d) / name for name in ("source", "source.wav", "tratado.m4a"))
            source.write_bytes(original)
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(source),
                        "-vn", "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(wav)], check=True)
            brightness = max(-3.0, min(3.0, float(plan.get("brightness_db", 0)))) if previous_audio else 0
            subprocess.run([sys.executable, str(HERE / "tratar_audio.py"), str(wav),
                            "-o", str(out), "--brilho-adicional", str(brightness)], check=True)
            audio = out.read_bytes()

    cover = previous_cover
    if not cover or title != job["title"] or plan.get("change_cover") is True:
        prompt = (f"{(HERE / 'identidade.md').read_text()}\n\nGere a capa quadrada final. "
                  f"Título exato: {title}. Cena: {plan['scene']}. Assine Pe. Marcus Vinícius Macedo. "
                  f"Orientação desta edição: {job['note'] or ''}")
        response = requests.post("https://api.openai.com/v1/images/generations",
            headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]},
            json={"model": os.getenv("HOMILIA_IMAGE_MODEL", "gpt-image-1.5"),
                  "size": "1024x1024", "prompt": prompt, "output_format": "png"},
            timeout=(15, 300))
        response.raise_for_status()
        cover = base64.b64decode(response.json()["data"][0]["b64_json"], validate=True)
        if not cover.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("Capa PNG inválida.")
    with engine.begin() as conn:
        store.save_preview(conn, job, audio, cover, title, description)
