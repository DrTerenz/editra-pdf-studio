"""Mappa dei font installati in Windows: famiglia -> file per stile.

Serve a incorporare nel PDF lo stesso carattere scelto nell'editor.
La fonte è il registro di Windows (font di sistema e font dell'utente).
"""
from __future__ import annotations

import os
import re
from functools import lru_cache

STYLE_WORDS = {
    "bold": "b", "grassetto": "b", "italic": "i", "oblique": "i", "corsivo": "i",
}
# stili che non sono né grassetto né corsivo ma fanno parte del nome della famiglia
_WEIGHT_WORDS = ("thin", "extralight", "ultralight", "light", "semilight", "regular", "normal",
                 "book", "medium", "semibold", "demibold", "extrabold", "ultrabold", "black", "heavy",
                 "condensed", "narrow")

# nomi PostScript dei 14 font standard -> famiglia Windows equivalente
STANDARD_ALIASES = {
    "helvetica": "Arial", "arialmt": "Arial", "arial": "Arial", "helv": "Arial",
    "times": "Times New Roman", "timesroman": "Times New Roman", "timesnewroman": "Times New Roman",
    "tiro": "Times New Roman", "courier": "Courier New", "couriernew": "Courier New", "cour": "Courier New",
    "symbol": "Symbol", "zapfdingbats": "Wingdings",
}

FALLBACK_FAMILY = "Arial"


def _font_dirs() -> list[str]:
    dirs = [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        dirs.append(os.path.join(local, "Microsoft", "Windows", "Fonts"))
    return dirs


def _registry_entries() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    try:
        import winreg
    except ImportError:
        return out
    key_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(root, key_path) as k:
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(k, i)
                    except OSError:
                        break
                    out.append((name, str(value)))
                    i += 1
        except OSError:
            continue
    return out


def _resolve_file(value: str) -> str | None:
    if os.path.isabs(value):
        return value if os.path.exists(value) else None
    for d in _font_dirs():
        p = os.path.join(d, value)
        if os.path.exists(p):
            return p
    return None


@lru_cache(maxsize=1)
def system_fonts() -> dict[str, dict[str, str]]:
    """{famiglia: {'r': file, 'b': file, 'i': file, 'bi': file}}"""
    fams: dict[str, dict[str, str]] = {}
    for name, value in _registry_entries():
        if not value.lower().endswith((".ttf", ".otf", ".ttc")):
            continue
        path = _resolve_file(value)
        if not path:
            continue
        clean = re.sub(r"\s*\((TrueType|OpenType|All res)\)\s*$", "", name, flags=re.I)
        for sub in clean.split(" & "):
            words = sub.split()
            style = ""
            fam_words = []
            for w in words:
                lw = w.lower()
                if lw in STYLE_WORDS:
                    style += STYLE_WORDS[lw]
                else:
                    fam_words.append(w)
            # "Arial Regular" -> "Arial"
            while fam_words and fam_words[-1].lower() in ("regular", "normal"):
                fam_words.pop()
            fam = " ".join(fam_words).strip()
            if not fam:
                continue
            key = {"": "r", "b": "b", "i": "i", "bi": "bi", "ib": "bi"}.get(style, "r")
            fams.setdefault(fam, {}).setdefault(key, path)
    return fams


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


@lru_cache(maxsize=1)
def _norm_index() -> dict[str, str]:
    return {_norm(f): f for f in system_fonts()}


def clean_pdf_font_name(name: str) -> tuple[str, bool, bool]:
    """'ABCDEF+Calibri-BoldItalic' -> ('Calibri', bold, italic)."""
    n = name.split("+", 1)[1] if re.match(r"^[A-Z]{6}\+", name) else name
    low = n.lower()
    bold = any(w in low for w in ("bold", "black", "heavy", "semibold", "demi"))
    italic = any(w in low for w in ("italic", "oblique", "it,", "-it"))
    base = re.split(r"[-,]", n)[0]
    base = re.sub(r"(PSMT|PS|MT)$", "", base)
    return base, bold, italic


def find_family(pdf_font_name: str) -> str | None:
    """Trova la famiglia di sistema che corrisponde a un nome di font PDF, se esiste."""
    base, _, _ = clean_pdf_font_name(pdf_font_name)
    nb = _norm(base)
    if nb in STANDARD_ALIASES:
        return STANDARD_ALIASES[nb]
    idx = _norm_index()
    if nb in idx:
        return idx[nb]
    # "TimesNewRomanPS" -> "timesnewroman"; "SegoeUISemibold" -> "segoeuisemibold"
    for k, fam in idx.items():
        if k and (nb.startswith(k) and len(k) >= 4):
            return fam
    return None


def font_file(family: str, bold: bool = False, italic: bool = False) -> str | None:
    """File del font per famiglia e stile; ripiega sullo stile regolare."""
    fams = system_fonts()
    f = fams.get(family)
    if f is None:
        nf = _norm_index().get(_norm(family))
        f = fams.get(nf) if nf else None
    if f is None:
        return None
    key = ("b" if bold else "") + ("i" if italic else "") or "r"
    if key == "":
        key = "r"
    return f.get(key) or (f.get("b") if bold else None) or (f.get("i") if italic else None) or f.get("r") or next(iter(f.values()))


def has_style(family: str, bold: bool, italic: bool) -> bool:
    f = system_fonts().get(family) or {}
    key = ("b" if bold else "") + ("i" if italic else "") or "r"
    return key in f
