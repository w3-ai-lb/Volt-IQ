# Integration report

## Discovered applications

### Energy Analytics and Customer Engagement Platform

Source is the parent of this integration directory. The frontend uses React 18, TypeScript, Vite 5, React Router, Tailwind 3, Chart.js and Axios. `src/main.tsx` mounts `App.tsx`; root, auth, `/app/*` and `/admin/*` routes are browser routes. `src/services/api.ts` attaches JWT authorization and language headers. The original build command is `npm run build` and development command is `npm run dev`.

The backend uses Python 3.11+, FastAPI, Uvicorn, SQLAlchemy, Pydantic, bcrypt/JWT, pandas, scikit-learn and statsmodels. Its entry is `app.main:app`. Dependencies are pinned in `requirements.txt`. SQLite is the default; PostgreSQL is configurable. Settings include DATABASE_URL, JWT_SECRET_KEY, CORS_ORIGINS, optional OPENAI_API_KEY, and local-demo flags. There was no existing database or installed virtual environment in the delivered project tree.

Major workflows include customer registration/claiming, login, consumption, bills, recorded payments, PDF receipts, recommendations, alerts, chat and preferences. Administrator functions include customers, revenue, forecasts, segmentation, anomalies, reports, energy losses and field visits. API groups include `/auth`, `/dashboard`, `/consumption`, `/bills`, `/payments`, `/customers`, `/ai`, `/chat`, `/reports`, `/ishtirak` and search/preferences. Local SQL tables, generated forecast artifacts and report output support the application. Optional LLM calls are external; the core local workflows have fallback implementations. No frontend WebSocket dependency was found for analytics.

### Smart Utility CRM

Discovered beside the analytics checkout at `smart-utility-crm-main/smart-utility-crm-main/Web app`. React 19, JavaScript, Vite 8, Tailwind 4, Recharts and Supabase JS. Its entry is `src/main.jsx` and `App.jsx`. It switches dashboard/customers/employees/billing-payments/reports/settings using React state. The original build and development commands are `npm run build` and `npm run dev`.

There is no separate server source in the web project. The browser directly queries Supabase tables (`employees`, `subscribers`, `employee_subscriber_assignments`, `meter_readings`) and subscribes to realtime changes through Supabase channels. Configuration uses VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY, with baked-in fallback values. Credentials are not reproduced in this report.

CRM features include customer and employee management, assignments, bills, payment recording, receipts, analytics, settings and invoice printing. DataContext combines remote rows with local/demo state. AuthContext starts fresh browsers with demo authentication and includes permissive email-based fallback login and browser-stored passwords. These existing limitations were observed, not introduced by the integration. The runtime retains the existing flows. They should not be represented as production-grade authentication.

The same repository includes Flutter mobile source with Supabase, camera/image picker and Google ML Kit text recognition. It is preserved and is outside the requested web launcher.

A third sibling, `dual-point-energy-monitoring-main`, contains only a README, so it cannot be identified as a runnable second application. The extra similarly named directory inside analytics is empty.

## Integration design

Python's standard library orchestrates builds and serves the portal and production frontend assets. The original FastAPI runs as a supervised child. Separate loopback origins preserve root-relative paths, SPA navigation, independent browser storage and existing application behavior without framework rewrites. The portal embeds the actual applications in persistent frames and offers separate-tab links for printing/download compatibility.

Both projects are copied into private `.runtime` build directories. Original lockfiles drive npm ci. Python dependencies use a dedicated `.venv`. Successful stages are fingerprinted. No original source or database is overwritten. The source SQLite database is copied via its online backup API if present; otherwise a new isolated demo database is initialized. The launcher does not use source external database URLs.

Supabase remains an external CRM dependency. Databases and authentication are deliberately independent because the user's requirement is unified operation, not new business-data integration.

Default ports are 8780 portal, 8781 analytics UI, 8782 CRM UI and 8783 analytics API. All listeners bind to 127.0.0.1. Port checks and an exclusive launcher lock prevent collisions/duplicates. Shutdown uses a random local control token; unrelated processes are not killed. Windows Job Objects ensure descendants are cleaned up when the launcher exits. Linux/macOS use process groups for normal shutdown.

## Created files

- `launcher.py`: source discovery, installation, builds, isolated data, servers, supervision and shutdown.
- `portal/index.html`: responsive bilingual entry point and persistent application switcher.
- `config.json`, `config.example.env`: relative project paths, ports and optional executable overrides.
- `START_APP.bat`, `STOP_APP.bat`, `python.cmd`, `start.sh`: startup wrappers.
- `verify.py`: runtime integration checks against real services, including lifecycle, assets and authenticated API workflows.
- `check_crm.py`: read-only Supabase checks with redacted output.
- `.gitignore`, `README.md`, this report, and `CODE_GUIDE_EN_AR.md` with a bilingual code walkthrough.

