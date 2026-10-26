"""Dry-run orchestration test — a scripted client stands in for the
Model API so the whole pipeline runs with zero spend.
Run: python3 tests/test_orchestration.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from audit import audit_document

PASS_JSON = json.dumps({
    "outcome": "pass", "note": "Settled against the record.",
    "evidence": [{"source_name": "Bibliographic record", "source_class": "primary_record",
                  "detail": "Agrees with the claim.", "reference": ""}],
})

EXTRACTION_JSON = json.dumps({"claims": [
    {"text": "Fifty editions in all: 18 Greek, 15 Latin, 14 vernacular.",
     "claim_type": "numerical", "citations": [], "aliases": [],
     "numbers": ["50"], "components": ["18", "15", "14"]},
    {"text": "Aldus issued his octavo Virgil in 1501.",
     "claim_type": "factual", "citations": [], "aliases": []},
]})


class ScriptedClient:
    def fresh(self):
        return ScriptedClient()

    def complete(self, model, system, user, json_schema=None):
        if json_schema and json_schema.get("name") == "claim_extraction":
            return EXTRACTION_JSON
        return PASS_JSON


report = audit_document(ScriptedClient(), "demo document", "Dry run")
# The numbers claim must be Corrected by the REAL deterministic check 7,
# even though every model-backed check "passed".
assert "Claim 1 — Corrected" in report, report
assert "47" in report, report
# The clean claim verifies.
assert "Claim 2 — Verified" in report, report
print("orchestration: dry run passed — pipeline holds together end to end")
