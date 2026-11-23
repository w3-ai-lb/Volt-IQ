# Backend: AI-Powered Energy Analytics and Customer Engagement Platform

**NXTTRN × MUBS: Industry Internship**

FastAPI backend implementing the Application Layer of the three-tier architecture:
authentication, business logic, REST APIs, AI services and database communication.

---

## Quick start

**Requirements:** Python 3.11 or newer (the code imports `datetime.UTC`, which Python 3.10
does not have) and Node.js for the frontend.

```bash
cd backend
python3.11 -m venv venv              # Windows: py -3.11 -m venv venv
source venv/bin/activate             # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # Windows: copy .env.example .env
python -m app.pipeline.seed          # acts only on an EMPTY database, see below
uvicorn app.main:app --reload        # starts the API on port 8000
```

On Windows, `start.bat` performs these steps with a virtual environment kept in
`%LOCALAPPDATA%\energy-analytics-venv`, outside OneDrive; on macOS or Linux, `start.sh` does
the same with `backend/venv` and refuses to run on Python older than 3.11.

The seeder fills an **empty** database with invented demo data and the two demo logins
listed under *Signing in*. On a database that already holds data, including the delivered
one, it does nothing.

Then open **http://localhost:8000/docs** for the interactive API documentation.

To run the frontend against it, in a second terminal:

```bash
cd frontend
npm install
npm run dev                          # http://localhost:5173
```

### Configuration (`backend/.env`)

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLite file by default; PostgreSQL in production |
| `JWT_SECRET_KEY` | Signs login tokens. Set a long random value, 32 characters or more. With the built-in placeholder or the one in `.env.example`, the server refuses to start on PostgreSQL and logs a warning on SQLite |
| `CORS_ORIGINS` | Frontend addresses allowed to call the API |
| `RETURN_RESET_TOKEN_IN_RESPONSE` | `false` by default. `true` returns password-reset tokens in API responses for a local demo, and is ignored on any database that is not SQLite |
| `REGISTRATION_CODE_VALID_DAYS` | Days a one-time registration code stays valid (default 30) |
| `OPENAI_API_KEY` | Optional. Lets the customer assistant and the ask-the-data box use a language model |
| `PROVISION_DEMO_DATA` | Keep `false`. `true` gives every new account a generated 12-month history |

The settings loader reads these from `backend/.env` when the server starts. On Render, set
them in the service's environment instead.

### Signing in

**The delivered database contains no demo logins.** The demo administrator and demo customer
are not in it; `python -m scripts.data_provenance` reports the one seeded record that remains,
a customer record without a password, which cannot be signed into. Create an administrator,
who is asked for a password:

```bash
python -m scripts.create_admin --email you@example.com --name "Your Name"
```

The two logins below exist only in a fresh local database created by the seeder. Their
passwords are published here and printed by the launchers, so a seeded database must never be
reachable by anyone else.

| Role | Email | Password |
|---|---|---|
| Administrator | `admin@nxttrn.com` | `admin123` |
| Customer | `customer@nxttrn.com` | `customer123` |

### Registering a new customer

Registration **claims an existing account** rather than creating one from
nothing. The customer enters the **Customer ID from their bill**, which is what
links their new login to the meter readings the provider already holds. The SRS
(Section VI-i) lists Customer ID as an *input* to the Customer Management
Module, not a generated value.

Without this link, a self-registered customer would sit on an empty dashboard
while their own readings lived under the provider's own account number as a
duplicate record.

**A Customer ID alone is not enough.** It is printed on every bill, so anyone who
has seen one, or who tries numbers in sequence, could otherwise take the account.
Registration also needs a **one-time registration code**, which the provider
issues for that account and gives only to its holder, on the paper bill or at the
office:

- for one account, on the **Customers** page: the key button beside an account
  nobody has registered yet asks for confirmation (an earlier code stops working,
  including one already printed on a bill), then shows the new code once with the
  date it expires. The page calls `POST /customers/{id}/registration-code`
  (administrators only);
- for many accounts, to print on the bills:

  ```bash
  python -m scripts.issue_registration_codes --out codes.csv --all-unregistered
  ```

  The CSV holds the codes themselves, while the database keeps only bcrypt hashes:
  print it, hand the codes over, then delete it. It is written with a UTF-8
  byte-order mark, so Excel shows names in Arabic script correctly.

