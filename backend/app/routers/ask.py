"""
The owner asks a question in ordinary language (FR-2.11 to FR-2.16).

    POST /ishtirak/ask          {"question": "How much did I lose last month?"}
    GET  /ishtirak/ask/catalogue    what can and cannot be asked

WHAT COMES BACK, AND WHY IT IS SHAPED THIS WAY
----------------------------------------------
The answer is not only prose. It carries `facts`, the query result the sentence
was written from, and `readsFrom`, the tables that produced it. That is what
turns the briefing's rule from an instruction into something checkable: anyone
can compare the sentence against the figures beside it and against the table
named, without trusting the wording.

`answered` is false when the question is outside what the system can support.
That is a normal reply, not an error, and it is deliberately as easy to render
as an answer: the interface should show a refusal as plainly as it shows a
number.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import require_admin
from app.database import get_db
from app.models.customer import Customer
from app.rag import engine, queries
from app.schemas.common import CamelModel

router = APIRouter(prefix="/ishtirak/ask", tags=["Ishtirak"])


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class AnswerOut(CamelModel):
    question: str
    answer: str
    answered: bool
    source: str               # database | documents | none
    intent: str | None = None
    facts: dict = {}
    reads_from: list[str] = []
    citations: list[str] = []
    rephrased_by_model: bool = False


@router.post("", response_model=AnswerOut)
def ask(
    payload: Question,
    db: Session = Depends(get_db),
    _: Customer = Depends(require_admin),
):
    result = engine.ask(db, payload.question)
    return AnswerOut(
        question=payload.question,
        answer=result.text,
        answered=result.answered,
        source=result.source,
        intent=result.intent,
        facts=result.facts,
        reads_from=result.reads_from,
        citations=result.citations,
        rephrased_by_model=result.rephrased_by_model,
    )


@router.get("/catalogue")
def catalogue(_: Customer = Depends(require_admin)):
    """
    FR-2.16: what is supported, and what is not.

    Generated from the intent registry, so it cannot advertise something that
    does not work or hide something that does.
    """
    return {
        "supported": queries.catalogue(),
        "notSupported": [
            {
                "kind": "predictions",
                "reason": "The system reports what was measured. Forecasting is not part of "
                          "this project's requirements.",
            },
            {
                "kind": "verdicts about a person",
                "reason": "Unexplained consumption is a reason to visit, not proof of anything. "
                          "The system ranks who is worth visiting; the decision stays with the "
                          "owner.",
            },
            {
                "kind": "anything outside the loaded data",
                "reason": "Every figure comes from a query. A question the tables cannot answer "
                          "is refused rather than guessed.",
            },
        ],
    }
