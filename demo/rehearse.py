#!/usr/bin/env python3
"""9 PHC — REHEARSAL driver. Zero spend.

A scripted client plays the part of a competent model: it returns the
demo briefs' claims and the check outcomes a good run SHOULD produce.
The pipeline, verdict engine, deterministic checks (7 and 8 run for
real, including the Crossref/DataCite registry lookup behind the
Fevre/Febvre letter check), report renderer, and scorer all run for
real. What this proves is the plumbing: that IF the models do their
jobs, the program catches what it is built to catch and says so
correctly. It does NOT prove the models will do their jobs — that is
what the live baseline run is for.

Outputs are named *.rehearsal.* so a rehearsal artifact can never be
mistaken for a live result.

Usage: python3 demo/rehearse.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from audit import audit_document_data  # noqa: E402

RECEIPT = [{"source_name": "Rehearsal receipt (scripted peer-reviewed stand-in)",
            "source_class": "peer_reviewed",
            "detail": "Scripted: supports the claim as written.",
            "reference": "rehearsal"}]


def _res(outcome, note="", door="", correction="", evidence=None):
    return json.dumps({"outcome": outcome, "note": note, "door": door,
                       "correction": correction,
                       "evidence": RECEIPT if evidence is None else evidence})


PASS = _res("pass", "Scripted pass: the record supports the claim.")


def _claim(text, citations=None, aliases=None, numbers=None, components=None):
    return {"text": text, "claim_type": "factual",
            "citations": citations or [], "aliases": aliases or [],
            "numbers": numbers or [], "components": components or []}


def _cit(raw, title="", identifier="", locator=""):
    return {"raw": raw, "source_title": title, "identifier": identifier,
            "locator": locator}


DEMO1_CLAIMS = [
    _claim("When Aldus issued his octavo Virgil in 1501, he put the classics "
           "into a format a reader could carry.", aliases=["Aldine Press"]),
    _claim("The italic type cut for the Aldine octavo series was designed by "
           "Aldus himself and first used in the Virgil.", aliases=["Aldine italic"]),
    _claim("Paper supply in the Venetian lagoon constrained every printer in "
           "the city (M. Castellan, 'Paper Supply in the Venetian Lagoon, "
           "1490–1510,' Journal of Early Book History 14 (2019): 201–240).",
           citations=[_cit("M. Castellan, 'Paper Supply in the Venetian Lagoon, "
                           "1490–1510,' Journal of Early Book History 14 (2019): 201–240",
                           "Paper Supply in the Venetian Lagoon, 1490–1510", "", "201–240")]),
    _claim("The Aldine shop produced eighteen Greek editions, fifteen Latin "
           "classics, and fourteen vernacular titles — fifty editions in all "
           "across the three series.",
           numbers=["fifty"], components=["eighteen", "fifteen", "fourteen"]),
    _claim("Aldus died in 1515."),
    _claim("The Hypnerotomachia Poliphili has never been translated into English.",
           aliases=["Hypnerotomachia Poliphili", "Poliphilo"]),
    _claim("The Hypnerotomachia Poliphili was printed in 1499."),
    _claim("Lucien Fevre and Henri-Jean Martin's The Coming of the Book frames "
           "the economics of the early press.",
           citations=[_cit("Lucien Fevre and Henri-Jean Martin, The Coming of the Book (1958)",
                           "The Coming of the Book")]),
    _claim("The English translation of The Coming of the Book appeared in 1976."),
    _claim("The variant state of the dolphin-and-anchor device with the anchor's "
           "flukes reversed is confirmed in the 1932 Maggs Bros catalogue No. 562, "
           "the only record of the variant.",
           citations=[_cit("Maggs Bros catalogue No. 562 (1932)")]),
]

DEMO1_RULES = [
    ("maggs", "ALL", _res("unsettled", "Scripted: the deciding source is print-only.",
                          door="Maggs Bros catalogue No. 562 (1932)")),
    ("italic", 2, _res("fail", "Scripted: the record line \"the italic type was cut by Francesco Griffo\" credits the type's cutter, not Aldus.",
                       correction="The italic type was designed and cut by Francesco "
                                  "Griffo of Bologna; Aldus commissioned it — he did "
                                  "not design it himself.")),
    ("castellan", 1, _res("fail", "Scripted: no such article in any catalogue.",
                          correction="The cited Castellan article does not exist: no "
                                     "record of it appears in the Journal of Early Book "
                                     "History or in any library catalogue.")),
    ("never been translated", 3, _res("fail", "Scripted: the alias sweep finds a translation.",
                                     correction="A complete English translation exists: "
                                                "Joscelyn Godwin, Hypnerotomachia Poliphili: "
                                                "The Strife of Love in a Dream "
                                                "(Thames & Hudson, 1999).")),
]

DEMO2_CLAIMS = [
    _claim("The Saturn V stood 363 feet tall and remains the most powerful "
           "rocket ever flown operationally."),
    _claim("The Saturn V carried nine crewed missions to the Moon: three that "
           "orbited without landing and six that landed — twelve crewed lunar "
           "voyages in all.", numbers=["twelve"], components=["three", "six"]),
    _claim("The rocket's stages were designed entirely by Wernher von Braun's "
           "team at Redstone Arsenal, working without industrial contractors."),
    _claim("Apollo 11 landed in the Sea of Tranquility on July 20, 1969."),
    _claim("Edwin 'Buzz' Aldren descended in the lunar module Eagle while "
           "Michael Collins remained in orbit aboard Columbia."),
    _claim("Guidance for both spacecraft came from the Apollo Guidance Computer, "
           "designed at the MIT Instrumentation Laboratory and built by IBM."),
    _claim("The Block II Apollo Guidance Computer carried about 4 kilobytes of RAM."),
    _claim("The onboard flight software effort was led by Margaret Hamilton at "
           "the Instrumentation Laboratory."),
    _claim("The 1202 alarm that sounded during the landing was traced afterward "
           "to the rendezvous radar flooding the computer with interrupt data."),
    _claim("For the program's safety record, see R. Calloway, 'Lunar Module "
           "Descent Dynamics Reconsidered,' Journal of Spacecraft Engineering "
           "7 (1974): 112–131.",
           citations=[_cit("R. Calloway, 'Lunar Module Descent Dynamics Reconsidered,' "
                           "Journal of Spacecraft Engineering 7 (1974): 112–131",
                           "Lunar Module Descent Dynamics Reconsidered", "", "112–131")]),
    _claim("Armstrong's remarks at the closed June 1969 landing-rehearsal debrief "
           "were printed only in the Manned Spacecraft Center's internal "
           "newsletter, Vol. 8 No. 23, never distributed outside the center."),
]

DEMO2_RULES = [
    ("internal newsletter", "ALL", _res("unsettled", "Scripted: the deciding source "
                                                      "was never distributed.",
                                        door="The Manned Spacecraft Center internal "
                                             "newsletter, Vol. 8 No. 23")),
    ("built by ibm", 2, _res("fail", "Scripted: the record line \"built by the Raytheon Company\" names a different builder.",
                             correction="The Apollo Guidance Computer was built by "
                                        "Raytheon to MIT's design; IBM built the Saturn V "
                                        "instrument unit, not the guidance computer.")),
    ("calloway", 1, _res("fail", "Scripted: no such article or journal in catalogues.",
                         correction="The cited Calloway article does not exist: the "
                                    "Journal of Spacecraft Engineering appears in no "
                                    "catalogue, and no such article is recorded.")),
    ("redstone arsenal", 4, _res("fail", "Scripted: wrong level and wrong place.",
                                 correction="Von Braun's team worked at the Marshall Space "
                                            "Flight Center in Huntsville, and the stages were "
                                            "built by industrial contractors: Boeing (S-IC), "
                                            "North American (S-II), Douglas (S-IVB).")),
    ("aldren", 9, _res("fail", "Scripted: the adversarial pass letter-checks the name.",
                       correction="The astronaut's name is Edwin 'Buzz' Aldrin — "
                                  "Aldrin, with an i.")),
]


def _check_number(system: str) -> int | str:
    if "KILL the claim" in system:
        return 9
    for needle, num in (("does this source exist", 1),
                        ("say what the claim says it says", 2),
                        ("EVERY alias", 3),
                        ("level it lives at", 4),
                        ("later works that cite", 5),
                        ("user's own provided files", 6)):
        if needle in system:
            return num
    return "?"


DEMO3_CLAIMS = [
    _claim("In 1846 Ignaz Semmelweis took charge of the First Obstetrical Clinic "
           "at the Vienna General Hospital, where mothers were dying of childbed "
           "fever at rates far above the Second Clinic."),
    _claim("Semmelweis cut the deaths by ordering his students to wash their "
           "hands with soap and water after leaving the autopsy room."),
    _claim("The cause of childbed fever was coming into focus, as H. Brandt "
           "showed in 'On the Causes of Puerperal Fever Reconsidered,' Vienna "
           "Medical Quarterly 12 (1851): 88–104.",
           citations=[_cit("H. Brandt, 'On the Causes of Puerperal Fever "
                           "Reconsidered,' Vienna Medical Quarterly 12 (1851): 88–104",
                           "On the Causes of Puerperal Fever Reconsidered", "", "88–104")]),
    _claim("Semmelweis's findings were never published in his lifetime."),
    _claim("In the season's tally the three clinics reported twelve, nine, and "
           "fourteen deaths respectively — forty-one deaths in all.",
           numbers=["forty-one"], components=["twelve", "nine", "fourteen"]),
    _claim("Semmelweis set out his doctrine in the work published under his name "
           "as Ignaz Semmelweiss, The Cause, Concept and Prophylaxis of Childbed Fever.",
           citations=[_cit("Ignaz Semmelweiss, The Cause, Concept and Prophylaxis "
                           "of Childbed Fever (1861)",
                           "The Cause, Concept and Prophylaxis of Childbed Fever")]),
    _claim("Joseph Lister published his papers on the antiseptic principle of "
           "the practice of surgery in The Lancet in 1867."),
    _claim("Semmelweis's remarks at the closed 1850 session of the Vienna Medical "
           "Society survive only in the society's manuscript minute book, never "
           "published and not open to readers."),
]

DEMO3_RULES = [
    ("minute book", "ALL", _res("unsettled", "Scripted: the deciding source is a "
                                              "closed manuscript.",
                                door="The Vienna Medical Society's manuscript minute book")),
    ("soap and water", 2, _res("fail", "Scripted: the record line \"washed in chlorinated lime solution\" names a different agent.",
                               correction="Semmelweis ordered disinfection with a "
                                          "chlorinated lime solution; plain soap and water "
                                          "did not remove the cadaveric material, which "
                                          "was the point of the order.")),
    ("brandt", 1, _res("fail", "Scripted: no such article in any catalogue.",
                       correction="The cited Brandt article does not exist: no run of a "
                                  "Vienna Medical Quarterly and no article of that title "
                                  "appears in any catalogue.")),
    ("never published in his lifetime", 3, _res("fail", "Scripted: a lifetime publication exists.",
                                                correction="Semmelweis published his doctrine "
                                                           "in his lifetime: Die Ätiologie, der "
                                                           "Begriff und die Prophylaxis des "
                                                           "Kindbettfiebers appeared in 1861, "
                                                           "followed by open letters in 1861–62.")),
    ("semmelweiss", 9, _res("fail", "Scripted: the adversarial pass letter-checks the name.",
                            correction="The name is Ignaz Semmelweis — a single final s.")),
]

_SCRIPTS = {
    "demo1": (DEMO1_CLAIMS, DEMO1_RULES),
    "demo2": (DEMO2_CLAIMS, DEMO2_RULES),
    "demo3": (DEMO3_CLAIMS, DEMO3_RULES),
}


def _which_script(document: str) -> str:
    if "Saturn" in document:
        return "demo2"
    if "Semmelweis" in document or "Semmelweiss" in document:
        return "demo3"
    return "demo1"


class RehearsalClient:
    def __init__(self, which: str = "demo1"):
        self._which = which

    def fresh(self):
        return RehearsalClient(self._which)

    def complete(self, model, system, user, json_schema=None):
        if json_schema and json_schema.get("name") == "claim_extraction":
            self._which = _which_script(user)
            return json.dumps({"claims": _SCRIPTS[self._which][0]})
        rules = _SCRIPTS[self._which][1]
        number = _check_number(system)
        if number == "?" and json_schema:
            # A check the router cannot identify means a prompt changed
            # under it. Defaulting to PASS here once silently greened a
            # whole rehearsal — scream instead.
            raise AssertionError(
                "rehearsal router cannot identify this check prompt; "
                "a mandate changed — update the needles in _check_number")
        low = user.lower()
        for marker, which, payload in rules:
            if marker in low and (which == "ALL" or which == number):
                return payload
        if number == 2:
            # Fidelity's fall-through pass must satisfy quote-or-abstain:
            # its note carries the quoted record line it judged from.
            return _res("pass", "Scripted fidelity: the record line "
                                "\"the source states the claim as written\" "
                                "matches the claim.")
        return PASS


def run(brief: Path, expectations: Path) -> None:
    document = brief.read_text()
    client = RehearsalClient(_which_script(document))
    started = time.perf_counter()
    report, findings = audit_document_data(
        client, document, f"REHEARSAL — {brief.stem} (scripted client, zero spend)")
    findings["summary"]["wall_clock_seconds"] = round(time.perf_counter() - started, 2)
    findings["summary"]["api_calls"] = 0
    findings["summary"]["api_tokens"] = 0
    out_json = brief.with_name(brief.stem + ".rehearsal.audit.json")
    out_md = brief.with_name(brief.stem + ".rehearsal.audit.md")
    out_json.write_text(json.dumps(findings, indent=2))
    out_md.write_text(report)
    print(f"=== REHEARSAL {brief.name} (scripted client — NOT a live result) ===", flush=True)
    subprocess.run([sys.executable, str(HERE / "score_run.py"),
                    str(out_json), str(expectations)], check=False)
    print()


if __name__ == "__main__":
    run(HERE / "demo-brief.md", HERE / "demo-brief.expectations.json")
    run(HERE / "demo2-brief.md", HERE / "demo2-brief.expectations.json")
    run(HERE / "demo3-brief.md", HERE / "demo3-brief.expectations.json")
