"""Conversioni da e verso PDF."""
from __future__ import annotations

import html as _html
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pymupdf

from .common import TEXT_FLAGS

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp", ".jxr", ".pnm")
OFFICE_EXT = {".doc": "word", ".docx": "word", ".rtf": "word", ".odt": "word", ".txt": None,
              ".xls": "excel", ".xlsx": "excel", ".ods": "excel", ".csv": "excel",
              ".ppt": "powerpoint", ".pptx": "powerpoint", ".odp": "powerpoint"}


# ------------------------------------------------------------- da PDF
def to_images(doc: pymupdf.Document, pages: list[int], out_dir: str, base: str, fmt: str = "png",
              dpi: int = 150, progress=None) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for k, p in enumerate(pages):
        if progress and progress(k, len(pages)) is False:
            break
        pix = doc[p].get_pixmap(dpi=dpi, alpha=False)
        path = os.path.join(out_dir, f"{base}_pag{p + 1:03d}.{fmt}")
        if fmt in ("png", "pnm", "psd"):
            pix.save(path)
        else:
            from PIL import Image
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            if fmt in ("jpg", "jpeg"):
                img.save(path, "JPEG", quality=90, dpi=(dpi, dpi))
            elif fmt in ("tif", "tiff"):
                img.save(path, "TIFF", compression="tiff_lzw", dpi=(dpi, dpi))
            elif fmt == "bmp":
                img.save(path, "BMP")
            elif fmt == "webp":
                img.save(path, "WEBP", quality=90)
        paths.append(path)
    return paths


def to_text(doc: pymupdf.Document, path: str, pages=None) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for p in (pages if pages is not None else range(doc.page_count)):
            f.write(doc[p].get_text(flags=TEXT_FLAGS, sort=True))
            f.write("\n\f\n")


def to_html(doc: pymupdf.Document, path: str, pages=None) -> None:
    parts = ["<!DOCTYPE html><html><head><meta charset='utf-8'>"
             f"<title>{_html.escape(doc.metadata.get('title') or Path(path).stem)}</title>"
             "<style>body{background:#eee}div.page{background:white;margin:20px auto;box-shadow:0 2px 8px #0003;"
             "position:relative}</style></head><body>"]
    for p in (pages if pages is not None else range(doc.page_count)):
        parts.append("<div class='page'>" + doc[p].get_text("html") + "</div>")
    parts.append("</body></html>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(parts))


def to_markdown(doc: pymupdf.Document, path: str, pages=None) -> None:
    """Markdown semplice: titoli riconosciuti dal corpo del carattere."""
    sizes = {}
    for p in (pages if pages is not None else range(doc.page_count)):
        for b in doc[p].get_text("dict", flags=TEXT_FLAGS)["blocks"]:
            for l in b.get("lines", []):
                for s in l["spans"]:
                    k = round(s["size"])
                    sizes[k] = sizes.get(k, 0) + len(s["text"])
    body = max(sizes, key=sizes.get) if sizes else 11
    out = []
    for p in (pages if pages is not None else range(doc.page_count)):
        for b in doc[p].get_text("dict", flags=TEXT_FLAGS)["blocks"]:
            if b.get("type") != 0:
                continue
            text = " ".join("".join(s["text"] for s in l["spans"]) for l in b["lines"]).strip()
            if not text:
                continue
            size = max((s["size"] for l in b["lines"] for s in l["spans"]), default=body)
            bold = all(s["flags"] & 16 for l in b["lines"] for s in l["spans"])
            if size >= body * 1.6:
                out.append("# " + text)
            elif size >= body * 1.3:
                out.append("## " + text)
            elif size >= body * 1.1 or (bold and len(text) < 90):
                out.append("### " + text)
            else:
                out.append(text)
            out.append("")
        out.append("\n---\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))


def to_word(pdf_bytes: bytes, out_path: str, pages=None, progress=None) -> None:
    """PDF -> DOCX con pdf2docx (ricostruisce paragrafi, tabelle e immagini)."""
    from pdf2docx import Converter
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    try:
        tmp.write(pdf_bytes)
        tmp.close()
        cv = Converter(tmp.name)
        try:
            cv.convert(out_path, pages=pages, multi_processing=False)
        finally:
            cv.close()
    finally:
        try:
            os.remove(tmp.name)
        except OSError:
            pass


def to_excel(doc: pymupdf.Document, out_path: str, pages=None) -> int:
    """Esporta le tabelle riconosciute in un foglio per tabella. Ritorna quante."""
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    wb.remove(wb.active)
    n = 0
    for p in (pages if pages is not None else range(doc.page_count)):
        try:
            tabs = doc[p].find_tables()
        except Exception:
            continue
        for k, t in enumerate(tabs.tables, 1):
            rows = t.extract()
            if not rows:
                continue
            ws = wb.create_sheet(f"Pag{p + 1}_T{k}"[:31])
            for r, row in enumerate(rows, 1):
                for c, val in enumerate(row, 1):
                    v = (val or "").replace("\n", " ").strip()
                    cell = ws.cell(row=r, column=c, value=_num(v))
                    if r == 1:
                        cell.font = Font(bold=True)
            n += 1
    if n == 0:
        # nessuna tabella: testo riga per riga
        ws = wb.create_sheet("Testo")
        r = 1
        for p in (pages if pages is not None else range(doc.page_count)):
            for line in doc[p].get_text(flags=TEXT_FLAGS, sort=True).splitlines():
                if line.strip():
                    ws.cell(row=r, column=1, value=p + 1)
                    ws.cell(row=r, column=2, value=line)
                    r += 1
    wb.save(out_path)
    return n


def _num(v: str):
    t = v.replace(".", "").replace(",", ".") if "," in v else v
    try:
        return float(t) if "." in t else int(t)
    except ValueError:
        return v


# -------------------------------------------------------------- a PDF
def images_to_pdf(paths: list[str], page_size: tuple[float, float] | None = None, margin: float = 0) -> pymupdf.Document:
    out = pymupdf.open()
    for path in paths:
        img = pymupdf.open(path)
        for i in range(img.page_count):
            rect = img[i].rect
            pdfbytes = img.convert_to_pdf(from_page=i, to_page=i)
            src = pymupdf.open("pdf", pdfbytes)
            if page_size:
                w, h = page_size
                if rect.width > rect.height and w < h:
                    w, h = h, w
                page = out.new_page(width=w, height=h)
                page.show_pdf_page(page.rect + (margin, margin, -margin, -margin), src, 0)
            else:
                out.insert_pdf(src)
            src.close()
        img.close()
    return out


def text_to_pdf(text: str, fontsize: float = 11, page_size=(595, 842), title: str = "") -> pymupdf.Document:
    html = "<pre style='font-family:monospace;white-space:pre-wrap;font-size:%gpx'>%s</pre>" % (
        fontsize, _html.escape(text))
    return html_to_pdf(html, page_size)


def html_to_pdf(html: str, page_size=(595, 842), margin: float = 50) -> pymupdf.Document:
    import io
    story = pymupdf.Story(html=html)
    out = io.BytesIO()
    writer = pymupdf.DocumentWriter(out)
    mediabox = pymupdf.Rect(0, 0, *page_size)
    where = mediabox + (margin, margin, -margin, -margin)
    more = True
    while more:
        dev = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
    writer.close()
    return pymupdf.open("pdf", out.getvalue())


def office_available(kind: str) -> bool:
    try:
        import winreg
        prog = {"word": "Word.Application", "excel": "Excel.Application", "powerpoint": "PowerPoint.Application"}[kind]
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, prog))
        return True
    except Exception:
        return False


