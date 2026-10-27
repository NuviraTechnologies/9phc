"""Round-3 guards, pinned (built after the round-2 live run):
- extraction citation discipline: the prompt carries the own-sentence +
  next-sentence attachment rule, and a deterministic re-attachment sweep
  backstops it (a citation-less claim whose source sentence carries a
  citation gains it; claims already cited and claims with no matching
  sentence are untouched)
- check 9 note floor: a FAIL whose note is degenerate (very short, no
  year named, no line quoted) degrades to UNSETTLED — the live specimen
  was a FAIL noted "at-check9" that printed a fragment as a correction
- scorer honesty: claims matching a planted marker are judged by their
  expectation alone; the clean sweep no longer flags the correct
  computed catches (tally "1515", Fevre "1976") as FALSE-CORRECTIONs
Run: python3 tests/test_round3_guards.py"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from audit import _adversarial_note_floor, _reattach_citations, extract_claims
from extraction import EXTRACTION_SYSTEM_PROMPT
from model import CheckOutcome, CheckResult, Claim, Evidence, SourceClass

ROOT = Path(__file__).resolve().parent.parent
FAILURES = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILURES.append(name)


# ---------------------------------------------------------------- lane 1a
check("extraction prompt carries the citation attachment rule",
      "immediately" in EXTRACTION_SYSTEM_PROMPT
      and "following it" in EXTRACTION_SYSTEM_PROMPT)

# ---------------------------------------------------------------- lane 1b
BRIEF = (ROOT / "demo" / "demo-brief.md").read_text()


class _StubClient:
    """Returns fixed extraction JSON: the round-2 failure shape —
    every claim citation-less."""

    CLAIMS = [
        {"text": "Paper supply in the Venetian lagoon constrained every printer "
                 "in the city, as M. Castellan has shown.",
         "claim_type": "factual", "citations": [], "aliases": [],
         "numbers": [], "components": []},
        {"text": "The Aldine shop produced eighteen Greek editions, fifteen "
                 "Latin classics, and fourteen vernacular titles — fifty "
                 "editions in all across the three series.",
         "claim_type": "numerical", "citations": [], "aliases": [],
         "numbers": ["fifty editions"],
         "components": ["eighteen Greek editions", "fifteen Latin classics",
                        "fourteen vernacular titles"]},
        {"text": "The variant state of the dolphin-and-anchor device is "
                 "confirmed in the 1932 Maggs Bros catalogue No. 562.",
         "claim_type": "factual", "citations": [], "aliases": [],
         "numbers": [], "components": []},
        {"text": "Zanzibar's clove exports doubled under the sultan's later reforms.",
         "claim_type": "factual", "citations": [], "aliases": [],
         "numbers": [], "components": []},
    ]

    def fresh(self):
        return self

    def complete(self, model, system, user, json_schema=None):
        return json.dumps({"claims": self.CLAIMS})


claims = extract_claims(_StubClient(), BRIEF)


def _find(substr):
    return next(c for c in claims if substr in c.text)


check("sweep attaches the Castellan paper to its claim",
      any("Paper Supply in the Venetian Lagoon" in (cit.source_title or "")
          for cit in _find("Castellan has shown").citations))
check("sweep attaches the Castellan paper to the tally claim (same sentence)",
      any("Paper Supply in the Venetian Lagoon" in (cit.source_title or "")
          for cit in _find("fifty editions in all").citations))
check("sweep attaches the Maggs catalogue reference",
      any("Maggs Bros catalogue No. 562" in (cit.raw or "")
          for cit in _find("dolphin-and-anchor").citations))
check("claim absent from the document gains nothing",
      _find("Zanzibar").citations == [])

already = Claim(id=99, text="Paper supply in the Venetian lagoon constrained "
                           "every printer in the city, as M. Castellan has shown.")
from model import Citation as _Cit
already.citations = [_Cit(raw="kept as extracted", source_title="Kept Title")]
n = _reattach_citations([already], BRIEF)
check("sweep never touches a claim the model already cited",
      n == 0 and already.citations[0].source_title == "Kept Title")

# ---------------------------------------------------------------- lane 2
EV = [Evidence("Registry record", SourceClass.PRIMARY_RECORD,
               "Settles the point.", "probe")]


def _adv(note, outcome=CheckOutcome.FAIL):
    return CheckResult(check_number=9, check_name="Adversarial pass",
                       outcome=outcome, note=note, evidence=list(EV))


check("the live specimen (note 'at-check9') degrades to UNSETTLED",
      _adversarial_note_floor(_adv("at-check9")).outcome is CheckOutcome.UNSETTLED)
check("a substantive FAIL note stands",
      _adversarial_note_floor(_adv(
          "The record shows the type was cut by Francesco Griffo; the claim's "
          "attribution to Aldus is contradicted by the editions themselves."
      )).outcome is CheckOutcome.FAIL)
check("a terse FAIL note naming a year stands",
      _adversarial_note_floor(_adv("Per Lowry 1979, Griffo cut it.")
                              ).outcome is CheckOutcome.FAIL)
check("a PASS is untouched by the floor",
      _adversarial_note_floor(_adv("ok", CheckOutcome.PASS)).outcome
      is CheckOutcome.PASS)

# ---------------------------------------------------------------- lane 3
def _claim_json(text, verdict, correction="", held_reason=""):
    return {"id": 0, "text": text, "verdict": verdict,
            "correction": correction, "held_reason": held_reason, "checks": []}


tiny = {
    "claims": [
        _claim_json("The italic type was designed by Aldus himself.",
                    "Corrected", "The italic was cut by Francesco Griffo."),
        _claim_json("Paper supply, as M. Castellan has shown, constrained printers.",
                    "Held", "",
                    "The cited source does not exist in any registry."),
        _claim_json("The Hypnerotomachia has never been translated into English.",
                    "Corrected", "Translated by Josiah Godwin in 1999."),
        _claim_json("The shop produced eighteen Greek editions, fifteen Latin "
                    "classics, and fourteen vernacular titles — fifty editions in "
                    "all before the founder's death in 1515.",
                    "Corrected", "Stated total is 50, but the items rebuild to 47."),
        _claim_json("Lucien Fevre and Henri-Jean Martin, The Coming of the Book "
                    "(English translation, 1976), still frame the economics.",
                    "Corrected", "Name 'Fevre' diverges from its source ('Febvre')."),
        _claim_json("The dolphin-and-anchor variant is confirmed in the Maggs "
                    "Bros catalogue No. 562.", "Held", "",
                    "The only record is the Maggs Bros catalogue No. 562 "
                    "(1932), print only."),
        _claim_json("The Aldine octavo series began in 1501 and ran for years.",
                    "Corrected", "A correction no clean claim should carry."),
    ],
    "summary": {"claims": 7, "confidence_percent": 0, "wall_clock_seconds": 0,
                "api_calls": 0, "api_tokens": 0},
}
with tempfile.TemporaryDirectory() as td:
    p = Path(td) / "tiny.audit.json"
    p.write_text(json.dumps(tiny))
    out = subprocess.run(
        [sys.executable, str(ROOT / "demo" / "score_run.py"), str(p)],
        capture_output=True, text=True).stdout
false_lines = [l for l in out.splitlines() if "FALSE-CORRECTION" in l]
check("scorer flags exactly the one genuine false correction",
      len(false_lines) == 1 and "1501" in false_lines[0])
check("scorer still catches 6/6 on the synthetic set",
      "Planted items: 6/6 caught" in out)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
    raise SystemExit(1)
print("ALL ROUND-3 GUARD TESTS PASS")
