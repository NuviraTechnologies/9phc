"""Round-2 guards, pinned (built after confirming live run 1):
- correction gate v2: boilerplate screen + claim-text-only token pool
- fidelity quote-or-abstain, enforced structurally in audit_claim
- check 9 receipt-bound FAILs (no evidence -> UNSETTLED, never a kill)
- engine: computed corrections (checks 7/8) take precedence and print alone
Run: python3 tests/test_round2_guards.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from audit import _accept_correction, audit_claim
from engine import resolve_verdict
from model import (CheckOutcome, CheckResult, Claim, Evidence, SourceClass,
                   Verdict)

PEER = {"source_name": "Registry record", "source_class": "peer_reviewed",
        "detail": "Settles the point.", "reference": "probe"}


def _res(outcome, note="", door="", correction="", evidence=None):
    return json.dumps({"outcome": outcome, "note": note, "door": door,
                       "correction": correction,
                       "evidence": [PEER] if evidence is None else evidence})


GENERIC_PASS = _res("pass", "Settled against the record.")


class StubClient:
    """Routes by mandate needle, like the rehearsal client. Fidelity and
    adversarial responses are configurable per test."""
    fidelity = _res("pass", 'The record line "the source states the claim '
                            'as written" matches the claim.')
    adversarial = _res("pass", "The claim survives the attack.")

    def fresh(self):
        return StubClient()

    def complete(self, model, system, user, json_schema=None):
        if "KILL the claim" in system:
            return StubClient.adversarial
        if "say what the claim says it says" in system:
            return StubClient.fidelity
        return GENERIC_PASS


def _check(verdict, number):
    return next(c for c in verdict.checks if c.check_number == number)


# --- gate v2: boilerplate is dropped even with claim-token overlap --------
claim = Claim(1, "The Coming of the Book still frames the economics of "
                 "the early press.")
dummy = CheckResult(9, "Adversarial pass", CheckOutcome.FAIL, note="x")
boiler = ("The economics of the early press involved wrongdoing and "
          "illegal activity and can cause serious harm.")
assert _accept_correction(claim, dummy, boiler) == "", \
    "boilerplate correction must be dropped despite token overlap"

# --- gate v2: tokens shared with the NOTE only no longer rescue -----------
claim2 = Claim(2, "The treatise circulated widely in manuscript.")
note_only = CheckResult(2, "Source fidelity", CheckOutcome.FAIL,
                        note="The record names chlorinated lime solution.")
corr = "Chlorinated lime solution was the agent of disinfection."
assert _accept_correction(claim2, note_only, corr) == "", \
    "note-only token overlap must not pass gate v2"
# ...while a correction grounded in the claim text still passes
claim3 = Claim(3, "The italic type was designed by Aldus himself.")
good = CheckResult(2, "Source fidelity", CheckOutcome.FAIL, note="x")
assert _accept_correction(claim3, good,
                          "The italic type was cut by Francesco Griffo; "
                          "Aldus commissioned it.") != ""

# --- fidelity quote guard: quoteless verdict is void ----------------------
StubClient.fidelity = _res("pass", "Settled against the record.")
StubClient.adversarial = _res("pass", "Survives.")
v = audit_claim(StubClient(), Claim(4, "Aldus issued his Virgil in 1501."))
assert _check(v, 2).outcome is CheckOutcome.UNSETTLED, \
    "quoteless fidelity PASS must be recorded UNSETTLED"
assert v.verdict is not Verdict.VERIFIED

StubClient.fidelity = _res("pass", 'The record line "issued at Venice in '
                                   '1501" matches the claim.')
v = audit_claim(StubClient(), Claim(5, "Aldus issued his Virgil in 1501."))
assert _check(v, 2).outcome is CheckOutcome.PASS
assert v.verdict is Verdict.VERIFIED, v.held_reason

# --- check 9: a FAIL naming no settling source does not land --------------
StubClient.adversarial = _res("fail", "The attack asserts a contradiction.",
                              correction="The Virgil claim is wrong about "
                                         "the publisher.",
                              evidence=[])
v = audit_claim(StubClient(), Claim(6, "Aldus issued his Virgil in 1501."))
assert _check(v, 9).outcome is CheckOutcome.UNSETTLED, \
    "evidence-free adversarial FAIL must degrade to UNSETTLED"
assert v.verdict is not Verdict.CORRECTED

StubClient.adversarial = _res("fail", "The record contradicts the claim.",
                              correction="The Virgil was issued in 1501 "
                                         "at Venice, not at Rome.")
v = audit_claim(StubClient(), Claim(7, "Aldus issued his Virgil at Rome."))
assert _check(v, 9).outcome is CheckOutcome.FAIL
assert v.verdict is Verdict.CORRECTED, v.held_reason

# --- engine: computed corrections print alone ------------------------------
def cr(n, outcome, note=""):
    r = CheckResult(check_number=n, check_name=f"check {n}",
                    outcome=outcome, note=note)
    r.evidence.append(Evidence("A record", SourceClass.PRIMARY_RECORD,
                               "Settles it."))
    return r

claim8 = Claim(8, "Fifty editions in all, and the italic designed by Aldus.")
checks = [cr(7, CheckOutcome.FAIL), cr(2, CheckOutcome.FAIL)]
v = resolve_verdict(claim8, checks, {7: "The items rebuild to 47.",
                                     2: "The italic was cut by Griffo."})
assert v.verdict is Verdict.CORRECTED
assert v.correction == "The items rebuild to 47.", v.correction

checks = [cr(2, CheckOutcome.FAIL)]
v = resolve_verdict(claim8, checks, {2: "The italic was cut by Griffo."})
assert v.correction == "The italic was cut by Griffo."

print("round-2 guards: gate v2, quote-or-abstain, receipt-bound kills, "
      "computed precedence — all pinned")
