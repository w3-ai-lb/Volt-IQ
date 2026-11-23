"""
Routing and answering (FR-2.11, FR-2.15).

HOW A QUESTION IS ANSWERED
--------------------------
1. Try every numeric intent. The first whose query returns facts wins, and the
   answer is written from those facts alone.
2. If no intent produced facts, look for a definition in the reference
   documents.
3. If neither, say so.

Step 3 is the one that matters. The briefing:

    "If the system cannot answer from the data, it must say 'I do not have that
     information', never a guess. An owner who catches one invented number will
     never trust the system again."

So there is no fallback that improvises. An unanswerable question returns the
sentence above, the list of what can be asked, and nothing that looks like a
figure.

WHERE A LANGUAGE MODEL FITS, AND WHERE IT DOES NOT
--------------------------------------------------
It does not compute, and it is not required for the system to work. Its two
jobs are to choose the intent when the patterns are ambiguous, and to rephrase
an answer more naturally. It is handed the facts and the sentence already
written from them; it never sees a request to add up kilowatt-hours.

With no API key configured the interface still answers every question in the
catalogue, because the sentence was written by the intent and not by the model.
That is not a degraded mode: it is the same numbers, in slightly stiffer prose.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.rag import documents, llm, queries

logger = logging.getLogger(__name__)

CANNOT_ANSWER = "I do not have that information."


@dataclass
class Answer:
    text: str
    # Every figure that appears in `text`, and the query that produced them.
    # NFR-5: a number on screen has to be traceable to a query result, and this
    # is what makes that checkable rather than merely asserted.
    facts: dict = field(default_factory=dict)
    intent: str | None = None
    source: str = "none"           # "database" | "documents" | "none"
    reads_from: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    answered: bool = True
    rephrased_by_model: bool = False


# A question in this shape is asking what a term MEANS, not what a quantity IS.
# Without this, "what is phase imbalance?" matched the numeric imbalance query
# and answered with June's figures for two generators, which is a correct
# number in reply to a question nobody asked.
DEFINITIONAL = re.compile(
    r"^\s*(what (is|are|does|do)\b(?!.*\b(my|our|the total|this month|last month)\b)"
    r"|what'?s\s+(a|an|the)?\s*\w"
    r"|define\b|meaning of\b|explain (what|the term)\b"
    r"|شو يعني|شو هي|شو هو|وين معنى)",
    re.IGNORECASE,
)

# The system measures what happened. It does not predict, and Project 3 has no
# forecasting requirement. A question about the future gets the honest answer
# rather than the nearest number that happens to match a keyword: before this
# guard, "what will the price of diesel be next year?" was answered with last
# month's litres per kWh.
ABOUT_THE_FUTURE = re.compile(
    r"\b(will be|will it|next (year|month|week)|predict|forecast|expect|going to be"
    r"|في المستقبل|السنة الجاي)\b",
    re.IGNORECASE,
)

CANNOT_PREDICT = (
    "I do not have that information. I report what the meters and the generators recorded; "
    "I do not predict. Ask me about a month that has already happened."
)

# NFR-2: a flag is a hypothesis for a field visit, never a verdict. The system
# cannot prove that anybody has taken anything, so it must not be drawn into
# advising that somebody be cut off, accused, or judged. Asked "should I
# disconnect S00023?" it previously returned the glossary definition of bypass,
# which reads uncomfortably like agreement.
ASKS_FOR_A_VERDICT = re.compile(
    r"\b(should i|shall i|do i|can i)\b.*\b(disconnect|cut off|remove|report|accuse|visit|charge)"
    r"|\b(is|are)\b.*\b(stealing|a thief|cheating|guilty|tampering)\b"
    r"|\bwho (is|are) (stealing|the thief|thieves)\b"
    r"|شو أعمل مع|اقطع",
    re.IGNORECASE,
)

NOT_A_VERDICT = (
    "I cannot answer that, and it is worth saying why rather than guessing. This system measures "
    "what was produced and what was billed, and explains the difference as far as the data allows. "
    "What is left over is unexplained consumption, which is a reason to send somebody to look, "
    "it is not proof that anyone has done anything. A sharp drop can be a bypass, and it can just "
    "as easily be a broken air conditioner, an empty house or a short circuit. Ask me which "
    "subscribers are worth visiting, and I will rank them; the decision about a person stays yours."
)


def _definition(question: str, min_score: float = 0.0) -> Answer | None:
    """
    A definition from the reference documents, or nothing.

    `min_score` is raised when this is reached as a LAST RESORT rather than
    because the question was asked in definitional form. A passage that merely
    shares a word with the question is not an answer to it: "should I
    disconnect S00023?" overlaps the glossary entry for bypass, and returning
    that reads like agreement with a decision the system must not make.
    """
    hits = documents.index().retrieve(question, k=2)
    hits = [h for h in hits if h.score >= min_score]
    if not hits:
        return None
    best = hits[0]
    return Answer(
        text=best.text.strip(),
        intent="definition",
        source="documents",
        citations=[h.citation for h in hits],
    )


def ask(db: Session, question: str, allow_model: bool = True) -> Answer:
    question = (question or "").strip()
    if not question:
        return Answer(text=CANNOT_ANSWER, answered=False)

    if ASKS_FOR_A_VERDICT.search(question):
        return Answer(text=NOT_A_VERDICT, answered=False)

    if ABOUT_THE_FUTURE.search(question):
        return Answer(text=CANNOT_PREDICT, answered=False)

    # A question about what a word means is answered from the documents, and
    # only falls through to the numbers if nothing there is relevant.
    if DEFINITIONAL.search(question):
        definition = _definition(question)
        if definition is not None:
            return definition

    candidates = queries.match(question)

    # The patterns only recognise the wordings somebody thought to write down.
    # When they recognise nothing, ask the model which of the KNOWN queries the
    # question is asking for. It chooses from a closed list and its answer is
    # validated against that list, so the worst case is the wrong one of eleven
    # correct queries, never an invented one.
    if not candidates and allow_model and llm.available():
        chosen = llm.choose_intent(question, queries.catalogue())
        if chosen:
            candidates = [i for i in queries.INTENTS if i.name == chosen]
            if candidates:
                logger.info("Routed by model: %r -> %s", question[:60], chosen)

    for intent in candidates:
        try:
            facts = intent.run(db, question)
        except Exception:
            logger.exception("Intent %s failed", intent.name)
            continue
        if not facts:
            continue

        drafted = intent.phrase(facts)
        answer = Answer(
            text=drafted,
            facts=facts,
            intent=intent.name,
            source="database",
            reads_from=intent.tables,
        )
        if allow_model:
            rewritten = llm.rephrase(question, drafted)
            if rewritten:
                answer.text = rewritten
                answer.rephrased_by_model = True
        return answer

    definition = _definition(question, min_score=0.30)
    if definition is not None:
        return definition

    return Answer(
        text=(
            f"{CANNOT_ANSWER} I can answer about loss per zone and per month, which zone is worst, "
            "how long a generator ran, fuel per kWh, whether loss is improving, who has not paid, "
            "whose consumption has fallen, collections, and phase imbalance. I can also explain "
            "the terms used in the reference documents."
        ),
        answered=False,
    )
