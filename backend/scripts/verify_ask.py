"""
Every question the briefing lists, asked and checked.

    python -m scripts.verify_ask

FR-2.16 asks for a documented list of what the interface supports and what it
does not. This is the executable half of that list: each of the briefing's own
example questions is asked, and the answer is checked for the thing that makes
it right rather than merely present.

Three properties are asserted, and the third is the one the whole design exists
for:

  ANSWERED     the question in the catalogue produces an answer from the data.
  CORRECT      the answer contains the figure the database actually holds, not
               a plausible one.
  DECLINED     a question outside the catalogue is refused in words, with no
               figure anywhere in the reply.
"""

from __future__ import annotations

import re
import sys

from sqlalchemy import func

from app.database import SessionLocal
from app.rag import engine, llm, queries
from app.models.loss import ZoneLossMonthly

passed = 0
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed
    if ok:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failures.append(f"{name}: {detail}")
        print(f"  FAIL  {name}  {detail}")


def has_no_figure(text: str) -> bool:
    """A refusal must not contain anything that could be read as a measurement."""
    return not re.search(r"\d", text)


def main() -> int:
    db = SessionLocal()
    try:
        print("=== The briefing's own example questions ===")
        expected_intent = {
            "How much did I lose last month?": "total_loss",
            "Which neighbourhood has the highest loss?": "worst_zone",
            "Why is Al-Wadi worse than Yassine?": "compare_zones",
            "How many hours did Hasan-4 run in July?": "generator_hours",
            "Which customers have not paid for three months?": "unpaid",
            "Show me customers whose consumption dropped more than 40%": "consumption_drop",
            "How much fuel did I burn per kWh this month compared to last month?": "fuel_per_kwh",
            "Is my loss getting better or worse?": "loss_trend",
        }
        for question, intent in expected_intent.items():
            answer = engine.ask(db, question, allow_model=False)
            check(f"{question[:52]:<54} -> {answer.intent}",
                  answer.answered and answer.intent == intent,
                  f"wanted {intent}")

        print("\n=== From the supervisor's voice note ===")
        for question, intent in {
            "How much did I invoice and collect this month?": "collections",
            "Which generator is unbalanced?": "phase_imbalance",
        }.items():
            answer = engine.ask(db, question, allow_model=False)
            check(f"{question[:52]:<54} -> {answer.intent}",
                  answer.answered and answer.intent == intent, f"wanted {intent}")

        print("\n=== The figures are the database's, not an invention ===")
        newest = db.query(func.max(ZoneLossMonthly.month)).scalar()
        delivered, billed = (
            db.query(
                func.sum(ZoneLossMonthly.energy_delivered_kwh),
                func.sum(ZoneLossMonthly.units_billed_kwh),
            )
            .filter(ZoneLossMonthly.month == newest)
            .one()
        )
        answer = engine.ask(db, "What is my loss this month?", allow_model=False)
        check("the delivered figure matches the table",
              f"{delivered:,.0f}" in answer.text, f"expected {delivered:,.0f} in: {answer.text[:120]}")
        check("the billed figure matches the table",
              f"{billed:,.0f}" in answer.text, f"expected {billed:,.0f}")
        check("the answer names the period it used", "2026" in answer.text, answer.text[:120])
        check("the facts behind the sentence are returned for inspection",
              bool(answer.facts) and "delivered_kwh" in answer.facts)
        check("the answer says which tables it read", answer.reads_from == ["zone_loss_monthly"],
              str(answer.reads_from))

        print("\n=== Definitions come from the documents, not the tables ===")
        for question, expect in [
            ("What is phase imbalance?", "neutral"),
            ("What does rollover mean?", "maximum reading"),
            ("What is a bypass?", "before the meter"),
        ]:
            answer = engine.ask(db, question, allow_model=False)
            check(f"{question[:40]:<42} -> documents",
                  answer.source == "documents" and expect in answer.text.lower(),
                  f"source={answer.source} text={answer.text[:90]}")

        print("\n=== A question outside the catalogue is refused, with no figure ===")
        for question in [
            "Who is the president of Lebanon?",
            "What will the price of diesel be next year?",
            "Can you predict next month's loss?",
            "Should I disconnect customer S00023?",
        ]:
            answer = engine.ask(db, question, allow_model=False)
            check(f"{question[:46]:<48} -> declined",
                  not answer.answered, f"answered with: {answer.text[:100]}")
            check(f"{question[:46]:<48} -> no figure in the refusal",
                  has_no_figure(answer.text), answer.text[:100])

        print("\n=== The word theft appears in no answer ===")
        offenders = []
        for question in list(expected_intent) + ["Which generator is unbalanced?"]:
            answer = engine.ask(db, question, allow_model=False)
            if "theft" in answer.text.lower() or "steal" in answer.text.lower():
                offenders.append(question)
        check("no answer uses the word theft or steal", not offenders, str(offenders))

        print("\n=== The catalogue is generated, so it cannot drift ===")
        catalogue = queries.catalogue()
        check(f"every intent is documented: {len(catalogue)} entries",
              len(catalogue) == len(queries.INTENTS))
        check("every entry names the tables it reads",
              all(c["readsFrom"] for c in catalogue),
              str([c["name"] for c in catalogue if not c["readsFrom"]]))
        check("every entry carries an example question",
              all(c["examples"] for c in catalogue))

        print("\n=== The language model, and the fence around it ===")
        print("    (exercised with a stub, so the guards are proven without a key)")

        class Stub(llm.Provider):
            """Answers with whatever the test needs it to answer."""
            name = "stub"
            def __init__(self, reply): self.reply = reply
            def complete(self, system, user, max_tokens=300): return self.reply

        check("with no key configured, nothing calls a model", not llm.available())

        # --- routing ------------------------------------------------------
        llm.set_provider(Stub('{"intent": "worst_zone"}'))
        check("a valid intent name is accepted",
              llm.choose_intent("which area should worry me", queries.catalogue()) == "worst_zone")

        llm.set_provider(Stub('{"intent": "delete_everything"}'))
        check("an intent the system does not have is discarded",
              llm.choose_intent("anything", queries.catalogue()) is None)

        llm.set_provider(Stub("I think you want the worst zone query!"))
        check("a reply that is not JSON is discarded",
              llm.choose_intent("anything", queries.catalogue()) is None)

        llm.set_provider(Stub('{"intent": null}'))
        check("the model is allowed to say none of them fits",
              llm.choose_intent("who won the match", queries.catalogue()) is None)

        # --- rephrasing ---------------------------------------------------
        draft = "In May 2026 you lost 9,338 kWh, which is 13.7% of what was delivered."

        llm.set_provider(Stub("You lost 9,338 kWh in May 2026, about 13.7% of everything sent out."))
        check("a faithful rewrite is used", llm.rephrase("q", draft) is not None)

        llm.set_provider(Stub("You lost 9,338 kWh in May, and about 42,000 kWh over the year."))
        check("a rewrite that invents a figure is discarded",
              llm.rephrase("q", draft) is None, "the 42,000 was not in the draft")

        llm.set_provider(Stub("You lost 9,338 kWh in May 2026, 13.7%, mostly to theft."))
        check("a rewrite that says theft is discarded", llm.rephrase("q", draft) is None)

        llm.set_provider(Stub(""))
        check("an empty reply leaves the drafted answer standing",
              llm.rephrase("q", draft) is None)

        class Broken(llm.Provider):
            def complete(self, system, user, max_tokens=300): raise RuntimeError("network down")
        llm.set_provider(Broken())
        check("a provider that fails does not break the answer",
              llm.rephrase("q", draft) is None and
              llm.choose_intent("q", queries.catalogue()) is None)

        # --- the whole path, end to end -----------------------------------
        llm.set_provider(Stub('{"intent": "worst_zone"}'))
        routed = engine.ask(db, "which part of town should I be worried about", allow_model=True)
        check("a question the patterns miss is routed by the model and answered",
              routed.answered and routed.intent == "worst_zone",
              f"intent={routed.intent} answered={routed.answered}")
        check("the answer still comes from the database, not the model",
              routed.source == "database" and bool(routed.facts))

        llm.set_provider(None)
        check("the stub is removed and the system is back to patterns only",
              not llm.available())

        print(f"\n  PASSED {passed}   FAILED {len(failures)}")
        for f in failures:
            print(f"   - {f}")
        return 1 if failures else 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
