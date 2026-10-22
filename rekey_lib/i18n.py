"""Messages in the reader's language. Code is written in English; messages.py holds the rest.

    _("Saved to {store}", store="1Password")

The language is REKEY_LANG, else the system locale (LC_ALL, LC_MESSAGES, LANG). Untranslated
messages fall back to English. Text written into shared files (templates, 1Password items)
stays in English so a team with mixed languages sees the same files.
"""

from __future__ import annotations

import os

from .messages import CATALOG

LANGS = ("en", "ko", "zh", "ja", "es")


def detect() -> str:
    for var in ("REKEY_LANG", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var, "").lower()
        if value:
            return next((code for code in LANGS if value.startswith(code)), "en")
    return "en"


LANG = detect()


def _(msg: str, **kw: object) -> str:
    text = CATALOG.get(LANG, {}).get(msg, msg)
    return text.format(**kw) if kw else text
