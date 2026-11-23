#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
exec "${UNIFIED_PYTHON:-python3}" launcher.py start
