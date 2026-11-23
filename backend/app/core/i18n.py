"""
The platform's own sentences, in the reader's language.

WHAT THIS IS FOR
----------------
The interface is translated in the frontend (src/i18n), seven languages. What
the frontend cannot translate is a sentence the backend writes: a
recommendation, an alert, the reasons beside a payment-risk score, the
explanation under a zone on the loss page, the evidence on a field visit. Those
reached every language in English, so an Arabic page carried English
paragraphs in the middle of it.

HOW
---
The English sentence is still written where it always was, and stored where
it always was (alerts and recommendations live in the database in English).
Each one has an entry in app/core/i18n_messages.py: the English wording with
its variable parts marked, and the same sentence in the other six languages.
When a response is built, `localize(text, lang)` finds the entry the English
sentence matches and writes it again in the requested language with the same
values. A stored alert is therefore shown in whatever language its reader has
chosen, including one chosen after the alert was written.

Figures are carried over exactly as the English wrote them: the same digits,
the same separators, the same "LBP". The interface does the same (see the note
on numerals at the top of src/i18n/arabic.ts), so a page never mixes two
styles of number. Dates and month names are written in the reader's language.

In Arabic an amount ("4,725,839 LBP") and an energy figure ("453.9 kWh") are
wrapped in the Unicode isolate marks (U+2066 ... U+2069, not displayed), so
the right-to-left text around them cannot reorder them into "LBP 4,725,839".
That is how the interface shows every figure with a unit (formatCurrency and
formatKwh in src/utils/helpers.ts), so a sentence from here and a card beside
it show the same figure the same way.

WHAT IS NOT TRANSLATED
----------------------
Records: names, zone and generator names, IDs, the provider's own alarm texts.
And values the frontend uses as keys (a status, a band, a segment or anomaly
type), which it translates itself; translating them here would break its logic.

A sentence with no entry is returned unchanged, in English, never broken. The
test suite fails when a sentence the system produces has no entry
(tests/test_review_fixes.py), so a gap is found by the tests, not by a reader.

WHICH LANGUAGE
--------------
The frontend sends the interface language in Accept-Language on every request
(src/services/api.ts). Anything else, or nothing, means English.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from fastapi import Request

LANGUAGES = ("en", "ar", "es", "fr", "de", "zh", "ja")
DEFAULT_LANGUAGE = "en"


def request_language(request: Request) -> str:
    """The first language in Accept-Language that the platform has, else English."""
    header = request.headers.get("accept-language", "")
    for part in header.split(","):
        tag = part.split(";")[0].strip().lower()
        primary = tag.split("-")[0]
        if primary in LANGUAGES:
            return primary
        if tag == "*":
            break
    return DEFAULT_LANGUAGE


# ---------------------------------------------------------------------------
# Months
# ---------------------------------------------------------------------------
MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTH_FULL = ["January", "February", "March", "April", "May", "June", "July", "August",
              "September", "October", "November", "December"]

# The month names of Lebanon and the Levant for Arabic, as on the provider's
# own bills, and the names the browser uses for these languages elsewhere on
# the page.
MONTH_NAMES = {
    "ar": ["كانون الثاني", "شباط", "آذار", "نيسان", "أيار", "حزيران", "تموز", "آب", "أيلول",
           "تشرين الأول", "تشرين الثاني", "كانون الأول"],
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
           "octubre", "noviembre", "diciembre"],
    "fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
           "octobre", "novembre", "décembre"],
    "de": ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September",
           "Oktober", "November", "Dezember"],
    "zh": [f"{n}月" for n in range(1, 13)],
    "ja": [f"{n}月" for n in range(1, 13)],
}

_ABBR = "|".join(MONTH_ABBR)
_FULL = "|".join(MONTH_FULL)


def _month_index(name: str) -> int:
    return (MONTH_ABBR.index(name) if name in MONTH_ABBR else MONTH_FULL.index(name)) + 1


def month_name(english: str, lang: str) -> str:
    """'Jun' or 'June' in `lang`."""
    if lang == DEFAULT_LANGUAGE:
        return english
    return MONTH_NAMES[lang][_month_index(english) - 1]


def month_year(english: str, lang: str) -> str:
    """'Jun 2026' or 'June 2026' in `lang`."""
    match = re.fullmatch(rf"({_ABBR}|{_FULL}) (\d{{4}})", english.strip())
    if not match or lang == DEFAULT_LANGUAGE:
        return english
    name, year = match.groups()
    month = MONTH_NAMES[lang][_month_index(name) - 1]
    if lang == "es":
        return f"{month} de {year}"
    if lang in ("zh", "ja"):
        return f"{year}年{month}"
    return f"{month} {year}"


def day_month_year(english: str, lang: str) -> str:
    """'31 Mar 2025' in `lang`."""
    match = re.fullmatch(rf"(\d{{1,2}}) ({_ABBR}) (\d{{4}})", english.strip())
    if not match or lang == DEFAULT_LANGUAGE:
        return english
    day, name, year = match.groups()
    day = str(int(day))
    month = MONTH_NAMES[lang][_month_index(name) - 1]
    if lang == "es":
        return f"{day} de {month} de {year}"
    if lang == "de":
        return f"{day}. {month} {year}"
    if lang in ("zh", "ja"):
        return f"{year}年{month}{day}日"
    return f"{day} {month} {year}"


# ---------------------------------------------------------------------------
# Plurals
# ---------------------------------------------------------------------------
def _arabic_category(n: int) -> str:
    """CLDR plural categories for Arabic."""
    if n == 0:
        return "zero"
    if n == 1:
        return "one"
    if n == 2:
        return "two"
    if 3 <= n % 100 <= 10:
        return "few"
    if 11 <= n % 100 <= 99:
        return "many"
    return "other"


@dataclass(frozen=True)
class Plural:
    """
    A translation whose wording depends on a count, for Arabic, where a noun
    after a number takes one of five forms (one day, two days, 3 to 10 days,
    11 to 99 days, a hundred days). `count` names the placeholder holding it.
    """

    count: str
    one: str
    two: str
    few: str
    many: str
    other: str

    def choose(self, value: str) -> str:
        try:
            n = int(value.replace(",", ""))
        except ValueError:
            return self.other
        category = _arabic_category(n)
        return getattr(self, "other" if category == "zero" else category)


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Message:
    """One English sentence and its translations, with {name} or {name:type} placeholders."""

    en: str
    ar: str | Plural
    es: str
    fr: str
    de: str
    zh: str
    ja: str


# What each kind of placeholder may match in the English, and how its value is
# written in another language.
_VALUE = {
    "text": r".+?",
    "num": r"[-+]?\d[\d,]*(?:\.\d+)?",
    "money": r"[-+]?\d[\d,]*(?:\.\d+)? LBP",
    "date": rf"\d{{1,2}} (?:{_ABBR}) \d{{4}}",
    "monthyear": rf"(?:{_ABBR}|{_FULL}) \d{{4}}",
    "monthname": rf"(?:{_FULL})",
    "sub": r".+?",
    # The inside of a bracket, e.g. "cv=2.32": no brackets, no clause break.
    "expr": r"[^();]+",
}
_PLACEHOLDER = re.compile(r"\{(\w+)(?::(\w+))?\}")

# How each language separates the clauses of a list written with "; ".
_LIST_SEPARATOR = {"ar": "؛ ", "zh": "；", "ja": "；", "fr": " ; "}

# Right-to-left languages, where a figure with a unit is isolated (see above).
_RTL = {"ar"}
_LRI, _PDI = "\u2066", "\u2069"
# "453.9 kWh", "1,200-1,800 kWh": a number, or a range, followed by the unit.
# It must start where the number starts: not after an isolate mark (a run
# isolated already, e.g. inside a translated sub-sentence) and not after a
# digit, comma or point (the middle of a number), so no run is wrapped twice.
_KWH_RUN = re.compile(r"(?<![\u2066\d,.])\d[\d,]*(?:\.\d+)?(?:-\d[\d,]*(?:\.\d+)?)? kWh")


def _isolate(text: str) -> str:
    return f"{_LRI}{text}{_PDI}"


@lru_cache(maxsize=1)
def _amount_run() -> re.Pattern:
    """'24,954,137 LBP', '-1,000 LBP': an amount as core/money.py writes it, in any sentence."""
    from app.config import settings

    code = re.escape((settings.CURRENCY or "LBP").upper())
    return re.compile(rf"(?<![\u2066\d,.\-])-?\d[\d,]*(?:\.\d+)? {code}\b")


def isolate_figures(text: str | None, lang: str) -> str | None:
    """
    `text` with every amount and kWh figure isolated, in a right-to-left language.

    For sentences written in Arabic directly rather than translated from the
    catalogue, which is how the customer assistant writes its replies. Without
    it a reply showed "LBP 24,954,137" where the dashboard card beside it
    showed "24,954,137 LBP". A run isolated already is left as it is.
    """
    if not text or lang not in _RTL:
        return text
    text = _amount_run().sub(lambda m: _isolate(m.group(0)), text)
    return _KWH_RUN.sub(lambda m: _isolate(m.group(0)), text)


def _convert(value: str, kind: str, lang: str) -> str:
    if kind == "money":
        return _isolate(value) if lang in _RTL else value
    if kind == "date":
        return day_month_year(value, lang)
    if kind == "monthyear":
        return month_year(value, lang)
    if kind == "monthname":
        return month_name(value, lang)
    if kind == "sub":
        return localize(value, lang)
    return value


@lru_cache(maxsize=1)
def _compiled():
    """(exact lookup, [(message, pattern, kinds)]) built once from the catalogue."""
    from app.core.i18n_messages import MESSAGES

    exact: dict[str, Message] = {}
    patterns = []
    for message in MESSAGES:
        names = [m.group(1) for m in _PLACEHOLDER.finditer(message.en)]
        for lang in LANGUAGES[1:]:
            translation = getattr(message, lang)
            variants = (
                [translation.one, translation.two, translation.few, translation.many, translation.other]
                if isinstance(translation, Plural) else [translation]
            )
            for variant in variants:
                used = sorted(set(re.findall(r"\{(\w+)\}", variant)))
                if used != sorted(set(names)) and not (isinstance(translation, Plural) and set(used) <= set(names)):
                    raise ValueError(f"{lang} translation of {message.en!r} uses {used}, English has {names}")
        if not names:
            if message.en in exact:
                raise ValueError(f"duplicate entry: {message.en!r}")
            exact[message.en] = message
            continue
        kinds: dict[str, str] = {}
        regex, position = "", 0
        for m in _PLACEHOLDER.finditer(message.en):
            regex += re.escape(message.en[position:m.start()])
            name, kind = m.group(1), m.group(2) or "text"
            kinds[name] = kind
            regex += f"(?P<{name}>{_VALUE[kind]})"
            position = m.end()
        regex += re.escape(message.en[position:])
        literal = len(_PLACEHOLDER.sub("", message.en))
        patterns.append((literal, message, re.compile(regex, re.S), kinds))
    # The most specific first: the entry with the most fixed text wins.
    patterns.sort(key=lambda item: -item[0])
    return exact, [(message, pattern, kinds) for _, message, pattern, kinds in patterns]


def _render(message: Message, lang: str, values: dict[str, str]) -> str:
    translation = getattr(message, lang)
    if isinstance(translation, Plural):
        translation = translation.choose(values.get(translation.count, ""))
    text = re.sub(r"\{(\w+)\}", lambda m: values[m.group(1)], translation)
    if lang in _RTL:
        text = _KWH_RUN.sub(lambda m: _isolate(m.group(0)), text)
    return text


def localize(text: str | None, lang: str) -> str | None:
    """`text` in `lang` when the catalogue has it, else `text` unchanged."""
    if not text or lang == DEFAULT_LANGUAGE or lang not in LANGUAGES:
        return text
    exact, patterns = _compiled()
    message = exact.get(text)
    if message is not None:
        return _render(message, lang, {})
    if "; " in text and all(is_translated(part) for part in text.split("; ")):
        # A list of clauses, as the anomaly model writes its reasons. Checked
        # before the patterns, so that a pattern with a free-text part cannot
        # swallow the whole list as if it were one clause.
        parts = [localize(part, lang) for part in text.split("; ")]
        return _LIST_SEPARATOR.get(lang, "; ").join(parts)
    for message, pattern, kinds in patterns:
        match = pattern.fullmatch(text)
        if match:
            values = {name: _convert(value, kinds[name], lang) for name, value in match.groupdict().items()}
            return _render(message, lang, values)
    return text


def localize_all(texts, lang: str) -> list:
    return [localize(text, lang) for text in texts]


def is_translated(text: str) -> bool:
    """Whether the catalogue has an entry for this English sentence (used by the tests)."""
    if not text:
        return True
    exact, patterns = _compiled()
    if text in exact:
        return True
    if "; " in text and all(is_translated(part) for part in text.split("; ")):
        return True
    for _, pattern, kinds in patterns:
        match = pattern.fullmatch(text)
        if match and all(is_translated(value) for name, value in match.groupdict().items()
                         if kinds[name] == "sub"):
            return True
    return False


def join_sentences(sentences: list[str], lang: str) -> str:
    """Sentences side by side: separated by a space, except in Chinese and Japanese."""
    return ("" if lang in ("zh", "ja") else " ").join(sentences)
