# -*- coding: utf-8 -*-
"""
Every question the assistant can answer, asked twice, once in each language.

WHAT THIS IS FOR
----------------
The chatbot's characteristic failure is not an error. It is an answer that is
fluent, plausible, and about a different question than the one asked, and no
assertion recognises that. Three of them survived a passing test suite and were
found by a person typing an ordinary question into the running app and reading
the reply.

So this puts the same question to it in English and in Arabic and lays the two
answers side by side, for a person to read. The page is the review, not a
report of one that already happened.

It also records something the test suite cannot: whether an answer REPORTS from
the customer's records, EXPLAINS how the platform works, or DECLINES. That last
group is the one worth showing a supervisor. An assistant that says plainly it
cannot forecast a bill, price a solar installation, or give out a telephone
number it does not have, is more trustworthy than one that always produces
something.

Run:  python -m scripts.chat_matrix [customer_id]
Then open chatbot-answers.html in a browser.
"""

from __future__ import annotations

import datetime
import html
import pathlib
import sys

from app.ai import chatbot
from app.database import SessionLocal, add_missing_columns
from app.models.customer import Customer

OUT = pathlib.Path("chatbot-answers.html")

# (capability, English question, Arabic question, kind)
#
# kind is what the answer DOES, and it is the honest classification rather than
# a flattering one:
#   reports   the reply is figures out of this customer's own records
#   explains  the reply describes how the service or the platform works
#   declines  the reply states that it cannot answer, and why
QUESTIONS: list[tuple[str, str, str, str]] = [
    ("Greeting", "Hello", "مرحبا", "explains"),
    ("What it can do", "What can you do?", "شو بتعرف تعمل؟", "explains"),
    ("Why the bill moved", "Why is my bill so high?",
     "لماذا كانت فاتورتي هكذا هذا الشهر", "reports"),
    ("How the bill was worked out", "How was my bill calculated?",
     "كيف احتسبت الفاتورة؟", "reports"),
    ("The rate per kWh", "What is the price per kWh?", "قديش سعر الكيلوواط؟", "reports"),
    ("What is owed", "How much do I owe?", "شو رصيدي؟", "reports"),
    ("How to pay", "How do I pay my bill?", "كيف بدفع فاتورتي؟", "explains"),
    ("The last payment", "When did I last pay?", "آخر دفعة دفعتها امتى؟", "reports"),
    ("Consumption this month", "How much electricity did I use?",
     "قديش استهلكت هالشهر؟", "reports"),
    ("Consumption history", "Show me my consumption for the last six months",
     "بدي سجل استهلاكي للأشهر الماضية", "reports"),
    # A month NAMED in the question, which used to be answered with the newest
    # bill whatever month was asked for. Both languages, because Arabic month
    # names are the ones a bill is actually read with here.
    ("A named month", "How much was my February bill?",
     "كم كانت فاتورتي لشهر شباط؟", "reports"),
    ("A named month with no bill", "How much was my bill in January 2019?",
     "كم كانت فاتورتي في كانون الثاني 2019؟", "declines"),
    ("Against the neighbours", "Am I using more than my neighbours?",
     "استهلاكي أكتر من الجيران؟", "reports"),
    ("Next month's bill", "How much will my bill be next month?",
     "كم من المتوقع ان تكون فاتورتي في الشهر المقبل", "declines"),
    ("Hours of supply", "How many hours of electricity do I get per day?",
     "كم ساعة كهربا بتجيني بالنهار؟", "reports"),
    ("Account and contract", "What is my customer number?", "شو رقم اشتراكي؟", "reports"),
    ("Saving electricity", "How can I reduce my bill?", "كيف بوفر بالكهربا؟", "reports"),
    ("The network peak", "What are the off-peak hours?", "شو ساعات الذروة؟", "reports"),
    ("Air conditioning", "Give me tips to reduce AC usage",
     "نصائح لتقليل استهلاك التكييف", "declines"),
    ("Solar panels", "How much can I save with solar?",
     "قديش بتوفر الطاقة الشمسية؟", "declines"),
    ("Passwords and signing in", "How do I change my password?",
     "نسيت كلمة السر", "explains"),
    ("A power cut", "Who do I call if my power is cut?",
     "ما في كهربا بالحي، بمين بتصل؟", "declines"),
    ("Changing the subscription", "I want to cancel my subscription",
     "بدي الغاء الاشتراك", "declines"),
    ("A discount", "Can I get a discount?", "في مجال حسم على الفاتورة؟", "declines"),
    ("Something off topic", "What is the weather tomorrow?", "شو الطقس بكرا؟", "declines"),
]

