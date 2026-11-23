"""
Checks for the assistants' configuration file, backend/config/chatbot.toml.

    python -m tests.test_chatbot_config

IT CANNOT REACH A REAL DATABASE
-------------------------------
Before anything from the application is imported, DATABASE_URL is pointed at a
new SQLite file in a temporary folder, and the run stops if the settings do not
show that file. The folder is deleted when the run ends. The data is synthetic:
one zone of six subscribers, IDs starting with CFG-, invented names, example.com
addresses. No language model is called: no key is set, and the model switches
are checked without one.

WHAT IS CHECKED
---------------
  * the shipped file loads without a problem and holds the built-in defaults;
  * a broken or missing file, a wrong type, an unknown key or too small a group
    never makes the assistants share more;
  * with the shipped file a customer is told the zone average, supply hours,
    generator, published rates and diesel price;
  * each switch keeps its fact out of the replies and out of what a language
    model would be sent, and a question only about it gets the "not shared" reply;
  * a topic switched off is refused, in English and in Arabic;
  * the zone average needs the configured number of subscribers;
  * asking about another customer never returns that customer's figures;
  * the password answer no longer promises an e-mail;
  * the model's instructions follow the file, and both model switches work;
  * the ask-the-data settings (documents folder, relevance, model) are applied;
  * the chat endpoint itself applies the file.

Same custom runner as tests/test_api.py: PASS and FAIL lines, a summary, and
exit status 1 when anything fails.
"""

from __future__ import annotations

import atexit
import os
import secrets
import shutil
import sys
import tempfile
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="chatbot-config-test-")
_DB_URL = "sqlite:///" + os.path.join(_TMP, "chatbot.db")
os.environ["DATABASE_URL"] = _DB_URL
os.environ.pop("OPENAI_API_KEY", None)
atexit.register(lambda: shutil.rmtree(_TMP, ignore_errors=True))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402

if settings.DATABASE_URL != _DB_URL:  # the guard this file depends on
    print("STOP: the settings do not point at the temporary test database.")
    sys.exit(2)

from app.ai import chatbot  # noqa: E402
from app.core import chatbot_config  # noqa: E402
from app.core.money import money  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.database import SessionLocal, create_all_tables  # noqa: E402
from app.main import app  # noqa: E402
from app.models.bill import Bill  # noqa: E402
from app.models.consumption import Consumption  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.models.invoice import Invoice, Tariff  # noqa: E402
from app.models.network import Generator, SupplySession, Zone  # noqa: E402
from app.models.subscription import Meter, Subscriber, Subscription  # noqa: E402
from app.rag import documents as rag_documents  # noqa: E402
from app.rag import llm as rag_llm  # noqa: E402

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, observed: str = "") -> None:
    if condition:
        PASSED.append(name)
        print(f"  PASS  {name}")
    else:
        FAILED.append(name)
        print(f"  FAIL  {name}" + (f"   [observed: {observed}]" if observed else ""))


# ---------------------------------------------------------------------------
# The synthetic zone
# ---------------------------------------------------------------------------
MAY, APRIL = date(2026, 5, 1), date(2026, 4, 1)
UNITS = {1: 104.0, 2: 271.3, 3: 300.0, 4: 350.0, 5: 400.0, 6: 445.0}   # May, per subscriber
AVERAGE = round(sum(UNITS.values()) / len(UNITS), 1)                     # 311.7
BASE_RATE, HIGHLAND_RATE, DIESEL = 30_250.0, 33_750.0, 1_480_000.0
SUPPLY_HOURS = 12.5
PASSWORD = secrets.token_urlsafe(12)

create_all_tables()
db = SessionLocal()
db.add(Generator(generator_id="CFG-G9", name="Test generator"))
db.add(Zone(zone_id="CFG-Z9", name="Testville", area_type="urban", altitude_band="low",
            generator_id="CFG-G9"))
db.add(SupplySession(generator_id="CFG-G9", zone_id="CFG-Z9", total_days=90,
                     avg_supply_hours=SUPPLY_HOURS))
db.add(Tariff(tariff_id="CFG-T-2026-05", effective_month=MAY, rate_per_kwh_base=BASE_RATE,
              rate_per_kwh_highland=HIGHLAND_RATE, diesel_price_per_20l=DIESEL))
