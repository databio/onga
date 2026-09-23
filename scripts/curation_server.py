#!/usr/bin/env python
"""Local curation daemon: lets the dashboard write the working tree.

Stdlib `http.server`, bound to a loopback address only (it refuses to start on
anything else; there is no auth and there must never be a reason for any).
The published site probes `/api/health`, fails, and renders read-only.

Endpoints
---------
  GET    /api/health              repo, branch, fingerprint, decision count, dirty flag
  GET    /api/decisions           the whole store (+ mtime_ns)
  POST   /api/decisions           create; mints DEC-NNNN              -> 201
  PUT    /api/decisions/<id>      replace a pending record
  DELETE /api/decisions/<id>      withdraw (status: withdrawn; never removed)
  GET    /api/subjects            curation/subjects.json
  GET    /api/status              curation/status.json (404 until it exists)
  PATCH  /api/proposals/<id>      set `status:` of an upstream request
  POST   /api/apply               run scripts/apply_decisions.py (503 until present)
  GET    /api/apply               the last run's log: {running, dry_run, log, exit}

Every decision write goes through scripts/workbench/store.py (`validate` is the
one gate). Errors are `{"errors": [...]}` with 400 (malformed), 404 (unknown id)
or 409 (conflict). Optimistic concurrency: a mutating request may send the
`X-Store-Mtime` header with the `mtime_ns` it last read; if the file changed
since, the daemon answers 409 with the current store.

The server sets `decided_by` (git config user.name), `decided_on`,
`schema_fingerprint`, `status: pending` and `origin: local`; the browser
cannot supply them.
"""
import argparse
import contextlib
import datetime
import ipaddress
import json
import socket
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from workbench import store, yamlio  # noqa: E402

ROOT = store.ROOT
PROPOSALS = ROOT / "proposals" / "upstream_requests.yaml"
STATUS = ROOT / "curation" / "status.json"
APPLY = ROOT / "scripts" / "apply_decisions.py"
ALLOWED_ORIGINS = {f"http://{h}:{p}" for h in ("localhost", "127.0.0.1") for p in range(4321, 4330)}
REQUEST_STATUSES = ("proposed", "filed", "accepted", "declined", "withdrawn")
# Fields only the server (or the apply engine) sets.
SERVER_FIELDS = ("id", "decided_by", "decided_on", "schema_fingerprint", "status", "applied", "origin")


def git(*args):
    out = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)
    return out.stdout.strip()


def is_loopback(host):
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    return bool(infos) and all(ipaddress.ip_address(i[4][0]).is_loopback for i in infos)


