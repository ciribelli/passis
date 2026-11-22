"""Pipeline de capas em 3 passos para Nos Passos de Cristo.

Passo 1 — Origem bruta (pintura IA sem texto, upload de arquivo ou URL externa).
Passo 2 — Tratamento da imagem-base (recorte 1:1 com foco/zoom, color grading editorial,
          scrim/gradiente calibrado pela luminosidade da obra e normalização de resolução).
Passo 3 — Composição tipográfica estruturada (marca, título curto, subtítulo litúrgico
          e assinatura do padre em Cormorant Garamond sobre a imagem tratada).
"""

import base64
from io import BytesIO
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
from urllib.parse import urljoin, urlparse

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
import requests

HERE = Path(__file__).parent
FONTS_DIR = HERE / "fonts"

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
SCRIM_LABELS = {
    "auto": "Automático (calibrado pela luz da imagem)",
    "light": "Leve",
    "medium": "Médio",
    "strong": "Forte",
    "none": "Sem escurecimento",
}
LAYOUT_LABELS = {
    "top": "Clássico (título no topo, assinatura na base)",
    "bottom": "Inferior (título e assinatura na base — preserva rostos no topo)",
    "none": "Sem texto (somente a imagem tratada)",
}
SOURCE_LABELS = {
    "ai": "Pintura gerada por IA",
    "upload": "Imagem enviada (upload)",
    "url": "Imagem importada por URL",
    "legacy": "Capa no formato anterior",
}

# Paleta de identidade.md
OLIVE_DEEP = (52, 53, 29)     # #34351D
UMBER = (73, 51, 34)          # #493322
GOLD_SOFT = (203, 164, 78)    # #CBA44E
IVORY = (244, 230, 189)       # #F4E6BD
SUBTITLE_TINT = (234, 214, 158)
SCRIM_RGB = (28, 27, 16)      # Oliva-umbra profundo para leitura sem preto chapado

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
    scrim="auto",
    layout="top",
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
        "scrim": scrim if scrim in VALID_SCRIMS else "auto",
        "layout": layout if layout in VALID_LAYOUTS else "top",
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
        scrim=data.get("scrim", "auto"),
        layout=data.get("layout", "top"),
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


def build_background_prompt(scene, title="", note="", layout="top"):
    """Prompt enxuto e dedicado ao Passo 1: pintura devocional pura, sem nenhum texto."""
    scene_text = _clean_text(scene, 500) or "Uma cena contemplativa com luz dourada suave e caminho acolhedor."
    if layout == "bottom":
        reserve = (
            "Compose the main subject slightly above center, leaving calm, darker, uncluttered "
            "painterly space along the lower third and a narrow quiet strip at the very top edge "
            "for typography to be added in a separate step."
        )
    else:
        reserve = (
            "Compose the main subject cleanly in the middle and lower-middle area, leaving calm, "
            "darker, uncluttered painterly space in the upper third and a quiet dark band near the "
            "bottom edge for typography to be added in a separate step."
        )
    parts = [
        "Create a square classical devotional oil painting for a Catholic homily podcast artwork.",
        f"Central scene: {scene_text}",
    ]
    if title:
        parts.append(f"Thematic mood inspired by: {_clean_text(title, 120)} (visual atmosphere only, do not write it).")
    if note:
        parts.append(f"Editorial direction: {_clean_text(note, 300)}")
    parts.extend([
        "Visual style: timeless classical sacred oil painting with subtle brushwork, warm golden directional light, "
        "organic textures (linen, wood, stone, foliage, earth), serene human expressions, coherent anatomy on hands "
        "and faces, and a softly detailed background.",
        "Color palette anchored in deep olive (#34351D), warm umber (#493322), earthy ochre (#A37B3D), "
        "soft gold (#CBA44E), ivory light (#F4E6BD), and deep burgundy (#6B302B) accents.",
        "Single unmistakable central motif recognizable even as a small 160x160px thumbnail.",
        reserve,
        "CRITICAL: Deliver ONLY the pure painting. Do NOT include ANY text, letters, words, titles, "
        "calligraphy, watermarks, frames, borders, or signatures anywhere in the image.",
    ])
    return "\n\n".join(parts)


