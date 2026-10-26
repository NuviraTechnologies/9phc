#!/usr/bin/env python3
"""9 PHC — command-line entry point.

Usage:
  python3 run_audit.py <document.md> [--title "Title"] [--files user-files.txt]
  python3 run_audit.py <document.md> --dry-run     # scripted client, zero spend

Live runs go through the connected Meta Model API connector
(custom.meta-model-api); the key stays in the Secure Vault and this
program never handles it. The report prints to stdout and is also
written next to the input as <name>.audit.md.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

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
