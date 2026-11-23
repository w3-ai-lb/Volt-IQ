#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Put the project under version control and push it to GitHub.
#
# "GitHub repository with full source code" is an explicit Proposal
# deliverable. This script does the local half; the push needs your own
# GitHub account, so it stops and tells you the two commands to run.
#
# Run it once, from the project root (the folder containing backend/ and
# project/):
#
#     bash backend/scripts/init_repo.sh
# ---------------------------------------------------------------------------
set -euo pipefail

# The frontend folder has been called both "project" and "frontend"; accept
# either rather than failing on a folder somebody renamed.
FRONTEND=""
for candidate in frontend project; do
  [ -d "$candidate" ] && FRONTEND="$candidate" && break
done

if [ ! -d backend ] || [ -z "$FRONTEND" ]; then
  echo "Run this from the project root, the folder that contains both"
  echo "backend/ and the frontend folder."
  exit 1
fi

if [ -d .git ]; then
  echo "This folder is already a git repository. Nothing to initialise."
  echo "To see what is not yet committed:  git status"
  exit 0
fi

# Refuse to proceed without ignore rules. A first commit that swallows
# node_modules and .env is far more work to undo than to prevent.
if [ ! -f .gitignore ]; then
  echo "No .gitignore in the project root."
  echo "Add it before initialising, or secrets and node_modules will be committed."
  exit 1
fi

echo "Initialising repository..."
git init -b main

# Identity, only if it is not already configured globally.
git config user.name  >/dev/null 2>&1 || git config user.name  "Christine Dakdouk"
git config user.email >/dev/null 2>&1 || git config user.email "christinedakdouk@gmail.com"

git add .

echo
echo "Files staged for the first commit:"
git diff --cached --name-only | head -40
staged=$(git diff --cached --name-only | wc -l)
echo "  ... $staged files total"

# Last line of defence: if these are staged, the ignore rules did not work.
for bad in .env node_modules venv; do
  if git diff --cached --name-only | grep -q "^${bad}\|/${bad}/"; then
    echo
    echo "STOP: '$bad' is staged. Fix .gitignore before committing."
    echo "      git rm -r --cached $bad"
    exit 1
  fi
done

git commit -q -m "AI-Powered Energy Analytics and Customer Engagement Platform

React + TypeScript frontend and FastAPI backend implementing the three-tier
architecture: presentation, application and data layers.

Backend: authentication (JWT + bcrypt), customer management, billing,
payments, reporting, and the AI module, demand forecasting (SARIMA),
anomaly detection (IsolationForest), customer segmentation (KMeans),
a recommendation engine, an alert engine, payment-default risk scoring
and a support chatbot.

NXTTRN x MUBS industry internship."

echo
echo "Committed. Next, create the repository on GitHub and push:"
echo
echo "  1. Go to https://github.com/new"
echo "     Name it, for example, energy-analytics-platform."
echo "     Do NOT tick 'Add a README'. This repository already has one."
echo
echo "  2. Then run these two commands here:"
echo
echo "       git remote add origin https://github.com/YOUR-USERNAME/energy-analytics-platform.git"
echo "       git push -u origin main"
echo
echo "If GitHub asks for a password, it wants a personal access token instead:"
echo "https://github.com/settings/tokens  ->  Generate new token (classic), scope 'repo'."
