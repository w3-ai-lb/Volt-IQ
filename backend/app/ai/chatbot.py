"""
AI Module, Customer Support Chatbot.

Handles the four responsibilities listed in Section V-v of the Software
Architecture: billing questions, payment assistance, consumption questions
and FAQs.

Design: the customer's real account context (current bill, balance, recent
usage, savings score) is assembled first, then either
  * sent to the LLM as a grounded system prompt (when OPENAI_API_KEY is set), or
  * answered by the built-in intent engine (default).

The fallback matters, it means the chatbot works during the demo with no API
key and no billing account, and the answers are still drawn from real data.

TWO THINGS THIS MODULE LEARNED THE HARD WAY
-------------------------------------------
It was asked twenty-two questions a real subscriber might ask, and the answers
were graded against the database rather than against how fluent they sounded.

ARABIC. The interface ships in Arabic with a right-to-left layout, the
customers are in Lebanon, and every Arabic question fell through to the English
catch-all, because the keyword table held English words only. A subscriber who
asks "شو رصيدي؟" and is told in English that the assistant can help with
billing questions has been answered by a wall. Arabic is matched here, and
answered in Arabic.

FOUR QUESTIONS THAT HAD ANSWERS AND DID NOT GET THEM. "What is the price per
kWh?" was answered with the bill total; the rate is in the `tariffs` table and
moves every month. "How many hours of electricity do I get?" was answered with
peak-hour advice; the supply hours are measured in `supply_sessions`. "What is
my customer number?" and "What is my address on file?" fell through to the
catch-all while sitting in the customer's own row.

And where there is genuinely no answer, a discount, a fault report, a contract
change, the reply now says so and names who can, in the manner of the `solar`
reply, rather than offering a menu of four things the person did not ask about.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.ai import peak_advice
from app.analytics import owed
from app.config import settings
from app.core import chatbot_config
from app.core.i18n import isolate_figures
from app.core.money import money
from app.models.bill import Bill
from app.models.consumption import Consumption
from app.models.customer import Customer
from app.models.invoice import Invoice, Tariff
from app.models.network import SupplySession, Zone
from app.models.payment import Payment
from app.models.subscription import Meter, MeterReading, Subscriber, Subscription

logger = logging.getLogger(__name__)

MONTH_NAMES = ["January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December"]

# Levantine month names, which is what a bill in Lebanon is read with. The
# Gulf/Egyptian set (يناير، فبراير) would be understood but reads foreign here.
# Western digits for the year, for the reason given at the top of i18n/arabic.ts:
# Lebanon writes 2026, not ٢٠٢٦, including on utility bills.
ARABIC_MONTHS = ["كانون الثاني", "شباط", "آذار", "نيسان", "أيار", "حزيران",
                 "تموز", "آب", "أيلول", "تشرين الأول", "تشرين الثاني", "كانون الأول"]


# ---------------------------------------------------------------------------
# Language
# ---------------------------------------------------------------------------
# The Arabic block, and the letters within it that a keyword can be built from.
_ARABIC_TEXT = re.compile(r"[؀-ۿ]")
_LATIN_TEXT = re.compile(r"[A-Za-z]")

# Short vowels, sukun, dagger alif and the kashida stretch character. All of
# them are optional in ordinary writing, so a keyword must not depend on them.
_DIACRITICS = re.compile(r"[ً-ْٰـ]")

# Letters that the same word is spelled with either way. A customer typing on a
# phone writes فاتوره as often as فاتورة, and أنا as often as انا, and neither
# is a mistake worth failing to understand.
_EQUIVALENT_LETTERS = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ى": "ي", "ئ": "ي",
    "ة": "ه",
    "ؤ": "و",
})


def _normalise(text: str) -> str:
    """Fold away the spelling choices that carry no meaning."""
    return _DIACRITICS.sub("", text.lower()).translate(_EQUIVALENT_LETTERS)


def _language_of(message: str, customer: Customer) -> str:
    """
    Which language to answer in.

    The language the person WROTE IN wins over the language their interface is
    set to: someone browsing in Arabic who types an English question is asking
    in English, and an Arabic keyboard is not always to hand.

    A message with no letters at all, "؟", an amount, an emoji, carries no
    signal, and then the account's own setting is the best guess available.
    """
    if _ARABIC_TEXT.search(message):
        return "ar"
    if _LATIN_TEXT.search(message):
        return "en"
    return "ar" if (customer.language or "").startswith("ar") else "en"


def _pick(lang: str, english: str, arabic: str) -> str:
    """
    Choose the reply for this language, with both versions written side by side.

    Deliberately not two separate reply functions. A fix applied to the English
    answer and forgotten in the Arabic one is a silent divergence, and the pair
    being one expression apart is what stops that.
    """
    return arabic if lang == "ar" else english


def _month_label(when: date | None, lang: str) -> str:
    if when is None:
        return ""
    names = ARABIC_MONTHS if lang == "ar" else MONTH_NAMES
    return f"{names[when.month - 1]} {when.year}"


def _date_label(when: date | None, lang: str) -> str:
    if when is None:
        return ""
    names = ARABIC_MONTHS if lang == "ar" else MONTH_NAMES
    return f"{when.day} {names[when.month - 1]} {when.year}"


def _month_name(number: int, lang: str) -> str:
    names = ARABIC_MONTHS if lang == "ar" else MONTH_NAMES
    return names[number - 1]


def _kwh(value: float | None, lang: str) -> str:
    """A kWh figure. The unit is written the same in both, as in the interface."""
    return f"{float(value or 0.0):,.1f} kWh"


# ---------------------------------------------------------------------------
# A month the customer names
# ---------------------------------------------------------------------------
# "كم كانت فاتورتي لشهر شباط؟" was answered with the June bill.
#
# Not with an error, and not with "I don't have that": with a complete, fluent,
# confident answer about a different month, decorated with the right arithmetic
# and the right rate. February 2026 is on that account, 21,462,468 LBP, and the
# reply named June because the reply had only ever known how to read the newest
# invoice. This is the fault the whole project keeps meeting: a number computed
# correctly from the wrong window and shown with complete confidence.
#
# So a month named in the question is now read out of it, and the answer is
# about that month or says plainly that there is no bill for it. Both month
# sets are accepted: Levantine, which is what a bill is read with here, and the
# Gulf/Egyptian set, which a phone keyboard's autocomplete will offer.
_GULF_MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
                "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]

_MONTH_WORDS: dict[str, int] = {}
for _index, _name in enumerate(MONTH_NAMES, start=1):
    _MONTH_WORDS[_name.lower()] = _index
    _MONTH_WORDS[_name.lower()[:3]] = _index
for _index, _name in enumerate(ARABIC_MONTHS + _GULF_MONTHS, start=1):
    _MONTH_WORDS[_normalise(_name)] = (_index - 1) % 12 + 1

# Longest first, so "تشرين الأول" is never read as something shorter inside it.
_MONTH_WORDS_BY_LENGTH = sorted(_MONTH_WORDS, key=len, reverse=True)

_ARABIC_LETTER = r"[ء-ي]"

# "May I pay next week?" names no month. The other eleven are not also English
# words, so this is the only one that needs the guard.
_MODAL_MAY = re.compile(r"(?<!\w)may(?!\w)\s+(i|we|you|he|she|they|it|be)(?!\w)")


def _named_month(message: str) -> tuple[int, int | None] | None:
    """
    The month, and the year if one was given, that this question is about.

    Returns None when no month is named, which is the ordinary case and leaves
    every answer exactly as it was.
    """
    text = _normalise(message)
    if _MODAL_MAY.search(text):
        text = _MODAL_MAY.sub(" ", text)

    for word in _MONTH_WORDS_BY_LENGTH:
        if _ARABIC_TEXT.search(word):
            # Arabic joins its prepositions to the word, so no left boundary of
            # the English kind exists. A letter on either side is the test:
            # آب is August standing alone and is a fragment inside الحساب.
            pattern = rf"(?<!{_ARABIC_LETTER}){re.escape(word)}(?!{_ARABIC_LETTER})"
        else:
            pattern = rf"(?<!\w){re.escape(word)}(?!\w)"
        if re.search(pattern, text):
            year = re.search(r"(?<!\d)(20\d{2})(?!\d)", text)
            return _MONTH_WORDS[word], int(year.group(1)) if year else None
    return None


# ---------------------------------------------------------------------------
# Context assembly
# ---------------------------------------------------------------------------
def _monthly_series(db: Session, customer_id: str) -> list[tuple[date, float]]:
    """
    This customer's consumption totalled by calendar month, oldest first.

    MONTHS, AND ANCHORED ON THE READING, NOT ON TODAY
    -------------------------------------------------
    Two faults lived in the thirty-day windows this replaces, and both showed
    up in the same sentence.

    The window was measured back from the wall clock. The provider's meters are
    read by hand and the data in hand ends in June, so "the last 30 days" fell
    in a gap and returned zero, and the chatbot then told a customer with
    eighteen months of history that it had no readings for his account at all.

    And thirty days is the wrong unit regardless. A meter read once a month
    puts one reading in a thirty-day window, so a window that happens to
    straddle two reading dates catches two months or none. The provider bills
    by the month; the answer is given by the month.
    """
    rows = (
        db.query(Consumption.timestamp, Consumption.kwh)
        .filter(Consumption.customer_id == customer_id)
        .all()
    )
    months: dict[tuple[int, int], float] = {}
    for moment, kwh in rows:
        if moment is None:
            continue
        key = (moment.year, moment.month)
        months[key] = months.get(key, 0.0) + float(kwh or 0.0)

    return [(date(year, month, 1), total) for (year, month), total in sorted(months.items())]


def build_customer_context(db: Session, customer: Customer) -> dict:
    """Gather the account facts the assistant is allowed to reason about."""
    # The NEWEST unpaid bill, not the oldest. Ordering ascending and taking the
    # first returns the earliest debt on the account, so a customer who has
    # fallen behind was told his "current bill" was one from a year ago.
    current_bill = (
        db.query(Bill)
        .filter(Bill.customer_id == customer.customer_id, Bill.status != "Paid")
        .order_by(Bill.due_date.desc())
        .first()
    )
    # And the newest bill whatever its status, which is a different row and a
    # different question. "Why was my bill like this this month?" is about the
    # bill that was issued; whether it has been paid is a separate fact, and an
    # account that owes nothing still has a most recent bill to explain.
    latest_bill = (
        db.query(Bill)
        .filter(Bill.customer_id == customer.customer_id)
        .order_by(Bill.due_date.desc())
        .first()
    )
    last_payment = (
        db.query(Payment)
        .filter(Payment.customer_id == customer.customer_id)
        .order_by(Payment.date.desc())
        .first()
    )

    series = _monthly_series(db, customer.customer_id)
    latest_month = series[-1][0] if series else None
    latest_kwh = series[-1][1] if series else 0.0
    previous_kwh = series[-2][1] if len(series) > 1 else 0.0
    change_pct = ((latest_kwh - previous_kwh) / previous_kwh * 100) if previous_kwh > 0 else 0.0

    return {
        "name": customer.name,
        "plan": customer.plan,
        "region": customer.region,
        # Computed from the bills and payments, not read from the stored
        # `customers.balance` column. The column is a snapshot written when the
        # identities are generated, so it is stale the moment a payment is
        # recorded, and the assistant is the one screen a customer asks after
        # paying. Same function as every other balance in the product.
        "balance": owed.outstanding_for(db, customer.customer_id),
        "current_bill_amount": float(current_bill.amount) if current_bill else 0.0,
        # Kept as a date as well as a sentence, because the sentence has to be
        # written in the language the customer asked in, and "15 August 2026"
        # cannot be turned back into a date once it is a string.
        "current_bill_due_date": current_bill.due_date if current_bill else None,
        "current_bill_due": current_bill.due_date.strftime("%d %B %Y") if current_bill else None,
        "current_bill_status": current_bill.status if current_bill else "No outstanding bill",
        "latest_bill_amount": float(latest_bill.amount) if latest_bill else 0.0,
        "latest_bill_due_date": latest_bill.due_date if latest_bill else None,
        "latest_bill_status": latest_bill.status if latest_bill else None,
        # has_last_payment lets the replies leave the sentence out entirely
        # rather than printing "0 LBP ... on None" for an account that has
        # never paid anything.
        "has_last_payment": last_payment is not None,
        "last_payment_amount": float(last_payment.amount) if last_payment else 0.0,
        "last_payment_on": last_payment.date if last_payment else None,
        "last_payment_date": last_payment.date.strftime("%d %B %Y") if last_payment else None,
        # The customer's own most recent BILLED MONTH, named, so the reply can
        # say which month it is talking about instead of implying "right now".
        "latest_period": _month_label(latest_month, "en") or None,
        "latest_period_month": latest_month,
        "latest_period_kwh": round(latest_kwh, 1),
        "previous_period_kwh": round(previous_kwh, 1),
        "change_pct": round(change_pct, 1),
        # Oldest first, for the month-by-month answer. Trimmed to a year so the
        # context handed to the LLM does not grow without limit.
        "monthly_series": series[-12:],
    }


def build_service_context(db: Session, customer: Customer) -> dict:
    """
    The facts about the SUPPLY rather than the account: which zone, which
    generator, which meter, which contract, which rate, and how the last
    invoice was arrived at.

    All of it optional. The platform runs against databases that hold only the
    customer-side tables, the test suite builds one, and a chatbot that
    raises AttributeError because a subscriber row is missing is worse than one
    that says it does not have that on file.
    """
    facts: dict = {
        "customer_id": customer.customer_id,
        "email": customer.email,
        "phone": customer.phone,
        "address": customer.address,
        "status": customer.status,
    }

    # The published rate is a fact about the business, not about the person, so
    # it is read before anything that depends on finding their subscriber row.
    # Somebody whose meter has not been linked yet can still be told what a
    # kilowatt-hour costs this month.
    tariff = db.query(Tariff).order_by(Tariff.effective_month.desc()).first()
    if tariff is not None:
        facts["tariff_month"] = tariff.effective_month
        facts["tariff_base_rate"] = tariff.rate_per_kwh_base
        facts["tariff_highland_rate"] = tariff.rate_per_kwh_highland
        facts["tariff_diesel_price"] = tariff.diesel_price_per_20l

    subscriber = (
        db.query(Subscriber)
        .filter(Subscriber.customer_id == customer.customer_id)
        .first()
    )
    if subscriber is None:
        return facts

    facts["subscriber_id"] = subscriber.subscriber_id
    facts["subscriber_type"] = subscriber.subscriber_type

    zone = db.get(Zone, subscriber.zone_id) if subscriber.zone_id else None
    if zone is not None:
        facts["zone_id"] = zone.zone_id
        facts["zone_name"] = zone.name
        facts["zone_area_type"] = zone.area_type
        facts["zone_altitude_band"] = zone.altitude_band
        facts["generator_id"] = zone.generator_id

        supply = (
            db.query(SupplySession)
            .filter(SupplySession.zone_id == zone.zone_id)
            .order_by(SupplySession.total_days.desc())
            .first()
        )
        if supply is not None and supply.avg_supply_hours:
            facts["supply_hours_per_day"] = round(float(supply.avg_supply_hours), 1)
            facts["supply_days_on_record"] = int(supply.total_days or 0)
            facts["supply_generator_id"] = supply.generator_id

    subscription = (
        db.query(Subscription)
        .filter(Subscription.subscriber_id == subscriber.subscriber_id)
        .first()
    )
    if subscription is not None:
        facts["subscription_id"] = subscription.subscription_id
        facts["ampere_capacity"] = subscription.ampere_capacity
        facts["phase_type"] = subscription.phase_type
        facts["billing_model"] = subscription.billing_model
        facts["contract_status"] = subscription.status

        meter = (
            db.query(Meter)
            .filter(Meter.subscription_id == subscription.subscription_id)
            .first()
        )
        if meter is not None:
            facts["meter_id"] = meter.meter_id
            facts["meter_serial"] = meter.serial_number
            facts["meter_type"] = meter.meter_type

        reading = (
            db.query(MeterReading)
            .filter(MeterReading.subscription_id == subscription.subscription_id)
            .order_by(MeterReading.billing_period.desc())
            .first()
        )
        if reading is not None:
            facts["last_reading_date"] = reading.reading_date or reading.billing_period
            facts["last_reading_period"] = reading.billing_period
            facts["last_reading_value"] = reading.reading_value
            facts["last_reading_method"] = reading.capture_method

    # TWO invoices, not one. A bill moves for exactly two reasons, the number of
    # kilowatt-hours or the price of one, and neither can be seen without the
    # month before to compare against. Both are on these two rows.
    recent = (
        db.query(Invoice)
        .filter(Invoice.subscriber_id == subscriber.subscriber_id)
        .order_by(Invoice.billing_period.desc())
        .limit(2)
        .all()
    )
    invoice = recent[0] if recent else None
    if len(recent) > 1:
        earlier = recent[1]
        facts["previous_invoice_period"] = earlier.billing_period
        facts["previous_invoice_units"] = earlier.units_consumed
        facts["previous_invoice_rate"] = earlier.rate_applied
        facts["previous_invoice_total"] = earlier.total_amount

    if invoice is not None:
        facts["invoice_id"] = invoice.invoice_id
        facts["invoice_period"] = invoice.billing_period
        facts["invoice_units"] = invoice.units_consumed
        # The rate the customer was ACTUALLY charged, off their own invoice.
        #
        # Not derived from the zone's altitude band, which is the obvious way to
        # do it and is wrong here: zone Z08 is recorded below 700 m and all 360
        # of its invoices bill at the highland rate, a discrepancy worth
        # 305,633,019 LBP that is the provider's to explain. Answering "your
        # rate is the base rate" from the band would contradict the invoice in
        # the customer's hand.
        facts["invoice_rate"] = invoice.rate_applied
        facts["invoice_fixed_charge"] = invoice.fixed_charge
        facts["invoice_variable_charge"] = invoice.variable_charge
        facts["invoice_total"] = invoice.total_amount

        if invoice.zone_id:
            average, count = (
                db.query(func.avg(Invoice.units_consumed), func.count(Invoice.invoice_id))
                .filter(
                    Invoice.zone_id == invoice.zone_id,
                    Invoice.billing_period == invoice.billing_period,
                )
                .one()
            )
            if count:
                facts["zone_average_kwh"] = round(float(average or 0.0), 1)
                facts["zone_invoice_count"] = int(count)

    # How far the rate has travelled, measured across THIS CUSTOMER'S OWN
    # invoices rather than across the tariff table.
    #
    # The table holds two rates a month, a base and a highland one, and quoting
    # the base range to somebody billed at the highland rate produces a sentence
    # where the rate they were just told they paid sits outside the range they
    # were just told it moves within. Their own invoices carry the rate that was
    # actually applied to them, month after month, and cannot disagree with the
    # bill in their hand.
    lowest, highest, months = (
        db.query(
            func.min(Invoice.rate_applied),
            func.max(Invoice.rate_applied),
            func.count(Invoice.invoice_id),
        )
        .filter(Invoice.subscriber_id == subscriber.subscriber_id,
                Invoice.rate_applied.isnot(None))
        .one()
    )
    if lowest and highest and months:
        facts["rate_lowest_charged"] = round(float(lowest))
        facts["rate_highest_charged"] = round(float(highest))
        facts["rate_months_on_record"] = int(months)

    return facts


def scope_to_month(
    db: Session,
    customer: Customer,
    ctx: dict,
    month: int,
    year: int | None,
) -> dict:
    """
    Re-point the context at the month the question named.

    Everything the billing and consumption answers read — the invoice, the
    month before it to compare against, the bill's status, the payment that
    settled it, the kilowatt-hours — is replaced with that month's. The answers
    themselves then need to know only two things: that a month was asked for,
    and whether it exists.

    A year is optional and usually absent. "شهر شباط" with eighteen months on
    file means the most recent February, which is what a person means.
    """
    overrides: dict = {"asked_month_number": month, "asked_month_year": year,
                       "asked_month_found": False}

    invoices: list[Invoice] = []
    if ctx.get("subscriber_id"):
        invoices = (
            db.query(Invoice)
            .filter(Invoice.subscriber_id == ctx["subscriber_id"])
            .order_by(Invoice.billing_period.desc())
            .all()
        )
    bills = (
        db.query(Bill)
        .filter(Bill.customer_id == customer.customer_id)
        .order_by(Bill.due_date.desc())
        .all()
    )

    # What the account actually holds, for the reply that has to say so.
    periods = [i.billing_period for i in invoices] or [b.due_date for b in bills]
    if periods:
        overrides["months_on_record_from"] = min(periods)
        overrides["months_on_record_to"] = max(periods)

    def in_asked_month(when: date) -> bool:
        return when.month == month and (year is None or when.year == year)

    invoice = next((i for i in invoices if in_asked_month(i.billing_period)), None)
    if invoice is not None:
        overrides["asked_month_found"] = True
        overrides["asked_month"] = invoice.billing_period
        overrides.update({
            "invoice_id": invoice.invoice_id,
            "invoice_period": invoice.billing_period,
            "invoice_units": invoice.units_consumed,
            "invoice_rate": invoice.rate_applied,
            "invoice_fixed_charge": invoice.fixed_charge,
            "invoice_variable_charge": invoice.variable_charge,
            "invoice_total": invoice.total_amount,
        })
        earlier = next(
            (i for i in invoices if i.billing_period < invoice.billing_period), None
        )
        # Explicitly cleared rather than left alone: the newest invoice's
        # predecessor is still sitting in the context, and comparing February
        # against May because May happened to be loaded first is the same class
        # of fault as answering about June.
        overrides.update({
            "previous_invoice_period": earlier.billing_period if earlier else None,
            "previous_invoice_units": earlier.units_consumed if earlier else None,
            "previous_invoice_rate": earlier.rate_applied if earlier else None,
            "previous_invoice_total": earlier.total_amount if earlier else None,
        })

    bill = next((b for b in bills if in_asked_month(b.due_date)), None)
    if bill is not None:
        overrides["asked_month_found"] = True
        overrides.setdefault("asked_month", date(bill.due_date.year, bill.due_date.month, 1))
        overrides.update({
            "latest_bill_amount": float(bill.amount),
            "latest_bill_due_date": bill.due_date,
            "latest_bill_status": bill.status,
        })
        # The payment that settled THIS bill, not the newest payment on the
        # account. A February bill answered with "your payment was received on
        # 23 August" is a true sentence about a different bill.
        payment = (
            db.query(Payment)
            .filter(Payment.bill_id == bill.bill_id)
            .order_by(Payment.date.desc())
            .first()
        )
        overrides["has_last_payment"] = payment is not None
        overrides["last_payment_amount"] = float(payment.amount) if payment else 0.0
        overrides["last_payment_on"] = payment.date if payment else None

    # The full series, not the twelve months the context carries for the LLM:
    # a question about a month further back than that deserves the same answer
    # as a question about last month.
    series = _monthly_series(db, customer.customer_id)
    # Newest first, and pinned to the invoice's own month when there is one.
    # Walking oldest-first answered "كم استهلكت في آذار؟" with March 2025 while
    # the bill half of the same context was pointing at March 2026 — the two
    # halves of one reply describing two different years.
    chosen = overrides.get("asked_month")
    for index in range(len(series) - 1, -1, -1):
        when, kwh = series[index]
        hit = (when.year, when.month) == (chosen.year, chosen.month) if chosen \
            else in_asked_month(when)
        if hit:
            previous = series[index - 1][1] if index > 0 else 0.0
            overrides["asked_month_found"] = True
            overrides.setdefault("asked_month", when)
            overrides["latest_period_month"] = when
            overrides["latest_period_kwh"] = round(kwh, 1)
            overrides["previous_period_kwh"] = round(previous, 1)
            overrides["change_pct"] = round(
                ((kwh - previous) / previous * 100) if previous > 0 else 0.0, 1
            )
            break

    return overrides


def _no_such_month(ctx: dict, lang: str, first: str) -> str:
    """The month was named, and the account has nothing for it."""
    asked = _month_name(ctx["asked_month_number"], lang)
    if ctx.get("asked_month_year"):
        asked = f"{asked} {ctx['asked_month_year']}"

    start, end = ctx.get("months_on_record_from"), ctx.get("months_on_record_to")
    if start and end:
        have = _pick(
            lang,
            f" What I have on your account runs from {_month_label(start, lang)} to "
            f"{_month_label(end, lang)}, and it is all on your Bills page.",
            f" وما لدي على حسابك يمتد من {_month_label(start, lang)} إلى "
            f"{_month_label(end, lang)}، وهو كله في صفحة الفواتير.",
        )
    else:
        have = _pick(lang,
                     " I have no bills on record for your account yet.",
                     " ولا توجد فواتير مسجّلة على حسابك بعد.")

    return _pick(
        lang,
        f"I have no bill for {asked} on your account, {first}.",
        f"لا توجد لدي فاتورة لشهر {asked} على حسابك يا {first}.",
    ) + have


# ---------------------------------------------------------------------------
# Intent engine (default / fallback)
# ---------------------------------------------------------------------------
# Arabic keywords are STEMS, not whole words, and the reason is grammatical
# rather than sloppy. Arabic attaches its prepositions, its article and its
# possessives to the word: فاتورة, الفاتورة, فاتورتي, بفاتورتي and لفاتورتك are
# one noun wearing five different sets of clothes. Whole-word matching, which is
# right for English, recognises none of them. So an Arabic key matches anywhere
# in the word and is chosen long enough that it cannot land inside an unrelated
# one. See `_mentions`.
_RAW_INTENTS: dict[str, tuple[str, ...]] = {
    "billing": ("bill", "bills", "invoice", "amount",
                "expensive", "high", "higher", "cost",
                "فاتور", "فواتير", "مبلغ", "غالي", "غالية", "ارتفع", "مرتفع", "كلفة"),
    # "owe" and "outstanding" live here rather than under billing, and the
    # difference is not cosmetic: "how much do I owe?" answered from the bill
    # quotes its FACE VALUE, and this provider takes part payments, so a
    # subscriber who has already paid half was told he owed the whole thing.
    # The balance is what he owes.
    "payment": ("pay", "paid", "payment", "due", "overdue", "balance", "receipt",
                "refund", "installment", "omt", "whish", "owe", "owed", "outstanding",
                "دفع", "ادفع", "بدفع", "تسديد", "سدد", "رصيد", "متأخر", "استحقاق",
                "ايصال", "تقسيط", "علي مصاري", "بقيت"),
    "consumption": ("usage", "use", "used", "using", "consumption", "consume",
                    "kwh", "electricity", "energy", "meter", "reading",
                    "استهلاك", "استهلكت", "كيلوواط", "كهربا", "طاقة", "قراءة", "قرأ"),
    "savings": ("save", "saving", "savings", "reduce", "lower", "cheaper",
                "efficient", "tip", "tips", "advice", "recommend",
                "وفر", "توفير", "أوفر", "نصيحة", "نصائح", "أقلل", "تقليل", "خفف"),
    # "when" and "time" were in here and are far too broad: "when is my bill
    # due" is a question about a date, not about the network peak.
    "peak": ("peak", "off-peak", "night", "busiest", "schedule",
             "ذروة", "الذروة", "أوقات الضغط"),
    # No "هاي" for "hi". It is three letters that sit inside نهاية, so "نهاية
    # الشهر", the end of the month, a perfectly ordinary thing to ask about, 
    # would have been greeted with hello. The English "hi" is safe only because
    # English matching is whole-word.
    "greeting": ("hello", "hi", "hey", "salam", "marhaba", "good morning", "good evening",
                 "مرحبا", "أهلا", "سلام", "صباح الخير", "مساء الخير", "كيفك"),
    # Asked often enough to be worth answering properly, and there is no honest
    # answer in this data: nothing in the provider's files records a panel, an
    # inverter or a kWh generated on site. The reply says so instead of falling
    # through to the peak-hours advice, which is what "How much can I save with
    # solar?", one of the four suggestions printed on the Assistant page, 
    # used to get.
    "solar": ("solar", "panel", "panels", "photovoltaic", "pv", "battery", "inverter",
              "شمسي", "شمسية", "ألواح", "بطارية", "انفرتر", "طاقة شمسية"),
    # Phrases, not single words, so this does not steal every question that
    # contains "payment". Whole-word matching handles a multi-word key as one
    # unit, so "last payment" matches only when both words appear together.
    "last_payment": ("last payment", "latest payment", "recent payment",
                     "previous payment", "payment history", "when did i pay",
                     "when i paid", "last time i paid", "did i last pay",
                     "my last payment", "when was my last",
                     "آخر دفعة", "اخر دفعة", "آخر تسديد", "امتى دفعت", "متى دفعت",
                     "كم دفعت", "آخر مرة دفعت"),
    # The rate per kWh. Was answered with the bill total, which is a different
    # question: the rate is published monthly, it has moved by a third across
    # the eighteen months on record, and it is in the `tariffs` table.
    "tariff": ("tariff", "rate", "rate per kwh", "price per kwh", "cost per kwh",
               "per kwh", "kwh cost", "kwh price", "unit price", "price of electricity",
               "price", "how much per kwh",
               "تعرفة", "التعرفة", "سعر", "أسعار", "التسعيرة", "سعر الكيلو"),
    # How many hours a day the zone is supplied. Measured in `supply_sessions`,
    # and previously answered with peak-hour advice, which is not the question
    # anybody in Lebanon is asking when they ask about hours.
    "supply_hours": ("hours a day", "hours per day", "how many hours", "supply hours",
                     "hours of electricity", "hours do i get", "how long",
                     "cut off", "cut-off", "rationing",
                     "كم ساعة", "ساعات التغذية", "ساعات الكهربا", "وقت التغذية",
                     "تقنين", "التقنين", "كم ساعه"),
    # Facts sitting in the customer's own row, which used to reach the
    # catch-all: the customer number the provider files everything under, the
    # address on file, the meter, the contracted amperes.
    "account": ("customer number", "customer id", "account number", "my address",
                "my phone", "my details", "my account", "my plan", "my meter",
                "meter number", "amperes", "ampere", "my subscription", "my zone",
                "my email", "who am i",
                "رقم الاشتراك", "رقم الحساب", "رقم الزبون", "عنواني", "معلوماتي",
                "أمبير", "امبير", "رقم العداد", "اشتراكي", "بياناتي", "منطقتي"),
    # How the amount was arrived at, kWh by kWh. Answerable to the pound from
    # the invoice row, and the right reply to "I think my bill is wrong".
    # "charge" and "charges" sit here and not under billing. Someone asking
    # what a charge IS wants the arithmetic; someone asking why the BILL is
    # high wants the trend, and "bill" plus "high" still scores that as billing.
    "bill_breakdown": ("how is my bill calculated", "how was my bill calculated",
                       "explain my bill", "breakdown", "break down", "itemised",
                       "fixed charge", "subscription charge", "how do you calculate",
                       "charge", "charges",
                       "كيف تحسب", "كيف احتسبت", "تفصيل الفاتورة", "رسم الثابت",
                       "احتساب", "شرح الفاتورة", "كيف طلعت"),
    "history": ("history", "last six months", "last 6 months", "past months",
                "previous months", "month by month", "over the year", "last year",
                "سجل استهلاك", "أشهر الماض", "آخر ستة أشهر", "شهر بشهر",
                "سنة الماض", "تاريخ استهلاكي"),
    "compare": ("compare", "comparison", "average", "neighbours", "neighbors",
                "other customers", "others", "than usual", "normal for",
                "مقارنة", "بالمقارنة", "معدل", "جيران", "غيري", "آخرين",
                "وسطي"),
    "password": ("password", "log in", "login", "sign in", "signin", "locked out",
                 "forgot my", "reset my",
                 "كلمة السر", "كلمة المرور", "نسيت", "تسجيل الدخول", "ما بقدر افوت",
                 "حساب مقفل"),
    "outage": ("power cut", "no electricity", "no power", "outage", "blackout",
               "emergency", "who do i call", "who to call", "contact", "phone number",
               "fault", "broken", "not working", "complaint", "complain",
               "انقطاع", "ما في كهربا", "مافي كهربا", "عطل", "شكوى", "أتصل بمين",
               "اتصل بمين", "رقم المولد", "طوارئ", "مقطوعة"),
    "account_change": ("cancel my subscription", "cancel my account", "disconnect",
                       "terminate", "increase my amperes", "upgrade my", "downgrade",
                       "move my meter", "change my subscription", "new subscription",
                       "إلغاء الاشتراك", "الغاء الاشتراك", "بدي افصل", "فصل الاشتراك",
                       "زيادة أمبير", "زيادة امبير", "ترقية", "نقل العداد"),
    "discount": ("discount", "waive", "forgive", "reduction on my bill", "too expensive",
                 "can you lower", "special price", "help with my bill",
                 "خصم", "حسم", "تخفيض", "اعتراض", "فاتورة غلط", "مش قادر ادفع",
                 "ما بقدر ادفع", "قادر ادفع", "بقدر ادفع"),
    # "How much will my bill be next month?" There is no answer to this in the
    # data, and there is a great deal that can honestly be said around it, which
    # is a different thing from the billing answer it used to be given.
    "forecast": ("next month", "next bill", "will my bill", "how much will",
                 "expected", "expect", "predict", "prediction", "forecast",
                 "estimate", "coming month", "going to be",
                 "المتوقع", "متوقع", "الشهر المقبل", "الشهر القادم", "الشهر الجاي",
                 "توقع", "رح تكون", "كم رح", "شو رح", "المستقبل"),
    # Cooling is the largest thing on a Lebanese summer bill and the one
    # appliance every subscriber asks about. A meter read once a month cannot
    # separate it from the fridge, but the season is plainly visible in the
    # readings, and that is worth answering with.
    "cooling": ("ac", "a/c", "ac usage", "reduce ac", "air conditioner",
                "air conditioning", "aircon", "cooling", "cool the house",
                "heater", "heating", "fan", "fridge", "refrigerator",
                "appliance", "appliances",
                "تكييف", "مكيف", "تبريد", "براد", "ثلاجة", "سخان", "مروحة",
                "أجهزة", "الاجهزة",
                # Phrases as well as the bare noun. "نصائح لتقليل استهلاك التكييف"
                # scores two for savings on نصائح and تقليل, so cooling needs two
                # of its own to reach the tie that priority then settles.
                "استهلاك التكييف", "استهلاك المكيف", "تقليل التكييف"),
    "capabilities": ("what can you do", "what do you do", "what can i ask",
                     "help me", "what are you", "who are you", "options",
                     "شو بتعرف", "شو فيك", "كيف بتساعدني", "شو بتقدر", "مين انت",
                     "وش تعرف", "كيف بدك تساعدني"),
}

_INTENTS: dict[str, tuple[str, ...]] = {
    intent: tuple(_normalise(keyword) for keyword in keywords)
    for intent, keywords in _RAW_INTENTS.items()
}

# Ties are broken by this order, most specific first. "How can I save energy?"
# scores one for savings ("save") and one for consumption ("energy"), and the
# person is asking how to save.
#
# The four that lead are the ones whose whole point is that they are NOT the
# general question they resemble: "what can you do" is not a request for help
# with a bill, "how much per kWh" is not a question about the bill total, "how
# many hours" is not a question about the peak hour, and "can I have a
# discount" is not a request for saving tips.
# The questions that are about a month already on record. Deliberately not
# `forecast`: that one is about a month that has not happened, and pointing it
# at an old invoice would be the same fault in the opposite direction.
_MONTH_SCOPED = frozenset({"billing", "consumption", "bill_breakdown",
                           "payment", "last_payment", "tariff"})

_INTENT_PRIORITY = ("greeting", "capabilities", "solar", "password", "outage",
                    "account_change", "discount", "forecast", "cooling",
                    "bill_breakdown", "tariff", "supply_hours", "last_payment",
                    "compare", "history", "account", "savings", "peak",
                    "payment", "billing", "consumption")


def _mentions(keyword: str, text: str) -> bool:
    """
    Whole words in English, stems in Arabic.

    ENGLISH. Plain `keyword in text` looks harmless and quietly mismatches. "hi"
    is inside "high", so "why is my bill so high?" scored as a greeting and was
    answered with "Hello!". "use" is inside "because" and "user". Every one of
    those is a question answered with the wrong thing and no error anywhere.

    The boundaries are \\w rather than \\b so that a hyphenated keyword such as
    "off-peak" still matches as one unit.

    ARABIC. The same rule applied to Arabic recognises almost nothing, because
    Arabic writes its article, its prepositions and its possessives joined to
    the word: ask about فاتورتي and a whole-word test for فاتورة fails. So an
    Arabic key is matched as a substring, and the keys are chosen long enough
    that they cannot land inside an unrelated word.
    """
    if _ARABIC_TEXT.search(keyword):
        return keyword in text
    return re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", text) is not None


def _detect_intent(message: str) -> str:
    text = _normalise(message)
    scores = {
        intent: sum(1 for keyword in keywords if _mentions(keyword, text))
        for intent, keywords in _INTENTS.items()
    }
    best = max(
        _INTENT_PRIORITY,
        key=lambda intent: (scores.get(intent, 0), -_INTENT_PRIORITY.index(intent)),
    )
    return best if scores.get(best, 0) > 0 else "faq"


# ---------------------------------------------------------------------------
# One handler per intent
#
# Each takes the assembled context, the language to answer in, the customer's
# first name and the measured peak advice, and returns the reply. Keeping them
# apart from the dispatcher is what makes it possible to read one answer
# without scrolling past eighteen others.
# ---------------------------------------------------------------------------
def _reply_greeting(ctx: dict, lang: str, first: str, advice: list[str]) -> str:
    return _pick(
        lang,
        f"Hello {first}! I'm your energy assistant. I can help with your bill, "
        "payments, consumption patterns and ways to save. What would you like to know?",
        f"أهلاً {first}! أنا مساعدك للطاقة. يمكنني مساعدتك في فاتورتك ودفعاتك "
        "واستهلاكك وطرق التوفير. ما الذي تحب أن تعرفه؟",
    )


# What the assistant can answer, one clause per capability, tagged with the
# topic it belongs to and the shared fact it needs (None: the customer's own
# records). Switching a topic or a fact off in config/chatbot.toml takes the
# clause out of the two lists below as well, so the assistant never offers
# something it will then refuse.
_CAPABILITIES: tuple[tuple[str, str | None, str, str], ...] = (
    ("billing", None, "your current bill and why it moved",
     "فاتورتك الحالية وسبب تغيّرها"),
    ("payments", None, "what you still owe and how to pay it",
     "ما تبقّى عليك وكيف تدفعه"),
    ("consumption", None, "how much you used in a month and across the last year",
     "استهلاكك في أي شهر وعلى مدى السنة الماضية"),
    ("billing", None, "how a bill was worked out, kWh by kWh",
     "كيف احتُسبت الفاتورة كيلوواط بكيلوواط"),
    ("billing", None, "the rate per kWh you were charged and why it changes every month",
     "سعر الكيلوواط الذي حُوسبت عليه ولماذا يتغيّر كل شهر"),
    ("service", "supply_hours", "how many hours a day your zone is supplied",
     "كم ساعة يومياً تُغذّى منطقتك"),
    ("account", None, "when your meter was last read",
     "متى قُرئ عدّادك آخر مرة"),
    ("account", None, "your account, meter and contract details",
     "تفاصيل حسابك وعدّادك واشتراكك"),
    ("consumption", "network_peak", "which hour the network is busiest",
     "أي ساعة تكون الشبكة في أوجّ ضغطها"),
)

_FAQ_TOPICS: tuple[tuple[str, str | None, str, str], ...] = (
    ("billing", None, "your bill and why it moved", "فاتورتك وسبب تغيّرها"),
    ("payments", None, "what you owe and how to pay", "ما تبقّى عليك وكيفية دفعه"),
    ("consumption", None, "your consumption and its history", "استهلاكك وسجله"),
    ("billing", None, "how a bill was calculated", "كيف احتُسبت الفاتورة"),
    ("billing", None, "the rate per kWh", "سعر الكيلوواط"),
    ("service", "supply_hours", "the hours your zone is supplied", "ساعات التغذية في منطقتك"),
    ("account", None, "when your meter was last read", "متى قُرئ عدّادك آخر مرة"),
    ("account", None, "your account and contract details", "تفاصيل حسابك واشتراكك"),
)


def _offered(clauses: tuple[tuple[str, str | None, str, str], ...]) -> list[tuple[str, str]]:
    """The clauses whose topic is on and whose shared fact, if any, is shared."""
    policy = chatbot_config.get().customer
    return [(en, ar) for topic, fact, en, ar in clauses
            if topic in policy.topics and (fact is None or policy.shares(fact))]


def _reply_capabilities(ctx: dict, lang: str, first: str, advice: list[str]) -> str:
    """
    What this assistant can and cannot do, said once and in full.

    Worth its own answer because the alternative is a person guessing. Every
    line of it is a question that reaches real data, and the last sentence is
    the boundary: the four things it will not pretend to do. The list follows
    config/chatbot.toml.
    """
    offered = _offered(_CAPABILITIES)
    if not offered:
        return chatbot_config.get().customer.reply("out_of_scope", lang)
    en = [e for e, _ in offered]
    ar = [a for _, a in offered]
    if len(offered) > 1:
        en[-1] = "and " + en[-1]
        ar[-1] = "و" + ar[-1]
    return _pick(
        lang,
        f"Quite a few things, {first}, and all of them from your own records: "
        + "; ".join(en) + ". "
        "Ask me in Arabic or in English, whichever you prefer. What I cannot do is "
        "change your contract, give a discount, report a fault or take a payment, and "
        "I will say so plainly rather than guess.",
        f"أشياء كثيرة يا {first}، وكلها من سجلاتك أنت: "
        + "؛ ".join(ar) + ". "
        "اسألني بالعربية أو بالإنجليزية، كما تفضّل. أما ما لا أستطيعه فهو تعديل اشتراكك، أو "
        "منحك حسماً، أو تسجيل عطل، أو قبض مبلغ، وسأقولها بصراحة بدل أن أخمّن.",
    )


def _billing_status(ctx: dict, lang: str) -> str:
    """
    Whether the bill just described still has to be paid. Said last, and briefly.

    The distinction in the middle branch is not pedantry. A subscriber whose
    June bill is paid can still owe money on March, and appending "you still
    have 14,208,708 LBP outstanding" to a sentence about June invites the reader
    to attach that figure to the June bill. It belongs to older bills and the
    reply says which.
    """
    balance = ctx["balance"]
    settled_now = ctx.get("latest_bill_status") == "Paid"

    if balance > 0 and not settled_now:
        due = _date_label(ctx["latest_bill_due_date"], lang)
        return _pick(
            lang,
            f" It has not been settled: {money(balance)} is outstanding on your account"
            + (f", and this bill was due on {due}." if due else "."),
            f" وهي غير مسدّدة: عليك {money(balance)} على حسابك"
            + (f"، وكان استحقاق هذه الفاتورة في {due}." if due else "."),
        )

    if balance > 0:
        return _pick(
            lang,
            f" That bill is settled. Separately, {money(balance)} is still outstanding on older "
            "bills, which are listed on your Bills page.",
            f" وهذه الفاتورة مسدّدة. أما بشكل منفصل، فما زال عليك {money(balance)} على فواتير "
            "أقدم، وهي مذكورة في صفحة الفواتير.",
        )

    if ctx["has_last_payment"]:
        paid_on = _date_label(ctx["last_payment_on"], lang)
        return _pick(lang,
                     f" It is settled: your payment was received on {paid_on}.",
                     f" وهي مسدّدة: استُلمت دفعتك في {paid_on}.")
    return _pick(lang, " It is settled.", " وهي مسدّدة.")


def _reply_billing(ctx: dict, lang: str, first: str, advice: list[str]) -> str:
    """
    Why the bill is what it is.

    THE NEWEST BILL LEADS, NOT THE NEWEST UNPAID ONE
    ------------------------------------------------
    "لماذا كانت فاتورتي هكذا هذا الشهر" was answered with "you have no
    outstanding bill right now". True, and about a different question, and it
    reads as though nothing had been understood. An account that owes nothing
    still has a most recent bill, and that bill is what was asked about. So the
    newest bill leads whatever its status, and whether anything is still owed
    goes at the end, where it belongs.

    AND THE ANSWER TO "WHY" IS THE DECOMPOSITION
    --------------------------------------------
    A bill moves for exactly two reasons: the number of kilowatt-hours changed,
    or the price of one did. Restating the total is not an answer to why; naming
    which of the two moved it is. Both are on the invoice, and the second one is
    not idle here: the Ministry sets the rate monthly against the diesel price,
    so it travels by a third across the eighteen months on record and can move a
    bill on its own while consumption sits still.

    AND A MONTH NAMED IN THE QUESTION IS THE MONTH ANSWERED
    -------------------------------------------------------
    See `scope_to_month`. By the time the reply runs, the context has already
    been re-pointed at whichever month was asked for, so everything below is
    unchanged; all this function has to know is whether that month exists.
    """
    if ctx.get("asked_month_number") and not ctx.get("asked_month_found"):
        return _no_such_month(ctx, lang, first)

    total = ctx.get("invoice_total")
    period = _month_label(ctx.get("invoice_period"), lang)
    units, rate = ctx.get("invoice_units"), ctx.get("invoice_rate")
    fixed = ctx.get("invoice_fixed_charge")
    prev_total = ctx.get("previous_invoice_total")
    prev_units, prev_rate = ctx.get("previous_invoice_units"), ctx.get("previous_invoice_rate")
    prev_period = _month_label(ctx.get("previous_invoice_period"), lang)

    # The full answer: this month's bill, last month's, and which of the two
    # things that decide it actually moved.
    if total and prev_total and units and prev_units and rate and prev_rate:
        bill_pct = (total - prev_total) / prev_total * 100
        units_pct = (units - prev_units) / prev_units * 100
        rate_pct = (rate - prev_rate) / prev_rate * 100

        opening = _pick(
            lang,
            f"Your {period} bill was {money(total)}, "
            f"{'up' if bill_pct >= 0 else 'down'} {abs(bill_pct):.0f}% on {prev_period}.",
            f"فاتورة {period} كانت {money(total)}، أي "
            f"{'بزيادة' if bill_pct >= 0 else 'بانخفاض'} {abs(bill_pct):.0f}% عن {prev_period}.",
        )
        parts = _pick(
            lang,
            f" Two things decide it: you used {units:,.1f} kWh against {prev_units:,.1f} the month "
            f"before, and the rate went from {money(prev_rate)} to {money(rate)} per kWh"
            + (f", on top of the fixed subscription charge of {money(fixed)}." if fixed else "."),
            f" شيئان يحدّدانها: استهلكت {units:,.1f} kWh مقابل {prev_units:,.1f} في الشهر الذي "
            f"قبله، وتغيّر السعر من {money(prev_rate)} إلى {money(rate)} للكيلوواط الساعي"
            + (f"، فوق رسم الاشتراك الثابت البالغ {money(fixed)}." if fixed else "."),
        )

        # Which of the two carried it. A factor of two apart is a clear answer;
        # closer than that and both moved, and the honest reply says so.
        if abs(units_pct) >= 2 * abs(rate_pct):
            driver = _pick(
                lang,
                " So this bill followed your consumption rather than the price.",
                " أي أن هذه الفاتورة تبعت استهلاكك لا السعر.",
            )
        elif abs(rate_pct) >= 2 * abs(units_pct):
            driver = _pick(
                lang,
                " So this bill followed the price rather than your consumption. The rate is set "
                "monthly by the Ministry of Energy and Water and follows the diesel price.",
                " أي أن هذه الفاتورة تبعت السعر لا استهلاكك. والسعر تحدّده وزارة الطاقة والمياه "
                "شهرياً وهو يتبع سعر المازوت.",
            )
        elif units_pct * rate_pct >= 0:
            driver = _pick(
                lang,
                " Both moved the same way, so they added together.",
                " وقد تحرّك الاثنان في الاتجاه نفسه، فاجتمع أثرهما.",
            )
        else:
            driver = _pick(
                lang,
                " They pulled against each other, and the larger of the two won.",
                " وقد تجاذبا في اتجاهين متعاكسين، فغلب الأكبر منهما.",
            )
        return opening + parts + driver + _billing_status(ctx, lang)

    # One invoice and no month to compare it against: the amount, and the
    # arithmetic behind it, without a change nobody can measure.
    if total and units and rate:
        return _pick(
            lang,
            f"Your {period} bill was {money(total)}: {units:,.1f} kWh at {money(rate)} per kWh"
            + (f", plus the fixed subscription charge of {money(fixed)}." if fixed else ".")
            + " There is no earlier month on your account to compare it against yet."
            + _billing_status(ctx, lang),
            f"فاتورة {period} كانت {money(total)}: {units:,.1f} kWh بسعر {money(rate)} للكيلوواط "
            "الساعي" + (f"، يضاف إليها رسم الاشتراك الثابت البالغ {money(fixed)}." if fixed else ".")
            + " ولا يوجد شهر سابق على حسابك للمقارنة به بعد."
            + _billing_status(ctx, lang),
        )

    # No itemised invoice, so fall back to the bill and the meter readings.
    if ctx["latest_bill_amount"] > 0:
        due = _date_label(ctx["latest_bill_due_date"], lang)
        month = _month_label(ctx["latest_period_month"], lang)
        if ctx["latest_period_month"] and ctx["previous_period_kwh"]:
            trend = _pick(
                lang,
                f" In {month} you used {ctx['latest_period_kwh']} kWh, "
                f"{abs(ctx['change_pct'])}% "
                f"{'higher' if ctx['change_pct'] > 0 else 'lower'} than the month before.",
                f" في {month} استهلكت {ctx['latest_period_kwh']} kWh، أي "
                f"{abs(ctx['change_pct'])}% "
                f"{'أعلى' if ctx['change_pct'] > 0 else 'أقل'} من الشهر الذي قبله.",
            )
        elif ctx["latest_period_month"]:
            trend = _pick(lang,
                          f" In {month} you used {ctx['latest_period_kwh']} kWh.",
                          f" في {month} استهلكت {ctx['latest_period_kwh']} kWh.")
        else:
            trend = _pick(lang,
                          " I do not have meter readings for your account yet.",
                          " وليست لدي قراءات عدّاد لحسابك بعد.")
        return _pick(
            lang,
            f"Your most recent bill is {money(ctx['latest_bill_amount'])}"
            + (f", due on {due}." if due else "."),
            f"آخر فاتورة لك هي {money(ctx['latest_bill_amount'])}"
            + (f"، استحقاقها في {due}." if due else "."),
        ) + trend + _billing_status(ctx, lang)

    return _pick(
        lang,
        f"I have no bills on record for your account yet, {first}. They appear on your Bills page "
        "as soon as the provider issues them.",
        f"لا توجد فواتير مسجّلة على حسابك بعد يا {first}. وتظهر في صفحة الفواتير حالما يصدرها "
        "المزوّد.",
    )


def _next_month(when: date) -> date:
    return date(when.year + (when.month == 12), when.month % 12 + 1, 1)


def _reply_forecast(ctx: dict, lang: str, first: str, advice: list[str]) -> str:
    """
    Next month's bill, which nobody knows.

    THE SHAPE OF AN HONEST ANSWER TO A QUESTION WITH NO ANSWER
    ----------------------------------------------------------
    Two unknowns decide it: the kilowatt-hours, which have not happened, and the
    rate, which the Ministry has not published. Producing one number here would
    be the worst thing this assistant could do, because it would be quoted back
    as a promise.

    Refusing flatly is not right either. The arithmetic a subscriber would do
    for themselves is legitimate, so it is done for them, on two bases that
    disagree, with what each one assumes stated plainly. Two figures that
    bracket the answer teach more than one that pretends to be it.

    The second basis is the same month a year ago rather than last month, for
    the reason the alert engine works that way: consumption here is seasonal,
    and comparing July with June says less than comparing July with July.
    """
    series = ctx.get("monthly_series") or []
    rate = ctx.get("invoice_rate")
    fixed = float(ctx.get("invoice_fixed_charge") or 0.0)
    lowest, highest = ctx.get("rate_lowest_charged"), ctx.get("rate_highest_charged")
    months = ctx.get("rate_months_on_record")

    opening = _pick(
        lang,
        f"I cannot tell you, {first}, and it is worth saying why rather than handing you a "
        "number that would be quoted back to me. Two things decide next month's bill and "
        "neither has happened yet: how much you use, and the rate.",
        f"لا أستطيع أن أقول لك يا {first}، ويستحق الأمر أن أشرح السبب بدل أن أعطيك رقماً "
        "سيُحاسَب عليه لاحقاً. شيئان يحدّدان فاتورة الشهر المقبل ولم يقع أي منهما بعد: كم "
        "ستستهلك، وكم سيكون السعر.",
    )
    if lowest and highest and months:
        opening += _pick(
            lang,
            f" The rate is set monthly by the Ministry of Energy and Water against the diesel "
            f"price, and across the {months} months on your account it has moved between "
            f"{money(lowest)} and {money(highest)} per kWh.",
            f" والسعر تحدّده وزارة الطاقة والمياه شهرياً بحسب سعر المازوت، وعلى مدى {months} "
            f"شهراً على حسابك تراوح بين {money(lowest)} و{money(highest)} للكيلوواط الساعي.",
        )

    if not series or rate is None:
        return opening + _pick(
            lang,
            " Once next month is read and billed it appears on your Bills page.",
            " وحالما يُقرأ الشهر المقبل وتصدر فاتورته ستظهر في صفحة الفواتير.",
        )

    recent = series[-3:]
    average = sum(kwh for _, kwh in recent) / len(recent)
    body = _pick(
        lang,
        f" What I can do is the arithmetic you would do yourself. Your last {len(recent)} "
        f"recorded months average {average:,.1f} kWh; at {money(rate)} per kWh, the rate you "
        f"were last charged, plus the fixed charge of {money(fixed)}, that comes to "
        f"{money(average * rate + fixed)}.",
        f" لكن أستطيع أن أجري الحساب الذي كنت ستجريه بنفسك. متوسط آخر {len(recent)} أشهر "
        f"مسجّلة لديك {average:,.1f} kWh؛ وبسعر {money(rate)} للكيلوواط الساعي، وهو السعر "
        f"الذي حُوسبت عليه آخر مرة، مضافاً إليه الرسم الثابت {money(fixed)}، يصبح المجموع "
        f"{money(average * rate + fixed)}.",
    )

    # The same month a year ago, which for a seasonal load is the better guide.
    target = _next_month(series[-1][0])
    year_ago = {month: kwh for month, kwh in series}.get(
        date(target.year - 1, target.month, 1)
    )
    if year_ago:
        body += _pick(
            lang,
            f" On a different basis: in {_month_label(date(target.year - 1, target.month, 1), 'en')} "
            f"you used {year_ago:,.1f} kWh, which at the same rate would be "
            f"{money(year_ago * rate + fixed)}. Consumption here is seasonal, so the same month "
            "a year ago is usually the better guide of the two.",
            f" وعلى أساس آخر: في {_month_label(date(target.year - 1, target.month, 1), 'ar')} "
            f"استهلكت {year_ago:,.1f} kWh، وهو ما يعادل بالسعر نفسه "
            f"{money(year_ago * rate + fixed)}. والاستهلاك هنا موسمي، فالشهر نفسه من السنة "
            "الماضية هو عادةً الدليل الأفضل بين الاثنين.",
        )

    return body and (opening + body + _pick(
        lang,
        " Neither of those is a forecast. They are your own past readings at today's price, and "
        "a hot month or a change in the rate moves both. The forecast on this platform predicts "
        "demand across the whole network, not one household's bill.",
        " ولا واحد من الرقمين توقّع. هما قراءاتك السابقة بسعر اليوم، وشهر حارّ أو تغيّر في "
        "السعر يحرّكهما معاً. أما التوقّعات في هذه المنصة فتقدّر الطلب على الشبكة كلها، لا "
        "فاتورة بيت واحد.",
    ))


def _reply_cooling(ctx: dict, lang: str, first: str, advice: list[str]) -> str:
    """
    Air conditioning, and what a monthly meter can and cannot say about it.

    It cannot say what the air conditioner costs. One reading a month is one
    number for the whole house, and no arithmetic separates the cooling from the
    fridge and the lights. Any figure claiming to would be invented, and it
    would be invented about the single largest line on a Lebanese summer bill,
    which is where a subscriber would act on it.

    What the readings do show is the SEASON, and clearly: this subscriber's use
    runs from 259.6 kWh in October to 903.0 in August. That gap is measured, it
    is the customer's own, and it is the honest version of the answer.
    """
    series = ctx.get("monthly_series") or []
    rate = ctx.get("invoice_rate")

    limit = _pick(
        lang,
        f"I cannot tell you what the air conditioner alone costs, {first}. Your meter is read "
        "once a month and reports a single number for the whole house, so nothing here "
        "separates the cooling from the fridge, the lights and everything else. Any figure I "
        "gave you for it would be invented.",
        f"لا أستطيع أن أقول لك كم يكلّفك المكيّف وحده يا {first}. عدّادك يُقرأ مرة واحدة في "
        "الشهر ويعطي رقماً واحداً للبيت كله، فليس هنا ما يفصل التبريد عن البرّاد والإنارة "
        "وسائر الأجهزة. وأي رقم أعطيك إياه عنه سيكون مخترعاً.",
    )

    if len(series) >= 4:
        high_month, high = max(series, key=lambda row: row[1])
        low_month, low = min(series, key=lambda row: row[1])
        gap = high - low
        worth = _pick(
            lang,
            f", worth {money(gap * rate)} at {money(rate)} per kWh" if rate else "",
            f"، أي ما قيمته {money(gap * rate)} بسعر {money(rate)} للكيلوواط الساعي" if rate else "",
        )
        limit += _pick(
            lang,
            f" What the readings do show is the season. You used {low:,.1f} kWh in "
            f"{_month_label(low_month, 'en')} and {high:,.1f} kWh in "
            f"{_month_label(high_month, 'en')}, a difference of {gap:,.1f} kWh{worth}.",
            f" لكن القراءات تُظهر الموسم بوضوح. استهلكت {low:,.1f} kWh في "
            f"{_month_label(low_month, 'ar')} و{high:,.1f} kWh في "
            f"{_month_label(high_month, 'ar')}، بفارق {gap:,.1f} kWh{worth}.",
        )
        # Only called cooling when the peak actually falls in the hot months.
        # Otherwise it is a rise with some other cause and this would be a guess.
        if high_month.month in (6, 7, 8, 9) and gap > 0:
            limit += _pick(
                lang,
                " A rise of that size between a mild month and midsummer is usually cooling, so "
                "that gap is the closest honest measure of what it costs you.",
                " وارتفاع بهذا الحجم بين شهر معتدل وذروة الصيف يكون عادةً بسبب التبريد، فهذا "
                "الفارق أقرب قياس صادق لما يكلّفك.",
            )

    if advice:
        limit += " " + advice[0]

    return limit + _pick(
        lang,
        " Your Recommendations page lists what the system worked out from your own readings.",
        " وصفحة التوصيات تعرض ما استنتجه النظام من قراءاتك أنت.",
    )


def _reply_solar(ctx: dict, lang: str, first: str, advice: list[str]) -> str:
    # There is nothing in this provider's data about generation on site: no
    # panel, no inverter, no exported kWh. Saying so is the whole answer. This
    # question is one of the four suggestions the Assistant page offers, and it
    # used to be answered with peak-hours advice.
    return _pick(
        lang,
        f"I cannot answer that one, {first}. This platform only sees what your "
        "meter records, the electricity you take from the generator, so it holds "
        "nothing about panels, batteries or anything generated at your own property. "
        "Working out what solar would save you needs your roof area, your daytime "
        "usage pattern and current equipment prices, none of which are here. What I "
        "can tell you is what you actually use and when, which is the starting point "
        "for that calculation: ask me about your consumption.",
        f"لا أستطيع الإجابة على هذا يا {first}. هذه المنصة لا ترى إلا ما يسجّله عدّادك، "
        "أي الكهرباء التي تأخذها من المولّد، فليس فيها شيء عن الألواح أو البطاريات أو "
        "أي طاقة تُولَّد في منزلك. حساب ما توفّره الطاقة الشمسية يحتاج مساحة سطحك ونمط "
        "استهلاكك النهاري وأسعار المعدّات اليوم، ولا شيء من ذلك موجود هنا. ما أستطيع "
        "قوله هو كم تستهلك فعلاً ومتى، وهذه نقطة البداية لذلك الحساب: اسألني عن استهلاكك.",
    )


def _reply_last_payment(ctx: dict, lang: str, first: str, advice: list[str]) -> str:
    if not ctx["has_last_payment"]:
        return _pick(
            lang,
            f"I have no payment on record for your account yet, {first}. Once the "
            "provider records one it will appear on your Payments page, with a receipt "
            "you can download.",
            f"لا توجد أي دفعة مسجّلة على حسابك حتى الآن يا {first}. حين يسجّل المزوّد "
            "دفعة ستظهر في صفحة المدفوعات مع إيصال يمكنك تنزيله.",
        )

    paid_on = _date_label(ctx["last_payment_on"], lang)
    reply = _pick(
        lang,
        f"Your last payment was {money(ctx['last_payment_amount'])} on {paid_on}.",
        f"آخر دفعة لك كانت {money(ctx['last_payment_amount'])} في {paid_on}.",
    )
    if ctx["balance"] > 0:
        reply += _pick(lang,
                       f" You still have {money(ctx['balance'])} outstanding.",
                       f" ما زال عليك {money(ctx['balance'])}.")
    else:
        reply += _pick(lang, " Your account is fully settled.", " حسابك مسدّد بالكامل.")
    return reply + _pick(
        lang,
        " Every payment is listed on your Payments page with a receipt.",
        " كل الدفعات مذكورة في صفحة المدفوعات مع إيصالاتها.",
    )


def _reply_payment(ctx: dict, lang: str, first: str, advice: list[str]) -> str:
    if ctx["balance"] > 0:
        due = _date_label(ctx["current_bill_due_date"], lang)
        return _pick(
            lang,
            f"You currently have an outstanding balance of {money(ctx['balance'])}"
            + (f", due on {due}" if due else "")
            + ". The provider collects in cash, through OMT and through Whish Money. "
            "Once a payment is recorded it appears on your Payments page with a receipt.",
            f"عليك حالياً رصيد مستحق قدره {money(ctx['balance'])}"
            + (f"، استحقاقه في {due}" if due else "")
            + ". المزوّد يقبض نقداً وعبر OMT وعبر Whish Money. وحين تُسجَّل الدفعة تظهر "
            "في صفحة المدفوعات مع إيصال.",
        )

    reply = _pick(lang,
                  "Your account is fully settled, so no payment is due.",
                  "حسابك مسدّد بالكامل، فلا توجد دفعة مستحقة.")
    if ctx["has_last_payment"]:
        paid_on = _date_label(ctx["last_payment_on"], lang)
        reply += _pick(
            lang,
            f" Your last payment of {money(ctx['last_payment_amount'])} was processed on "
            f"{paid_on}.",
            f" آخر دفعة لك بقيمة {money(ctx['last_payment_amount'])} عولجت في {paid_on}.",
        )
    return reply


def _reply_consumption(ctx: dict, lang: str, first: str, advice: list[str]) -> str:
    # A month was named. If it is not on the account, say so; if it is, the
    # context already points at it, and the only thing that has to change is
    # the phrase calling it the most recent reading, because it is not.
    named = bool(ctx.get("asked_month_number"))
    if named and not ctx.get("asked_month_found"):
        return _no_such_month(ctx, lang, first)

    # An account whose meter readings have not been loaded yet has nothing to
    # compare, so say that plainly instead of reporting "0 kWh, down 0%".
    if ctx["latest_period_month"] is None:
        return _pick(
            lang,
            f"I do not have any meter readings for your account yet, {first}, so "
            "there is no consumption history to show. Readings appear here once your "
            "meter data has been loaded by the provider.",
            f"لا توجد لدي أي قراءات عدّاد لحسابك بعد يا {first}، فلا يوجد سجل استهلاك "
            "أعرضه. تظهر القراءات هنا بمجرد أن يحمّل المزوّد بيانات عدّادك.",
        )

    # The month is NAMED. Meters here are read once a month and the reading can
    # be weeks old, so "recently" would imply a currency the number does not have.
    period = _month_label(ctx["latest_period_month"], lang)
    # ...and it is only the most recent reading when nobody asked for an older one.
    whose = "" if named else _pick(lang, ", your most recent reading", "، وهي أحدث قراءة لديك")

    if ctx["previous_period_kwh"] <= 0:
        return _pick(
            lang,
            f"In {period}{whose}, you used "
            f"{ctx['latest_period_kwh']} kWh. There is not enough earlier history to "
            "compare it against yet. You can see the full month-by-month breakdown on "
            "your Consumption page.",
            f"في {period}{whose}، استهلكت {ctx['latest_period_kwh']} kWh. "
            "ولا يوجد سجل سابق كافٍ للمقارنة بعد. تجد التفصيل شهراً بشهر في صفحة الاستهلاك.",
        )

    return _pick(
        lang,
        f"In {period}{whose}, you used "
        f"{ctx['latest_period_kwh']} kWh, compared with {ctx['previous_period_kwh']} kWh "
        f"the month before, which is {'up' if ctx['change_pct'] > 0 else 'down'} "
        f"{abs(ctx['change_pct'])}%. Your meter is read once a month, so the month is the "
        "smallest period I can show you. The full history is on your Consumption page.",
        f"في {period}{whose}، استهلكت {ctx['latest_period_kwh']} kWh، "
        f"مقابل {ctx['previous_period_kwh']} kWh في الشهر الذي قبله، أي "
        f"{'بزيادة' if ctx['change_pct'] > 0 else 'بانخفاض'} {abs(ctx['change_pct'])}%. "
        "عدّادك يُقرأ مرة واحدة في الشهر، فالشهر هو أصغر فترة أستطيع عرضها. والسجل "
        "الكامل في صفحة الاستهلاك.",
    )


def _reply_savings(ctx: dict, lang: str, first: str, advice: list[str]) -> str:
    # Was three invented tips and an invented "10-15%". Neither the tips nor the
    # percentage came from anything measured, and a number in a sentence about
    # somebody's own bill is exactly where not to invent one. peak_advice reads
    # the generator telemetry and frames its advice around the NETWORK's peak,
    # because monthly meter readings cannot tell anyone what hour their own
    # house is busiest.
    if advice:
        joined = " ".join(advice)
        return _pick(
            lang,
            joined + " Your personalised list, with what each change is worth, is on the "
            "Recommendations page.",
            joined + " وقائمتك الخاصة، مع قيمة كل تغيير، موجودة في صفحة التوصيات.",
        )
    return _pick(
        lang,
        "I do not have enough load data yet to tell you which hours are worth avoiding. "
        "Your Recommendations page lists whatever the system has been able to work out "
        "from your own readings.",
        "لا تتوفر لدي بيانات حِمل كافية بعد لأقول لك أي الساعات يجدر تجنّبها. وصفحة "
        "التوصيات تعرض ما استطاع النظام استنتاجه من قراءاتك أنت.",
    )


def _reply_peak(ctx: dict, lang: str, first: str, advice: list[str]) -> str:
    # The old answer said peak was 6pm-10pm and off-peak "8pm through 6am", two
    # windows that overlap by two hours, and neither was measured. The real
    # busiest hour is read off the generator telemetry.
    if advice:
        return _pick(
            lang,
            advice[0] + " There is no separate off-peak tariff here: the rate is the "
            "same all day and set monthly, so shifting load saves the network, not your "
            "bill directly.",
            advice[0] + " ولا توجد هنا تعرفة مخفّضة خارج الذروة: السعر واحد طوال اليوم "
            "ويُحدَّد شهرياً، فنقل الاستهلاك يخفّف عن الشبكة لا عن فاتورتك مباشرة.",
        )
    return _pick(
        lang,
        "I do not have enough load data yet to say which hour the network is busiest.",
        "لا تتوفر لدي بيانات حِمل كافية بعد لأحدّد الساعة التي تبلغ فيها الشبكة ذروتها.",
    )


def _reply_tariff(ctx: dict, lang: str, first: str, advice: list[str]) -> str:
    """
    The price of a kilowatt-hour: what this customer was charged, and why it moves.

    The rate on their own invoice leads, because that is the number they can
    check against the paper in their hand. The published pair for the month
    follows as context, not as the answer.
    """
    rate = ctx.get("invoice_rate")
    period = _month_label(ctx.get("invoice_period"), lang)
    base = ctx.get("tariff_base_rate")
    highland = ctx.get("tariff_highland_rate")
    tariff_month = _month_label(ctx.get("tariff_month"), lang)
    lowest, highest = ctx.get("rate_lowest_charged"), ctx.get("rate_highest_charged")
    months = ctx.get("rate_months_on_record")
    diesel = ctx.get("tariff_diesel_price")

    if rate is None and base is None:
        return _pick(
            lang,
            "I do not have the tariff on file for your account, so I cannot quote you a "
            "rate. The figure is printed on your invoice, and the provider's office can "
            "confirm the current month's.",
            "لا تتوفر لدي التعرفة الخاصة بحسابك، فلا أستطيع أن أذكر لك سعراً. الرقم "
            "مطبوع على فاتورتك، ومكتب المزوّد يستطيع تأكيد سعر الشهر الحالي.",
        )

    # With no invoice on the account there is no personal rate to lead with, so
    # the published pair becomes the opening rather than being repeated as
    # context two sentences later.
    if rate is None:
        opening = _pick(
            lang,
            f"The published rates for {tariff_month} are {money(base)} per kWh for the "
            f"ordinary band"
            + (f" and {money(highland)} for zones above 700 m." if highland else "."),
            f"السعران المعلنان لشهر {tariff_month} هما {money(base)} للكيلوواط الساعي "
            f"في النطاق العادي"
            + (f" و{money(highland)} للمناطق فوق 700 متر." if highland else "."),
        )
    else:
        opening = _pick(
            lang,
            f"You were charged {money(rate)} per kWh on your {period} invoice.",
            f"حُوسبت على {money(rate)} للكيلوواط الساعي في فاتورة {period}.",
        )

    why = _pick(
        lang,
        " The rate is not fixed: the Ministry of Energy and Water sets it monthly and it "
        "follows the diesel price, which is why it changes on every bill.",
        " والسعر ليس ثابتاً: وزارة الطاقة والمياه تحدّده شهرياً وهو يتبع سعر المازوت، "
        "ولهذا يتغيّر مع كل فاتورة.",
    )
    if rate is None and diesel:
        why += _pick(
            lang,
            f" That month diesel stood at {money(diesel)} per 20 litres.",
            f" وفي ذلك الشهر بلغ سعر المازوت {money(diesel)} لكل 20 ليتراً.",
        )

    if lowest and highest and months:
        why += _pick(
            lang,
            f" Across the {months} months billed on your account it has moved between "
            f"{money(lowest)} and {money(highest)} per kWh.",
            f" وعلى مدى {months} شهراً مفوتراً على حسابك تراوح بين {money(lowest)} "
            f"و{money(highest)} للكيلوواط الساعي.",
        )

    published = ""
    if rate is not None and base and highland and tariff_month:
        published = _pick(
            lang,
            f" For {tariff_month} the published rates were {money(base)} for the ordinary "
            f"band and {money(highland)} for zones above 700 m"
            + (f", with diesel at {money(diesel)} per 20 litres." if diesel else "."),
            f" ولشهر {tariff_month} كان السعران المعلنان {money(base)} للنطاق العادي "
            f"و{money(highland)} للمناطق فوق 700 متر"
            + (f"، وسعر المازوت {money(diesel)} لكل 20 ليتراً." if diesel else "."),
        )

    closing = _pick(
        lang,
        " It is the same rate at every hour of the day; there is no cheaper night rate.",
        " والسعر نفسه في كل ساعات اليوم؛ لا توجد تعرفة ليلية أرخص.",
    )
    return opening + why + published + closing


def _reply_supply_hours(ctx: dict, lang: str, first: str, advice: list[str]) -> str:
    """
    How many hours a day the zone is fed. Measured, and labelled as an average.

    The distinction in the last sentence is the honest part: the platform holds
    what the generators RAN, not the timetable the office publishes, and those
    are not the same promise.
    """
    hours = ctx.get("supply_hours_per_day")
    zone = ctx.get("zone_name")
    generator = ctx.get("supply_generator_id") or ctx.get("generator_id")
    days = ctx.get("supply_days_on_record")

    if hours is None:
        return _pick(
            lang,
            "I do not have supply hours recorded for your zone, so I cannot tell you how "
            "many hours a day you are fed. The provider's office publishes the schedule.",
            "ليست لدي ساعات تغذية مسجّلة لمنطقتك، فلا أستطيع أن أقول لك كم ساعة يومياً "
            "تصلك الكهرباء. مكتب المزوّد هو من ينشر برنامج التغذية.",
        )

    named_en = f"your zone, {zone}," if zone else "your zone"
    named_ar = f"منطقتك {zone}" if zone else "منطقتك"
    span_en = f" over the {days} days on record" if days else " on record"
    span_ar = f" على مدى {days} يوماً مسجّلاً" if days else " حسب السجل"

    if generator:
        opening_en = (f"Generator {generator} feeds {named_en} and supplied it{span_en} "
                      f"for an average of {hours} hours a day.")
        opening_ar = (f"المولّد {generator} يغذّي {named_ar}، وقد غذّاها{span_ar} بمعدّل "
                      f"{hours} ساعة يومياً.")
    else:
        opening_en = f"{named_en.capitalize()} was supplied{span_en} for an average of {hours} hours a day."
        opening_ar = f"{named_ar} غُذّيت{span_ar} بمعدّل {hours} ساعة يومياً."

    return _pick(
        lang,
        opening_en + " That is the measured average of what the generator actually ran, "
        "not today's schedule: the platform records the running, it does not hold the "
        "daily timetable, so for tonight's hours ask the provider's office.",
        opening_ar + " وهذا معدّل مقاس لما اشتغله المولّد فعلاً، لا برنامج اليوم: المنصة "
        "تسجّل التشغيل ولا تحتفظ بجدول التغذية اليومي، فلمعرفة ساعات هذه الليلة اسأل "
        "مكتب المزوّد.",
    )


def _reply_account(ctx: dict, lang: str, first: str, advice: list[str]) -> str:
    """The customer's own row, read back to them. Every line of it is on file."""
    lines_en: list[str] = [
        f"Your customer number is {ctx['customer_id']}, which is the number the provider "
        f"files everything under."
    ]
    lines_ar: list[str] = [
        f"رقم اشتراكك هو {ctx['customer_id']}، وهو الرقم الذي يحفظ المزوّد كل شيء تحته."
    ]

    on_file_en = [f"name {ctx['name']}", f"plan {ctx['plan']}"]
    on_file_ar = [f"الاسم {ctx['name']}", f"الفئة {ctx['plan']}"]
    if ctx.get("region"):
        on_file_en.append(f"region {ctx['region']}")
        on_file_ar.append(f"المنطقة {ctx['region']}")
    if ctx.get("address"):
        on_file_en.append(f"address {ctx['address']}")
        on_file_ar.append(f"العنوان {ctx['address']}")
    if ctx.get("phone"):
        on_file_en.append(f"phone {ctx['phone']}")
        on_file_ar.append(f"الهاتف {ctx['phone']}")
    if ctx.get("email"):
        on_file_en.append(f"email {ctx['email']}")
        on_file_ar.append(f"البريد {ctx['email']}")

    lines_en.append("On file: " + ", ".join(on_file_en) + ".")
    lines_ar.append("المسجّل لدينا: " + "، ".join(on_file_ar) + ".")

    if ctx.get("meter_id"):
        supply_en = f"Your supply is metered by meter {ctx['meter_id']}"
        supply_ar = f"تغذيتك مقيسة بالعدّاد {ctx['meter_id']}"
        if ctx.get("meter_serial"):
            supply_en += f" (serial {ctx['meter_serial']})"
            supply_ar += f" (تسلسل {ctx['meter_serial']})"
        if ctx.get("ampere_capacity"):
            phase_en = (ctx.get("phase_type") or "").replace("_", " ")
            phase_ar = {"three_phase": "ثلاثي الطور",
                        "single_phase": "أحادي الطور"}.get(ctx.get("phase_type") or "", "")
            supply_en += (f", contracted at {ctx['ampere_capacity']:.0f} amperes"
                          + (f", {phase_en}" if phase_en else ""))
            supply_ar += (f"، والاشتراك {ctx['ampere_capacity']:.0f} أمبير"
                          + (f"، {phase_ar}" if phase_ar else ""))
        if ctx.get("zone_name"):
            supply_en += f", in zone {ctx['zone_name']}"
            supply_ar += f"، في منطقة {ctx['zone_name']}"
        lines_en.append(supply_en + ".")
        lines_ar.append(supply_ar + ".")

    if ctx.get("last_reading_date"):
        read_on_en = _date_label(ctx["last_reading_date"], "en")
        read_on_ar = _date_label(ctx["last_reading_date"], "ar")
        lines_en.append(f"It was last read on {read_on_en}.")
        lines_ar.append(f"وقد قُرئ آخر مرة في {read_on_ar}.")

    lines_en.append(
        "You can correct your name, email, phone and address yourself on the Profile "
        "page. The meter and the contract are changed by the provider."
    )
    lines_ar.append(
        "يمكنك تصحيح اسمك وبريدك وهاتفك وعنوانك بنفسك من صفحة الملف الشخصي. أما "
        "العدّاد والاشتراك فيعدّلهما المزوّد."
    )

    return _pick(lang, " ".join(lines_en), " ".join(lines_ar))


