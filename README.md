# VoltIQ

**One platform for a private electricity provider (ishtirak):** customer
portal, AI analytics, office CRM and a field app for meter readers, all
running on **one API, one database and one login**.

Built from the NXTTRN × MUBS industry internship projects (Energy Analytics,
Smart Utility CRM, Field mobile app) and unified into a single system that can
grow into a stand-alone product or a SaaS.

- **Architecture, components and why we chose them:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- **Putting it online (GitHub Pages, Render, Codespaces, Docker):** [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
- **API details, data loading and security notes:** [backend/README.md](backend/README.md)
- **Field app:** [mobile/README.md](mobile/README.md)

---

## What is inside

| Folder | What it is | Tech |
|---|---|---|
| [`backend/`](backend) | The API: login and roles, analytics, AI, CRM, reports | Python 3.11, FastAPI, SQLAlchemy, scikit-learn, statsmodels |
| [`frontend/`](frontend) | The web app: customer portal (`/app`), admin analytics (`/admin`), CRM (`/crm`) | React 18, TypeScript, Vite, Tailwind |
| [`mobile/`](mobile) | Field app for meter readings and collection | Flutter |
| [`deploy/`](deploy), [`docker-compose.yml`](docker-compose.yml) | Install everything on one server | Docker, nginx, PostgreSQL |
| [`render.yaml`](render.yaml) | Free online API + database on Render | Render Blueprint |
| [`.github/workflows/`](.github/workflows) | Tests on every push, web app published to GitHub Pages | GitHub Actions |
| [`.devcontainer/`](.devcontainer) | Run the whole system inside GitHub Codespaces | Dev Containers |
| [`docs/`](docs) | Architecture, deployment, old internship notes (`docs/legacy/`) | Markdown |

### Who uses what

| Person | App | After sign-in |
|---|---|---|
| Customer | Web | `/app`: own consumption, bills, payments, tips, alerts, chatbot |
| Admin / manager | Web | `/admin`: analytics, energy loss, forecast, segments, anomalies, reports, and the CRM (menu **Utility CRM**) |
| Office staff | Web | `/crm`: customers, employees, billing and payments, reports, settings |
| Field employee | Mobile (and web `/crm`) | Assigned customers, meter readings, collections |

---

## Run it on your computer (VS Code)

### 1. What you need

- **Python 3.11 or 3.12** (`python --version`)
- **Node.js 22** or newer (`node --version`)
- **Git** and **VS Code**
- Optional: the **Flutter SDK**, for the mobile app

### 2. Get the code

```bash
git clone https://github.com/w3-ai-lb/Volt-IQ.git
cd Volt-IQ
code .
```

When VS Code asks, install the recommended extensions (Python, ESLint, Tailwind, Flutter).

### 3. Set up the API (first time only)

```bash
cd backend
python -m venv .venv
# Windows:   .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # Windows: copy .env.example .env
python -m app.pipeline.seed   # creates a local database with demo data
```

> In VS Code, choose the `.venv` Python with **Ctrl+Shift+P > Python: Select Interpreter**,
> so the tasks below use it.

### 4. Set up the web app (first time only)

```bash
cd frontend
npm install
```

### 5. Start everything

In VS Code: **Terminal > Run Task... > VoltIQ: start everything**.

Or by hand, in two terminals:

```bash
# terminal 1
cd backend && python -m uvicorn app.main:app --reload --port 8000
# terminal 2
cd frontend && npm run dev
```

- Web app: **http://localhost:5173**
- API documentation (try every endpoint): **http://localhost:8000/docs**

### 6. Demo accounts

These exist **only** in a database created by the demo seeder. The passwords
are public, so never use the seeder on a server with real data.

| Role | Email | Password | Lands on |
|---|---|---|---|
| Admin | `admin@nxttrn.com` | `admin123` | `/admin` (CRM in the menu) |
| Customer | `customer@nxttrn.com` | `customer123` | `/app` |
| Office staff | `office@voltiq.demo` | `office1234` | `/crm` |
| Field employee | `field@voltiq.demo` | `field1234` | `/crm`, and the mobile app |

### 7. Run the tests

```bash
cd backend
python -m pytest tests/test_crm.py -q     # CRM module
python -m tests.test_security             # 64 security checks
python -m tests.test_api                  # full API walk-through (needs the demo data)
cd ../frontend
npm run typecheck && npm run build
```

Or **Terminal > Run Task... > VoltIQ: run tests**. The same checks run on
GitHub for every push (Actions tab).

---

## Put it online for free

Short version (details in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)):