def generate_ai_background(scene, title="", note="", layout="top", api_key=None, model=None, quality=None, post=None):
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
# Passo 2 — Tratamento da imagem-base (recorte 1:1, color grading, scrim)
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


def measure_band_luminance(img, y0_frac, y1_frac):
    """Retorna a luminância média (0..1) de uma faixa horizontal da imagem."""
    w, h = img.size
    y0 = max(0, min(h - 1, int(round(h * y0_frac))))
    y1 = max(y0 + 1, min(h, int(round(h * y1_frac))))
    band = img.crop((0, y0, w, y1)).resize((64, 32), Image.Resampling.BILINEAR)
    arr = np.asarray(band, dtype=np.float32) / 255.0
    lum = 0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2]
    return float(np.mean(lum))


def _auto_scrim_alpha(band_lum, is_primary):
    """Calibra a opacidade do gradiente pela luminosidade medida na região do texto."""
    if is_primary:
        # Área de título: entre 0.34 (obra já bem escura) e 0.84 (céu claro renascentista)
        return float(np.clip(0.32 + band_lum * 0.62, 0.32, 0.84))
    # Área secundária (marca ou assinatura): mais discreta
    return float(np.clip(0.24 + band_lum * 0.52, 0.24, 0.74))


def apply_scrim_and_vignette(img, layout="top", scrim="auto", has_top=True, has_bottom=True):
    """Aplica gradientes suaves de leitura e vinheta editorial em oliva-umbra profundo."""
    if layout == "none" or scrim == "none":
        return img

    w, h = img.size
    preset_scale = {"auto": 1.0, "light": 0.65, "medium": 1.0, "strong": 1.32}[scrim]
    fixed_primary = {"light": 0.44, "medium": 0.66, "strong": 0.84}
    fixed_secondary = {"light": 0.34, "medium": 0.52, "strong": 0.70}

    y = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
    alpha = np.zeros((h, w), dtype=np.float32)

    if has_top:
        top_is_primary = (layout == "top")
        top_span = 0.48 if top_is_primary else 0.22
        if scrim == "auto":
            top_strength = _auto_scrim_alpha(measure_band_luminance(img, 0.0, top_span * 0.8), top_is_primary)
        else:
            top_strength = fixed_primary[scrim] if top_is_primary else fixed_secondary[scrim]
        t = np.clip(1.0 - (y / top_span), 0.0, 1.0)
        # Curva suave (cubic ease) evita degrau visível na pintura
        top_grad = np.power(t, 1.65) * top_strength
        alpha = np.maximum(alpha, top_grad)

    if has_bottom:
        bot_is_primary = (layout == "bottom")
        bot_span = 0.50 if bot_is_primary else 0.24
        if scrim == "auto":
            bot_strength = _auto_scrim_alpha(measure_band_luminance(img, 1.0 - bot_span * 0.8, 1.0), bot_is_primary)
        else:
            bot_strength = fixed_primary[scrim] if bot_is_primary else fixed_secondary[scrim]
        b = np.clip((y - (1.0 - bot_span)) / bot_span, 0.0, 1.0)
        bot_grad = np.power(b, 1.65) * bot_strength
        alpha = np.maximum(alpha, bot_grad)

    # Vinheta radial sutil nos cantos para unidade editorial
    x = np.linspace(-1.0, 1.0, w, dtype=np.float32)[None, :]
    yv = np.linspace(-1.0, 1.0, h, dtype=np.float32)[:, None]
    dist = np.sqrt(x * x + yv * yv)
    vignette = np.clip((dist - 0.82) / 0.65, 0.0, 1.0) ** 2 * (0.24 * min(1.2, preset_scale))
    alpha = np.clip(1.0 - (1.0 - alpha) * (1.0 - vignette), 0.0, 0.90)

    arr = np.asarray(img, dtype=np.float32)
    scrim_color = np.array(SCRIM_RGB, dtype=np.float32)[None, None, :]
    out = arr * (1.0 - alpha[..., None]) + scrim_color * alpha[..., None]
    return Image.fromarray(np.round(np.clip(out, 0, 255)).astype(np.uint8), mode="RGB")