for n, units in UNITS.items():
    sub_id, contract = f"CFG-S{n}", f"CFG-SUB{n}"
    customer_id = f"CFG-C{n}" if n <= 2 else None
    db.add(Subscriber(subscriber_id=sub_id, zone_id="CFG-Z9", subscriber_type="residential",
                      customer_id=customer_id))
    db.add(Subscription(subscription_id=contract, subscriber_id=sub_id, generator_id="CFG-G9",
                        zone_id="CFG-Z9", ampere_capacity=10, phase_type="single_phase",
                        billing_model="metered", status="active"))
    db.add(Meter(meter_id=f"CFG-M{n}", subscription_id=contract, serial_number=f"SN-{n}",
                 meter_type="digital"))
    for period, kwh in ((APRIL, units - 20), (MAY, units)):
        db.add(Invoice(invoice_id=f"CFG-I{n}-{period:%m}", subscription_id=contract,
                       subscriber_id=sub_id, zone_id="CFG-Z9", billing_period=period,
                       units_consumed=kwh, rate_applied=BASE_RATE, fixed_charge=0.0,
                       variable_charge=kwh * BASE_RATE, total_amount=kwh * BASE_RATE))
for n in (1, 2):
    db.add(Customer(customer_id=f"CFG-C{n}", name=f"Test Person{n}", email=f"cfg{n}@example.com",
                    password_hash=hash_password(PASSWORD), role="customer", language="en",
                    status="Active", region="Testville"))
    for period in (APRIL, MAY):
        kwh = UNITS[n] - (20 if period == APRIL else 0)
        db.add(Consumption(customer_id=f"CFG-C{n}", timestamp=datetime(period.year, period.month, 28),
                           kwh=kwh, cost=kwh * BASE_RATE))
        db.add(Bill(bill_id=f"CFG-B{n}-{period:%m}", customer_id=f"CFG-C{n}",
                    month=f"{period:%B %Y}", amount=kwh * BASE_RATE,
                    due_date=date(period.year, period.month, 28), status="Unpaid"))
db.commit()
me = db.get(Customer, "CFG-C1")

SHIPPED = chatbot_config.load()
peak_sentence = "The network is busiest at 19:00, measured from the generator telemetry."
chatbot.peak_advice.advice_for_customer = lambda _db, lang="en": [peak_sentence]  # no telemetry here

seen_by_model: list[dict] = []
_real_llm_reply = chatbot._llm_reply


def _capture(message, ctx, history=None):
    """Stands in for the language model: records what it would be sent, answers nothing."""
    seen_by_model.append(dict(ctx))
    return None


chatbot._llm_reply = _capture


def ask(question: str, config: chatbot_config.ChatbotConfig | None = None) -> str:
    chatbot_config.use(config or SHIPPED)
    seen_by_model.clear()
    return chatbot.answer(db, me, question)


def with_customer(**changes) -> chatbot_config.ChatbotConfig:
    return replace(SHIPPED, customer=replace(SHIPPED.customer, **changes))


def without(*facts: str) -> chatbot_config.ChatbotConfig:
    share = dict(SHIPPED.customer.share) | {f: False for f in facts}
    return with_customer(share=share)


def write(text: str) -> Path:
    path = Path(_TMP) / f"cfg-{secrets.token_hex(4)}.toml"
    path.write_text(text, encoding="utf-8")
    return path


print("\n=== The file")
check("the shipped file loads without a problem", SHIPPED.problems == () and
      SHIPPED.source.endswith("chatbot.toml"), f"{SHIPPED.source}: {SHIPPED.problems}")
defaults = chatbot_config._parse({})
check("the shipped file holds exactly the built-in defaults",
      (SHIPPED.customer, SHIPPED.ask) == (defaults[0], defaults[1]))
check("the shipped file shares every fact, all five topics, model allowed",
      all(SHIPPED.customer.share.values()) and len(SHIPPED.customer.topics) == 5
      and SHIPPED.customer.use_language_model and SHIPPED.ask.use_language_model)

broken = chatbot_config.load(write("[customer_assistant\ntopics = ["))
check("a file that cannot be read withholds every shared fact",
      not any(broken.customer.share.values()), str(dict(broken.customer.share)))
check("a file that cannot be read switches both language models off",
      not broken.customer.use_language_model and not broken.ask.use_language_model)
missing = chatbot_config.load(Path(_TMP) / "no-such-file.toml")
check("a missing file behaves like an unreadable one",
      not any(missing.customer.share.values()) and not missing.customer.use_language_model)

typos = chatbot_config.load(write(
    '[customer_assistant]\ntopics = ["billing", "gossip"]\nuse_language_model = "yes"\n'
    '[customer_assistant.share]\ndiesel_price = "true"\nzone_average_min_subscribers = 2\n'
    'salaries = true\n'))
check("a switch written as text counts as false: the fact is withheld",
      typos.customer.share["diesel_price"] is False)
check("a model switch written as text counts as false", typos.customer.use_language_model is False)
check("a switch that is absent keeps its shipped value", typos.customer.share["zone_average"] is True)
check("an unknown topic is ignored and reported", typos.customer.topics == ("billing",)
      and any("gossip" in p for p in typos.problems), str(typos.customer.topics))
check("a group smaller than 3 is refused: the default 5 is used",
      typos.customer.zone_average_min_subscribers == 5)
