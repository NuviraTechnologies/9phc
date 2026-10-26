#!/usr/bin/env python3
"""Score a 9 PHC audit JSON against the planted-errors answer key.

Usage: python3 demo/score_run.py demo/demo-brief.audit.json

Objective grading: each planted item names the claim-text marker to
find, the verdict it must carry, and the term its correction or held
reason must contain. Clean claims must come back Verified. The score
is printed plainly; a miss is a miss.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

EXPECTATIONS = [
    # (marker in claim text, expected verdict, term in correction, label)
    ("italic", "Corrected", "Griffo", "1 fidelity: italic credited to Aldus"),
    ("Castellan", None, "exist", "2 existence: invented Castellan citation flagged"),
    ("never been translated", "Corrected", "Godwin", "3 alias sweep: Hypnerotomachia translation"),
    ("fifty editions", "Corrected", "47", "4 numbers: total rebuilds to 47"),
    ("Fevre", "Corrected", "Febvre", "5 names: Fevre letter-checked to Febvre"),
    ("Maggs", "Held", "Maggs", "6 held: Maggs Bros 562 named as the door"),
]

CLEAN_MARKERS = ["1501", "1515", "1499", "1976"]


def main() -> int:
    data = json.loads(Path(sys.argv[1]).read_text())
    if len(sys.argv) > 2:
        spec = json.loads(Path(sys.argv[2]).read_text())
        expectations = [tuple(x) for x in spec["expectations"]]
        clean_markers = spec["clean_markers"]
    else:
        expectations, clean_markers = EXPECTATIONS, CLEAN_MARKERS
    claims = data["claims"]
    caught, missed = [], []
    for marker, verdict, term, label in expectations:
        hits = [c for c in claims if marker.lower() in c["text"].lower()]
        if not hits:
            missed.append(f"{label} — claim not found in extraction")
            continue
        c = hits[0]
        blob = (c.get("correction", "") + " " + c.get("held_reason", "")).lower()
        ok_verdict = verdict is None or c["verdict"] == verdict or c["verdict"].startswith(verdict)
        if c["verdict"] in ("Corrected", "Held") and not ok_verdict:
            ok_verdict = False
        if ok_verdict and term.lower() in blob:
            caught.append(label)
        else:
            missed.append(
                f"{label} — got verdict {c['verdict']}, correction/held text lacks '{term}'")
    clean_bad = []
    for marker in clean_markers:
        hits = [c for c in claims if marker in c["text"]]
        for c in hits:
            if c["verdict"] == "Corrected":
                clean_bad.append(f"clean claim corrected in error: {c['text'][:70]}…")
    s = data["summary"]
    print(f"Planted items: {len(caught)}/{len(expectations)} caught")
    for x in caught:
        print(f"  CAUGHT  {x}")
    for x in missed:
        print(f"  MISSED  {x}")
    for x in clean_bad:
        print(f"  FALSE-CORRECTION  {x}")
    print(f"Summary: {s['claims']} claims · confidence {s.get('confidence_percent')}% · "
          f"wall clock {s.get('wall_clock_seconds')}s · "
          f"API {s.get('api_calls')} calls / {s.get('api_tokens')} tokens")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
