"""Publicação pelo Spotify for Creators com perfil de navegador próprio."""
import os
from pathlib import Path
import re
import tempfile

import requests
from playwright.sync_api import sync_playwright, expect, TimeoutError as PlaywrightTimeout

from . import store

SHOW = "04yjeHqDd36rhxnVdEz60l"
BASE = f"https://creators.spotify.com/pod/show/{SHOW}/episode"


def profile():
    return Path(os.getenv("HOMILIA_SPOTIFY_PROFILE", "~/.passis-spotify")).expanduser()


def browser(playwright):
    return playwright.chromium.launch_persistent_context(str(profile()), headless=False, locale="en-US")


def login():
    with sync_playwright() as pw:
        context = browser(pw)
        page = context.pages[0]
        page.goto(f"https://creators.spotify.com/home/show/{SHOW}")
        input("Entre na conta do canal e pressione Enter neste terminal para salvar a sessão. ")
        context.close()


def public_url(spotify_id):
    return f"https://open.spotify.com/episode/{spotify_id}"


def confirmed(spotify_id, title):
    if not spotify_id:
        return False
    result = requests.get("https://open.spotify.com/oembed",
                          params={"url": public_url(spotify_id)}, timeout=20)
    return result.ok and result.json().get("title", "").strip() == title


def publish(engine, job):
    eid = job["id"]
    with engine.begin() as conn:
        audio, cover = (store.asset(conn, eid, k) for k in ("audio", "cover"))
    with tempfile.TemporaryDirectory() as d, sync_playwright() as pw:
        audio_path, cover_path = Path(d) / "homilia.m4a", Path(d) / "capa.png"
        audio_path.write_bytes(audio)
        cover_path.write_bytes(cover)
        context = browser(pw)
        page = context.pages[0]
        page.set_default_timeout(25000)
        wizard = f"{BASE}/{job['spotify_id']}/wizard" if job["spotify_id"] else f"{BASE}/wizard"
        page.goto(wizard)
        if not job["spotify_id"]:
            audio_input = page.locator('input[type=file][accept*="audio"]')
            if audio_input.count() == 0:
                upload = page.locator('input[type=file]')
            else:
                upload = audio_input
            upload.set_input_files(str(audio_path))
            page.wait_for_url(re.compile(re.escape(BASE) + r"/[a-zA-Z0-9]{22}/wizard"), timeout=180000)
        spotify_id = re.fullmatch(re.escape(BASE) + r"/([a-zA-Z0-9]{22})/wizard/?(?:\?.*)?", page.url)
        if not spotify_id:
            raise RuntimeError("Identidade do rascunho não confirmada.")
        sid = spotify_id[1]
        with engine.begin() as conn:
            if not store.transition(conn, eid, job["owner"], job["version"], "publishing",
                                    "publishing", spotify_id=sid):
                raise RuntimeError("Ordem expirada.")

        title = page.get_by_role("textbox", name=re.compile("title|título", re.I))
        title.fill(job["title"])
        description = page.locator('[contenteditable=true]:visible, textarea:visible')
        description.fill(job["description"])
        art = page.locator('input[type=file][accept*="image"]')
        if not art.count():
            details = page.get_by_role("button", name=re.compile("additional details|detalhes adicionais", re.I))
            if details.is_visible():
                details.click()
        if not art.count():
            chooser_button = page.get_by_role("button", name=re.compile("upload.*(art|image)|carregar.*(arte|imagem)", re.I))
            with page.expect_file_chooser() as picker:
                chooser_button.click()
            picker.value.set_files(str(cover_path))
        else:
            art.set_input_files(str(cover_path))
        expect(title).to_have_value(job["title"])
        next_button = page.get_by_role("button", name=re.compile(r"^(next|avançar|continuar|próximo)$", re.I))
        if next_button.is_visible():
            next_button.click()
        final = page.get_by_role("button", name=re.compile(r"^(publish( now| episode)?|publicar( agora| episódio)?)$", re.I))
        expect(final).to_be_enabled(timeout=180000)
        # Gravar antes do primeiro clique com efeito público. Um timeout pode indicar sucesso.
        with engine.begin() as conn:
            if not store.transition(conn, eid, job["owner"], job["version"], "publishing", "clicked"):
                raise RuntimeError("Ordem já consumida.")
        final.click()
        dialog = page.get_by_role("dialog")
        confirmation = dialog.get_by_role("button", name=re.compile(r"^(publish( now)?|publicar( agora)?)$", re.I))
        try:
            confirmation.wait_for(state="visible", timeout=4000)
        except PlaywrightTimeout:
            pass  # Alguns fluxos concluem com um único clique.
        else:
            confirmation.click()
        context.close()
