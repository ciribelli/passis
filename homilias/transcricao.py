"""Transcrição do áudio da homilia para a capa e a prévia editorial."""
import os
from pathlib import Path
import subprocess
import tempfile

import imageio_ffmpeg
import sqlalchemy as sa

from . import store


def transcribe(client, audio):
    """Converte inclusive Ogg/Opus em trechos de voz WAV abaixo de um minuto."""
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        original = folder / "original"
        original.write_bytes(audio)
        subprocess.run([
            imageio_ffmpeg.get_ffmpeg_exe(), "-nostdin", "-v", "error", "-i", str(original),
            "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
            "-f", "segment", "-segment_time", "50", "-reset_timestamps", "1",
            str(folder / "voz-%06d.wav"),
        ], check=True)
        paragraphs = []
        model = os.getenv("HOMILIA_TRANSCRIPTION_MODEL", "gpt-4o-mini-transcribe")
        for chunk in sorted(folder.glob("voz-*.wav")):
            with chunk.open("rb") as stream:
                result = client.audio.transcriptions.create(model=model, file=stream, language="pt")
            if result.text.strip():
                paragraphs.append(result.text.strip())
        if not paragraphs:
            raise ValueError("Nenhuma fala reconhecida no áudio da homilia.")
        return "\n\n".join(paragraphs)


def episode_transcript(engine, client, job, audio):
    if job["transcript"].strip():
        return job["transcript"]
    text = transcribe(client, audio)
    # O áudio de origem é imutável. Reaproveitar o texto mesmo se a geração da capa falhar.
    with engine.begin() as conn:
        conn.execute(store.episodes.update().where(
            store.episodes.c.id == job["id"], store.episodes.c.transcript == job["transcript"],
        ).values(transcript=text))
        return conn.execute(sa.select(store.episodes.c.transcript).where(store.episodes.c.id == job["id"])).scalar_one()
