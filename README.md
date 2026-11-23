# Energy Platform

Start the combined web workspace with `Unified_Application/START_APP.bat` on Windows.
The local portal opens at http://127.0.0.1:8780 after startup.
See [launcher instructions](Unified_Application/README.md) and the [bilingual code guide](Unified_Application/CODE_GUIDE_EN_AR.md).

Analytics uses the root frontend and backend. The CRM web and Flutter mobile projects are in `crm/`.
Supply your Supabase project URL and **publishable** key in `crm/Web app/.env`
using VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY. For Flutter use
`--dart-define=SUPABASE_URL=...` and `--dart-define=SUPABASE_ANON_KEY=...`.
Private datasets for optional import pipelines are supplied separately. The local demo seeder is included.
CRM authentication is demo-oriented. Provision a working backend and enforce company data access before live customer use.

---

# AI-Powered Energy Analytics and Customer Engagement Platform

**NXTTRN × MUBS Industry Internship**

A web platform for a private Lebanese electricity provider. It gives customers a
clear view of their own consumption, bills and payments, and gives the provider
analytics across its whole customer base.

The system follows a three-tier architecture: a React presentation layer, a
FastAPI application layer, and a PostgreSQL data layer.

---

## What is in this repository

| Folder | Contents | Status |
|---|---|---|
| `frontend/` | React + TypeScript client, all customer and administrator screens | Complete |
| `backend/` | FastAPI application layer, REST API and AI module | Complete |

Setup, configuration, data loading and testing for the backend are in
[`backend/README.md`](backend/README.md).

---

## Frontend

React 18 with TypeScript, built with Vite and styled with Tailwind CSS.

| Concern | Choice |
|---|---|
| Routing | React Router v7 |
| Charts | Chart.js via react-chartjs-2 |
| Animation | Framer Motion |
| Icons | Lucide React |
| HTTP | Axios, with a shared interceptor for the auth token |

### Running it

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```

`npm install` restores the dependencies from `package.json`. They are not
committed, which is why this repository is under a megabyte rather than the
176 MB the installed tree occupies on disk.

### Configuration

Copy `frontend/.env.example` to `frontend/.env` if the API is not on the default
address:

```
VITE_API_URL=http://localhost:8000
```

The client falls back to that same address when the variable is unset, so local
development needs no configuration at all.

---

## Screens

**Customer portal.** Dashboard, consumption (monthly, daily and an averaged
24-hour load profile), bills, payments with downloadable receipts, personalised
recommendations, alerts, an assistant, and profile settings.

**Administrator.** Executive dashboard, customer management, analytics with a
regional breakdown, revenue, demand forecasting, customer segmentation, anomaly
detection, and report generation.

Which application a user sees is decided by their account role, and the
distinction is enforced by the API rather than only hidden in the interface.

---

## Structure

```
frontend/src/
├── pages/
│   ├── customer/        Dashboard, consumption, bills, payments,
│   │                    recommendations, alerts, assistant, profile
│   ├── admin/           Executive dashboard, customers, analytics, revenue,
│   │                    forecast, segmentation, anomalies, reports
│   └── auth/            Login, register, password recovery
├── components/
│   ├── ui/              Buttons, inputs, cards, tables, modals, toasts
│   └── charts/          Line, bar, area and doughnut wrappers
├── layouts/             Auth, customer and admin shells
├── context/             Authentication, theme and toast providers
├── routes/              Route guards by role
└── services/api.ts      Every API call the application makes
```

`services/api.ts` is the single place the frontend talks to the backend. Every
page goes through it, so the API surface is visible in one file rather than
scattered across thirty components.

---

## Documentation

`Software Requirements Specification SRS.docx` and `Software Architecture.docx`
are in this repository. The architecture document describes the three-tier design
the code follows, and the SRS lists the functional and non-functional
requirements each screen implements.