A code has 8 characters, is valid for 30 days (`REGISTRATION_CODE_VALID_DAYS`),
works once, and is replaced when a new one is issued. Every failed attempt,
whatever the reason (unknown ID, already registered, deactivated account, wrong,
missing or expired code, email already in use), gets the same `400` and the same
message, so the form cannot be used to find out which IDs exist. Registration
never reactivates an account an administrator has deactivated.

In a **fresh demo database**, the seeder creates three unclaimed accounts, records
that exist with full consumption history but no login yet, exactly as the pipeline
produces them, so the flow can be demonstrated:

| Customer ID | Name |
|---|---|
| `MTR-40118` | Georges Rizk |
| `MTR-40219` | Sarah Mroueh |
| `MTR-40327` | Tarek Zeineddine |

Issue a code for one of them
(`python -m scripts.issue_registration_codes --out codes.csv <Customer ID>`), then
register with the ID and the code: its existing bills, payments and charts appear
immediately. An unclaimed record has an empty password hash, so it cannot be signed
into until someone registers for it.

---

## Technology stack

Exactly as specified in Section III of the Software Architecture document:

| Layer | Technology |
|---|---|
| Backend | FastAPI (Python) |
| Database | PostgreSQL (SQLite for local development) |
| Authentication | JWT + bcrypt |
| AI models | scikit-learn, statsmodels, pandas |
| Chatbot | OpenAI API, with a grounded rule-based fallback |
| Deployment | Render (see `render.yaml`) |

### A note on SQLite

`DATABASE_URL` defaults to SQLite so the project runs with zero setup. The code is
identical for both engines, SQLAlchemy abstracts the difference. To use PostgreSQL
as the architecture specifies, change one line in `.env`:

```
DATABASE_URL=postgresql+psycopg2://postgres:yourpassword@localhost:5432/energy_analytics
```

Nothing else changes.

### Updating an existing database

There is no migration tool. Tables a newer version needs are created when the server
starts, and the columns it adds to existing tables (listed in `_LATER_COLUMNS` in
`app/database.py`) are added at the same moment; the scripts that read customer records
(`check-data.bat`, `purge-demo.bat`, `check-chatbot.bat`, `scripts.portal_access` and the
chat scripts) add those columns first as well, so they also work before the server has
been started on the updated code. Nothing is ever dropped or retyped. Back up first
(`python -m scripts.backup`). This has been run on SQLite only; on PostgreSQL, which
this project has not been run on, try an update on a copy first.

---

## Project structure

