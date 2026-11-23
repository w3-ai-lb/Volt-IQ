# -*- coding: utf-8 -*-
"""
Which chatbot file is this backend actually running, and what does it say?

WHY THIS EXISTS
---------------
The Arabic answers were written, tested and delivered, and the running app kept
replying in English. Every explanation for that is a different fix, and from the
outside they look identical:

  * the new file was never copied into this project
  * it was copied somewhere else, into a second copy of the project
  * it was copied correctly and the server was not restarted, so Python is still
    serving the module it loaded at startup
  * an OpenAI key is configured, so the answer is coming from the model rather
    than from this file at all

So this asks the backend itself. It imports the chatbot exactly the way the API
does, prints the full path of the file that import resolved to, the date on it,
and whether it is the new version, then puts real questions to it.

The answers go to a FILE rather than to the screen. The Windows console usually
runs a codepage that cannot print Arabic, and would either show ????? or stop
with an error, which would look like one more bug.

Run:  python -m scripts.check_chatbot
Then open chatbot-check.txt in Notepad.
"""

from __future__ import annotations

import datetime
import inspect
import pathlib
import sys

OUT = pathlib.Path("chatbot-check.txt")

QUESTIONS = [
    "شو بتعرف تعمل؟",
    "لماذا كانت فاتورتي هكذا هذا الشهر",
    "كم اوفر اذا استخدمة الطاقه الشمسيه",
    "قديش سعر الكيلوواط؟",
    "كم ساعة كهربا بتجيني بالنهار؟",
    "شو رقم اشتراكي؟",
    "Why is my bill so high?",
]


def main() -> int:
    lines: list[str] = []

    def say(text: str = "") -> None:
        lines.append(text)

    from app.ai import chatbot
    from app.config import settings
    from app.database import SessionLocal
    from app.models.customer import Customer

    path = pathlib.Path(inspect.getfile(chatbot)).resolve()
    modified = datetime.datetime.fromtimestamp(path.stat().st_mtime)

    # The new file has an intent the old one does not, and a fallback sentence
    # the old one does not. Either is a reliable signature.
    is_new = "capabilities" in getattr(chatbot, "_INTENTS", {})

    say("Chatbot check")
    say("=" * 60)
    say("file loaded      %s" % path)
    say("last modified    %s" % modified.strftime("%d %B %Y at %H:%M"))
    say("version          %s" % ("NEW, with Arabic" if is_new else "OLD, English only"))
    say("intents          %d" % len(getattr(chatbot, "_INTENTS", {})))
    say("OpenAI key set   %s" % ("yes" if settings.OPENAI_API_KEY else "no"))
    say("python           %s" % sys.executable)
    say("")

    if not is_new:
        say("This backend is running the OLD chatbot.")
        say("")
        say("The file it loaded is the one printed above. Copy the new")
        say("chatbot.py over THAT path, not over any other copy of the")
        say("project, then stop the backend window and start it again.")
        OUT.write_text("\n".join(lines), encoding="utf-8")
        print("Wrote %s. Open it in Notepad." % OUT)
        return 1

    if settings.OPENAI_API_KEY:
        say("NOTE: an OpenAI key is configured, so answers come from the model")
        say("first and from this file only if the model call fails. If the")
        say("replies below are Arabic but the app answers in English, the")
        say("model is the one answering. Clear OPENAI_API_KEY in .env to use")
        say("the built-in answers.")
        say("")

    db = SessionLocal()
    try:
        customer = (
            db.query(Customer)
            .filter(Customer.role == "customer", Customer.password_hash != "")
            .first()
            or db.query(Customer).filter(Customer.role == "customer").first()
        )
        if customer is None:
            say("No customer records in this database. Run load-data.bat first.")
            OUT.write_text("\n".join(lines), encoding="utf-8")
            return 1

        say("Answering as %s (%s)" % (customer.name, customer.customer_id))
        say("=" * 60)
        for question in QUESTIONS:
            reply = chatbot.answer(db, customer, question)
            arabic = chatbot._ARABIC_TEXT.search(reply) is not None
            asked_arabic = chatbot._ARABIC_TEXT.search(question) is not None
            mark = "ok" if arabic == asked_arabic else "WRONG LANGUAGE"
            say("")
            say("Q  %s" % question)
            say("   intent: %s   %s" % (chatbot._detect_intent(question), mark))
            say("A  %s" % reply)
    finally:
        db.close()

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("Wrote %s. Open it in Notepad." % OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
