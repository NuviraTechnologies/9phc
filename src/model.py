"""9 PHC — core data model.

A Claim is one checkable statement extracted from the audited document.
A CheckResult is the outcome of one of the nine checks against one claim.
A ClaimVerdict is the final word on a claim: exactly one of
VERIFIED, CORRECTED, HELD — with the receipts that earned it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Verdict(Enum):
    VERIFIED = "Verified"
    CORRECTED = "Corrected"
    HELD = "Held — unverified"


class CheckOutcome(Enum):
    PASS = "pass"            # the check supports the claim
    FAIL = "fail"            # the check contradicts the claim
    UNSETTLED = "unsettled"  # the check could not settle the claim (door named)


# Source classes permitted to carry a verdict, per the source standard:
# peer-reviewed literature and primary records only.
class SourceClass(Enum):
    PEER_REVIEWED = "peer_reviewed"
    PRIMARY_RECORD = "primary_record"
    TERTIARY = "tertiary"  # e.g. crowd-edited pages — may point, never settles


@dataclass
class Citation:
    """A citation attached to a claim, as written in the audited document."""
    raw: str                      # exactly as written
    source_title: str = ""
    identifier: str = ""          # DOI, catalogue number, record ID, etc.
    locator: str = ""             # page, line, section — where in the source


@dataclass
class Claim:
    id: int
    text: str
    citations: list[Citation] = field(default_factory=list)
    claim_type: str = "general"   # factual | numerical | identity | existence | other
    aliases: list[str] = field(default_factory=list)  # other names the subject carries


@dataclass
class Evidence:
    """One receipt: a source actually opened, and what it said."""
    source_name: str
    source_class: SourceClass
    detail: str                   # what the source says, in the checker's words
    reference: str = ""           # DOI / URL / catalogue ID of the evidence source


@dataclass
class CheckResult:
    check_number: int             # 1..9
    check_name: str
    outcome: CheckOutcome
    note: str = ""                # what the check found, plainly
    door: str = ""                # if UNSETTLED: the unreachable source that decides it
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class ClaimVerdict:
    claim: Claim
    verdict: Verdict
    checks: list[CheckResult] = field(default_factory=list)
    correction: str = ""          # for CORRECTED: what the record actually says
    held_reason: str = ""         # for HELD: why it could not be settled, door named

    def receipts(self) -> list[Evidence]:
        out: list[Evidence] = []
        for c in self.checks:
            out.extend(c.evidence)
        return out
