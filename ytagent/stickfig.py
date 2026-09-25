"""Draws stick-figure scenes with Pillow.

A scene is the JSON Claude produces in content.PLAN_SCHEMA:
    {"caption": str, "figures": [...], "props": [...]}
Figures have a pose, expression, facing direction, optional label and speech
bubble; props are simple doodled objects. Everything is drawn from primitives
so the style stays consistent across every video.
"""

from __future__ import annotations

import math
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BG = (251, 250, 246)
INK = (20, 20, 20)
GROUND = 0.80  # ground line, as a fraction of height

# (upper, lower) limb angles in degrees: 0 = straight down, +90 = forward.
POSES = {
    "standing": {"arm_f": (20, 10), "arm_b": (-20, -10), "leg_f": (12, 0), "leg_b": (-12, 0)},
    "waving": {"arm_f": (110, 150), "arm_b": (-20, -10), "leg_f": (12, 0), "leg_b": (-12, 0)},
    "pointing": {"arm_f": (90, 90), "arm_b": (-20, -10), "leg_f": (12, 0), "leg_b": (-12, 0)},
    "arms_up": {"arm_f": (120, 150), "arm_b": (-120, -150), "leg_f": (15, 0), "leg_b": (-15, 0)},
    "thinking": {"arm_f": (30, 165), "arm_b": (-20, -10), "leg_f": (10, 0), "leg_b": (-10, 0)},
    "walking": {"arm_f": (30, 45), "arm_b": (-30, -20), "leg_f": (25, 10), "leg_b": (-25, -35)},
    "running": {"arm_f": (60, 130), "arm_b": (-50, -20), "leg_f": (55, -10), "leg_b": (-40, -90)},
    "sitting": {"arm_f": (35, 70), "arm_b": (25, 60), "leg_f": (90, 0), "leg_b": (80, 0)},
    "slumped": {"arm_f": (5, 0), "arm_b": (-5, 0), "leg_f": (8, 0), "leg_b": (-8, 0)},
}

_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


def font(size: int) -> ImageFont.FreeTypeFont:
    for p in _FONT_PATHS:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size=size)


def hex_to_rgb(value: str, default=(31, 111, 235)) -> tuple[int, int, int]:
    v = (value or "").lstrip("#")
    if len(v) != 6:
        return default
    try:
        return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return default


def _limb(start, angles, lengths, direction):
    """Two-segment limb; returns [start, joint, end]."""
    pts = [start]
    x, y = start
    for ang, length in zip(angles, lengths):
        rad = math.radians(ang)
        x += math.sin(rad) * length * direction
        y += math.cos(rad) * length
        pts.append((x, y))
    return pts


