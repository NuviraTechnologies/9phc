# Demo video script — 9 PHC (3 minutes, kickoff spec)

Division of labor (Richard's call, 2026-10-26): Kai writes the script and
produces the demonstration body with her tools. Richard records his own
introduction and does the final edit on his gear.

PRODUCTION RULE: the body segments are produced from the LIVE baseline run
(real Spark/Wonder calls) once the credits land. Rehearsal footage is a
placeholder for timing only and never appears in the final cut. The video
shows only what was built during the event (kickoff rule).

Total target: 3:00.

---

## Segment 1 — Introduction (0:00–0:35) — RICHARD, to camera

His piece. Draft lines in his own framing, offered to use or throw away:

[Opening line, per the organizers' own guidance in #faqs — state what was
pre-existing and what was built, first thing:]
"I came up with this idea last week. We didn't write a line of it
until the kickoff today — every part of the program you're about to
see was built during this event."

"I'm Richard Vigslist. I've worked with AI for years, and I do research —
real research, the kind that gets published with your name on it. And I
can tell you the failure that costs you: hallucinations. AI will hand you
a citation that doesn't exist, a fact that's almost right, and say it
with total confidence. I've trusted it and been burned in my own research.
So during this hackathon I built the thing I needed: a program that puts
finished research through the gauntlet before it carries anybody's name.
It's called 9-Point Hallucination Calibration — 9 PHC."

## Segment 2 — What it is (0:35–0:55) — PRODUCED (screen: the run starting)

Narration / on-screen text:

"9 PHC is a post-research audit. You hand it a finished piece of
AI-assisted research. It pulls out every checkable claim and runs each
one through nine checks — existence, fidelity, an alias sweep, a
secondary sweep of the works that cite the source, the numbers rebuilt
in plain code, the names letter-checked against the record, and an
adversarial pass in a fresh session whose whole job is to kill the
claim. Every claim comes back Verified, Corrected, or Held unverified —
with receipts."

## Segment 3 — The demonstration, beat one: the scored test (0:55–1:50) — PRODUCED (screen: the live run on the stage)

The Aldine brief goes in. The report comes back, claim by claim:

- "The brief says Aldus designed the italic type. The record says
  Francesco Griffo cut it. **Corrected** — on a receipt, not an opinion."
- "One citation is invented outright — an author and a journal that do
  not exist. The registry lookup flags it cold."
- "The brief says a famous book was never translated into English. The
  alias sweep searches the registries under the book's other names and
  finds the translation: Godwin, 1999. **Corrected.**"
- "Eighteen plus fifteen plus fourteen is stated as fifty. The code
  rebuilds it three times: forty-seven. **Corrected.**"
- "A name is spelled Fevre. The registry record spells it Febvre,
  letter-checked character by character. **Corrected.**"
- "And one claim rests on a print-only 1932 bookseller's catalogue that
  no reachable source can open. 9 PHC does not guess. **Held —
  unverified**, and the report names the door: that catalogue. A checker
  that cannot say unverified cannot make its verified mean
  anything."
- Show the run manifest line: "Every run stamps the document's hash, so
  the report can be tied to the exact text it audited."

The document confidence shown is whatever the filmed run produces —
it is counted in code from the verdicts, never chosen for the camera.

## Segment 3B — The demonstration, beat two: unscripted (1:50–2:20) — PRODUCED (screen: the stage, paste box)

Richard's design (2026-10-26): the planted brief proves the scoring;
this beat proves it is not rehearsed. On camera, an AI is asked for a
short sourced brief on an off-the-wall subject — the Hurrian Hymn, the
oldest song in the world. What it hands back is pasted into the stage
unedited and audited LIVE:

- "It invents a scholar — a Dr. Saracoglu and a journal article that
  do not exist. The existence check flags it cold."
- "It states twenty-nine tablets plus twelve as 'over fifty.' The
  code rebuilds it: forty-one."
- "It claims the hymn's lyrics have never been translated. The alias
  sweep finds the translations. **Corrected.**"
- Narration over the cards landing: "Nobody planted those errors for
  us. The AI wrote them thirty seconds ago, on camera — and the
  checker caught them the same way it catches everything: against
  the record."

## Segment 4 — Why it is hard to fool (2:20–2:42) — PRODUCED

- "The corrections themselves are audited: a correction prints only
  when a receipt backs it. Corrections are claims too."
- "The registries are real — Crossref, DataCite, Open Library, and two
  citation graphs, OpenAlex and Semantic Scholar — read before any model
  judges anything."
- "It is built on Meta's models in two roles: Muse Spark extracts and
  gathers evidence; Muse Wonder does the deep fidelity reads and runs
  the adversarial pass, in a fresh session that never saw the work."
- "And it is an agent tool: any AI can call it — access 9 PHC, get
  findings — and run its own output through the gauntlet."

## Segment 5 — Close (2:42–3:00) — PRODUCED text, or Richard if he wants it

"9 PHC is open source. Anybody can use it: run your AI, then run its
research through the checker before the work carries your name.
Built this week for the Meta Global AI Developer Hackathon.
I'm Richard Vigslist — and I don't trust unchecked research anymore.
Neither should you."

---

Production checklist for Kai:
- [ ] Live filmed run on the Aldine brief via the stage (standing $50 elevation budget; the filmed take is a real live run)
- [ ] Capture the stage run at readable size (verdict board + summary strip), both beats
- [ ] Captions for every narration line (Richard edits; captions ship with the segments)
- [ ] Segment files named by number + timing, delivered to Richard ready to assemble
