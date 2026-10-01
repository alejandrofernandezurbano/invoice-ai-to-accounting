"""Step 1: get the statement lines out of a PDF or text export.

- Digital PDFs: the text layer is read with PyMuPDF (fast, exact).
- Scanned PDFs (images): OCR with Tesseract, only if pytesseract is installed.
- Bank exports (.txt/.csv): read directly.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .models import RawLine

# "2026-09-02  TRANSFER FROM ACME LOGISTICS SAS INV-1043   1,250.00" (amount may be signed or in a CR/DR column)
LINE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<desc>.+?)\s+(?P<amount>[-+]?\$?[\d,]+\.\d{2})\s*(?P<side>CR|DR)?\s*$"
)


def read_text(path: Path) -> str:
    if path.suffix.lower() != ".pdf":
        return path.read_text(encoding="utf-8")
    try:
        import pymupdf as fitz
    except ImportError:  # pragma: no cover - older PyMuPDF
        try:
            import fitz
        except ImportError as e:
            raise SystemExit("Reading PDFs needs PyMuPDF: pip install pymupdf") from e
    text = []
    with fitz.open(path) as doc:
        for page in doc:
            page_text = page.get_text()
            if page_text.strip():
                text.append(page_text)
            else:
                text.append(_ocr(page))
    return "\n".join(text)


def _ocr(page) -> str:  # pragma: no cover - needs Tesseract installed
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        raise SystemExit("This page is a scanned image. Install Tesseract + pytesseract to OCR it.")
    pix = page.get_pixmap(dpi=300)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    return pytesseract.image_to_string(img)


def parse_lines(text: str, source: str) -> list[RawLine]:
    rows = []
    for raw in text.splitlines():
        m = LINE.match(raw.strip())
        if not m:
            continue
        try:
            amount = Decimal(m["amount"].replace(",", "").replace("$", ""))
        except InvalidOperation:
            continue
        if m["side"] == "DR":
            amount = -abs(amount)
        elif m["side"] == "CR":
            amount = abs(amount)
        rows.append(RawLine(date.fromisoformat(m["date"]), " ".join(m["desc"].split()), amount, source))
    return rows


def extract(path: str | Path) -> list[RawLine]:
    p = Path(path)
    return parse_lines(read_text(p), p.name)
