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
import re
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


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\u201c\"*(])")
_DOI_IN_TEXT = re.compile(r"10\.\d{4,9}/[^\s\"'<>\]\)]+")
_QUOTED_TITLE = re.compile(r"[\u201c\"]([^\u201d\"]{8,120})[\u201d\"]")
_ITALIC_TITLE = re.compile(r"\*([^*]{4,120})\*")
_YEAR_IN_TEXT = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")
_CATALOGUE_REF = re.compile(
    r"((?:\d{4}\s+)?(?:[A-Z][A-Za-z&.'-]+\s+){0,3}catalogue\s+No\.?\s*\d+)",
    re.IGNORECASE)


def _parse_sentence_citations(sentence: str) -> list[Citation]:
    """Deterministic citation harvest from one sentence of the audited
    document: quoted and italic titles, DOIs, catalogue references —
    the shapes research prose actually cites in. What is harvested
    feeds the same gated retrieval as model-extracted citations, so a
    span that is not really a source resolves to nothing downstream
    and settles nothing; it only gives the checks a dossier to open."""
    found: list[Citation] = []
    doi_m = _DOI_IN_TEXT.search(sentence)
    year_m = _YEAR_IN_TEXT.search(sentence)
    titles: list[str] = []
    for rx in (_QUOTED_TITLE, _ITALIC_TITLE):
        for m in rx.finditer(sentence):
            t = m.group(1).strip().strip(",;: ")
            if t and t not in titles:
                titles.append(t)
    for t in titles:
        found.append(Citation(
            raw=t, source_title=t,
            identifier=doi_m.group(0) if doi_m else "",
            locator=year_m.group(0) if year_m else ""))
    if not titles and doi_m:
        found.append(Citation(raw=doi_m.group(0), identifier=doi_m.group(0)))
    if not found:
        cat_m = _CATALOGUE_REF.search(sentence)
        if cat_m:
            found.append(Citation(raw=cat_m.group(1).strip()))
    return found


def _reattach_citations(claims: list[Claim], document: str) -> int:
    """Round 3: extraction's citation discipline varies run to run, and
    a citation-less claim's dossier is empty — every deciding check
    abstains and the claim is Held for starvation, not on its merits
    (round-2 live run: most claims carried no citations). The model
    pass is now instructed to attach citations from the claim's
    sentence and the one following; this sweep is the deterministic
    backstop. For each citation-less claim, find the document sentence
    it was drawn from (significant-token overlap), harvest citations
    from that sentence and the next, and attach what is found. Claims
    the model already cited are never touched. Returns how many
    claims gained citations."""
    sentences: list[str] = []
    for para in document.split("\n"):
        para = para.strip()
        if para:
            sentences.extend(s.strip() for s in _SENTENCE_SPLIT.split(para) if s.strip())
    attached = 0
    for claim in claims:
        if claim.citations:
            continue
        claim_tokens = _significant_tokens(claim.text)
        if len(claim_tokens) < 3:
            continue
        best_i, best_score = -1, 0
        for i, sent in enumerate(sentences):
            score = len(claim_tokens & _significant_tokens(sent))
            if score > best_score:
                best_i, best_score = i, score
        if best_i < 0 or best_score < 3:
            continue
        harvested: list[Citation] = []
        for j in (best_i, best_i + 1):
            if j < len(sentences):
                harvested.extend(_parse_sentence_citations(sentences[j]))
        seen_keys: set[tuple[str, str]] = set()
        for cit in harvested:
            key = (cit.source_title.lower(), cit.identifier.lower())
            if key not in seen_keys:
                seen_keys.add(key)
                claim.citations.append(cit)
        if claim.citations:
            attached += 1
    return attached


