# -*- coding: utf-8 -*-
"""
Put every question to EVERY subscriber, and look for the answers that break.

WHY ONE ACCOUNT IS NOT ENOUGH
-----------------------------
The answer sheet (scripts/chat_matrix.py) proves the assistant answers well for
one customer. It proves nothing about the other 299, and they are not alike: one
has never paid anything, one settled every bill, one has a single month of
history, one lives in a zone with four neighbours rather than thirty-five. Every
one of those is a different branch, and the branches that break do not raise:
they print "None", or "0.0%", or an empty month name, inside a fluent sentence.

So this asks all of them, in both languages, and reads every reply with a set of
rules that catch what a human eye would catch:

  * a None or a nan that reached the page as text
  * an unfilled placeholder, {like_this}
  * an English answer to an Arabic question, or the reverse
  * a reply so short it cannot be an answer
  * money written negative, which no bill and no balance ever is
  * punctuation left stranded by a missing value: " ,"  " ."  "()"

None of these is a crash, and that is the point. Every defect this assistant has
had was a sentence that read perfectly and said the wrong thing.

Run:  python -m scripts.chat_sweep [--limit N]
"""

from __future__ import annotations

import argparse
import re
import time
from datetime import date

from app.ai import chatbot
from app.database import SessionLocal, add_missing_columns
from app.models.customer import Customer
from scripts.chat_matrix import QUESTIONS

# Text that should never survive into an answer a customer reads.
FORBIDDEN = [
    ("None", re.compile(r"\bNone\b")),
    ("nan", re.compile(r"\bnan\b", re.IGNORECASE)),
    ("inf", re.compile(r"(?<![A-Za-z])inf(?![A-Za-z])", re.IGNORECASE)),
    ("unfilled placeholder", re.compile(r"\{[a-z_]+\}")),
    ("stranded punctuation", re.compile(r"\s[,.]\s|\(\)|\s{2,}")),
    ("negative amount", re.compile(r"-[\d,]+(\.\d+)? LBP")),
    ("empty month", re.compile(r"\bin\s+\d{4}\b|في\s+\d{4}\b")),
]

MIN_LENGTH = 40


def _suffix(labels: dict, customer: Customer) -> str:
    label = labels.get(customer.customer_id) or ""
    return " (%s)" % label if label else ""


def problems(question: str, reply: str) -> list[str]:
    found = []
    for name, pattern in FORBIDDEN:
        if pattern.search(reply):
            found.append(name)
    if len(reply.strip()) < MIN_LENGTH:
        found.append("reply too short")

    asked_arabic = chatbot._ARABIC_TEXT.search(question) is not None
    answered_arabic = chatbot._ARABIC_TEXT.search(reply) is not None
    if asked_arabic != answered_arabic:
        found.append("answered in the wrong language")
    return found