# ---------------------------------------------------------------------------
# Passo 3 — Composição tipográfica estruturada (Cormorant Garamond)
# ---------------------------------------------------------------------------

def _load_font(filename, px):
    px = max(12, int(round(px)))
    candidates = [
        FONTS_DIR / filename,
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf" if "Bold" in filename else "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"),
        Path("/System/Library/Fonts/Supplemental/Georgia Bold.ttf" if "Bold" in filename else "/System/Library/Fonts/Supplemental/Georgia.ttf"),
    ]
    for path in candidates:
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), px)
            except OSError:
                continue
    return ImageFont.load_default()


def _text_width(draw, text, font, tracking=0):
    if not text:
        return 0
    if tracking <= 0:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0]
    total = 0.0
    for idx, ch in enumerate(text):
        total += draw.textlength(ch, font=font)
        if idx < len(text) - 1:
            total += tracking
    return int(round(total))


def _line_height(draw, font):
    bbox = draw.textbbox((0, 0), "ÁgÇp", font=font)
    return bbox[3] - bbox[1]


def _wrap_balanced(text, font, draw, max_width, max_lines=3):
    """Quebra o texto em até max_lines buscando linhas visualmente equilibradas (sem órfãs)."""
    words = text.split()
    if not words:
        return []
    if _text_width(draw, text, font) <= max_width:
        return [text]

    # Programação dinâmica para minimizar soma dos quadrados da folga de cada linha.
    n = len(words)
    INF = 10**18
    # dp[i][k] = (cost, prev_index) para quebrar words[:i] em k linhas
    dp = [[(INF, -1)] * (max_lines + 1) for _ in range(n + 1)]
    dp[0][0] = (0, -1)

    for k in range(1, max_lines + 1):
        for i in range(k, n + 1):
            for j in range(k - 1, i):
                if dp[j][k - 1][0] >= INF:
                    continue
                line = " ".join(words[j:i])
                w = _text_width(draw, line, font)
                if w > max_width:
                    continue
                slack = max_width - w
                # Penaliza levemente linha final com apenas 1 palavra curta
                orphan_penalty = (max_width * 0.22) ** 2 if (i == n and (i - j) == 1 and len(line) <= 5 and k > 1) else 0
                cost = dp[j][k - 1][0] + slack * slack + orphan_penalty
                if cost < dp[i][k][0]:
                    dp[i][k] = (cost, j)

    best_k = None
    best_cost = INF
    for k in range(1, max_lines + 1):
        if dp[n][k][0] < best_cost:
            best_cost = dp[n][k][0]
            best_k = k

    if best_k is None:
        return None

    lines = []
    idx = n
    for k in range(best_k, 0, -1):
        prev = dp[idx][k][1]
        lines.append(" ".join(words[prev:idx]))
        idx = prev
    lines.reverse()
    return lines


def _fit_wrapped(text, font_file, max_width, size_start, size_min, draw, max_lines=3):
    """Ajusta automaticamente o corpo da fonte para caber em até max_lines com equilíbrio."""
    step = max(2, int(round((size_start - size_min) / 14)))
    for px in range(size_start, size_min - 1, -step):
        font = _load_font(font_file, px)
        lines = _wrap_balanced(text, font, draw, max_width, max_lines=max_lines)
        if lines is not None:
            return font, lines

    # Fallback para títulos muito longos sem espaços ou extremos: quebra gulosa no menor tamanho.
    font = _load_font(font_file, size_min)
    words = text.split()
    lines, current = [], ""
    for word in words:
        candidate = (current + " " + word).strip()
        if current and _text_width(draw, candidate, font) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(" .,;:-") + "…"
    return font, lines


