#!/usr/bin/env python3
"""9 PHC demo launcher — the filmable front door.

One command. Pick a brief; the audit runs and every claim's verdict
prints on screen AS IT LANDS (claims audit in parallel, so they arrive
in completion order — that is the product working, not a glitch).
When the run completes: the document confidence, the score against the
brief's planted defects, and the exact spend.

  python3 demo/launch.py          # asks which brief, runs it LIVE
  python3 demo/launch.py 1        # brief 1, live
  python3 demo/launch.py 1 --dry  # rehearsal client, $0, labelled DRY

Live runs write the same artifacts as run_audit.py (report, findings,
spend ledger, checkpoint armor). A filmed run is a real run: if it is
interrupted, re-running resumes from the checkpoint instead of paying
twice — drop --fresh behaviour by answering the resume prompt with y.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "demo"))

BRIEFS = {
    1: ("demo-brief.md", "demo-brief.expectations.json", "demo1"),
    2: ("demo2-brief.md", "demo2-brief.expectations.json", "demo2"),
    3: ("demo3-brief.md", "demo3-brief.expectations.json", "demo3"),
}
PRICES = {"muse-spark-1.3": (1.25, 4.25), "muse-wonder-1.0": (4.0, 20.0)}


def _show(cv) -> None:
    verdict = cv.verdict.value
    line = f"  Claim {cv.claim.id} — {verdict}"
    print(line, flush=True)
    if verdict == "Corrected" and cv.correction:
        print(f"      → {cv.correction[:150]}", flush=True)
    elif verdict.startswith("Held") and cv.held_reason:
        print(f"      → {cv.held_reason[:150]}", flush=True)


def _ledger_lines(path: Path) -> int:
    return len(path.read_text().strip().split("\n")) if path.exists() else 0


def _spend(path: Path, before: int) -> str:
    if not path.exists():
        return "$0.0000"
    total = 0.0
    for line in path.read_text().strip().split("\n")[before:]:
        if not line.strip():
            continue
        e = json.loads(line)
        pin, pout = PRICES.get(e.get("model", ""), (0.0, 0.0))
        total += (e.get("prompt_tokens", 0) / 1e6 * pin
                  + e.get("completion_tokens", 0) / 1e6 * pout)
    return f"${total:.4f}"


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--dry"]
    dry = "--dry" in sys.argv[1:]
    if args:
        pick = int(args[0])
    else:
        print("Which brief?  1 = Aldine press · 2 = Apollo/Saturn V · "
              "3 = Semmelweis")
        pick = int(input("Brief number: ").strip())
    brief_name, exp_name, script = BRIEFS[pick]
    brief = ROOT / "demo" / brief_name
    document = brief.read_text()
    ledger = brief.with_suffix(".spend.jsonl")
    before = _ledger_lines(ledger)

    print()
    print("9-Point Hallucination Calibration (9 PHC)")
    print(f"Auditing: {brief_name} · mode: {'DRY rehearsal ($0)' if dry else 'LIVE'}")
    print("Verdicts print as each claim's audit lands.")
    print()

    from audit import MetaModelClient, audit_document_data
    if dry:
        from rehearse import RehearsalClient
        client = RehearsalClient(script)
        checkpoint = None
    else:
        client = MetaModelClient()
        client.attach_ledger(ledger)
        checkpoint = brief.with_suffix(".checkpoint.json")
        if checkpoint.exists():
            ans = input("A checkpoint from an earlier run exists. "
                        "Resume it [y] or start fresh [n]? ").strip().lower()
            if ans != "y":
                checkpoint.unlink()

    report, findings = audit_document_data(
        client, document, f"Demo brief {pick}",
        checkpoint_path=checkpoint, on_claim_done=_show)

    out_json = brief.with_suffix(".rehearsal.audit.json" if dry
                                 else ".audit.json")
    out_md = brief.with_suffix(".rehearsal.audit.md" if dry else ".audit.md")
    out_json.write_text(json.dumps(findings, indent=1))
    out_md.write_text(report)

    summary = findings["summary"]
    print()
    print(f"Done — {summary['claims']} claims · confidence "
          f"{summary.get('confidence_percent')}% · spend "
          f"{'$0 (dry)' if dry else _spend(ledger, before)}")
    scored = subprocess.run(
        [sys.executable, str(ROOT / "demo" / "score_run.py"),
         str(out_json), str(ROOT / "demo" / exp_name)],
        capture_output=True, text=True)
    for line in scored.stdout.splitlines():
        if line.startswith(("Planted", "  CAUGHT", "  MISSED", "  FALSE")):
            print(line)
    print(f"Full report: {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