def edge_accounts(db) -> list[tuple[str, Customer]]:
    """
    The accounts the supplied data does not contain, built here so they can be
    asked the same questions.

    All 300 subscribers in the provider's export are alike in the ways that
    matter to this code: every one has eighteen billed months, a payment
    history, and a zone with at least twenty neighbours. So the sweep over them,
    however green, never reaches the branches written for an account that has
    none of that.

    Those branches are not hypothetical. The admin "Add Customer" form creates
    exactly this account: a real customer, registered today, with no readings,
    no invoice, no payment and no meter yet. On their first visit the assistant
    has to say so rather than divide by a month that does not exist.

    Nothing here is committed. The rows are flushed so the queries can see them
    and the transaction is rolled back by the caller, so the database is
    untouched.
    """
    from app.models.bill import Bill
    from app.models.invoice import Invoice
    from app.models.network import Zone
    from app.models.subscription import Subscriber, Subscription

    def customer(suffix: str, name: str) -> Customer:
        row = Customer(customer_id="SWEEP-%s" % suffix, name=name,
                       email="sweep.%s@example.com" % suffix.lower(),
                       role="customer", plan="Residential", status="Active",
                       region="Sweep")
        db.add(row)
        return row

    built: list[tuple[str, Customer]] = []

    # 1. Registered today. Nothing behind the account at all.
    built.append(("brand new, no data whatsoever", customer("NEW", "Rana Haddad")))

    # 2. One billed month, so there is no earlier month to compare against and
    #    every "up or down on last month" sentence has to be suppressed.
    one = customer("ONEMONTH", "Samir Aoun")
    sub = Subscriber(subscriber_id="SWEEPSUB1", zone_id=None,
                     subscriber_type="residential", customer_id=one.customer_id)
    db.add(sub)
    db.add(Subscription(subscription_id="SWEEPSCR1", subscriber_id=sub.subscriber_id,
                        ampere_capacity=5.0, phase_type="single_phase",
                        billing_model="metered", status="active"))
    db.add(Invoice(invoice_id="SWEEPINV1", subscription_id="SWEEPSCR1",
                   subscriber_id=sub.subscriber_id, zone_id=None,
                   billing_period=date(2026, 6, 1), units_consumed=120.0,
                   rate_applied=30981.0, fixed_charge=385000.0,
                   variable_charge=3717720.0, total_amount=4102720.0))
    # The matching bill, because in the real system invoices and bills come in
    # pairs: app/pipeline/portal.py writes a BILL-INV row for every invoice. An
    # invoice with no bill is a state the product cannot reach, and a fixture
    # that reaches it tests something that will never happen.
    db.add(Bill(bill_id="SWEEPBILL2", customer_id=one.customer_id,
                month="2026-06", amount=4102720.0,
                due_date=date(2026, 6, 30), status="Pending"))
    built.append(("one billed month, nothing to compare", one))

    # 3. Billed and never paid a thing, which is where "your last payment"
    #    has to leave the sentence out rather than print a zero.
    unpaid = customer("NEVERPAID", "Layla Chami")
    db.add(Bill(bill_id="SWEEPBILL1", customer_id=unpaid.customer_id,
                month="2026-06", amount=4102720.0,
                due_date=date(2026, 6, 30), status="Pending"))
    built.append(("billed, never paid anything", unpaid))

    # 4. A new connection on an EXISTING feeder: the zone is real, so it has
    #    supply hours and neighbours to compare against, but this subscriber has
    #    no invoice of their own yet. Half the context is present and half is
    #    missing, which is the combination most likely to produce a sentence
    #    built from one and divided by the other.
    zone_id = db.query(Zone.zone_id).order_by(Zone.zone_id).limit(1).scalar()
    joined = customer("NEWZONE", "Karim Sfeir")
    db.add(Subscriber(subscriber_id="SWEEPSUB2", zone_id=zone_id,
                      subscriber_type="residential", customer_id=joined.customer_id))
    db.add(Subscription(subscription_id="SWEEPSCR2", subscriber_id="SWEEPSUB2",
                        zone_id=zone_id, ampere_capacity=10.0,
                        phase_type="single_phase", billing_model="metered",
                        status="active"))
    built.append(("new connection in a live zone, not yet billed", joined))

    db.flush()
    return built


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0,
                        help="only sweep the first N customers (default: all)")
    parser.add_argument("--no-edges", action="store_true",
                        help="skip the constructed empty and new accounts")
    args = parser.parse_args()

    # Whole customer records are read below: first add any column this version
    # of the code expects, as the server does when it starts (app/database.py).
    add_missing_columns()
    db = SessionLocal()
    try:
        customers = db.query(Customer).filter(Customer.role == "customer").order_by(
            Customer.customer_id
        ).all()
        if args.limit:
            customers = customers[: args.limit]
        if not customers:
            print("No customers in this database. Run load-data.bat first.")
            return 1

        labels = {c.customer_id: "" for c in customers}
        if not args.no_edges:
            for label, extra in edge_accounts(db):
                customers.append(extra)
                labels[extra.customer_id] = label

        pairs = [(q_en, q_ar) for _, q_en, q_ar, _ in QUESTIONS]
        total = len(customers) * len(pairs) * 2
        print("Sweeping %d customers x %d questions x 2 languages = %d replies"
              % (len(customers), len(pairs), total))
        print()

        started = time.time()
        failures: list[str] = []
        crashes: list[str] = []
        checked = 0

        for index, customer in enumerate(customers, 1):
            for q_en, q_ar in pairs:
                for question in (q_en, q_ar):
                    try:
                        reply = chatbot.answer(db, customer, question)
                    except Exception as exc:                       # noqa: BLE001
                        crashes.append("%s%s | %s | %s: %s"
                                       % (customer.customer_id,
                                          _suffix(labels, customer), question,
                                          type(exc).__name__, exc))
                        continue
                    checked += 1
                    for problem in problems(question, reply):
                        failures.append("%s%s | %s | %s\n      %s"
                                        % (customer.customer_id,
                                           _suffix(labels, customer), problem,
                                           question, reply[:200]))
            if index % 25 == 0:
                print("  %3d/%d customers, %.0f s elapsed"
                      % (index, len(customers), time.time() - started))

        print()
        print("=" * 72)
        print("%d replies read in %.0f seconds" % (checked, time.time() - started))
        print("%d crashed, %d had a problem in the text"
              % (len(crashes), len(failures)))
        print("=" * 72)

        for line in crashes[:40]:
            print("  CRASH   %s" % line)
        for line in failures[:60]:
            print("  PROBLEM %s" % line)
        if len(failures) > 60:
            print("  ... and %d more" % (len(failures) - 60))

        if not crashes and not failures:
            print()
            print("  Every customer got a usable answer to every question, in the")
            print("  language it was asked in.")
        return 1 if (crashes or failures) else 0
    finally:
        # The constructed accounts were flushed, never committed. This is what
        # takes them away again, and it runs even if the sweep raised.
        db.rollback()
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