def _draw_centered_text(draw, text, center_x, y, font, fill, tracking=0):
    if not text:
        return
    width = _text_width(draw, text, font, tracking=tracking)
    x = center_x - width / 2.0
    if tracking <= 0:
        draw.text((x, y), text, font=font, fill=fill)
        return
    cursor = x
    for ch in text:
        draw.text((cursor, y), ch, font=font, fill=fill)
        cursor += draw.textlength(ch, font=font) + tracking


def _draw_gold_rule(draw, center_x, y, width, thickness=2, alpha=215):
    half = width / 2.0
    color = (*GOLD_SOFT, alpha)
    # Filete fino com pequeno losango central clássico
    diamond = max(3, int(round(thickness * 2.2)))
    gap = diamond + max(6, int(round(thickness * 3)))
    draw.line([(center_x - half, y), (center_x - gap, y)], fill=color, width=thickness)
    draw.line([(center_x + gap, y), (center_x + half, y)], fill=color, width=thickness)
    draw.polygon(
        [
            (center_x, y - diamond),
            (center_x + diamond, y),
            (center_x, y + diamond),
            (center_x - diamond, y),
        ],
        fill=color,
    )


def render_cover(raw_bytes, config, size=COVER_SIZE):
    """Executa Passo 2 (tratamento) + Passo 3 (tipografia estruturada) e devolve PNG final."""
    cfg = parse_cover_config(config)
    with Image.open(BytesIO(raw_bytes)) as opened:
        img = ImageOps.exif_transpose(opened).convert("RGB")

    # Passo 2: recorte 1:1 + tratamento de cor
    prepared = crop_square(img, crop_x=cfg["crop_x"], crop_y=cfg["crop_y"], zoom=cfg["zoom"], size=size)
    prepared = apply_color_grade(prepared, grade=cfg["grade"])

    # Modo "capa pronta" ou layout "sem texto": devolve sem sobrepor tipografia
    if cfg["mode"] == "final" or cfg["layout"] == "none":
        out = BytesIO()
        prepared.save(out, format="PNG", optimize=True)
        return out.getvalue()

    brand = cfg["brand"]
    title = cfg["title"]
    subtitle = cfg["subtitle"]
    signature = cfg["signature"]
    layout = cfg["layout"]

    has_top = bool(brand or (layout == "top" and (title or subtitle)))
    has_bottom = bool(signature or (layout == "bottom" and (title or subtitle)))
    prepared = apply_scrim_and_vignette(prepared, layout=layout, scrim=cfg["scrim"], has_top=has_top, has_bottom=has_bottom)

    # Passo 3: tipografia estruturada com sombra suave integrada
    base_rgba = prepared.convert("RGBA")
    shadow_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    text_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)
    text_draw = ImageDraw.Draw(text_layer)

    margin_x = int(round(size * 0.085))
    margin_y = int(round(size * 0.062))
    max_w = size - 2 * margin_x
    cx = size / 2.0

    brand_font = _load_font("CormorantGaramond-Medium.ttf", size * 0.028)
    brand_tracking = max(2, int(round(size * 0.0032)))
    sig_font = _load_font("CormorantGaramond-Medium.ttf", size * 0.032)
    sig_tracking = max(1, int(round(size * 0.0014)))

    title_font, title_lines = (
        _fit_wrapped(title, "CormorantGaramond-Bold.ttf", max_w, int(size * 0.072), int(size * 0.044), text_draw, max_lines=3)
        if title else (None, [])
    )
    sub_font, sub_lines = (
        _fit_wrapped(subtitle, "CormorantGaramond-MediumItalic.ttf", int(max_w * 0.92), int(size * 0.036), int(size * 0.025), text_draw, max_lines=2)
        if subtitle else (None, [])
    )

    shadow_color = (16, 14, 8, 175)
    shadow_offset = max(2, int(round(size * 0.0025)))
    rule_w = int(round(size * 0.16))
    rule_t = max(2, int(round(size * 0.0016)))

    def draw_text_both(txt, y_pos, fnt, fill, tracking=0):
        _draw_centered_text(shadow_draw, txt, cx, y_pos + shadow_offset, fnt, shadow_color, tracking=tracking)
        _draw_centered_text(text_draw, txt, cx, y_pos, fnt, fill, tracking=tracking)

    # 1. Marca discreta no topo (em ambos os layouts)
    cursor_top = margin_y
    if brand:
        draw_text_both(brand, cursor_top, brand_font, (*IVORY, 232), tracking=brand_tracking)
        cursor_top += _line_height(text_draw, brand_font) + int(round(size * 0.024))
        _draw_gold_rule(text_draw, cx, cursor_top, rule_w, thickness=rule_t, alpha=205)
        cursor_top += int(round(size * 0.022))

    if layout == "top":
        # Título e subtítulo no terço superior
        if title_lines:
            lh = int(round(_line_height(text_draw, title_font) * 1.12))
            for line in title_lines:
                draw_text_both(line, cursor_top, title_font, (*IVORY, 255))
                cursor_top += lh
        if sub_lines:
            cursor_top += int(round(size * 0.014))
            lh = int(round(_line_height(text_draw, sub_font) * 1.20))
            for line in sub_lines:
                draw_text_both(line, cursor_top, sub_font, (*SUBTITLE_TINT, 242))
                cursor_top += lh

        # Assinatura do padre na base
        if signature:
            sig_h = _line_height(text_draw, sig_font)
            sig_y = size - margin_y - sig_h
            rule_y = sig_y - int(round(size * 0.018))
            _draw_gold_rule(text_draw, cx, rule_y, int(rule_w * 0.85), thickness=rule_t, alpha=190)
            draw_text_both(signature, sig_y, sig_font, (*IVORY, 242), tracking=sig_tracking)
    else:
        # layout == "bottom": agrupa título, subtítulo e assinatura na faixa inferior
        blocks = []
        total_h = 0
        if title_lines:
            lh = int(round(_line_height(text_draw, title_font) * 1.12))
            blocks.append(("title", title_lines, title_font, lh, (*IVORY, 255), 0))
            total_h += lh * len(title_lines)
        if sub_lines:
            gap = int(round(size * 0.014)) if blocks else 0
            lh = int(round(_line_height(text_draw, sub_font) * 1.20))
            blocks.append(("gap", gap))
            blocks.append(("sub", sub_lines, sub_font, lh, (*SUBTITLE_TINT, 242), 0))
            total_h += gap + lh * len(sub_lines)
        if signature:
            rule_gap = int(round(size * 0.026)) if blocks else 0
            sig_h = _line_height(text_draw, sig_font)
            if blocks:
                blocks.append(("rule", rule_gap))
                total_h += rule_gap * 2
            blocks.append(("sig", [signature], sig_font, sig_h, (*IVORY, 242), sig_tracking))
            total_h += sig_h

        y_cursor = size - margin_y - total_h
        for item in blocks:
            kind = item[0]
            if kind == "gap":
                y_cursor += item[1]
            elif kind == "rule":
                y_cursor += item[1]
                _draw_gold_rule(text_draw, cx, y_cursor, int(rule_w * 0.9), thickness=rule_t, alpha=195)
                y_cursor += item[1]
            else:
                _, lines, fnt, lh, fill, trk = item
                for line in lines:
                    draw_text_both(line, y_cursor, fnt, fill, tracking=trk)
                    y_cursor += lh

    blurred_shadow = shadow_layer.filter(ImageFilter.GaussianBlur(radius=max(3.0, size * 0.0055)))
    composed = Image.alpha_composite(base_rgba, blurred_shadow)
    composed = Image.alpha_composite(composed, text_layer).convert("RGB")

    out = BytesIO()
    composed.save(out, format="PNG", optimize=True)
    return out.getvalue()
