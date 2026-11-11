"""
The limits of the platform's two assistants, read from backend/config/chatbot.toml.

WHAT THE FILE CONTROLS
----------------------
For the customer assistant (app/ai/chatbot.py): which topics it answers, which
facts that are not the customer's own records it may mention (the published
tariff, the diesel price, the zone average and its minimum group size, supply
hours, the generator, the network peak), the wording of its refusals, and
whether a language model words the answers.

For the ask-the-data box (app/rag/): which folder of definition documents it
searches, the relevance below which a passage is ignored, and whether a
language model routes and rewords.

WHAT IT CANNOT CONTROL
----------------------
Whose records the customer assistant reads. Every account query filters on the
signed-in customer's ID in code, and nothing here can change that. Likewise the
ask-the-data box is admin-only by `require_admin` on its routes. The file can
narrow what the assistants say; it cannot widen whose data they read.

FAILURE
-------
Read once, on first use, so an edit needs a backend restart. Every problem is
written to the backend log, and none of them can make the assistants share more:

  * a missing or unreadable file (a syntax error, for instance) puts both
    assistants in their most private mode until it is fixed: every shared fact
    withheld and no language model, while the topics keep their shipped values;
  * a single value of the wrong type is ignored in the same direction: a fact is
    withheld, the model stays off, anything else keeps its shipped value;
  * an unknown key or topic is ignored.
"""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]
CONFIG_FILE = BACKEND_DIR / "config" / "chatbot.toml"

# The rule engine's intents, grouped into the topics the file switches on and
# off. Greetings, "what can you do?" and the catch-all are always answered:
# they are how a customer finds out what the assistant is for.
TOPICS: Mapping[str, frozenset[str]] = MappingProxyType({
    "billing": frozenset({"billing", "bill_breakdown", "tariff", "discount", "forecast"}),
    "payments": frozenset({"payment", "last_payment"}),
    "consumption": frozenset({"consumption", "history", "compare", "savings", "peak",
                              "cooling", "solar"}),
    "account": frozenset({"account", "account_change", "password"}),
    "service": frozenset({"supply_hours", "outage"}),
})
ALWAYS_ANSWERED = frozenset({"greeting", "capabilities", "faq"})

# Plain-language names, for the language model's instructions.
TOPIC_LABELS: Mapping[str, str] = MappingProxyType({
    "billing": "bills, how a bill was calculated and the rate per kWh",
    "payments": "what is owed and payments",
    "consumption": "electricity consumption and ways to save",
    "account": "the customer's own account, meter and contract details",
    "service": "the supply hours of the customer's zone and power cuts",
})

SHARES = ("published_tariff", "diesel_price", "zone_average", "supply_hours",
          "generator", "network_peak")
REPLIES = ("out_of_scope", "not_shared", "password_help")
MIN_GROUP_FLOOR = 3

_DEFAULT_REPLIES: Mapping[str, str] = MappingProxyType({
    "out_of_scope_en": (
        "I can only help with your own electricity account: your bills, payments, "
        "consumption and contract. For anything else, please contact the provider's office."),
    "out_of_scope_ar": (
        "أستطيع مساعدتك في حسابك أنت فقط: فواتيرك ودفعاتك واستهلاكك واشتراكك. "
        "لأي أمر آخر، يُرجى مراجعة مكتب المزوّد."),
    "not_shared_en": (
        "That information is not shared through the assistant. The provider's office can "
        "tell you."),
    "not_shared_ar": "هذه المعلومة لا تُعطى عبر المساعد. يستطيع مكتب المزوّد إفادتك بها.",
    "password_help_en": (
        "If you are signed in and want a new password, open the Profile page and use "
        "Change password; it asks for your current one first. If you cannot sign in at "
        "all, the provider's office can set a new one for you, because reset by e-mail "
        "is not available yet. I cannot set a password for you, and nobody at the "
        "provider can read your existing one."),
    "password_help_ar": (
        "إن كنت داخلاً إلى حسابك وتريد كلمة مرور جديدة، افتح صفحة الملف الشخصي واستخدم قسم "
        "«تغيير كلمة المرور»؛ ستطلب منك كلمة المرور الحالية أولاً. وإن كنت لا تستطيع الدخول "
        "أصلاً، فمكتب المزوّد يستطيع تعيين كلمة مرور جديدة لك، لأن إعادة التعيين عبر البريد "
        "الإلكتروني غير متاحة بعد. أنا لا أستطيع تعيين كلمة مرور لك، ولا أحد لدى المزوّد "
        "يستطيع قراءة كلمة مرورك الحالية."),
})