```
backend/
├── app/
│   ├── main.py              FastAPI app, CORS, router registration
│   ├── config.py            Settings loaded from .env
│   ├── database.py          SQLAlchemy engine and session
│   │
│   ├── models/              The 7 entities from Section VII + Alert, Anomaly,
│   │                        NotificationPreference, PasswordReset, Forecast,
│   │                        and the provider's own side: Subscriber,
│   │                        Subscription, Meter, MeterReading, Invoice,
│   │                        Tariff, Zone, Generator, telemetry and loss
│   ├── schemas/             Pydantic models (camelCase on the wire)
│   ├── routers/             REST endpoints grouped by feature
│   ├── core/                security.py (JWT, bcrypt), deps.py (RBAC and
│   │                        session versions), money.py (one place that
│   │                        formats LBP), registration_codes.py (one-time
│   │                        codes for claiming), rate_limit.py (attempt
│   │                        limits), chatbot_config.py (reads
│   │                        config/chatbot.toml), i18n.py and
│   │                        i18n_messages.py (the server's sentences in the
│   │                        reader's language)
│   │
│   ├── analytics/           ★ The loss account and what to do about it
│   │   ├── asof.py            Every window anchored on the data, not the clock
│   │   ├── loss.py            Delivered vs billed, attributed by cause
│   │   ├── generator_metrics.py  Fuel, run hours and phase balance per set
│   │   ├── rules.py           The six field-visit rules, with their evidence
│   │   └── owed.py            One definition of what a customer owes
│   │
│   ├── ai/                  ★ AI Module
│   │   ├── forecasting.py     Demand forecasting: SARIMA
│   │   ├── anomaly.py         Anomaly detection, daily and monthly
│   │   ├── subscriber_anomaly.py  IsolationForest over monthly readings
│   │   ├── segmentation.py    Customer segmentation: KMeans
│   │   ├── recommender.py     Personalised recommendation engine
│   │   ├── alerts.py          Alert engine
│   │   ├── risk.py            Payment-default risk scoring
│   │   ├── peak_advice.py     Network peak, measured from telemetry
│   │   ├── evaluation.py      Every model against its baseline
│   │   ├── chatbot.py         Customer support assistant, English and Arabic
│   │   └── artifacts/         Cached fitted models (generated, not source)
│   │
│   ├── rag/                 ★ Ask the data in plain language
│   │   ├── documents.py       The provider's own notes, indexed
│   │   ├── engine.py          Retrieval
│   │   ├── queries.py         The questions it can answer with SQL
│   │   └── llm.py             Optional model call, with a rule-based fallback
│   │
│   ├── reports/             PDF and Excel generation
│   │   ├── builder.py         Report data
│   │   ├── render.py          Layout
│   │   └── receipt.py         Payment receipts and bill PDFs
│   │
│   └── pipeline/            ★ Data pipeline
│       ├── ishtirak.py        Loads the fourteen files of the supplied synthetic dataset
│       ├── identities.py      A customer record for each of its 300 subscribers
│       ├── crm_identities.py  The CRM project's customer-side records
│       ├── portal.py          Projects invoices onto bills and payments
│       ├── ingest.py          General CSV loader for other exports
│       ├── plans.py           The three tariff plans
│       ├── provision.py       Creates accounts from provider records
│       └── seed.py            Generates demo data
│
├── scripts/
│   ├── backup.py                Daily database backup (SRS IV, Reliability)
│   ├── create_admin.py          An administrator for a database without demo logins
│   ├── issue_registration_codes.py  One-time registration codes, as a CSV for printing
│   ├── portal_access.py         Sets a password on one customer account (demonstrations)
│   ├── reset_demo_payments.py   Undoes payments made through the portal
│   ├── repair_overpayments.py   Corrects a bill charged more than it asked
│   ├── data_provenance.py       Which rows came from the provider, which we
│   │                            computed, which the seeder invented, and the
│   │                            purge that removes only the last of those
│   ├── chat_battery.py          56 questions, each routed as it should be
│   ├── chat_matrix.py           The answer sheet, both languages, as HTML
│   ├── chat_sweep.py            Every account x every question x both languages
│   ├── rules_vs_model.py        The rules engine against IsolationForest
│   ├── score_rules.py           Precision and recall of the field-visit rules
│   ├── verify_ishtirak_load.py  The load is reproducible row for row
│   ├── verify_purge.py          The purge removes the invented rows and no more
│   ├── verify_ask.py            Every answer traces to a query you can run
│   └── init_repo.sh             First-time Git setup
│
├── config/
│   └── chatbot.toml             What the two assistants may answer and share
│
└── tests/
    ├── test_api.py          The API, asserted against what the UI expects
    ├── test_security.py     Claiming, codes, reset tokens, guards (own temporary database)
    ├── test_review_fixes.py The October code-review findings (own temporary database)
    ├── test_chatbot_config.py  config/chatbot.toml and what each setting changes
    ├── e2e_profile.mjs      The profile and password flows, in a real browser
    └── e2e_engines.mjs      Alerts, payment risk and the load heatmap
```

---

## Loading the supplied dataset

The company supplied a **synthetic** dataset for this project: fourteen CSV files in
`data/ishtirak/`, 71,589 rows, that model an ishtirak provider's generators, zones,
subscribers, meter readings, invoices and payments, with anomalies injected deliberately so
that detection can be scored. None of it describes a real provider's customers or losses.
`load-data.bat` (Windows) runs this sequence with the project's virtual environment:

```bash
python -m app.pipeline.ishtirak --dir data/ishtirak         # 1. clear and reload the 14 provider tables, rebuild the loss account
python -m scripts.verify_ishtirak_load --dir data/ishtirak  # 2. every row arrived, the account reconciles (read-only)
python -m app.pipeline.identities --replace                 # 3. a customer record for each of the 300 subscribers
python -m app.pipeline.portal --replace                     # 4. bills and payments from the invoices, for the portal
```

Then create an administrator (see *Signing in*) and check where every row came from with
`python -m scripts.data_provenance`, which only reports.

Run the steps together. Step 1 on its own clears every subscriber's link to its customer
record (all 300 `subscribers.customer_id` values), and step 3 is what restores them. Step 1
is repeatable: loading twice gives identical row counts and an identical loss account (only
the `computed_at` timestamps differ; checked on 11 October 2026). Step 3 builds names and
contact details from `data/crm/customer_side_seed_data.sql` and generated values; every
figure on those records is measured from the dataset. The answer key,
`subscriber_labels_for_intern.csv`, is never loaded: the scoring scripts take its path as an
argument.

## Loading other exports with `ingest.py`

`app/pipeline/ingest.py` is a general CSV loader, kept for other exports, for example a
future export from a provider's live system:

```bash
python -m app.pipeline.ingest --consumption path/to/readings.csv --rebuild-ai
```

### The full procedure, for a first load

The loader **adds**; it does not replace. Run it against the demo database and
the loaded customers end up sitting in the same tables as seventeen
invented ones, which is worse than either alone: every total on the admin
dashboard becomes a mixture and nobody looking at the screen can tell which
rows are which. `--fresh` empties the database first, and says what it is about
to delete before it does.

```bash
# 1. Load the export into an empty database
python -m app.pipeline.ingest --fresh \
    --customers   data/customers.csv \
    --consumption data/readings.csv \
    --bills       data/bills.csv \
    --payments    data/payments.csv \
    --rebuild-ai

# 2. Create somebody who can sign in
python -m scripts.create_admin --email you@nxttrn.com --name "Your Name"
```

Step 2 is not optional, and it is easy to be surprised by. Every customer the
loader imports is left **unclaimed**, with an empty password hash, because a
record the provider holds is not a login until a person registers for it. That
is correct, and it means a database built only from loaded data contains no
account anyone can sign in to at all. `create_admin` is what makes the platform
reachable; run it again with the same email to reset that password.

Also set `PROVISION_DEMO_DATA=false` in `.env` once loaded data is the source of
truth, so an account created through the Register page is no longer given a
generated history.

### What to expect the first time

Two things on the admin dashboard depend on how much history the dataset
carries, and both report honestly rather than guessing:

**The forecast backtest card** reads *Not enough data* until there are 32 weeks of
readings. A rolling-origin backtest has to fit the model on weeks that exclude
the ones being predicted, and under 32 weeks there is nothing left to fit on.
It is not a broken model; `GET /ai/evaluation` says the same thing in a sentence.

**On the supplied dataset that figure is not a validated measure.** Meters are read
once a month over approximately ten days, so the weekly series contains observations
in only 42 of its 76 calendar weeks, at irregular intervals. Consequently, a backtest
on this series measures the effects of the reading schedule and does not establish
reliable demand-forecasting performance. Read the card and `GET /ai/evaluation` as
diagnostics, not as evidence that the forecast works. The Forecast Report and the
`limitations` field of `GET /ai/evaluation` say so beside the figure, in these words.

**The month figures are the data's, not the calendar's.** Consumption and revenue on
the executive dashboard are for the newest complete month in the data, compared
with the month before it. The page prints the day its figures are for (the newest
meter reading, `asOf`) and names the month the consumption card covers
(`consumptionPeriod`), so on the supplied dataset it reads "as of 12 June 2026" and
"Consumption in May 2026". Payment risk is scored as of the same day, so its bands
do not change while the data does not.

The forecast adapts on its own: with under two years it uses a short
seasonal period, and under 24 weeks it drops to a damped-trend model and
reports `seasonal: false` rather than claiming a yearly cycle it cannot see.

You can pass any combination of the four file types:

```bash
python -m app.pipeline.ingest \
    --customers   data/customers.csv \
    --consumption data/readings.csv \
    --bills       data/bills.csv \
    --payments    data/payments.csv \
    --rebuild-ai
```

**The loader is column-name tolerant.** It recognises many common spellings of each
field, so most utility exports load without editing the CSV. For meter readings it
needs three things in some form: a customer identifier, a timestamp, and a kWh value.
Recognised aliases include:

| Field | Accepted column names |
|---|---|
| customer id | `customer_id`, `customer`, `cust_id`, `meter_id`, `account`, `id` |
| timestamp | `timestamp`, `datetime`, `date`, `reading_time`, `time`, `period` |
| kWh | `kwh`, `consumption`, `energy`, `usage`, `value`, `active_power`, `load` |
| cost | `cost`, `amount`, `charge`, `price` (optional, derived from tariff if absent) |

Anything it cannot map is reported rather than silently dropped. Customers referenced
by the readings but not present in a customers file are created automatically, so a
readings-only dataset works on its own.

`--rebuild-ai` re-runs the recommendation engine, anomaly detection and the alert
engine against the newly loaded data, and clears the cached forecast so the next
request refits it.

---

## The AI module

| Capability | Model | Endpoint |
|---|---|---|
| Demand forecasting | SARIMA (statsmodels) | `GET /ai/forecast` |
| Anomaly detection | IsolationForest (scikit-learn) | `GET /ai/anomalies` |
| Customer segmentation | KMeans + StandardScaler | `GET /ai/segments` |
| Recommendations | Rules over measured usage signals | `GET /recommendations` |
| Alerts | Rules over usage, billing and anomalies | `POST /alerts/refresh` |
| Payment-default risk | Weighted score over billing behaviour | `GET /analytics/risk` |
| Chatbot | OpenAI API or grounded fallback | `POST /chat/message` |

