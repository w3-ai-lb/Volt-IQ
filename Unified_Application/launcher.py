"""Local orchestration, isolated builds, real application servers, and shutdown."""
from __future__ import annotations

import argparse
import hashlib
import http.client
import http.server
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tarfile
import threading
import time
import tempfile
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / ".runtime"
LOGS = ROOT / "logs"
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
PORTS = CONFIG["ports"]
STATE = RUNTIME / "session.json"
STOP = threading.Event()
SERVERS = []
CHILDREN = []
TOKEN = ""
JOB = None


class WindowsJob:
    """Windows closes this job on launcher exit, including closing its console."""
    def __init__(self):
        import ctypes
        from ctypes import wintypes
        class Basic(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                        ("flags", wintypes.DWORD), ("minimum", ctypes.c_size_t),
                        ("maximum", ctypes.c_size_t), ("active", wintypes.DWORD),
                        ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                        ("scheduling", wintypes.DWORD)]
        class Counters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in
                        ("reads", "writes", "other", "read_bytes", "write_bytes", "other_bytes")]
        class Extended(ctypes.Structure):
            _fields_ = [("basic", Basic), ("io", Counters), ("process_memory", ctypes.c_size_t),
                        ("job_memory", ctypes.c_size_t), ("peak_process", ctypes.c_size_t),
                        ("peak_job", ctypes.c_size_t)]
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.api.CreateJobObjectW.restype = wintypes.HANDLE
        self.api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.api.CreateJobObjectW(None, None)
        limits = Extended()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.handle or not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise ctypes.WinError(ctypes.get_last_error())

    def add(self, process):
        if not self.api.AssignProcessToJobObject(self.handle, int(process._handle)):
            process.terminate()
            process.wait()
            raise RuntimeError("Windows could not attach the managed child to its cleanup job.")

    def close(self):
        self.api.CloseHandle(self.handle)


def spawn(*args, **kwargs):
    if os.name != "nt":
        kwargs["start_new_session"] = True
    process = subprocess.Popen(*args, **kwargs)
    if JOB:
        JOB.add(process)
    CHILDREN.append(process)
    return process


def terminate(process):
    if os.name == "nt":
        process.terminate()
    else:
        os.killpg(process.pid, signal.SIGTERM)


def url(name):
    return f"http://127.0.0.1:{PORTS[name]}"


def paths():
    analytics = (ROOT / CONFIG["analytics"]).resolve()
    crm = (ROOT / CONFIG["crm"]).resolve()
    for file in (analytics / "frontend/package.json", analytics / "backend/app/main.py", crm / "package.json"):
        if not file.is_file():
            raise RuntimeError(f"Missing project file: {file}. Update config.json with the project folder.")
    return analytics, crm


