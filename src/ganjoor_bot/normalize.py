from __future__ import annotations

import re
import unicodedata

_ARABIC_TO_PERSIAN = str.maketrans(
    {
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "ۀ": "ه",
        "ة": "ه",
        "ؤ": "و",
        "آ": "ا",
        "أ": "ا",
        "إ": "ا",
        "ٱ": "ا",
    }
)

_ZERO_WIDTH = {"\u200b", "\u200c", "\u200d", "\ufeff"}
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_persian(text: str) -> str:
    """Return a conservative normalized representation for search.

    Original text must always be stored separately. This function intentionally
    removes Arabic/Persian combining marks and normalizes Arabic character forms,
    zero-width characters, and whitespace so common typing variations match.
    """
    text = unicodedata.normalize("NFKC", text).translate(_ARABIC_TO_PERSIAN)
    text = "".join(ch for ch in text if ch not in _ZERO_WIDTH)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text