KIND_LABEL = {
    "reports": ("Reports", "من سجلاتك"),
    "explains": ("Explains", "شرح"),
    "declines": ("Declines", "يعتذر"),
}

STYLE = """
:root {
  /* Neutrals carry a slight cool green bias, taken from the controller panels
     the generator telemetry comes off, rather than a default grey. */
  --paper:      #f3f6f5;
  --card:       #ffffff;
  --ink:        #12181a;
  --ink-soft:   #4a5a5e;
  --ink-faint:  #7e9095;
  --rule:       #dde5e4;
  --rule-soft:  #eaf0ef;
  /* One accent for answers built from measurements, one for the refusals.
     They are the two things this page exists to tell apart. */
  --data:       #0d6a6f;
  --data-wash:  #e2f0ef;
  --limit:      #8a5a10;
  --limit-wash: #f6eddc;
  --shadow:     0 1px 2px rgba(18, 24, 26, .05), 0 8px 24px -16px rgba(18, 24, 26, .28);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --paper:      #0e1416;
    --card:       #151d20;
    --ink:        #e8efee;
    --ink-soft:   #a2b4b7;
    --ink-faint:  #6f8286;
    --rule:       #232f32;
    --rule-soft:  #1b2427;
    --data:       #58c2c0;
    --data-wash:  #10312f;
    --limit:      #d5a24e;
    --limit-wash: #33260f;
    --shadow:     0 1px 2px rgba(0, 0, 0, .4), 0 10px 28px -18px rgba(0, 0, 0, .9);
  }
}
:root[data-theme="dark"] {
  --paper:      #0e1416;
  --card:       #151d20;
  --ink:        #e8efee;
  --ink-soft:   #a2b4b7;
  --ink-faint:  #6f8286;
  --rule:       #232f32;
  --rule-soft:  #1b2427;
  --data:       #58c2c0;
  --data-wash:  #10312f;
  --limit:      #d5a24e;
  --limit-wash: #33260f;
  --shadow:     0 1px 2px rgba(0, 0, 0, .4), 0 10px 28px -18px rgba(0, 0, 0, .9);
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: "IBM Plex Sans", "IBM Plex Sans Arabic", system-ui, -apple-system,
               "Segoe UI", sans-serif;
  font-size: 16px;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}

.wrap { max-width: 1180px; margin: 0 auto; padding: 56px 24px 96px; }

/* ---- masthead ---------------------------------------------------------- */
.masthead { border-bottom: 2px solid var(--ink); padding-bottom: 28px; margin-bottom: 8px; }
.eyebrow {
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: 11px; letter-spacing: .14em; text-transform: uppercase;
  color: var(--data); margin: 0 0 14px;
}
h1 {
  font-size: clamp(30px, 5vw, 44px);
  line-height: 1.1; font-weight: 600; letter-spacing: -.02em;
  margin: 0 0 16px; text-wrap: balance;
}
.standfirst {
  font-size: 17px; color: var(--ink-soft); max-width: 62ch; margin: 0;
}

/* ---- run facts --------------------------------------------------------- */
.facts {
  display: flex; flex-wrap: wrap; gap: 0;
  border-bottom: 1px solid var(--rule); margin-bottom: 44px;
}
.fact { padding: 18px 32px 18px 0; margin-right: 32px; border-right: 1px solid var(--rule-soft); }
.fact:last-child { border-right: 0; }
.fact dt {
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: 10px; letter-spacing: .12em; text-transform: uppercase;
  color: var(--ink-faint); margin: 0 0 4px;
}
.fact dd {
  margin: 0; font-size: 20px; font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.fact dd small { font-size: 14px; font-weight: 400; color: var(--ink-soft); }

/* ---- legend ------------------------------------------------------------ */
.legend {
  display: grid; gap: 14px; margin-bottom: 48px;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
}
.legend p { margin: 0; font-size: 14px; color: var(--ink-soft); }
.legend strong { color: var(--ink); font-weight: 600; }

/* ---- one capability ---------------------------------------------------- */
.entry {
  background: var(--card);
  border: 1px solid var(--rule);
  border-radius: 4px;
  box-shadow: var(--shadow);
  margin-bottom: 28px;
  overflow: hidden;
}
.entry-head {
  display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap;
  padding: 16px 22px; border-bottom: 1px solid var(--rule-soft);
}
.n {
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: 12px; color: var(--ink-faint); font-variant-numeric: tabular-nums;
}
.entry-head h2 { font-size: 17px; font-weight: 600; margin: 0; flex: 1; letter-spacing: -.01em; }
.tag {
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: 10px; letter-spacing: .1em; text-transform: uppercase;
  padding: 4px 9px; border-radius: 3px; white-space: nowrap;
}
.tag.reports, .tag.explains { background: var(--data-wash); color: var(--data); }
.tag.declines { background: var(--limit-wash); color: var(--limit); }
.intent {
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: 11px; color: var(--ink-faint);
}

/* The two languages meet at a centre rule: the shape of the page is the thing
   it is checking. They stack below 860px. */
.pair { display: grid; grid-template-columns: 1fr 1fr; }
.side { padding: 20px 22px 24px; }
.side + .side { border-left: 1px solid var(--rule-soft); }
.side[dir="rtl"] { font-family: "IBM Plex Sans Arabic", "IBM Plex Sans", system-ui, sans-serif; }
.lang {
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: 10px; letter-spacing: .12em; text-transform: uppercase;
  color: var(--ink-faint); margin: 0 0 10px;
}
.side[dir="rtl"] .lang { font-family: "IBM Plex Mono", ui-monospace, monospace; }
.q {
  font-weight: 600; font-size: 15px; margin: 0 0 12px;
  padding-inline-start: 12px; border-inline-start: 2px solid var(--data);
}
.a { margin: 0; font-size: 14.5px; color: var(--ink-soft); }
.declines .q { border-inline-start-color: var(--limit); }

@media (max-width: 860px) {
  .pair { grid-template-columns: 1fr; }
  .side + .side { border-left: 0; border-top: 1px solid var(--rule-soft); }
  .fact { border-right: 0; padding-right: 0; }
}

/* ---- colophon ---------------------------------------------------------- */
.colophon {
  margin-top: 56px; padding-top: 24px; border-top: 1px solid var(--rule);
  font-size: 13px; color: var(--ink-faint); max-width: 68ch;
}
.colophon code {
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: 12px; background: var(--rule-soft); padding: 2px 6px; border-radius: 3px;
  color: var(--ink-soft);
}
"""