1. **API + database on Render:** New > Blueprint > pick this repo (`render.yaml` does the rest).
2. **Web app on GitHub Pages:** Settings > Pages > Source: **GitHub Actions**,
   and set the repository variable `VITE_API_URL` to the Render address.
   GitHub Pages on a free organisation needs a **public** repository.
3. **Or, with nothing to install:** Code > Codespaces > Create codespace, then
   run the task **VoltIQ: start everything**.

---

## How the code is organised (where to change things)

| I want to... | Look here |
|---|---|
| Add an API endpoint | `backend/app/routers/<module>.py` (+ shapes in `backend/app/schemas/`) |
| Add a database column/table | `backend/app/models/` (new columns on existing tables: also `_LATER_COLUMNS` in `backend/app/database.py`) |
| Change who may do what | `backend/app/core/deps.py` (`require_admin`, `require_staff`, `require_office`) |
| Change a customer or admin page | `frontend/src/pages/` |
| Change a CRM screen | `frontend/src/modules/crm/components/` (data: `frontend/src/modules/crm/context/DataContext.jsx`) |
| Change how the web app calls the API | `frontend/src/services/api.ts` and `frontend/src/modules/crm/crmApi.js` |
| Change the field app | `mobile/lib/screens/` (API calls: `mobile/lib/services/api_service.dart`) |
| Change the demo data | `backend/app/pipeline/seed.py` and `backend/app/pipeline/crm_seed.py` |
| Change the AI | `backend/app/ai/` |

### Main settings (`backend/.env`)

| Setting | Meaning |
|---|---|
| `DATABASE_URL` | SQLite file by default; `postgresql+psycopg2://...` in production |
| `JWT_SECRET_KEY` | Signs login tokens. Must be long and random outside your laptop |
| `CORS_ORIGINS` | Web addresses allowed to call the API |
| `CURRENCY`, `TARIFF_LBP_PER_KWH` | Currency and fallback tariff (the CRM **Settings** page sets the monthly tariff) |
| `FIXED_CHARGE_PER_INVOICE` | Fixed charge added to each invoice issued from a reading |
| `OPENAI_API_KEY` | Optional, for better chatbot answers |
| `SEED_DEMO_DATA_ON_EMPTY_DB` | `true` only for demo servers: loads demo data on first start |

---

## What changed in the unification (summary)

- **CRM web app** moved into the main web app as a module (`/crm`). It now
  reads and writes through the API (`/crm/*`) instead of Supabase. Its separate
  login, browser-stored passwords and "switch user" menu were removed. Staff
  use the platform login.
- **Field app** now calls the API instead of Supabase. The hard-coded admin
  login was removed. Bills are calculated by the server, not the phone.
- **Backend** gained the CRM module (`backend/app/routers/crm.py`), an
  `employees` table with sign-in roles `staff` and `field`, demo CRM data, and tests.
- **Removed:** the separate launcher (`Unified_Application/`) and the
  Supabase dependency. Old notes are kept in [`docs/legacy/`](docs/legacy).
- **Added:** CI, GitHub Pages deploy, Render blueprint, Codespaces, Docker Compose, VS Code tasks.

The full history of the original internship repository is preserved in this
repository's git log.

## Next steps

See the roadmap in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#5-from-internship-project-to-product-the-roadmap).
The next big step is **multi-company support (SaaS)**.
