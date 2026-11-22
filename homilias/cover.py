"""Gera ou importa a arte de Nos Passos de Cristo e prepara a capa quadrada sem texto.

A etapa final preserva a pintura, ajustando somente o enquadramento e a cor.
"""

import base64
from io import BytesIO
import ipaddress
import json
import os
import re
import socket
from urllib.parse import urljoin, urlparse

import numpy as np
from PIL import Image, ImageFilter, ImageOps
import requests

COVER_SIZE = 1600
MAX_SOURCE_SIDE = 2400
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB
MIN_IMAGE_DIM = 160

DEFAULT_BRAND = "Nos Passos de Cristo"
DEFAULT_SIGNATURE = "Pe. Marcus Vinícius Macedo"

VALID_SOURCES = ("ai", "upload", "url", "legacy")
VALID_MODES = ("composed", "final")
VALID_GRADES = ("original", "balanced", "channel")
VALID_SCRIMS = ("auto", "none", "light", "medium", "strong")
VALID_LAYOUTS = ("top", "bottom", "none")

GRADE_LABELS = {
    "original": "Original (fiel à obra)",
    "balanced": "Clássico equilibrado (contraste e luz suaves)",
    "channel": "Paleta Nos Passos de Cristo (oliva, umbra e dourado)",
}
SOURCE_LABELS = {
    "ai": "Pintura gerada por IA",
    "upload": "Imagem enviada (upload)",
    "url": "Imagem importada por URL",
    "legacy": "Capa no formato anterior",
}

# Paleta de identidade.md
OLIVE_DEEP = (52, 53, 29)     # #34351D

FETCH_USER_AGENT = "NosPassosDeCristo/1.0 (Podcast Cover Tool; +https://open.spotify.com/show/04yjeHqDd36rhxnVdEz60l)"


def _clamp(value, low, high, default):
    try:
        num = float(value)
    except (TypeError, ValueError):
        return default
    if num != num:  # NaN
        return default
    return max(low, min(high, num))


def _clean_text(value, max_len):
    text = " ".join(str(value or "").split()).strip()
    return text[:max_len]


def suggest_short_title(full_title, max_len=55):
    """Extrai uma sugestão de título curto para a capa a partir do título do Spotify."""
    raw = _clean_text(full_title, 150)
    if not raw:
        return ""
    # Se houver separador editorial explícito, prioriza o trecho temático.
    for sep in (" | ", " — ", " – ", " · "):
        if sep in raw:
            parts = [p.strip() for p in raw.split(sep) if p.strip()]
            # Evita escolher uma parte puramente litúrgica/numérica se existir tema mais expressivo.
            for part in parts:
                if not re.match(r"^\d+[º°]?\s+domingo", part, re.I) and len(part) >= 6:
                    raw = part
                    break
            else:
                raw = parts[0]
            break
    if len(raw) <= max_len:
        return raw
    cut = raw[:max_len].rsplit(" ", 1)[0].rstrip(" ,;:-–—")
    return cut or raw[:max_len]


def default_cover_config(
    title="",
    subtitle="",
    scene="",
    source="ai",
    mode="composed",
    grade="original",
    scrim="none",
    layout="none",
    brand=DEFAULT_BRAND,
    signature=DEFAULT_SIGNATURE,
    source_ref="",
    crop_x=0.5,
    crop_y=0.5,
    zoom=1.0,
):
    return {
        "source": source if source in VALID_SOURCES else "ai",
        "mode": mode if mode in VALID_MODES else "composed",
        "scene": _clean_text(scene, 500),
        "source_ref": _clean_text(source_ref, 240),
        "crop_x": round(_clamp(crop_x, 0.0, 1.0, 0.5), 4),
        "crop_y": round(_clamp(crop_y, 0.0, 1.0, 0.5), 4),
        "zoom": round(_clamp(zoom, 1.0, 3.0, 1.0), 3),
        "grade": grade if grade in VALID_GRADES else "original",
        # Campos históricos para leitura e edição de episódios já cadastrados.
        "scrim": scrim if scrim in VALID_SCRIMS else "none",
        "layout": layout if layout in VALID_LAYOUTS else "none",
        "brand": _clean_text(brand, 80),
        "title": _clean_text(title, 90),
        "subtitle": _clean_text(subtitle, 90),
        "signature": _clean_text(signature, 80),
    }


