"""
Ask the assistant everything a subscriber might ask, and print what it says.

Not a pass/fail test. The failure this catches is an answer that is fluent and
about the wrong subject, and no assertion recognises that, a person reading
the intent beside the reply does. What it does assert is the two things that
CAN be checked mechanically: that an Arabic question is answered in Arabic, and
that nothing falls through to the catch-all unless it should.

Run: python -m scripts.chat_battery [customer_id]
"""

from __future__ import annotations

import sys

from app.ai import chatbot
from app.database import SessionLocal, add_missing_columns
from app.models.customer import Customer

# (question, the intent it should reach). "faq" means the catch-all is the
# right answer, which is true only for something genuinely off-topic.
QUESTIONS: list[tuple[str, str]] = [
    # --- English, the account -------------------------------------------------
    ("Hello", "greeting"),
    ("What can you do?", "capabilities"),
    ("Why is my bill so high?", "billing"),
    ("How much do I owe?", "payment"),
    ("How do I pay my bill?", "payment"),
    ("When did I last pay?", "last_payment"),
    ("How much electricity did I use?", "consumption"),
    ("Show me my consumption for the last six months", "history"),
    ("Am I using more than my neighbours?", "compare"),
    ("How was my bill calculated?", "bill_breakdown"),
    ("What is the fixed charge on my bill?", "bill_breakdown"),
    ("What is the price per kWh?", "tariff"),
    ("Why does the rate change every month?", "tariff"),
    ("How many hours of electricity do I get per day?", "supply_hours"),
    ("What is my customer number?", "account"),
    ("What is my address on file?", "account"),
    ("How many amperes am I subscribed for?", "account"),
    ("When was my meter last read?", "account"),
    ("How can I reduce my bill?", "savings"),
    ("What are the off-peak hours?", "peak"),
    ("How much can I save with solar?", "solar"),
    ("How much will my bill be next month?", "forecast"),
    ("Give me tips to reduce AC usage", "cooling"),
    # --- English, the things it cannot do ------------------------------------
    ("How do I change my password?", "password"),
    ("I forgot my password and cannot sign in", "password"),
    ("Who do I call if my power is cut?", "outage"),
    ("There is no electricity in my street", "outage"),
    ("Can I get a discount?", "discount"),
    ("I want to cancel my subscription", "account_change"),
    ("I want to increase my amperes", "account_change"),
    ("What is the weather tomorrow?", "faq"),
    # --- Arabic ---------------------------------------------------------------
    ("مرحبا", "greeting"),
    ("شو بتعرف تعمل؟", "capabilities"),
    ("شو رصيدي؟", "payment"),
    ("كيف بدفع فاتورتي؟", "payment"),
    ("ليش فاتورتي غالية؟", "billing"),
    ("لماذا كانت فاتورتي هكذا هذا الشهر", "billing"),
    # A missing letter, which is what a phone keyboard produces. The Arabic
    # keys are stems for exactly this reason.
    ("لماذا كانت فاتورني هكذا هذا الشهر", "billing"),
    ("قديش سعر الكيلوواط؟", "tariff"),
    ("كم ساعة كهربا بتجيني بالنهار؟", "supply_hours"),
    ("قديش استهلكت هالشهر؟", "consumption"),
    ("بدي سجل استهلاكي للأشهر الماضية", "history"),
    ("كيف احتسبت الفاتورة؟", "bill_breakdown"),
    ("شو رقم اشتراكي؟", "account"),
    ("وين عنواني المسجل عندكم؟", "account"),
    ("آخر دفعة دفعتها امتى؟", "last_payment"),
    ("كيف بوفر بالكهربا؟", "savings"),
    ("شو ساعات الذروة؟", "peak"),
    ("نسيت كلمة السر", "password"),
    ("ما في كهربا بالحي، بمين بتصل؟", "outage"),
    ("في مجال حسم على الفاتورة؟", "discount"),
    ("بدي الغاء الاشتراك", "account_change"),
    ("قديش بتوفر الطاقة الشمسية؟", "solar"),
    ("كم من المتوقع ان تكون فاتورتي في الشهر المقبل", "forecast"),
    ("نصائح لتقليل استهلاك التكييف", "cooling"),
    ("كم كانت فاتورتي لشهر حزيران", "billing"),
]


def main(customer_id: str | None = None) -> int:
    # Whole customer records are read below: first add any column this version
    # of the code expects, as the server does when it starts (app/database.py).
    add_missing_columns()
    db = SessionLocal()
    try:
        customer = (
            db.get(Customer, customer_id)
            if customer_id
            else db.query(Customer).filter(Customer.role == "customer").first()
        )
        if customer is None:
            print(f"No such customer: {customer_id}")
            return 1

        print(f"Signed in as {customer.customer_id} ({customer.name})\n")

        wrong_intent: list[str] = []
        wrong_language: list[str] = []

        for question, expected in QUESTIONS:
            detected = chatbot._detect_intent(question)
            reply = chatbot.answer(db, customer, question)

            flag = "  " if detected == expected else "!!"
            if detected != expected:
                wrong_intent.append(f"{question}  ->  {detected}, expected {expected}")

            asked_in_arabic = chatbot._ARABIC_TEXT.search(question) is not None
            answered_in_arabic = chatbot._ARABIC_TEXT.search(reply) is not None
            if asked_in_arabic != answered_in_arabic:
                wrong_language.append(question)
                flag = "!!"

            print(f"{flag} [{detected}] {question}")
            print(f"      {reply}\n")

        print("=" * 70)
        print(f"{len(QUESTIONS)} questions, "
              f"{len(QUESTIONS) - len(wrong_intent)} routed as expected")
        for line in wrong_intent:
            print(f"  intent   {line}")
        for line in wrong_language:
            print(f"  language {line}")
        return 1 if wrong_intent or wrong_language else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else None))
