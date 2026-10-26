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

"I'm Richard Vigslist. I've worked with AI for years, and I do research —
real research, the kind that gets published with your name on it. And I
can tell you the failure that costs you: hallucinations. AI will hand you
a citation that doesn't exist, a fact that's almost right, and say it
with total confidence. I've trusted it and been burned in my own research.
So during this hackathon I built the thing I needed: a program that puts
finished research through the gauntlet before it carries anybody's name.
It's called 9 PHC."

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

## Segment 3 — The demonstration (0:55–2:15) — PRODUCED (screen: the live run)

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
  that can say unverified is the only kind whose verified means
  anything."
- Show the run manifest line: "Every run stamps the document's hash, so
  the report can be tied to the exact text it audited."

Document confidence for the brief: 40% — counted in code from the
verdicts, printed in the report.

## Segment 4 — Why it is hard to fool (2:15–2:40) — PRODUCED

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

## Segment 5 — Close (2:40–3:00) — PRODUCED text, or Richard if he wants it

"9 PHC is open source. Anybody can use it: run your AI, then run its
research through the checker before the work carries your name.
Built this week for the Meta Global AI Developer Hackathon.
I'm Richard Vigslist — and I don't trust unchecked research anymore.
Neither should you."

---

Production checklist for Kai:
- [ ] Live baseline run on the Aldine brief (credits + Richard's word first)
- [ ] Capture the run + report render at readable size, terminal and report both
- [ ] Captions for every narration line (Richard edits; captions ship with the segments)
- [ ] Segment files named by number + timing, delivered to Richard ready to assemble