@dataclass(frozen=True)
class CustomerAssistant:
    topics: tuple[str, ...]
    use_language_model: bool
    share: Mapping[str, bool]
    zone_average_min_subscribers: int
    replies: Mapping[str, str]

    def allows(self, intent: str) -> bool:
        """Whether a detected intent falls inside a topic that is switched on."""
        if intent in ALWAYS_ANSWERED:
            return True
        return any(intent in TOPICS[t] for t in self.topics)

    def shares(self, fact: str) -> bool:
        return bool(self.share.get(fact, False))

    def reply(self, name: str, lang: str) -> str:
        key = f"{name}_{'ar' if lang == 'ar' else 'en'}"
        return self.replies.get(key) or _DEFAULT_REPLIES[key]


@dataclass(frozen=True)
class AskTheData:
    documents_dir: Path
    min_relevance: float
    use_language_model: bool


@dataclass(frozen=True)
class ChatbotConfig:
    customer: CustomerAssistant
    ask: AskTheData
    source: str
    problems: tuple[str, ...]


def _defaults() -> dict[str, Any]:
    return {
        "customer_assistant": {
            "topics": list(TOPICS),
            "use_language_model": True,
        },
        "ask_the_data": {
            "documents_dir": "data/rag_documents",
            "min_relevance": 0.08,
            "use_language_model": True,
        },
    }


def _table(raw: Mapping[str, Any], key: str, problems: list[str]) -> Mapping[str, Any]:
    value = raw.get(key, {})
    if not isinstance(value, dict):
        problems.append(f"[{key}] is not a table; defaults used")
        return {}
    return value


def _bool(raw: Mapping[str, Any], key: str, default: bool, where: str, problems: list[str]) -> bool:
    """A true/false setting. Absent: the default. Not true or false: false, the private choice."""
    if key not in raw:
        return default
    if isinstance(raw[key], bool):
        return raw[key]
    problems.append(f"{where}.{key} must be true or false; false used")
    return False


def _unknown(raw: Mapping[str, Any], known: set[str], where: str, problems: list[str]) -> None:
    for key in sorted(set(raw) - known):
        problems.append(f"{where}.{key} is not a known setting and was ignored")


