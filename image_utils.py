"""
Renders the leaderboard widget as a PNG image — a dark, neon "robot HUD"
look: near-black glass panel, glowing cyan/magenta/violet accents, a
faint circuit-grid backdrop, scanlines, and circuit-trace tick marks
along the frame.

Self-contained: only needs the two fonts the project already ships with
(FONT_BOLD, FONT_REGULAR). No new files, no config.py changes required —
this file is the only thing you ever need to touch to restyle the widget.

Everything is drawn with Pillow shapes/text rather than relying on emoji
glyphs from the system font (those often render as blank boxes on a
headless server), so the card looks identical everywhere it's hosted.
"""

from __future__ import annotations

import asyncio
import io
import time
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter
import aiohttp

from config import FONT_BOLD, FONT_REGULAR

# ---- Everything below is safe to tweak in this one file ----
BRAND_TEXT = "POINTS SYSTEM"  # small tag shown bottom-right of the card

# How long a fetched avatar is kept before re-fetching (seconds).
# Avatars rarely change, so a few minutes of caching removes almost all
# repeat network calls on back-to-back /leaderboard requests.
AVATAR_CACHE_TTL = 300
# Give up on a single slow avatar after this many seconds so one bad
# connection can't stall the whole image.
AVATAR_FETCH_TIMEOUT = 4

WIDTH = 1040
PADDING = 40
HEADER_HEIGHT = 210
ROW_HEIGHT = 104
ROW_GAP = 10
FOOTER_HEIGHT = 70
AVATAR_SIZE = 60

# ---- Palette: near-black glass + neon cyan / magenta / violet ----
BG_TOP = (9, 11, 18)
BG_BOTTOM = (4, 5, 9)
CARD_BG = (13, 16, 24)
CARD_BORDER = (40, 48, 64)
ROW_BG = (16, 20, 30)
ROW_BORDER = (32, 39, 53)
DIVIDER = (30, 36, 50)

NEON_CYAN = (56, 226, 255)
NEON_MAGENTA = (255, 72, 190)
NEON_VIOLET = (158, 108, 255)
NEON_GREEN = (78, 255, 170)

WHITE = (232, 238, 248)
MUTED = (138, 148, 170)
FAINT = (78, 86, 104)

MEDAL_COLORS = {1: NEON_CYAN, 2: NEON_MAGENTA, 3: NEON_VIOLET}
MEDAL_TEXT_ON = (8, 10, 16)  # dark text drawn on top of a bright neon badge


def _font(path, size):
    return ImageFont.truetype(path, size)