def _reply_bill_breakdown(ctx: dict, lang: str, first: str, advice: list[str]) -> str:
    """
    How the amount was arrived at, to the pound.

    This is also the right answer to "I think my bill is wrong": the arithmetic
    is handed over so it can be checked rather than argued about.
    """
    units = ctx.get("invoice_units")
    rate = ctx.get("invoice_rate")
    fixed = ctx.get("invoice_fixed_charge")
    variable = ctx.get("invoice_variable_charge")
    total = ctx.get("invoice_total")
    period = _month_label(ctx.get("invoice_period"), lang)

    if units is None or rate is None or total is None:
        return _pick(
            lang,
            "I do not have an itemised invoice on file for your account, so I cannot "
            "show you the calculation. Your bills are listed on the Bills page, and the "
            "provider's office can print the breakdown.",
            "لا تتوفر لدي فاتورة مفصّلة على حسابك، فلا أستطيع أن أعرض لك طريقة الاحتساب. "
            "فواتيرك مذكورة في صفحة الفواتير، ومكتب المزوّد يستطيع طباعة التفصيل.",
        )

    return _pick(
        lang,
        f"Your {period} invoice was worked out like this: {units:,.1f} kWh at "
        f"{money(rate)} per kWh comes to {money(variable)}, plus a fixed subscription "
        f"charge of {money(fixed)}, giving {money(total)}. The fixed charge is for the "
        "connection itself and is due whether or not you draw a single kWh, which is why "
        "a quiet month is never zero. Multiply it back yourself if you want to check it.",
        f"احتُسبت فاتورة {period} هكذا: {units:,.1f} kWh بسعر {money(rate)} للكيلوواط "
        f"الساعي تساوي {money(variable)}، يضاف إليها رسم اشتراك ثابت قدره {money(fixed)}، "
        f"فيصبح المجموع {money(total)}. والرسم الثابت هو بدل الوصلة نفسها ويُستحق سواء "
        "استهلكت كيلوواطاً واحداً أم لا، ولهذا لا تكون فاتورة الشهر الهادئ صفراً. "
        "أعد الضرب بنفسك إن أردت التحقق.",
    )


