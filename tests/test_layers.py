"""Layer tests — the audit audits itself:
(1) a correction prints only when a peer-reviewed / primary receipt
    backs it (corrections are claims too);
(2) Held claims leave as a structured work queue with doors;
(3) every run carries a provenance manifest whose hash names the
    exact audited document.
Run: python3 tests/test_layers.py"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from engine import render_report, resolve_verdict, verdicts_to_dict
from model import (CheckOutcome, CheckResult, Claim, Evidence, SourceClass,
                   Verdict)

CLAIM = Claim(id=1, text="The total was fifty.")

def _check(number, outcome, evidence=None, door=""):
    return CheckResult(check_number=number, check_name=f"check {number}",
                       outcome=outcome, note="n", door=door,
                       evidence=evidence or [])

STRONG = [Evidence("A record", SourceClass.PRIMARY_RECORD, "says otherwise", "10.0/x")]
WEAK = [Evidence("A wiki page", SourceClass.TERTIARY, "says otherwise", "")]

# 1a. FAIL + correction + strong receipt on the failing check -> Corrected
v = resolve_verdict(CLAIM, [_check(2, CheckOutcome.FAIL, STRONG)], {2: "It was 47."})
assert v.verdict is Verdict.CORRECTED and v.correction == "It was 47.", v

# 1b. FAIL + correction, receipt only tertiary -> Held, gap named
v = resolve_verdict(CLAIM, [_check(2, CheckOutcome.FAIL, WEAK)], {2: "It was 47."})
assert v.verdict is Verdict.HELD, v
assert "no peer-reviewed or primary receipt backs that correction" in v.held_reason, v.held_reason

# 1c. FAIL + correction, no evidence at all -> Held
v = resolve_verdict(CLAIM, [_check(2, CheckOutcome.FAIL)], {2: "It was 47."})
assert v.verdict is Verdict.HELD, v

# 1d. The receipt must sit on a check that SUPPLIED the correction:
# a backed pass elsewhere does not rescue an unbacked correction.
v = resolve_verdict(CLAIM, [_check(1, CheckOutcome.PASS, STRONG),
                            _check(2, CheckOutcome.FAIL)], {2: "It was 47."})
assert v.verdict is Verdict.HELD, v

# 2. Held queue: structured in the findings, doors named, and the
# report renders the queue section.
held_claim = Claim(id=2, text="A print-only catalogue settles this.")
v2 = resolve_verdict(held_claim, [_check(1, CheckOutcome.UNSETTLED,
                                         door="Maggs Bros catalogue No. 562 (1932)")])
assert v2.verdict is Verdict.HELD
findings = verdicts_to_dict([v2], "Doc")
assert findings["held_queue"] == [{
    "claim_id": 2, "text": held_claim.text,
    "doors": ["Maggs Bros catalogue No. 562 (1932)"],
    "reason": v2.held_reason}], findings["held_queue"]
report = render_report([v2], "Doc")
assert "## Held — the work queue" in report, report
assert "Maggs Bros catalogue No. 562 (1932)" in report, report

# 3. Manifest: audit_document_data stamps the document's real hash.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_orchestration import ScriptedClient  # noqa: E402  (runs its own asserts on import)

from audit import audit_document_data  # noqa: E402

doc = "Aldus issued his octavo Virgil in 1501."
_, f3 = audit_document_data(ScriptedClient(), doc, "Manifest probe")
m = f3["manifest"]
assert m["document_sha256"] == hashlib.sha256(doc.encode("utf-8")).hexdigest(), m
assert m["models"]["adversarial"] == "muse-wonder-1.0", m
assert m["claims_audited"] == f3["summary"]["claims"], m

print("layers: corrections carry receipts, Held leaves a work queue, runs carry provenance")
