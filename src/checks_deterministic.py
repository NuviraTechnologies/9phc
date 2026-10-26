"""9 PHC — deterministic checks 7 and 8.

These two checks are PLAIN CODE by design. Counting, arithmetic, and
string comparison must never be a model's opinion.

Check 7 — Numbers recomputed: any total stated in a claim is rebuilt
from its underlying component items three independent times; the three
runs must agree, and the agreed value must match the stated total.

Check 8 — Names and IDs letter-checked: any name or identifier as
written in the claim is compared character by character against the
same name/identifier as it appears in its source of record; the first
divergence, if any, is reported exactly.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from model import CheckOutcome, CheckResult, Evidence, SourceClass


# ---------------------------------------------------------------- check 7

_ONES = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
         "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
         "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
         "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
         "seventy": 70, "eighty": 80, "ninety": 90}


def _words_to_number(text: str) -> Decimal:
    """Parse a leading English number (digits or words) out of a phrase:
    'fifty' -> 50, 'eighteen Greek editions' -> 18, '1,250 items' -> 1250."""
    cleaned = text.replace(",", "").strip().lower()
    first = cleaned.split()[0] if cleaned.split() else ""
    if first.replace(".", "", 1).isdigit():
        return Decimal(first)
    total, current, seen = 0, 0, False
    for tok in cleaned.replace("-", " ").split():
        if tok in _ONES:
            current += _ONES[tok]; seen = True
        elif tok in _TENS:
            current += _TENS[tok]; seen = True
        elif tok == "hundred":
            current = (current or 1) * 100; seen = True
        elif tok == "thousand":
            total += (current or 1) * 1000; current = 0; seen = True
        elif tok == "dozen":
            current = (current or 1) * 12; seen = True
        elif tok == "and":
            continue
        else:
            break
    if not seen:
        raise InvalidOperation(f"no number at the start of {text!r}")
    return Decimal(total + current)


def _to_decimal(value) -> Decimal:
    s = str(value).replace(",", "").strip().rstrip("%").strip()
    try:
        return Decimal(s)
    except InvalidOperation:
        return _words_to_number(s)


def recompute_three_times(components: list) -> tuple[Decimal, bool]:
    """Rebuild a total from its components three times.

    Returns (value, agreed). Agreement is a hard requirement: if the
    three independent recomputations disagree, the discrepancy is
    reported upstream, never averaged away.
    """
    runs: list[Decimal] = []
    for _ in range(3):
        total = Decimal("0")
        for c in components:
            total += _to_decimal(c)
        runs.append(total)
    return runs[0], runs[0] == runs[1] == runs[2]


def check_numbers(claim_id: int, stated_total, components: list) -> CheckResult:
    """Verify a stated total against the items it claims to count."""
    try:
        stated = _to_decimal(stated_total)
    except (InvalidOperation, ValueError):
        return CheckResult(
            check_number=7, check_name="Numbers recomputed",
            outcome=CheckOutcome.UNSETTLED,
            note=f"Stated total {stated_total!r} is not a readable number.",
            door="The underlying item list, in a readable source",
        )
    value, agreed = recompute_three_times(components)
    if not agreed:
        return CheckResult(
            check_number=7, check_name="Numbers recomputed",
            outcome=CheckOutcome.UNSETTLED,
            note="Three recomputations of the same items did not agree; "
                 "the discrepancy is reported, not averaged away.",
            door="A clean item list from the source of record",
        )
    # The receipt for an arithmetic verdict is the document itself:
    # the components as the author wrote them are the primary record
    # for the author's own total. A correction printed by this program
    # must carry its receipt — deterministic checks included.
    receipt = Evidence(
        source_name="The audited document's own stated components",
        source_class=SourceClass.PRIMARY_RECORD,
        detail=f"Components as written: {', '.join(str(c) for c in components)} — "
               f"they rebuild to {value} (three recomputations, in agreement).",
    )
    if value == stated:
        return CheckResult(
            check_number=7, check_name="Numbers recomputed",
            outcome=CheckOutcome.PASS,
            note=f"Total rebuilt from {len(components)} items three times: "
                 f"{value} — matches the stated total.",
            evidence=[receipt],
        )
    return CheckResult(
        check_number=7, check_name="Numbers recomputed",
        outcome=CheckOutcome.FAIL,
        note=f"Stated total is {stated}, but the {len(components)} underlying "
             f"items rebuild to {value} (three runs, in agreement).",
        evidence=[receipt],
    )


# ---------------------------------------------------------------- check 8

def _first_divergence(a: str, b: str) -> int | None:
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i
    if len(a) != len(b):
        return min(len(a), len(b))
    return None


def letter_check(as_written: str, as_in_source: str, what: str = "identifier") -> CheckResult:
    """Compare a name/ID as written against its source of record, letter by letter."""
    if as_written == as_in_source:
        return CheckResult(
            check_number=8, check_name="Names and IDs letter-checked",
            outcome=CheckOutcome.PASS,
            note=f"{what} matches its source exactly, character by character: {as_in_source}",
        )
    pos = _first_divergence(as_written, as_in_source)
    written_char = as_written[pos] if pos is not None and pos < len(as_written) else "(end of string)"
    source_char = as_in_source[pos] if pos is not None and pos < len(as_in_source) else "(end of string)"
    return CheckResult(
        check_number=8, check_name="Names and IDs letter-checked",
        outcome=CheckOutcome.FAIL,
        note=(
            f"{what} as written ({as_written!r}) diverges from its source "
            f"({as_in_source!r}) at character {pos + 1 if pos is not None else '?'}: "
            f"written has {written_char!r}, the source has {source_char!r}."
        ),
    )


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _surname(author: str) -> str:
    """The family name from a registry author string. Registries do not
    agree on format: Crossref/Open Library give 'Given Family', DataCite
    creators give 'Family, Given'. Taking the last token of a DataCite
    string would letter-check against the author's FIRST name — a bug
    that manufactures false corrections. The comma decides."""
    author = author.strip()
    if "," in author:
        head = author.split(",", 1)[0].strip()
        if "-" in head:
            return head  # hyphenated family names travel whole ('Martin-Du Gard')
        parts = head.split()
        return parts[-1] if parts else ""
    parts = author.split()
    return parts[-1] if parts else ""


def registry_name_check(claim, records: list[dict]) -> CheckResult | None:
    """Check 8's name half, wired to the registries: author surnames as
    written in the document's citations are letter-checked against the
    surnames in the resolved source records. A near-miss (edit distance
    1-2, not equal) is a misspelling with the correction in hand — the
    record's own spelling. Names written in the claim TEXT are held to
    a tighter window (distance exactly 1): ordinary prose is full of
    capitalized words, and a loose window would manufacture findings.
    Deterministic code, no model opinion."""
    import re as _re
    surnames: list[str] = []
    surname_source: dict[str, tuple[str, dict]] = {}
    for rec in records:
        for author in rec.get("authors", []):
            sur = _surname(author)
            if sur and sur not in surnames:
                surnames.append(sur)
                surname_source[sur] = (author, rec)
    if not surnames:
        return None

    def _with_receipt(result: CheckResult, sur: str) -> CheckResult:
        """A name correction's receipt is the registry record itself —
        the record that spells the name is named and referenced, so
        the correction can be re-opened by anyone reading the report."""
        author, rec = surname_source[sur]
        result.evidence = [Evidence(
            source_name=f"Registry record: \"{rec.get('title', '')}\"",
            source_class=SourceClass.PRIMARY_RECORD,
            detail=f"The record's author of record is {author} — the name "
                   f"is spelled '{sur}'.",
            reference=rec.get("doi", ""))]
        return result
    token_re = _re.compile(r"[A-Z][a-zà-ÿ]+(?:-[A-Z][a-zà-ÿ]+)*")

    def candidates(text: str, title: str) -> list[str]:
        out: list[str] = []
        for tok in token_re.findall(text or ""):
            if len(tok) >= 3 and tok not in title and tok not in out:
                out.append(tok)
        return out

    cited: list[str] = []
    titles = ""
    for cit in claim.citations:
        titles += " " + (cit.source_title or "")
        cited.extend(candidates(cit.raw or "", cit.source_title or ""))
    matched = False
    for cand in cited:
        for sur in surnames:
            if cand == sur or cand == sur.split("-")[-1]:
                matched = True
            elif 1 <= _levenshtein(cand.lower(), sur.lower()) <= 2:
                result = letter_check(cand, sur, what=f"Name '{cand}'")
                result.note += (f" Registry record for the cited source spells it '{sur}'.")
                return _with_receipt(result, sur)
    for cand in candidates(claim.text or "", titles):
        if cand in cited:
            continue
        for sur in surnames:
            if cand == sur:
                matched = True
            elif _levenshtein(cand.lower(), sur.lower()) == 1:
                result = letter_check(cand, sur, what=f"Name '{cand}'")
                result.note += (f" Registry record for the cited source spells it '{sur}'.")
                return _with_receipt(result, sur)
    if matched:
        return CheckResult(
            check_number=8, check_name="Names and IDs letter-checked",
            outcome=CheckOutcome.PASS,
            note="Cited author names match the registry records exactly.")
    return None


_DOI_SHAPE = re.compile(r"^10\.\d{4,9}/\S+$")


def doi_shape_check(doi: str) -> CheckResult:
    """Shape only: does this string have the form of a DOI at all?
    Existence of the DOI is check 1's job, not this one's."""
    cleaned = doi.strip().removeprefix("https://doi.org/").removeprefix("doi:")
    if _DOI_SHAPE.match(cleaned):
        return CheckResult(
            check_number=8, check_name="Names and IDs letter-checked",
            outcome=CheckOutcome.PASS,
            note=f"DOI {cleaned} has valid DOI form (existence is check 1).",
        )
    return CheckResult(
        check_number=8, check_name="Names and IDs letter-checked",
        outcome=CheckOutcome.FAIL,
        note=f"{doi!r} does not have the form of a DOI.",
    )
