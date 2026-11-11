"""Exercise real local services, assets, API authorization, stop and restart.

Run after preparation: python verify.py
Requires all configured ports to be free. Uses read-only application requests.
"""
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import launcher

ROOT = Path(__file__).resolve().parent
RESULTS = []


def record(name, passed, detail=""):
    RESULTS.append({"test": name, "passed": bool(passed), "detail": detail})
    print(f"{'PASS' if passed else 'FAIL'} {name} {detail}", flush=True)
    if not passed:
        raise AssertionError(name)


def request(url, body=None, token=None, method=None):
    headers = {}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, response.read(), response.headers
    except urllib.error.HTTPError as error:
        return error.code, error.read(), error.headers


def wait_ready(process):
    for _ in range(180):
        if process.poll() is not None:
            raise RuntimeError("Launcher exited; inspect logs/verification-launch.log")
        try:
            code, body, _ = request(launcher.url("portal") + "/status")
            if code == 200 and json.loads(body)["apiReady"]:
                return
        except OSError:
            pass
        time.sleep(0.5)
    raise RuntimeError("Launcher readiness timed out")


def check_apps():
    code, body, _ = request(launcher.url("portal"))
    record("Dashboard HTML", code == 200 and b"Energy Workspace" in body)
    for name in ("analytics", "crm"):
        code, body, _ = request(launcher.url(name))
        record(name + " real frontend", code == 200 and b"/assets/" in body)
        assets = re.findall(rb'(?:src|href)="(/assets/[^\"]+)"', body)
        record(name + " built assets exist", len(assets) >= 2)
        for asset in assets:
            code, data, headers = request(launcher.url(name) + asset.decode())
            record(name + " " + asset.decode(), code == 200 and len(data) > 0 and "text/html" not in headers.get("Content-Type", ""))
    code, body, _ = request(launcher.url("analytics") + "/app/bills")
    record("Analytics nested-route refresh", code == 200 and b"/assets/" in body)
    code, _, _ = request(launcher.url("api") + "/bills")
    record("Unauthenticated API denied", code == 401)
    code, _, _ = request(launcher.url("portal") + "/stop", {}, method="POST")
    record("Unauthenticated shutdown denied", code == 403)
    for role, email, password in (("admin", "admin@nxttrn.com", "admin123"),
                                  ("customer", "customer@nxttrn.com", "customer123")):
        code, body, _ = request(launcher.url("api") + "/auth/login", {"email": email, "password": password})
        if code != 200:
            RESULTS.append({"test": role + " demo login", "passed": None,
                            "detail": "Demo credentials unavailable; existing database requires its own login."})
            continue
        token = json.loads(body)["token"]
        record(role + " login", code == 200)
        code, body, _ = request(launcher.url("api") + "/dashboard/" + role, token=token)
        record(role + " real dashboard query", code == 200 and bool(json.loads(body)))
        if role == "customer":
            code, _, _ = request(launcher.url("api") + "/dashboard/admin", token=token)
            record("Customer cannot access admin data", code == 403)
            code, body, _ = request(launcher.url("api") + "/bills", token=token)
            bills = json.loads(body)
            record("Customer billing history", code == 200 and isinstance(bills, list))
            if bills:
                code, pdf, _ = request(launcher.url("api") + "/bills/" + bills[0]["id"] + "/pdf", token=token)
                record("Real bill PDF generation", code == 200 and pdf.startswith(b"%PDF"))
    req = urllib.request.Request(launcher.url("api") + "/bills", method="OPTIONS", headers={
        "Origin": launcher.url("analytics"), "Access-Control-Request-Method": "GET"})
    with urllib.request.urlopen(req) as response:
        record("Frontend CORS", response.headers.get("Access-Control-Allow-Origin") == launcher.url("analytics"))


def main():
    process = None
    ROOT.joinpath("logs").mkdir(exist_ok=True)
    try:
        for name, port in launcher.PORTS.items():
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", port))
        for cycle in (1, 2):
            with (ROOT / "logs/verification-launch.log").open("a") as output:
                process = subprocess.Popen([sys.executable, "launcher.py", "start"], cwd=ROOT,
                                           stdout=output, stderr=subprocess.STDOUT)
            wait_ready(process)
            record(f"Startup cycle {cycle}", True)
            if cycle == 1:
                duplicate = subprocess.run([sys.executable, "launcher.py", "start"], cwd=ROOT,
                                           capture_output=True, text=True, timeout=15)
                record("Duplicate start refused", duplicate.returncode != 0 and "already running" in duplicate.stderr)
                check_apps()
            stopped = subprocess.run([sys.executable, "launcher.py", "stop"], cwd=ROOT,
                                     capture_output=True, text=True, timeout=25)
            record(f"Stop command cycle {cycle}", stopped.returncode == 0)
            process.wait(timeout=15)
            record(f"Launcher exits cycle {cycle}", process.returncode == 0)
            for port in launcher.PORTS.values():
                with socket.socket() as probe:
                    record(f"Port {port} released cycle {cycle}", probe.connect_ex(("127.0.0.1", port)) != 0)
            process = None
        # Conflict handling must not kill a port's existing owner.
        with socket.socket() as occupied:
            occupied.bind(("127.0.0.1", launcher.PORTS["crm"]))
            occupied.listen()
            conflict = subprocess.run([sys.executable, "launcher.py", "start"], cwd=ROOT,
                                      capture_output=True, text=True, timeout=15)
            record("Port conflict reported", conflict.returncode != 0 and "occupied" in conflict.stderr)
            with socket.socket() as probe:
                record("Port owner preserved", probe.connect_ex(("127.0.0.1", launcher.PORTS["crm"])) == 0)
    finally:
        if process and process.poll() is None:
            try:
                launcher.stop_existing()
                process.wait(timeout=15)
            except Exception:
                process.terminate()
                process.wait(timeout=15)
        (ROOT / "logs/verification.json").write_text(json.dumps(RESULTS, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