def _reply_history(ctx: dict, lang: str, first: str, advice: list[str]) -> str:
    """The months themselves, listed. Six of them: enough to see a shape."""
    series = ctx.get("monthly_series") or []
    if not series:
        return _pick(
            lang,
            f"I have no consumption history on file for your account yet, {first}.",
            f"لا يوجد لدي سجل استهلاك لحسابك بعد يا {first}.",
        )

    recent = series[-6:]
    listed = "؛ ".join(
        f"{_month_label(month, 'ar')} {total:,.1f}" for month, total in reversed(recent)
    ) if lang == "ar" else "; ".join(
        f"{_month_label(month, 'en')} {total:,.1f}" for month, total in reversed(recent)
    )

    highest = max(recent, key=lambda row: row[1])
    lowest = min(recent, key=lambda row: row[1])

    return _pick(
        lang,
        f"Your last {len(recent)} recorded months, newest first, in kWh: {listed}. The "
        f"highest was {_month_label(highest[0], 'en')} at {highest[1]:,.1f} and the "
        f"lowest {_month_label(lowest[0], 'en')} at {lowest[1]:,.1f}. The whole series is "
        "charted on your Consumption page.",
        f"آخر {len(recent)} أشهر مسجّلة لديك، من الأحدث إلى الأقدم، بالكيلوواط الساعي: "
        f"{listed}. أعلاها {_month_label(highest[0], 'ar')} بـ {highest[1]:,.1f} وأدناها "
        f"{_month_label(lowest[0], 'ar')} بـ {lowest[1]:,.1f}. والسلسلة كاملة مرسومة في "
        "صفحة الاستهلاك.",
    )


