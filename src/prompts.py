"""9 PHC — the checker prompts.

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
UNSETTLED and you must name the door: the exact source that would decide it."""

CHECK_PROMPTS = {
    1: ("Source existence",
        "For each citation attached to the claim: does this source exist? "
        "Resolve it in catalogues/records (publisher, journal archive, library "
        "catalogue, DOI registry). Report PASS if every citation resolves, "
        "FAIL if any citation cannot be found anywhere, naming which one."),
    2: ("Source fidelity",
        "Open the cited source at the cited place. Does it say what the claim "
        "says it says? Summaries, abstracts, and other people's paraphrases do "
        "not count — the source itself, at the place cited. PASS if it matches, "
        "FAIL if it differs, stating what the source actually says."),
    3: ("Alias sweep",
        "The claim's subject carries other names (listed with the claim). "
        "Search the record under EVERY alias: alternate titles, incipits, "
        "catalogue labels, nicknames. A claim of absence ('never published', "
        "'no translation exists', 'first') fails if anything surfaces under "
        "any alias. Report what the sweep found under each name. When an "
        "ALIAS DOSSIER is attached, it is registry ground truth gathered "
        "before this check ran: judge the sweep from it, not from memory."),
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
