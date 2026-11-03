"""Traduzioni dell'interfaccia.

Il testo di partenza è l'italiano: T("Salva") restituisce "Save" se la lingua è
l'inglese. I dizionari stanno in editra/lang/<codice>.py (variabile STRINGS).
La lingua si sceglie nelle Impostazioni e si applica al riavvio; al primo avvio
si usa quella di Windows (italiano se Windows è in italiano, altrimenti inglese).
"""
from __future__ import annotations

import importlib

LANGUAGES = [("it", "Italiano"), ("en", "English")]

_strings: dict[str, str] = {}
LANG = "it"


def _system_language() -> str:
    try:
        import locale
        code = (locale.getlocale()[0] or "").lower()
        if code.startswith("it") or code.startswith("italian"):
            return "it"
    except Exception:
        pass
    try:
        import ctypes
        lid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        if lid & 0x3FF == 0x10:   # LANG_ITALIAN
            return "it"
    except Exception:
        pass
    return "en"


def configured_language() -> str:
    import os
    from . import settings
    lang = os.environ.get("EDITRA_LANG") or settings.get("language", "") or _system_language()
    return lang if lang in dict(LANGUAGES) else "en"


def set_language(lang: str) -> None:
    global LANG, _strings
    LANG = lang
    _strings = {}
    if lang != "it":
        try:
            _strings = importlib.import_module(f"{__package__}.lang.{lang}").STRINGS
        except Exception:
            _strings = {}


def T(text: str) -> str:
    """Testo tradotto nella lingua corrente (se manca la traduzione resta l'italiano)."""
    return _strings.get(text, text) if _strings else text


set_language(configured_language())