def _reply_compare(ctx: dict, lang: str, first: str, advice: list[str]) -> str:
    """
    This customer against the average of their own zone, in the same month.

    Both sides come from the same column of the same table, billed units off
    the invoices, so it is a comparison and not a coincidence. The caveat at
    the end is not modesty: a shop and a flat sit inside that one average.
    """
    mine = ctx.get("invoice_units")
    average = ctx.get("zone_average_kwh")
    count = ctx.get("zone_invoice_count") or 0
    zone = ctx.get("zone_name") or ctx.get("zone_id")
    period = _month_label(ctx.get("invoice_period"), lang)

    # Two different reasons a comparison cannot be made, and they are not
    # interchangeable. A new connection on a busy feeder was told "I do not hold
    # enough billed months for your zone" when the zone had thirty-five
    # subscribers and plenty of months: what was missing was HIS side of it.
    # Blaming the zone for that is a small lie, and it is the kind that sends
    # somebody to the office to ask about the wrong thing.
    if mine is None:
        return _pick(
            lang,
            "You have no billed month yet, so there is nothing of yours to compare "
            "against anyone. Once your first invoice is issued I can set it beside the "
            "average for your zone.",
            "لا يوجد لديك شهر مفوتر بعد، فليس هناك ما يُقارَن من طرفك. وحالما تصدر "
            "فاتورتك الأولى أستطيع أن أضعها إلى جانب معدّل منطقتك.",
        )

    # Under a handful of neighbours an "average" describes individuals, not a
    # group. The minimum is set in config/chatbot.toml and is never below 3.
    if average is None or count < chatbot_config.get().customer.zone_average_min_subscribers:
        return _pick(
            lang,
            "I cannot compare you with anyone: I do not hold enough billed months for "
            "your zone to work out an average worth quoting. What I can show you is your "
            "own history, month by month.",
            "لا أستطيع مقارنتك بأحد: لا تتوفر لدي أشهر مفوترة كافية في منطقتك لأحسب "
            "معدّلاً يستحق الذكر. لكن أستطيع أن أعرض عليك سجلك أنت، شهراً بشهر.",
        )

    gap = ((float(mine) - average) / average * 100) if average else 0.0
    return _pick(
        lang,
        f"In {period} you were billed for {mine:,.1f} kWh. The average across the {count} "
        f"subscribers billed in your zone ({zone}) that month was {average:,.1f} kWh, so "
        f"you are about {abs(gap):.0f}% {'above' if gap > 0 else 'below'} it. Treat that "
        "as a rough bearing rather than a verdict: a shop, a workshop and a two-room flat "
        "all sit inside that one average.",
        f"في {period} فُوترت على {mine:,.1f} kWh. ومعدّل المشتركين المفوترين في منطقتك "
        f"({zone}) ذلك الشهر، وعددهم {count}، كان {average:,.1f} kWh، أي أنك "
        f"{'أعلى' if gap > 0 else 'أدنى'} منه بنحو {abs(gap):.0f}%. وخذ الرقم كمؤشّر عام "
        "لا كحكم: المحل والمشغل والشقة من غرفتين كلها داخل هذا المعدّل الواحد.",
    )