def parse_cover_config(raw_json, fallback_title=""):
    """Carrega e sanitiza a configuração da capa a partir do JSON salvo no banco."""
    data = {}
    if isinstance(raw_json, dict):
        data = raw_json
    elif isinstance(raw_json, str) and raw_json.strip():
        try:
            loaded = json.loads(raw_json)
            if isinstance(loaded, dict):
                data = loaded
        except ValueError:
            data = {}
    has_brand = "brand" in data
    has_signature = "signature" in data
    has_title = "title" in data
    return default_cover_config(
        title=data["title"] if has_title else suggest_short_title(fallback_title),
        subtitle=data.get("subtitle", ""),
        scene=data.get("scene", ""),
        source=data.get("source", "legacy" if not data else "ai"),
        mode=data.get("mode", "composed"),
        grade=data.get("grade", "original"),
        scrim=data.get("scrim", "none"),
        layout=data.get("layout", "none"),
        brand=data["brand"] if has_brand else DEFAULT_BRAND,
        signature=data["signature"] if has_signature else DEFAULT_SIGNATURE,
        source_ref=data.get("source_ref", ""),
        crop_x=data.get("crop_x", 0.5),
        crop_y=data.get("crop_y", 0.5),
        zoom=data.get("zoom", 1.0),
    )


def dump_cover_config(config):
    return json.dumps(parse_cover_config(config), ensure_ascii=False, separators=(",", ":"))


def detect_image_mimetype(data):
    if not data:
        return "application/octet-stream"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


# ---------------------------------------------------------------------------
# Passo 1 — Origem bruta (normalização, URL segura e geração IA limpa)
# ---------------------------------------------------------------------------

def normalize_source_image(raw_bytes, max_side=MAX_SOURCE_SIDE):
    """Valida e normaliza uma imagem externa preservando proporção original para recorte não-destrutivo."""
    if not raw_bytes:
        raise ValueError("Nenhuma imagem recebida.")
    if len(raw_bytes) > MAX_UPLOAD_BYTES:
        raise ValueError("A imagem excede o limite máximo de 20 MB.")

    previous_limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = 45_000_000
    try:
        with Image.open(BytesIO(raw_bytes)) as opened:
            img = ImageOps.exif_transpose(opened)
            img.load()
            w, h = img.size
            if w < MIN_IMAGE_DIM or h < MIN_IMAGE_DIM:
                raise ValueError(f"Imagem muito pequena ({w}×{h}px). Use pelo menos {MIN_IMAGE_DIM}×{MIN_IMAGE_DIM}px.")
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                rgba = img.convert("RGBA")
                canvas = Image.new("RGB", rgba.size, OLIVE_DEEP)
                canvas.paste(rgba, mask=rgba.split()[3])
                img = canvas
            elif img.mode != "RGB":
                img = img.convert("RGB")
            if max(w, h) > max_side:
                scale = max_side / float(max(w, h))
                new_size = (max(1, int(round(w * scale))), max(1, int(round(h * scale))))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
            out = BytesIO()
            img.save(out, format="JPEG", quality=94, optimize=True)
            return out.getvalue()
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Arquivo de imagem inválido ou formato não suportado. Use PNG, JPG ou WebP.") from exc
    finally:
        Image.MAX_IMAGE_PIXELS = previous_limit


