"""9 PHC — source retrieval.

The model checks must open sources, not remember them. This module is
the retrieval layer: resolve a DOI through Crossref (free, no key),
fetch a page and pull its readable text, and classify what came back
against the source standard (peer-reviewed / primary record / tertiary).

Retrieval failure is a first-class result: it routes the claim to
Held with the door named, upstream in the engine.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request

_UA = {"User-Agent": "9PHC-audit/0.1 (source retrieval for fact audit; "
                     "mailto:richardvigslist@nuviratechnologies.io)"}
_MAILTO = "richardvigslist@nuviratechnologies.io"

TERTIARY_HOSTS = ("wikipedia.org", "wikipedia.com", "fandom.com", "reddit.com")


def classify_host(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower()
    if any(h in host for h in TERTIARY_HOSTS):
        return "tertiary"
    if host.endswith(".gov") or host.endswith(".edu") or "crossref" in host:
        return "primary_record"
    return "unknown"


def fetch_text(url: str, limit: int = 20000) -> str:
    """Fetch a URL and return stripped readable text (best effort)."""
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8", "replace")
    text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", raw)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _clean_abstract(raw: str) -> str:
    """Crossref abstracts arrive as JATS XML. Strip the tags; the plain
    text is fidelity material for check 2 — the source's own words,
    not just its metadata."""
    text = re.sub(r"<[^>]+>", " ", raw or "")
    return re.sub(r"\s+", " ", text).strip()


def _datacite_lookup(cleaned: str) -> dict | None:
    url = "https://api.datacite.org/dois/" + urllib.parse.quote(cleaned, safe="")
    req = urllib.request.Request(url, headers=_UA)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            attrs = json.loads(resp.read())["data"]["attributes"]
    except Exception:
        return None
    creators = [c.get("name", "") for c in attrs.get("creators", [])]
    return {
        "doi": attrs.get("doi", cleaned),
        "title": (attrs.get("titles") or [{}])[0].get("title", ""),
        "authors": creators,
        "container": (attrs.get("publisher") or ""),
        "year": attrs.get("publicationYear"),
        "type": (attrs.get("types") or {}).get("resourceTypeGeneral", ""),
    }


def doi_lookup(doi: str) -> dict | None:
    """Resolve a DOI through Crossref, falling back to DataCite
    (Zenodo and many repositories register there, not Crossref).
    Returns title/authors/container or None when the DOI does not
    resolve anywhere (check 1 evidence)."""
    cleaned = doi.strip().removeprefix("https://doi.org/").removeprefix("doi:")
    url = "https://api.crossref.org/works/" + urllib.parse.quote(cleaned, safe="")
    req = urllib.request.Request(url, headers=_UA)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            msg = json.loads(resp.read())["message"]
    except Exception:
        return _datacite_lookup(cleaned)
    return {
        "doi": msg.get("DOI", cleaned),
        "title": (msg.get("title") or [""])[0],
        "authors": [" ".join(filter(None, [a.get("given", ""), a.get("family", "")]))
                    for a in msg.get("author", [])],
        "container": (msg.get("container-title") or [""])[0],
        "year": (msg.get("issued", {}).get("date-parts") or [[None]])[0][0],
        "type": msg.get("type", ""),
        "abstract": _clean_abstract(msg.get("abstract", "")),
    }


def title_search(title: str, rows: int = 3) -> list[dict]:
    """Search Crossref by title — the existence sweep's first pass for
    citations that carry no DOI."""
    q = urllib.parse.urlencode({"query.title": title, "rows": rows})
    req = urllib.request.Request(f"https://api.crossref.org/works?{q}", headers=_UA)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            items = json.loads(resp.read())["message"]["items"]
    except Exception:
        return []
    out = []
    for it in items:
        out.append({
            "doi": it.get("DOI", ""),
            "title": (it.get("title") or [""])[0],
            "authors": [" ".join(filter(None, [a.get("given", ""), a.get("family", "")]))
                        for a in it.get("author", [])],
            "container": (it.get("container-title") or [""])[0],
            "year": (it.get("issued", {}).get("date-parts") or [[None]])[0][0],
            "score": it.get("score", 0),
            "abstract": _clean_abstract(it.get("abstract", "")),
        })
    return out


def title_similarity(a: str, b: str) -> float:
    """Token-overlap (Jaccard) between two titles, normalized. A search
    hit is only the cited source's record if the titles actually match —
    Crossref's free-text ranking returns 'Book Review: The Coming
    Christ' for 'The Coming of the Book', and a junk record fed to the
    name check could manufacture a false correction. Similarity is the
    gate, in code, not a model's guess. Titles are compared by their
    core (the part before a subtitle colon), so a real record carrying
    a long subtitle still matches its citation."""
    def toks(s: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]+", s.lower())) - {"the", "a", "an", "of"}

    def core(s: str) -> str:
        return re.split(r"[:—–]| - ", s, maxsplit=1)[0]

    def norm(s: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", s.lower()))

    def jac(x: set[str], y: set[str]) -> float:
        if not x or not y:
            return 0.0
        return len(x & y) / len(x | y)

    # Prefix containment: a citation's title that opens the record's
    # full title (subtitle and all) is the same work — 'The Coming of
    # the Book' opens 'The Coming of the Book: The Impact of Printing…'.
    # Junk rankings share scattered words but never that opening.
    na, nb = norm(core(a)), norm(b)
    if na and nb and (nb.startswith(na) or na.startswith(norm(core(b)))):
        return 1.0
    return jac(toks(core(a)), toks(core(b)))


def gated_title_records(title: str, rows: int = 3) -> list[dict]:
    """The one gated path from a title to registry records: Crossref
    first, Open Library when Crossref has nothing that matches — and a
    hit counts only when its title genuinely matches the query (the
    similarity gate, in code). Used for citation titles AND for the
    alias sweep, so both live under the same standard."""
    hits = [h for h in title_search(title, rows=rows)
            if title_similarity(title, h["title"]) >= 0.5]
    if not hits:
        hits = [h for h in openlibrary_title_search(title, rows=rows)
                if title_similarity(title, h["title"]) >= 0.5]
    return hits


# ---------------------------------------------------------------- OpenAlex
# OpenAlex is the cited-by index: free, no key, and it answers the one
# question Crossref cannot — who cited this work later. That is the
# secondary sweep's raw material (check 5), fetched as records, not
# recalled by a model.

def parse_openalex_work(payload: dict) -> dict | None:
    """Pure parse of an OpenAlex work record (offline-testable)."""
    if not isinstance(payload, dict) or not payload.get("id"):
        return None
    doi = (payload.get("doi") or "").removeprefix("https://doi.org/")
    return {
        "openalex_id": payload["id"].rsplit("/", 1)[-1],
        "title": payload.get("display_name", ""),
        "doi": doi,
        "cited_by_count": payload.get("cited_by_count", 0),
        "year": payload.get("publication_year"),
    }


def _openalex_brief(payload: dict) -> dict:
    authors = [a.get("author", {}).get("display_name", "")
               for a in payload.get("authorships", [])][:3]
    source = ((payload.get("primary_location") or {}).get("source") or {})
    return {
        "title": payload.get("display_name", ""),
        "year": payload.get("publication_year"),
        "doi": (payload.get("doi") or "").removeprefix("https://doi.org/"),
        "authors": authors,
        "container": source.get("display_name", ""),
        "cited_by_count": payload.get("cited_by_count", 0),
    }


def parse_openalex_cited_by(payload: dict) -> list[dict]:
    """Pure parse of an OpenAlex cited-by listing (offline-testable)."""
    if not isinstance(payload, dict):
        return []
    return [_openalex_brief(w) for w in payload.get("results", [])
            if isinstance(w, dict)]


import threading as _threading
import time as _time

_OPENALEX_LOCK = _threading.Lock()
_OPENALEX_LAST = [0.0]
_OPENALEX_MIN_GAP = 0.4  # seconds between OpenAlex calls, process-wide


def _openalex_get(url: str) -> dict:
    """One OpenAlex GET, in the polite pool (mailto), serialized and
    spaced process-wide, with a single retry on a transient failure.
    OpenAlex rate-limits bursts hard — and this program calls it from
    parallel claim threads, which IS a burst. A 429 in the first build
    test masqueraded as 'no record exists', a false finding; the
    spacing, the retry, and the honest error paths exist because of it."""
    last_exc: Exception | None = None
    for attempt in range(2):
        with _OPENALEX_LOCK:
            wait = _OPENALEX_MIN_GAP - (_time.monotonic() - _OPENALEX_LAST[0])
            if wait > 0:
                _time.sleep(wait)
            try:
                req = urllib.request.Request(url, headers=_UA)
                with urllib.request.urlopen(req, timeout=30) as resp:
                    payload = json.loads(resp.read())
                _OPENALEX_LAST[0] = _time.monotonic()
                return payload
            except Exception as exc:  # noqa: BLE001 — classified by the caller
                _OPENALEX_LAST[0] = _time.monotonic()
                pass  # retried above; silence settles nothing
        if attempt == 0:
            _time.sleep(1.5)
    raise last_exc  # type: ignore[misc]


def openalex_cited_by(doi: str, limit: int = 5) -> dict | None:
    """Resolve a DOI in OpenAlex and fetch the works that cite it,
    most-cited first. Three honest outcomes, never an exception:
    - {'work': ..., 'citing': [...]} — the citation graph, as recorded.
    - None — OpenAlex holds no record for this DOI (a 404: a finding).
    - {'unavailable': reason} — the lookup itself failed (rate limit,
      network). NOT a finding: the dossier must say the door could not
      be reached, never that nothing stands behind it."""
    cleaned = doi.strip().removeprefix("https://doi.org/").removeprefix("doi:")
    if not cleaned:
        return None
    try:
        payload = _openalex_get(
            "https://api.openalex.org/works/doi:"
            + urllib.parse.quote(cleaned, safe="")
            + "?" + urllib.parse.urlencode({"mailto": _MAILTO}))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        return {"unavailable": f"OpenAlex work lookup failed (HTTP {exc.code})"}
    except Exception as exc:  # noqa: BLE001
        return {"unavailable": f"OpenAlex work lookup failed ({type(exc).__name__})"}
    work = parse_openalex_work(payload)
    if work is None:
        return None
    try:
        q = urllib.parse.urlencode({
            "filter": f"cites:{work['openalex_id']}",
            "sort": "cited_by_count:desc", "per-page": limit,
            "mailto": _MAILTO})
        citing = parse_openalex_cited_by(
            _openalex_get(f"https://api.openalex.org/works?{q}"))
    except Exception as exc:  # noqa: BLE001
        # The work record itself resolved — its citation COUNT is
        # already ground truth. Report the count and name the list as
        # the unreached part, instead of throwing the record away.
        return {"work": work, "citing": [],
                "citing_unavailable":
                    f"the citing-works list could not be fetched ({type(exc).__name__})"}
    return {"work": work, "citing": citing}


def parse_semanticscholar_citations(payload: dict) -> list[dict]:
    """Pure parse of a Semantic Scholar citations listing
    (offline-testable)."""
    if not isinstance(payload, dict):
        return []
    out = []
    for entry in payload.get("data", []):
        paper = (entry or {}).get("citingPaper") or {}
        ext = paper.get("externalIds") or {}
        out.append({
            "title": paper.get("title", ""),
            "year": paper.get("year"),
            "doi": ext.get("DOI", ""),
            "authors": [a.get("name", "") for a in paper.get("authors", [])][:3],
            "container": paper.get("venue", ""),
        })
    return out


def semanticscholar_citations(doi: str, limit: int = 5) -> list[dict] | None:
    """The second citation graph: Semantic Scholar's record of the
    works citing a DOI. Free, no key. It exists in this program
    because OpenAlex's free tier budgets by IP address — from a shared
    egress IP its list calls can be exhausted by strangers while its
    single-work lookups still answer. Two independent graphs mean one
    budget wall never silences the secondary sweep. Returns the citing
    works, [] when the paper is known but uncited, or None when the
    graph holds no record / the call failed (the dossier says which
    doors were tried; it never merges the two into a blur)."""
    cleaned = doi.strip().removeprefix("https://doi.org/").removeprefix("doi:")
    if not cleaned:
        return None
    q = urllib.parse.urlencode({
        "fields": "title,year,venue,externalIds,authors", "limit": limit})
    url = ("https://api.semanticscholar.org/graph/v1/paper/DOI:"
           + urllib.parse.quote(cleaned, safe="") + f"/citations?{q}")
    # Semantic Scholar's keyless tier is a rate, not a daily budget —
    # its own 429 says 'wait and try again'. So: space the calls
    # process-wide and retry with backoff. A 404 is different (the
    # graph holds no such paper) and returns at once.
    for attempt in range(3):
        with _OPENALEX_LOCK:  # one shared registry-spacing lock
            wait = 0.5 - (_time.monotonic() - _OPENALEX_LAST[0])
            if wait > 0:
                _time.sleep(wait)
            try:
                req = urllib.request.Request(url, headers=_UA)
                with urllib.request.urlopen(req, timeout=30) as resp:
                    payload = json.loads(resp.read())
                _OPENALEX_LAST[0] = _time.monotonic()
                return parse_semanticscholar_citations(payload)
            except urllib.error.HTTPError as exc:
                _OPENALEX_LAST[0] = _time.monotonic()
                if exc.code == 404:
                    return None
                pass  # retried above; silence settles nothing
            except Exception as exc:  # noqa: BLE001
                _OPENALEX_LAST[0] = _time.monotonic()
                pass  # retried above; silence settles nothing
        if attempt < 2:
            _time.sleep(3 * (attempt + 1))
    return None


def openlibrary_title_search(title: str, rows: int = 3) -> list[dict]:
    """Open Library title search — the book-shaped complement to
    Crossref, whose index is journal-heavy and often misses the book
    itself. Free, no key."""
    q = urllib.parse.urlencode({"title": title, "limit": rows,
                                "fields": "title,author_name,first_publish_year,key"})
    req = urllib.request.Request(f"https://openlibrary.org/search.json?{q}", headers=_UA)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            docs = json.loads(resp.read()).get("docs", [])
    except Exception:
        return []
    out = []
    for d in docs:
        out.append({
            "doi": "",
            "title": d.get("title", ""),
            "authors": d.get("author_name", []),
            "container": "Open Library",
            "year": d.get("first_publish_year"),
            "score": title_similarity(title, d.get("title", "")) * 100,
        })
    return out