def _reply_password(ctx: dict, lang: str, first: str, advice: list[str]) -> str:
    # This used to say that a reset link is e-mailed. No e-mail is ever sent:
    # there is no mail provider yet (Architecture Section XI). The wording now
    # comes from config/chatbot.toml and sends a locked-out customer to the office.
    return chatbot_config.get().customer.reply("password_help", lang)


def _reply_outage(ctx: dict, lang: str, first: str, advice: list[str]) -> str:
    """
    A cut, a fault, or a complaint. None of which this platform can act on.

    The provider's telephone number is not in any of the supplied files, so it
    is not quoted. Inventing a number here would be the single most damaging
    thing this assistant could do.
    """
    zone = ctx.get("zone_name")
    generator = ctx.get("supply_generator_id") or ctx.get("generator_id")
    hours = ctx.get("supply_hours_per_day")

    where_en = ""
    where_ar = ""
    if not generator and zone and hours:
        where_en = (f" What I can tell you is that your zone, {zone}, has averaged {hours} "
                    "hours a day on record.")
        where_ar = f" وما أستطيع قوله هو أن منطقتك {zone} غُذّيت بمعدّل {hours} ساعة يومياً حسب السجل."
    elif generator:
        where_en = (
            f" What I can tell you is where your supply comes from: generator "
            f"{generator} feeds your zone{f', {zone}' if zone else ''}"
            + (f", which has averaged {hours} hours a day on record." if hours else ".")
        )
        where_ar = (
            f" وما أستطيع قوله هو من أين تأتي تغذيتك: المولّد {generator} يغذّي منطقتك"
            f"{f' {zone}' if zone else ''}"
            + (f"، بمعدّل {hours} ساعة يومياً حسب السجل." if hours else ".")
        )

    return _pick(
        lang,
        f"I cannot report a fault or send anyone out, {first}, and the provider's "
        "telephone number is not in my records, so I will not guess at one. For a cut, "
        "call the office or tell the collector who reads your meter." + where_en +
        " If the whole street is dark it is the generator or the feeder rather than your "
        "own connection, which is worth mentioning when you call.",
        f"لا أستطيع تسجيل عطل ولا إرسال أحد يا {first}، ورقم هاتف المزوّد ليس في سجلاتي، "
        "ولن أخمّن رقماً. عند الانقطاع اتصل بالمكتب أو أبلغ الجابي الذي يقرأ عدّادك." +
        where_ar +
        " وإن كان الشارع كله مظلماً فالمسألة في المولّد أو في الخط لا في وصلتك أنت، "
        "وهذا يستحق الذكر حين تتصل.",
    )


