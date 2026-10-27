"""Round-7 pin: the fidelity quote-demanded retry.

A fidelity verdict without a quoted line is void under
quote-or-abstain. The hardening probe (2026-10-27, live) showed a
single retry — with the void explained and the quote demanded —
engaging exactly where the first attempt summarized instead of
quoting, and still abstaining where the record is silent. These
pins hold the mechanism to that shape:

1. First fidelity answer PASSes without a quote; the retry (system
   carries the retry instruction) PASSes WITH a quoted line → the
   claim's check 2 stands as that PASS, not the void.
2. Retry also answers without a quote → the void stands (check 2
   recorded UNSETTLED with the quote-or-abstain note). The rule
   does not move for having asked twice.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import audit  # noqa: E402
from model import Claim  # noqa: E402

PASS_QUOTED = json.dumps({
    "outcome": "pass",
    "note": "The record states \"the work was printed in 1499\" — the "
            "claim matches the record line for line.",
    "door": "", "correction": "",
    "evidence": [{"source_name": "Registry record", "source_class": "primary_record",
                  "detail": "The record gives the 1499 printing.",
                  "reference": "10.0000/probe"}]})
PASS_BARE = json.dumps({
    "outcome": "pass",
    "note": "The record supports the claim as written.",
    "door": "", "correction": "",
    "evidence": [{"source_name": "Registry record", "source_class": "primary_record",
                  "detail": "The record gives the 1499 printing.",
                  "reference": "10.0000/probe"}]})
UNSETTLED = json.dumps({
    "outcome": "unsettled", "note": "The record in hand is silent.",
    "door": "The deciding record", "correction": "", "evidence": []})


class RetryClient:
    """Fidelity: bare PASS first, quoted PASS when the retry
    instruction is in the system prompt (or bare again, in mode 2).
    Every other model check: quoted PASS. Adversarial: unsettled."""

    def __init__(self, retry_engages=True):
        self.retry_engages = retry_engages
        self.fidelity_calls = 0

    def fresh(self):
        return RetryClient(self.retry_engages)

    def complete(self, model, system, user, json_schema=None):
        if "RETRY — READ CAREFULLY" in system:
            self.fidelity_calls += 1
            return PASS_QUOTED if self.retry_engages else PASS_BARE
        if model == "muse-wonder-1.0" and system.startswith("Does the cited source say"):
            self.fidelity_calls += 1
            return PASS_BARE
        if model == "muse-wonder-1.0":
            return UNSETTLED          # adversarial pass
        return PASS_QUOTED            # spark checks quote their lines


audit._gather = lambda claim: ([], "")  # hermetic: no retrieval in pins

claim = Claim(id=1, text="The work was printed in 1499.", claim_type="factual")

cv = audit.audit_claim(RetryClient(retry_engages=True), claim)
r2 = [c for c in cv.checks if c.check_number == 2][0]
assert r2.outcome.value == "pass", \
    f"an engaging retry must stand as the fidelity verdict, got {r2.outcome.value}"
assert "printed in 1499" in r2.note, r2.note

cv2 = audit.audit_claim(RetryClient(retry_engages=False), claim)
r2b = [c for c in cv2.checks if c.check_number == 2][0]
assert r2b.outcome.value == "unsettled", \
    f"a retry that still does not quote must stay void, got {r2b.outcome.value}"
assert "quote-or-abstain" in r2b.note, r2b.note

print("round-7 fidelity retry pins passed")
