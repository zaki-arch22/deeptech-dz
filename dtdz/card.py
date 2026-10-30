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
ACCENT = {"news": BRAND, "free": "#4ADE80", "market": "#FBBF24", "tool": "#A78BFA", "odd": "#F472B6"}
LABEL = {"news": "أخبار", "free": "فرصة مجانية", "market": "السوق", "tool": "أداة", "odd": "غريب لكنه حقيقي"}
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


def render(post: dict, out: str | Path) -> Path:
    ptype = post["type"]
    accent = ACCENT.get(ptype, BRAND)
    img = Image.new("RGB", (W, H), INK)
    d = ImageDraw.Draw(img)

    # background: quiet dot grid + accent glow strip on the right edge
    for x in range(PAD // 2, W, 32):
        for y in range(PAD // 2, H, 32):
            d.point((x, y), fill=GRID)
    d.rectangle((W - 10, 0, W, H), fill=accent)

    right = W - PAD
    # top row: category chip (right), date (left)
    chip_f = _font("SemiBold", 28)
    label = LABEL.get(ptype, "")
    lw = _len(chip_f, label)
    d.rounded_rectangle((right - lw - 40, PAD - 6, right, PAD + 50), radius=28, outline=accent, width=2)
    _rtl(d, right - 20, PAD - 2, label, chip_f, accent)
    date_f = _font("Regular", 26)
    d.text((PAD, PAD + 2), _date(post["slot"]), font=date_f, fill=MUTED, direction="rtl", language="ar")

    # headline (auto-fit) — market cards keep it shorter to leave room for figures
    title = _isolate(post.get("headline") or headline(post["text"]))
    data = _market_rows(post["text"]) if ptype == "market" else []
    width = W - 2 * PAD - 20
    # prefer 3 comfortable lines, accept 4 at smaller sizes; market cards keep 2
    plans = [(2, (60, 54, 48, 44))] if data else [(3, (68, 62, 56, 52)), (4, (52, 48, 44, 40))]
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
    lh = int(size * 1.45)
    y = PAD + 110
    for ln in lines:
        _rtl(d, right, y, ln, f, TEXT)
        y += lh

    # market figures: label right (Arabic), value left (LTR) — a small table
    if data:
        y += 28
        row_f, val_f = _font("SemiBold", 34), _font("Bold", 34)
        for label, value in data[:5]:
            colour = "#4ADE80" if "+" in value else "#F87171" if re.search(r"[-−]\d", value) else TEXT
            _rtl(d, right, y, label, row_f, MUTED)
            d.text((PAD, y), value, font=val_f, fill=colour, direction="ltr")
            d.line((PAD, y + 50, right, y + 50), fill=GRID, width=1)
            y += 58

    # footer: brand mark
    d.line((PAD, H - PAD - 24, right, H - PAD - 24), fill=LINE, width=2)
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
            rows.append((label.strip(), value.strip()))
    return rows