def _reply_account_change(ctx: dict, lang: str, first: str, advice: list[str]) -> str:
    amps = ctx.get("ampere_capacity")
    phase_en = (ctx.get("phase_type") or "").replace("_", " ")
    phase_ar = {"three_phase": "ثلاثي الطور",
                "single_phase": "أحادي الطور"}.get(ctx.get("phase_type") or "", "")
    status = ctx.get("contract_status")
    zone = ctx.get("zone_name")

    current_en = ""
    current_ar = ""
    if amps:
        current_en = (
            f" Yours today: {amps:.0f} amperes"
            + (f", {phase_en}" if phase_en else "")
            + (f", status {status}" if status else "")
            + (f", in zone {zone}" if zone else "")
            + "."
        )
        current_ar = (
            f" واشتراكك اليوم: {amps:.0f} أمبير"
            + (f"، {phase_ar}" if phase_ar else "")
            + (f"، الحالة {status}" if status else "")
            + (f"، في منطقة {zone}" if zone else "")
            + "."
        )

    return _pick(
        lang,
        "Changing the contracted amperes, moving a meter, disconnecting or cancelling are "
        "all changes to the contract, and this platform only reads the contract, it cannot "
        "alter it." + current_en + " Take the change to the provider's office; it will "
        "appear here once they record it.",
        "تغيير عدد الأمبيرات أو نقل العدّاد أو الفصل أو إلغاء الاشتراك كلها تعديلات على "
        "العقد، وهذه المنصة تقرأ العقد فقط ولا تستطيع تعديله." + current_ar +
        " راجع مكتب المزوّد بالتعديل، وسيظهر هنا بمجرد أن يسجّلوه.",
    )