def extract_claims(client: ModelClient, document: str) -> list[Claim]:
    """Extract checkable claims, chunking long documents, running two
    extraction passes per chunk and union-merging them (a repeated
    claim counted twice would corrupt the confidence arithmetic, which
    counts claims; two passes blunt the run-to-run variance of either
    one alone). Malformed entries with no text are skipped, never
    guessed at. If both passes on a chunk fail outright the run stops
    loudly — auditing half a document in silence is worse than no
    audit."""
    raw_claims: list[dict] = []
    for chunk_no, chunk in enumerate(_chunk_document(document), start=1):
        # Round 5: extraction runs TWICE per chunk and the passes are
        # unioned below. Extraction is the run's ceiling — across the
        # live runs it swung 18/16/16/14 claims, with citation
        # attachment swinging with it — and it is a small share of the
        # run's cost. Two independent passes over the same text,
        # merged, hand the checks the fuller claim set every time. One
        # successful pass is a complete extraction; both failing stops
        # the run loudly, as a failed extraction always has.
        passes: list[str] = []
        for _ in range(2):
            raw = _safe_complete(client, MODEL_EXTRACTION,
                                 EXTRACTION_SYSTEM_PROMPT, chunk,
                                 json_schema=EXTRACTION_SCHEMA)
            if raw is not None:
                passes.append(raw)
        if not passes:
            raise RuntimeError(
                f"Claim extraction failed on chunk {chunk_no} on both "
                "extraction passes; the audit would be incomplete, so "
                "it does not proceed.")
        for raw in passes:
            raw_claims.extend(json.loads(raw).get("claims", []))

    claims: list[Claim] = []
    by_key: dict[str, Claim] = {}
    for c in raw_claims:
        text = (c.get("text") or "").strip()
        if not text:
            continue
        key = _normalize(text)
        new_citations = [
            Citation(raw=x.get("raw", ""), source_title=x.get("source_title", ""),
                     identifier=x.get("identifier", ""), locator=x.get("locator", ""))
            for x in c.get("citations", []) if isinstance(x, dict)]
        existing = by_key.get(key)
        if existing is not None:
            # Union merge: a claim found by both passes keeps every
            # citation and alias either pass attached. Numbers and
            # components fill only when empty — the parts of a sum are
            # one reading of the text, never a blend of two readings.
            have = {(x.source_title.lower(), x.identifier.lower(),
                     x.raw.lower()) for x in existing.citations}
            for cit in new_citations:
                k = (cit.source_title.lower(), cit.identifier.lower(),
                     cit.raw.lower())
                if k not in have:
                    existing.citations.append(cit)
                    have.add(k)
            for a in c.get("aliases", []):
                if a not in existing.aliases:
                    existing.aliases.append(a)
            if not getattr(existing, "numbers", []) and c.get("numbers"):
                existing.numbers = c["numbers"]              # type: ignore[attr-defined]
            if not getattr(existing, "components", []) and c.get("components"):
                existing.components = c["components"]        # type: ignore[attr-defined]
            continue
        claim = Claim(
            id=len(claims) + 1,
            text=text,
            claim_type=c.get("claim_type", "general"),
            citations=new_citations,
            aliases=c.get("aliases", []),
        )
        claim.numbers = c.get("numbers", [])        # type: ignore[attr-defined]
        claim.components = c.get("components", [])  # type: ignore[attr-defined]
        by_key[key] = claim
        claims.append(claim)
    _reattach_citations(claims, document)
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

    # Dossier enrichment: a record with no abstract gives the fidelity
    # check nothing it may quote, so it must abstain even when the book
    # is real and catalogued (proven live, 2026-10-26 probes 1-2). When
    # a record resolves abstract-less, pull its catalogue description
    # from Open Library (gated there like every record here) and put it
    # in the dossier, labelled with its source. Cached per title — the
    # alias sweep often re-resolves the same work.
    enrich_cache: dict[str, str] = {}

    def _enrich(rec: dict) -> None:
        if rec.get("abstract"):
            return
        key = (rec.get("title") or "").strip().lower()
        if not key:
            return
        if key not in enrich_cache:
            try:
                from retrieve import catalogue_description
                enrich_cache[key] = catalogue_description(
                    rec["title"], rec.get("authors") or [])
            except Exception:
                enrich_cache[key] = ""
        text = enrich_cache[key]
        if text:
            rec["catalogue_note"] = text
            lines.append(
                f"Catalogue description (Open Library) for "
                f"\"{rec['title']}\": {text}")

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
                _enrich(rec)
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
                _enrich(h)
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
                _enrich(h)
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
    # Gate v3 — an additive restatement is not a correction. The
    # round-3 live run 'corrected' the true claim "The Hypnerotomachia
    # Poliphili was published in 1499" into the same statement with
    # "first (printed) by Aldus Manutius" added: every significant
    # token of the claim carried over, nothing was negated, nothing
    # was replaced — the claim was embellished, not contradicted. A
    # correction that keeps (all but at most one of) the claim's own
    # tokens and contains no negation or contradiction marker is a
    # restatement; it is dropped, and the FAIL resolves as
    # contradicted-but-uncorrected. Real corrections negate, strike,
    # or replace — each of the run's genuine corrections carries such
    # a marker or sheds the claim's tokens, and passes.
    claim_tokens = _significant_tokens(claim.text)
    corr_tokens = _significant_tokens(correction)
    if claim_tokens and len(claim_tokens - corr_tokens) <= 1 \
            and not any(m in low for m in _NEGATION_MARKERS):
        return ""
    if corr_tokens & claim_tokens:
        return correction
    return ""


_NEGATION_MARKERS = (
    "not ", "n't", "never", "strike", "wrong", "incorrect", "in fact",
    "actually", "rather than", "instead", "does not", "did not",
    "cannot", "no longer", "false", "nonexistent", "no such",
)


