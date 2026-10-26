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

_UA = {"User-Agent": "9PHC-audit/0.1 (source retrieval for fact audit)"}

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
