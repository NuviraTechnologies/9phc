"""Engine test — drives verdict resolution with the demo brief's planted
claims and asserts the answer key's expected verdicts.
Run: python3 tests/test_engine.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from checks_deterministic import check_numbers, letter_check
from engine import render_report, resolve_verdict
from model import (
    CheckOutcome,
    CheckResult,
    Citation,
    Claim,
    Evidence,
    SourceClass,
    Verdict,
)


def cr(n, name, outcome, note="", door=""):
    return CheckResult(check_number=n, check_name=name, outcome=outcome, note=note, door=door)


# 1 — Fidelity error (italic credited to Aldus; actually Griffo) -> CORRECTED
claim = Claim(1, "The Aldine italic type was designed by Aldus Manutius.")
checks = [cr(2, "Source fidelity", CheckOutcome.FAIL,
             "Opened scholarship on Aldine type credits the design to Francesco Griffo.")]
checks[0].evidence.append(Evidence("Peer-reviewed scholarship on Griffo and Aldine type",
                                   SourceClass.PEER_REVIEWED, "The italic was cut by Francesco Griffo."))
v = resolve_verdict(claim, checks, {2: "The italic was designed by Francesco Griffo."})
assert v.verdict is Verdict.CORRECTED and "Griffo" in v.correction

# 2 — Invented citation -> contradicted, no correction in hand -> HELD
claim = Claim(2, "Castellan documented Venetian paper supply in JEBH 14 (2019).",
              citations=[Citation("Castellan, JEBH 14 (2019): 201-240")])
checks = [cr(1, "Source existence", CheckOutcome.FAIL,
             "No such article resolves in any catalogue.",
             door="The cited journal's own archive")]
v = resolve_verdict(claim, checks)
assert v.verdict is Verdict.HELD and "Door" in v.held_reason

# 3 — Alias-missed translation ("never translated") -> CORRECTED
claim = Claim(3, "The Hypnerotomachia Poliphili has never been translated into English.")
checks = [cr(3, "Alias sweep", CheckOutcome.FAIL,
             "Sweep under the work's other names found a complete English translation.")]
checks[0].evidence.append(Evidence("Publisher's catalogue record, Thames & Hudson",
                                   SourceClass.PRIMARY_RECORD,
                                   "Complete English translation by Joscelyn Godwin, 1999."))
v = resolve_verdict(claim, checks, {3: "Translated into English by Joscelyn Godwin (Thames & Hudson, 1999)."})
assert v.verdict is Verdict.CORRECTED

# 4 — Numbers (real deterministic check 7): 18+15+14 stated as 50 -> CORRECTED
claim = Claim(4, "Fifty editions in all: 18 Greek, 15 Latin, 14 vernacular.")
real = check_numbers(4, "50", [18, 15, 14])
assert real.outcome is CheckOutcome.FAIL
v = resolve_verdict(claim, [real], {7: "The three series sum to 47 editions, not 50."})
assert v.verdict is Verdict.CORRECTED

# 5 — Name letter-check via the real registry path (check 8):
# Fevre vs Febvre -> CORRECTED. The pipeline path is registry_name_check
# (bare letter_check knows no record, so it carries no receipt — and
# since the corrections-carry-receipts rule, an unbacked correction
# would resolve Held, as test_layers case 1c pins down).
claim = Claim(5, "Lucien Fevre, The Coming of the Book.",
              citations=[Citation("Fevre, The Coming of the Book",
                                  source_title="The Coming of the Book")])
from checks_deterministic import registry_name_check
real = registry_name_check(claim, [{"title": "The Coming of the Book",
                                    "authors": ["Lucien Febvre", "Henri-Jean Martin"],
                                    "doi": "10.0/record", "container": "Verso",
                                    "year": 1976}])
assert real is not None and real.outcome is CheckOutcome.FAIL
assert real.evidence and real.evidence[0].source_class is SourceClass.PRIMARY_RECORD
v = resolve_verdict(claim, [real], {8: "The name is Lucien Febvre."})
assert v.verdict is Verdict.CORRECTED

# 6 — Print-only deciding source -> HELD, door named
claim = Claim(6, "The anchor-flukes-reversed device variant is confirmed in Maggs Bros catalogue No. 562 (1932).")
checks = [cr(2, "Source fidelity", CheckOutcome.UNSETTLED,
             "The deciding source could not be opened in this run.",
             door="Maggs Bros catalogue No. 562 (1932), print only")]
v = resolve_verdict(claim, checks)
assert v.verdict is Verdict.HELD and "Maggs Bros" in v.held_reason

# 7 — Clean claim with a primary-record receipt -> VERIFIED
claim = Claim(7, "Aldus issued his octavo Virgil in 1501.")
checks = [cr(1, "Source existence", CheckOutcome.PASS, "The edition's record resolves.")]
checks[0].evidence.append(Evidence("Bibliographic record of the 1501 Aldine Virgil",
                                   SourceClass.PRIMARY_RECORD, "Octavo Virgil, Venice, 1501."))
v = resolve_verdict(claim, checks)
assert v.verdict is Verdict.VERIFIED

# 8 — Passes on tertiary receipts only -> HELD (source standard)
claim = Claim(8, "Aldus died in 1515.")
checks = [cr(1, "Source existence", CheckOutcome.PASS, "A tertiary page agrees.")]
checks[0].evidence.append(Evidence("Wikipedia, 'Aldus Manutius'", SourceClass.TERTIARY, "States 1515."))
v = resolve_verdict(claim, checks)
assert v.verdict is Verdict.HELD

verdicts = []
for i, (c, ch, corr) in enumerate([], start=1):
    pass
print("engine: all verdict-resolution tests passed")

# Render a report from two of the verdicts above as a smoke check.
sample = render_report([resolve_verdict(Claim(1, "The Aldine italic type was designed by Aldus Manutius."),
                                        [cr(2, "Source fidelity", CheckOutcome.FAIL, "Credits Griffo.")],
                                        {2: "Designed by Francesco Griffo."})],
                       "demo")
assert "Corrected" in sample and "9 PHC audit" in sample
print("engine: report render smoke test passed")