def node_binary():
    candidates = [os.environ.get("UNIFIED_NODE"), shutil.which("node"),
                  str(Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe")]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            version = subprocess.check_output([candidate, "--version"], text=True).strip()
            parts = tuple(int(part) for part in version.lstrip("v").split(".")[:2])
            if parts >= (22, 12):
                return str(Path(candidate).resolve())
    raise RuntimeError("Install Node.js 22.12+ (24 LTS recommended), or set UNIFIED_NODE to its executable.")


def run(command, cwd, log_name, env=None):
    print(f"  {log_name} ...", flush=True)
    with (LOGS / f"{log_name}.log").open("w", encoding="utf-8") as output:
        process = spawn(command, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT)
        try:
            while process.poll() is None:
                if STOP.wait(0.3):
                    terminate(process)
                    raise RuntimeError("Startup cancelled.")
            if process.returncode:
                raise RuntimeError(f"{log_name} failed. See logs/{log_name}.log.")
        finally:
            if process.poll() is not None:
                CHILDREN.remove(process)


def npm_cli(node):
    for candidate in (Path(node).parent / "node_modules/npm/bin/npm-cli.js",
                      Path(node).parent.parent / "node_modules/npm/bin/npm-cli.js",
                      ROOT / ".tools/npm/bin/npm-cli.js"):
        if candidate.is_file():
            return candidate
    # A project-local npm installation avoids global machine changes.
    destination = ROOT / ".tools/npm"
    destination.mkdir(parents=True, exist_ok=True)
    archive = ROOT / ".tools/npm.tgz"
    print("Downloading npm 11.6.2 from registry.npmjs.org ...", flush=True)
    downloader = """
const https = require('node:https');
const fs = require('node:fs');
const request = https.get(process.argv[1], {family: 4}, response => {
  if (response.statusCode !== 200) { console.error('Download HTTP ' + response.statusCode); process.exit(1); }
  const output = fs.createWriteStream(process.argv[2]);
  response.pipe(output);
  output.on('error', () => process.exit(1));
});
request.setTimeout(30000, () => request.destroy(new Error('Download timed out')));
request.on('error', error => { console.error(error.message); process.exit(1); });
"""
    curl = shutil.which("curl.exe" if os.name == "nt" else "curl")
    if curl:
        subprocess.run([curl, "-4", "-fLsS", "--retry", "2", "--connect-timeout", "15", "--max-time", "300",
                        "-C", "-", "https://registry.npmjs.org/npm/-/npm-11.6.2.tgz", "-o", str(archive)], check=True)
    else:
        subprocess.run([node, "-e", downloader, "https://registry.npmjs.org/npm/-/npm-11.6.2.tgz", str(archive)], check=True, timeout=300)
    with tarfile.open(archive) as bundle:
        for member in bundle.getmembers():
            relative = Path(*Path(member.name).parts[1:])
            target = (destination / relative).resolve()
            if not target.is_relative_to(destination.resolve()) or member.issym() or member.islnk():
                raise RuntimeError("Unsafe npm archive entry")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.extractfile(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
    archive.unlink()
    return destination / "bin/npm-cli.js"


def snapshot(source, destination):
    """Refresh code only. Runtime data and installed packages remain intact."""
    excluded = {"node_modules", "dist", ".git", "venv", ".venv", "__pycache__", "artifacts", "backups"}
    digest = hashlib.sha256()
    for folder, directories, files in os.walk(source):
        directories[:] = sorted(d for d in directories if d not in excluded)
        for name in sorted(files):
            if name.endswith((".db", ".db-wal", ".db-shm", ".pyc")):
                continue
            original = Path(folder) / name
            relative = original.relative_to(source)
            content = original.read_bytes()
            digest.update(str(relative).encode())
            digest.update(content)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists() or target.read_bytes() != content:
                target.write_bytes(content)
    return digest.hexdigest()


def prepare():
    if not (3, 11) <= sys.version_info[:2] <= (3, 12):
        raise RuntimeError("Use Python 3.11 or 3.12 for the pinned analytics requirements.")
    analytics, crm = paths()
    node = node_binary()
    npm = npm_cli(node)
    env = os.environ.copy()
    env["PATH"] = str(Path(node).parent) + os.pathsep + env.get("PATH", "")
    env["NODE_OPTIONS"] = env.get("NODE_OPTIONS", "") + " --dns-result-order=ipv4first"
    venv = ROOT / ".venv"
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.exists():
        run([sys.executable, "-m", "venv", str(venv)], ROOT, "python-environment")
    backend = RUNTIME / "backend"
    snapshot(analytics / "backend", backend)
    requirement_hash = hashlib.sha256((backend / "requirements.txt").read_bytes()).hexdigest()
    marker = RUNTIME / "requirements.sha256"
    if not marker.exists() or marker.read_text() != requirement_hash:
        run([str(python), "-m", "pip", "install", "-r", "requirements.txt"], backend, "backend-install")
        marker.write_text(requirement_hash)
    for name, source in (("analytics", analytics / "frontend"), ("crm", crm)):
        destination = RUNTIME / name
        fingerprint = snapshot(source, destination) + str(PORTS["api"])
        build_marker = RUNTIME / f"{name}.sha256"
        if build_marker.exists() and build_marker.read_text() == fingerprint and (destination / "dist/index.html").exists():
            continue
        command = "ci" if (destination / "package-lock.json").exists() else "install"
        run([node, str(npm), command, "--no-audit", "--no-fund"], destination, f"{name}-install", env)
        build_env = env.copy()
        if name == "analytics":
            build_env["VITE_API_URL"] = url("api")
        run([node, str(npm), "run", "build"], destination, f"{name}-build", build_env)
        build_marker.write_text(fingerprint)
    database = RUNTIME / "energy_analytics.db"
    # Copy the original default SQLite database safely, if delivered. Never reset it.
    original_database = analytics / "backend/energy_analytics.db"
    if not database.exists() and original_database.exists():
        with sqlite3.connect(f"file:{original_database.as_posix()}?mode=ro", uri=True) as source:
            with sqlite3.connect(database) as destination:
                source.backup(destination)
    secret_path = RUNTIME / "jwt-secret"
    if not secret_path.exists():
        secret_path.write_text(secrets.token_urlsafe(48))
    backend_env = os.environ.copy()
    backend_env.update(DATABASE_URL="sqlite:///" + database.as_posix(),
                       JWT_SECRET_KEY=secret_path.read_text(),
                       CORS_ORIGINS=",".join(url(n) for n in ("portal", "analytics", "crm")),
                       RETURN_RESET_TOKEN_IN_RESPONSE="false", PROVISION_DEMO_DATA="false")
    if not database.exists():
        print("Creating a NEW isolated demo database in .runtime (source databases are preserved).", flush=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix="seed-", suffix=".db", dir=RUNTIME)
        os.close(descriptor)
        temporary_database = Path(temporary_name)
        seed_env = backend_env.copy()
        seed_env["DATABASE_URL"] = "sqlite:///" + temporary_database.as_posix()
        try:
            run([str(python), "-m", "app.pipeline.seed"], backend, "database-initialization", seed_env)
            temporary_database.replace(database)
        finally:
            if temporary_database.exists():
                temporary_database.unlink()
    return python, backend, backend_env


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False


class StaticHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, directory, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self):
        # SPA fallback for client-side routes, including browser refresh.
        path = Path(self.translate_path(self.path.split("?", 1)[0]))
        if not path.exists() and not path.suffix:
            self.path = "/index.html"
        super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, *_):
        pass


def api_ready():
    try:
        with urllib.request.urlopen(url("api") + "/health", timeout=2) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


class PortalHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/status":
            crm_check = LOGS / "crm-connectivity.json"
            try:
                crm_results = json.loads(crm_check.read_text()) if crm_check.exists() else []
            except (ValueError, OSError):
                crm_results = []
            body = json.dumps({"system": "energy-unified", "apiReady": api_ready(),
                               "apps": {n: url(n) for n in ("analytics", "crm")},
                               "crmLastCheck": "unavailable" if crm_results and not all(r["passed"] for r in crm_results) else "not-verified" if not crm_results else "reachable",
                               "external": "CRM uses the original Supabase configuration; local readiness does not verify cloud data."}).encode()
            content_type = "application/json"
        elif self.path in ("/", "/index.html"):
            body = (ROOT / "portal/index.html").read_bytes()
            content_type = "text/html; charset=utf-8"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/stop" or self.headers.get("X-Unified-Token") != TOKEN:
            self.send_error(403)
            return
        self.send_response(202)
        self.end_headers()
        STOP.set()

    def log_message(self, *_):
        pass


def start_server(port, handler):
    server = Server(("127.0.0.1", port), handler)
    SERVERS.append(server)
    threading.Thread(target=server.serve_forever, daemon=True).start()


def stop_existing():
    if not STATE.exists():
        print("No managed session is recorded.")
        return
    state = json.loads(STATE.read_text())
    request = urllib.request.Request(state["url"] + "/stop", data=b"", method="POST",
                                     headers={"X-Unified-Token": state["token"]})
    try:
        urllib.request.urlopen(request, timeout=3).close()
    except (OSError, urllib.error.URLError) as exc:
        raise RuntimeError("Recorded session is not responding. No unrelated process was stopped.") from exc
    for _ in range(60):
        if not STATE.exists():
            print("Unified system stopped.")
            return
        time.sleep(0.25)
    raise RuntimeError("Shutdown was requested but did not finish within 15 seconds. Check the launch terminal.")


def main():
    global TOKEN, JOB
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["start", "stop", "prepare"], nargs="?", default="start")
    args = parser.parse_args()
    RUNTIME.mkdir(exist_ok=True)
    LOGS.mkdir(exist_ok=True)
    if args.action == "stop":
        stop_existing()
        return
    # Exclusive OS file lock protects startup as well as the running session.
    lock = (RUNTIME / "launcher.lock").open("a+b")
    lock.seek(0)
    lock.write(b"0")
    lock.flush()
    lock.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        raise RuntimeError(f"The unified launcher is already running or preparing. Wait for its readiness message, then open {url('portal')}.") from exc
    signal.signal(signal.SIGINT, lambda *_: STOP.set())
    signal.signal(signal.SIGTERM, lambda *_: STOP.set())
    try:
        if os.name == "nt":
            JOB = WindowsJob()
        if len(set(PORTS.values())) != len(PORTS):
            raise RuntimeError("Each service needs a different port in config.json.")
        for name, port in PORTS.items():
            with socket.socket() as probe:
                try:
                    probe.bind(("127.0.0.1", port))
                except OSError as exc:
                    raise RuntimeError(f"Port {port} ({name}) is occupied. Change config.json or close its owner. No process was stopped.") from exc
        python, backend, env = prepare()
        if args.action == "prepare":
            print("Dependencies, builds, and isolated database are prepared.")
            return
        with (LOGS / "api.log").open("a", encoding="utf-8") as output:
            process = spawn([str(python), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                                        "--port", str(PORTS["api"])], cwd=backend, env=env,
                                       stdout=output, stderr=subprocess.STDOUT)
        for _ in range(180):
            if process.poll() is not None:
                raise RuntimeError("Analytics API exited. See logs/api.log.")
            if api_ready():
                break
            if STOP.wait(0.5):
                raise RuntimeError("Startup cancelled.")
        else:
            raise RuntimeError("API did not become ready. See logs/api.log.")
        from functools import partial
        for name in ("analytics", "crm"):
            start_server(PORTS[name], partial(StaticHandler, directory=str(RUNTIME / name / "dist")))
        TOKEN = secrets.token_urlsafe(32)
        start_server(PORTS["portal"], PortalHandler)
        STATE.write_text(json.dumps({"url": url("portal"), "token": TOKEN, "pid": os.getpid()}))
        print(f"\nLOCAL SERVICES READY: {url('portal')}\nCRM cloud connectivity must be verified separately.\nStop with STOP_APP.bat or Ctrl+C.\n", flush=True)
        while not STOP.wait(1):
            if process.poll() is not None:
                raise RuntimeError("Analytics API stopped unexpectedly. See logs/api.log.")
    finally:
        for server in SERVERS:
            server.shutdown()
            server.server_close()
        for process in reversed(CHILDREN):
            if process.poll() is None:
                terminate(process)
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        if JOB:
            JOB.close()
        if TOKEN and STATE.exists():
            STATE.unlink()
        lock.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
