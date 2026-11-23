#!/usr/bin/env bash
# ============================================================
#  AI-Powered Energy Analytics Platform: Backend launcher
#  (macOS / Linux. Windows users run start.bat instead)
# ============================================================
set -e
cd "$(dirname "$0")"

echo
echo " [1/4] Checking Python..."
PY=$(command -v python3 || command -v python) || {
    echo " ERROR: Python not found. Install Python 3.11 or newer."; exit 1; }
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' || {
    echo " ERROR: Python 3.11 or newer is required. You have: $("$PY" --version)"; exit 1; }
"$PY" --version

echo " [2/4] Setting up the virtual environment..."
[ -d venv ] || "$PY" -m venv venv
# shellcheck disable=SC1091
source venv/bin/activate
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
echo "       Dependencies ready."

echo " [3/4] Preparing the database..."
[ -f .env ] || cp .env.example .env
python -m app.pipeline.seed

echo " [4/4] Starting the API server..."
cat <<'BANNER'

 ============================================================
   API   http://localhost:8000
   Docs  http://localhost:8000/docs

   Admin      admin@nxttrn.com     / admin123
   Customer   customer@nxttrn.com  / customer123

   Leave this terminal OPEN. Press CTRL+C to stop.
 ============================================================

BANNER
exec uvicorn app.main:app --reload --port 8000
