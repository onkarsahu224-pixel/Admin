"""
Renders the "🏆 Live Leaderboard" widget as a PNG image.

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
                data = await resp.read()
        img = Image.open(io.BytesIO(data)).convert("RGB")
        return img
    except Exception:
        return None


def _circle_avatar(img: Image.Image, size: int) -> Image.Image:
    img = ImageOps.fit(img, (size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.ellipse((0, 0, size, size), fill=255)
    out = Image.new("RGBA", (size, size))
    out.paste(img, (0, 0), mask)
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