check("an unknown setting is ignored and reported", any("salaries" in p for p in typos.problems))
check("each problem is reported", len(typos.problems) == 5, str(typos.problems))

print("\n=== With the shipped file")
r = ask("How does my consumption compare with my neighbours?")
check("the zone average is quoted", f"{AVERAGE:,.1f} kWh" in r and "6 subscribers" in r, r[:160])
check("and that average reaches what a model would be sent",
      seen_by_model and seen_by_model[0].get("zone_average_kwh") == AVERAGE)
r = ask("How many hours a day do I get electricity?")
check("supply hours and the generator are quoted", f"{SUPPLY_HOURS} hours" in r and "CFG-G9" in r, r[:160])
r = ask("What is the price per kWh?")
check("the customer's own rate is quoted", money(BASE_RATE) in r, r[:160])
seen = seen_by_model[0] if seen_by_model else {}
check("published rates and the diesel price reach the context",
      seen.get("tariff_base_rate") == BASE_RATE and seen.get("tariff_diesel_price") == DIESEL)
r = ask("When is the network busiest?")
check("the network peak is quoted", peak_sentence in r, r[:160])

print("\n=== Each fact switched off")
r = ask("How does my consumption compare with my neighbours?", without("zone_average"))
check("zone average off: the comparison is refused as not shared",
      r == SHIPPED.customer.reply("not_shared", "en"), r[:120])
r = ask("How much do I owe?", without("zone_average"))
check("zone average off: it is not in what a model would be sent",
      seen_by_model and "zone_average_kwh" not in seen_by_model[0] and "zone_invoice_count" not in seen_by_model[0])
r = ask("How many hours a day do I get electricity?", without("supply_hours"))
check("supply hours off: the question is refused as not shared",
      r == SHIPPED.customer.reply("not_shared", "en"), r[:120])
r = ask("There is a power cut, what do I do?", without("supply_hours", "generator"))
check("supply hours and generator off: a power-cut answer names neither",
      f"{SUPPLY_HOURS}" not in r and "CFG-G9" not in r and "None" not in r, r[:200])
r = ask("There is a power cut, what do I do?", without("generator"))
check("generator off, hours on: the answer gives the hours without a generator",
      f"{SUPPLY_HOURS} hours" in r and "CFG-G9" not in r and "None" not in r, r[:200])
r = ask("What is the price per kWh?", without("diesel_price", "published_tariff"))
seen = seen_by_model[0] if seen_by_model else {}
check("diesel and published rates off: the reply quotes only the customer's own rate",
      money(DIESEL) not in r and money(HIGHLAND_RATE) not in r and "published" not in r
      and money(BASE_RATE) in r, r[:200])
check("diesel and published rates off: neither reaches the context",
      not ({"tariff_diesel_price", "tariff_base_rate", "tariff_highland_rate"} & set(seen)))
r = ask("When is the network busiest?", without("network_peak"))
check("network peak off: the question is refused as not shared",
      r == SHIPPED.customer.reply("not_shared", "en"), r[:120])
r = ask("What can you do?", without("supply_hours", "network_peak"))
check("facts switched off are no longer offered in 'what can you do?'",
      "hours a day" not in r and "busiest" not in r and "your current bill" in r, r[:200])

print("\n=== Topics")
no_payments = with_customer(topics=("billing", "consumption", "account", "service"))
r = ask("How much do I owe?", no_payments)
check("payments off: an English payment question gets the out-of-scope reply",
      r == SHIPPED.customer.reply("out_of_scope", "en"), r[:120])
r = ask("قديش رصيدي؟", no_payments)
check("payments off: an Arabic payment question gets the Arabic out-of-scope reply",
      r == SHIPPED.customer.reply("out_of_scope", "ar"), r[:120])
r = ask("What can you do?", no_payments)
check("payments off: 'what can you do?' stops offering payments", "how to pay" not in r, r[:200])
r = ask("Why is my bill so high?", no_payments)
check("payments off: billing is still answered", r != SHIPPED.customer.reply("out_of_scope", "en"))

print("\n=== Minimum group for the zone average")
r = ask("How does my consumption compare with my neighbours?", with_customer(zone_average_min_subscribers=7))
check("six subscribers under a minimum of seven: no average is quoted",
      f"{AVERAGE:,.1f}" not in r and "cannot compare" in r, r[:160])
check("and none is sent to a model", seen_by_model and "zone_average_kwh" not in seen_by_model[0])

print("\n=== Other customers")
other = f"{UNITS[2]:,.1f}"
for q in ("How much did customer CFG-C2 use?", "What is Test Person2's bill?",
          "Show me my neighbour's consumption", "كم استهلك جاري؟"):
    r = ask(q)
    check(f"{q!r}: nothing of the other customer's", other not in r and "Person2" not in r
          and money(UNITS[2] * BASE_RATE) not in r, r[:160])