def _reply_discount(ctx: dict, lang: str, first: str, advice: list[str]) -> str:
    rate = ctx.get("invoice_rate")
    rate_en = f" On your last invoice it was {money(rate)} per kWh." if rate else ""
    rate_ar = f" وفي فاتورتك الأخيرة كان {money(rate)} للكيلوواط الساعي." if rate else ""

    return _pick(
        lang,
        f"I cannot give a discount or change a price, {first}. The rate per kWh is set "
        "monthly and applies to every subscriber on the same band, so it is not mine to "
        "move and not the office's either." + rate_en + " Two things I can do instead. If "
        "you think a bill is wrong, ask me to explain your bill and I will show you the "
        "arithmetic, kWh by kWh, so you can check it. If the problem is timing rather "
        "than the amount, arranging that is a conversation with the provider's office.",
        f"لا أستطيع منح حسم أو تغيير سعر يا {first}. سعر الكيلوواط يُحدَّد شهرياً ويُطبَّق "
        "على كل المشتركين في النطاق نفسه، فهو ليس بيدي ولا بيد المكتب." + rate_ar +
        " لكن أستطيع أمرين. إن كنت ترى أن الفاتورة غير صحيحة، اطلب مني شرح فاتورتك "
        "وسأعرض لك الحساب كيلوواطاً بكيلوواط لتتحقق منه. وإن كانت المشكلة في الموعد لا "
        "في المبلغ، فترتيب ذلك يكون مع مكتب المزوّد.",
    )


