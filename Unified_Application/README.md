# Unified Energy Workspace

One local launcher starts the original Energy Analytics web application, its FastAPI API, the Smart Utility CRM web application, and a central application switcher.

Verified on Windows: both builds, 37 integration checks, and 64 original backend security checks passed. CRM's remote Supabase dependency remains unavailable; its interface runs, but cloud-backed records and synchronization are blocked. See `INTEGRATION_REPORT.md` for the exact verification scope and `CODE_GUIDE_EN_AR.md` for the English/Arabic code walkthrough.

## Start on Windows

1. Open this folder.
2. Double-click **START_APP.bat**. Keep its terminal open.
3. On first launch, allow time for dependency downloads and both production builds. Progress is printed in the terminal; detailed output is in `logs`.
4. When **LOCAL SERVICES READY** appears, open **http://127.0.0.1:8780**.
5. Choose **Energy Analytics** or **Utility CRM**. The top navigation remains available. **Open in tab** supports workflows such as printing in a full browser tab.

بالعربية: افتح هذا المجلد وشغّل `START_APP.bat`، وانتظر رسالة جاهزية الخدمات، ثم افتح الرابط أعلاه واختر التطبيق. لإيقاف الخدمات شغّل `STOP_APP.bat`.

Stop with **STOP_APP.bat**, or press **Ctrl+C** in the launch terminal. A second start is refused while the first launcher is active. On Windows, a Job Object closes managed process trees when the launcher exits, including when its terminal is closed.

Command-line equivalents, from this folder:

```text
python launcher.py prepare
python launcher.py start
python launcher.py stop
```

`prepare` downloads dependencies, builds the real frontends, and prepares isolated local data. `start` performs preparation automatically if necessary. On macOS/Linux, use `sh start.sh` with Python 3.11/3.12 and Node 22.12+ installed. Cross-platform launch is provided but Windows is the target verification environment.

## Prerequisites

- Python **3.11 or 3.12**, with pip and venv.
- Node.js **22.12 or newer** (24 LTS recommended). CRM uses Vite 8, so older Node installations are unsuitable.
- Internet access for the initial npm/PyPI installation and CRM Supabase features.
- Several GB of free disk space for isolated dependencies and builds.

The Windows wrapper checks `UNIFIED_PYTHON`, the Python launcher, PATH, then the Codex bundled Python if present. Node detection checks `UNIFIED_NODE`, PATH, then the Codex bundled Node. No global package installation is required. If npm is unavailable, a pinned official npm archive is installed under `.tools`.

## Applications and source locations

`config.json` contains paths relative to this folder:

- Analytics: `..`, with `frontend` and `backend` directories.
- CRM: `../../../smart-utility-crm-main/smart-utility-crm-main/Web app`.

Update those two paths if you move the projects. Both original source trees must remain available. The launcher copies source into `.runtime`, installs dependencies there using the projects' existing lockfiles, and builds real production bundles. Source content changes trigger a rebuild on the next start. Original source files are preserved.

The CRM repository also contains a Flutter mobile application. This launcher integrates the two web applications; mobile build/distribution is a separate workflow.

## Architecture and ports

| Service | Default URL |
|---|---|
| Central dashboard | http://127.0.0.1:8780 |
| Analytics frontend | http://127.0.0.1:8781 |
| CRM frontend | http://127.0.0.1:8782 |
| Analytics API / Swagger | http://127.0.0.1:8783/docs |

All listeners bind to loopback only. Each frontend has a separate origin, preserving its root routes and independent browser storage. The central dashboard embeds the real application pages and retains frames while switching. SPA refresh fallback is enabled. Separate-tab links are available for printing or browser restrictions.

CRM contacts Supabase directly using the original configuration, including its realtime WebSocket subscriptions. There is no local CRM backend to launch. Analytics calls the managed local FastAPI service. CORS is set explicitly for the configured local origins. Changing ports in `config.json` rebuilds the frontend API address on the next launch.

The portal does not merge authentication or synchronize business databases. Its green local-service indicator verifies the local API, not the availability or correctness of the remote Supabase service.

## Data and configuration

- Analytics uses `.runtime/energy_analytics.db`. On first setup, the default source SQLite file is copied using SQLite's backup API if present. Otherwise the project's existing seeder creates a **new synthetic demo database** inside `.runtime`.
- Subsequent starts preserve this database. The launcher never invokes `--reset`, the replacing data loaders, or the CRM SQL setup script.
- The delivered source tree in this session contained no analytics database, so a fresh local demo is required.
- A source backend `.env` is copied when present, but the launcher explicitly overrides the database URL, JWT secret, local CORS origins, demo provisioning and reset-token exposure. It always uses its isolated SQLite database. Existing external database configurations are not opened by this launcher.
- A random signing secret is persisted privately under `.runtime/jwt-secret` so sessions survive restarts.
- Frontend `.env` files are copied privately into their runtime build directories. Analytics `VITE_API_URL` is overridden for the managed API. CRM retains its configured Supabase URL and publishable key.
- `.runtime`, `.venv`, `.tools`, and `logs` are excluded from source control. Do not share them, since they can contain private configuration and application data.

For a newly seeded analytics demo only, the source project's documented logins are `admin@nxttrn.com` / `admin123` and `customer@nxttrn.com` / `customer123`. A copied existing database keeps its own credentials.

CRM's existing implementation defaults a fresh browser to a demo administrator, stores session state locally, and has permissive fallback sign-in logic. The unified launcher preserves this original behavior; it is not a secure production authentication implementation. CRM also mixes local fallback records and remote data. A visible dashboard alone does not confirm that records were synchronized.

## Troubleshooting

- **Port occupied**: edit the corresponding port in `config.json`, or close the application that owns it. The launcher never stops unrelated processes.
- **Already running**: open the portal or run `STOP_APP.bat`. The OS releases the launcher lock after exit; the lock file itself is harmless.
- **Install/build failure**: read the named file under `logs`. Restore internet access and run START again. Successful dependency/build stages are cached.
- **Missing project file**: correct the relative project path in `config.json`.
- **CRM appears but cloud data fails**: verify the original Supabase project is active, the URL/publishable key are valid, required tables exist, and access policies permit the intended operations. Configure the source frontend environment and restart to rebuild. Never put a Supabase service-role secret in a Vite variable.
- **Supabase setup**: the delivered `supabase_setup.sql` starts by dropping tables. It is not executed by this integration. Have the project owner inspect the existing schema and apply only necessary non-destructive changes.
- **Analytics API fails**: inspect `logs/api.log` and verify Python requirements installed successfully.
- **CRM refresh returns to its dashboard**: the original CRM uses in-memory tab state instead of URL routes. This behavior is preserved.
- **Print/download issue in embedded view**: select Overview and use Open in tab, then repeat the workflow.

The portal is for local operation. Production hosting, shared sign-in, mobile changes and cross-application business-data migration are outside this integration.
