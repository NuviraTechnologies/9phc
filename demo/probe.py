#!/usr/bin/env python3
"""9 PHC single-check probe — test ONE check against ONE hand-fed claim
on the live models, for cents, instead of a full $4 audit run.

The claim is built by hand (no extraction call), the dossier is gathered
by the same retrieval pre-pass the audit uses (free registries), and
exactly one model check runs. Spend lands in demo/probe.spend.jsonl,
one line per call, priced with the verified rate card.

Usage:
  python3 demo/probe.py --check 2 --text "The italic type cut for that
      series was designed by Aldus himself." --title "Virgil" \
      --aliases "Aldine italic"
  python3 demo/probe.py --check 2 --text "..." --dry   # wiring only, $0

Checks 7 and 8 are deterministic code — a probe cannot test them; run
the battery instead."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from audit import MetaModelClient, _gather, run_adversarial, run_model_check  # noqa: E402
from model import Citation, Claim  # noqa: E402

PRICES = {"muse-spark-1.3": (1.25, 4.25), "muse-wonder-1.0": (4.0, 20.0)}
LEDGER = ROOT / "demo" / "probe.spend.jsonl"


class _DryClient:
    def fresh(self):
        return _DryClient()

    def complete(self, model, system, user, json_schema=None):
        return json.dumps({
            "outcome": "pass",
            "note": 'Dry probe: "the record states the claim as written."',
            "door": "", "correction": "",
            "evidence": [{"source_name": "dry", "source_class":
                          "primary_record", "detail": "dry",
                          "reference": ""}]})


def _spend_since(lines_before: int) -> str:
    if not LEDGER.exists():
        return "$0.0000 (no ledger)"
    lines = LEDGER.read_text().strip().split("\n")[lines_before:]
    total, calls = 0.0, 0
    for line in lines:
        if not line.strip():
            continue
        e = json.loads(line)
        pin, pout = PRICES.get(e.get("model", ""), (0.0, 0.0))
        total += (e.get("prompt_tokens", 0) / 1e6 * pin
                  + e.get("completion_tokens", 0) / 1e6 * pout)
        calls += 1
    return f"${total:.4f} across {calls} call(s)"


def main() -> int:
    ap = argparse.ArgumentParser(description="Single-check live probe")
    ap.add_argument("--check", type=int, required=True, choices=[1, 2, 3, 4, 5, 6, 9])
    ap.add_argument("--text", required=True)
    ap.add_argument("--title", default="", help="cited source title")
    ap.add_argument("--identifier", default="", help="cited DOI/identifier")
    ap.add_argument("--aliases", default="", help="comma-separated aliases")
    ap.add_argument("--dry", action="store_true", help="wiring only, $0")
    args = ap.parse_args()

    claim = Claim(
        id=1, text=args.text, claim_type="factual",
        citations=[Citation(raw=args.title or args.identifier,
                            source_title=args.title,
                            identifier=args.identifier, locator="")]
        if (args.title or args.identifier) else [],
        aliases=[a.strip() for a in args.aliases.split(",") if a.strip()])
    records, dossier = _gather(claim)
    print(f"dossier: {len(records)} record(s), {len(dossier)} chars")

    before = len(LEDGER.read_text().strip().split("\n")) if LEDGER.exists() else 0
    if args.dry:
        client = _DryClient()
    else:
        client = MetaModelClient()
        client.attach_ledger(LEDGER)

    if args.check == 9:
        result, correction = run_adversarial(client, claim, dossier)
    else:
        result, correction = run_model_check(client, args.check, claim,
                                             "", dossier)
    print(f"check {result.check_number} ({result.check_name}): "
          f"{result.outcome.value}")
    print(f"note: {result.note}")
    if result.door:
        print(f"door: {result.door}")
    if correction:
        print(f"correction: {correction}")
    for e in result.evidence:
        print(f"evidence: [{e.source_class.value}] {e.source_name} — {e.detail}")
    print(f"spend: {_spend_since(before)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