Every model degrades gracefully. If a library is missing or a fit fails, a simpler
method takes over and the API still responds, the dashboard never breaks because a
model could not be fitted.

Two design decisions worth knowing about:

**The forecast validates itself.** An over-parameterised SARIMA on a short series can
oscillate and diverge into negative values. Since electricity demand is strictly
positive and changes gradually, `_is_plausible()` rejects any forecast that goes
negative, leaves the historical envelope, or swings more than 60% week-on-week, and
falls back to a damped linear trend. The incomplete final week is also dropped before
fitting, otherwise a partial week reads as a demand collapse and gets extrapolated.

**The forecast is cached, not recomputed.** Fitting SARIMA costs about 1.2 seconds and
the forecast is system-wide, so every admin opening the dashboard was paying to compute
the same answer. The fitted result is stored in `app/ai/artifacts/` under a fingerprint
of the consumption table, its row count and newest timestamp. Loading data changes the
fingerprint, so a stale forecast cannot survive an ingest and nothing has to remember to
clear anything. Cached responses come back in about 6 ms.

**The chatbot works without an API key.** Set `OPENAI_API_KEY` in `.env` to use the
LLM. Without it, the built-in intent engine answers from the bill, balance and
consumption figures stored for that customer, so the demo works offline and every
number comes from the database rather than from a language model. The ask-the-data box
on the loss dashboard uses the same key, when it is set, only to pick one of its written
queries and to reword the answer; the figures still come from SQL.

**What the two assistants may answer is set in `config/chatbot.toml`**: the customer
assistant's topics, the shared facts it may quote (the published tariff, the zone
average, supply hours and so on), whether a language model is used at all, and the
fixed replies for out-of-scope questions. Restart the backend after editing it. The file
cannot widen access: a customer is only ever told about their own account, the
ask-the-data box stays administrators-only, and a file that is missing or broken makes
both assistants withhold every shared fact. `python -m tests.test_chatbot_config` checks
what each setting changes.

---

## Languages

The interface is in **seven languages**: English, Arabic (right to left), Spanish,
French, German, Chinese and Japanese, chosen on the Settings page and saved to the
account. Its text lives in `frontend/src/i18n/` (`translations.ts` and `arabic.ts`), keyed
by the English. Figures keep Western digits and the units `kWh` and `LBP` in every
language; dates and month names follow the language, with the Levantine month names in
Arabic.

**The sentences the server writes are translated too**: alerts, recommendations, the
reasons beside a payment-risk score, zone explanations on the loss page, the evidence and
checks on the field-visit list and the dashboard's activity feed. The interface sends its
language in `Accept-Language` on every request, and `app/core/i18n.py` rewrites each
English sentence from its entry in `app/core/i18n_messages.py`, with the same figures.
Stored alerts and recommendations stay in English in the database, so a reader who
changes language sees them in the new one at once. A sentence with no entry is shown in
English rather than broken, and `tests.test_review_fixes` and `tests.test_api` fail when
the system writes a sentence that has none. A refusal a user can meet (a wrong password,
too many attempts) is a fixed English sentence, which the interface translates from its
own catalogue.

What stays as it is: records (names, zone and generator names, IDs, the controller's own
alarm texts); the PDF and Excel reports and statements, which are written in English; and
the answers of the ask-the-data box, which understands questions in English and the
common ones in Arabic and answers in English, as the page says. The customer assistant
answers in Arabic or English, whichever the question is written in.

From the `frontend` folder, `npm run check:i18n` checks the catalogue against the code:
every `t('...')` phrase has all six translations, every translation keeps its
`{placeholders}`, and it lists any phrase that nothing uses any more.

---

## Security

Implements every item in Section IX of the Software Architecture:

| Requirement | Implementation |
|---|---|
| JWT Authentication | `python-jose`, signed tokens with expiry |
| Password Hashing | bcrypt with per-password salt |
| HTTPS | Provided by Render / Vercel |
| Role-Based Access Control | `require_admin` dependency on admin routes |
| Input Validation | Pydantic schemas on every request body |
| Secure Database Access | SQLAlchemy ORM (parameterised), credentials in `.env` |
| Session Management | Token expiry, client-side cleanup on 401, and a password change or reset signs out every other session |
| Attempt limits | Wrong passwords, refused registrations, reset requests and invalid reset tokens are limited per account and per client address (`app/core/rate_limit.py`); the answer is `429` with `Retry-After` |
| Signing key | The server will not start on PostgreSQL with a placeholder `JWT_SECRET_KEY` or one under 32 characters |

