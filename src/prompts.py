"""9 PHC — the check prompts.

Each model-backed check runs as its own pass with its own mandate.
Check 9 is the important one: it runs in a FRESH context, with a
debunk mandate, and never sees the producing session's reasoning
(the independence rule).
"""

SOURCE_STANDARD = """Source standard (hard rule): a claim may be supported or
contradicted only by a peer-reviewed source or a primary record (the cited
source itself, opened; an official catalogue or record). Wikipedia and other
crowd-edited tertiary pages NEVER settle a claim — at most they point toward
a source that does. If the deciding source cannot be opened, the check is
UNSETTLED and you must name the door: the exact source that would decide it.

The SOURCE DOSSIER attached to a claim is the source opened at registry
level: the catalogue record, the metadata of record, the abstract of record.
Judge from the record in hand. UNSETTLED requires naming the deciding point
the record in hand is SILENT on — the absence of a fetched full text is not
by itself a deciding point when the record in hand speaks to the claim. A
third party's paraphrase still never counts; the source's own record does."""

CHECK_PROMPTS = {
    1: ("Source existence",
        "For each citation attached to the claim: does this source exist? "
        "Resolve it in catalogues/records (publisher, journal archive, library "
        "catalogue, DOI registry). Report PASS if every citation resolves. "
        "FAIL only on positive grounds: a registry-class source (a journal "
        "article with volume and pages, a DOI- or ISBN-bearing work) that "
        "resolves NOWHERE, or a record that resolves and is a different work "
        "than the one cited — in the first case the correction is that the "
        "cited source does not exist. A source of a class registries do not "
        "hold (print-only catalogues, manuscripts, ephemera) that does not "
        "resolve is UNSETTLED, with the artifact itself as the door: registry "
        "silence about print artifacts settles nothing."),
    2: ("Source fidelity",
        "Does the cited source say what the claim says it says? Judge against "
        "the source's own record in the dossier — its abstract of record, its "
        "catalogue description, the passage of record — at the place cited. "
        "Other people's paraphrases do not count; the source's own record "
        "does. PASS if it matches, FAIL if it differs, stating what the "
        "source actually says. UNSETTLED only when the record in hand is "
        "silent on the deciding point, naming that point as the door."),
    3: ("Alias sweep",
        "The claim's subject carries other names (listed with the claim). "
        "Search the record under EVERY alias: alternate titles, incipits, "
        "catalogue labels, nicknames. A claim of absence ('never published', "
        "'no translation exists', 'first') fails if anything surfaces under "
        "any alias. Report what the sweep found under each name. When an "
        "ALIAS DOSSIER is attached, it is registry ground truth gathered "
        "before this check ran: judge the sweep from it, not from memory. "
        "The dossier's search under each alias IS the sweep: if every listed "
        "alias was searched, the sweep is complete and you judge PASS or FAIL "
        "from what it found. UNSETTLED only for an alias that could not be "
        "searched at all, naming it as the door."),
    4: ("Right-level check",
        "Verify the claim at the level it lives at. A claim about a work is "
        "checked against the work's own record — not only the record of one "
        "copy, edition, or witness of it, which may be silent about the work. "
        "If you only reached a lower-level record, say so and mark UNSETTLED "
        "with the right-level record as the door."),
    5: ("Secondary sweep",
        "Find later works that cite the claim's source. Later scholarship often "
        "names an edition, a correction, or a retraction in a single line. "
        "PASS if nothing found contradicts the claim; FAIL if a citing work "
        "contradicts it, quoting the line. When a CITED-BY DOSSIER is "
        "attached, it lists real later works from the OpenAlex and "
        "Semantic Scholar citation graphs: judge from it, and never "
        "invent a citing work it does not list."),
    6: ("Own-files sweep",
        "Search the user's own provided files and prior outputs for anything "
        "bearing on this claim. A contradiction inside the user's own record "
        "is a finding: report it exactly, naming the file. If no user files "
        "were provided, mark UNSETTLED with the door 'the user's own files'."),
}

ADVERSARIAL_SYSTEM_PROMPT = """You are the adversarial pass of an audit program — check 9.
Your mandate is to KILL the claim in front of you.

You did not write this claim, you owe it nothing, and you have not seen the
reasoning that produced it. Argue as an opponent who wants the claim dead:
search for the source that contradicts it, the edition it missed, the alias
it never swept, the count it got wrong. Use fresh sources you find yourself,
not the claim's own citations where avoidable.

{standard}

Outcomes:
- If you land a contradiction from a peer-reviewed source or a primary
  record: FAIL, and state what the record actually says (that becomes the
  correction).
- If the claim survives your attack and is backed by a peer-reviewed or
  primary source you opened yourself: PASS.
- If you cannot settle it from reachable sources: UNSETTLED, naming the
  exact door — the source that would decide it. Never soften this.
A claim you cannot kill and cannot confirm is HELD. That is a real result,
not a failure of your pass."""
