#!/usr/bin/env python
"""
Database backup, SRS Section IV, Reliability: "daily backups".

Works against whichever engine DATABASE_URL points at:

  PostgreSQL   runs pg_dump into a timestamped .sql.gz
  SQLite       uses the sqlite3 online backup API, which is safe to run while
               the server is serving requests, copying the file with `cp`
               while a write is in flight can produce a corrupt backup

Usage:
    python -m scripts.backup                      # write into ./backups
    python -m scripts.backup --out /var/backups   # somewhere else
    python -m scripts.backup --keep 14            # change the retention window
    python -m scripts.backup --verify-only PATH   # check an existing backup

Scheduling is in the deployment notes at the bottom of this file.
"""

from __future__ import annotations

import argparse
import gzip
import logging
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

# Run from the backend/ directory so `app` is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
logger = logging.getLogger("backup")

DEFAULT_KEEP_DAYS = 7


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------
def backup_sqlite(url: str, out_dir: Path) -> Path:
    """
    Copy the database using SQLite's online backup API.

    Taking a consistent snapshot matters more than it looks: a plain file copy
    taken mid-transaction yields a file that opens fine and fails later, which
    is the worst kind of backup, one you find out about when you need it.
    """
    source_path = url.split("///", 1)[-1]
    source = Path(source_path)
    if not source.is_absolute():
        source = Path(__file__).resolve().parent.parent / source

    if not source.exists():
        raise FileNotFoundError(f"No SQLite database at {source}")

    target = out_dir / f"energy-{_stamp()}.sqlite3"

    with sqlite3.connect(str(source)) as src, sqlite3.connect(str(target)) as dst:
        src.backup(dst)

    compressed = target.with_suffix(target.suffix + ".gz")
    with open(target, "rb") as raw, gzip.open(compressed, "wb") as gz:
        shutil.copyfileobj(raw, gz)
    target.unlink()

    return compressed


# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------
def backup_postgres(url: str, out_dir: Path) -> Path:
    """Run pg_dump and gzip the result."""
    if shutil.which("pg_dump") is None:
        raise RuntimeError(
            "pg_dump is not on PATH. Install the PostgreSQL client tools "
            "(postgresql-client on Debian/Ubuntu)."
        )

    parsed = urlparse(url.replace("postgresql+psycopg2://", "postgresql://"))
    target = out_dir / f"energy-{_stamp()}.sql.gz"

    env = dict(os.environ)
    if parsed.password:
        # Passed by environment rather than on the command line, so the
        # password does not appear in the process list.
        env["PGPASSWORD"] = parsed.password

    command = [
        "pg_dump",
        "--host", parsed.hostname or "localhost",
        "--port", str(parsed.port or 5432),
        "--username", parsed.username or "postgres",
        "--dbname", (parsed.path or "/energy_analytics").lstrip("/"),
        "--no-owner",
        "--no-privileges",
    ]

    logger.info("Running pg_dump against %s", parsed.hostname or "localhost")
    with gzip.open(target, "wb") as gz:
        process = subprocess.run(command, stdout=subprocess.PIPE, env=env, check=False)
        if process.returncode != 0:
            target.unlink(missing_ok=True)
            raise RuntimeError(f"pg_dump exited with status {process.returncode}")
        gz.write(process.stdout)

    return target


# ---------------------------------------------------------------------------
# Verification and retention
# ---------------------------------------------------------------------------
def verify(path: Path) -> bool:
    """
    Confirm the file is a readable archive with content in it.

    A backup nobody has ever restored is a hope, not a backup. This is the
    cheap half of that: it at least proves the archive is not truncated or
    empty, which is how most silent backup failures present.
    """
    try:
        with gzip.open(path, "rb") as gz:
            head = gz.read(512)
            if not head:
                logger.error("%s is empty", path.name)
                return False
            if path.name.endswith(".sqlite3.gz") and not head.startswith(b"SQLite format 3"):
                logger.error("%s does not look like a SQLite database", path.name)
                return False
            # Read to the end so a truncated gzip raises here rather than on
            # the day someone needs to restore it.
            while gz.read(1 << 20):
                pass
        return True
    except Exception as exc:
        logger.error("%s failed verification: %s", path.name, exc)
        return False


def prune(out_dir: Path, keep: int) -> int:
    """Keep the newest `keep` backups, delete the rest."""
    backups = sorted(
        [p for p in out_dir.glob("energy-*.gz")],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    removed = 0
    for old in backups[keep:]:
        old.unlink()
        logger.info("Pruned %s", old.name)
        removed += 1
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="Back up the platform database.")
    parser.add_argument("--out", default="backups", help="Directory to write into")
    parser.add_argument("--keep", type=int, default=DEFAULT_KEEP_DAYS,
                        help="How many backups to retain")
    parser.add_argument("--verify-only", metavar="PATH",
                        help="Verify an existing backup and exit")
    args = parser.parse_args()

    if args.verify_only:
        return 0 if verify(Path(args.verify_only)) else 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    url = settings.DATABASE_URL
    logger.info("Backing up %s", "PostgreSQL" if url.startswith("postgres") else "SQLite")

    try:
        target = backup_postgres(url, out_dir) if url.startswith("postgres") \
            else backup_sqlite(url, out_dir)
    except Exception as exc:
        logger.error("Backup failed: %s", exc)
        return 1

    size_mb = target.stat().st_size / (1024 * 1024)
    if not verify(target):
        logger.error("Backup written but failed verification, not counting it as good")
        return 1

    logger.info("Wrote %s (%.2f MB), verified", target.name, size_mb)
    prune(out_dir, args.keep)
    return 0


if __name__ == "__main__":
    sys.exit(main())


# ---------------------------------------------------------------------------
# Scheduling
#
# Render (what render.yaml deploys to): add a Cron Job service:
#
#     name:     energy-analytics-backup
#     schedule: "0 2 * * *"          # 02:00 UTC daily
#     command:  python -m scripts.backup --out /var/data/backups --keep 7
#
#   Attach a persistent disk mounted at /var/data, otherwise the backups go
#   into the container filesystem and vanish with it: which would leave the
#   Reliability requirement technically satisfied and practically useless.
#
# Linux server: crontab -e:
#
#     0 2 * * * cd /srv/energy/backend && ./venv/bin/python -m scripts.backup >> /var/log/energy-backup.log 2>&1
#
# Windows: Task Scheduler, daily at 02:00:
#
#     Program:   C:\path\to\venv\Scripts\python.exe
#     Arguments: -m scripts.backup
#     Start in:  C:\path\to\backend
# ---------------------------------------------------------------------------
