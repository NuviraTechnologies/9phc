"""Self-test for the deterministic checks (7 and 8). Run: python3 tests/test_deterministic.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from checks_deterministic import check_numbers, doi_shape_check, letter_check
from model import CheckOutcome

failures = []

# Check 7: a correct total passes
r = check_numbers(1, "112", [2, 110])
assert r.outcome is CheckOutcome.PASS, r.note
# Check 7: a wrong total fails and names the rebuilt value
r = check_numbers(2, "113", [2, 110])
assert r.outcome is CheckOutcome.FAIL and "112" in r.note, r.note
# Check 7: decimal components
r = check_numbers(3, "0.3", ["0.1", "0.2"])
assert r.outcome is CheckOutcome.PASS, r.note

# Check 8: exact match passes
r = letter_check("Richard Vigslist", "Richard Vigslist", "name")
assert r.outcome is CheckOutcome.PASS, r.note
# Check 8: a dropped letter is caught, at the right character
r = letter_check("Richard Viglist", "Richard Vigslist", "name")
assert r.outcome is CheckOutcome.FAIL and "character 12" in r.note, r.note

# DOI shape: valid and invalid forms
assert doi_shape_check("10.5281/zenodo.23640488").outcome is CheckOutcome.PASS
assert doi_shape_check("zenodo.23640488").outcome is CheckOutcome.FAIL

# Check 7 upgrades: dozen and percent forms (2026-10-26 elevation pass)
r = check_numbers(4, "two dozen", ["twelve", "twelve"])
assert r.outcome is CheckOutcome.PASS, r.note
r = check_numbers(5, "100%", ["40%", "60%"])
assert r.outcome is CheckOutcome.PASS, r.note
r = check_numbers(6, "fifty", ["eighteen", "fifteen", "fourteen"])
assert r.outcome is CheckOutcome.FAIL and "47" in r.note, r.note

# Check 8 registry upgrades: DataCite 'Family, Given' author strings
# must yield the FAMILY name (the old last-token rule read 'Lucien'
# and could manufacture a false correction), and a misspelling carried
# in the claim TEXT (citation spelled right) is still caught.
from checks_deterministic import _surname, registry_name_check
from model import Citation, Claim

assert _surname("Febvre, Lucien") == "Febvre"
assert _surname("Lucien Febvre") == "Febvre"
assert _surname("Martin-Du Gard, Roger") == "Martin-Du Gard"

records = [{"authors": ["Febvre, Lucien", "Martin, Henri-Jean"],
            "title": "The Coming of the Book"}]
bad_text = Claim(id=1, text="As Fevre showed, print changed Europe.",
                 citations=[Citation(raw="Febvre and Martin, The Coming of the Book (1958)",
                                       source_title="The Coming of the Book")])
r = registry_name_check(bad_text, records)
assert r is not None and r.outcome is CheckOutcome.FAIL and "Febvre" in r.note, r
good_text = Claim(id=2, text="As Febvre showed, print changed Europe.",
                  citations=[Citation(raw="Febvre and Martin, The Coming of the Book (1958)",
                                        source_title="The Coming of the Book")])
r = registry_name_check(good_text, records)
assert r is not None and r.outcome is CheckOutcome.PASS, r

print("deterministic checks: all self-tests passed")
