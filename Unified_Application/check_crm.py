"""Read-only Supabase reachability checks. Prints status, never credentials or rows."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import launcher


def main():
    _, source = launcher.paths()
    values = {}
    for filename in (".env", ".env.local", ".env.production", ".env.production.local"):
        path = source / filename
        if path.exists():
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                match = re.match(r"\s*(VITE_SUPABASE_\w+)\s*=\s*(.*)", line)
                if match:
                    values[match[1]] = match[2].strip().strip("\"'")
    client = (source / "src/lib/supabaseClient.js").read_text(encoding="utf-8")
    for name in ("VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY"):
        if os.environ.get(name):
            values[name] = os.environ[name]
        if not values.get(name):
            match = re.search(re.escape(name) + r"\s*\|\|\s*['\"]([^'\"]+)", client)
            if match:
                values[name] = match[1]
    base = values.get("VITE_SUPABASE_URL", "").rstrip("/")
    key = values.get("VITE_SUPABASE_ANON_KEY", "")
    if not base.startswith("https://") or not key:
        raise RuntimeError("CRM requires a valid HTTPS Supabase URL and publishable key.")
    curl = shutil.which("curl.exe" if os.name == "nt" else "curl")
    if not curl:
        raise RuntimeError("curl is required for this optional connectivity check.")
    results = []
    for table in ("employees", "subscribers", "meter_readings", "employee_subscriber_assignments"):
        command = [curl, "-4", "-sS", "--connect-timeout", "10", "--max-time", "20",
                   "-H", "apikey: " + key, "-w", "\n%{http_code}", base + "/rest/v1/" + table + "?select=*&limit=1"]
        if key.startswith("eyJ"):
            command[1:1] = ["-H", "Authorization: Bearer " + key]
        process = subprocess.run(command, capture_output=True, text=True)
        response, _, code = process.stdout.rpartition("\n")
        try:
            data = json.loads(response)
        except ValueError:
            data = None
        passed = process.returncode == 0 and code == "200" and isinstance(data, list)
        result = {"table": table, "http_status": code, "passed": passed,
                  "transport_exit_code": process.returncode,
                  "transport_error": process.stderr.strip().replace(key, "[redacted]"),
                  "has_visible_row": bool(data) if passed else None}
        results.append(result)
        print(json.dumps(result), flush=True)
    (launcher.LOGS / "crm-connectivity.json").write_text(json.dumps(results, indent=2))
    return 0 if all(result["passed"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