class Api(BaseHTTPRequestHandler):
    server_version = "onga-curation/1"
    decided_by = None  # set in main()
    # The last apply run, kept so a page reloaded mid-run (the dev server
    # reloads when apply rewrites site data) can pick the log back up.
    last_apply = {"running": False, "dry_run": False, "log": [], "exit": None}

    # ------------------------------------------------------------ plumbing

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[curate] {self.command} {self.path} {fmt % args}\n")

    def _cors(self):
        origin = self.headers.get("Origin")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Expose-Headers", "X-Store-Mtime")

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, indent=1).encode()
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        if store.STORE.exists():
            self.send_header("X-Store-Mtime", str(store.mtime_ns()))
        self.end_headers()
        self.wfile.write(data)

    def _error(self, code, errors, **extra):
        self._send(code, {"errors": list(errors), **extra})

    def _json_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError as e:
            raise store.StoreError(400, [f"body is not JSON: {e}"])
        if not isinstance(body, dict):
            raise store.StoreError(400, ["body must be a JSON object"])
        return body

    def _guard(self):
        """Refuse requests from foreign pages and DNS-rebound hosts."""
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
        if host not in ("localhost", "127.0.0.1", "::1"):
            self._error(403, [f"bad Host {host!r}"])
            return False
        origin = self.headers.get("Origin")
        if origin and origin not in ALLOWED_ORIGINS:
            self._error(403, [f"origin {origin} not allowed"])
            return False
        return True

    def _check_mtime(self):
        sent = self.headers.get("X-Store-Mtime")
        if sent is not None and sent != str(store.mtime_ns()):
            raise store.StoreError(409, ["decisions.yaml changed since it was read; reload"])

    def _store_json(self):
        doc = store.load()
        return {**store.to_plain(dict(doc.data)), "mtime_ns": store.mtime_ns()}

    def _dispatch(self, routes):
        if not self._guard():
            return
        path = urlparse(self.path).path.rstrip("/")
        for prefix, fn in routes:
            if path == prefix or (prefix.endswith("/") and path.startswith(prefix)):
                try:
                    # Reads skip the lock (writes are atomic renames), so health
                    # and the apply log stay reachable while an apply runs.
                    with store.LOCK if self.command != "GET" else contextlib.nullcontext():
                        return fn(path[len(prefix):] if prefix.endswith("/") else None)
                except store.StoreError as e:
                    extra = {"store": self._store_json()} if e.status == 409 else {}
                    return self._error(e.status, e.errors, **extra)
                except FileNotFoundError as e:
                    return self._error(503, [f"missing input: {e.filename}"])
        self._error(404, [f"no route {self.command} {path}"])

    # ------------------------------------------------------------ verbs

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Store-Mtime")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def do_GET(self):
        self._dispatch([
            ("/api/health", self.health),
            ("/api/decisions", lambda _: self._send(200, self._store_json())),
            ("/api/subjects", lambda _: self._file(store.SUBJECTS)),
            ("/api/status", lambda _: self._file(STATUS)),
            ("/api/apply", lambda _: self._send(200, Api.last_apply)),
        ])

    def do_POST(self):
        self._dispatch([("/api/decisions", self.create), ("/api/apply", self.apply)])

    def do_PUT(self):
        self._dispatch([("/api/decisions/", self.update)])

    def do_DELETE(self):
        self._dispatch([("/api/decisions/", self.withdraw)])

    def do_PATCH(self):
        self._dispatch([("/api/proposals/", self.patch_proposal)])

    # ------------------------------------------------------------ handlers

    def _file(self, path):
        if not path.exists():
            return self._error(404, [f"{path.relative_to(ROOT)} not generated yet"])
        self._send(200, path.read_bytes())

    def health(self, _):
        subjects = store.Subjects.load()
        self._send(200, {
            "ok": True,
            "repo_root": str(ROOT),
            "git_branch": git("rev-parse", "--abbrev-ref", "HEAD"),
            "schema_fingerprint": subjects.fingerprint,
            "decision_count": len(store.records()),
            "working_tree_dirty": bool(git("status", "--porcelain")),
            "decided_by": self.decided_by,
            "apply_available": APPLY.exists(),
        })

    def _client_record(self):
        body = self._json_body()
        body.pop("mtime_ns", None)
        for f in SERVER_FIELDS:
            body.pop(f, None)
        return body

    def create(self, _):
        self._check_mtime()
        rec = self._client_record()
        rec["decided_by"] = self.decided_by
        rec["origin"] = {"kind": "local", "ref": None}
        subjects = store.Subjects.load()
        rec["schema_fingerprint"] = subjects.fingerprint
        out = store.create(rec, subjects, store.load_verdicts())
        self._send(201, {"decision": out})

    def update(self, dec_id):
        self._check_mtime()
        _, cur = store.find(store.load(), dec_id)
        if cur["status"] != "pending":
            raise store.StoreError(400, [f"{dec_id} is {cur['status']}; only pending records can change"])
        rec = self._client_record()
        subjects = store.Subjects.load()
        rec.update(id=dec_id, decided_by=self.decided_by, status="pending",
                   decided_on=datetime.date.today().isoformat(),
                   origin=store.to_plain(cur["origin"]), schema_fingerprint=subjects.fingerprint)
        out = store.update(dec_id, rec, subjects, store.load_verdicts())
        self._send(200, {"decision": out})

    def withdraw(self, dec_id):
        self._check_mtime()
        self._send(200, {"decision": store.withdraw(dec_id)})

    def patch_proposal(self, req_id):
        body = self._json_body()
        status = body.get("status")
        if status not in REQUEST_STATUSES:
            raise store.StoreError(400, [f"status must be one of {list(REQUEST_STATUSES)}"])
        doc = yamlio.load(PROPOSALS)
        for reqs in (doc.data.get("requests") or {}).values():
            for req in reqs:
                if req.get("id") == req_id:
                    req["status"] = status
                    yamlio.dump(doc, PROPOSALS)
                    return self._send(200, {"id": req_id, "status": status})
        raise store.StoreError(404, [f"no upstream request {req_id}"])

    def apply(self, _):
        if not APPLY.exists():
            return self._error(503, ["the apply engine (scripts/apply_decisions.py) is not built yet"])
        body = self._json_body()
        cmd = [sys.executable, str(APPLY)]
        if body.get("dry_run"):
            cmd.append("--dry-run")
        if body.get("ids"):
            cmd += ["--ids", *map(str, body["ids"])]
        proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        run = Api.last_apply = {"running": True, "dry_run": bool(body.get("dry_run")), "log": [], "exit": None}
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Connection", "close")
        self.end_headers()
        client = True
        for line in proc.stdout:
            run["log"].append(line.decode(errors="replace").rstrip("\n"))
            if client:
                try:
                    self.wfile.write(line)
                    self.wfile.flush()
                except OSError:  # the page went away; keep draining the run
                    client = False
        run["exit"], run["running"] = proc.wait(), False
        if client:
            try:
                self.wfile.write(f"\nexit {run['exit']}\n".encode())
            except OSError:
                pass
        self.close_connection = True


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8781)
    args = ap.parse_args(argv)
    if not is_loopback(args.host):
        sys.exit(f"refusing to bind {args.host!r}: the curation daemon listens on loopback only")
    Api.decided_by = git("config", "user.name")
    if not Api.decided_by:
        sys.exit("git config user.name is empty; the daemon needs it for decided_by")
    family = socket.AF_INET6 if ":" in args.host else socket.AF_INET
    ThreadingHTTPServer.address_family = family
    httpd = ThreadingHTTPServer((args.host, args.port), Api)
    print(f"curation daemon on http://{args.host}:{args.port} (decided_by={Api.decided_by})", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