def libreoffice_path() -> str | None:
    for p in (r"C:\Program Files\LibreOffice\program\soffice.exe",
              r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"):
        if os.path.exists(p):
            return p
    return shutil.which("soffice")


def office_to_pdf(path: str, out_pdf: str, timeout: int = 300) -> None:
    """Converte un documento Office con Microsoft Office (se installato) o LibreOffice."""
    ext = Path(path).suffix.lower()
    kind = OFFICE_EXT.get(ext)
    src = os.path.abspath(path)
    dst = os.path.abspath(out_pdf)
    if kind and office_available(kind):
        ps = {
            "word": "$a=New-Object -ComObject Word.Application;$a.Visible=$false;"
                    "$d=$a.Documents.Open('{src}',$false,$true);$d.ExportAsFixedFormat('{dst}',17);"
                    "$d.Close($false);$a.Quit()",
            "excel": "$a=New-Object -ComObject Excel.Application;$a.Visible=$false;$a.DisplayAlerts=$false;"
                     "$d=$a.Workbooks.Open('{src}',0,$true);$d.ExportAsFixedFormat(0,'{dst}');"
                     "$d.Close($false);$a.Quit()",
            "powerpoint": "$a=New-Object -ComObject PowerPoint.Application;"
                          "$d=$a.Presentations.Open('{src}',$true,$false,$false);$d.SaveAs('{dst}',32);"
                          "$d.Close();$a.Quit()",
        }[kind].format(src=src.replace("'", "''"), dst=dst.replace("'", "''"))
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                           capture_output=True, text=True, timeout=timeout,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode == 0 and os.path.exists(dst):
            return
        err = (r.stderr or r.stdout).strip()
    else:
        err = "Microsoft Office non trovato"
    lo = libreoffice_path()
    if lo:
        outdir = tempfile.mkdtemp()
        subprocess.run([lo, "--headless", "--convert-to", "pdf", "--outdir", outdir, src],
                       capture_output=True, timeout=timeout,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        produced = os.path.join(outdir, Path(src).stem + ".pdf")
        if os.path.exists(produced):
            shutil.move(produced, dst)
            shutil.rmtree(outdir, ignore_errors=True)
            return
        shutil.rmtree(outdir, ignore_errors=True)
    raise RuntimeError("Conversione non riuscita. Serve Microsoft Office o LibreOffice installato.\n" + err)


def any_to_pdf(path: str) -> pymupdf.Document:
    """Converte un file qualsiasi supportato in un documento PDF in memoria."""
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        return pymupdf.open(path)
    if ext in IMAGE_EXT:
        return images_to_pdf([path])
    if ext in (".txt", ".log", ".md", ".py", ".csv", ".json", ".xml", ".ini"):
        with open(path, encoding="utf-8", errors="replace") as f:
            return text_to_pdf(f.read())
    if ext in (".html", ".htm"):
        with open(path, encoding="utf-8", errors="replace") as f:
            return html_to_pdf(f.read())
    if ext in OFFICE_EXT:
        fd, tmp = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        try:
            office_to_pdf(path, tmp)
            d = pymupdf.open(tmp)
            data = d.tobytes()
            d.close()
            return pymupdf.open("pdf", data)
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
    src = pymupdf.open(path)  # xps, epub, cbz, svg, fb2, mobi
    return pymupdf.open("pdf", src.convert_to_pdf())