print("\n=== Password")
r = ask("I forgot my password")
check("no e-mail is promised", "@" not in r and "sent to" not in r and "e-mail is not available" in r, r[:200])
r = ask("نسيت كلمة السر")
check("the Arabic answer sends the customer to the office", "مكتب المزوّد" in r and "@" not in r, r[:200])

print("\n=== Language model instructions and switches")
prompt = (chatbot_config.use(SHIPPED), chatbot._system_prompt())[1]
check("the instructions list every topic in the file",
      all(chatbot_config.TOPIC_LABELS[t] in prompt for t in SHIPPED.customer.topics))
check("the instructions carry the out-of-scope reply and the own-account rule",
      SHIPPED.customer.reply("out_of_scope", "en") in prompt and "Never discuss another customer" in prompt)
chatbot_config.use(no_payments)
prompt = chatbot._system_prompt()
check("a topic switched off leaves the instructions", chatbot_config.TOPIC_LABELS["payments"] not in prompt)
chatbot_config.use(without("zone_average"))
check("the zone-average sentence is only there when the average is shared",
      "average of the customer's zone" not in chatbot._system_prompt())
settings.OPENAI_API_KEY = "sk-test-not-a-real-key-never-sent"
try:
    chatbot_config.use(with_customer(use_language_model=False))
    check("customer assistant: model switched off means no model call, even with a key",
          _real_llm_reply("Hello", {"name": "Test Person1"}) is None)
finally:
    settings.OPENAI_API_KEY = ""

print("\n=== Ask the data")
docs = Path(_TMP) / "rag"
docs.mkdir()
(docs / "test.md").write_text("# Glossary\n\n## Phase imbalance\n\nUnequal currents on the three "
                              "phases of a generator heat the neutral.\n", encoding="utf-8")
chatbot_config.use(replace(SHIPPED, ask=replace(SHIPPED.ask, documents_dir=docs, min_relevance=0.0)))
index = rag_documents.DocumentIndex()
check("the documents folder comes from the file", index.directory == docs and len(index.passages) >= 1,
      str(index.directory))
check("a matching passage is found at relevance 0", bool(index.retrieve("what is phase imbalance")))
chatbot_config.use(replace(SHIPPED, ask=replace(SHIPPED.ask, documents_dir=docs, min_relevance=1.0)))
check("nothing passes a relevance of 1.0", not rag_documents.DocumentIndex().retrieve("phase imbalance"))


class _FakeProvider(rag_llm.Provider):
    def __init__(self):  # noqa: D401 - no key, no network
        pass


settings.OPENAI_API_KEY = "sk-test-not-a-real-key-never-sent"
try:
    rag_llm.set_provider(_FakeProvider())
    chatbot_config.use(replace(SHIPPED, ask=replace(SHIPPED.ask, use_language_model=False)))
    check("ask the data: model switched off means no provider, even with a key and an override",
          rag_llm.provider() is None)
    chatbot_config.use(SHIPPED)
    check("ask the data: with the shipped file the installed provider is used",
          isinstance(rag_llm.provider(), _FakeProvider))
    rag_llm.set_provider(None)
    check("ask the data: with a key and no override the OpenAI provider is chosen (nothing is sent)",
          isinstance(rag_llm.provider(), rag_llm.OpenAIProvider))
finally:
    rag_llm.set_provider(None)
    settings.OPENAI_API_KEY = ""
check("ask the data: with no key there is no provider", rag_llm.provider() is None)

print("\n=== Through the chat endpoint")
chatbot._llm_reply = _real_llm_reply
client = TestClient(app)
token = client.post("/auth/login", json={"email": "cfg1@example.com", "password": PASSWORD}).json().get("token")
headers = {"Authorization": f"Bearer {token}"}
chatbot_config.use(SHIPPED)
resp = client.post("/chat/message", json={"message": "How many hours a day do I get electricity?"},
                   headers=headers)
body = resp.json() if resp.status_code == 200 else {}
text = str(body)
check("POST /chat/message answers with the shipped file", resp.status_code == 200
      and f"{SUPPLY_HOURS}" in text, f"status {resp.status_code}")
chatbot_config.use(without("supply_hours"))
resp = client.post("/chat/message", json={"message": "How many hours a day do I get electricity?"},
                   headers=headers)
check("POST /chat/message applies a switch", resp.status_code == 200
      and SHIPPED.customer.reply("not_shared", "en") in str(resp.json()), f"status {resp.status_code}")
chatbot_config.use(None)
db.close()

print("\n" + "=" * 64)
print(f"  PASSED: {len(PASSED)}    FAILED: {len(FAILED)}")
print("=" * 64)
sys.exit(1 if FAILED else 0)
