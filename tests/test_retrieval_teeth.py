"""Retrieval teeth — offline tests for the alias dossier (check 3) and
the OpenAlex cited-by dossier (check 5). Network functions are patched
with canned payloads: these tests prove the parsing, the similarity
gate, and the dossier wiring. They never touch the network.
Run: python3 tests/test_retrieval_teeth.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import retrieve
from retrieve import (gated_title_records, parse_openalex_cited_by,
                      parse_openalex_work, parse_semanticscholar_citations)
from model import Citation, Claim
import audit

# ---- OpenAlex parse: work record
work_payload = {
    "id": "https://openalex.org/W123456",
    "display_name": "The Coming of the Book",
    "doi": "https://doi.org/10.1017/CBO9780511519369",
    "cited_by_count": 342,
    "publication_year": 1976,
}
w = parse_openalex_work(work_payload)
assert w == {"openalex_id": "W123456", "title": "The Coming of the Book",
             "doi": "10.1017/CBO9780511519369", "cited_by_count": 342,
             "year": 1976}, w
assert parse_openalex_work({}) is None
assert parse_openalex_work(None) is None
assert parse_openalex_work({"display_name": "no id"}) is None

# ---- OpenAlex parse: cited-by listing
citing_payload = {"results": [
    {"display_name": "Print Culture Revisited", "publication_year": 2003,
     "doi": "https://doi.org/10.1000/xyz123", "cited_by_count": 41,
     "authorships": [{"author": {"display_name": n}} for n in
                     ("A One", "B Two", "C Three", "D Four")],
     "primary_location": {"source": {"display_name": "Book History"}}},
    {"display_name": "A Later Note", "publication_year": 2011,
     "doi": None, "cited_by_count": 2, "authorships": [],
     "primary_location": None},
]}
citing = parse_openalex_cited_by(citing_payload)
assert len(citing) == 2, citing
assert citing[0]["title"] == "Print Culture Revisited"
assert citing[0]["authors"] == ["A One", "B Two", "C Three"]  # capped at 3
assert citing[0]["doi"] == "10.1000/xyz123"                   # prefix stripped
assert citing[0]["container"] == "Book History"
assert citing[1]["doi"] == "" and citing[1]["container"] == ""
assert parse_openalex_cited_by({}) == []
assert parse_openalex_cited_by(None) == []

# ---- Semantic Scholar parse (the second citation graph)
s2_payload = {"data": [
    {"citingPaper": {"title": "Graph Methods in Bibliometrics", "year": 2020,
                     "venue": "Scientometrics",
                     "externalIds": {"DOI": "10.1007/s11192-020-0000"},
                     "authors": [{"name": "E Five"}, {"name": "F Six"},
                                 {"name": "G Seven"}, {"name": "H Eight"}]}},
    {"citingPaper": {"title": "An Untitled Note", "year": None,
                     "venue": "", "externalIds": {}, "authors": []}},
]}
s2 = parse_semanticscholar_citations(s2_payload)
assert len(s2) == 2, s2
assert s2[0]["authors"] == ["E Five", "F Six", "G Seven"]  # capped at 3
assert s2[0]["doi"] == "10.1007/s11192-020-0000"
assert s2[0]["container"] == "Scientometrics"
assert s2[1]["title"] == "An Untitled Note" and s2[1]["doi"] == ""
assert parse_semanticscholar_citations({}) == []
assert parse_semanticscholar_citations(None) == []

# ---- The similarity gate on the shared title path
real = {"doi": "10.1/real", "title": "The Coming of the Book",
        "authors": ["Lucien Febvre", "Henri-Jean Martin"],
        "container": "Verso", "year": 1976, "score": 98.0}
junk = {"doi": "10.1/junk", "title": "Book Review: The Coming Plague",
        "authors": ["Someone Else"], "container": "A Journal",
        "year": 1995, "score": 40.0}
orig_ts, orig_ol = retrieve.title_search, retrieve.openlibrary_title_search
try:
    retrieve.title_search = lambda title, rows=3: [junk, real]
    hits = gated_title_records("The Coming of the Book")
    assert [h["doi"] for h in hits] == ["10.1/real"], hits  # junk gated out

    retrieve.title_search = lambda title, rows=3: []
    retrieve.openlibrary_title_search = lambda title, rows=3: [
        {"doi": "", "title": "The Coming of the Book",
         "authors": ["Lucien Febvre"], "container": "Open Library",
         "year": 1976, "score": 100.0}]
    hits = gated_title_records("The Coming of the Book")
    assert len(hits) == 1 and hits[0]["container"] == "Open Library", hits
finally:
    retrieve.title_search, retrieve.openlibrary_title_search = orig_ts, orig_ol

# ---- Dossier wiring: alias + cited-by sections reach the claim
orig_gtr, orig_cb = retrieve.gated_title_records, retrieve.openalex_cited_by
orig_doi = retrieve.doi_lookup
orig_s2 = retrieve.semanticscholar_citations
try:
    retrieve.semanticscholar_citations = lambda doi, limit=5: [
        {"title": "Graph Methods in Bibliometrics", "year": 2020,
         "doi": "10.1007/s11192-020-0000", "authors": ["E Five"],
         "container": "Scientometrics"}]
    retrieve.doi_lookup = lambda doi: {
        "doi": "10.1/real", "title": "The Coming of the Book",
        "authors": ["Lucien Febvre"], "container": "Verso", "year": 1976,
        "type": "book", "abstract": ""}
    retrieve.gated_title_records = lambda title, rows=3: [real] \
        if "Coming" in title else []
    retrieve.openalex_cited_by = lambda doi, limit=5: {
        "work": {"openalex_id": "W1", "title": "The Coming of the Book",
                 "doi": "10.1/real", "cited_by_count": 342, "year": 1976},
        "citing": [{"title": "Print Culture Revisited", "year": 2003,
                    "doi": "10.1000/xyz123", "authors": ["A One"],
                    "container": "Book History", "cited_by_count": 41}]}
    claim = Claim(
        id=1, text="The book was never translated into English.",
        citations=[Citation(raw="Febvre & Martin 1958",
                            source_title="The Coming of the Book",
                            identifier="10.1/real")],
        aliases=["L'apparition du livre"])
    records, dossier = audit._gather(claim)
    assert "ALIAS DOSSIER" in dossier, dossier
    assert "L'apparition du livre" in dossier, dossier
    assert "CITED-BY DOSSIER" in dossier, dossier
    assert "Print Culture Revisited" in dossier, dossier
    assert "cited by 342" in dossier, dossier
    assert any(r["doi"] == "10.1/real" for r in records), records

    # OpenAlex holds no record for a DOI: the dossier says so — and
    # the second graph answers in its place.
    retrieve.openalex_cited_by = lambda doi, limit=5: None
    _, dossier2 = audit._gather(claim)
    assert "OpenAlex holds no record" in dossier2, dossier2
    assert "per Semantic Scholar" in dossier2, dossier2
    assert "Graph Methods in Bibliometrics" in dossier2, dossier2

    # The lookup itself failed (rate limit): the dossier must NOT read
    # that as absence — it names the unreached door instead.
    retrieve.openalex_cited_by = lambda doi, limit=5: {
        "unavailable": "OpenAlex work lookup failed (HTTP 429)"}
    _, dossier3 = audit._gather(claim)
    assert "could not be reached" in dossier3, dossier3
    assert "OpenAlex holds no record" not in dossier3, dossier3
finally:
    retrieve.gated_title_records = orig_gtr
    retrieve.openalex_cited_by = orig_cb
    retrieve.doi_lookup = orig_doi
    retrieve.semanticscholar_citations = orig_s2

print("retrieval teeth: alias dossier + cited-by dossier parse, gate, and wire correctly")