def _reply_faq(ctx: dict, lang: str, first: str, advice: list[str]) -> str:
    """
    Nothing matched.

    The old reply offered four topics and closed with "What would you like to
    explore?", which reads as a menu rather than an admission. Saying that the
    question was not understood comes first, because it is the true part. The
    list of what it can answer follows config/chatbot.toml.
    """
    offered = _offered(_FAQ_TOPICS)
    if not offered:
        return chatbot_config.get().customer.reply("out_of_scope", lang)
    en = [e for e, _ in offered]
    ar = [a for _, a in offered]
    if len(en) > 1:
        en[-1] = "and " + en[-1]
    reply = _pick(
        lang,
        f"I did not follow that one, {first}. I can answer questions about "
        + ", ".join(en) + ". Ask me in Arabic or in English.",
        f"لم أفهم سؤالك يا {first}. أستطيع الإجابة عن "
        + ar[0] + "".join("، و" + a for a in ar[1:]) + ". اسألني بالعربية أو بالإنجليزية.",
    )
    topics = chatbot_config.get().customer.topics
    if ctx["latest_period_month"] and "payments" in topics and "consumption" in topics:
        period = _month_label(ctx["latest_period_month"], lang)
        reply += _pick(
            lang,
            f" For reference: your balance is {money(ctx['balance'])} and you used "
            f"{ctx['latest_period_kwh']} kWh in {period}.",
            f" وللعلم: رصيدك {money(ctx['balance'])} واستهلكت {ctx['latest_period_kwh']} "
            f"kWh في {period}.",
        )
    return reply


_HANDLERS: dict[str, Callable[[dict, str, str, list[str]], str]] = {
    "greeting": _reply_greeting,
    "capabilities": _reply_capabilities,
    "forecast": _reply_forecast,
    "cooling": _reply_cooling,
    "billing": _reply_billing,
    "solar": _reply_solar,
    "last_payment": _reply_last_payment,
    "payment": _reply_payment,
    "consumption": _reply_consumption,
    "savings": _reply_savings,
    "peak": _reply_peak,
    "tariff": _reply_tariff,
    "supply_hours": _reply_supply_hours,
    "account": _reply_account,
    "bill_breakdown": _reply_bill_breakdown,
    "history": _reply_history,
    "compare": _reply_compare,
    "password": _reply_password,
    "outage": _reply_outage,
    "account_change": _reply_account_change,
    "discount": _reply_discount,
    "faq": _reply_faq,
}


def _rule_based_reply(
    message: str,
    ctx: dict,
    advice: list[str] | None = None,
    lang: str = "en",
    intent: str | None = None,
) -> str:
    intent = intent or _detect_intent(message)
    first_name = (ctx["name"] or "there").split()[0]
    return _HANDLERS.get(intent, _reply_faq)(ctx, lang, first_name, advice or [])


# ---------------------------------------------------------------------------
# LLM path
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """You are the customer support assistant for an electricity provider.
You help only with these topics: {topics}. For anything else, reply with this
message in the customer's language. English: "{out_of_scope_en}" Arabic: "{out_of_scope_ar}"

Rules:
- Answer only from the account context provided. Never invent figures.
- Discuss only this customer's own account. Never discuss another customer or give
  any figure that is not in the account context.{zone_rule}
- ANSWER IN THE LANGUAGE THE CUSTOMER WROTE IN. Most write Arabic or English. Keep
  the units "kWh" and "LBP" in Latin letters in every language, as the interface does,
  and use Western digits.
- If asked something outside electricity service, politely redirect.
- Be concise (2-4 sentences), warm and specific. Use the customer's real numbers.
- Amounts are in LEBANESE POUNDS (LBP), consumption in kWh. Write amounts with
  thousands separators and no decimals, e.g. "14,761,123 LBP". Never a dollar sign.
- Meters are read once a MONTH, so the smallest period you can speak about is a
  month, and the newest one may be several weeks old. Say which month a figure is
  for. Never imply a figure is from today.
- There is no off-peak tariff: the rate is the same all day and is set monthly.
  If asked about peak hours, use the network peak given in the context and say
  that shifting load helps the network rather than the customer's own bill.
- The per-kWh rate the customer paid is `invoice_rate`, taken from their own invoice.
  Quote that rather than deriving a rate from the zone's altitude band.
- Supply hours in the context are a MEASURED AVERAGE of what the generator ran, not
  a published schedule. Never present them as tonight's timetable.
- You cannot take a payment, apply a discount, change a contract or report a fault,
  and no telephone number for the provider exists in your context. Say plainly what
  you cannot do and point at the provider's office. Never invent a phone number.
"""


def _system_prompt() -> str:
    """The instructions above, filled in from config/chatbot.toml."""
    policy = chatbot_config.get().customer
    zone_rule = (" If the context holds the average of the customer's zone, you may quote it "
                 "as an average, never as any one person's figure." if policy.shares("zone_average") else "")
    return _SYSTEM_PROMPT.format(
        topics="; ".join(chatbot_config.TOPIC_LABELS[t] for t in policy.topics) or "none",
        out_of_scope_en=policy.reply("out_of_scope", "en"),
        out_of_scope_ar=policy.reply("out_of_scope", "ar"),
        zone_rule=zone_rule,
    )


def _llm_reply(message: str, ctx: dict, history: list[dict] | None = None) -> str | None:
    """Return an LLM answer, or None to fall back to the intent engine."""
    if not chatbot_config.get().customer.use_language_model or not settings.OPENAI_API_KEY:
        return None

    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        context_lines = "\n".join(f"- {key}: {value}" for key, value in ctx.items())

        messages = [
            {"role": "system", "content": _system_prompt()},
            {"role": "system", "content": f"Account context:\n{context_lines}"},
        ]
        for turn in (history or [])[-6:]:
            messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": message})

        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=messages,
            max_tokens=350,
            temperature=0.4,
        )
        return response.choices[0].message.content
    except Exception as exc:  # pragma: no cover - network path
        logger.warning("LLM call failed, using rule-based assistant: %s", exc)
        return None


# ---------------------------------------------------------------------------
# What config/chatbot.toml keeps private
# ---------------------------------------------------------------------------
# A question that is only about one of these facts gets the "not shared" reply
# when the file switches the fact off.
_NEEDS_SHARE = {"supply_hours": "supply_hours", "compare": "zone_average", "peak": "network_peak"}

# The context keys that carry each shared fact. None of them is the customer's
# own record: their own invoices, rate, readings and bills are always theirs.
_SHARED_KEYS: dict[str, tuple[str, ...]] = {
    "published_tariff": ("tariff_month", "tariff_base_rate", "tariff_highland_rate"),
    "diesel_price": ("tariff_diesel_price",),
    "zone_average": ("zone_average_kwh", "zone_invoice_count"),
    "supply_hours": ("supply_hours_per_day", "supply_days_on_record"),
    "generator": ("generator_id", "supply_generator_id"),
    "network_peak": ("network_peak_advice",),
}


def _withhold(ctx: dict, policy: chatbot_config.CustomerAssistant) -> dict:
    """The context with every fact the configuration keeps private taken out."""
    kept = dict(ctx)
    for fact, keys in _SHARED_KEYS.items():
        if not policy.shares(fact):
            for key in keys:
                kept.pop(key, None)
    # An average over too few subscribers describes individuals: drop it.
    if (kept.get("zone_invoice_count") or 0) < policy.zone_average_min_subscribers:
        kept.pop("zone_average_kwh", None)
        kept.pop("zone_invoice_count", None)
    return kept


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def answer(
    db: Session,
    customer: Customer,
    message: str,
    history: list[dict] | None = None,
) -> str:
    """Produce the assistant's reply for POST /chat/message."""
    lang = _language_of(message, customer)
    policy = chatbot_config.get().customer

    # The limits in config/chatbot.toml come first. A question in a topic that
    # is switched off, or one that is only about a fact the file keeps private,
    # is answered without reading anything.
    intent = _detect_intent(message)
    if not policy.allows(intent):
        return policy.reply("out_of_scope", lang)
    needed = _NEEDS_SHARE.get(intent)
    if needed and not policy.shares(needed):
        return policy.reply("not_shared", lang)

    ctx = build_customer_context(db, customer)

    # The supply-side facts: zone, generator, meter, contract, tariff, invoice.
    # Failing to load them must not take the chatbot down with it, a database
    # holding only the customer-side tables is a supported shape, so the
    # replies that need them check, and the ones that do not are unaffected.
    try:
        ctx.update(build_service_context(db, customer))
    except Exception:                               # pragma: no cover
        logger.warning("Service context unavailable; answering without it", exc_info=True)

    # A month named in the question re-points the whole context at that month,
    # but only for the questions that are about a month that has already
    # happened. "Will my bill be high in August?" is a forecast, and scoping it
    # to last August would answer a question nobody asked.
    asked_month = _named_month(message) if intent in _MONTH_SCOPED else None
    if asked_month:
        try:
            ctx.update(scope_to_month(db, customer, ctx, *asked_month))
        except Exception:                           # pragma: no cover
            logger.warning("Could not scope to the named month", exc_info=True)

    # Facts that are not the customer's own records leave the context here, so
    # no reply and no language model can see what the file keeps private.
    ctx = _withhold(ctx, policy)

    # Measured from the generator telemetry, not invented here. Failing to load
    # it must not take the chatbot down with it: the reply then simply says it
    # does not know which hours are busiest, which is true.
    #
    # Asked for in the customer's language, because these two sentences are
    # quoted verbatim inside the peak and savings replies: an Arabic answer with
    # an English sentence bolted into the middle of it is worse than either.
    advice: list[str] = []
    if policy.shares("network_peak"):
        try:
            advice = peak_advice.advice_for_customer(db, lang)
        except Exception:                           # pragma: no cover
            logger.warning("Peak advice unavailable; answering without it", exc_info=True)
            advice = []

    if advice:
        # The LLM prompt is written in English and the model is asked to reply
        # in the customer's language, so the context it reasons over stays
        # English regardless of who is asking. Recomputed only when there is an
        # LLM to read it: `analyse` sweeps the whole telemetry table through
        # pandas, and paying for that twice per message to fill a field nobody
        # reads is not a trade worth making.
        if lang == "en" or settings.OPENAI_API_KEY:
            english = advice if lang == "en" else peak_advice.advice_for_customer(db)
            ctx = {**ctx, "network_peak_advice": " ".join(english)}

    reply = (_llm_reply(message, ctx, history)
             or _rule_based_reply(message, ctx, advice, lang, intent))
    # An Arabic reply shows its amounts and kWh figures the way every card and
    # translated sentence does ("24,954,137 LBP", not "LBP 24,954,137").
    return isolate_figures(reply, lang)


def suggest_title(message: str) -> str:
    """Short conversation title for the chat sidebar."""
    cleaned = " ".join(message.strip().split())
    return cleaned[:47] + "..." if len(cleaned) > 50 else cleaned or "New conversation"