def _parse(raw: Mapping[str, Any], private: bool = False) -> tuple[CustomerAssistant, AskTheData, list[str]]:
    """Check every value. `private`: the file could not be read, so share nothing and use no model."""
    problems: list[str] = []
    d = _defaults()
    shipped = not private
    _unknown(raw, {"customer_assistant", "ask_the_data"}, "file", problems)

    # ---- customer assistant
    ca = _table(raw, "customer_assistant", problems)
    _unknown(ca, {"topics", "use_language_model", "share", "replies"}, "customer_assistant", problems)
    topics = d["customer_assistant"]["topics"]
    if "topics" in ca:
        given = ca["topics"]
        if isinstance(given, list) and all(isinstance(t, str) for t in given):
            known = [t for t in given if t in TOPICS]
            for t in given:
                if t not in TOPICS:
                    problems.append(f"customer_assistant.topics: unknown topic {t!r} ignored")
            topics = list(dict.fromkeys(known))
        else:
            problems.append("customer_assistant.topics must be a list of topic names; default used")
    use_model = _bool(ca, "use_language_model", shipped, "customer_assistant", problems)

    sh = _table(ca, "share", problems)
    _unknown(sh, set(SHARES) | {"zone_average_min_subscribers"}, "customer_assistant.share", problems)
    share = {name: _bool(sh, name, shipped, "customer_assistant.share", problems) for name in SHARES}
    min_group = 5
    if "zone_average_min_subscribers" in sh:
        value = sh["zone_average_min_subscribers"]
        if isinstance(value, int) and not isinstance(value, bool) and value >= MIN_GROUP_FLOOR:
            min_group = value
        else:
            problems.append(
                "customer_assistant.share.zone_average_min_subscribers must be a whole number "
                f"of at least {MIN_GROUP_FLOOR}; default 5 used")

    rp = _table(ca, "replies", problems)
    _unknown(rp, set(_DEFAULT_REPLIES), "customer_assistant.replies", problems)
    replies = dict(_DEFAULT_REPLIES)
    for key in _DEFAULT_REPLIES:
        if key in rp:
            if isinstance(rp[key], str) and rp[key].strip():
                replies[key] = rp[key].strip()
            else:
                problems.append(f"customer_assistant.replies.{key} must be non-empty text; default used")

    customer = CustomerAssistant(
        topics=tuple(topics),
        use_language_model=use_model,
        share=MappingProxyType(share),
        zone_average_min_subscribers=min_group,
        replies=MappingProxyType(replies),
    )

    # ---- ask the data
    ad = _table(raw, "ask_the_data", problems)
    _unknown(ad, {"documents_dir", "min_relevance", "use_language_model"}, "ask_the_data", problems)
    docs = BACKEND_DIR / d["ask_the_data"]["documents_dir"]
    if "documents_dir" in ad:
        value = ad["documents_dir"]
        candidate = (BACKEND_DIR / value) if isinstance(value, str) else None
        if candidate is not None and candidate.is_dir():
            docs = candidate
        else:
            problems.append(f"ask_the_data.documents_dir {value!r} is not a folder; default used")
    relevance = d["ask_the_data"]["min_relevance"]
    if "min_relevance" in ad:
        value = ad["min_relevance"]
        if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1:
            relevance = float(value)
        else:
            problems.append("ask_the_data.min_relevance must be a number from 0 to 1; default used")
    ask = AskTheData(
        documents_dir=docs,
        min_relevance=relevance,
        use_language_model=_bool(ad, "use_language_model", shipped, "ask_the_data", problems),
    )
    return customer, ask, problems


def load(path: Path | None = None) -> ChatbotConfig:
    """Read and check the file. Never raises: problems are logged and defaults used."""
    path = path or CONFIG_FILE
    private = False
    try:
        with open(path, "rb") as fh:
            raw = tomllib.load(fh)
        source = str(path)
    except (tomllib.TOMLDecodeError, OSError) as exc:
        raw, source, private = {}, "most private mode (file not readable)", True
        logger.error("Chatbot configuration %s could not be read (%s). Until it is fixed both "
                     "assistants withhold every shared fact and use no language model.", path, exc)
    customer, ask, problems = _parse(raw, private=private)
    for problem in problems:
        logger.error("Chatbot configuration: %s", problem)
    return ChatbotConfig(customer=customer, ask=ask, source=source, problems=tuple(problems))


_override: ChatbotConfig | None = None


@lru_cache(maxsize=1)
def _read() -> ChatbotConfig:
    return load()


def get() -> ChatbotConfig:
    """The configuration in force: the file, read on first use, unless a test installed one."""
    return _override if _override is not None else _read()


def use(config: ChatbotConfig | None) -> None:
    """Install a configuration (tests), or with None go back to the file and re-read it."""
    global _override
    _override = config
    _read.cache_clear()
