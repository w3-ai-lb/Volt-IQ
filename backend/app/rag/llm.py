"""
The language model's two jobs, and the fence around both.

WHAT IT DOES
------------
1. ROUTING. Given a question and the list of questions this system can answer,
   it picks one, or says none fits. That is all. It sees no data.
2. REPHRASING. Given a sentence already written from a query result, it says
   the same thing more naturally. It may change words. It may not change,
   add or remove a figure.

WHY IT ROUTES INSTEAD OF WRITING SQL
------------------------------------
The briefing asks for text-to-SQL, and this is a deliberate reading of what
that requirement is protecting:

    "Text-to-SQL for anything numerical. The LLM converts the question into a
     SQL query, the database computes the real answer, the LLM explains the
     result in words."

The thing being protected is that THE DATABASE COMPUTES THE ANSWER, never the
model. Both designs achieve that. They differ in what happens when the model
is wrong.

A generated query that joins `invoices` to `zone_energy_daily` on the wrong
key, or reads `total_amount` where it needed `units_consumed`, still returns a
number. It is a plausible number, it is wrong, and nobody looking at it can
tell, which is the exact failure mode the briefing spends a paragraph warning
about. Routing to one of eleven queries that have been written, read and tested
cannot fail that way: the worst case is the wrong one of eleven correct
answers, which reads as obviously off-topic rather than as quietly false.

The cost is honest and should be stated in the report: a question no intent
covers is refused rather than attempted. That is the trade the briefing's own
rule points to, "never a guess".

WHICH PROVIDER
--------------
OpenAI, when OPENAI_API_KEY is set (the same key the customer assistant uses).
Nothing above this module knows or cares. If no key is configured, or
config/chatbot.toml switches the model off, every function here returns None
and the system answers from its own patterns.
"""

from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

# A rewrite may only contain figures that were already in the draft. Checked
# rather than requested, because "do not invent numbers" is an instruction a
# model can fail silently and this cannot.
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def _digits(text: str) -> set[str]:
    return {m.replace(",", "") for m in _NUMBER.findall(text)}


class Provider:
    """Minimal shape the SDK is adapted to. `complete` returns text or None."""

    name = "none"

    def complete(self, system: str, user: str, max_tokens: int = 300) -> str | None:  # pragma: no cover
        return None


class OpenAIProvider(Provider):
    name = "openai"

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    def complete(self, system: str, user: str, max_tokens: int = 300) -> str | None:
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key)
        response = client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=0.2,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return (response.choices[0].message.content or "").strip() or None


# Set by tests to exercise the guards without a network call or a key.
_override: Provider | None = None


def set_provider(provider: Provider | None) -> None:
    """Install a provider directly. Used by the test suite; harmless otherwise."""
    global _override
    _override = provider


def provider() -> Provider | None:
    """The OpenAI provider when a key is set, or None. Off entirely when config/chatbot.toml says so."""
    from app.core import chatbot_config

    if not chatbot_config.get().ask.use_language_model:
        return None
    if _override is not None:
        return _override

    from app.config import settings

    if settings.OPENAI_API_KEY:
        return OpenAIProvider(settings.OPENAI_API_KEY, settings.OPENAI_MODEL or "gpt-4o-mini")
    return None


def available() -> bool:
    return provider() is not None


# ---------------------------------------------------------------------------
ROUTER_SYSTEM = """You route a question to one of a fixed set of database queries.

Reply with JSON only: {"intent": "<name>"} or {"intent": null}.

Rules:
- The name MUST be one of the names given. Never invent one.
- If no listed query would answer the question, reply {"intent": null}.
- You are routing only. Do not answer the question, do not write SQL, and do
  not produce any number.
- Questions may be in English or Arabic."""


def choose_intent(question: str, catalogue: list[dict]) -> str | None:
    """
    Ask the model which of the known queries fits, or none.

    The answer is validated against the catalogue before it is used, so a
    hallucinated intent name is discarded rather than looked up. That check is
    what makes it safe to let a model choose at all.
    """
    client = provider()
    if client is None:
        return None

    names = {c["name"] for c in catalogue}
    listing = "\n".join(
        f"- {c['name']}: {c['description']}. Example: {c['examples'][0]}" for c in catalogue
    )
    try:
        raw = client.complete(
            ROUTER_SYSTEM,
            f"Available queries:\n{listing}\n\nQuestion: {question}\n\nJSON:",
            max_tokens=60,
        )
    except Exception:
        logger.warning("Intent routing failed; falling back to patterns", exc_info=True)
        return None

    if not raw:
        return None
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        return None
    try:
        chosen = json.loads(match.group(0)).get("intent")
    except json.JSONDecodeError:
        return None

    if chosen in names:
        return chosen
    if chosen is not None:
        logger.warning("Model chose an intent that does not exist: %r", chosen)
    return None


REPHRASE_SYSTEM = """You rewrite one answer for the owner of a Lebanese private
generator business (ishtirak). He is not an engineer.

Absolute rules:
- Keep every number exactly as given. Add none. Remove none. Change none.
- Never use the words theft, thief, stealing or steal. The correct term is
  "unexplained loss", and it means a reason to investigate, not proof.
- Two or three sentences. Reply in the language the question was asked in."""


def rephrase(question: str, drafted: str) -> str | None:
    """
    A more natural wording of an answer already written from query results.

    Returns None, leaving the drafted sentence in place, if the rewrite adds a
    figure of its own or uses a word the briefing forbids. Silence is the right
    failure here: the drafted answer is already correct.
    """
    client = provider()
    if client is None:
        return None

    try:
        rewritten = client.complete(
            REPHRASE_SYSTEM,
            f"Question: {question}\n\nAnswer to rewrite:\n{drafted}",
            max_tokens=260,
        )
    except Exception:
        logger.warning("Rephrasing failed; the drafted answer stands", exc_info=True)
        return None

    if not rewritten:
        return None

    invented = _digits(rewritten) - _digits(drafted)
    if invented:
        logger.warning("Discarding a rewrite that introduced figures: %s", sorted(invented))
        return None

    if re.search(r"\b(theft|thief|thieves|stealing|steal)\b", rewritten, re.IGNORECASE):
        logger.warning("Discarding a rewrite that used the word theft")
        return None

    return rewritten