def _vertical_gradient(size, top, bottom):
    w, h = size
    base = Image.new("RGB", (1, h), 0)
    for y in range(h):
        t = y / max(h - 1, 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        base.putpixel((0, y), color)
    return base.resize((w, h))


def _blend(base, tint, alpha):
    return tuple(int(base[i] + (tint[i] - base[i]) * alpha) for i in range(3))


def _rounded_rect(draw, box, radius, fill=None, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _text_w(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1], bbox[0], bbox[1]


def _draw_tracked(draw, xy, text, font, fill, tracking=4):
    """Draws text with extra letter-spacing — used for small-caps labels
    and (with a small tracking value) to give plain numbers a spaced-out
    'digital readout' feel without needing a monospace font file."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        w, _, _, _ = _text_w(draw, ch, font)
        x += w + tracking


def _glow_rounded_rect(canvas, box, radius, color, blur=16, alpha=140, width=3):
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(box, radius=radius, outline=color + (alpha,), width=width)
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    canvas.paste(layer, (0, 0), layer)


def _glow_text(canvas, xy, text, font, color, blur=8, alpha=190):
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).text(xy, text, font=font, fill=color + (alpha,))
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    canvas.paste(layer, (0, 0), layer)


def _glow_ellipse(canvas, box, color, blur=10, alpha=170):
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse(box, fill=color + (alpha,))
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    canvas.paste(layer, (0, 0), layer)


def _draw_grid(draw, size, color=(90, 140, 200), alpha=9, step=48):
    w, h = size
    for x in range(0, w, step):
        draw.line((x, 0, x, h), fill=color + (alpha,), width=1)
    for y in range(0, h, step):
        draw.line((0, y, w, y), fill=color + (alpha,), width=1)


def _draw_scanlines(draw, size, color=(0, 0, 0), alpha=28, step=3):
    w, h = size
    for y in range(0, h, step):
        draw.line((0, y, w, y), fill=color + (alpha,), width=1)


def _draw_corner_brackets(draw, box, color, size=26, width=3):
    x0, y0, x1, y1 = box
    for cx, cy, dx, dy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
        draw.line((cx, cy, cx + size * dx, cy), fill=color, width=width)
        draw.line((cx, cy, cx, cy + size * dy), fill=color, width=width)


def _draw_circuit_ticks(draw, box, color, count=14, tick=8):
    """Small perpendicular tick marks along the top and bottom edges of
    the card, like PCB trace pads — reinforces the 'robotic' HUD feel."""
    x0, y0, x1, y1 = box
    span = x1 - x0
    step = span / (count + 1)
    for i in range(1, count + 1):
        x = x0 + step * i
        draw.line((x, y0, x, y0 + tick), fill=color, width=2)
        draw.line((x, y1, x, y1 - tick), fill=color, width=2)


def _draw_signal_bars(draw, x, y, color, bar_w=4, gap=3, heights=(6, 10, 14, 18)):
    """Small ascending signal-strength bars, drawn next to the LIVE tag
    for an extra 'system status' touch."""
    cx = x
    base_y = y
    for h in heights:
        draw.rectangle((cx, base_y - h, cx + bar_w, base_y), fill=color)
        cx += bar_w + gap
    return cx - gap


def _initials(name: str) -> str:
    parts = [p for p in name.split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()


_avatar_cache: dict[int, tuple[float, "Image.Image | None"]] = {}


async def _fetch_avatar_uncached(bot, user_id: int) -> Image.Image | None:
    photos = await bot.get_user_profile_photos(user_id, limit=1)
    if not photos or not photos.photos:
        return None
    file_id = photos.photos[0][-1].file_id
    tg_file = await bot.get_file(file_id)
    async with aiohttp.ClientSession() as session:
        async with session.get(tg_file.file_path) as resp:
            data = await resp.read()
    return Image.open(io.BytesIO(data)).convert("RGB")


async def _fetch_avatar(bot, user_id: int) -> Image.Image | None:
    cached = _avatar_cache.get(user_id)
    if cached and time.monotonic() - cached[0] < AVATAR_CACHE_TTL:
        return cached[1]
    try:
        img = await asyncio.wait_for(_fetch_avatar_uncached(bot, user_id), timeout=AVATAR_FETCH_TIMEOUT)
    except Exception:
        img = None
    _avatar_cache[user_id] = (time.monotonic(), img)
    return img


async def _fetch_avatars_concurrently(bot, user_ids: list[int]) -> dict[int, "Image.Image | None"]:
    """Fetches every avatar for the board at once instead of one-by-one —
    this is the single biggest speed win for /leaderboard, since network
    calls used to be awaited sequentially inside the drawing loop."""
    results = await asyncio.gather(*[_fetch_avatar(bot, uid) for uid in user_ids])
    return dict(zip(user_ids, results))


def _circle_avatar(img: Image.Image, size: int, ring_color=None) -> Image.Image:
    pad = 4 if ring_color else 0
    full = size + pad * 2
    img = ImageOps.fit(img, (size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    out = Image.new("RGBA", (full, full), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    if ring_color:
        d.ellipse((0, 0, full, full), fill=ring_color)
    out.paste(img, (pad, pad), mask)
    return out


def _initials_avatar(name: str, size: int, color, ring_color=None) -> Image.Image:
    pad = 4 if ring_color else 0
    full = size + pad * 2
    out = Image.new("RGBA", (full, full), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    if ring_color:
        d.ellipse((0, 0, full, full), fill=ring_color)
    d.ellipse((pad, pad, pad + size, pad + size), fill=color)
    font = _font(FONT_BOLD, int(size * 0.38))
    text = _initials(name)
    tw, th, bx, by = _text_w(d, text, font)
    d.text((pad + (size - tw) / 2 - bx, pad + (size - th) / 2 - by), text, font=font, fill=(10, 12, 18))
    return out


def _fmt_points(points: int) -> str:
    return f"{points:,}"


def _draw_card(width: int, height: int, group_title: str, updated_label: str,
                rows: list[dict], avatars: dict, leader_points: int,
                min_visible_rank: int = 1, dot_pulse: float = 0.6) -> Image.Image:
    """Draws one complete card and returns it as a PIL Image (RGB).

    min_visible_rank: rows with rank >= this are drawn; lower ranks are
    skipped (used by the animation to reveal the board bottom-up).
    dot_pulse (0..1): controls the LIVE dot's glow strength/size, so the
    animation can make it visibly pulse across frames.
    """
    n = len(rows)
    canvas = _vertical_gradient((width, height), BG_TOP, BG_BOTTOM)
    draw = ImageDraw.Draw(canvas, "RGBA")

    _draw_grid(draw, canvas.size)

    card_box = (PADDING - 10, PADDING - 10, width - PADDING + 10, height - PADDING + 10)
    _glow_rounded_rect(canvas, card_box, 26, NEON_CYAN, blur=18, alpha=95, width=2)
    draw = ImageDraw.Draw(canvas, "RGBA")

    _rounded_rect(draw, card_box, 26, fill=CARD_BG, outline=CARD_BORDER, width=1)
    _draw_corner_brackets(draw, card_box, NEON_CYAN + (210,), size=26, width=3)
    _draw_circuit_ticks(draw, card_box, NEON_CYAN + (70,), count=16, tick=7)

    left = PADDING + 16
    eyebrow_font = _font(FONT_BOLD, 16)
    title_font = _font(FONT_BOLD, 44)
    sub_font = _font(FONT_REGULAR, 22)

    _draw_tracked(draw, (left, PA"""
Renders the leaderboard widget as a PNG image — a dark, neon "robot HUD"
look: near-black glass panel, glowing cyan/magenta/violet accents, a
faint circuit-grid backdrop, scanlines, and circuit-trace tick marks
along the frame.

Self-contained: only needs the two fonts the project already ships with
(FONT_BOLD, FONT_REGULAR). No new files, no config.py changes required —
this file is the only thing you ever need to touch to restyle the widget.

Everything is drawn with Pillow shapes/text rather than relying on emoji
glyphs from the system font (those often render as blank boxes on a
headless server), so the card looks identical everywhere it's hosted.
"""

from __future__ import annotations

import asyncio
import io
import time
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter
import aiohttp

from config import FONT_BOLD, FONT_REGULAR

# ---- Everything below is safe to tweak in this one file ----
BRAND_TEXT = "POINTS SYSTEM"  # small tag shown bottom-right of the card

# How long a fetched avatar is kept before re-fetching (seconds).
# Avatars rarely change, so a few minutes of caching removes almost all
# repeat network calls on back-to-back /leaderboard requests.
AVATAR_CACHE_TTL = 300
# Give up on a single slow avatar after this many seconds so one bad
# connection can't stall the whole image.
AVATAR_FETCH_TIMEOUT = 4

WIDTH = 1040
PADDING = 40
HEADER_HEIGHT = 210
ROW_HEIGHT = 104
ROW_GAP = 10
FOOTER_HEIGHT = 70
AVATAR_SIZE = 60

# ---- Palette: near-black glass + neon cyan / magenta / violet ----
BG_TOP = (9, 11, 18)
BG_BOTTOM = (4, 5, 9)
CARD_BG = (13, 16, 24)
CARD_BORDER = (40, 48, 64)
ROW_BG = (16, 20, 30)
ROW_BORDER = (32, 39, 53)
DIVIDER = (30, 36, 50)

NEON_CYAN = (56, 226, 255)
NEON_MAGENTA = (255, 72, 190)
NEON_VIOLET = (158, 108, 255)
NEON_GREEN = (78, 255, 170)

WHITE = (232, 238, 248)
MUTED = (138, 148, 170)
FAINT = (78, 86, 104)

MEDAL_COLORS = {1: NEON_CYAN, 2: NEON_MAGENTA, 3: NEON_VIOLET}
MEDAL_TEXT_ON = (8, 10, 16)  # dark text drawn on top of a bright neon badge


def _font(path, size):
    return ImageFont.truetype(path, size)


def _vertical_gradient(size, top, bottom):
    w, h = size
    base = Image.new("RGB", (1, h), 0)
    for y in range(h):
        t = y / max(h - 1, 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        base.putpixel((0, y), color)
    return base.resize((w, h))


def _blend(base, tint, alpha):
    return tuple(int(base[i] + (tint[i] - base[i]) * alpha) for i in range(3))


def _rounded_rect(draw, box, radius, fill=None, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _text_w(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1], bbox[0], bbox[1]


def _draw_tracked(draw, xy, text, font, fill, tracking=4):
    """Draws text with extra letter-spacing — used for small-caps labels
    and (with a small tracking value) to give plain numbers a spaced-out
    'digital readout' feel without needing a monospace font file."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        w, _, _, _ = _text_w(draw, ch, font)
        x += w + tracking


def _glow_rounded_rect(canvas, box, radius, color, blur=16, alpha=140, width=3):
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(box, radius=radius, outline=color + (alpha,), width=width)
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    canvas.paste(layer, (0, 0), layer)


def _glow_text(canvas, xy, text, font, color, blur=8, alpha=190):
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).text(xy, text, font=font, fill=color + (alpha,))
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    canvas.paste(layer, (0, 0), layer)


def _glow_ellipse(canvas, box, color, blur=10, alpha=170):
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse(box, fill=color + (alpha,))
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    canvas.paste(layer, (0, 0), layer)


def _draw_grid(draw, size, color=(90, 140, 200), alpha=9, step=48):
    w, h = size
    for x in range(0, w, step):
        draw.line((x, 0, x, h), fill=color + (alpha,), width=1)
    for y in range(0, h, step):
        draw.line((0, y, w, y), fill=color + (alpha,), width=1)


def _draw_scanlines(draw, size, color=(0, 0, 0), alpha=28, step=3):
    w, h = size
    for y in range(0, h, step):
        draw.line((0, y, w, y), fill=color + (alpha,), width=1)


def _draw_corner_brackets(draw, box, color, size=26, width=3):
    x0, y0, x1, y1 = box
    for cx, cy, dx, dy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
        draw.line((cx, cy, cx + size * dx, cy), fill=color, width=width)
        draw.line((cx, cy, cx, cy + size * dy), fill=color, width=width)


def _draw_circuit_ticks(draw, box, color, count=14, tick=8):
    """Small perpendicular tick marks along the top and bottom edges of
    the card, like PCB trace pads — reinforces the 'robotic' HUD feel."""
    x0, y0, x1, y1 = box
    span = x1 - x0
    step = span / (count + 1)
    for i in range(1, count + 1):
        x = x0 + step * i
        draw.line((x, y0, x, y0 + tick), fill=color, width=2)
        draw.line((x, y1, x, y1 - tick), fill=color, width=2)


def _draw_signal_bars(draw, x, y, color, bar_w=4, gap=3, heights=(6, 10, 14, 18)):
    """Small ascending signal-strength bars, drawn next to the LIVE tag
    for an extra 'system status' touch."""
    cx = x
    base_y = y
    for h in heights:
        draw.rectangle((cx, base_y - h, cx + bar_w, base_y), fill=color)
        cx += bar_w + gap
    return cx - gap


def _initials(name: str) -> str:
    parts = [p for p in name.split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()


_avatar_cache: dict[int, tuple[float, "Image.Image | None"]] = {}


async def _fetch_avatar_uncached(bot, user_id: int) -> Image.Image | None:
    photos = await bot.get_user_profile_photos(user_id, limit=1)
    if not photos or not photos.photos:
        return None
    file_id = photos.photos[0][-1].file_id
    tg_file = await bot.get_file(file_id)
    async with aiohttp.ClientSession() as session:
        async with session.get(tg_file.file_path) as resp:
            data = await resp.read()
    return Image.open(io.BytesIO(data)).convert("RGB")


async def _fetch_avatar(bot, user_id: int) -> Image.Image | None:
    cached = _avatar_cache.get(user_id)
    if cached and time.monotonic() - cached[0] < AVATAR_CACHE_TTL:
        return cached[1]
    try:
        img = await asyncio.wait_for(_fetch_avatar_uncached(bot, user_id), timeout=AVATAR_FETCH_TIMEOUT)
    except Exception:
        img = None
    _avatar_cache[user_id] = (time.monotonic(), img)
    return img


async def _fetch_avatars_concurrently(bot, user_ids: list[int]) -> dict[int, "Image.Image | None"]:
    """Fetches every avatar for the board at once instead of one-by-one —
    this is the single biggest speed win for /leaderboard, since network
    calls used to be awaited sequentially inside the drawing loop."""
    results = await asyncio.gather(*[_fetch_avatar(bot, uid) for uid in user_ids])
    return dict(zip(user_ids, results))


def _circle_avatar(img: Image.Image, size: int, ring_color=None) -> Image.Image:
    pad = 4 if ring_color else 0
    full = size + pad * 2
    img = ImageOps.fit(img, (size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    out = Image.new("RGBA", (full, full), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    if ring_color:
        d.ellipse((0, 0, full, full), fill=ring_color)
    out.paste(img, (pad, pad), mask)
    return out


def _initials_avatar(name: str, size: int, color, ring_color=None) -> Image.Image:
    pad = 4 if ring_color else 0
    full = size + pad * 2
    out = Image.new("RGBA", (full, full), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    if ring_color:
        d.ellipse((0, 0, full, full), fill=ring_color)
    d.ellipse((pad, pad, pad + size, pad + size), fill=color)
    font = _font(FONT_BOLD, int(size * 0.38))
    text = _initials(name)
    tw, th, bx, by = _text_w(d, text, font)
    d.text((pad + (size - tw) / 2 - bx, pad + (size - th) / 2 - by), text, font=font, fill=(10, 12, 18))
    return out


def _fmt_points(points: int) -> str:
    return f"{points:,}"


def _draw_card(width: int, height: int, group_title: str, updated_label: str,
                rows: list[dict], avatars: dict, leader_points: int,
                min_visible_rank: int = 1, dot_pulse: float = 0.6) -> Image.Image:
    """Draws one complete card and returns it as a PIL Image (RGB).

    min_visible_rank: rows with rank >= this are drawn; lower ranks are
    skipped (used by the animation to reveal the board bottom-up).
    dot_pulse (0..1): controls the LIVE dot's glow strength/size, so the
    animation can make it visibly pulse across frames.
    """
    n = len(rows)
    canvas = _vertical_gradient((width, height), BG_TOP, BG_BOTTOM)
    draw = ImageDraw.Draw(canvas, "RGBA")

    _draw_grid(draw, canvas.size)

    card_box = (PADDING - 10, PADDING - 10, width - PADDING + 10, height - PADDING + 10)
    _glow_rounded_rect(canvas, card_box, 26, NEON_CYAN, blur=18, alpha=95, width=2)
    draw = ImageDraw.Draw(canvas, "RGBA")

    _rounded_rect(draw, card_box, 26, fill=CARD_BG, outline=CARD_BORDER, width=1)
    _draw_corner_brackets(draw, card_box, NEON_CYAN + (210,), size=26, width=3)
    _draw_circuit_ticks(draw, card_box, NEON_CYAN + (70,), count=16, tick=7)

    left = PADDING + 16
    eyebrow_font = _font(FONT_BOLD, 16)
    title_font = _font(FONT_BOLD, 44)
    sub_font = _font(FONT_REGULAR, 22)

    _draw_tracked(draw, (left, PADDING + 14), "SYSTEM · GROUP RANKINGS", eyebrow_font, NEON_CYAN, tracking=3)
    _glow_text(canvas, (left, PADDING + 36), "LEADERBOARD", title_font, NEON_CYAN, blur=10, alpha=130)
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.text((left, PADDING + 36), "LEADERBOARD", font=title_font, fill=WHITE)

    bar_y0, bar_y1, bar_w = PADDING + 98, PADDING + 102, 220
    for i in range(bar_w):
        t = i / bar_w
        c = _blend(NEON_CYAN, NEON_MAGENTA, t / 0.5) if t < 0.5 else _blend(NEON_MAGENTA, NEON_VIOLET, (t - 0.5) / 0.5)
        draw.line((left + i, bar_y0, left + i, bar_y1), fill=c)

    subtitle = (group_title or "Group").strip()
    if len(subtitle) > 64:
        subtitle = subtitle[:61] + "..."
    draw.text((left, PADDING + 114), subtitle, font=sub_font, fill=MUTED)

    # "LIVE" neon tag + pulsing dot + signal bars, top-right
    tag_font = _font(FONT_BOLD, 16)
    tag_text = "LIVE"
    tw, th, bx, by = _text_w(draw, tag_text, tag_font)
    tag_pad_x, tag_pad_y = 14, 8
    tag_w, tag_h = tw + tag_pad_x * 2, th + tag_pad_y * 2
    tag_x1 = width - PADDING - 16 - tag_w
    tag_y1 = PADDING + 14
    _glow_rounded_rect(canvas, (tag_x1, tag_y1, tag_x1 + tag_w, tag_y1 + tag_h), tag_h / 2,
                        NEON_GREEN, blur=10, alpha=130, width=2)
    draw = ImageDraw.Draw(canvas, "RGBA")
    _rounded_rect(draw, (tag_x1, tag_y1, tag_x1 + tag_w, tag_y1 + tag_h), tag_h / 2,
                  fill=_blend(CARD_BG, NEON_GREEN, 0.16), outline=NEON_GREEN, width=1)
    dot_r = 3 + dot_pulse * 3
    dot_cx, dot_cy = tag_x1 + tag_pad_x - 8, tag_y1 + tag_h / 2
    _glow_ellipse(canvas, (dot_cx - dot_r - 3, dot_cy - dot_r - 3, dot_cx + dot_r + 3, dot_cy + dot_r + 3),
                  NEON_GREEN, blur=6, alpha=int(140 + dot_pulse * 100))
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.ellipse((dot_cx - dot_r, dot_cy - dot_r, dot_cx + dot_r, dot_cy + dot_r), fill=NEON_GREEN)
    draw.text((tag_x1 + tag_pad_x + 6, tag_y1 + tag_pad_y - by), tag_text, font=tag_font, fill=NEON_GREEN)
    _draw_signal_bars(draw, tag_x1 - 78, tag_y1 + tag_h - 6, NEON_CYAN)

    draw.line((PADDING + 10, HEADER_HEIGHT, width - PADDING - 10, HEADER_HEIGHT), fill=DIVIDER, width=1)

    y = HEADER_HEIGHT + 18
    rank_font_top = _font(FONT_BOLD, 26)
    rank_font = _font(FONT_BOLD, 24)
    name_font = _font(FONT_BOLD, 26)
    handle_font = _font(FONT_REGULAR, 17)
    pts_font = _font(FONT_BOLD, 28)
    pts_label_font = _font(FONT_BOLD, 13)

    for i, m in enumerate(rows, start=1):
        top, bottom = y, y + ROW_HEIGHT
        y += ROW_HEIGHT + ROW_GAP
        if i < min_visible_rank:
            continue  # not revealed yet in this animation frame

        is_top3 = i <= 3
        medal = MEDAL_COLORS.get(i)
        row_box = (PADDING + 6, top, width - PADDING - 6, bottom)

        if is_top3:
            _glow_rounded_rect(canvas, row_box, 16, medal, blur=14, alpha=75, width=2)
            draw = ImageDraw.Draw(canvas, "RGBA")

        row_bg = _blend(ROW_BG, medal, 0.12) if is_top3 else ROW_BG
        _rounded_rect(draw, row_box, 16, fill=row_bg, outline=(medal if is_top3 else ROW_BORDER), width=1)

        if is_top3:
            draw.rounded_rectangle((PADDING + 6, top, PADDING + 12, bottom), 4, fill=medal)

        rank_x = PADDING + 34
        if is_top3:
            r = 22
            cx, cy = rank_x + r, top + ROW_HEIGHT // 2
            _glow_ellipse(canvas, (cx - r - 4, cy - r - 4, cx + r + 4, cy + r + 4), medal, blur=8, alpha=155)
            draw = ImageDraw.Draw(canvas, "RGBA")
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=medal)
            rt = str(i)
            tw, th, bx, by = _text_w(draw, rt, rank_font_top)
            draw.text((cx - tw / 2 - bx, cy - th / 2 - by), rt, font=rank_font_top, fill=MEDAL_TEXT_ON)
            avatar_x = rank_x + r * 2 + 18
        else:
            rt = str(i)
            tw, th, bx, by = _text_w(draw, rt, rank_font)
            draw.text((rank_x, top + ROW_HEIGHT / 2 - th / 2 - by), rt, font=rank_font, fill=FAINT)
            avatar_x = rank_x + 40

        display_name = m.get("first_name") or m.get("username") or f"User {m['user_id']}"
        ring = medal if is_top3 else (48, 56, 74)
        avatar_img = avatars.get(m["user_id"])
        av = _circle_avatar(avatar_img, AVATAR_SIZE, ring) if avatar_img else \
            _initials_avatar(display_name, AVATAR_SIZE, medal if is_top3 else (58, 66, 86), ring)
        canvas.paste(av, (avatar_x, top + (ROW_HEIGHT - av.height) // 2), av)
        draw = ImageDraw.Draw(canvas, "RGBA")

        name_x = avatar_x + av.width + 18
        name_display = display_name
        if len(name_display) > 26:
            name_display = name_display[:23] + "..."
        draw.text((name_x, top + 16), name_display, font=name_font, fill=WHITE)
        if m.get("username"):
            handle = f"@{m['username']}"
            if len(handle) > 28:
                handle = handle[:25] + "..."
            draw.text((name_x, top + 48), handle, font=handle_font, fill=MUTED)
        else:
            draw.text((name_x, top + 48), f"RANK #{i}", font=handle_font, fill=FAINT)

        pts_text = _fmt_points(m["points"])
        pts_color = medal if is_top3 else WHITE
        tw, th, bx, by = _text_w(draw, pts_text, pts_font)
        tracked_w = tw + (len(pts_text) - 1) * 2
        pts_x = width - PADDING - 36 - tracked_w
        _draw_tracked(draw, (pts_x, top + ROW_HEIGHT / 2 - th / 2 - by - 6), pts_text, pts_font, pts_color, tracking=2)
        lbl_w, _, lbl_bx, _ = _text_w(draw, "PTS", pts_label_font)
        draw.text((width - PADDING - 36 - lbl_w, top + ROW_HEIGHT / 2 + 14), "PTS",
                   font=pts_label_font, fill=FAINT)

        bar_x0, bar_x1 = PADDING + 22, width - PADDING - 22
        bar_y0, bar_y1 = bottom - 16, bottom - 12
        draw.rounded_rectangle((bar_x0, bar_y0, bar_x1, bar_y1), 2, fill=(255, 255, 255, 16))
        pct = min(1.0, max(0.0, m["points"] / leader_points)) if leader_points > 0 else 0.0
        fill_x1 = bar_x0 + (bar_x1 - bar_x0) * pct
        if fill_x1 > bar_x0 + 2:
            bar_color = medal if is_top3 else NEON_CYAN
            draw.rounded_rectangle((bar_x0, bar_y0, fill_x1, bar_y1), 2, fill=bar_color + (210,))

    if n == 0:
        draw.text((left, y + 10), "No members ranked yet.", font=name_font, fill=MUTED)
        y += ROW_HEIGHT

    footer_y = y + 12
    bar_w2 = width - PADDING * 2 - 20
    for i in range(0, bar_w2, 4):
        t = i / bar_w2
        c = _blend(NEON_CYAN, NEON_MAGENTA, t / 0.5) if t < 0.5 else _blend(NEON_MAGENTA, NEON_VIOLET, (t - 0.5) / 0.5)
        draw.line((PADDING + 10 + i, footer_y, PADDING + 10 + min(i + 4, bar_w2), footer_y), fill=c + (120,), width=1)

    footer_font = _font(FONT_REGULAR, 18)
    draw.text((left, footer_y + 18), updated_label, font=footer_font, fill=MUTED)

    brand_font = _font(FONT_BOLD, 16)
    brand_text = f"[ {BRAND_TEXT.upper()} ]"
    tw, th, bx, by = _text_w(draw, brand_text, brand_font)
    _draw_tracked(draw, (width - PADDING - 16 - tw - (len(brand_text) - 1) * 2, footer_y + 18 - by),
                  brand_text, brand_font, NEON_CYAN, tracking=2)

    _draw_scanlines(draw, canvas.size)
    return canvas.convert("RGB")


async def render_leaderboard(bot, group_title: str, rows: list[dict], updated_label: str) -> bytes:
    """rows: list of dicts with user_id, username, first_name, points (already sorted desc)"""
    n = len(rows)
    body_height = max(n, 1) * (ROW_HEIGHT + ROW_GAP)
    height = HEADER_HEIGHT + body_height + FOOTER_HEIGHT + PADDING

    avatars = await _fetch_avatars_concurrently(bot, [m["user_id"] for m in rows]) if rows else {}
    leader_points = max((m["points"] for m in rows), default=1)

    canvas = _draw_card(WIDTH, height, group_title, updated_label, rows, avatars, leader_points,
                         min_visible_rank=1, dot_pulse=0.6)

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


async def render_leaderboard_animation(bot, group_title: str, rows: list[dict], updated_label: str,
                                        fps: int = 15, hold_per_step: int = 3,
                                        final_hold_seconds: float = 1.6) -> bytes:
    """Renders an MP4 (silent, autoplay, loops in Telegram) that reveals the
    board from last place up to #1, then holds on the finished board with a
    gently pulsing LIVE indicator.

    Uses actual video encoding (not a GIF) so the neon glow keeps full color
    quality — GIF's 256-colour palette would band and muddy the gradients.
    """
    import imageio.v2 as imageio
    import numpy as np
    import os

    n = len(rows)
    body_height = max(n, 1) * (ROW_HEIGHT + ROW_GAP)
    height = HEADER_HEIGHT + body_height + FOOTER_HEIGHT + PADDING
    # H.264 needs even dimensions
    width = WIDTH if WIDTH % 2 == 0 else WIDTH + 1
    height = height if height % 2 == 0 else height + 1

    avatars = await _fetch_avatars_concurrently(bot, [m["user_id"] for m in rows]) if rows else {}
    leader_points = max((m["points"] for m in rows), default=1)

    frames: list = []

    # Reveal bottom-up: show only the last rank first, then progressively
    # more of the board, ending with #1 appearing last (countdown suspense).
    for reveal_step in range(n, 0, -1):
        frame = _draw_card(width, height, group_title, updated_label, rows, avatars, leader_points,
                            min_visible_rank=reveal_step, dot_pulse=0.5)
        for _ in range(hold_per_step):
            frames.append(frame)

    if n == 0:
        frames.append(_draw_card(width, height, group_title, updated_label, rows, avatars, leader_points,
                                  min_visible_rank=1, dot_pulse=0.5))

    # Final hold: fully revealed board with a few pulse variants of the LIVE
    # dot, cycled to keep it feeling "alive" without re-rendering every frame.
    pulse_variants = [
        _draw_card(width, height, group_title, updated_label, rows, avatars, leader_points,
                   min_visible_rank=1, dot_pulse=p)
        for p in (0.2, 0.6, 1.0, 0.6)
    ]
    hold_frames = max(1, int(final_hold_seconds * fps))
    for i in range(hold_frames):
        frames.append(pulse_variants[i % len(pulse_variants)])

    tmp_path = f"/tmp/leaderboard_{id(rows)}_{int(time.monotonic() * 1000)}.mp4"
    try:
        with imageio.get_writer(tmp_path, fps=fps, codec="libx264", quality=8,
                                 pixelformat="yuv420p", macro_block_size=None) as writer:
            for frame in frames:
                writer.append_data(np.array(frame))
        with open(tmp_path, "rb") as f:
            data = f.read()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return dataG + 14), "SYSTEM · GROUP RANKINGS", eyebrow_font, NEON_CYAN, tracking=3)
    _glow_text(canvas, (left, PADDING + 36), "LEADERBOARD", title_font, NEON_CYAN, blur=10, alpha=130)
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.text((left, PADDING + 36), "LEADERBOARD", font=title_font, fill=WHITE)

    bar_y0, bar_y1, bar_w = PADDING + 98, PADDING + 102, 220
    for i in range(bar_w):
        t = i / bar_w
        c = _blend(NEON_CYAN, NEON_MAGENTA, t / 0.5) if t < 0.5 else _blend(NEON_MAGENTA, NEON_VIOLET, (t - 0.5) / 0.5)
        draw.line((left + i, bar_y0, left + i, bar_y1), fill=c)

    subtitle = (group_title or "Group").strip()
    if len(subtitle) > 64:
        subtitle = subtitle[:61] + "..."
    draw.text((left, PADDING + 114), subtitle, font=sub_font, fill=MUTED)

    # "LIVE" neon tag + pulsing dot + signal bars, top-right
    tag_font = _font(FONT_BOLD, 16)
    tag_text = "LIVE"
    tw, th, bx, by = _text_w(draw, tag_text, tag_font)
    tag_pad_x, tag_pad_y = 14, 8
    tag_w, tag_h = tw + tag_pad_x * 2, th + tag_pad_y * 2
    tag_x1 = width - PADDING - 16 - tag_w
    tag_y1 = PADDING + 14
    _glow_rounded_rect(canvas, (tag_x1, tag_y1, tag_x1 + tag_w, tag_y1 + tag_h), tag_h / 2,
                        NEON_GREEN, blur=10, alpha=130, width=2)
    draw = ImageDraw.Draw(canvas, "RGBA")
    _rounded_rect(draw, (tag_x1, tag_y1, tag_x1 + tag_w, tag_y1 + tag_h), tag_h / 2,
                  fill=_blend(CARD_BG, NEON_GREEN, 0.16), outline=NEON_GREEN, width=1)
    dot_r = 3 + dot_pulse * 3
    dot_cx, dot_cy = tag_x1 + tag_pad_x - 8, tag_y1 + tag_h / 2
    _glow_ellipse(canvas, (dot_cx - dot_r - 3, dot_cy - dot_r - 3, dot_cx + dot_r + 3, dot_cy + dot_r + 3),
                  NEON_GREEN, blur=6, alpha=int(140 + dot_pulse * 100))
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.ellipse((dot_cx - dot_r, dot_cy - dot_r, dot_cx + dot_r, dot_cy + dot_r), fill=NEON_GREEN)
    draw.text((tag_x1 + tag_pad_x + 6, tag_y1 + tag_pad_y - by), tag_text, font=tag_font, fill=NEON_GREEN)
    _draw_signal_bars(draw, tag_x1 - 78, tag_y1 + tag_h - 6, NEON_CYAN)

    draw.line((PADDING + 10, HEADER_HEIGHT, width - PADDING - 10, HEADER_HEIGHT), fill=DIVIDER, width=1)

    y = HEADER_HEIGHT + 18
    rank_font_top = _font(FONT_BOLD, 26)
    rank_font = _font(FONT_BOLD, 24)
    name_font = _font(FONT_BOLD, 26)
    handle_font = _font(FONT_REGULAR, 17)
    pts_font = _font(FONT_BOLD, 28)
    pts_label_font = _font(FONT_BOLD, 13)

    for i, m in enumerate(rows, start=1):
        top, bottom = y, y + ROW_HEIGHT
        y += ROW_HEIGHT + ROW_GAP
        if i < min_visible_rank:
            continue  # not revealed yet in this animation frame

        is_top3 = i <= 3
        medal = MEDAL_COLORS.get(i)
        row_box = (PADDING + 6, top, width - PADDING - 6, bottom)

        if is_top3:
            _glow_rounded_rect(canvas, row_box, 16, medal, blur=14, alpha=75, width=2)
            draw = ImageDraw.Draw(canvas, "RGBA")

        row_bg = _blend(ROW_BG, medal, 0.12) if is_top3 else ROW_BG
        _rounded_rect(draw, row_box, 16, fill=row_bg, outline=(medal if is_top3 else ROW_BORDER), width=1)

        if is_top3:
            draw.rounded_rectangle((PADDING + 6, top, PADDING + 12, bottom), 4, fill=medal)

        rank_x = PADDING + 34
        if is_top3:
            r = 22
            cx, cy = rank_x + r, top + ROW_HEIGHT // 2
            _glow_ellipse(canvas, (cx - r - 4, cy - r - 4, cx + r + 4, cy + r + 4), medal, blur=8, alpha=155)
            draw = ImageDraw.Draw(canvas, "RGBA")
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=medal)
            rt = str(i)
            tw, th, bx, by = _text_w(draw, rt, rank_font_top)
            draw.text((cx - tw / 2 - bx, cy - th / 2 - by), rt, font=rank_font_top, fill=MEDAL_TEXT_ON)
            avatar_x = rank_x + r * 2 + 18
        else:
            rt = str(i)
            tw, th, bx, by = _text_w(draw, rt, rank_font)
            draw.text((rank_x, top + ROW_HEIGHT / 2 - th / 2 - by), rt, font=rank_font, fill=FAINT)
            avatar_x = rank_x + 40

        display_name = m.get("first_name") or m.get("username") or f"User {m['user_id']}"
        ring = medal if is_top3 else (48, 56, 74)
        avatar_img = avatars.get(m["user_id"])
        av = _circle_avatar(avatar_img, AVATAR_SIZE, ring) if avatar_img else \
            _initials_avatar(display_name, AVATAR_SIZE, medal if is_top3 else (58, 66, 86), ring)
        canvas.paste(av, (avatar_x, top + (ROW_HEIGHT - av.height) // 2), av)
        draw = ImageDraw.Draw(canvas, "RGBA")

        name_x = avatar_x + av.width + 18
        name_display = display_name
        if len(name_display) > 26:
            name_display = name_display[:23] + "..."
        draw.text((name_x, top + 16), name_display, font=name_font, fill=WHITE)
        if m.get("username"):
            handle = f"@{m['username']}"
            if len(handle) > 28:
                handle = handle[:25] + "..."
            draw.text((name_x, top + 48), handle, font=handle_font, fill=MUTED)
        else:
            draw.text((name_x, top + 48), f"RANK #{i}", font=handle_font, fill=FAINT)

        pts_text = _fmt_points(m["points"])
        pts_color = medal if is_top3 else WHITE
        tw, th, bx, by = _text_w(draw, pts_text, pts_font)
        tracked_w = tw + (len(pts_text) - 1) * 2
        pts_x = width - PADDING - 36 - tracked_w
        _draw_tracked(draw, (pts_x, top + ROW_HEIGHT / 2 - th / 2 - by - 6), pts_text, pts_font, pts_color, tracking=2)
        lbl_w, _, lbl_bx, _ = _text_w(draw, "PTS", pts_label_font)
        draw.text((width - PADDING - 36 - lbl_w, top + ROW_HEIGHT / 2 + 14), "PTS",
                   font=pts_label_font, fill=FAINT)

        bar_x0, bar_x1 = PADDING + 22, width - PADDING - 22
        bar_y0, bar_y1 = bottom - 16, bottom - 12
        draw.rounded_rectangle((bar_x0, bar_y0, bar_x1, bar_y1), 2, fill=(255, 255, 255, 16))
        pct = min(1.0, max(0.0, m["points"] / leader_points)) if leader_points > 0 else 0.0
        fill_x1 = bar_x0 + (bar_x1 - bar_x0) * pct
        if fill_x1 > bar_x0 + 2:
            bar_color = medal if is_top3 else NEON_CYAN
            draw.rounded_rectangle((bar_x0, bar_y0, fill_x1, bar_y1), 2, fill=bar_color + (210,))

    if n == 0:
        draw.text((left, y + 10), "No members ranked yet.", font=name_font, fill=MUTED)
        y += ROW_HEIGHT

    footer_y = y + 12
    bar_w2 = width - PADDING * 2 - 20
    for i in range(0, bar_w2, 4):
        t = i / bar_w2
        c = _blend(NEON_CYAN, NEON_MAGENTA, t / 0.5) if t < 0.5 else _blend(NEON_MAGENTA, NEON_VIOLET, (t - 0.5) / 0.5)
        draw.line((PADDING + 10 + i, footer_y, PADDING + 10 + min(i + 4, bar_w2), footer_y), fill=c + (120,), width=1)

    footer_font = _font(FONT_REGULAR, 18)
    draw.text((left, footer_y + 18), updated_label, font=footer_font, fill=MUTED)

    brand_font = _font(FONT_BOLD, 16)
    brand_text = f"[ {BRAND_TEXT.upper()} ]"
    tw, th, bx, by = _text_w(draw, brand_text, brand_font)
    _draw_tracked(draw, (width - PADDING - 16 - tw - (len(brand_text) - 1) * 2, footer_y + 18 - by),
                  brand_text, brand_font, NEON_CYAN, tracking=2)

    _draw_scanlines(draw, canvas.size)
    return canvas.convert("RGB")


async def render_leaderboard(bot, group_title: str, rows: list[dict], updated_label: str) -> bytes:
    """rows: list of dicts with user_id, username, first_name, points (already sorted desc)"""
    n = len(rows)
    body_height = max(n, 1) * (ROW_HEIGHT + ROW_GAP)
    height = HEADER_HEIGHT + body_height + FOOTER_HEIGHT + PADDING

    avatars = await _fetch_avatars_concurrently(bot, [m["user_id"] for m in rows]) if rows else {}
    leader_points = max((m["points"] for m in rows), default=1)

    canvas = _draw_card(WIDTH, height, group_title, updated_label, rows, avatars, leader_points,
                         min_visible_rank=1, dot_pulse=0.6)

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


async def render_leaderboard_animation(bot, group_title: str, rows: list[dict], updated_label: str,
    enders the "🏆 Live Leaderboard" widget as a PNG image.

We draw everything with Pillow shapes/text rather than relying on emoji
glyphs from the system font (those often render as tofu boxes on a
headless server), so the card looks clean and consistent everywhere,
including on Wispbyte.
"""

from __future__ import annotations

import io
from PIL import Image, ImageDraw, ImageFont, ImageOps
import aiohttp

from config import FONT_BOLD, FONT_REGULAR

WIDTH = 1000
ROW_HEIGHT = 84
HEADER_HEIGHT = 170
FOOTER_HEIGHT = 60
PADDING = 30
AVATAR_SIZE = 56

BG_TOP = (24, 15, 56)
BG_BOTTOM = (10, 8, 30)
CARD_BG = (32, 24, 66)
ROW_BG_ODD = (38, 29, 78)
ROW_BG_EVEN = (44, 34, 90)
GOLD = (255, 199, 44)
SILVER = (200, 205, 214)
BRONZE = (205, 127, 80)
WHITE = (245, 245, 250)
MUTED = (170, 165, 195)
ACCENT = (108, 99, 255)


def _font(path, size):
    return ImageFont.truetype(path, size)


def _vertical_gradient(size, top, bottom):
    w, h = size
    base = Image.new("RGB", (1, h), 0)
    for y in range(h):
        t = y / max(h - 1, 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        base.putpixel((0, y), color)
    return base.resize((w, h))


def _rounded_rect(draw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def _draw_star(draw, cx, cy, r_outer, r_inner, fill):
    import math
    points = []
    for i in range(10):
        angle = math.pi / 2 + i * math.pi / 5
        r = r_outer if i % 2 == 0 else r_inner
        points.append((cx + r * math.cos(angle), cy - r * math.sin(angle)))
    draw.polygon(points, fill=fill)


def _initials(name: str) -> str:
    parts = [p for p in name.split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()


async def _fetch_avatar(bot, user_id: int) -> Image.Image | None:
    try:
        photos = await bot.get_user_profile_photos(user_id, limit=1)
        if not photos or not photos.photos:
            return None
        file_id = photos.photos[0][-1].file_id
        tg_file = await bot.get_file(file_id)
        async with aiohttp.ClientSession() as session:
            async with session.get(tg_file.file_path) as resp:
            ita"""
data = await resp.read()
        img = Image.open(io.BytesIO(data)).convert("RGB")
        return img
    except Exception:
        return None


def _circle_avatar(img: Image.Image, size: int) -> Image.Image:
    img = ImageOps.fit(img, (size, size), Image.LANCZOS)
dmask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.ellipse((0, 0, size, size), fill=255)
    out = Image.new("RGBA", (size, size))
    oaaste(img, (0, 0), mask)
    return out


def _initials_avatar(name: str, size: int, color) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((0, 0, size, size), fill=color)
    font = _font(FONT_BOLD, int(size * 0.4))
    text = _initials(name)
    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1]), text, font=font, fill=WHITE)
    return img


async def render_leaderboard(bot, group_title: str, rows: list[dict], updated_label: str) -> bytes:
    """rows: list of dicts with user_id, username, first_name, points (already sorted desc)"""
    n = len(rows)
    height = HEADER_HEIGHT + max(n, 1) * ROW_HEIGHT + FOOTER_HEIGHT + PADDING
    canvas = _vertical_gradient((WIDTH, height), BG_TOP, BG_BOTTOM)
    draw = ImageDraw.Draw(canvas, "RGBA")

    # Card background
    _rounded_rect(draw, (PADDING // 2, PADDING // 2, WIDTH - PADDING // 2, height - PADDING // 2),
                  28, CARD_BG)

    # Header
    title_font = _font(FONT_BOLD, 46)
    sub_font = _font(FONT_REGULAR, 24)
    _draw_star(draw, PADDING + 42, 60, 24, 10, GOLD)
    draw.text((PADDING + 76, 34), "LIVE LEADERBOARD", font=title_font, fill=GOLD)
    draw.text((PADDING + 20, 96), (group_title or "Group")[:60], font=sub_font, fill=MUTED)

    y = HEADER_HEIGHT
    rank_font = _font(FONT_BOLD, 30)
    name_font = _font(FONT_BOLD, 28)
    pts_font = _font(FONT_BOLD, 30)

    medal_colors = {1: GOLD, 2: SILVER, 3: BRONZE}

    for i, m in enumerate(rows, start=1):
        row_bg = ROW_BG_ODD if i % 2 else ROW_BG_EVEN
        top = y
        bottom = y + ROW_HEIGHT - 10
        _rounded_rect(draw, (PADDING, top, WIDTH - PADDING, bottom), 18, row_bg)

        # rank badge
        badge_color = medal_colors.get(i, ACCENT if i <= 10 else (60, 55, 100))
        cx, cy, r = PADDING + 46, top + (bottom - top) // 2, 26
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=badge_color)
        rank_text = str(i)
        bbox = draw.textbbox((0, 0), rank_text, font=rank_font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        text_color = (30, 20, 10) if i <= 3 else WHITE
        draw.text((cx - tw / 2 - bbox[0], cy - th / 2 - bbox[1]), rank_text, font=rank_font, fill=text_color)

        # avatar
        display_name = m.get("first_name") or m.get("username") or f"User {m['user_id']}"
        avatar_img = None
        try:
            avatar_img = await _fetch_avatar(bot, m["user_id"])
        except Exception:
            avatar_img = None
        if avatar_img:
            av = _circle_avatar(avatar_img, AVATAR_SIZE)
        else:
            av = _initials_avatar(display_name, AVATAR_SIZE, badge_color if i <= 3 else (70, 62, 120))
        canvas.paste(av, (PADDING + 90, top + (ROW_HEIGHT - 10 - AVATAR_SIZE) // 2), av)

        # name
        name_x = PADDING + 90 + AVATAR_SIZE + 20
        name_display = display_name if not m.get("username") else f"{display_name} (@{m['username']})"
        if len(name_display) > 34:
            name_display = name_display[:31] + "..."
        draw.text((name_x, top + 14), name_display, font=name_font, fill=WHITE)
        draw.text((name_x, top + 44), f"Rank #{i}", font=_font(FONT_REGULAR, 18), fill=MUTED)

        # points (right aligned)
        pts_text = f"{m['points']} pts"
        bbox = draw.textbbox((0, 0), pts_text, font=pts_font)
        tw = bbox[2] - bbox[0]
        draw.text((WIDTH - PADDING - 30 - tw, top + (ROW_HEIGHT - 10) / 2 - 18), pts_text,
                   font=pts_font, fill=GOLD if i <= 3 else WHITE)

        y += ROW_HEIGHT

    if n == 0:
        draw.text((PADDING + 20, y + 10), "No members ranked yet.", font=name_font, fill=MUTED)
        y += ROW_HEIGHT

    footer_font = _font(FONT_REGULAR, 20)
    draw.text((PADDING + 20, y + 12), updated_label, font=footer_font, fill=MUTED)

    buf = io.BytesIO()
    canvas.convert("RGB").save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()
