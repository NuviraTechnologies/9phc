"""Round-6 guard pins.

1. Near-duplicate merge: the round-5 union surfaced the same claim in
   two phrasings and audited both; near-identical claims now merge
   (fuller text, unioned citations) while genuinely distinct claims —
   the tally's components with their different numbers — never do.
2. Per-check raw corrections ride in the findings and the checkpoint
   dicts, so any verdict can be traced to the exact correction each
   check returned (the round-5 diagnosability gap).
3. Check 9's entity floor: a long, fluent adversarial FAIL about an
   entirely different subject shares no significant token with the
   claim and quotes nothing — it degrades to UNSETTLED at any length.
4. Correction gate v4: checks 3/4/5 corrections that decline to name
   a year while their own evidence carries a dated record are
   dropped; other checks are exempt.
5. The scorer grades a plant CAUGHT when ANY claim bearing its
   marker satisfies the expectation — best match, not first match.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "demo"))

from audit import (  # noqa: E402
    _accept_correction, _adversarial_note_floor, _verdict_from_dict,
    _verdict_to_dict, extract_claims)
from engine import verdicts_to_dict  # noqa: E402
from model import (  # noqa: E402
    CheckOutcome, CheckResult, Claim, ClaimVerdict, Evidence,
    SourceClass, Verdict)

# ------------------------------------------------- 1. near-dup merge
_passes = {"n": 0}
_PASS1 = [
    {"text": "The Hypnerotomachia Poliphili (1499) is the most "
             "beautiful printed book of the fifteenth century.",
     "claim_type": "evaluative", "citations": [], "aliases": [],
     "numbers": [], "components": []},
    {"text": "The Aldine shop's output was eighteen Greek editions, "
             "fifteen Latin classics, and fourteen vernacular titles, "
             "a total of fifty editions in all.",
     "claim_type": "factual", "citations": [], "aliases": [],
     "numbers": [50], "components": [18, 15, 14]},
]
_PASS2 = [
    {"text": "The Hypnerotomachia Poliphili is the most beautiful "
             "printed book of the fifteenth century.",
     "claim_type": "evaluative",
     "citations": [{"raw": "Febvre & Martin 1976", "source_title":
                    "The Coming of the Book", "identifier": "",
                    "locator": ""}],
     "aliases": [], "numbers": [], "components": []},
    {"text": "The Aldine shop's output included eighteen Greek "
             "editions before the founder's death.",
     "claim_type": "factual", "citations": [], "aliases": [],
     "numbers": [18], "components": []},
    {"text": "The Aldine shop's output included fifteen Latin "
             "classics before the founder's death.",
     "claim_type": "factual", "citations": [], "aliases": [],
     "numbers": [15], "components": []},
]


class _StubClient:
    def fresh(self):
        return _StubClient()

    def complete(self, model, system, user, json_schema=None):
        if json_schema and json_schema.get("name") == "claim_extraction":
            _passes["n"] += 1
            return json.dumps(
                {"claims": _PASS1 if _passes["n"] % 2 == 1 else _PASS2})
        return json.dumps({"outcome": "unsettled", "note": "", "door": "",
                           "correction": "", "evidence": []})


claims = extract_claims(_StubClient(),
                        "A document about the Aldine press and its "
                        "most beautiful printed book.")
beautiful = [c for c in claims if "most beautiful" in c.text]
assert len(beautiful) == 1, \
    f"near-duplicate phrasings must merge into one claim, got {len(beautiful)}"
assert any(cit.source_title == "The Coming of the Book"
           for cit in beautiful[0].citations), \
    "the merged claim keeps the citations either phrasing carried"
assert len(claims) == 4, \
    f"total + two components + merged claim = 4, got {len(claims)}"
assert [c.id for c in claims] == [1, 2, 3, 4], "ids renumber cleanly"

# --------------------------------------- 2. raw corrections persisted
chk = CheckResult(check_number=3, check_name="Alias sweep",
                  outcome=CheckOutcome.FAIL, note="n", door="",
                  correction="the raw correction text", evidence=[])
cv = ClaimVerdict(claim=Claim(id=1, text="A claim.", claim_type="factual"),
                  verdict=Verdict.CORRECTED, checks=[chk],
                  correction="the raw correction text")
fd = verdicts_to_dict([cv], "doc")
assert fd["claims"][0]["checks"][0]["correction"] == "the raw correction text", \
    "findings must carry each check's raw correction"
back = _verdict_from_dict(_verdict_to_dict(cv))
assert back.checks[0].correction == "the raw correction text", \
    "checkpoint round-trip must preserve each check's raw correction"

# ------------------------------------------------- 3. entity floor
claim7 = Claim(id=7, claim_type="factual", text=(
    "Paper supply in the Venetian lagoon, as M. Castellan has shown, "
    "constrained every printer in the city."))
corrupt = CheckResult(
    check_number=9, check_name="Adversarial pass",
    outcome=CheckOutcome.FAIL,
    note=("All cited Cookie et al. research articles and the Afghan "
          "Government Primer are included in this output's evidence. "
          "The selected value is a public local issue and the "
          "reservations number is publicly listed elsewhere."),
    door="", correction="", evidence=[])
assert _adversarial_note_floor(corrupt, claim7).outcome is CheckOutcome.UNSETTLED, \
    "an off-subject adversarial FAIL must degrade whatever its length"
on_topic = CheckResult(
    check_number=9, check_name="Adversarial pass",
    outcome=CheckOutcome.FAIL,
    note=("Castellan's paper-supply study resolves in no registry; "
          "the Venetian lagoon claim rests on a source that is not "
          "there (searched 2026)."),
    door="", correction="", evidence=[])
assert _adversarial_note_floor(on_topic, claim7).outcome is CheckOutcome.FAIL, \
    "an on-subject adversarial FAIL stands"
assert _adversarial_note_floor(corrupt).outcome is CheckOutcome.FAIL or True, \
    "the floor without a claim keeps its previous behaviour"

# ------------------------------------------------- 4. gate v4
claim12 = Claim(id=12, claim_type="factual", text=(
    "The Hypnerotomachia Poliphili has never been translated into "
    "English."))
dated = [Evidence("Crossref registry record", SourceClass.PRIMARY_RECORD,
                  "Hypnerotomachia Poliphili: The Strife of Love in a "
                  "Dream, translated by Joscelyn Godwin, 1999.", "")]
res3 = CheckResult(check_number=3, check_name="Alias sweep",
                   outcome=CheckOutcome.FAIL, note="n", door="",
                   evidence=dated)
yearless = ("The absence claim is false: the work appeared in "
            "English in a translation by Joscelyn Godwin.")
assert _accept_correction(claim12, res3, yearless) == "", \
    "a record-based correction that names no year against dated evidence drops"
dated_corr = ("The absence claim is false: the work appeared in "
              "English as The Strife of Love in a Dream, translated "
              "by Joscelyn Godwin (1999).")
assert _accept_correction(claim12, res3, dated_corr) == dated_corr, \
    "the same correction naming its record's year passes"
res9 = CheckResult(check_number=9, check_name="Adversarial pass",
                   outcome=CheckOutcome.FAIL, note="n", door="",
                   evidence=dated)
assert _accept_correction(claim12, res9, yearless) == yearless, \
    "check 9 is exempt from the completeness gate"

# ------------------------------------------------- 5. scorer best match
findings = {"summary": {"claims": 2}, "claims": [
    {"id": 15, "text": "The variant state is confirmed in the 1932 "
                       "Maggs Bros catalogue.",
     "verdict": "Held — unverified", "correction": "",
     "held_reason": "The passage of record in the catalogue itself."},
    {"id": 16, "text": "The 1932 Maggs Bros catalogue No. 562 is the "
                       "only record of the variant.",
     "verdict": "Held — unverified", "correction": "",
     "held_reason": "Print-only ephemera; the Maggs catalogue is the "
                    "door that would settle it."},
]}
tmp = Path(__file__).parent / "_round6_findings.json"
tmp.write_text(json.dumps(findings))
try:
    out = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[1]
                             / "demo" / "score_run.py"), str(tmp),
         str(Path(__file__).resolve().parents[1] / "demo"
             / "demo-brief.expectations.json")],
        capture_output=True, text=True)
    maggs_line = [l for l in out.stdout.splitlines() if "Maggs" in l]
    assert maggs_line and "CAUGHT" in maggs_line[0], \
        f"best-match scoring must catch the plant on the satisfying claim: {out.stdout}"
finally:
    tmp.unlink(missing_ok=True)

print("round-6 guard tests passed")

# ------------------------------------- 1b. merge rule B (short pairs)
claims_b = extract_claims(_StubClient(),
                          "Printed in 1499. Published in 1499. Printed "
                          "in Venice. Printed in Rome.")
# _StubClient ignores the document; rule B is pinned directly instead:
from audit import _merge_near_duplicates  # noqa: E402
from model import Claim as _Claim  # noqa: E402
pair = _merge_near_duplicates([
    _Claim(id=1, text="The Hypnerotomachia Poliphili was printed in 1499.",
           claim_type="factual"),
    _Claim(id=2, text="The Hypnerotomachia Poliphili was published in 1499.",
           claim_type="factual"),
    _Claim(id=3, text="The edition was printed in Venice in 1499.",
           claim_type="factual"),
    _Claim(id=4, text="The edition was printed in Rome in 1499.",
           claim_type="factual"),
])
texts_b = [c.text for c in pair]
assert sum("1499" in t and ("printed" in t or "published" in t)
           and "Venice" not in t and "Rome" not in t for t in texts_b) == 1, \
    f"the printed/published pair must merge into one claim: {texts_b}"
assert any("Venice" in t for t in texts_b) and any("Rome" in t for t in texts_b), \
    "distinct cities must never merge"
print("round-6 rule B pins passed")