Login returns the same error for an unknown email and a wrong password, so the
endpoint cannot be used to discover which accounts exist. `/auth/forgot-password`
always reports success for the same reason. Registration works the same way: it needs
the one-time registration code as well as the Customer ID, every failure gets one `400`
and one message, and it never reactivates an account an administrator has deactivated
(see *Registering a new customer*).

**Changing the password signs out every other device.** Each account has a session
version that every sign-in token carries; a password change or reset raises it, so tokens
issued before are refused, and the device that made the change receives a new token.
Revoking portal access with `scripts.portal_access --revoke` ends open sessions the same way.

**Repeated attempts are limited.** Within any 15 minutes: five wrong passwords for one
address from one client, five refused registrations for one Customer ID, five reset
requests for one address, or five wrong current passwords on one signed-in account are
answered with `429 Too Many Requests` and a `Retry-After` header until the window
passes, and each client address has a larger allowance of its own (50 sign-in failures,
30 refused registrations, 30 reset requests, 30 invalid reset tokens). A correct
password clears the count for that address. The sign-in count is kept per address and
client together, so a stranger typing wrong passwords cannot lock the owner out from
another machine. The counts are kept in the server's memory, which suits the
single-process deployment in `render.yaml`; several processes would need a shared store.

**Password-reset tokens are never returned in API responses** unless
`RETURN_RESET_TOKEN_IN_RESPONSE=true`, and that setting is honoured only on a local
SQLite database, to demonstrate the flow; on any other database it is ignored and
startup logs a warning. There is no email provider yet (Architecture Section XI), so
**customers of a deployed system cannot reset a forgotten password themselves** until
email delivery is implemented; the Forgot-password page tells them to contact the
provider's office. Until then a password can only be set from the server, for example
with `python -m scripts.portal_access <Customer ID>`, which generates one and shows it
once.

---

## API reference

63 endpoints. Full interactive documentation at `/docs` when the server is running.

### Authentication
```
POST   /auth/login              Sign in, returns { token, user }
POST   /auth/register           Claim an existing account: Customer ID + registration code
POST   /auth/forgot-password    Begin password recovery (no token returned; see Security)
POST   /auth/reset-password     Redeem a reset token
POST   /auth/change-password    Change password while signed in
GET    /auth/me                 Validate a stored token
```

### Customer portal
```
GET    /dashboard/customer      Composite dashboard payload
GET    /consumption/monthly     Monthly kWh and cost
GET    /consumption/daily       Daily totals
GET    /consumption/hourly      Average 24-hour load profile
GET    /consumption/export      Consumption history as CSV
GET    /bills                   Customer bills
GET    /bills/{id}              Single bill
POST   /bills/{id}/pay          Pay a bill: records a payment and settles it
GET    /bills/{id}/pdf          The bill itself as PDF
GET    /payments                Payment history
GET    /payments/{id}/receipt   Payment receipt as PDF
GET    /recommendations         Personalised recommendations
PATCH  /recommendations/{id}    Mark one complete
POST   /recommendations/refresh Re-run the engine
GET    /alerts                  Customer alerts
POST   /alerts/refresh          Re-run the alert engine
PATCH  /alerts/{id}             Mark an alert read or unread
GET    /search                  Role-aware search across bills, payments, alerts
GET    /profile                 Profile details
PATCH  /profile                 Update name, email, phone, address, theme, language
GET    /preferences/notifications    Which alert categories this account wants
PATCH  /preferences/notifications    Turn a category on or off
```

`/search` is one endpoint with two behaviours rather than two endpoints: an
administrator searches customers, regions and accounts, a customer searches only
their own bills, payments and alerts. The customer branch filters on
`customer_id` before anything else, because that filter is the access control
and not a convenience.

Theme and language are stored on the customer row rather than in the browser, so
they belong to the person and not to the machine. Two people sharing a computer
each keep their own, and a newly registered account starts from the default
instead of inheriting whatever the previous person chose.

