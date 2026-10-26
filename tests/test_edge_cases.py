#!/usr/bin/env python3
"""9 PHC — edge-case tests. Zero spend: every client here is scripted.

Run: python3 tests/test_edge_cases.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from audit import _chunk_document, audit_document_data, extract_claims  # noqa: E402

PASS_JSON = json.dumps({
    "outcome": "pass", "note": "scripted pass: \"the record states it\"", "door": "", "correction": "",
    "evidence": [{"source_name": "Scripted receipt", "source_class": "peer_reviewed",
                  "detail": "supports the claim", "reference": "test"}],
})
PASS_NO_RECEIPT_JSON = json.dumps({
    "outcome": "pass", "note": "scripted pass, no receipt: \"the record states it\"", "door": "",
    "correction": "", "evidence": [],
})


class StubClient:
    """Returns a fixed extraction; check calls return a fixed verdict."""

    def __init__(self, extraction_claims, check_json=PASS_JSON):
        self._claims = extraction_claims
        self._check_json = check_json

    def fresh(self):
        return StubClient(self._claims, self._check_json)

    def complete(self, model, system, user, json_schema=None):
        if json_schema and json_schema.get("name") == "claim_extraction":
            return json.dumps({"claims": self._claims})
        return self._check_json


def claim(text, **kw):
    base = {"text": text, "claim_type": "factual", "citations": [],
            "aliases": [], "numbers": [], "components": []}
    base.update(kw)
    return base


# 1. Empty document: zero claims must not crash the confidence math.
report, findings = audit_document_data(StubClient([]), "", "Empty doc")
assert findings["summary"]["claims"] == 0
assert findings["summary"]["confidence_percent"] is None
assert "0 claims audited" in report
print("edge 1 OK — empty document: 0 claims, confidence null, report renders")

# 2. Duplicate claims collapse to one (confidence counts claims, so a
#    repeated claim must not be counted twice).
dup = StubClient([claim("The press opened in 1501."),
                  claim("the press opened in 1501!"),
                  claim("Aldus died in 1515.")])
claims = extract_claims(dup, "doc")
assert [c.text for c in claims] == ["The press opened in 1501.", "Aldus died in 1515."], claims
assert [c.id for c in claims] == [1, 2]
print("edge 2 OK — duplicates removed, ids renumbered")

# 3. Malformed extraction entries (no text, empty text) are skipped.
bad = StubClient([{"claim_type": "factual"}, claim(""), claim("A real claim.")])
claims = extract_claims(bad, "doc")
assert len(claims) == 1 and claims[0].text == "A real claim."
print("edge 3 OK — malformed entries skipped, never guessed at")

# 4. Long documents chunk on paragraph boundaries within the budget.
paras = [f"Paragraph {i}. " + "x" * 900 for i in range(50)]
doc = "\n\n".join(paras)
chunks = _chunk_document(doc)
assert len(chunks) >= 3, len(chunks)
assert all(len(c) <= 20_000 + 1_000 for c in chunks)
assert "\n\n".join(chunks).replace("\n\n", " ") or True
recovered = " ".join(" ".join(chunks).split())
assert all(f"Paragraph {i}." in recovered for i in range(50))
print(f"edge 4 OK — {len(doc)} chars split into {len(chunks)} chunks, nothing lost")

# 5. All checks pass but NO receipts at all -> Held, and the reason says
#    receipts are missing (not the tertiary wording).
_, findings = audit_document_data(
    StubClient([claim("An unsupported assertion.")], PASS_NO_RECEIPT_JSON),
    "doc", "No receipts")
c = findings["claims"][0]
assert c["verdict"].startswith("Held"), c
assert "no check produced a receipt" in c["held_reason"], c["held_reason"]
print("edge 5 OK — pass with no receipts is Held, reason names the gap")

# 6. Check 6 runs only when user files are provided.
_, findings = audit_document_data(StubClient([claim("A claim.")]), "doc", "No files")
nums = [ch["number"] for ch in findings["claims"][0]["checks"]]
assert 6 not in nums, nums
_, findings = audit_document_data(StubClient([claim("A claim.")]), "doc", "With files",
                                  user_files="the user's own notes")
nums = [ch["number"] for ch in findings["claims"][0]["checks"]]
assert 6 in nums, nums
print("edge 6 OK — own-files sweep applies only when files are provided")

# 7. Stress: 60 claims, all passing with receipts -> confidence 100,
#    verdicts all Verified, order preserved at scale.
many = [claim(f"Stress claim number {i} about the record.") for i in range(60)]
_, findings = audit_document_data(StubClient(many), "doc", "Stress")
s = findings["summary"]
assert s["claims"] == 60 and s["verified"] == 60 and s["confidence_percent"] == 100, s
assert [c["id"] for c in findings["claims"]] == list(range(1, 61))
print("edge 7 OK — 60-claim stress: all Verified, confidence 100, order preserved")

# 8. Stress the other way: every check unsettled -> every claim Held,
#    confidence 0. Held is a first-class result, not a crash.
UNSETTLED_JSON = json.dumps({
    "outcome": "unsettled", "note": "scripted: cannot settle", "door": "a closed archive",
    "correction": "", "evidence": []})
_, findings = audit_document_data(
    StubClient([claim("An unreachable claim.")], UNSETTLED_JSON), "doc", "All held")
s = findings["summary"]
assert s["held_unverified"] == 1 and s["confidence_percent"] == 0, s
assert "closed archive" in findings["claims"][0]["held_reason"]
print("edge 8 OK — all-unsettled document: Held with the door named, confidence 0")

print("edge cases: all passed")
