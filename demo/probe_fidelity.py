"""Probe: does a quote-demanded retry make fidelity engage?

The confirming run of 2026-10-27 Held the brief's 1499 claims because
fidelity returned verdicts without quoting the record, and the
quote-or-abstain rule voided them. This probe extracts the Aldine
brief's claims with the production extractor, picks the claims about
1499, gathers their real dossiers, then calls check 2 twice per
claim: once as the pipeline does today (baseline) and once with an
explicit retry instruction appended — quote the deciding line
verbatim in the note, or return unsettled. It reports, per claim,
whether each call returned a verdict carrying a quoted span.

Cost: extraction (2 Spark calls) + 2 Wonder calls per target claim.
Run: python3 demo/probe_fidelity.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from audit import (  # noqa: E402
    _CHECK_RESULT_SCHEMA, _QUOTED_SPAN, _gather, _parse_check,
    _safe_complete, MetaModelClient, MODEL_FIDELITY, extract_claims)
from prompts import CHECK_PROMPTS, SOURCE_STANDARD  # noqa: E402

RETRY_SUFFIX = """

RETRY — READ CAREFULLY: a previous attempt at this check returned a
verdict whose note quoted no line of the record, and under the
quote-or-abstain rule that verdict was void. In your note, quote the
deciding line of the record VERBATIM (the exact words, in quotation
marks) before you state your verdict — or return "unsettled" if no
line of the record in hand decides this claim."""


def call(client, claim, dossier, retry):
    name, mandate = CHECK_PROMPTS[2]
    user = f"CLAIM: {claim.text}\nALIASES: {', '.join(claim.aliases) or '(none listed)'}\n"
    user += "CITATIONS:\n" + ("\n".join(f"- {c.raw}" for c in claim.citations) or "(none)")
    user += ("\n\nSOURCE DOSSIER (registry retrieval — ground truth, "
             f"gathered before this check ran):\n{dossier}")
    if retry:
        user += RETRY_SUFFIX
    raw = _safe_complete(
        client, MODEL_FIDELITY,
        f"{mandate}\n\n{SOURCE_STANDARD}\n\nFill EVERY field of the schema; "
        "use an empty string when a field does not apply.",
        user, json_schema=_CHECK_RESULT_SCHEMA)
    if raw is None:
        return None
    result, _ = _parse_check(2, name, raw)
    return result


def main():
    doc = Path("demo/demo-brief.md").read_text()
    client = MetaModelClient()
    client.attach_ledger("demo/probe-fidelity.spend.jsonl")
    claims = extract_claims(client, doc)
    targets = [c for c in claims if "1499" in c.text][:3]
    print(f"extracted {len(claims)} claims; probing {len(targets)} about 1499")
    for claim in targets:
        _, dossier = _gather(claim)
        for label, retry in (("baseline", False), ("retry", True)):
            r = call(client, claim, dossier, retry)
            if r is None:
                print(f"  claim {claim.id} {label}: call failed")
            else:
                quoted = bool(_QUOTED_SPAN.search(r.note or ""))
                print(f"  claim {claim.id} {label}: outcome={r.outcome.value} "
                      f"quoted={quoted} note={r.note[:90]!r}")
    print(f"probe usage: {client.usage_snapshot()}")


if __name__ == "__main__":
    main()
