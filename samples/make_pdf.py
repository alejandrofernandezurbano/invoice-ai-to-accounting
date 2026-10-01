"""Turn the fictitious text statement into a PDF, to test the PDF path: python samples/make_pdf.py"""
from pathlib import Path

from fpdf import FPDF  # pip install fpdf2

here = Path(__file__).parent
pdf = FPDF()
pdf.add_page()
pdf.set_font("Courier", size=9)
for line in (here / "statement_2026-09.txt").read_text(encoding="utf-8").splitlines():
    pdf.cell(0, 5, line, new_x="LMARGIN", new_y="NEXT")
pdf.output(str(here / "statement_2026-09.pdf"))
print("samples/statement_2026-09.pdf written")
