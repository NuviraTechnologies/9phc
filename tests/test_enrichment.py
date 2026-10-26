"""Dossier enrichment, pinned (built after live probes 1-2, 2026-10-26):
a record that resolves without an abstract must gain its catalogue
description in the dossier — labelled with its library source — so the
fidelity check has a line it may quote instead of abstaining on an
empty plate. Live-registry test, like the rest of the retrieval suite.
Run: python3 tests/test_enrichment.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from audit import _gather
from model import Citation, Claim
from retrieve import catalogue_description

# A real, catalogued book whose Crossref record carries no abstract:
desc = catalogue_description("The Coming of the Book",
                             ["Lucien Febvre", "Henri-Jean Martin"])
assert desc, "expected a catalogue description for a catalogued book"
assert "Febvre" in desc, desc[:200]

# The gate holds: a title that matches nothing enriches nothing.
assert catalogue_description("Zqxwv Unlikely Monograph On Nothing") == ""

# End to end: the dossier for a claim citing that book carries the
# labelled description line, and the record itself is annotated.
claim = Claim(1, "The Coming of the Book still frames the economics of "
                 "the early press.",
              citations=[Citation(raw="Febvre & Martin, The Coming of "
                                        "the Book",
                                  source_title="The Coming of the Book",
                                  identifier="", locator="")])
records, dossier = _gather(claim)
assert "Catalogue description (Open Library)" in dossier, dossier[:800]
assert any(r.get("catalogue_note") for r in records)

# No citations: nothing to enrich, nothing breaks.
records, dossier = _gather(Claim(2, "A claim with no citations at all."))
assert records == [] and "Catalogue description" not in dossier

print("enrichment: abstract-less records gain a labelled catalogue "
      "description; the gate holds; empty claims stay empty")
