"""9 PHC — verdict engine and report renderer.

The engine takes a claim plus the results of the checks that ran on it
and resolves exactly one verdict, by these rules (from the spec):

- CORRECTED: a check contradicted the claim AND the record supplies
  what is actually true. A contradiction always outranks uncertainty.
- HELD — unverified: no contradiction settled it, but a deciding check
  could not settle the claim from reachable peer-reviewed / primary
  sources. The door (the unreachable source) is named. Never softened.
- VERIFIED: every applicable check passed, with at least one receipt
  from a peer-reviewed source or a primary record.

A verdict may not rest on tertiary evidence (Wikipedia and its kin).
If the only support is tertiary, the claim is HELD — the standard is
peer-reviewed or primary, or the claim does not carry a verdict of
confidence.
"""

from __future__ import annotations

from model import (
    CheckOutcome,
    Claim,
    ClaimVerdict,
    SourceClass,
    Verdict,
)


def _has_strong_receipt(verdict_in: ClaimVerdict) -> bool:
    return any(
        e.source_class in (SourceClass.PEER_REVIEWED, SourceClass.PRIMARY_RECORD)
        for e in verdict_in.receipts()
    )


def resolve_verdict(claim: Claim, checks, corrections: dict[int, str] | None = None) -> ClaimVerdict:
    """corrections: {check_number: what the record actually says}, for FAILed checks."""
    corrections = corrections or {}
    v = ClaimVerdict(claim=claim, verdict=Verdict.HELD, checks=list(checks))

    fails = [c for c in checks if c.outcome is CheckOutcome.FAIL]
    unsettled = [c for c in checks if c.outcome is CheckOutcome.UNSETTLED]

    if fails:
        corr_texts = [corrections[c.check_number] for c in fails if c.check_number in corrections]
        if corr_texts:
            v.verdict = Verdict.CORRECTED
            v.correction = " ".join(corr_texts)
            return v
        # Contradicted but the correction itself is not in hand:
        # the claim cannot stand, and we do not guess — it is HELD.
        v.held_reason = (
            "A check contradicted this claim, but the correcting record was not "
            "reachable in this run, so no correction is asserted."
        )
        doors = [c.door for c in fails if c.door] + [c.door for c in unsettled if c.door]
        if doors:
            v.held_reason += f" Door: {doors[0]}."
        return v

    if unsettled:
        v.verdict = Verdict.HELD
        reasons = [c.note for c in unsettled if c.note]
        doors = [c.door for c in unsettled if c.door]
        v.held_reason = " ".join(reasons)
        if doors:
            v.held_reason += f" Door: {doors[0]}."
        return v

    if checks and all(c.outcome is CheckOutcome.PASS for c in checks):
        if _has_strong_receipt(v):
            v.verdict = Verdict.VERIFIED
            return v
        v.verdict = Verdict.HELD
        if not v.receipts():
            v.held_reason = (
                "Checks passed, but no check produced a receipt from any source "
                "in this run. Under the source standard a claim is Verified on "
                "receipts, not on the absence of contradiction."
            )
        else:
            v.held_reason = (
                "Checks passed, but the only receipts are tertiary sources, which "
                "never settle a claim under the source standard."
            )
        return v

    v.held_reason = "No check settled this claim in this run."
    return v


# ------------------------------------------------------------------ report

def verdicts_to_dict(verdicts: list[ClaimVerdict], document_title: str = "Audited document") -> dict:
    """The findings as structured data — the form an AI agent consumes
    when it calls 9 PHC as a tool. Same verdicts, same receipts."""
    counts = {v: 0 for v in Verdict}
    for cv in verdicts:
        counts[cv.verdict] += 1
    total = len(verdicts)
    return {
        "program": "9 PHC",
        "document": document_title,
        "summary": {
            "claims": total,
            "verified": counts[Verdict.VERIFIED],
            "corrected": counts[Verdict.CORRECTED],
            "held_unverified": counts[Verdict.HELD],
            # The confidence rating: arithmetic over verdicts, computed
            # in code — the share of claims that verified AS WRITTEN.
            # Never a model's opinion of a claim; a claim is verified
            # or it is not. The number lives at document level, where
            # it is real counting.
            "confidence_percent": (round(100 * counts[Verdict.VERIFIED] / total)
                                   if total else None),
        },
        "claims": [
            {
                "id": cv.claim.id,
                "text": cv.claim.text,
                "verdict": cv.verdict.value,
                "correction": cv.correction,
                "held_reason": cv.held_reason,
                "checks": [
                    {"number": ch.check_number, "name": ch.check_name,
                     "outcome": ch.outcome.value, "note": ch.note, "door": ch.door}
                    for ch in cv.checks
                ],
                "receipts": [
                    {"source": e.source_name, "class": e.source_class.value,
                     "detail": e.detail, "reference": e.reference}
                    for e in cv.receipts()
                ],
            }
            for cv in verdicts
        ],
    }


def render_report(verdicts: list[ClaimVerdict], document_title: str = "Audited document") -> str:
    counts = {v: 0 for v in Verdict}
    for cv in verdicts:
        counts[cv.verdict] += 1

    lines: list[str] = []
    lines.append(f"# 9 PHC audit — {document_title}")
    lines.append("")
    lines.append(
        f"**{len(verdicts)} claims audited.** "
        f"Verified: {counts[Verdict.VERIFIED]} · "
        f"Corrected: {counts[Verdict.CORRECTED]} · "
        f"Held — unverified: {counts[Verdict.HELD]}"
    )
    if verdicts:
        conf = round(100 * counts[Verdict.VERIFIED] / len(verdicts))
        lines.append("")
        lines.append(
            f"**Document confidence: {conf}%** — the share of claims that verified "
            "as written, counted from the verdicts above. A rating of the document, "
            "never a guess about a claim: each claim below is Verified, Corrected, "
            "or Held, with its receipts."
        )
    lines.append("")
    lines.append(
        "Tier note: 9 PHC is the third tier of truth constraint — a post-research "
        "audit over finished work. Verdicts rest on peer-reviewed sources and "
        "primary records only."
    )
    lines.append("")

    if verdicts:
        lines.append("## Verdict index")
        lines.append("")
        for cv in verdicts:
            text = cv.claim.text.replace("\n", " ")
            if len(text) > 90:
                text = text[:87] + "…"
            lines.append(f"- Claim {cv.claim.id} — **{cv.verdict.value}** — {text}")
        lines.append("")

    for cv in verdicts:
        c = cv.claim
        lines.append(f"## Claim {c.id} — {cv.verdict.value}")
        lines.append("")
        lines.append(f"> {c.text}")
        lines.append("")
        if cv.verdict is Verdict.CORRECTED and cv.correction:
            lines.append(f"**Correction:** {cv.correction}")
            lines.append("")
        if cv.verdict is Verdict.HELD and cv.held_reason:
            lines.append(f"**Why held:** {cv.held_reason}")
            lines.append("")
        if cv.checks:
            lines.append("Checks:")
            for ch in cv.checks:
                lines.append(f"- Check {ch.check_number} ({ch.check_name}): {ch.outcome.value} — {ch.note}")
            lines.append("")
        receipts = cv.receipts()
        if receipts:
            lines.append("Receipts:")
            for e in receipts:
                ref = f" [{e.reference}]" if e.reference else ""
                lines.append(f"- {e.source_name} ({e.source_class.value}){ref}: {e.detail}")
            lines.append("")

    return "\n".join(lines)
