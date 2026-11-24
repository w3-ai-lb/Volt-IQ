# VoltIQ Architecture

This document explains **how VoltIQ is built**, **what each part does**, and
**why we chose it**. It is written in simple English on purpose.

VoltIQ started as three separate pieces from the NXTTRN × MUBS internship:

1. **Energy Analytics**: a website plus a Python API, for customers and for the company's managers.
2. **Utility CRM (web)**: a separate website for office staff, using its own database on Supabase.
3. **Field app (mobile)**: a Flutter phone app for meter readers, also using Supabase.

These three pieces did not share data. A reading taken on the phone did not reach
the analytics. Each piece had its own login. A small launcher started them side by side.

**VoltIQ joins them into one system:** one API, one database and one login, used by every app.

> **Optimization log:** every improvement is recorded as a named, timestamped
> stage in [section 7](#7-optimization-log). The newest stage is marked **🆕 NEW**.
>
> | Stage | Name | Date | |
> |---|---|---|---|
> | 1 | One System (unification) | 2026-11-24 00:13 (UTC+2) | |
> | 2 | Linked Billing, Staff Users & Fast Lists | 2026-11-24 02:20 (UTC+2) | **🆕 NEW** |

---

## 1. The big picture

```mermaid
flowchart TB
    subgraph Users
        C[Customer]
        M[Manager / Admin]
        O[Office staff]
        F[Field employee]
    end

    subgraph Apps["Apps (what people use)"]
        W["Web app (React)<br/>customer portal + admin analytics + CRM"]
        P["Field app (Flutter)<br/>meter readings and collection"]
    end

    subgraph Server["Server (one API)"]
        API["VoltIQ API (FastAPI, Python)"]
        AUTH[Login and roles]
        AN[Analytics and reports]
        AI[AI engine: forecast, anomalies, segments, chatbot]
        CRM[CRM: customers, staff, readings, invoices, payments]
        API --- AUTH & AN & AI & CRM
    end

    DB[("PostgreSQL database<br/>(SQLite on a laptop)")]

    C & M & O --> W
    F --> P
    W -- "HTTPS + JSON" --> API
    P -- "HTTPS + JSON" --> API
    API --> DB
```

**In one sentence:** every app talks only to the API, and only the API talks
to the database.

That single rule is the most important decision in this document. It means:

- The data has **one source of truth**. A reading saved on a phone is already
  an invoice in the CRM and a data point for the AI.
- **Security is in one place.** The API checks who you are and what you may
  do, for every request, from every app.
- We can **change or add an app** (for example a customer mobile app) without
  touching the database.

---

## 2. The components, one by one

### 2.1 Web app: `frontend/`

| | |
|---|---|
| **What it is** | One website with three areas: the **customer portal** (`/app`), the **admin analytics** (`/admin`) and the **CRM** (`/crm`). |
| **Built with** | React 18, TypeScript, Vite, Tailwind CSS, React Router, Chart.js and Recharts. |
| **Who uses it** | Customers, managers, office staff. |

**Why React + TypeScript + Vite?**
- The analytics website was already built this way and works well.
- React is the most common web UI library, so new developers can join easily.
- TypeScript catches many mistakes before the code runs.
- Vite builds a fast, **static** website (plain HTML, CSS and JavaScript files),
  which can be hosted for free on GitHub Pages.

**Why we merged the CRM into the same web app** instead of keeping two websites:
- One login, one address, one design.
- An admin can jump between analytics and CRM with one click.
- The CRM screens were kept almost as they were. They live in
  `frontend/src/modules/crm/`. We changed only how they get their data:
  they now call the API instead of Supabase.

Which area a person sees depends on their **role**, and the API checks the
role again on every request.

| Role | Lands on | Can open |
|---|---|---|
| `customer` | `/app` | Own consumption, bills, payments, tips, chatbot |
| `admin` | `/admin` | Everything: analytics, AI, reports, and the CRM |
| `staff` (office) | `/crm` | CRM: customers, employees, billing, payments |
| `field` (meter reader) | `/crm` and the field app | Assigned customers, readings, collection |

### 2.2 Field app: `mobile/`

| | |
|---|---|
| **What it is** | A phone app for field employees: see your assigned customers, read the meter (camera + text recognition), and the server issues the invoice. |
| **Built with** | Flutter (Dart), Google ML Kit text recognition, camera. |
| **Talks to** | The VoltIQ API, through `lib/services/api_service.dart`. |

**Why Flutter?** It was already built, and one codebase runs on Android and iPhone.

**What we changed:** the app used to talk to Supabase. Now it uses the same API
as the website. We also removed two risky things:
- a hidden admin login written in the app's code;
- price calculation on the phone. The **server** now calculates every bill
  from the official tariff, so the phone and the office always show the same amount.

### 2.3 API: `backend/`

| | |
|---|---|
| **What it is** | The brain of the system. It receives requests from the apps, checks the user, applies the business rules, runs the AI, and reads or writes the database. |
| **Built with** | Python 3.11, FastAPI, SQLAlchemy, Pydantic. |
| **Address** | `http://localhost:8000` on your laptop. Live documentation is at `/docs`. |

**Why Python + FastAPI?**
- The AI part (forecasting, anomaly detection, segmentation) uses Python
  libraries (scikit-learn, statsmodels, pandas). Keeping the API in the same
  language means no second server just for AI.
- FastAPI is fast and simple, and it **writes the API documentation by itself**
  (open `/docs`), so the web and mobile developers can see every endpoint.
- It was already built and tested in the internship (more than 150 tests).

The API is split into **modules** (folders in `backend/app/routers/`):

| Module | Address | What it does |
|---|---|---|
| Auth | `/auth/*` | Sign in, register with a code, password reset and change |
| Customer portal | `/dashboard/customer`, `/consumption`, `/bills`, `/payments`, `/alerts`, ... | A customer's own data |
| Analytics | `/analytics/*`, `/revenue/*`, `/customers`, `/dashboard/admin` | Company-wide numbers, regions, revenue, customer accounts |
| AI | `/ai/*`, `/chat/*`, `/ishtirak/ask` | Forecasts, anomalies, segments, recommendations, chatbot |
| Ishtirak (energy loss) | `/ishtirak/*` | Generator output vs. billed energy, loss per zone |
| **CRM** (new) | `/crm/*` | Customers (subscribers), employees, assignments, meter readings, invoices, payments, tariff |
| Reports | `/reports/*` | PDF and Excel exports |

**The CRM module** (`backend/app/routers/crm.py`) is the new part. It
works on the **same tables** the analytics already used (subscribers, meters,
meter readings, invoices, payments, tariffs), plus a new `employees` table.
That is what connects the three original projects.

### 2.4 Database

| | |
|---|---|
| **What it is** | Where all data lives: customers, meters, readings, invoices, payments, staff, AI results. |
| **Production** | PostgreSQL. |
| **On a laptop** | SQLite (a single file, no installation). |
| **Access** | Only through the API, using SQLAlchemy. |

**Why PostgreSQL?** It is free, very reliable, used by large companies, and
every cloud supports it. Later it lets us keep different companies' data
apart (see the roadmap below).

**Why SQLite on a laptop?** Zero setup. A new developer can run the whole
system in minutes. The code is the same for both. Only one setting
(`DATABASE_URL`) changes.

**Why we removed Supabase:** the CRM and the phone app had their own Supabase
database. That meant two copies of the customers, two logins and two sets of
rules. It also tied the product to one outside company. With everything in
one PostgreSQL database behind our API, we own the data and the rules. We can
also install the product on a customer's own server.

### 2.5 Login and security

- **One login for everyone.** Customers, admins, office staff and field staff
  all sign in with the same `/auth/login`.
- **Two account tables (since Stage 2).** Staff (admin, office, field) are in
  the `users` table. Customers sign in with their own record in `customers`.
  The login looks in `users` first, then `customers`, and one email can
  belong to only one account (`backend/app/core/accounts.py`).
- After sign-in, the API gives the app a **token (JWT)**. The app sends it
  with every request. The token says who you are and your role.
- Passwords are stored only as **bcrypt hashes**, never as plain text.
- The API checks the **role** on every request (`require_admin`,
  `require_staff`, `require_office` in `backend/app/core/deps.py`). Hiding a
  button in the app is only for convenience. The real protection is on the server.
- **What we removed for safety:** the old CRM kept staff passwords in the
  browser's storage and had a "switch user" menu. The old phone app had a
  hard-coded admin password. All of these are gone.

### 2.6 AI engine: `backend/app/ai/`

| Feature | Method | Why this method |
|---|---|---|
| Demand forecast | SARIMA (statsmodels) | Good for monthly data with seasons (summer/winter) |
| Customer segments | K-Means (scikit-learn) | Simple, explainable groups |
| Anomalies (possible theft or faults) | Isolation Forest + rules | Works without labelled "theft" examples |
| Recommendations, alerts | Rules on the customer's own data | Clear and explainable advice |
| Chatbot / "ask the data" | Rules + search in company documents (RAG), optional OpenAI model | Works with no AI key; better answers with one |

**Why simple, classic models?** They run on a small server, they need little
data, and a manager can understand **why** a customer was flagged. That
matters before anyone is accused of stealing electricity.

### 2.7 Hosting and tools

| Tool | Used for | Why | Cost |
|---|---|---|---|
| **GitHub** | Code, history, reviews | The team already uses it | Free |
| **GitHub Actions** | Runs the tests and builds on every push (`.github/workflows/ci.yml`) | Catches breakage before it reaches users | Free minutes |
| **GitHub Pages** | Hosts the **web app** online (`.github/workflows/pages.yml`) | Free, automatic on every push | Free (needs a public repo or a paid plan) |
| **Render** | Hosts the **API + PostgreSQL** (`render.yaml`) | GitHub Pages cannot run Python, so the API must live somewhere else. Render has a free tier and reads our file automatically | Free tier (sleeps when idle; free database expires after 30 days) |
| **GitHub Codespaces** | Runs the **whole system in the browser** for development or a quick demo (`.devcontainer/`) | Nothing to install | Free monthly hours for personal accounts |
| **Docker Compose** | Installs the whole system **on one server** (`docker-compose.yml`) | This is the "stand-alone product" install for a customer | Free |

See [DEPLOYMENT.md](DEPLOYMENT.md) for the exact steps.

---

## 3. How the data flows: one meter reading

This shows why the single API matters:

```mermaid
sequenceDiagram
    participant F as Field app
    participant API as VoltIQ API
    participant DB as Database
    participant W as Web app (CRM / Admin)

    F->>API: POST /crm/readings {customer, reading}
    API->>API: check the user is staff, the reading is not lower than the last one
    API->>DB: save the meter reading
    API->>DB: create the invoice (tariff of the month x kWh)
    API-->>F: the invoice (amount, kWh, rate)
    W->>API: GET /crm/invoices (refreshes every 30 s)
    API-->>W: the new invoice is already there
    Note over API,DB: The same reading feeds the energy-loss and anomaly models
```

---

## 4. Folder map

```
Volt-IQ/
├── backend/                 API (FastAPI)
│   ├── app/
│   │   ├── routers/         one file per module (auth, crm, analytics, ...)
│   │   ├── models/          database tables
│   │   ├── schemas/         request/response shapes
│   │   ├── ai/              AI engine
│   │   ├── rag/             chatbot document search
│   │   ├── pipeline/        data loading and demo data (seed.py, crm_seed.py)
│   │   └── core/            security, roles, settings helpers
│   └── tests/
├── frontend/                Web app (React)
│   └── src/
│       ├── pages/           customer and admin pages
│       ├── modules/crm/     the CRM module
│       ├── services/api.ts  every call to the API
│       └── routes/          who may open which page
├── mobile/                  Field app (Flutter)
├── deploy/                  Dockerfiles and nginx for the stand-alone install
├── docs/                    this document, deployment guide, old internship notes
├── .github/workflows/       CI and GitHub Pages
├── .devcontainer/           GitHub Codespaces setup
├── docker-compose.yml       stand-alone install
└── render.yaml              free API + database hosting
```

---

## 5. From internship project to product: the roadmap

The work so far is **Phase 1: one system.** The next phases turn it into
something you can sell as **stand-alone** (installed for one company) or as
**SaaS** (we host it for many companies).

| Phase | Goal | Main work | Status |
|---|---|---|---|
| **1. One system** | One API, one database, one login | Merge the CRM and the field app into the API; remove Supabase; CI; free hosting | **Done** |
| **2. Many companies (multi-tenant)** | One installation serves many electricity providers, each seeing only its own data | Add a `companies` table and a `company_id` on every table; PostgreSQL row-level security; a "company" claim in the login token; per-company settings (currency, tariff, logo, languages) | Next |
| **3. Packaging and selling** | Easy install and paid plans | Docker images on GitHub Container Registry; licence key that switches modules on/off (stand-alone); plans and online payment (SaaS); automatic backups and monitoring | Later |
| **4. Scale** | More customers, more data | Background job queue (Celery + Redis) for AI jobs; database migrations (Alembic); smart-meter data connectors; email/SMS delivery | Later |

**Why this order?** Phase 1 had to come first: you cannot sell one product
while it is still three systems with three databases. Phase 2 is the change
that makes SaaS possible, and it is much easier now that there is only one database.

---

## 6. Known limits today (honest list)

*Updated in Stage 2. Items fixed by a stage are listed in that stage in section 7.*

- **One company per installation.** Multi-company (SaaS) is roadmap Phase 2.
- **Two billing ledgers are kept in step, not merged.** Since Stage 2 every
  CRM invoice has a matching portal bill and payments are copied both ways,
  so all screens agree. They are still two tables underneath. Merging them
  into one is a future stage.
- **Customers' logins are still on the `customers` table.** Stage 2 moved
  only staff to `users`. Moving customers too means changing the
  registration-code flow and about 90 places in the code.
- **Staff cannot reset a forgotten password themselves** (reset by email
  works only for customers, and there is no email sending yet). An admin
  sets a new one with `python -m scripts.create_admin`.
- **The demo clean-up script** (`scripts.data_provenance --purge`) removes the
  demo staff logins, but not yet the CRM demo records (employees, meters, invoices).
- **No database migrations tool yet.** New columns and the Stage 2 staff move
  run in a small built-in step at start-up (`backend/app/database.py`). Alembic is planned.
- **The CRM web screens refresh every 30 seconds** instead of live push updates.
- **The field app was converted without a Flutter build on this machine.**
  Run `flutter pub get` and `flutter run` once to confirm (see `mobile/README.md`).
- **The Docker install was written but not run** in this environment (no Docker here).
- **GitHub Pages hosts only the web app.** The API needs Render (or another
  host) to be fully online. See [DEPLOYMENT.md](DEPLOYMENT.md).
- **Pickers still load every customer**, as small rows (name, account number,
  balance). That is fine for thousands of customers, but a searchable picker
  will be needed for tens of thousands.

---

## 7. Optimization log

Every improvement to VoltIQ is recorded here as a **stage**. The rules:

1. Each stage gets the **next number**, a **short name**, and a **timestamp**
   (date, time and time zone).
2. The newest stage is marked **🆕 NEW**. When a new stage is added, the
   marker moves to it and the old stage keeps its entry unchanged.
3. Each stage says, in simple English: **what was wrong**, **what we changed**,
   **why**, **which files**, **how it was tested**, and **what is still open**.
4. The stage table at the top of this document is updated at the same time.

---

### Stage 1: One System (unification)

**Timestamp:** 2026-11-24 00:13 (UTC+2) · commit `dd7ec9b`

**What was wrong:** three separate internship apps, two databases (one on
Supabase), three logins, and a launcher that started them side by side.

**What we changed:**
- The CRM web app became a module of the main web app (`/crm`).
- The field app calls the main API instead of Supabase.
- A new CRM part in the API (`/crm/*`), with employees and staff roles.
- Removed: Supabase, the launcher, browser-stored passwords, the "switch user"
  menu, and the hard-coded admin password in the phone app.
- Added: CI, GitHub Pages, Render, Codespaces, Docker Compose, and documentation.

**Tested:** 5 CRM tests, 64 security checks, 86 review checks, the web
build, and a check in the browser.

---

### Stage 2: Linked Billing, Staff Users & Fast Lists **🆕 NEW**

**Timestamp:** 2026-11-24 02:20 (UTC+2)

This is the second level of optimization. It fixes the first two problems found
in the Stage 1 review, plus separate staff accounts.

#### 2.1 Linked billing: one bill, seen everywhere

**What was wrong:** the customer portal reads `bills` and `payments`, but the CRM and the
field app write `invoices` and `invoice_payments`. A meter reading created an
invoice that the office could see but **the customer could not**. A payment
made in the portal never reached the CRM.

**What we changed:**
- When the CRM issues an invoice for a customer with a portal account, the
  matching **portal bill is created in the same save**. The bill is linked by
  the new column `bills.invoice_id`.
- A payment taken in the **CRM or on the phone** also appears in the customer's
  portal, and the bill turns *Paid*.
- A payment made **in the portal** also settles the CRM invoice. The CRM shows it
  as collected by "Customer portal".
- Payments are linked both ways (`payments.invoice_payment_id`), so one payment
  is never counted twice.
- The demo data links the CRM's sample invoices to the customers' existing
  portal bills, with the same amounts and the same payments.

**Why this way (mirror, not merge):** every existing screen, report and AI
model keeps reading the table it was built on, so nothing else had to change.
Merging the two ledgers into one table is a bigger job and is left for later.

**Files:** `backend/app/core/billing_link.py` (new), `backend/app/routers/crm.py`,
`backend/app/routers/billing.py`, `backend/app/models/bill.py`, `payment.py`,
`backend/app/pipeline/crm_seed.py`.

#### 2.2 Staff users: a separate `users` table

**What was wrong:** admins, office staff and field employees were stored in
the `customers` table with special roles. Two different kinds of person were
mixed in one table.

**What we changed:**
- New table **`users`** for everyone who works for the provider (roles `admin`,
  `staff`, `field`). `customers` now holds only customers.
- Sign-in checks `users` first, then `customers`. The login token records
  which table the account is in.
- **Automatic move:** when the server starts, any staff login still in
  `customers` (from an older database) is moved to `users` with the **same id**,
  so links to employees, invoices and payments still work. If that old row
  has history, it is kept without a password instead of being deleted.
- New employees created in the CRM, the demo staff, the demo admin and
  `scripts.create_admin` all go into `users`.
- One email can belong to only one account across both tables.
- Staff accounts cannot write customer-only records (chat, alert settings).

**Why staff first:** the customer login is tied to the bill registration-code
flow and to about 90 places in the code. Moving staff out gives the clean
separation now, safely. Customers can follow in a later stage.

**Files:** `backend/app/models/user.py` (new), `backend/app/core/accounts.py`
(new), `backend/app/core/deps.py`, `backend/app/core/security.py`,
`backend/app/routers/auth.py`, `analytics.py`, `billing.py`, `chat.py`,
`preferences.py`, `crm.py`, `backend/app/database.py`, `backend/app/pipeline/seed.py`,
`crm_seed.py`, `backend/scripts/create_admin.py`, `data_provenance.py`.

#### 2.3 Fast lists: fixed queries, paging and search on the server

**What was wrong:** the CRM customer list ran **one database query per
customer**, so 5,000 customers meant 5,000 queries. The web CRM downloaded
every customer, invoice and payment, and downloaded them all again every 30 seconds.

**What we changed:**
- Every list now uses a **fixed number of queries** however many rows it
  returns. The last two meter readings of all customers come from one query.
  The test checks that 2 rows and 200 rows need the same number of queries.
- New **`/crm/customers/page`**: search (name, account, phone, meter), filters
  (tariff, officer, zone, status) and paging, all done by the database.
- New **`/crm/summary`**: all dashboard totals in one small request.
- New **`/crm/customers/options`**: a small row per customer for pickers.
- Invoice and payment lists return the **latest 200** by default, with paging (`offset`).
- Web CRM: the customer directory pages and searches on the server (25 per
  page), the dashboard uses the summary, and a customer's profile loads only
  their own invoices. The 30-second refresh now reloads only the summary and
  the latest activity.

**Files:** `backend/app/routers/crm.py`, `backend/app/schemas/crm.py`,
`frontend/src/modules/crm/crmApi.js`, `context/DataContext.jsx`,
`components/customers/CustomerList.jsx`, `CustomerDetailModal.jsx`,
`components/dashboard/DashboardView.jsx`, `components/billing-payments/BillingAndPaymentsView.jsx`.

#### How Stage 2 was tested

- CRM test file: **9 of 9 pass**. The 4 new tests check: staff are in `users`
  and the old admin row was moved; a reading appears on the customer's Bills
  page and a CRM payment marks it Paid; a portal payment settles the CRM
  invoice; and lists use a fixed number of queries.
- Security checks **64 of 64**, review checks **86 of 86**. The original API
  walk-through has **1** remaining failure (the heatmap check), which was
  already failing before Stage 1.
- Fresh demo database: **51 of 51** invoices linked to a portal bill, **46 of 46**
  payments linked, and **0** differences in amount or paid status between CRM and portal.
- In the browser: admin sign-in from `users`, server-side search ("maya" → 1
  of 17), paging, and the customer profile loading its own invoices.
- Web app typecheck and build pass.

#### Still open after Stage 2

See the updated list in [section 6](#6-known-limits-today-honest-list). The
next candidates, from the Stage 1 review: smaller website downloads, real
numbers on the CRM reports page, live updates instead of 30-second refresh,
offline mode in the field app, and security (cookie login, refresh tokens,
email/SMS password reset).

---

<!-- To add Stage 3: copy the Stage 2 block above, change the number, name and
timestamp, move the "🆕 NEW" marker to it (remove it from Stage 2), and add a
row to the stage table at the top of this document. -->

