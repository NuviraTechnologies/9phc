"""9 PHC — audit orchestrator.

Pipeline: document -> claim extraction -> nine checks per claim ->
verdict resolution -> Markdown report.

Model-backed checks (1-6, 9) run through a ModelClient. The client is
an interface: the live Meta Model API client slots in once the API key
exists; a scripted client drives dry runs without spending anything.

Checks 7 and 8 are deterministic code and always run for real.
Check 9 always runs in a FRESH client session (the independence rule):
the orchestrator opens a new session for it and passes only the claim.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from checks_deterministic import check_numbers, letter_check
from concurrent.futures import ThreadPoolExecutor
from engine import render_report, resolve_verdict, verdicts_to_dict
from extraction import EXTRACTION_SCHEMA, EXTRACTION_SYSTEM_PROMPT
from model import CheckOutcome, CheckResult, Citation, Claim, ClaimVerdict, Verdict
from prompts import ADVERSARIAL_SYSTEM_PROMPT, CHECK_PROMPTS, SOURCE_STANDARD

API_BASE = "https://api.meta.ai/v1"
HELPER = Path.home() / "workspace/custom-connectors/custom.meta-model-api/bin/meta_api.py"
MODEL_EXTRACTION = "muse-spark-1.3"     # structured output: extraction + evidence checks
MODEL_FIDELITY = "muse-wonder-1.0"      # check 2 (source fidelity): the deep read
MODEL_ADVERSARIAL = "muse-wonder-1.0"   # adversarial pass + deep reads (ID verified live 2026-10-26)


class ModelClient(Protocol):
    def complete(self, model: str, system: str, user: str,
                 json_schema: dict | None = None) -> str: ...
    def fresh(self) -> "ModelClient": ...


class MetaModelClient:
    """Live client for the Meta Model API, via the registered connector.

    The API key lives in the Secure Vault connector (custom.meta-model-api)
    and reaches requests through the connector helper's surrogate exchange.
    This program never sees, stores, or logs the key. Standard API mode
    only — contributor-mode models are never used.
    """

    TOKEN_CEILING = 1_500_000  # hard spend brake: total token ceiling across all calls in a run

    def __init__(self, _state: dict | None = None):
        if not HELPER.exists():
            raise RuntimeError(f"Connector helper not found at {HELPER} — setup is incomplete.")
        if _state is None:
            _state = {"tokens": 0, "calls": 0, "ledger": None,
                      "lock": threading.Lock()}
        self._state = _state

    def fresh(self) -> "MetaModelClient":
        # Fresh session, SHARED spend state: the ceiling covers the run.
        return MetaModelClient(_state=self._state)

    def usage_snapshot(self) -> dict:
        return {"api_calls": self._state["calls"], "api_tokens": self._state["tokens"]}

    def attach_ledger(self, path) -> None:
        """Append one JSON line per API call to this file, at call time.
        The spend record must survive the process: if the run is killed,
        what it burned is still on disk, accounted to the token."""
        self._state["ledger"] = str(path)

    def _record_usage(self, model: str, tokens: int,
                      prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
        with self._state["lock"]:
            self._state["calls"] += 1
            self._state["tokens"] += tokens
            total_calls, total_tokens = self._state["calls"], self._state["tokens"]
            ledger = self._state.get("ledger")
            if ledger:
                line = json.dumps({
                    "ts_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "model": model, "tokens": tokens,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "run_calls": total_calls, "run_tokens": total_tokens})
                with open(ledger, "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
        if total_tokens > self.TOKEN_CEILING:
            raise RuntimeError(
                f"Token ceiling hit ({total_tokens} > {self.TOKEN_CEILING}); "
                "run stopped under the spend cap.")

    def complete(self, model, system, user, json_schema=None):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            cmd = ["python3", str(HELPER), "complete", "--model", model]
            (td / "system.txt").write_text(system)
            (td / "user.txt").write_text(user)
            cmd += ["--system-file", str(td / "system.txt"),
                    "--user-file", str(td / "user.txt")]
            if json_schema:
                (td / "schema.json").write_text(json.dumps(json_schema))
                cmd += ["--schema-file", str(td / "schema.json")]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()
            raise RuntimeError(
                "Meta Model API call failed: " + (tail[-1] if tail else "unknown error"))
        data = json.loads(proc.stdout)
        usage = data.get("usage") or {}
        self._record_usage(model, int(usage.get("total_tokens") or 0),
                           int(usage.get("prompt_tokens") or 0),
                           int(usage.get("completion_tokens") or 0))
        return data["choices"][0]["message"]["content"]


# ---------------------------------------------------------------- extraction

def _safe_complete(client: ModelClient, model: str, system: str, user: str,
                   json_schema: dict | None = None) -> str | None:
    """One retry, then None. A verification program must degrade to
    Held on infrastructure failure — never crash and lose the run."""
    for _ in range(2):
        try:
            return client.complete(model, system, user, json_schema=json_schema)
        except Exception:
            continue
    return None


def _unsettled(number: int, name: str, why: str) -> CheckResult:
    return CheckResult(
        check_number=number, check_name=name, outcome=CheckOutcome.UNSETTLED,
        note=f"This check could not complete: {why}. The claim is not settled by it.",
        door="The model endpoint (call failed twice)")


_CHUNK_CHARS = 20_000  # extraction input budget per call, in characters


def _chunk_document(document: str) -> list[str]:
    """Split a long document on paragraph boundaries so no single
    extraction call carries more than the budget. A document the model
    sees whole is a document whose claims all get checked; a document
    that overflows one call gets silently truncated — so chunk first."""
    if len(document) <= _CHUNK_CHARS:
        return [document]
    chunks: list[str] = []
    current = ""
    for para in document.split("\n\n"):
        if current and len(current) + len(para) + 2 > _CHUNK_CHARS:
            chunks.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current:
        chunks.append(current)
    return chunks


def _normalize(text: str) -> str:
    import re as _re
    return _re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def extract_claims(client: ModelClient, document: str) -> list[Claim]:
    """Extract checkable claims, chunking long documents and removing
    exact duplicates (a repeated claim counted twice would corrupt the
    confidence arithmetic, which counts claims). Malformed entries with
    no text are skipped, never guessed at. If a chunk's extraction fails
    outright the run stops loudly — auditing half a document in silence
    is worse than no audit."""
    raw_claims: list[dict] = []
    for chunk_no, chunk in enumerate(_chunk_document(document), start=1):
        raw = _safe_complete(client, MODEL_EXTRACTION, EXTRACTION_SYSTEM_PROMPT,
                             chunk, json_schema=EXTRACTION_SCHEMA)
        if raw is None:
            raise RuntimeError(
                f"Claim extraction failed on chunk {chunk_no} after two attempts; "
                "the audit would be incomplete, so it does not proceed.")
        raw_claims.extend(json.loads(raw).get("claims", []))

    claims: list[Claim] = []
    seen: set[str] = set()
    for c in raw_claims:
        text = (c.get("text") or "").strip()
        if not text:
            continue
        key = _normalize(text)
        if key in seen:
            continue
        seen.add(key)
        claim = Claim(
            id=len(claims) + 1,
            text=text,
            claim_type=c.get("claim_type", "general"),
            citations=[Citation(raw=x.get("raw", ""), source_title=x.get("source_title", ""),
                                identifier=x.get("identifier", ""), locator=x.get("locator", ""))
                       for x in c.get("citations", []) if isinstance(x, dict)],
            aliases=c.get("aliases", []),
        )
        claim.numbers = c.get("numbers", [])        # type: ignore[attr-defined]
        claim.components = c.get("components", [])  # type: ignore[attr-defined]
        claims.append(claim)
    return claims


# ---------------------------------------------------------------- model checks

_CHECK_RESULT_SCHEMA = {
    "name": "check_result",
    "schema": {
        "type": "object", "additionalProperties": False,
        "properties": {
            "outcome": {"type": "string", "enum": ["pass", "fail", "unsettled"]},
            "note": {"type": "string"},
            "door": {"type": "string"},
            "correction": {"type": "string"},
            "evidence": {
                "type": "array",
                "items": {
                    "type": "object", "additionalProperties": False,
                    "properties": {
                        "source_name": {"type": "string"},
                        "source_class": {"type": "string",
                                         "enum": ["peer_reviewed", "primary_record", "tertiary"]},
                        "detail": {"type": "string"},
                        "reference": {"type": "string"},
                    },
                    "required": ["source_name", "source_class", "detail", "reference"],
                },
            },
        },
        "required": ["outcome", "note", "door", "correction", "evidence"],
    },
    "strict": True,
}


def _parse_check(number: int, name: str, raw: str) -> tuple[CheckResult, str]:
    from model import Evidence, SourceClass
    d = json.loads(raw)
    result = CheckResult(
        check_number=number, check_name=name,
        outcome=CheckOutcome(d["outcome"]), note=d.get("note", ""), door=d.get("door", ""),
        evidence=[Evidence(e["source_name"], SourceClass(e["source_class"]),
                           e["detail"], e.get("reference", ""))
                  for e in d.get("evidence", [])],
    )
    return result, d.get("correction", "")


def _gather(claim: Claim) -> tuple[list[dict], str]:
    """Retrieval pre-pass: resolve the claim's citations against the
    real registries BEFORE the model judges them. Existence is settled
    by Crossref/DataCite, not by a model's memory. Returns the records
    (for the deterministic name check) and the dossier text (for the
    model checks). Failures become 'did not resolve' lines — that IS
    the check 1 evidence."""
    try:
        from retrieve import (doi_lookup, gated_title_records, openalex_cited_by,
                              semanticscholar_citations)
    except Exception:
        return [], ""
    records: list[dict] = []
    lines: list[str] = []
    for cit in claim.citations:
        ident = (cit.identifier or "").strip()
        if ident.lower().startswith(("10.", "doi:", "https://doi.org")):
            rec = doi_lookup(ident)
            if rec:
                records.append(rec)
                lines.append(
                    f"DOI {rec['doi']} RESOLVES: \"{rec['title']}\" — "
                    f"{rec['container']}, {rec['year']}, authors: {', '.join(rec['authors'])}")
                if rec.get("abstract"):
                    lines.append(f"Abstract of record: {rec['abstract'][:600]}")
            else:
                lines.append(f"DOI {ident} DOES NOT RESOLVE in Crossref or DataCite.")
        if cit.source_title:
            # A search hit counts as this citation's record only when
            # the titles genuinely match (code gate). Junk hits are
            # dropped, never handed to the name check or the models.
            hits = gated_title_records(cit.source_title, rows=3)
            for h in hits:
                records.append(h)
                lines.append(
                    f"Title match: \"{h['title']}\" — {h['container']}, {h['year']} "
                    f"(DOI {h['doi'] or 'none'}, match score {h['score']:.0f})")
                if h.get("abstract"):
                    lines.append(f"Abstract of record: {h['abstract'][:600]}")
            if not hits:
                lines.append(f"Title search found NO registry record for \"{cit.source_title}\".")

    # Alias dossier (check 3's teeth): the subject's other names are
    # searched in the same registries, under the same similarity gate.
    # Before this, the alias sweep ran on a model's memory; now it runs
    # on records — which is the whole point of the sweep: the edition
    # hiding under another name is a registry fact, not a recollection.
    if claim.aliases:
        lines.append("")
        lines.append("ALIAS DOSSIER — registry search under the subject's other names "
                     "(ground truth for the alias sweep):")
        for alias in claim.aliases:
            hits = gated_title_records(alias, rows=3)
            for h in hits:
                records.append(h)
                lines.append(
                    f"Under \"{alias}\": \"{h['title']}\" — {h['container']}, {h['year']} "
                    f"(DOI {h['doi'] or 'none'})")
                if h.get("abstract"):
                    lines.append(f"Abstract of record: {h['abstract'][:600]}")
            if not hits:
                lines.append(f"Under \"{alias}\": NO registry record found.")

    # Cited-by dossier (check 5's teeth): two independent citation
    # graphs — OpenAlex and Semantic Scholar — list the later works
    # that cite each resolved source. The secondary sweep now reads
    # real citation graphs instead of asking a model what later
    # scholarship probably said. OpenAlex leads (its count is the
    # record's own figure); Semantic Scholar answers whenever
    # OpenAlex's list cannot be fetched — OpenAlex budgets its free
    # tier by IP address, and from a shared egress IP that budget can
    # be spent by strangers. A graph that could not be reached is
    # named as unreached, never read as empty.
    dois: list[str] = []
    for rec in records:
        d = (rec.get("doi") or "").strip()
        if d and d not in dois:
            dois.append(d)
    if dois:
        lines.append("")
        lines.append("CITED-BY DOSSIER — later works citing the source, from the "
                     "OpenAlex and Semantic Scholar citation graphs "
                     "(ground truth for the secondary sweep):")
        for d in dois[:2]:
            res = openalex_cited_by(d, limit=5)
            list_in_hand = False
            if res is None:
                lines.append(f"DOI {d}: OpenAlex holds no record for this DOI.")
            elif "unavailable" in res:
                lines.append(f"DOI {d}: {res['unavailable']} — that door could not "
                             "be reached this run; nothing is settled by its silence.")
            else:
                w = res["work"]
                lines.append(
                    f"DOI {d} (\"{w['title']}\") is cited by {w['cited_by_count']} work(s) "
                    "in OpenAlex. Most-cited of the later works:")
                for c in res["citing"]:
                    lines.append(
                        f"- \"{c['title']}\" — {c['container']}, {c['year']} "
                        f"(DOI {c['doi'] or 'none'})")
                if res.get("citing_unavailable"):
                    lines.append(f"- ({res['citing_unavailable']} this run; the count "
                                 "above is the record's own figure.)")
                elif not res["citing"]:
                    lines.append("- (OpenAlex lists no citing works.)")
                    list_in_hand = True
                else:
                    list_in_hand = True
            if not list_in_hand:
                s2 = semanticscholar_citations(d, limit=5)
                if s2:
                    lines.append(f"Later works citing DOI {d}, per Semantic Scholar:")
                    for c in s2:
                        lines.append(
                            f"- \"{c['title']}\" — {c['container']}, {c['year']} "
                            f"(DOI {c['doi'] or 'none'})")
                elif s2 == []:
                    lines.append(f"Semantic Scholar lists no citing works for DOI {d}.")
                else:
                    lines.append(f"Semantic Scholar's record for DOI {d} could not "
                                 "be reached this run either.")
    return records, "\n".join(lines)


def _source_dossier(claim: Claim) -> str:
    return _gather(claim)[1]


def run_model_check(client: ModelClient, number: int, claim: Claim,
                    user_files: str = "", dossier: str = "") -> tuple[CheckResult, str]:
    name, mandate = CHECK_PROMPTS[number]
    user = f"CLAIM: {claim.text}\nALIASES: {', '.join(claim.aliases) or '(none listed)'}\n"
    user += "CITATIONS:\n" + ("\n".join(f"- {c.raw}" for c in claim.citations) or "(none)")
    if dossier and number in (1, 2, 3, 5):
        user += f"\n\nSOURCE DOSSIER (registry retrieval — ground truth, gathered before this check ran):\n{dossier}"
    if number == 6:
        user += f"\n\nUSER FILES:\n{user_files or '(none provided)'}"
    model = MODEL_FIDELITY if number == 2 else MODEL_EXTRACTION
    raw = _safe_complete(client, model, f"{mandate}\n\n{SOURCE_STANDARD}\n\nFill EVERY field of the schema; use an empty string when a field does not apply.",
                         user, json_schema=_CHECK_RESULT_SCHEMA)
    if raw is None:
        return _unsettled(number, name, "the model call failed (timeout or API error)"), ""
    return _parse_check(number, name, raw)


def run_adversarial(client: ModelClient, claim: Claim,
                    dossier: str = "") -> tuple[CheckResult, str]:
    """Check 9 — fresh session, debunk mandate (independence rule: it never
    sees the producing session's reasoning; it DOES receive the registry
    dossier, because a kill must land on a named record, not on memory)."""
    fresh = client.fresh()
    system = ADVERSARIAL_SYSTEM_PROMPT.format(standard=SOURCE_STANDARD)
    user = f"CLAIM: {claim.text}\nALIASES: {', '.join(claim.aliases) or '(none listed)'}"
    if dossier:
        user += f"\n\nSOURCE DOSSIER (registry retrieval — gathered before this pass):\n{dossier}"
    raw = _safe_complete(fresh, MODEL_ADVERSARIAL, system, user, json_schema=_CHECK_RESULT_SCHEMA)
    if raw is None:
        return _unsettled(9, "Adversarial pass", "the model call failed (timeout or API error)"), ""
    return _parse_check(9, "Adversarial pass", raw)



def _failed_verdict(claim: Claim, exc: Exception) -> ClaimVerdict:
    """A claim whose audit crashed internally is Held, never lost and
    never silently passed: the run completes, the failure is the door."""
    return ClaimVerdict(
        claim=claim, verdict=Verdict.HELD, checks=[],
        held_reason=(f"The audit of this claim failed internally "
                     f"({type(exc).__name__}: {exc}); it is Held, not settled. "
                     "Re-run the audit to settle it."))

# ---------------------------------------------------------------- checkpointing
# A run must survive the machine it runs on. Findings reach disk after
# every claim, not at the end: if the process is killed — a restart, a
# crash, anything — a resumed run pays only for the claims still
# missing, and the spend ledger (MetaModelClient) already holds what
# the killed run burned. Checkpoint identity is the document's hash:
# a changed document is a different audit and starts fresh.

def _claim_to_dict(claim: Claim) -> dict:
    return {
        "id": claim.id, "text": claim.text, "claim_type": claim.claim_type,
        "aliases": list(claim.aliases),
        "citations": [{"raw": c.raw, "source_title": c.source_title,
                       "identifier": c.identifier, "locator": c.locator}
                      for c in claim.citations],
        "numbers": getattr(claim, "numbers", []),
        "components": getattr(claim, "components", []),
    }


def _claim_from_dict(d: dict) -> Claim:
    claim = Claim(
        id=d["id"], text=d["text"], claim_type=d.get("claim_type", "general"),
        citations=[Citation(raw=x.get("raw", ""), source_title=x.get("source_title", ""),
                            identifier=x.get("identifier", ""), locator=x.get("locator", ""))
                   for x in d.get("citations", [])],
        aliases=d.get("aliases", []))
    claim.numbers = d.get("numbers", [])        # type: ignore[attr-defined]
    claim.components = d.get("components", [])  # type: ignore[attr-defined]
    return claim


def _verdict_to_dict(cv: ClaimVerdict) -> dict:
    from model import Evidence as _Ev  # noqa: F401  (kept for symmetry)
    return {
        "claim": _claim_to_dict(cv.claim),
        "verdict": cv.verdict.value,
        "correction": cv.correction,
        "held_reason": cv.held_reason,
        "checks": [{
            "check_number": ch.check_number, "check_name": ch.check_name,
            "outcome": ch.outcome.value, "note": ch.note, "door": ch.door,
            "evidence": [{"source_name": e.source_name,
                          "source_class": e.source_class.value,
                          "detail": e.detail, "reference": e.reference}
                         for e in ch.evidence],
        } for ch in cv.checks],
    }


def _verdict_from_dict(d: dict) -> ClaimVerdict:
    from model import CheckOutcome as _CO, Evidence as _Ev, SourceClass as _SC, Verdict as _V
    checks = [CheckResult(
        check_number=ch["check_number"], check_name=ch["check_name"],
        outcome=_CO(ch["outcome"]), note=ch.get("note", ""), door=ch.get("door", ""),
        evidence=[_Ev(e["source_name"], _SC(e["source_class"]), e["detail"],
                      e.get("reference", ""))
                  for e in ch.get("evidence", [])])
        for ch in d.get("checks", [])]
    return ClaimVerdict(claim=_claim_from_dict(d["claim"]), verdict=_V(d["verdict"]),
                        checks=checks, correction=d.get("correction", ""),
                        held_reason=d.get("held_reason", ""))


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_checkpoint(path: Path, document: str, title: str, user_files: str):
    """Return (claims, verdicts_by_id, prior_usage) or None. Any doubt —
    wrong document, wrong title, different user files, unreadable file —
    means no checkpoint: a fresh run is always the safe answer."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if (data.get("document_sha256") != _sha(document)
                or data.get("title") != title
                or data.get("user_files_sha256") != _sha(user_files)):
            return None
        claims = [_claim_from_dict(d) for d in data.get("claims", [])]
        verdicts = {int(k): _verdict_from_dict(v)
                    for k, v in (data.get("verdicts") or {}).items()}
        return claims, verdicts, data.get("usage") or {"calls": 0, "tokens": 0}
    except Exception:
        return None


