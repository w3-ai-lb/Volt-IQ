"""
Score the simple rules against the abnormal-behaviour labels.

    python -m scripts.score_rules --labels "path/to/subscriber_labels_for_intern.csv"

WHY THE PATH IS AN ARGUMENT AND NOT A CONSTANT
----------------------------------------------
The label file is not in the project and must not be. Anything inside the
project can be imported by something that builds a rule, and a detector tuned
on the labels it is later scored against reports a number that measures
nothing. Passing the path in makes the separation something you can see rather
than something you have to trust.

The rules in app/analytics/rules.py were written from the briefing's own list
and from the data, and this script was written afterwards. That order is the
only thing that makes the figures below mean anything, and it is worth stating
plainly in the report.

WHAT IS REPORTED, AND WHY IT IS NOT ONE NUMBER
----------------------------------------------
Precision and recall overall, then recall per category, then the categories no
rule can reach. A single headline figure hides the useful part: a detector that
finds every stuck meter and no bypass is a different tool from one that does the
reverse, and the owner needs to know which he has.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from app.analytics import rules
from app.database import SessionLocal

# Which label category each rule is trying to catch. Written down rather than
# inferred, because a rule that fires on the right subscriber for the wrong
# reason is luck, and luck does not survive a change of dataset.
RULE_TARGETS = {
    "disconnected_use": ["disconnected_use"],
    "stuck_meter": ["stuck_meter"],
    "reading_went_backwards": ["tamper"],
    "over_draw": ["over_draw"],
    "sustained_drop": ["bypass", "tamper"],
}

# Categories no rule in Phase 3 Step 1 attempts. Listed so the gap is a
# reported result rather than a silence.
NOT_ATTEMPTED = {
    "payment_default": "a collections matter, not an energy-loss one: the electricity was "
                       "delivered, measured and billed correctly",
    "collector_fraud": "money taken and not recorded. Needs the collector's own records "
                       "against the receipts, which are not in this dataset",
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
    anomalous = {s for s, types in truth.items() if types}

    db = SessionLocal()
    try:
        result = rules.run_all(db)
        defaulters = set(rules.payment_defaulters(db))
    finally:
        db.close()

    flagged = set(result["flaggedSubscribers"])
    total = len(truth)

    def score(predicted: set[str], actual: set[str]) -> tuple[int, int, int, float, float, float]:
        tp = len(predicted & actual)
        fp = len(predicted - actual)
        fn = len(actual - predicted)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        return tp, fp, fn, precision, recall, f1

    print("=" * 74)
    print("  THE SIMPLE-RULE BASELINE, MEASURED")
    print("=" * 74)
    print(f"  subscribers in the dataset      {total}")
    print(f"  labelled as abnormal            {len(anomalous)}")
    print(f"  flagged by the rules            {len(flagged)}")

    tp, fp, fn, precision, recall, f1 = score(flagged, anomalous)
    print(f"\n  correctly flagged (TP)          {tp}")
    print(f"  flagged but labelled normal(FP) {fp}")
    print(f"  abnormal and missed (FN)        {fn}")
    print(f"\n  PRECISION                       {precision:.1%}")
    print(f"  RECALL                          {recall:.1%}")
    print(f"  F1                              {f1:.2f}")

    print("\n" + "-" * 74)
    print("  RECALL PER CATEGORY  (what each rule was aiming at)")
    print("-" * 74)
    per_rule = {name: set(subs) for name, subs in result["perRule"].items()}
    for rule, targets in RULE_TARGETS.items():
        actual = {s for s, types in truth.items() if types & set(targets)}
        if not actual:
            continue
        t, f, m, p, r, _ = score(per_rule.get(rule, set()), actual)
        print(f"  {rule:<24} targets {'/'.join(targets):<18} "
              f"found {t:>2} of {len(actual):<3} recall {r:>5.0%}  precision {p:>5.0%}")

    print("\n" + "-" * 74)
    print("  CATEGORIES NO RULE ATTEMPTS")
    print("-" * 74)
    for category, why in NOT_ATTEMPTED.items():
        actual = {s for s, types in truth.items() if category in types}
        print(f"  {category:<20} {len(actual):>3} subscribers")
        print(f"  {'':<20} {why}")
    print("\n  Detected separately for completeness:")
    t, f, m, p, r, _ = score(defaulters, {s for s, types in truth.items() if "payment_default" in types})
    print(f"    payment defaulters by unpaid invoices: recall {r:.0%}, precision {p:.0%}")

    print("\n" + "-" * 74)
    print("  WHAT WAS MISSED, AND WHAT THAT MEANS")
    print("-" * 74)
    missed = anomalous - flagged
    breakdown: dict[str, int] = {}
    for s in missed:
        for kind in truth[s]:
            breakdown[kind] = breakdown.get(kind, 0) + 1
    for kind, n in sorted(breakdown.items(), key=lambda kv: -kv[1]):
        note = " (no rule attempts this)" if kind in NOT_ATTEMPTED else ""
        print(f"    {kind:<20} {n:>3}{note}")

    reachable = anomalous - {s for s, types in truth.items() if types <= set(NOT_ATTEMPTED)}
    t2, _f2, _m2, _p2, r2, _ = score(flagged, reachable)
    print(f"\n  Recall over the categories the rules ACTUALLY TARGET: {r2:.1%} "
          f"({t2} of {len(reachable)})")
    print("  That second figure is the fair bar for a model to beat. The first is the")
    print("  fair figure to report, because a category nobody attempted is still missed.")

    print("\n" + "-" * 74)
    print("  FINDINGS ABOUT THE GRID, WHICH NO SUBSCRIBER SCORE CAN HOLD")
    print("-" * 74)
    for g in result["gridFindings"]:
        print(f"    {g['generatorName']:<10} {g['rule']:<20} {g['evidence']}")
    if not result["gridFindings"]:
        print("    none")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