Generated dependencies, source snapshots, builds, logs and data are confined to ignored directories within Unified_Application. There are no intentional modifications to either team's original source.

## Investigation findings and external blockers

- Node and Python were absent from the command shell's ordinary executable resolution. Existing Codex runtimes supply Node 24.22.1 and Python 3.12.14. The launcher supports these without hardcoding this user's absolute paths.
- npm was absent; the launcher bootstraps official npm 11.6.2 privately. Slow network downloads required IPv4 curl with resumable transfer. Python dependency downloads are also substantial.
- The CRM's configured Supabase hostname failed DNS resolution even when checked with network access enabled. Read-only checks of all four required table endpoints returned curl exit code 6 and HTTP status 000. Remote data, realtime synchronization, remote record creation and mobile synchronization are blocked until the owner supplies a working Supabase project/configuration.
- The user confirmed this is a GitHub download and has not supplied an active replacement Supabase project.
- `supabase_setup.sql` starts with DROP TABLE statements. It has not been executed. Recovering the original backend or provisioning a replacement requires reviewing the schema and access policies without deleting existing data.
- Analytics uses newly generated demo records if no source SQLite database exists. Imported operational CSV files remain available in the copied backend, but destructive/replacing import scripts are not run automatically.

## Verification

Verified on Windows on 7 November 2026. Detailed local results are stored under `logs`.

| Check | Observed result |
| --- | --- |
| Python syntax compilation and Windows Job Object child cleanup | Passed |
| Backend dependencies and both production frontend builds | Passed; existing large-bundle warnings are non-fatal |
| Real Windows `START_APP.bat` | Passed; printed LOCAL SERVICES READY |
| Automated integration checks | **37 passed**, no failures or skipped demo logins; `logs/verification.json` |
| Original backend security suite | **64 passed, 0 failed**; `logs/analytics-security.log`; disposable test database only |
| Portal, both real frontend bundles and JS/CSS assets | Passed |
| Local API, admin/customer login and dashboard queries | Passed |
| Unauthenticated API denial and customer/admin separation | Passed (401 and 403 respectively) |
| Customer billing history and PDF generation | Passed using the real backend and isolated synthetic records |
| CORS and nested frontend route refresh | Passed |
| Duplicate start and occupied-port handling | Passed; unrelated port owner preserved |
| Shutdown/restart | Two successful cycles; all four managed ports released after each stop |
| Browser portal navigation and portal refresh | Both applications rendered inside the portal; CRM selection survived portal refresh |
| Browser analytics workflows | Customer login, dashboard, bills, bill detail dialog, nested `/app/bills` refresh, and logout-to-login verified in its separate-tab view |
| Browser CRM workflows | Dashboard/customer directory, sign-out screen and existing demo sign-in verified in its separate-tab view |
| CRM remote database/realtime/write workflows | **Blocked**: configured Supabase host does not resolve; no remote writes attempted |

The browser automation had difficulty targeting controls inside cross-origin frames, so detailed form interaction checks used the portal's supported separate-tab origins. Both embedded interfaces themselves were observed rendering. The portal was visually inspected at a narrow viewport, with stacked cards and visible navigation; `logs/portal-proof.png` records it. This is representative workflow verification, not exhaustive validation of every original application feature.

Initial restricted test execution could not create Python's internal loopback sockets. Running the same isolated security suite with local connections enabled completed successfully; no application security logic was changed to make it pass. The local system was started again after lifecycle tests and left running at http://127.0.0.1:8780.

بالعربية: اكتمل البناء والتشغيل المحلي، ونجح 37 فحص تكامل و64 اختبار أمان. تم فحص الدخول والخروج والفواتير والتنقل وإعادة التشغيل. بيانات التحليلات تجريبية محلية. واجهة CRM تعمل، لكن الحفظ والمزامنة السحابية ما زالا متوقفين بسبب خدمة Supabase غير المتاحة؛ ظهور الواجهة لا يعني نجاح هذه العمليات.

## Startup

Open Unified_Application and double-click START_APP.bat. After local readiness is printed, open http://127.0.0.1:8780. Switch using the top bar. Stop using STOP_APP.bat or Ctrl+C in the launcher terminal. See README for prerequisites and configuration.
