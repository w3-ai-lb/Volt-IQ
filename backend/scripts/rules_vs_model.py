"""
The comparison the briefing asks for: do the simple rules beat the model?

    python -m scripts.rules_vs_model --labels "path/to/subscriber_labels_for_intern.csv"

    "The rule: the AI must beat the simple rules. If the rules catch 60% and
     the model catches 55%, the rules win. Reporting that honestly is a good
     result, not a failure."

Both methods are given the same number of flags, because an owner has a fixed
number of afternoons and the honest question is which shortlist is better, not
which one is longer.

The labels are read here and nowhere else. The rules were written from the
briefing and the data; the model is unsupervised and never sees a label at all.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from app.ai import subscriber_anomaly
from app.analytics import rules
from app.database import SessionLocal

# The categories the rules attempt. The model is judged on the same ones, so
# neither is credited with a category its opponent was not allowed to enter.
COMPARABLE = {"disconnected_use", "stuck_meter", "bypass", "tamper", "over_draw"}


def score(predicted: set[str], actual: set[str]) -> dict:
    tp = len(predicted & actual)
    fp = len(predicted - actual)
    fn = len(actual - predicted)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": precision, "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", type=Path, required=True)
    args = parser.parse_args()
    if not args.labels.is_file():
        print(f"No label file at {args.labels}")
        return 1

    labels = pd.read_csv(args.labels)
    labels["anomaly_types"] = labels.anomaly_types.fillna("")
    truth = {
        str(r.subscriber_id): set(filter(None, str(r.anomaly_types).split("|")))
        for r in labels.itertuples()
    }
    comparable = {s for s, types in truth.items() if types & COMPARABLE}

    db = SessionLocal()
    try:
        rule_result = rules.run_all(db)
        rule_flags = set(rule_result["flaggedSubscribers"])
        budget = len(rule_flags)

        ranked = subscriber_anomaly.detect(db, budget=budget)
        model_flags = set(ranked[ranked.flagged].subscriber_id)
    finally:
        db.close()

    print("=" * 74)
    print("  SIMPLE RULES  vs  ISOLATION FOREST")
    print("=" * 74)
    print(f"  Both given the same budget: {budget} subscribers to flag, out of {len(truth)}.")
    print(f"  Judged on the categories the rules attempt: {', '.join(sorted(COMPARABLE))}")
    print(f"  Subscribers in those categories: {len(comparable)}\n")

    r = score(rule_flags, comparable)
    m = score(model_flags, comparable)

    print(f"  {'':<22}{'RULES':>12}{'MODEL':>12}")
    print("  " + "-" * 46)
    for label, key, fmt in [
        ("correctly flagged", "tp", "{:>12}"),
        ("false alarms", "fp", "{:>12}"),
        ("missed", "fn", "{:>12}"),
        ("precision", "precision", "{:>11.1%}"),
        ("recall", "recall", "{:>11.1%}"),
        ("F1", "f1", "{:>12.2f}"),
    ]:
        print(f"  {label:<22}" + fmt.format(r[key]) + fmt.format(m[key]))

    print("\n  " + "-" * 46)
    if m["recall"] > r["recall"] and m["precision"] >= r["precision"] * 0.9:
        verdict = "THE MODEL WINS. It earns its place."
    elif abs(m["recall"] - r["recall"]) < 0.03:
        verdict = "A TIE. The rules win by default: they are explainable and free to run."
    else:
        verdict = "THE RULES WIN. The model does not earn its place on this data."
    print(f"  {verdict}")

    overlap = rule_flags & model_flags
    print(f"\n  Both methods flagged {len(overlap)} of the same subscribers.")
    print(f"  The rules alone found {len(rule_flags - model_flags)}; the model alone "
          f"found {len(model_flags - rule_flags)}.")
    only_model_right = (model_flags - rule_flags) & comparable
    if only_model_right:
        print(f"  Of the model's own finds, {len(only_model_right)} are labelled abnormal: "
              f"{', '.join(sorted(only_model_right)[:6])}")
        print("  Those are worth reading: they are what a model can see and a threshold cannot.")

    print("\n" + "-" * 74)
    print("  WHY THE MODEL FLAGGED ITS TOP FIVE")
    print("-" * 74)
    top = ranked[ranked.flagged].head(5)
    for row in top.itertuples():
        mark = "labelled abnormal" if truth.get(row.subscriber_id) else "labelled normal"
        print(f"  {row.subscriber_id}  score {row.anomaly_score:.3f}  ({mark})")
        print(f"      {subscriber_anomaly.explain(pd.Series(row._asdict()), ranked)}")

    print("\n" + "-" * 74)
    print("  AND IF YOU USE BOTH")
    print("-" * 74)
    union = score(rule_flags | model_flags, comparable)
    print(f"  Together they flag {len(rule_flags | model_flags)} subscribers, not {budget}, so this")
    print("  is not the same comparison: it buys recall with more visits.")
    print(f"    recall    {r['recall']:.1%} -> {union['recall']:.1%}")
    print(f"    precision {r['precision']:.1%} -> {union['precision']:.1%}")
    extra_visits = len(rule_flags | model_flags) - budget
    extra_found = union["tp"] - r["tp"]
    if extra_found > 0:
        print(f"    {extra_visits} extra visits to find {extra_found} more real cases, "
              f"one in {extra_visits / extra_found:.1f}.")
    print("  Whether that trade is worth making is the owner's decision, not the")
    print("  system's. Both figures belong in front of him.")

    print("\n" + "-" * 74)
    print("  HOW TO READ THIS")
    print("-" * 74)
    print("  The model never saw a label: IsolationForest is unsupervised, so it")
    print("  could not have been fitted to the answers it is scored against.")
    print("  The rules were written from the briefing and the data before any")
    print("  score existed. Whichever wins, the comparison is honest.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
