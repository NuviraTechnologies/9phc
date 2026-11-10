#!/usr/bin/env python3
"""9 PHC — command-line entry point.

Usage:
  python3 run_audit.py <document.md> [--title "Title"] [--files user-files.txt]
  python3 run_audit.py <document.md> --dry-run     # scripted client, zero spend

Live runs call the Meta Model API with YOUR OWN key. Put it in a file
named .env beside this script (copy .env.example) or export it:

  META_API_KEY=<your key>

The key is read from the environment only. It is never written into
the report, the findings, or the spend ledger. The report prints to
stdout and is also written next to the input as <name>.audit.md.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


def _load_dotenv() -> None:
    """Read KEY=VALUE lines from a .env beside this script into the
    environment (values already in the environment win). Stdlib only —
    the package carries no dependencies."""
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from audit import MetaModelClient, audit_document_data  # noqa: E402


class _DryRunClient:
    """Minimal scripted client for --dry-run smoke checks."""

    def fresh(self):
        return _DryRunClient()

    def complete(self, model, system, user, json_schema=None):
        if json_schema and json_schema.get("name") == "claim_extraction":
            return json.dumps({"claims": []})
        return json.dumps({"outcome": "unsettled", "note": "dry run", "door": "n/a"})


def main() -> int:
    ap = argparse.ArgumentParser(description="Run a 9-Point Hallucination Calibration (9 PHC) audit over a document.")
    ap.add_argument("document", help="Path to the document to audit (.md/.txt)")
    ap.add_argument("--title", default=None)
    ap.add_argument("--files", default=None, help="User's own files text, for check 6")
    ap.add_argument("--json", action="store_true",
                    help="Also write structured findings JSON (the agent-caller form)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--fresh", action="store_true",
                    help="Discard any checkpoint and run the audit from zero")
    args = ap.parse_args()

    _load_dotenv()
    if not args.dry_run and not os.environ.get("META_API_KEY"):
        print(
            "9 PHC needs your own Meta Model API key to run live.\n"
            "Nothing has been called and nothing has been spent.\n\n"
            "Set it one of two ways:\n"
            "  1. Copy .env.example to .env beside run_audit.py and put "
            "your key in it, or\n"
            "  2. export META_API_KEY=<your key>\n\n"
            "Get a key at dev.meta.ai. The key stays on your machine: it "
            "is read from\n"
            "the environment, sent only to api.meta.ai, and never written "
            "into any file\n"
            "this program produces.\n"
            "To watch the pipeline run with no key and no spend: --dry-run",
            file=sys.stderr)
        return 2

    doc_path = Path(args.document)
    document = doc_path.read_text()
    user_files = Path(args.files).read_text() if args.files else ""
    title = args.title or doc_path.stem

    # Restart armor: findings checkpoint to disk after every claim, so
    # a killed run resumes and pays only for what is missing; every API
    # call is written to the spend ledger at call time.
    checkpoint_path = doc_path.with_suffix(".checkpoint.json")
    if args.fresh and checkpoint_path.exists():
        checkpoint_path.unlink()
    if checkpoint_path.exists() and not args.dry_run:
        print(f"[resuming from checkpoint {checkpoint_path}]", file=sys.stderr)

    client = _DryRunClient() if args.dry_run else MetaModelClient()
    if hasattr(client, "attach_ledger"):
        client.attach_ledger(doc_path.with_suffix(".spend.jsonl"))

    def _progress(cv):
        print(f"[claim {cv.claim.id}: {cv.verdict.value}]", file=sys.stderr, flush=True)

    started = time.perf_counter()
    report, findings = audit_document_data(
        client, document, title, user_files,
        checkpoint_path=None if args.dry_run else checkpoint_path,
        on_claim_done=_progress)
    findings["summary"]["wall_clock_seconds"] = round(time.perf_counter() - started, 2)

    out_path = doc_path.with_suffix(".audit.md")
    out_path.write_text(report)
    if args.json:
        json_path = doc_path.with_suffix(".audit.json")
        json_path.write_text(json.dumps(findings, indent=2))
        print(f"[findings JSON written to {json_path}]", file=sys.stderr)
    print(report)
    print(f"\n[report written to {out_path}]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
