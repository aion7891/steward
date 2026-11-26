"""Create a small fake "home folder" so you can test Steward safely.

Nothing here touches your real Documents/Downloads. Everything is created inside
review-system/demo/sample_home/. Each file is planted on purpose so a feature of
Steward has something to find (duplicates, temp files, old files, secrets...).

Run from the project root:
    uv run python review-system/demo/create_sample_folder.py
"""

import os
import shutil
import time
from pathlib import Path

from docx import Document
from openpyxl import Workbook
from PIL import Image

DEMO_DIR = Path(__file__).resolve().parent
HOME = DEMO_DIR / "sample_home"


def make_pdf(path, lines):
    """Write a tiny but valid one-page text PDF without extra libraries."""
    text_ops = "BT /F1 12 Tf 72 720 Td 16 TL " + " ".join(
        "(" + line.replace("(", "[").replace(")", "]") + ") '" for line in lines
    ) + " ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(text_ops)} >>\nstream\n{text_ops}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = "%PDF-1.4\n", []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{body}\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    path.write_bytes(out.encode("latin-1"))


def set_age(path, days):
    """Pretend a file was last modified `days` ago."""
    old = time.time() - days * 86400
    os.utime(path, (old, old))


def main():
    """Rebuild sample_home/ from scratch."""
    if HOME.exists():
        shutil.rmtree(HOME)
    docs, downloads, desktop = HOME / "Documents", HOME / "Downloads", HOME / "Desktop"
    for folder in (docs / "Acme", docs / "Recipes", docs / "Work" / "Clients", downloads, desktop):
        folder.mkdir(parents=True, exist_ok=True)

    # 1. A PDF invoice -> tests PDF reading, RAG search, and OKF concepts
    make_pdf(docs / "Acme" / "invoice-q3.pdf", [
        "Acme Corporation - Invoice Q3 2026",
        "Consulting services for the Phoenix migration project.",
        "Total amount due: 4,800 USD. Payment terms: 30 days.",
        "Contact: billing@acme.example",
    ])
    # 2. A Word document -> tests DOCX reading
    doc = Document()
    doc.add_heading("Phoenix Project Kickoff Notes", level=1)
    doc.add_paragraph("The Phoenix project moves Acme's billing system to the cloud.")
    doc.add_paragraph("Deadline is March 2027. Budget approved: 50,000 USD.")
    doc.save(str(docs / "Acme" / "phoenix-kickoff.docx"))
    # 3. An Excel budget -> tests XLSX reading
    wb = Workbook()
    ws = wb.active
    ws.title = "Budget"
    ws.append(["Item", "Cost"])
    ws.append(["Cloud hosting", 1200])
    ws.append(["Consulting", 4800])
    wb.save(str(docs / "Acme" / "budget-2026.xlsx"))
    # 4. Markdown + text -> tests text reading and topics
    (docs / "Recipes" / "pasta.md").write_text(
        "# Tomato Pasta\n\nBoil pasta for 9 minutes. Add tomato sauce, garlic and basil.\n", encoding="utf-8")
    (docs / "Recipes" / "pasta-copy.md").write_text(
        "# Tomato Pasta\n\nBoil pasta for 9 minutes. Add tomato sauce, garlic and basil.\n", encoding="utf-8")
    # 5. An OLD file (200 days) -> tests "stale file" detection
    old_note = docs / "Recipes" / "old-shopping-list.txt"
    old_note.write_text("milk, eggs, bread\n", encoding="utf-8")
    set_age(old_note, 200)
    # 6. A protected client file -> must NEVER be moved, even if approved
    (docs / "Work" / "Clients" / "contract.txt").write_text("Confidential client contract.\n", encoding="utf-8")
    # 7. A secret file -> must never be read, embedded, or copied into OKF
    (docs / ".env").write_text("API_KEY=sk-demo-should-never-be-read-1234567890\n", encoding="utf-8")
    # 8. Downloads: an exact duplicate of the invoice, a temp file, an image, a "big" file
    shutil.copy2(docs / "Acme" / "invoice-q3.pdf", downloads / "invoice-q3 (1).pdf")
    (downloads / "report.tmp").write_text("half written temp data\n", encoding="utf-8")
    Image.new("RGB", (640, 480), (30, 120, 200)).save(str(downloads / "holiday-photo.png"))
    (downloads / "big-installer.dmg").write_bytes(os.urandom(3 * 1024 * 1024))
    # 9. Desktop: a code file
    (desktop / "hello.py").write_text("print('hello from the desktop')\n", encoding="utf-8")

    count = sum(1 for p in HOME.rglob("*") if p.is_file())
    print(f"Created {count} sample files under {HOME}")


if __name__ == "__main__":
    main()
