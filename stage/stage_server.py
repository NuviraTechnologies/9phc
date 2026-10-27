#!/usr/bin/env python3
"""9 PHC — demo stage server.

A thin presentation layer over the proven audit engine. It runs the
REAL pipeline (src/audit.py) — never a playback: verdicts stream to
the page as each claim's audit lands, through the engine's own
on_claim_done path. Two modes:

- DRY: the scripted rehearsal client (demo/rehearse.py) drives the
  real pipeline at zero spend. Labelled DRY on the page, always.
- LIVE: the Meta Model API through stage/meta_api_server.py, with
  the key supplied by the service environment. Offered only when a
  key is configured. Every live run writes its spend ledger to the
  state dir and the page reports the exact figure.

One run at a time (it is a stage, not a service). Findings are kept
per run and served as JSON — the agent-caller form: any AI handed
the findings, or the command in the page's hand-off panel, can run
or consume the same audit.

Binds 127.0.0.1 only; the web server in front of it carries the TLS
and the access control, per this host's established pattern.
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "demo"))

from audit import MetaModelClient, audit_document_data  # noqa: E402
from rehearse import RehearsalClient  # noqa: E402

PORT = int(os.environ.get("PHC_STAGE_PORT", "8917"))
STATE_DIR = Path(os.environ.get("PHC_STAGE_STATE", str(HERE / "state")))
STATE_DIR.mkdir(parents=True, exist_ok=True)
VOICE_DIR = HERE / "voice"

PRICES = {"muse-spark-1.3": (1.25, 4.25), "muse-wonder-1.0": (4.0, 20.0)}

BRIEFS = {
    "1": ("demo-brief.md", "demo-brief.expectations.json",
          "The Aldine Press — a short research brief"),
    "2": ("demo2-brief.md", "demo2-brief.expectations.json",
          "Apollo / Saturn V — a short research brief"),
    "3": ("demo3-brief.md", "demo3-brief.expectations.json",
          "Semmelweis — a short research brief"),
}

_runs: dict[str, dict] = {}
_runs_lock = threading.Lock()
_active: str | None = None


class _GenericDryClient:
    """Dry mode for pasted text: the scripted clients are written for
    the demo briefs, so a custom document in dry mode gets an honest
    illustrative pass — sentence claims, every check unsettled, every
    claim Held. The page labels it as such; LIVE is the real audit."""

    def fresh(self):
        return _GenericDryClient()

    def complete(self, model, system, user, json_schema=None):
        if json_schema and json_schema.get("name") == "claim_extraction":
            sentences = [s.strip() for s in
                         re.split(r"(?<=[.!?])\s+", user.replace("\n", " "))
                         if len(s.strip()) > 24][:12]
            claims = [{"text": s, "claim_type": "factual", "citations": [],
                       "aliases": [], "numbers": [], "components": []}
                      for s in sentences]
            return json.dumps({"claims": claims})
        return json.dumps({
            "outcome": "unsettled",
            "note": "Dry mode is scripted for the demo briefs; a pasted "
                    "document needs a LIVE run for a real audit.",
            "door": "A live run of the audit",
            "correction": "", "evidence": []})


def _score(findings: dict, expectations_path: Path) -> dict | None:
    try:
        spec = json.loads(expectations_path.read_text())
        expectations = [tuple(x) for x in spec["expectations"]]
        clean_markers = spec["clean_markers"]
    except Exception:
        return None
    claims = findings["claims"]
    caught, missed, planted_idx = [], [], set()
    for marker, verdict, term, label in expectations:
        hits = [c for c in claims if marker.lower() in c["text"].lower()]
        planted_idx.update(claims.index(c) for c in hits)
        if not hits:
            missed.append(label)
            continue
        c = hits[0]
        blob = (c.get("correction", "") + " " + c.get("held_reason", "")).lower()
        ok = verdict is None or c["verdict"] == verdict \
            or c["verdict"].startswith(verdict)
        if ok and term.lower() in blob:
            caught.append(label)
        else:
            missed.append(label)
    false_corrections = []
    for marker in clean_markers:
        for i, c in enumerate(claims):
            if i in planted_idx:
                continue
            if marker in c["text"] and c["verdict"] == "Corrected":
                false_corrections.append(c["text"][:70])
    return {"caught": len(caught), "total": len(expectations),
            "missed": missed, "false_corrections": false_corrections}


def _spend(ledger_path: Path) -> float:
    total = 0.0
    try:
        for line in ledger_path.read_text().strip().split("\n"):
            if not line.strip():
                continue
            e = json.loads(line)
            pi, po = PRICES.get(e.get("model", ""), (0.0, 0.0))
            total += e.get("prompt_tokens", 0) / 1e6 * pi \
                + e.get("completion_tokens", 0) / 1e6 * po
    except Exception:
        return 0.0
    return round(total, 4)


def _run_worker(run_id: str, document: str, title: str, mode: str,
                brief_key: str | None) -> None:
    global _active
    run = _runs[run_id]

    def _emit(kind, payload):
        run["events"].append((kind, payload))

    def on_claim(cv):
        _emit("claim", {
            "id": cv.claim.id, "text": cv.claim.text,
            "verdict": cv.verdict.value,
            "correction": cv.correction, "held_reason": cv.held_reason,
            "checks": [{"number": c.check_number, "name": c.check_name,
                        "outcome": c.outcome.value} for c in cv.checks],
            "receipts": [{"source": e.source_name, "detail": e.detail}
                         for e in cv.receipts()],
        })

    try:
        if mode == "live":
            client = MetaModelClient()
            ledger = STATE_DIR / f"run-{run_id}.spend.jsonl"
            client.attach_ledger(ledger)
        elif brief_key:
            client = RehearsalClient(f"demo{brief_key}")
            ledger = None
        else:
            client = _GenericDryClient()
            ledger = None
        started = time.time()
        report, findings = audit_document_data(
            client, document, title, "",
            checkpoint_path=STATE_DIR / f"run-{run_id}.checkpoint.json",
            on_claim_done=on_claim)
        findings["summary"]["wall_clock_seconds"] = round(time.time() - started, 2)
        score = None
        if brief_key:
            score = _score(findings, REPO / "demo" / BRIEFS[brief_key][1])
        spend = _spend(ledger) if ledger else 0.0
        (STATE_DIR / f"run-{run_id}.findings.json").write_text(
            json.dumps(findings, indent=2))
        run["findings"] = findings
        run["done"] = True
        _emit("done", {
            "claims": findings["summary"]["claims"],
            "confidence_percent": findings["summary"].get("confidence_percent"),
            "spend": spend, "mode": mode, "score": score,
            "manifest": findings.get("manifest", {}),
            "wall_clock_seconds": findings["summary"]["wall_clock_seconds"],
        })
    except Exception as exc:  # the stage reports failure, never hangs
        run["failed"] = True
        _emit("error", {"message": f"{type(exc).__name__}: {exc}"})
    finally:
        with _runs_lock:
            if _active == run_id:
                _active = None


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # quiet
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            self._send(200, (HERE / "stage.html").read_text(),
                       "text/html; charset=utf-8")
            return
        if path.startswith("/voice/"):
            name = Path(path).name
            f = VOICE_DIR / name
            if f.exists() and f.suffix == ".mp3":
                self._send(200, f.read_bytes(), "audio/mpeg")
            else:
                self._send(404, "{}")
            return
        if path == "/api/status":
            self._send(200, json.dumps({
                "live_ready": bool(os.environ.get("META_API_KEY")),
                "briefs": [{"id": k, "title": v[2]} for k, v in BRIEFS.items()],
                "running": _active is not None,
            }))
            return
        if path == "/api/findings":
            run_id = parse_qs(parsed.query).get("id", [""])[0]
            f = STATE_DIR / f"run-{run_id}.findings.json"
            if f.exists():
                self._send(200, f.read_text())
            else:
                self._send(404, "{}")
            return
        if path == "/api/stream":
            run_id = parse_qs(parsed.query).get("id", [""])[0]
            run = _runs.get(run_id)
            if run is None:
                self._send(404, "{}")
                return
            self.close_connection = True
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            # Replay anything already landed, then follow live.
            sent = 0
            idle = 0.0
            try:
                while True:
                    if sent < len(run["events"]):
                        kind, payload = run["events"][sent]
                        sent += 1
                        idle = 0.0
                        self.wfile.write(
                            f"event: {kind}\ndata: {json.dumps(payload)}\n\n"
                            .encode())
                        self.wfile.flush()
                        if kind in ("done", "error"):
                            break
                    elif run.get("done") or run.get("failed"):
                        break
                    else:
                        time.sleep(0.4)
                        idle += 0.4
                        if idle >= 12:
                            idle = 0.0
                            self.wfile.write(b": heartbeat\n\n")
                            self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        self._send(404, "{}")

    def do_POST(self):
        global _active
        parsed = urlparse(self.path)
        if parsed.path != "/api/run":
            self._send(404, "{}")
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            req = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            self._send(400, json.dumps({"error": "bad request body"}))
            return
        mode = req.get("mode", "dry")
        if mode == "live" and not os.environ.get("META_API_KEY"):
            self._send(400, json.dumps(
                {"error": "LIVE mode is not configured on this stage"}))
            return
        brief_key = req.get("brief")
        if brief_key in BRIEFS:
            document = (REPO / "demo" / BRIEFS[brief_key][0]).read_text()
            title = BRIEFS[brief_key][2]
        else:
            document = (req.get("text") or "").strip()
            title = "Pasted document"
            brief_key = None
            if len(document) < 40:
                self._send(400, json.dumps(
                    {"error": "paste a document of at least a few sentences"}))
                return
        with _runs_lock:
            if _active is not None:
                self._send(409, json.dumps(
                    {"error": "an audit is already running on this stage"}))
                return
            run_id = uuid.uuid4().hex[:12]
            _runs[run_id] = {"events": [], "done": False,
                             "failed": False, "findings": None}
            _active = run_id
        threading.Thread(target=_run_worker,
                         args=(run_id, document, title, mode, brief_key),
                         daemon=True).start()
        self._send(200, json.dumps({"run_id": run_id}))


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"9 PHC stage on 127.0.0.1:{PORT} "
          f"(live_ready={bool(os.environ.get('META_API_KEY'))})", flush=True)
    server.serve_forever()