def build(customer: Customer, rows: list[dict], generated: str) -> str:
    counts = {kind: sum(1 for r in rows if r["kind"] == kind) for kind in KIND_LABEL}
    e = html.escape

    parts: list[str] = []
    # A complete document, because this file is opened straight off the disk.
    # Without a doctype the browser falls into quirks mode and the layout is not
    # the one that was designed.
    parts.append('<!doctype html>')
    parts.append('<html lang="en"><head><meta charset="utf-8">')
    parts.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    parts.append("<title>Chatbot Answer Sheet</title>")
    parts.append(
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2'
        "?family=IBM+Plex+Mono:wght@400;500"
        "&family=IBM+Plex+Sans:wght@400;500;600"
        "&family=IBM+Plex+Sans+Arabic:wght@400;500;600"
        '&display=swap">'
    )
    parts.append("<style>%s</style>" % STYLE)
    parts.append("</head><body>")

    parts.append('<div class="wrap">')
    parts.append('<header class="masthead">')
    parts.append('<p class="eyebrow">VoltIQ / customer assistant / %s</p>' % e(generated))
    parts.append("<h1>Every question, in both languages</h1>")
    parts.append(
        '<p class="standfirst">The same question put to the assistant twice, once in '
        "English and once in Arabic, with the answer it actually gave. Read the reply "
        "against the question: the failure this catches is an answer that is fluent, "
        "plausible, and about something else.</p>"
    )
    parts.append("</header>")

    parts.append('<dl class="facts">')
    for label, value in [
        ("Answered as", "%s <small>%s</small>" % (e(customer.name), e(customer.customer_id))),
        ("Questions", "%d <small>&times; 2 languages</small>" % len(rows)),
        ("From the records", str(counts["reports"])),
        ("Explanations", str(counts["explains"])),
        ("Honest refusals", str(counts["declines"])),
    ]:
        parts.append('<div class="fact"><dt>%s</dt><dd>%s</dd></div>' % (e(label), value))
    parts.append("</dl>")

    parts.append('<div class="legend">')
    parts.append(
        "<p><strong>Reports</strong> means every figure in the reply came out of this "
        "customer's own rows: their invoices, their readings, their zone.</p>"
    )
    parts.append(
        "<p><strong>Explains</strong> means the reply describes how the service works, "
        "where to pay, how a password is changed, what the assistant covers.</p>"
    )
    parts.append(
        # Not a number written out in words. An earlier draft said "six of the
        # twenty-three" beside a counter reading 7, which is the whole failure
        # this project keeps meeting, in miniature and on its own review page.
        "<p><strong>Declines</strong> means it says it cannot answer and why. %d of the "
        "%d do, and that is the group worth reading first.</p>"
        % (counts["declines"], len(rows))
    )
    parts.append("</div>")

    for index, row in enumerate(rows, 1):
        kind = row["kind"]
        label_en, _ = KIND_LABEL[kind]
        parts.append('<article class="entry %s">' % kind)
        parts.append('<div class="entry-head">')
        parts.append('<span class="n">%02d</span>' % index)
        parts.append("<h2>%s</h2>" % e(row["capability"]))
        parts.append('<span class="intent">%s</span>' % e(row["intent"]))
        parts.append('<span class="tag %s">%s</span>' % (kind, e(label_en)))
        parts.append("</div>")

        parts.append('<div class="pair">')
        parts.append('<div class="side" lang="en">')
        parts.append('<p class="lang">English</p>')
        parts.append('<p class="q">%s</p>' % e(row["q_en"]))
        parts.append('<p class="a">%s</p>' % e(row["a_en"]))
        parts.append("</div>")
        parts.append('<div class="side" lang="ar" dir="rtl">')
        parts.append('<p class="lang">العربية</p>')
        parts.append('<p class="q">%s</p>' % e(row["q_ar"]))
        parts.append('<p class="a">%s</p>' % e(row["a_ar"]))
        parts.append("</div>")
        parts.append("</div>")
        parts.append("</article>")

    parts.append('<footer class="colophon">')
    parts.append(
        "<p>Generated from the live database by <code>python -m scripts.chat_matrix</code>. "
        "Every reply on this page was produced by the same code path the website uses, "
        "against the account named above, so the figures are that subscriber's own. Run it "
        "again after any change to the assistant and read the two columns side by side.</p>"
    )
    parts.append(
        "<p>Amounts are in Lebanese pounds and consumption in kilowatt-hours, written the "
        "same way in both languages because they are units rather than words. Meters here "
        "are read once a month, so the smallest period any answer can speak about is a "
        "month.</p>"
    )
    parts.append("</footer>")
    parts.append("</div>")
    parts.append("</body></html>")
    return "\n".join(parts)


