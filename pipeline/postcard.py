"""Module 4 — Branded postcard PDF generator.

Front of a standard 6x4" postcard:
  * Configurable brand lockup (config.BRAND_NAME; generic branded template —
    NO human faces, NO fabricated imagery of any real person).
  * Business name.
  * Review-gap line: "You have {n} reviews. Top competitor: {benchmark}."
  * QR code pointing to the business's review-collection landing page.

Rendered with ReportLab (vector, no photographic assets).
"""
from __future__ import annotations

import io
import os
from typing import List, Optional

import qrcode
from reportlab.lib.colors import HexColor
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

import config

# Lob 4x6 postcard requires the artwork at full bleed: 6.25" x 4.25"
# (the 6x4 mail size plus 0.125" bleed on every edge). Keep meaningful
# content inside the ~0.1875" safe margin from the trim.
CARD_W = 6.25 * inch
CARD_H = 4.25 * inch

_INK = HexColor("#0f172a")
_ACCENT = HexColor("#38bdf8")
_MUTED = HexColor("#475569")
_PAPER = HexColor("#f8fafc")


def _qr_image(data: str) -> ImageReader:
    qr = qrcode.QRCode(box_size=10, border=1)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return ImageReader(buf)


def _wrap(text: str, max_chars: int) -> List[str]:
    words = text.split()
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= max_chars:
            cur = f"{cur} {w}".strip()
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def render_postcard(
    business: dict,
    out_path: str,
    benchmark: Optional[int] = None,
) -> str:
    """Render a single postcard PDF; return the file path."""
    reviews = int(business.get("user_ratings_total", 0) or 0)
    name = business.get("name", "Your Business")
    landing = business.get("landing_url") or config.LANDING_BASE_URL

    if benchmark is None:
        # Conservative generic benchmark if none supplied.
        benchmark = max(reviews * 5, 50)

    c = canvas.Canvas(out_path, pagesize=(CARD_W, CARD_H))

    # Background
    c.setFillColor(_PAPER)
    c.rect(0, 0, CARD_W, CARD_H, fill=1, stroke=0)

    # Left accent band + brand
    c.setFillColor(_INK)
    c.rect(0, 0, 0.35 * inch, CARD_H, fill=1, stroke=0)
    c.setFillColor(_ACCENT)
    c.rect(0.35 * inch, 0, 0.06 * inch, CARD_H, fill=1, stroke=0)

    # Brand lockup (top-left)
    c.setFillColor(_INK)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(0.65 * inch, CARD_H - 0.55 * inch, config.BRAND_NAME)
    c.setFillColor(_MUTED)
    c.setFont("Helvetica", 8)
    c.drawString(0.65 * inch, CARD_H - 0.75 * inch, config.BRAND_TAGLINE)

    # Business name (headline)
    c.setFillColor(_INK)
    c.setFont("Helvetica-Bold", 18)
    y = CARD_H - 1.35 * inch
    for line in _wrap(name, 26):
        c.drawString(0.65 * inch, y, line)
        y -= 0.28 * inch

    # Review-gap line
    c.setFillColor(_MUTED)
    c.setFont("Helvetica", 11)
    gap_line_1 = f"You have {reviews} reviews."
    gap_line_2 = f"Top competitor: {benchmark}."
    c.drawString(0.65 * inch, y - 0.05 * inch, gap_line_1)
    c.drawString(0.65 * inch, y - 0.28 * inch, gap_line_2)

    # Call to action
    c.setFillColor(_INK)
    c.setFont("Helvetica-Bold", 10.5)
    c.drawString(
        0.65 * inch, y - 0.62 * inch, "Scan to start collecting more 5-star reviews"
    )

    # QR code (bottom-right), pointing to the landing page
    qr = _qr_image(landing)
    qr_size = 1.5 * inch
    c.drawImage(
        qr,
        CARD_W - qr_size - 0.35 * inch,
        0.35 * inch,
        width=qr_size,
        height=qr_size,
        preserveAspectRatio=True,
        mask="auto",
    )
    c.setFillColor(_MUTED)
    c.setFont("Helvetica", 6.5)
    c.drawRightString(
        CARD_W - 0.35 * inch, 0.2 * inch, f"Powered by {config.BRAND_NAME}"
    )

    c.showPage()
    c.save()
    return out_path


def generate(businesses: List[dict], benchmark: Optional[int] = None) -> List[dict]:
    """Render one postcard PDF per business; annotate with postcard_pdf_path."""
    os.makedirs(config.POSTCARD_DIR, exist_ok=True)
    count = 0
    for b in businesses:
        pid = b.get("place_id", f"row{count}")
        out_path = os.path.join(config.POSTCARD_DIR, f"{pid}.pdf")
        render_postcard(b, out_path, benchmark=benchmark)
        b["postcard_pdf_path"] = out_path
        count += 1

    print(f"✅ postcard — {count} records")
    return businesses


if __name__ == "__main__":
    import json
    import sys

    data = json.load(sys.stdin)
    print(json.dumps(generate(data), indent=2))
