"""Round-4 guards, pinned (built after the round-3 live run):
- existence binding: check 1 fails a claim over a dead citation only
  when the claim's text leans on it (names its author or work). Four
  clean claims were Held in the round-3 run for the neighboring
  Castellan citation they never made.
- check-9 note receipt: a FAIL whose note concedes its record is
  silent on the claim, naming no year and quoting no line, degrades.
- correction gate v3: an additive restatement (keeps the claim's
  tokens, negates nothing) is not a correction — the round-3 specimen
  'corrected' a true 1499 publication claim by embellishing it.
Run: python3 tests/test_round4_guards.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from audit import (_accept_correction, _adversarial_note_floor,
                   _existence_binding, audit_claim)
from model import (CheckOutcome, CheckResult, Citation, Claim, Evidence,
                   SourceClass, Verdict)

FAILURES = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILURES.append(name)


CASTELLAN = Citation(
    raw='as M. Castellan has shown in "Paper Supply in the Venetian '
        'Lagoon, 1490-1510," Journal of Early Book History 14 (2019)',
    source_title="", identifier="", locator="")

EV = [Evidence("Registry search", SourceClass.PRIMARY_RECORD,
               "No registry record for the Castellan article.", "crossref")]


def _check1_fail():
    return CheckResult(
        check_number=1, check_name="Source existence",
        outcome=CheckOutcome.FAIL,
        note="The cited source does not exist: M. Castellan, \"Paper "
             "Supply in the Venetian Lagoon,\" resolves in no registry.",
        evidence=list(EV))


# ------------------------------------------------------- existence binding
nonlean = Claim(1, "Aldus issued his octavo Virgil in 1501.",
                citations=[CASTELLAN])
check("dead citation does not fail a claim that never leans on it",
      _existence_binding(nonlean, _check1_fail()).outcome
      is CheckOutcome.UNSETTLED)

lean = Claim(2, "Paper supply in the Venetian lagoon constrained every "
                "printer in the city, as M. Castellan has shown.",
             citations=[CASTELLAN])
check("the claim that names Castellan is failed for his dead citation",
      _existence_binding(lean, _check1_fail()).outcome is CheckOutcome.FAIL)

vague = CheckResult(
    check_number=1, check_name="Source existence",
    outcome=CheckOutcome.FAIL,
    note="The record contradicts the citation.",
    evidence=[Evidence("Registry search", SourceClass.PRIMARY_RECORD,
                       "No registry record for the cited article.",
                       "crossref")])
check("an unattributable existence FAIL stands untouched",
      _existence_binding(nonlean, vague).outcome is CheckOutcome.FAIL)

nocit = Claim(3, "Aldus issued his octavo Virgil in 1501.")
check("a citation-less claim's check 1 is untouched",
      _existence_binding(nocit, _check1_fail()).outcome is CheckOutcome.FAIL)

# ------------------------------------------------------------- integration
def _res(outcome, note="", door="", correction="", evidence=None):
    return json.dumps({"outcome": outcome, "note": note, "door": door,
                       "correction": correction,
                       "evidence": evidence if evidence is not None else []})


class Stub:
    def fresh(self):
        return Stub()

    def complete(self, model, system, user, json_schema=None):
        if "KILL the claim" in system:
            return _res("pass", "The claim survives the attack.")
        if "does this source exist" in system:
            return _res(
                "fail",
                "The cited source does not exist: M. Castellan, \"Paper "
                "Supply in the Venetian Lagoon,\" resolves in no registry.",
                correction="The cited source does not exist: M. Castellan's "
                           "article resolves in no registry.",
                evidence=[{"source_name": "Registry search",
                           "source_class": "primary_record",
                           "detail": "No record for the Castellan article.",
                           "reference": "crossref"}])
        if "say what the claim says it says" in system:
            return _res("pass", 'The record line "issued at Venice in 1501" '
                                'matches the claim.')
        return _res("pass", "Settled against the record.")


v = audit_claim(Stub(), Claim(11, "Aldus issued his octavo Virgil in 1501.",
                              citations=[CASTELLAN]))
c1 = next(c for c in v.checks if c.check_number == 1)
check("integration: over-attached dead citation leaves the clean claim "
      "uncorrected", c1.outcome is CheckOutcome.UNSETTLED
      and v.verdict is not Verdict.CORRECTED)

v = audit_claim(Stub(), Claim(12, "Paper supply in the Venetian lagoon "
                                  "constrained every printer in the city, "
                                  "as M. Castellan has shown.",
                              citations=[CASTELLAN]))
c1 = next(c for c in v.checks if c.check_number == 1)
check("integration: the leaning claim is Corrected on the dead citation",
      c1.outcome is CheckOutcome.FAIL and v.verdict is Verdict.CORRECTED)

# ------------------------------------------------------------ gate v3
dummy = CheckResult(9, "Adversarial pass", CheckOutcome.FAIL, note="x")
c10 = Claim(20, "The Hypnerotomachia Poliphili was published in 1499.")
check("gate v3 drops the additive restatement (round-3 specimen)",
      _accept_correction(c10, dummy,
                         "The Hypnerotomachia Poliphili was first published "
                         "(printed) by Aldus Manutius in 1499.") == "")
c12 = Claim(21, "The Hypnerotomachia Poliphili has never been translated "
                "into English.")
check("gate v3 keeps the genuine Godwin correction",
      _accept_correction(c12, dummy,
                         "Strike 'never been translated into English'. The "
                         "Hypnerotomachia Poliphili has been translated "
                         "into English in full by Joscelyn Godwin "
                         "(Thames and Hudson, 1999).") != "")
check("gate v3 keeps a negating correction that reuses claim tokens",
      _accept_correction(c10, dummy,
                         "The Hypnerotomachia Poliphili was not published "
                         "in 1499; the edition appeared in 1500.") != "")

# ------------------------------------------------------- note receipt (9)
def _adv(note):
    return CheckResult(check_number=9, check_name="Adversarial pass",
                       outcome=CheckOutcome.FAIL, note=note,
                       evidence=list(EV))


check("a silence-conceding FAIL with no year and no quote degrades",
      _adversarial_note_floor(_adv(
          "The source dossier attached to the claim itself is silent on "
          "the claim (its retrieved record concerns another work), but "
          "the claim overstates the case and should not stand as written."
      )).outcome is CheckOutcome.UNSETTLED)
check("a silence-conceding note that quotes its record stands",
      _adversarial_note_floor(_adv(
          "The dossier is silent on the claim, but the edition's own line "
          "\"printed at Venice by Aldus\" contradicts the claim's place "
          "of printing, and the attack lands on that line."
      )).outcome is CheckOutcome.FAIL)
check("round-3 specimens unchanged: degenerate note degrades, year stands",
      _adversarial_note_floor(_adv("at-check9")).outcome
      is CheckOutcome.UNSETTLED
      and _adversarial_note_floor(_adv("Per Lowry 1979, Griffo cut it.")
                                  ).outcome is CheckOutcome.FAIL)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
    raise SystemExit(1)
print("ALL ROUND-4 GUARD TESTS PASS")
