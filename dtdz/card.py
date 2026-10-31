"""Image card for each post: 1280x720 PNG in the Deeptech DZ identity."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .text import EMOJI

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
W, H = 1280, 720
PAD = 88
INK, GRID, LINE = "#0B0F14", "#131A23", "#1E2833"
TEXT, MUTED, BRAND = "#F2F5F8", "#8A97A6", "#22D3EE"
ACCENT = {"news": BRAND, "free": "#4ADE80", "market": "#FBBF24", "tool": "#A78BFA", "odd": "#F472B6",
          "app": "#FB923C", "site": "#38BDF8", "breaking": "#F87171", "sport": "#34D399", "film": "#E879F9",
          "discovery": "#60A5FA", "list": "#22D3EE", "study": "#FACC15", "visa": "#2DD4BF", "trend": "#FB7185"}
LABEL = {"news": "أخبار", "free": "فرصة مجانية", "market": "السوق", "tool": "أداة", "odd": "غريب لكنه حقيقي",
         "app": "تطبيق اليوم", "site": "موقع اليوم", "breaking": "عاجل", "sport": "رياضة",
         "film": "ماذا نشاهد؟", "discovery": "اكتشاف", "list": "مختارات", "study": "منح ودراسة", "visa": "هجرة وتأشيرات",
         "trend": "ترند"}
MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "ماي", "جوان", "جويلية", "أوت", "سبتمبر", "أكتوبر",
          "نوفمبر", "ديسمبر"]  # Algerian month names


def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / f"IBMPlexSansArabic-{weight}.ttf"), size,
                              layout_engine=ImageFont.Layout.RAQM)


def _len(font, s: str) -> float:
    return font.getlength(s, direction="rtl", language="ar")


def _rtl(draw: ImageDraw.ImageDraw, right: float, y: float, s: str, font, fill) -> float:
    """Draw right-aligned RTL text; returns its width."""
    w = _len(font, s)
    draw.text((right - w, y), s, font=font, fill=fill, direction="rtl", language="ar")
    return w


def _wrap(s: str, font, width: float) -> list[str]:
    lines, cur = [], ""
    for word in s.split():
        trial = f"{cur} {word}".strip()
        if _len(font, trial) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    return lines + ([cur] if cur else [])


SYMBOLS = re.compile("[₿Ξ️]")
FIGURE = re.compile(r"[+\-−]?[$€£]\d[\d,.]*%?|[+\-−]?\d[\d,.]*\s?%")  # only figures with a symbol


def _isolate(s: str) -> str:
    """Keep figures like 40% or $67,012 left-to-right inside Arabic lines."""
    return FIGURE.sub(lambda m: "⁦" + m.group().strip() + "⁩", s)


def headline(text: str) -> str:
    first = text.strip().split("\n")[0]
    first = SYMBOLS.sub("", EMOJI.sub("", first))
    return re.sub(r"\s+", " ", first).strip(" .،")


def _date(slot: str) -> str:
    d = datetime.fromisoformat(slot)
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


VIS_W = 500                      # left visual panel width
TEXT_L = VIS_W + 40               # text column left edge


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _lum(rgb) -> float:
    r, g, b = (v / 255 for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _glow(img: Image.Image, center, radius: int, rgb, strength: float) -> Image.Image:
    from PIL import ImageFilter
    layer = Image.new("RGB", img.size, (0, 0, 0))
    ImageDraw.Draw(layer).ellipse((center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius),
                                  fill=tuple(int(v * strength) for v in rgb))
    layer = layer.filter(ImageFilter.GaussianBlur(radius // 2))
    from PIL import ImageChops
    return ImageChops.add(img, layer)


def _fit(im: Image.Image, box: int) -> Image.Image:
    bb = im.getbbox()
    if bb:
        im = im.crop(bb)
    scale = box / max(im.size)
    return im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.LANCZOS)


def _tile(spec: dict, size: int) -> Image.Image:
    """Logo tile. Prefers the brand's real full-colour logo on white; then its official glyph in brand
    colour; a wordmark only if both are unavailable (offline and unknown brand)."""
    from .brands import brand_color, brand_icon, real_logo
    slug = spec.get("slug")
    tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    td = ImageDraw.Draw(tile)
    real = real_logo(spec["key"], spec.get("domain"), spec.get("wiki"))
    glyph = brand_icon(slug) if slug else None
    rgb = _hex(brand_color(slug)) if slug else (34, 211, 238)

    def white_tile():
        td.rounded_rectangle((0, 0, size - 1, size - 1), radius=size // 5, fill=(255, 255, 255, 255))

    if real is not None and (min(real.size) >= 128 or glyph is None):
        white_tile()
        lg = _fit(real, int(size * (0.66 if min(real.size) >= 128 else 0.5)))
        tile.alpha_composite(lg, ((size - lg.width) // 2, (size - lg.height) // 2))
        return tile
    if glyph is not None:
        light = _lum(rgb) > 0.85
        bg = (17, 24, 32, 255) if light else (255, 255, 255, 255)
        td.rounded_rectangle((0, 0, size - 1, size - 1), radius=size // 5, fill=bg)
        g = _fit(Image.open(glyph).convert("RGBA"), int(size * 0.58))
        colored = Image.new("RGBA", g.size, rgb + (255,))
        colored.putalpha(g.getchannel("A"))
        tile.alpha_composite(colored, ((size - g.width) // 2, (size - g.height) // 2))
        return tile
    td.rounded_rectangle((0, 0, size - 1, size - 1), radius=size // 5, fill=rgb + (255,))
    label = spec.get("label") or slug or "?"
    fg = (11, 15, 20) if _lum(rgb) > 0.55 else (255, 255, 255)
    for fs in range(size // 3, 18, -4):
        f = ImageFont.truetype(str(FONTS / "IBMPlexSansArabic-Bold.ttf"), fs)
        bb = td.textbbox((0, 0), label, font=f)
        if bb[2] - bb[0] <= size * 0.8:
            break
    td.text(((size - (bb[2] - bb[0])) / 2 - bb[0], (size - (bb[3] - bb[1])) / 2 - bb[1]), label, font=f, fill=fg)
    return tile


def _topic_badge(topic: str, accent_rgb, size: int) -> Image.Image:
    from .brands import topic_icon
    badge = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bd = ImageDraw.Draw(badge)
    bd.ellipse((0, 0, size - 1, size - 1), fill=(18, 26, 36, 255), outline=accent_rgb + (255,), width=6)
    icon = topic_icon(topic)
    if icon:
        g = Image.open(icon).convert("RGBA").resize((int(size * 0.5),) * 2, Image.LANCZOS)
        colored = Image.new("RGBA", g.size, accent_rgb + (255,))
        colored.putalpha(g.getchannel("A"))
        badge.alpha_composite(colored, ((size - g.width) // 2, (size - g.height) // 2))
    return badge


def _visual(img: Image.Image, post: dict, accent: str) -> Image.Image:
    """Left panel: brand logos when the story is about a brand, otherwise a topic icon."""
    from .brands import brand_color, detect_topic, logo_specs
    text = (post.get("headline") or "") + "\n" + post["text"]
    specs = logo_specs(post, text)
    topic = post.get("topic") or detect_topic(text, post["type"])
    cx, cy = VIS_W // 2 + 20, H // 2
    accent_rgb = _hex(accent)
    brands = specs
    photo = None
    if post.get("photo"):
        from .brands import photo_for
        photo = photo_for(post["photo"])
    if photo is not None:
        ph = post["photo"]
        credit = ph.get("credit") or ("صورة: ويكيميديا كومنز" if ph.get("commons") else
                                      "صورة: ويكيبيديا" if ph.get("wiki") else "صورة: المصدر الرسمي")
        return _photo_panel(img, photo, specs, credit)
    if specs:
        glow_rgb = _hex(brand_color(specs[0]["slug"])) if specs[0].get("slug") else accent_rgb
        if _lum(glow_rgb) < 0.08 or _lum(glow_rgb) > 0.9:
            glow_rgb = accent_rgb
        img = _glow(img, (cx, cy), 260, glow_rgb, 0.45)
        base = img.convert("RGBA")
        if len(specs) == 1:
            t = _tile(specs[0], 270)
            base.alpha_composite(t, (cx - 135, cy - 135))
        else:
            a, b = _tile(specs[0], 190), _tile(specs[1], 190)
            base.alpha_composite(a, (cx - 200, cy - 165))
            base.alpha_composite(b, (cx + 10, cy - 25))
            d = ImageDraw.Draw(base)
            d.ellipse((cx - 22, cy - 42, cx + 22, cy + 2), fill=(11, 15, 20, 255), outline=(242, 245, 248, 255), width=3)
            d.text((cx, cy - 20), "×", font=_font("Bold", 34), fill=TEXT, anchor="mm")
        # small topic badge pinned to the corner of the logo group: tells *what* happened
        if topic and post["type"] == "news":
            badge = _topic_badge(topic, accent_rgb, 120)
            base.alpha_composite(badge, (cx + 70, cy + 70) if len(brands) == 1 else (cx - 230, cy + 70))
        return base.convert("RGB")
    img = _glow(img, (cx, cy), 240, accent_rgb, 0.35)
    base = img.convert("RGBA")
    base.alpha_composite(_topic_badge(topic, accent_rgb, 300), (cx - 150, cy - 150))
    return base.convert("RGB")


def _photo_panel(img: Image.Image, photo: Image.Image, specs: list[dict], credit: str = "صورة: ويكيبيديا") -> Image.Image:
    """Left panel filled with the product photo, fading into the card; logos pinned bottom-left."""
    pw = VIS_W + 60
    scale = max(pw / photo.width, H / photo.height)
    ph = photo.resize((int(photo.width * scale) + 1, int(photo.height * scale) + 1), Image.LANCZOS)
    left, top = (ph.width - pw) // 2, (ph.height - H) // 2
    ph = ph.crop((left, top, left + pw, top + H))
    # fade: opaque on the left, transparent toward the text column; slight darkening for contrast
    mask = Image.new("L", (pw, H))
    md = ImageDraw.Draw(mask)
    for x in range(pw):
        a = 235 if x < pw * 0.55 else int(235 * (1 - (x - pw * 0.55) / (pw * 0.45)))
        md.line((x, 0, x, H), fill=max(0, a))
    dark = Image.new("RGB", ph.size, (11, 15, 20))
    ph = Image.blend(ph, dark, 0.18)
    base = img.convert("RGBA")
    base.paste(ph, (0, 0), mask)
    x = 40
    for spec in specs[:2]:
        t = _tile(spec, 120)
        base.alpha_composite(t, (x, H - 120 - 44))
        x += 136
    d = ImageDraw.Draw(base)

    return base.convert("RGB")


def _hero(post: dict, photo: Image.Image, accent: str, specs: list[dict], credit: str) -> Image.Image:
    """The news photo fills the whole card; headline over a dark gradient; logo top-left."""
    scale = max(W / photo.width, H / photo.height)
    ph = photo.convert("RGB").resize((int(photo.width * scale) + 1, int(photo.height * scale) + 1), Image.LANCZOS)
    l, t = (ph.width - W) // 2, max(0, (ph.height - H) // 3)
    img = ph.crop((l, t, l + W, t + H))
    shade = Image.new("L", (W, H))
    sd = ImageDraw.Draw(shade)
    for y in range(H):                      # transparent top -> dark bottom
        sd.line((0, y, W, y), fill=int(min(250, max(0, (y - H * 0.15)) / (H * 0.6) * 250)))
    img = Image.composite(Image.new("RGB", (W, H), INK), img, shade)
    base = img.convert("RGBA")
    d = ImageDraw.Draw(base)
    d.rectangle((W - 10, 0, W, H), fill=accent)
    right = W - PAD
    chip_f = _font("SemiBold", 28)
    label = LABEL["breaking"] if post.get("breaking") else LABEL.get(post["type"], "")
    lw = _len(chip_f, label)


    x = PAD - 40
    for spec in specs[:2]:
        t_ = _tile(spec, 96)
        base.alpha_composite(t_, (x, PAD - 48))
        x += 108
    title = _isolate((post.get("headline") or headline(post["text"])).replace("**", ""))
    for size in (60, 54, 48, 44, 40):
        f = _font("Bold", size)
        lines = _wrap(title, f, W - 2 * PAD)
        if len(lines) <= 3:
            break
    lh = int(size * 1.45)
    y = H - PAD - 40 - lh * len(lines)
    for ln in lines:
        _rtl(d, right, y, ln, f, TEXT)
        y += lh
    brand_f = _font("Bold", 26)
    bw = _len(brand_f, "Deeptech DZ")
    d.text((right - bw, H - PAD + 6), "Deeptech DZ", font=brand_f, fill=TEXT)
    cx, cy = right - bw - 22, H - PAD + 22
    d.polygon([(cx, cy - 9), (cx + 9, cy), (cx, cy + 9), (cx - 9, cy)], fill=BRAND)

    return base.convert("RGB")


MIN_PHOTO_W, MIN_PHOTO_H = 1200, 675      # only sharp, high-resolution photos go full-card


def edit_photo(photo: Image.Image, spec: dict) -> Image.Image:
    """Optional edits that make the photo tell the story:
    crop  [x0, y0, x1, y1] as fractions — zoom on the subject
    blur  [x0, y0, x1, y1] as fractions — e.g. show a map area being blurred
    focus [x, y] — keep this point visible when the card crops the photo"""
    from PIL import ImageFilter
    im = photo.convert("RGB")
    if spec.get("crop"):
        x0, y0, x1, y1 = spec["crop"]
        im = im.crop((int(x0 * im.width), int(y0 * im.height), int(x1 * im.width), int(y1 * im.height)))
    if spec.get("blur"):
        x0, y0, x1, y1 = spec["blur"]
        box = (int(x0 * im.width), int(y0 * im.height), int(x1 * im.width), int(y1 * im.height))
        region = im.crop(box).filter(ImageFilter.GaussianBlur(max(12, (box[2] - box[0]) // 18)))
        im.paste(region, box)
    return im


def render(post: dict, out: str | Path) -> Path:
    if post.get("photo") and post.get("layout", "hero") == "hero":
        from .brands import logo_specs, photo_for
        photo = photo_for(post["photo"])
        if photo is not None and (photo.width < MIN_PHOTO_W or photo.height < MIN_PHOTO_H):
            import logging
            logging.getLogger("dtdz.card").warning("photo too small (%sx%s) for %s — logo layout used",
                                                  photo.width, photo.height, post.get("id"))
            photo = None
        if photo is not None:
            ph = post["photo"]
            photo = edit_photo(photo, ph)
            credit = ph.get("credit") or ("صورة: ويكيميديا كومنز" if ph.get("commons") else
                                          "صورة: ويكيبيديا" if ph.get("wiki") else "صورة: المصدر الرسمي")
            accent = ACCENT.get("breaking" if post.get("breaking") else post["type"], BRAND)
            img = _hero(post, photo, accent, logo_specs(post, (post.get("headline") or "") + "\n" + post["text"]), credit)
            out = Path(out)
            out.parent.mkdir(parents=True, exist_ok=True)
            img.save(out, "PNG", optimize=True)
            return out
    ptype = post["type"]
    accent = ACCENT.get("breaking" if post.get("breaking") else ptype, BRAND)
    img = Image.new("RGB", (W, H), INK)
    d = ImageDraw.Draw(img)
    for x in range(PAD // 2, W, 32):
        for y in range(PAD // 2, H, 32):
            d.point((x, y), fill=GRID)
    img = _visual(img, post, accent)
    d = ImageDraw.Draw(img)
    d.rectangle((W - 10, 0, W, H), fill=accent)

    right = W - PAD
    chip_f = _font("SemiBold", 28)
    label = LABEL["breaking"] if post.get("breaking") else LABEL.get(ptype, "")
    lw = _len(chip_f, label)


    date_f = _font("Regular", 26)
    _rtl(d, right, PAD + 2, _date(post["slot"]), date_f, MUTED)

    title = _isolate((post.get("headline") or headline(post["text"])).replace("**", ""))
    data = _market_rows(post["text"]) if ptype == "market" else []
    width = right - TEXT_L
    plans = [(2, (52, 48, 44, 40))] if data else [(3, (64, 58, 54, 50)), (4, (50, 46, 42, 38))]
    chosen = None
    for max_lines, sizes in plans:
        for size in sizes:
            f = _font("Bold", size)
            lines = _wrap(title, f, width)
            if len(lines) <= max_lines:
                chosen = (f, size, lines)
                break
        if chosen:
            break
    if not chosen:
        lines = lines[:max_lines]
        lines[-1] += "…"
        chosen = (f, size, lines)
    f, size, lines = chosen
    lh = int(size * 1.5)
    block = lh * len(lines)
    y = (PAD + 70 + (H - PAD - 40)) // 2 - block // 2 if not data else PAD + 100
    for ln in lines:
        _rtl(d, right, y, ln, f, TEXT)
        y += lh

    if data:
        y += 20
        row_f, val_f = _font("SemiBold", 30), _font("Bold", 30)
        for label_, value in data[:5]:
            colour = "#4ADE80" if "+" in value else "#F87171" if re.search(r"[-−]\d", value) else TEXT
            _rtl(d, right, y, label_, row_f, MUTED)
            d.text((TEXT_L, y), value, font=val_f, fill=colour, direction="ltr")
            d.line((TEXT_L, y + 46, right, y + 46), fill=LINE, width=1)
            y += 52

    d.line((TEXT_L, H - PAD - 24, right, H - PAD - 24), fill=LINE, width=2)
    brand_f = _font("Bold", 30)
    bw = _len(brand_f, "Deeptech DZ")
    d.text((right - bw, H - PAD - 4), "Deeptech DZ", font=brand_f, fill=TEXT)
    cx, cy = right - bw - 26, H - PAD + 16
    d.polygon([(cx, cy - 11), (cx + 11, cy), (cx, cy + 11), (cx - 11, cy)], fill=BRAND)

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG", optimize=True)
    return out


def _market_rows(text: str) -> list[tuple[str, str]]:
    rows = []
    for ln in text.split("\n")[1:]:
        ln = SYMBOLS.sub("", EMOJI.sub("", ln)).strip()
        if "%" in ln and ":" in ln and re.search(r"\d", ln):
            label, value = ln.split(":", 1)
            value = re.sub(r"([\d.,]+)\s*دولار", r"$\1", value)
            value = re.sub(r"،?\s*بتراجع\s*([\d.]+)%", r" (-\1%)", value)
            value = re.sub(r"،?\s*بارتفاع\s*([\d.]+)%", r" (+\1%)", value).strip()   # LTR: "$76,881 (-2.5%)"
            rows.append((label.strip(), value))
    return rows