def _adversarial_note_floor(result: CheckResult) -> CheckResult:
    """Round 3: an adversarial FAIL must show its work in its note. The
    round-2 live run printed a 'correction' that was a sentence fragment
    ("Only specialists read it in translation.") off a FAIL whose note
    was the 9-character string "at-check9" — a degenerate output the
    receipt rule could not catch, because evidence WAS attached; the
    reasoning itself was empty. A FAIL whose note is very short AND
    names no year and quotes no line of the record has not shown its
    work, whatever its evidence list holds: it degrades to UNSETTLED.
    A terse note that names a year or quotes the record stands — the
    floor judges emptiness, not brevity."""
    if result.outcome is not CheckOutcome.FAIL:
        return result
    note = (result.note or "").strip()
    if len(note) >= 40 or _YEAR_IN_TEXT.search(note) or _QUOTED_SPAN.search(note):
        # A FAIL whose own note concedes the record in hand is silent
        # on the claim — and names no year and quotes no line in its
        # place — has described an absence, not landed a kill. The
        # round-3 specimen failed a true publication claim while
        # conceding "the source dossier attached to the claim itself
        # is silent on the claim"; a concession is not a contradiction.
        low = note.lower()
        if any(m in low for m in _SILENCE_CONCESSIONS) \
                and not _YEAR_IN_TEXT.search(note) \
                and not _QUOTED_SPAN.search(note):
            return CheckResult(
                check_number=9, check_name="Adversarial pass",
                outcome=CheckOutcome.UNSETTLED,
                note=("The adversarial pass returned FAIL while conceding "
                      "its record does not speak to the claim, and named no "
                      "contradicting record in its place; a concession is "
                      "not a kill."),
                door="The contradicting record, named or quoted")
        return result
    return CheckResult(
        check_number=9, check_name="Adversarial pass",
        outcome=CheckOutcome.UNSETTLED,
        note=(f"The adversarial pass returned FAIL with a degenerate note "
              f"({len(note)} characters, no year named, no line of the record "
              "quoted); a kill that does not show its work in its reasoning "
              "does not land."),
        door="The adversarial pass's reasoning, stated in full")


_SILENCE_CONCESSIONS = (
    "silent on the claim", "silent on this claim",
    "does not speak to the claim", "no line in the record speaks to",
    "record is silent on the claim",
)


_CITATION_SURNAME_STOPWORDS = {
    "journal", "press", "review", "studies", "history", "books", "book",
    "early", "modern", "volume", "quarterly", "annual", "proceedings",
    "transactions", "bulletin", "magazine", "catalogue", "library",
}


def _citation_keys(cit: Citation) -> tuple[set[str], set[str]]:
    """(surname tokens, title tokens) identifying a citation in prose.
    Surnames: capitalized tokens in the raw citation that are not part
    of its title and not publication furniture (Journal, Press, ...)."""
    title_tokens = _significant_tokens(cit.source_title or "")
    surnames: set[str] = set()
    for tok in re.findall(r"[A-Z][a-zà-ÿ]{3,}", cit.raw or ""):
        low = tok.lower()
        if low not in _CITATION_SURNAME_STOPWORDS and low not in title_tokens:
            surnames.add(low)
    return surnames, title_tokens


def _claim_leans_on(claim: Claim, cit: Citation) -> bool:
    """A claim leans on a citation when its own text names the cited
    author or the cited work — the extraction rule has always made the
    attribution part of such a claim. A citation attached from a
    neighboring sentence (the round-3 attachment rule) that the claim
    never names is furniture, not a load-bearing source."""
    surnames, title_tokens = _citation_keys(cit)
    claim_tokens = set(_normalize(claim.text).split())
    if surnames & claim_tokens:
        return True
    return len(title_tokens & _significant_tokens(claim.text)) >= 2


def _existence_binding(claim: Claim, result: CheckResult) -> CheckResult:
    """Round 4: check 1 may fail a claim over a dead citation only when
    the claim leans on it. The round-3 live run attached the invented
    Castellan citation to four neighboring claims that never name him;
    check 1 failed all four on its non-existence and they were Held
    for a citation they never made. When the condemned citation is
    identifiable in the FAIL's own note/evidence and the claim leans
    on none of the condemned citations, the FAIL degrades to
    UNSETTLED: the dead citation is recorded on the claim, and settles
    nothing about it. An unattributable FAIL stands as returned —
    the binding never voids what it cannot attribute."""
    if result.check_number != 1 or result.outcome is not CheckOutcome.FAIL:
        return result
    if not claim.citations:
        return result
    blob = _normalize((result.note or "") + " " + " ".join(
        e.detail + " " + e.source_name for e in result.evidence))
    blob_tokens = set(blob.split())
    condemned: list[Citation] = []
    for cit in claim.citations:
        surnames, title_tokens = _citation_keys(cit)
        if surnames & blob_tokens or \
                len(title_tokens & _significant_tokens(blob)) >= 2:
            condemned.append(cit)
    if not condemned or any(_claim_leans_on(claim, c) for c in condemned):
        return result
    dead = condemned[0]
    return CheckResult(
        check_number=1, check_name=result.check_name,
        outcome=CheckOutcome.UNSETTLED,
        note=(f"Check 1 established that the attached citation "
              f"\"{(dead.raw or dead.source_title)[:80]}\" does not resolve. "
              "The claim's text does not lean on that citation — it names "
              "neither its author nor its work — so the claim is not failed "
              "for it. The dead citation stands recorded; it settles "
              "nothing about this claim."),
        door="A source this claim actually leans on, examined directly")


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
        if number == 1:
            result = _existence_binding(claim, result)
            if result.outcome is not CheckOutcome.FAIL:
                correction = ""
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
    result = _adversarial_note_floor(result)
    if result.outcome is not CheckOutcome.FAIL:
        correction = ""
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
