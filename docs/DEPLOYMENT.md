# Putting VoltIQ online

VoltIQ has two parts that need hosting:

| Part | What it is | Where it can live for free |
|---|---|---|
| **Web app** | Static files (HTML/CSS/JS) | **GitHub Pages** |
| **API + database** | A Python server and PostgreSQL | **Render** (free tier), or **GitHub Codespaces** for short demos |

GitHub Pages can only serve static files. It cannot run the Python API. So
"online for free" means **GitHub Pages for the web app + Render for the API**.

---

## Option A: GitHub Pages + Render (recommended free setup)

### Step 1: Turn on GitHub Pages

> **Important:** on a **free** GitHub organisation, Pages works only for
> **public** repositories. `w3-ai-lb/Volt-IQ` is private. Choose one:
> - make the repository public (Settings > General > Danger Zone > Change visibility), or
> - upgrade the organisation to GitHub Team, or
> - keep it private and use Option B or C below.

1. Repository **Settings > Pages**.
2. Under **Build and deployment > Source**, choose **GitHub Actions**.
3. Push to `main` (or run the workflow by hand: **Actions > Deploy web app to GitHub Pages > Run workflow**).
4. The site appears at **https://w3-ai-lb.github.io/Volt-IQ/**.

At this point the site opens, but sign-in fails because there is no API yet.

### Step 2: Put the API on Render

1. Create a free account at render.com and connect your GitHub.
2. **New > Blueprint** and pick the `Volt-IQ` repository. Render reads
   `render.yaml` and creates:
   - `voltiq-api` (the Python API),
   - `energy-analytics-db` (PostgreSQL).
3. When it is live, copy the API address, for example
   `https://voltiq-api.onrender.com`. Open `/docs` on it to check.

`render.yaml` sets `SEED_DEMO_DATA_ON_EMPTY_DB=true`, so the first start fills
the empty database with **demo data**. Change it to `false` in the Render
dashboard **before** real customer data goes in. The demo passwords are public.

### Step 3: Connect the two

1. GitHub repository **Settings > Secrets and variables > Actions > Variables > New repository variable**:
   - Name: `VITE_API_URL`
   - Value: your Render address, for example `https://voltiq-api.onrender.com`
2. Re-run the Pages workflow (Actions > Deploy web app to GitHub Pages > Run workflow).
3. If your Pages address is different from `https://w3-ai-lb.github.io`, add
   it to `CORS_ORIGINS` on Render (comma-separated).

Now open the Pages site and sign in with a demo account (see the README).

**Free tier limits:** a free Render server sleeps after about 15 minutes
without visitors. The first request after that takes around a minute. The free
PostgreSQL database is deleted after 30 days unless you upgrade.

---

## Option B: GitHub Codespaces (whole system, nothing to install)

Good for development and for showing the system to someone for an hour.

1. On the repository page: **Code > Codespaces > Create codespace on main**.
2. Wait for the setup to finish. It installs everything and loads demo data.
3. **Terminal > Run Task... > VoltIQ: start everything**.
4. Open the **Ports** tab. Port **5173** is the web app and **8000** is the API.
5. To show it to someone else, right-click both ports and choose
   **Port Visibility > Public**. Then set the web app to use the public API
   address. Create `frontend/.env.local` with
   `VITE_API_URL=<the public 8000 address>`, add the 5173 address to
   `CORS_ORIGINS` in `backend/.env`, and restart the tasks.

Codespaces stops when idle, and personal accounts get a number of free hours each month.

---

## Option C: One server with Docker (the stand-alone product)

This is how you would install VoltIQ for one electricity company on its own server.

```bash
cp deploy/.env.example deploy/.env     # then edit every value
docker compose --env-file deploy/.env up -d --build
```

Open `http://<server-address>/`. The web app and the API share one address,
because nginx forwards `/api` to the API container.

Create the first administrator:

```bash
docker compose exec api python -m scripts.create_admin --email you@company.com --name "Your Name"
```

Back up the database volume (`db-data`) regularly.

> This setup was written but not yet run end-to-end. Test it on a spare machine first.