### Administration
```
GET    /dashboard/admin         Executive dashboard
GET    /customers               All customers
POST   /customers               Create a customer record
GET    /customers/{id}          Single customer
PATCH  /customers/{id}          Update customer details
DELETE /customers/{id}          Delete a customer and its data
POST   /customers/{id}/activate      Reactivate an account
POST   /customers/{id}/deactivate    Deactivate an account
POST   /customers/{id}/registration-code   Issue a one-time registration code
GET    /analytics/kpis          Business KPIs
GET    /analytics/regional      Regional breakdown
GET    /analytics/risk          Payment-default risk across the customer base
GET    /consumption/heatmap     System load by weekday and hour
GET    /revenue/overview        Revenue and billing status
GET    /reports                 Available report types
GET    /reports/{type}          Generate a report as PDF or Excel
```

### AI
```
GET    /ai/forecast             Demand forecast
GET    /ai/segments             Customer segments
GET    /ai/anomalies            Detected anomalies
POST   /ai/anomalies/run        Re-run detection
GET    /ai/evaluation           Backtest and scoring diagnostics (see the forecast note)
GET    /chat/history            Conversation list
GET    /chat/history/{id}       One conversation with its messages
DELETE /chat/history/{id}       Delete a conversation
POST   /chat/message            Ask the assistant
```

### Service
```
GET    /                        API banner
GET    /health                  Liveness check
```

### Passwords: three separate flows

`/auth/forgot-password` + `/auth/reset-password` recover an account the user is
locked out of, ownership is proved by receiving the token. `/auth/change-password`
is for a user who is already signed in, and requires the current password, so a
stolen session token alone cannot lock the real owner out. Changing a password also
invalidates any reset link still outstanding for that account. While no email provider
exists, the reset token reaches nobody outside a local demo database, so the first flow
is not available in a deployment (see *Security*).

---

## Testing

**`tests.test_api` writes to whatever database `DATABASE_URL` points at.** It signs in
as an administrator and a customer (setting temporary passwords when the demo logins are
absent), claims and releases an account, makes and reverses changes, and restores what
it changes. Run it against a copy:

```bash
cp energy_analytics.db /tmp/test-copy.db
DATABASE_URL=sqlite:////tmp/test-copy.db python -m tests.test_api

# Windows PowerShell
copy energy_analytics.db test-copy.db
$env:DATABASE_URL = 'sqlite:///./test-copy.db'; python -m tests.test_api
```

It asserts each response shape, including camelCase field names, against what the React
pages expect. On 17 October 2026, against a copy of a database rebuilt from
`data/ishtirak` with the four steps of `load-data.bat` plus an administrator (Python
3.11.15, the pinned requirements), it executed 310 checks with 0 failures, and a second
run on the same copy gave the same 310 checks and the same result. It exercised 62 of
the 63 endpoints: every endpoint a page calls, the ones no page calls, and the health
checks. The one left out is `POST /ishtirak/loss/refresh`, which rebuilds the stored loss
account. The number of checks depends on the database, because some checks run only
when there is data to check, so quote it with the date and the database it came from.

Running it twice gives the same result: it restores the profile it edits, the passwords
it changes, the chats it opens and the account it claims, and it deletes the account it
creates. What stays behind: the password-reset tokens it requests (five rows per run in
`password_reset_tokens`), one regenerated alert, and, when the customer it signs in as had
no notification preferences saved, one `notification_preferences` row holding the
defaults that applied anyway. It also writes `app/ai/artifacts/forecast.json` in the
working folder.

The other three suites each create their own temporary SQLite database with synthetic
accounts, refuse to run if the settings point anywhere else, and delete it afterwards,
so they cannot touch a real one:

```bash
python -m tests.test_security          # claiming, registration codes, reset tokens,
                                       # deactivated accounts, seeder guard, account scripts
python -m tests.test_review_fixes      # the findings of the October code review, one
                                       # section each, written to fail on the code before
python -m tests.test_chatbot_config    # config/chatbot.toml and what each setting changes
python -m scripts.verify_ask           # every answer of the ask-the-data box traces to a query
```

On 17 October 2026: 64, 74, 54 and 43 checks, all with 0 failures (`verify_ask` on a
copy of the same rebuilt database).

For the interface, from the `frontend` folder: `npm run typecheck` (clean),
`npm run lint` (0 errors; 11 warnings from the hot-reload plugin, about files that export
a hook beside a component), `npm run check:i18n` (no problems) and `npm run build`.

Two browser-level suites cover the things an API test cannot see, because the bugs
they were written for were invisible from the API alone: a page that reported
success while writing only to `localStorage` answers exactly like a page that
saved. They need the frontend built and both servers running, and Playwright
installed with its Chromium (`npx playwright install chromium`); to use a Chromium already
on the machine instead, set `PLAYWRIGHT_CHROMIUM_PATH` to its executable:

```bash
node tests/e2e_profile.mjs      # profile edits and the three password flows
node tests/e2e_engines.mjs      # the alert engine, payment risk, load heatmap
```

Both restore what they touch: the alert they mark read they mark unread again,
and the demo password they change they change back. They sign in with the demo logins,
so they need a seeded local database.

A bill paid through the portal is a real write and cannot be undone through the
API, deliberately, because a portal must not be able to unmake a payment. After
demonstrating it:

```bash
python -m scripts.reset_demo_payments            # report what the portal created
python -m scripts.reset_demo_payments --apply    # remove them, reopen the bills
```

---

## Commands that change data

Back up first (`python -m scripts.backup`), and never run these against a database you
cannot lose.

| Command | What it changes |
|---|---|
| `python -m app.pipeline.seed --reset` | Drops every table, then builds a demo database (refused on anything but SQLite) |
| `python -m app.pipeline.ingest --fresh …` | Empties the database before loading |
| `python -m app.pipeline.ishtirak --dir data/ishtirak` | Replaces the 14 provider tables and the loss account; clears the subscriber-to-account links |
| `python -m app.pipeline.identities --replace` | Rebuilds the customer record of every subscriber |
| `python -m app.pipeline.portal --replace` | Rebuilds the portal's bills and payments from the invoices |
| `python -m scripts.data_provenance --purge-demo` | Deletes the rows the seeder invented |
| `python -m scripts.data_provenance --clear-chat` | Deletes stored chat conversations |
| `python -m scripts.reset_demo_payments --apply` | Deletes portal payments and reopens their bills |
| `python -m scripts.repair_overpayments` (without `--dry-run`) | Reduces portal payments recorded above what a bill still owed |
| `python -m scripts.create_admin --email …` | Creates an administrator, or resets that administrator's password |
| `python -m scripts.portal_access <Customer ID>` (or `--revoke`) | Sets, or removes, one customer's portal password |
| `python -m scripts.issue_registration_codes …` | Replaces the registration codes of the accounts it covers |
| `python -m tests.test_api` | Writes test data to the database it is pointed at, then restores most of it |
| `node tests/e2e_profile.mjs`, `node tests/e2e_engines.mjs` | Change demo passwords and alerts, then restore them |
| `POST /ishtirak/loss/refresh`, `POST /ai/anomalies/run` | Rebuild stored analysis tables |

---

## Deployment

`render.yaml` is a Render blueprint covering the web service and the PostgreSQL
database. After pushing to GitHub:

1. **Render** → New → Blueprint → select the repository. It reads `render.yaml`.
2. Set `CORS_ORIGINS` in the Render dashboard to your Vercel URL.
3. **Vercel** → import the repo, root directory `frontend`, and set
   `VITE_API_URL` to the Render service URL.
4. Create the first administrator from the Render shell:
   `python -m scripts.create_admin --email <address> --name "<name>"`.

**Never run the seeder against a deployed database.** It creates demo logins whose
passwords are published in this README, and it refuses any database that is not SQLite.
`render.yaml` sets `RETURN_RESET_TOKEN_IN_RESPONSE` to `false`, and it must stay `false`
in production.

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'app'`**, run commands from the `backend/`
directory, not from inside `app/`.

**Frontend shows "Cannot reach the server"**: the backend is not running, or
`VITE_API_URL` in `project/.env` does not match its address.

**CORS error in the browser console**: add the frontend's origin to `CORS_ORIGINS`
in `.env` and restart the backend.

**Login fails with correct credentials**: a database loaded from the supplied dataset
has no logins until you run `python -m scripts.create_admin`; the seeder does nothing on a
database that already holds data.

**Want to start over**: `python -m app.pipeline.seed --reset` **deletes every table**,
including loaded data and registered accounts, then rebuilds the demo database. Back up
first.

---

## Backups

SRS Section IV requires daily backups.

```bash
python -m scripts.backup                    # writes into ./backups
python -m scripts.backup --keep 14          # change the retention window
python -m scripts.backup --verify-only backups/energy-20260730-020000.sql.gz
```

The script picks its method from `DATABASE_URL`: `pg_dump` for PostgreSQL, and
SQLite's online backup API for SQLite, which is safe to run while the server is
serving requests, unlike copying the file. Every backup is gzipped, then read back
end to end before being counted as good, because a truncated archive opens fine and
fails on the day you need it.

`render.yaml` schedules it as a daily cron service at 02:00 UTC, writing to a
mounted disk. Scheduling instructions for cron and Windows Task Scheduler are at
the bottom of `scripts/backup.py`.