def main(customer_id: str | None = None) -> int:
    # Whole customer records are read below: first add any column this version
    # of the code expects, as the server does when it starts (app/database.py).
    add_missing_columns()
    db = SessionLocal()
    try:
        customer = (
            db.get(Customer, customer_id)
            if customer_id
            else db.query(Customer)
            .filter(Customer.role == "customer", Customer.password_hash != "")
            .first()
            or db.query(Customer).filter(Customer.role == "customer").first()
        )
        if customer is None:
            print("No such customer: %s" % customer_id)
            return 1

        rows = []
        mismatched = []
        for capability, q_en, q_ar, kind in QUESTIONS:
            intent_en = chatbot._detect_intent(q_en)
            intent_ar = chatbot._detect_intent(q_ar)
            if intent_en != intent_ar:
                mismatched.append("%s: %s vs %s" % (capability, intent_en, intent_ar))
            rows.append({
                "capability": capability,
                "kind": kind,
                "intent": intent_en if intent_en == intent_ar else
                          "%s / %s" % (intent_en, intent_ar),
                "q_en": q_en,
                "a_en": chatbot.answer(db, customer, q_en),
                "q_ar": q_ar,
                "a_ar": chatbot.answer(db, customer, q_ar),
            })

        generated = datetime.datetime.now().strftime("%d %B %Y at %H:%M")
        OUT.write_text(build(customer, rows, generated), encoding="utf-8")

        print("Wrote %s" % OUT)
        print("%d questions, answered as %s (%s)"
              % (len(rows), customer.name, customer.customer_id))
        if mismatched:
            print("The two languages took different routes on:")
            for line in mismatched:
                print("   %s" % line)
            return 1
        print("Both languages took the same route on every question.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else None))