def draw_text_center(d: ImageDraw.ImageDraw, xy, text, size, fill=INK, stroke=0, stroke_fill=BG, max_chars=28):
    f = font(size)
    lines = textwrap.wrap(text, max_chars) or [""]
    line_h = int(size * 1.15)
    x, y = xy
    y -= line_h * len(lines) / 2
    for line in lines:
        w = d.textlength(line, font=f)
        d.text((x - w / 2, y), line, font=f, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
        y += line_h


def draw_bubble(d: ImageDraw.ImageDraw, anchor, text, H, W):
    size = max(18, H // 30)
    f = font(size)
    lines = textwrap.wrap(text, 18)[:4]
    pad = size // 2
    tw = max(d.textlength(line, font=f) for line in lines)
    th = len(lines) * size * 1.15
    ax, ay = anchor
    x0 = min(max(ax - tw / 2 - pad, 10), W - tw - 2 * pad - 10)
    y1 = ay - size
    y0 = max(y1 - th - 2 * pad, 10)
    y1 = y0 + th + 2 * pad
    lw = max(3, H // 300)
    d.rounded_rectangle((x0, y0, x0 + tw + 2 * pad, y1), radius=pad, fill="white", outline=INK, width=lw)
    tail_x = min(max(ax, x0 + pad * 2), x0 + tw)
    d.polygon([(tail_x - pad, y1 - lw), (tail_x + pad, y1 - lw), (ax, ay - size * 0.2)], fill="white")
    d.line([(tail_x - pad, y1), (ax, ay - size * 0.2), (tail_x + pad, y1)], fill=INK, width=lw)
    ty = y0 + pad
    for line in lines:
        d.text((x0 + pad + (tw - d.textlength(line, font=f)) / 2, ty), line, font=f, fill=INK)
        ty += size * 1.15


def draw_face(d, cx, cy, r, expression, direction, lw):
    ex = cx + direction * r * 0.25
    eye_dx, eye_y, er = r * 0.3, cy - r * 0.15, max(2, r * 0.09)
    for sx in (-1, 1):
        d.ellipse((ex + sx * eye_dx - er, eye_y - er, ex + sx * eye_dx + er, eye_y + er), fill=INK)
    mw, my = r * 0.45, cy + r * 0.38
    box = (ex - mw, my - r * 0.3, ex + mw, my + r * 0.3)
    if expression == "happy":
        d.arc(box, 20, 160, fill=INK, width=lw)
    elif expression in ("sad", "worried"):
        d.arc((box[0], my, box[2], my + r * 0.5), 200, 340, fill=INK, width=lw)
    elif expression == "surprised":
        d.ellipse((ex - r * 0.14, my - r * 0.1, ex + r * 0.14, my + r * 0.2), outline=INK, width=lw)
    else:
        d.line((ex - mw * 0.7, my, ex + mw * 0.7, my), fill=INK, width=lw)
    if expression == "angry":
        for sx in (-1, 1):
            d.line((ex + sx * eye_dx * 1.6, eye_y - r * 0.35, ex + sx * eye_dx * 0.3, eye_y - r * 0.18), fill=INK, width=lw)
    elif expression == "worried":
        for sx in (-1, 1):
            d.line((ex + sx * eye_dx * 1.6, eye_y - r * 0.2, ex + sx * eye_dx * 0.3, eye_y - r * 0.38), fill=INK, width=lw)


def draw_figure(d: ImageDraw.ImageDraw, fig: dict, W: int, H: int, height_frac=0.42):
    ground = H * GROUND
    fig_h = H * height_frac
    u = fig_h / 7
    x = W * (0.08 + 0.84 * min(max(fig.get("x", 50), 0), 100) / 100)
    direction = 1 if fig.get("facing", "right") == "right" else -1
    pose = POSES.get(fig.get("pose", "standing"), POSES["standing"])
    lw = max(4, int(H / 140))
    accent = hex_to_rgb(fig.get("color", ""))

    leg = (1.4 * u, 1.4 * u)
    sitting = fig.get("pose") == "sitting"
    hip_y = ground - (1.4 * u if sitting else 2.8 * u)
    if fig.get("pose") == "slumped":
        hip_y += 0.2 * u
    neck_y = hip_y - 2.6 * u
    r = 1.1 * u  # big round heads, explainer-channel style
    head_c = (x + (direction * 0.25 * u if fig.get("pose") == "slumped" else 0), neck_y - r)
    shoulder = (x, neck_y + 0.4 * u)
    hip = (x, hip_y)
    arm = (1.1 * u, 1.1 * u)

    if sitting:  # a simple stool
        d.rectangle((x - 1.2 * u, hip_y, x + 0.4 * u, hip_y + 0.25 * u), fill=INK)
        d.line((x - u, hip_y, x - u, ground), fill=INK, width=lw)
        d.line((x + 0.2 * u, hip_y, x + 0.2 * u, ground), fill=INK, width=lw)

    for name in ("leg_b", "leg_f"):
        d.line(_limb(hip, pose[name], leg, direction), fill=INK, width=lw, joint="curve")
    d.line((shoulder[0], neck_y, hip[0], hip[1]), fill=accent, width=int(lw * 1.6))
    for name in ("arm_b", "arm_f"):
        d.line(_limb(shoulder, pose[name], arm, direction), fill=INK, width=lw, joint="curve")

    cx, cy = head_c
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill="white", outline=INK, width=lw)
    draw_face(d, cx, cy, r, fig.get("expression", "neutral"), direction, max(2, lw - 1))

    if fig.get("label"):
        draw_text_center(d, (x, ground + H * 0.06), fig["label"], max(16, H // 32), fill=accent,
                         stroke=max(2, H // 360), stroke_fill="white")
    if fig.get("speech"):
        draw_bubble(d, (cx, cy - r * 1.3), fig["speech"], H, W)


def draw_prop(d: ImageDraw.ImageDraw, prop: dict, W: int, H: int):
    ground = H * GROUND
    s = H * 0.18
    x = W * (0.08 + 0.84 * min(max(prop.get("x", 50), 0), 100) / 100)
    lw = max(4, int(H / 160))
    k = prop.get("kind", "box")
    L, R, T, B = x - s / 2, x + s / 2, ground - s, ground
    gold, green, red = (242, 181, 36), (46, 160, 67), (218, 54, 51)

    if k == "house":
        d.rectangle((L, B - s * 0.6, R, B), outline=INK, width=lw, fill="white")
        d.polygon([(L - s * 0.1, B - s * 0.6), (x, T - s * 0.1), (R + s * 0.1, B - s * 0.6)], outline=INK, width=lw, fill=(230, 120, 90))
        d.rectangle((x - s * 0.1, B - s * 0.3, x + s * 0.1, B), outline=INK, width=lw)
    elif k == "tree":
        d.rectangle((x - s * 0.07, B - s * 0.5, x + s * 0.07, B), fill=(120, 80, 40))
        d.ellipse((L, T - s * 0.3, R, B - s * 0.35), fill=(80, 170, 90), outline=INK, width=lw)
    elif k == "money_bag":
        d.ellipse((L, T + s * 0.25, R, B), fill=(220, 190, 120), outline=INK, width=lw)
        d.polygon([(x - s * 0.15, T + s * 0.3), (x, T + s * 0.05), (x + s * 0.15, T + s * 0.3)], fill=(220, 190, 120), outline=INK)
        draw_text_center(d, (x, B - s * 0.35), "$", int(s * 0.4), fill=green)
    elif k == "coin":
        d.ellipse((x - s * 0.3, B - s * 0.6, x + s * 0.3, B), fill=gold, outline=INK, width=lw)
        draw_text_center(d, (x, B - s * 0.3), "$", int(s * 0.35))
    elif k in ("chart_up", "chart_down"):
        d.line([(L, T), (L, B), (R, B)], fill=INK, width=lw)
        pts = [(L + s * 0.1, B - s * 0.2), (L + s * 0.4, B - s * 0.45), (L + s * 0.6, B - s * 0.35), (R, T + s * 0.1)]
        if k == "chart_down":
            pts = [(px, T + B - py) for px, py in pts]
        d.line(pts, fill=green if k == "chart_up" else red, width=lw + 2)
    elif k == "clock":
        d.ellipse((L, T, R, B), fill="white", outline=INK, width=lw)
        d.line([(x, T + s / 2), (x, T + s * 0.15)], fill=INK, width=lw)
        d.line([(x, T + s / 2), (x + s * 0.3, T + s / 2)], fill=INK, width=lw)
    elif k == "laptop":
        d.rectangle((L + s * 0.1, T + s * 0.3, R - s * 0.1, B - s * 0.15), fill=(200, 225, 255), outline=INK, width=lw)
        d.polygon([(L, B), (R, B), (R - s * 0.1, B - s * 0.15), (L + s * 0.1, B - s * 0.15)], fill=(180, 180, 180), outline=INK)
    elif k == "phone":
        d.rounded_rectangle((x - s * 0.2, T + s * 0.2, x + s * 0.2, B), radius=s * 0.05, fill=(200, 225, 255), outline=INK, width=lw)
    elif k == "car":
        d.rounded_rectangle((L - s * 0.3, B - s * 0.5, R + s * 0.3, B - s * 0.15), radius=s * 0.08, fill=(90, 140, 230), outline=INK, width=lw)
        d.polygon([(L, B - s * 0.5), (L + s * 0.2, B - s * 0.8), (R - s * 0.1, B - s * 0.8), (R + s * 0.1, B - s * 0.5)], fill=(200, 225, 255), outline=INK)
        for wx in (L, R):
            d.ellipse((wx - s * 0.13, B - s * 0.28, wx + s * 0.13, B), fill=INK)
    elif k == "sign":
        d.line([(x, B), (x, T + s * 0.3)], fill=INK, width=lw)
        d.rectangle((L - s * 0.2, T - s * 0.1, R + s * 0.2, T + s * 0.35), fill="white", outline=INK, width=lw)
        if prop.get("label"):
            draw_text_center(d, (x, T + s * 0.12), prop["label"], int(s * 0.14), max_chars=14)
        return
    elif k == "box":
        d.rectangle((L, T + s * 0.3, R, B), fill=(215, 170, 110), outline=INK, width=lw)
        d.line([(L, T + s * 0.5), (R, T + s * 0.5)], fill=INK, width=lw)
    elif k == "lightbulb":
        d.ellipse((x - s * 0.3, T, x + s * 0.3, T + s * 0.6), fill=(255, 230, 90), outline=INK, width=lw)
        d.rectangle((x - s * 0.12, T + s * 0.6, x + s * 0.12, T + s * 0.8), fill=(150, 150, 150), outline=INK)
    elif k == "question_mark":
        draw_text_center(d, (x, T + s * 0.4), "?", int(s * 1.0), fill=(130, 80, 200))
    elif k == "arrow_right":
        d.polygon([(L, B - s * 0.6), (x, B - s * 0.6), (x, B - s * 0.8), (R, B - s * 0.5), (x, B - s * 0.2), (x, B - s * 0.4), (L, B - s * 0.4)], fill=(240, 130, 40), outline=INK)
    elif k == "heart":
        d.ellipse((L, T + s * 0.2, x + s * 0.03, T + s * 0.6), fill=red)
        d.ellipse((x - s * 0.03, T + s * 0.2, R, T + s * 0.6), fill=red)
        d.polygon([(L + s * 0.03, T + s * 0.48), (R - s * 0.03, T + s * 0.48), (x, B)], fill=red)
    elif k == "skull":
        d.ellipse((L + s * 0.1, T + s * 0.1, R - s * 0.1, B - s * 0.2), fill="white", outline=INK, width=lw)
        for sx in (-1, 1):
            d.ellipse((x + sx * s * 0.17 - s * 0.1, T + s * 0.35, x + sx * s * 0.17 + s * 0.1, T + s * 0.55), fill=INK)
    elif k == "book":
        d.rectangle((L, T + s * 0.35, R, B), fill=(180, 60, 60), outline=INK, width=lw)
        d.line([(L + s * 0.12, T + s * 0.35), (L + s * 0.12, B)], fill=INK, width=lw)
    elif k == "desk":
        d.rectangle((L - s * 0.3, B - s * 0.5, R + s * 0.3, B - s * 0.42), fill=(150, 100, 60), outline=INK)
        for lx in (L - s * 0.2, R + s * 0.2):
            d.line([(lx, B - s * 0.42), (lx, B)], fill=INK, width=lw)
    elif k == "door":
        d.rectangle((x - s * 0.25, T - s * 0.3, x + s * 0.25, B), fill=(170, 120, 70), outline=INK, width=lw)
        d.ellipse((x + s * 0.12, B - s * 0.6, x + s * 0.18, B - s * 0.54), fill=INK)
    elif k == "mountain":
        d.polygon([(L - s * 0.5, B), (x, T - s * 0.4), (R + s * 0.5, B)], fill=(150, 160, 175), outline=INK)
        d.polygon([(x - s * 0.2, T - s * 0.05), (x, T - s * 0.4), (x + s * 0.2, T - s * 0.05)], fill="white")
    elif k == "sun":
        cy = H * 0.2
        d.ellipse((x - s * 0.3, cy - s * 0.3, x + s * 0.3, cy + s * 0.3), fill=(255, 210, 60))
        return
    elif k == "cloud":
        cy = H * 0.22
        for dx, rr in ((-0.3, 0.22), (0, 0.3), (0.3, 0.22)):
            d.ellipse((x + dx * s - rr * s, cy - rr * s, x + dx * s + rr * s, cy + rr * s), fill=(225, 230, 238))
        return
    elif k == "crown":
        d.polygon([(L, B - s * 0.2), (L, T + s * 0.3), (L + s * 0.25, T + s * 0.55), (x, T + s * 0.2), (R - s * 0.25, T + s * 0.55), (R, T + s * 0.3), (R, B - s * 0.2)], fill=gold, outline=INK)

    if prop.get("label"):
        draw_text_center(d, (x, ground + H * 0.06), prop["label"], max(16, H // 34))


SETTING_COLORS = {
    # (sky/wall, ground)
    "outdoors": ((135, 200, 245), (120, 190, 90)),
    "indoors": ((240, 228, 205), (185, 140, 95)),
    "night": ((30, 40, 80), (50, 80, 60)),
}


def draw_setting(d: ImageDraw.ImageDraw, setting: str, W: int, H: int) -> None:
    ground = H * GROUND
    if setting not in SETTING_COLORS:
        d.line((0, ground, W, ground), fill=(200, 200, 195), width=max(2, H // 400))
        return
    top, bottom = SETTING_COLORS[setting]
    d.rectangle((0, 0, W, ground), fill=top)
    d.rectangle((0, ground, W, H), fill=bottom)
    d.line((0, ground, W, ground), fill=INK, width=max(3, H // 300))
    if setting == "night":
        d.ellipse((W * 0.85, H * 0.08, W * 0.85 + H * 0.1, H * 0.18), fill=(245, 240, 200))
    elif setting == "indoors":
        wx, wy, ww = W * 0.12, H * 0.2, H * 0.22  # a window
        d.rectangle((wx, wy, wx + ww, wy + ww), fill=(170, 215, 245), outline=INK, width=max(3, H // 300))
        d.line((wx + ww / 2, wy, wx + ww / 2, wy + ww), fill=INK, width=max(3, H // 300))


def render_scene(scene: dict, path: str | Path, size=(1920, 1080), caption: str | None = None,
                 figure_scale: float = 1.0) -> Path:
    W, H = size
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    draw_setting(d, scene.get("setting", "plain"), W, H)

    for prop in scene.get("props", []):
        draw_prop(d, prop, W, H)
    figures = scene.get("figures", [])
    fig_frac = (0.40 if W >= H else 0.28) * figure_scale
    for fig in figures:
        draw_figure(d, fig, W, H, fig_frac)

    caption = scene.get("caption", "") if caption is None else caption
    if caption:
        draw_text_center(d, (W / 2, H * 0.1), caption, max(28, H // 16), fill=(255, 214, 10),
                         stroke=max(3, H // 180), stroke_fill=INK, max_chars=30 if W >= H else 18)

    path = Path(path)
    img.save(path, quality=92)
    return path


def add_headline(path: str | Path, text: str, top: bool = True) -> Path:
    """Big yellow outlined headline (thumbnail style) over an existing image."""
    img = Image.open(path).convert("RGB")
    W, H = img.size
    d = ImageDraw.Draw(img)
    size_px = H // 8 if W >= H else W // 9
    f = font(size_px)
    lines = textwrap.wrap(text.upper(), 22 if W >= H else 12)[:2]
    y = H * 0.03 if top else H - len(lines) * size_px * 1.15 - H * 0.04
    for line in lines:
        w = d.textlength(line, font=f)
        d.text(((W - w) / 2, y), line, font=f, fill=(255, 230, 0), stroke_width=max(4, size_px // 10), stroke_fill=INK)
        y += size_px * 1.15
    img.save(path, quality=92)
    return Path(path)


def add_caption(path: str | Path, caption: str) -> Path:
    """Scene caption along the top, smaller than a thumbnail headline."""
    img = Image.open(path).convert("RGB")
    W, H = img.size
    d = ImageDraw.Draw(img)
    draw_text_center(d, (W / 2, H * 0.1), caption, max(28, H // 16), fill=(255, 214, 10),
                     stroke=max(3, H // 180), stroke_fill=INK, max_chars=30 if W >= H else 18)
    img.save(path, quality=92)
    return Path(path)


def render_thumbnail(scene: dict, text: str, path: str | Path, size=(1280, 720)) -> Path:
    figures = [{**f, "speech": "", "label": ""} for f in scene.get("figures", [])]
    render_scene({**scene, "figures": figures}, path, size, caption="", figure_scale=1.35)
    return add_headline(path, text)
