#!/usr/bin/env python3
"""Correction sanity gate — offline. A model-supplied correction that
shares no significant token with its claim is stray text and is dropped;
the claim then resolves as contradicted-but-uncorrected (Held), never
as Corrected with nonsense attached. Genuine corrections pass."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from audit import _accept_correction, audit_claim  # noqa: E402
from model import CheckOutcome, CheckResult, Claim, Verdict  # noqa: E402


def _result(note=""):
    return CheckResult(check_number=1, check_name="Source existence",
                       outcome=CheckOutcome.FAIL, note=note)


def main() -> int:
    claim = Claim(id=1, text="The Hypnerotomachia Poliphili contains a dense mixture of languages.")
    gibberish = ("Only a small amount of people change their opinion and learn "
                 "their lessons after their death and are being reborn as a "
                 "better person.")
    assert _accept_correction(claim, _result(), gibberish) == "", "stray correction must be dropped"

    claim2 = Claim(id=2, text="The italic type cut for that series was designed by Aldus himself.")
    good = ("The Aldine italic was cut by punchcutter Francesco Griffo da Bologna "
            "for Aldus Manutius.")
    assert _accept_correction(claim2, _result(), good) == good, "a real correction must pass"

    # End to end: every model check FAILs with the gibberish correction.
    class GibberishClient:
        def fresh(self):
            return self

        def complete(self, model, system, user, json_schema=None):
            if json_schema and json_schema.get("name") == "claim_extraction":
                return json.dumps({"claims": []})
            return json.dumps({"outcome": "fail", "note": "contradicted",
                               "door": "", "correction": gibberish,
                               "evidence": []})

    cv = audit_claim(GibberishClient(), claim)
    assert cv.verdict is Verdict.HELD, f"gibberish-corrected claim must be Held, got {cv.verdict}"
    assert cv.correction == "", "no correction may be printed"
    print("correction gate: stray text dropped, real corrections pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