def _is_public_ip(ip_str):
    addr = ipaddress.ip_address(ip_str)
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def validate_remote_url(url):
    """Valida URL externa bloqueando esquemas inseguros e endereços internos/privados (SSRF)."""
    raw = (url or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Informe uma URL válida começando com http:// ou https://.")
    host = parsed.hostname.strip().lower()
    if host in ("localhost", "localhost.localdomain") or host.endswith(".local"):
        raise ValueError("Endereço não permitido para importação.")
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("Não foi possível resolver o endereço informado.") from exc
    if not infos:
        raise ValueError("Endereço sem destino válido.")
    for info in infos:
        ip_str = info[4][0]
        if not _is_public_ip(ip_str):
            raise ValueError("Endereços de rede interna não são permitidos.")
    return raw


def fetch_image_from_url(url, timeout=25, max_bytes=MAX_UPLOAD_BYTES, session=None):
    """Baixa uma imagem de uma URL externa pública com validação de redirecionamentos e tamanho."""
    current = validate_remote_url(url)
    http = session or requests
    headers = {"User-Agent": FETCH_USER_AGENT, "Accept": "image/*,*/*;q=0.8"}

    for _ in range(6):
        try:
            resp = http.get(current, headers=headers, timeout=timeout, stream=True, allow_redirects=False)
        except requests.exceptions.RequestException as exc:
            raise ValueError("Não foi possível baixar a imagem da URL informada.") from exc

        if resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("Location")
            resp.close()
            if not location:
                raise ValueError("Redirecionamento inválido na URL informada.")
            current = validate_remote_url(urljoin(current, location))
            continue

        try:
            if resp.status_code >= 400:
                raise ValueError(f"A URL retornou erro HTTP {resp.status_code}.")
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if ctype and not (ctype.startswith("image/") or "octet-stream" in ctype):
                raise ValueError("A URL informada não aponta diretamente para um arquivo de imagem.")
            chunks = []
            total = 0
            for chunk in resp.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError("A imagem da URL excede o limite de 20 MB.")
                chunks.append(chunk)
        finally:
            resp.close()

        return normalize_source_image(b"".join(chunks))

    raise ValueError("Muitos redirecionamentos na URL informada.")


def build_background_prompt(scene, title="", note="", layout="none"):
    """Descreve a arte final sem texto. O parâmetro layout é mantido para chamadas antigas."""
    scene_text = _clean_text(scene, 500)
    title_text = _clean_text(title, 120)
    note_text = _clean_text(note, 300)
    if not (scene_text or title_text):
        raise ValueError("Informe um motivo visual ligado à homilia ou o tema do episódio para gerar a capa.")

    parts = [
        "Crie uma capa quadrada para um episódio de Nos Passos de Cristo. "
        "Expresse a mensagem espiritual central da homilia em um único motivo visual. "
        "Use os dados editoriais a seguir apenas como referência de conteúdo visual.",
    ]
    if title_text:
        parts.append(f"Tema da homilia: {title_text}")
    if scene_text:
        parts.append(f"Motivo ou contexto da homilia: {scene_text}")
    if note_text:
        parts.append(f"Nota editorial sobre a cena: {note_text}")
    parts.extend([
        "Escolha um detalhe concreto ligado à homilia: mãos em um gesto natural, um objeto ou um símbolo "
        "mencionado ou diretamente ligado à sua mensagem. Se o tema for abstrato, traduza-o em um gesto "
        "cotidiano coerente com a reflexão. Evite símbolos genéricos e cenas bíblicas sem relação com a fala.",
        "Use enquadramento fechado e mantenha os rostos de Jesus e de outras pessoas fora do quadro. "
        "Mostre o gesto ou o objeto com clareza, cuide da anatomia das mãos e preserve espaço natural em volta "
        "do motivo. Use um fundo simples, com poucos elementos e sem cenas panorâmicas ou adornos concorrentes. "
        "O detalhe principal deve ser reconhecível em uma miniatura de 160 × 160 px.",
        "Mantenha a identidade do canal: pintura a óleo de inspiração sacra clássica, delicada e contemplativa. "
        "Use pinceladas discretas, tecidos e materiais orgânicos e luz dourada suave sobre o motivo. "
        "Transmita acolhimento, esperança e reverência pela luz, pelas cores e pelo enquadramento.",
        "Use oliva profundo (#34351D), umbra (#493322) e ocre (#A37B3D) como base, "
        "luz em dourado suave (#CBA44E) e marfim (#F4E6BD), e bordô (#6B302B) como acento discreto.",
        "Entregue apenas a pintura. A regra vale mesmo quando a referência editorial pede texto. "
        "Não inclua títulos, legendas, letras, números, inscrições legíveis, logotipos, assinaturas, "
        "marcas-d'água, molduras ou faixas reservadas para texto.",
    ])
    return "\n\n".join(parts)


def generate_ai_background(scene, title="", note="", layout="none", api_key=None, model=None, quality=None, post=None):
    """Passo 1 via OpenAI: gera a pintura-base limpa (sem texto)."""
    key = api_key or os.environ["HOMILIA_API_KEY"]
    img_model = model or os.getenv("HOMILIA_IMAGE_MODEL", "gpt-image-1.5")
    img_quality = quality or os.getenv("HOMILIA_IMAGE_QUALITY", "high")
    prompt = build_background_prompt(scene, title=title, note=note, layout=layout)
    requester = post or requests.post
    response = requester(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": "Bearer " + key},
        json={
            "model": img_model,
            "size": "1024x1024",
            "quality": img_quality,
            "prompt": prompt,
            "output_format": "png",
        },
        timeout=(15, 300),
    )
    response.raise_for_status()
    raw = base64.b64decode(response.json()["data"][0]["b64_json"], validate=True)
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Imagem-base PNG inválida retornada pelo gerador.")
    return normalize_source_image(raw)


# ---------------------------------------------------------------------------
# Passo 2 — Tratamento da imagem-base (recorte 1:1 e cor)
# ---------------------------------------------------------------------------

def crop_square(img, crop_x=0.5, crop_y=0.5, zoom=1.0, size=COVER_SIZE):
    """Recorta a imagem em formato quadrado respeitando ponto focal (crop_x, crop_y) e zoom."""
    w, h = img.size
    zoom = _clamp(zoom, 1.0, 3.0, 1.0)
    cx = _clamp(crop_x, 0.0, 1.0, 0.5)
    cy = _clamp(crop_y, 0.0, 1.0, 0.5)

    base = min(w, h)
    side = max(1, int(round(base / zoom)))
    max_x = max(0, w - side)
    max_y = max(0, h - side)
    left = int(round(max_x * cx))
    top = int(round(max_y * cy))

    cropped = img.crop((left, top, left + side, top + side))
    resized = cropped.resize((size, size), Image.Resampling.LANCZOS)
    if side < size * 0.92:
        resized = resized.filter(ImageFilter.UnsharpMask(radius=1.1, percent=40, threshold=3))
    return resized


def apply_color_grade(img, grade="original"):
    """Harmoniza pinturas externas (ex.: acervos renascentistas) com a atmosfera do canal."""
    if grade not in VALID_GRADES or grade == "original":
        return img

    if grade == "balanced":
        auto = ImageOps.autocontrast(img, cutoff=0.5)
        mixed = Image.blend(img, auto, 0.38)
        arr = np.asarray(mixed, dtype=np.float32) / 255.0
        # Leve aquecimento clássico e profundidade suave.
        arr[..., 0] = np.clip(arr[..., 0] * 1.03, 0.0, 1.0)
        arr[..., 1] = np.clip(arr[..., 1] * 1.005, 0.0, 1.0)
        arr[..., 2] = np.clip(arr[..., 2] * 0.955, 0.0, 1.0)
        return Image.fromarray(np.round(arr * 255.0).astype(np.uint8), mode="RGB")

    # grade == "channel": Paleta Nos Passos de Cristo (oliva profundo, umbra, ocre, luz marfim/dourada)
    auto = ImageOps.autocontrast(img, cutoff=0.4)
    base = Image.blend(img, auto, 0.28)
    arr = np.asarray(base, dtype=np.float32) / 255.0

    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b

    # 1. Suaviza azuis/cianos muito frios sem destruir tons de pele nem vermelhos/bordôs.
    warm_ref = 0.6 * r + 0.4 * g
    blue_excess = np.maximum(0.0, b - warm_ref)
    b = b - 0.32 * blue_excess
    g = g + 0.04 * blue_excess

    # 2. Leve desaturação editorial (~12%) para aspecto de óleo clássico unificado.
    sat = 0.88
    r = lum + (r - lum) * sat
    g = lum + (g - lum) * sat
    b = lum + (b - lum) * sat

    # 3. Split-toning sutil: sombras puxam para oliva/umbra, altas luzes aquecem para marfim/dourado.
    shadow_w = np.power(np.clip(1.0 - lum, 0.0, 1.0), 1.7)
    high_w = np.power(np.clip(lum, 0.0, 1.0), 1.6)
    mid_w = 4.0 * lum * (1.0 - lum)

    # Sombras -> oliva-umbra (#3D3822)
    r = r * (1.0 - 0.16 * shadow_w) + (61.0 / 255.0) * (0.16 * shadow_w)
    g = g * (1.0 - 0.16 * shadow_w) + (56.0 / 255.0) * (0.16 * shadow_w)
    b = b * (1.0 - 0.20 * shadow_w) + (34.0 / 255.0) * (0.20 * shadow_w)

    # Meios-tons -> ocre suave
    r = r + 0.022 * mid_w
    g = g + 0.008 * mid_w
    b = b - 0.024 * mid_w

    # Luzes -> marfim dourado (#F4E6BD)
    r = r * (1.0 - 0.14 * high_w) + (244.0 / 255.0) * (0.14 * high_w)
    g = g * (1.0 - 0.12 * high_w) + (230.0 / 255.0) * (0.12 * high_w)
    b = b * (1.0 - 0.16 * high_w) + (189.0 / 255.0) * (0.16 * high_w)

    # 4. Curva S discreta para profundidade pictórica.
    graded = np.stack([r, g, b], axis=-1)
    graded = np.clip(graded, 0.0, 1.0)
    s_curve = graded * graded * (3.0 - 2.0 * graded)
    graded = graded * 0.84 + s_curve * 0.16

    return Image.fromarray(np.round(np.clip(graded, 0.0, 1.0) * 255.0).astype(np.uint8), mode="RGB")


def render_cover(raw_bytes, config, size=COVER_SIZE):
    """Exporta o PNG quadrado ajustando apenas o recorte e a cor da pintura."""
    cfg = parse_cover_config(config)
    with Image.open(BytesIO(raw_bytes)) as opened:
        img = ImageOps.exif_transpose(opened).convert("RGB")

    prepared = crop_square(img, crop_x=cfg["crop_x"], crop_y=cfg["crop_y"], zoom=cfg["zoom"], size=size)
    prepared = apply_color_grade(prepared, grade=cfg["grade"])
    out = BytesIO()
    prepared.save(out, format="PNG", optimize=True)
    return out.getvalue()