def _save_checkpoint(path: Path, document: str, title: str, user_files: str,
                     claims: list[Claim], verdicts: dict, usage: dict) -> None:
    data = {
        "version": 1,
        "document_sha256": _sha(document),
        "title": title,
        "user_files_sha256": _sha(user_files),
        "claims": [_claim_to_dict(c) for c in claims],
        "verdicts": {str(k): _verdict_to_dict(v) for k, v in verdicts.items()},
        "usage": usage,
        "saved_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    os.replace(tmp, path)

# ---------------------------------------------------------------- orchestration

_GATE_STOPWORDS = {
    "about", "above", "after", "again", "being", "could", "every",
    "first", "found", "given", "other", "their", "there", "these",
    "those", "under", "using", "where", "which", "while", "would",
    "claim", "check", "source", "record", "sources", "records",
}


import re as _re_mod
_QUOTED_SPAN = _re_mod.compile(r'["\u201c][^"\u201d]{8,}["\u201d]|\u00ab[^\u00bb]{8,}\u00bb')


def _significant_tokens(text: str) -> set[str]:
    import re as _re
    return {t for t in _re.findall(r"[a-zà-ÿ]{5,}", (text or "").lower())
            if t not in _GATE_STOPWORDS}


_BOILERPLATE_MARKERS = (
    "illegal activity", "wrongdoing", "cause serious harm",
    "refusal language", "as an ai", "i cannot", "i can't help",
    "content policy", "safety guidelines", "detailed instructions "
    "or guidance",
)


def _accept_correction(claim: Claim, result: CheckResult, correction: str) -> str:
    """Sanity gate v2 for MODEL-supplied corrections. Two screens:
    (1) boilerplate — refusal/policy text a model emitted into the
    wrong seat (one live run 'corrected' a clean book-history claim
    with refusal boilerplate about wrongdoing and illegal activity)
    is dropped whatever else it contains; (2) ground — a correction
    must share a significant token with THE CLAIM IT CORRECTS. The
    pool is the claim text only: v1 also admitted the check's own
    note, and a corrupted note waved its own corruption through.
    Dropped corrections leave the FAIL standing; the verdict then
    resolves as contradicted-but-uncorrected (Held), the honest
    state. Deterministic corrections (checks 7 and 8) are computed
    from the document and never pass through this gate."""
    if not correction:
        return ""
    low = correction.lower()
    if any(marker in low for marker in _BOILERPLATE_MARKERS):
        return ""
    if _significant_tokens(correction) & _significant_tokens(claim.text):
        return correction
    return ""


def audit_claim(client: ModelClient, claim: Claim, user_files: str = "") -> ClaimVerdict:
    checks: list[CheckResult] = []
    corrections: dict[int, str] = {}
    records, dossier = _gather(claim)

    for number in (1, 2, 3, 4, 5, 6):
        # Check 6 (own-files sweep) applies only when the user's own
        # files were actually provided. Run without them, its mandate
        # can only answer UNSETTLED — and an unsettled deciding check
        # would hold EVERY claim on a technicality, including claims
        # fully verified from the record. Applicability is the
        # orchestrator's call, made in code, not a model's mood.
        if number == 6 and not user_files.strip():
            continue
        result, correction = run_model_check(client, number, claim, user_files, dossier)
        if number == 2 and result.outcome in (CheckOutcome.PASS, CheckOutcome.FAIL) \
                and not _QUOTED_SPAN.search(result.note or ""):
            # Quote-or-abstain, enforced: a fidelity verdict that quotes
            # no line of the record never engaged with the record. It is
            # recorded as UNSETTLED, with the unquoted record as the door.
            result = CheckResult(
                check_number=2, check_name=CHECK_PROMPTS[2][0],
                outcome=CheckOutcome.UNSETTLED,
                note=("Fidelity returned a verdict without quoting the line "
                      "of the record that decides the claim; under the "
                      "quote-or-abstain rule the verdict is void."),
                door="The cited source's own record, quoted line in hand")
            correction = ""
        checks.append(result)
        correction = _accept_correction(claim, result, correction)
        if correction:
            corrections[number] = correction

    # Deterministic checks — real code, always. Their findings carry
    # their own corrections (the rebuilt number; the source's spelling).
    numbers = getattr(claim, "numbers", [])
    components = getattr(claim, "components", [])
    if numbers and components:
        det = check_numbers(claim.id, numbers[0], components)
        checks.append(det)
        if det.outcome is CheckOutcome.FAIL:
            corrections[7] = det.note
    for cit in claim.citations:
        if cit.identifier:
            from checks_deterministic import doi_shape_check
            shape = doi_shape_check(cit.identifier)
            if shape is not None:
                checks.append(shape)
    from checks_deterministic import registry_name_check
    name_result = registry_name_check(claim, records)
    if name_result is not None:
        checks.append(name_result)
        if name_result.outcome is CheckOutcome.FAIL:
            corrections[8] = name_result.note

    result, correction = run_adversarial(client, claim, dossier)
    if result.outcome is CheckOutcome.FAIL and not result.evidence:
        # Receipt-bound kills: an adversarial FAIL that names no settling
        # source in its evidence is an assertion, not a kill. It degrades
        # to UNSETTLED — the honest record of an unlanded attack.
        result = CheckResult(
            check_number=9, check_name="Adversarial pass",
            outcome=CheckOutcome.UNSETTLED,
            note=("The adversarial pass asserted a contradiction but named "
                  "no settling source in its evidence; an unnamed kill "
                  "does not land."),
            door="The settling record the attack relied on, named")
        correction = ""
    checks.append(result)
    correction = _accept_correction(claim, result, correction)
    if correction:
        corrections[9] = correction

    return resolve_verdict(claim, checks, corrections)


def audit_document_data(client: ModelClient, document: str, title: str = "Audited document",
                        user_files: str = "", max_workers: int = 4,
                        checkpoint_path=None, on_claim_done=None) -> tuple[str, dict]:
    """Full audit. Claims are independent, so they run in parallel —
    the gauntlet's cost is minutes of wall clock on the audit step,
    never latency inside anyone's generation. Returns the Markdown
    report and the structured findings an agent caller consumes.

    With checkpoint_path set, extraction and every finished claim are
    written to disk as they land; a killed run resumes where it
    stopped and pays only for what is missing."""
    from concurrent.futures import as_completed

    ckpt = Path(checkpoint_path) if checkpoint_path else None
    claims: list[Claim] = []
    verdicts_by_id: dict[int, ClaimVerdict] = {}
    prior_usage = {"calls": 0, "tokens": 0}
    if ckpt is not None and ckpt.exists():
        loaded = _load_checkpoint(ckpt, document, title, user_files)
        if loaded is not None:
            claims, verdicts_by_id, prior_usage = loaded

    def _usage_now() -> dict:
        snap = getattr(client, "usage_snapshot", None)
        now = snap() if callable(snap) else {"api_calls": 0, "api_tokens": 0}
        return {"calls": prior_usage["calls"] + now.get("api_calls", 0),
                "tokens": prior_usage["tokens"] + now.get("api_tokens", 0)}

    if not claims:
        claims = extract_claims(client, document)
        if ckpt is not None:
            _save_checkpoint(ckpt, document, title, user_files,
                             claims, verdicts_by_id, _usage_now())

    todo = [c for c in claims if c.id not in verdicts_by_id]
    if todo:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(audit_claim, client, c, user_files): c for c in todo}
            for fut in as_completed(futures):
                try:
                    cv = fut.result()
                except Exception as exc:  # one claim's crash loses nothing
                    cv = _failed_verdict(futures[fut], exc)
                verdicts_by_id[cv.claim.id] = cv
                if ckpt is not None:
                    _save_checkpoint(ckpt, document, title, user_files,
                                     claims, verdicts_by_id, _usage_now())
                if on_claim_done is not None:
                    on_claim_done(cv)

    verdicts = [verdicts_by_id[c.id] for c in sorted(claims, key=lambda x: x.id)]
    findings = verdicts_to_dict(verdicts, title)
    snapshot = getattr(client, "usage_snapshot", None)
    if callable(snapshot):
        snap = snapshot()
        findings["summary"].update({
            "api_calls": prior_usage["calls"] + snap.get("api_calls", 0),
            "api_tokens": prior_usage["tokens"] + snap.get("api_tokens", 0),
        })

    # Run manifest — provenance for the audit itself. The document's
    # hash names the exact text these verdicts belong to: a changed
    # document is a different audit, and anyone holding the document
    # can recompute the hash and confirm this report is its audit.
    manifest = {
        "program": "9-Point Hallucination Calibration (9 PHC)",
        "document_title": title,
        "document_sha256": _sha(document),
        "audited_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "models": {
            "extraction_and_evidence": MODEL_EXTRACTION,
            "fidelity": MODEL_FIDELITY,
            "adversarial": MODEL_ADVERSARIAL,
        },
        "claims_audited": len(verdicts),
    }
    findings["manifest"] = manifest
    report = render_report(verdicts, title)
    report += (
        "\n---\n\n"
        f"**Run manifest** — document SHA-256: `{manifest['document_sha256']}` · "
        f"models: {MODEL_EXTRACTION} (extraction, evidence), {MODEL_FIDELITY} "
        f"(fidelity), {MODEL_ADVERSARIAL} (adversarial, fresh session) · "
        f"audited at {manifest['audited_at_utc']} · "
        "Recompute the hash over the audited document to confirm this report is its audit."
    )
    if ckpt is not None:
        try:
            ckpt.unlink()  # the run finished; its checkpoint has done its work
        except OSError:
            pass
    return report, findings


def audit_document(client: ModelClient, document: str, title: str = "Audited document",
                   user_files: str = "") -> str:
    report, _ = audit_document_data(client, document, title, user_files)
    return report
