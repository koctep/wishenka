"""Bounded, deterministic decoding of external HTML documents."""

import codecs
import re
from html.parser import HTMLParser


class _MetaCharset(HTMLParser):
    """Read charset declarations from meta tags in the bounded HTML prefix."""

    def __init__(self) -> None:
        super().__init__()
        self.labels: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "meta":
            return
        values = dict(attrs)
        label = values.get("charset")
        if label:
            self.labels.append(label)
        if (values.get("http-equiv") or "").lower() == "content-type":
            match = re.search(
                r"charset\s*=\s*['\"]?([^\s;'\"]+)", values.get("content") or "", re.I
            )
            if match:
                self.labels.append(match.group(1))


def _codec(label: str | None) -> str | None:
    if not label or len(label) > 64:
        return None
    try:
        info = codecs.lookup(label.strip())
    except (LookupError, ValueError):
        return None
    return info.name if info._is_text_encoding else None


def _russian_score(text: str) -> float:
    """Rank common Russian letter pairs; this is a heuristic, not detection proof."""
    sample = text[:4096].lower()
    letters = sum("а" <= char <= "я" or char == "ё" for char in sample)
    pairs = (
        "ст",
        "но",
        "то",
        "на",
        "ен",
        "ов",
        "ни",
        "ра",
        "во",
        "пр",
        "ос",
        "ор",
        "ро",
        "по",
        "ре",
        "ри",
        "ко",
        "ка",
        "ог",
        "ие",
        "ан",
        "го",
        "та",
        "ер",
        "се",
        "ой",
        "ал",
        "от",
        "ли",
        "ле",
        "ть",
        "де",
        "те",
        "ет",
        "не",
        "од",
        "для",
    )
    return sum(sample.count(pair) for pair in pairs) / max(letters, 1)


def decode_html(raw: bytes, content_type: str) -> str:
    """Decode HTML using BOM, UTF-8, declarations, then a conservative Cyrillic guess."""
    for bom, encoding in (
        (codecs.BOM_UTF8, "utf-8-sig"),
        (codecs.BOM_UTF32_LE, "utf-32"),
        (codecs.BOM_UTF32_BE, "utf-32"),
        (codecs.BOM_UTF16_LE, "utf-16"),
        (codecs.BOM_UTF16_BE, "utf-16"),
    ):
        if raw.startswith(bom):
            return raw.decode(encoding, errors="replace")
    try:
        utf8 = raw.decode("utf-8")
        if any(byte >= 128 for byte in raw):
            return utf8
    except UnicodeDecodeError:
        utf8 = None

    header = re.search(r"charset\s*=\s*['\"]?([^\s;'\"]+)", content_type[:1024], re.I)
    parser = _MetaCharset()
    parser.feed(raw[:4096].decode("ascii", errors="replace"))
    labels = ([header.group(1)] if header else []) + parser.labels
    for label in labels:
        candidate = _codec(label)
        if candidate:
            try:
                return raw.decode(candidate)
            except (UnicodeDecodeError, ValueError):
                pass
    if utf8 is not None:
        return utf8
    guesses = []
    for encoding in ("cp1251", "koi8-r"):
        try:
            value = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        guesses.append((_russian_score(value), value))
    guesses.sort(key=lambda item: item[0], reverse=True)
    if (
        guesses
        and guesses[0][0] >= 0.06
        and (len(guesses) == 1 or guesses[0][0] - guesses[1][0] >= 0.03)
    ):
        return guesses[0][1]
    return raw.decode("utf-8", errors="replace")
