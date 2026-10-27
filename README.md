# 9-Point Hallucination Calibration (9 PHC)

A post-research audit program. Paste in a finished piece of AI-assisted research — a draft, a report, a set of claims with citations. 9 PHC extracts every checkable claim, runs each one through nine verification checks, and returns a verdict report: every claim **Verified**, **Corrected**, or **Held — unverified**, with receipts.

It is not a detector (it does not guess whether AI wrote something) and it is not a guardrail (it does not block output). It audits what was said, fixes what is wrong, and shows the receipts.

## Where 9 PHC sits — the three tiers of truth constraint

1. **Architecture** — truth constraints baked into a model's under-architecture during design and training. The governing layer.
2. **Guard rails and seat belts** — constraints on the outside of the architecture, around generation and output.
3. **9 PHC** — the processor program on top: an in-depth research audit for researchers who want the facts checked before the work carries their name.

9 PHC's builder does not build models, so tiers 1 and 2 are not his to give. Tier 3 strengthens both: it works on any model's output, and it works best on models whose own tiers lean toward truth, because every layer then leans the same way.

## The nine checks

1. **Source existence** — every cited book, record, page, and identifier must be shown to exist.
2. **Source fidelity** — the cited source, opened, must say what the claim says it says, at the place cited.
3. **Alias sweep** — the subject is searched under every other name it carries: alternate titles, incipits, catalogue labels, nicknames.
4. **Right-level check** — a claim is verified at the level it lives at (a claim about a composition against the composition's record, not only the nearest object's).
5. **Secondary sweep** — later works that cite the source are checked; they often name an edition or a correction in a single line.
6. **Own-files sweep** — the user's own prior files and outputs are searched for anything that contradicts the claim.
7. **Numbers recomputed** — every count, total, and figure is rebuilt from the underlying items, three times. The three runs must agree. *(Deterministic code — no model.)*
8. **Names and IDs letter-checked** — every name, DOI, and identifier is verified character by character against its source. *(Deterministic code — no model.)*
9. **Adversarial pass** — a separate checker instance that did not produce the answer, running in a fresh context with a debunk mandate, tries to kill each surviving claim from outside sources.

**The independence rule:** the adversarial pass never shares a session or context with the work being audited. A model grading its own homework in the same conversation satisfies nothing.

## Source standard

Peer-reviewed sources and primary records only. A claim is Verified or Corrected on the strength of a peer-reviewed source or a primary record (the cited source itself, opened; an official catalogue or record) — or it is Held. Crowd-edited tertiary pages (Wikipedia and its kin) never settle a claim; at most they point toward a door.

## The three verdicts

- **Verified** — the claim stands; the backing source is named.
- **Corrected** — the claim was wrong; the report states what was wrong and what the record actually says.
- **Held — unverified** — the claim could not be settled from reachable sources. Stated plainly, with the unreachable door named. A checker that cannot say "unverified" cannot make its "verified" mean anything.

## Stack

- Claim extraction and report structure: Muse Spark (Meta Model API), structured output.
- Adversarial pass and source-fidelity reads: Muse Wonder (Meta Model API), fresh context per audit.
- Checks 7 and 8: plain deterministic code.
- Source retrieval: citations are resolved against the Crossref and DataCite registries (Open Library for books) BEFORE any model judges them — existence is a registry fact, not a model's memory. A code-level title-match gate keeps junk search hits out of the evidence, and registry abstracts are fed to the fidelity check as the source's own words. The alias sweep (check 3) searches the same registries under every other name the subject carries, and the secondary sweep (check 5) reads two independent citation graphs — OpenAlex and Semantic Scholar — for the later works citing each source. A registry that cannot be reached is reported as unreached, never read as empty.

## Built to fail honestly

A timed-out or failed model call never kills a run: the affected check reports unsettled and the claim degrades to Held, with the endpoint named. Long documents are chunked on paragraph boundaries so nothing is silently truncated; duplicate claims are removed before counting, so the confidence rating counts each claim once; a chunk that fails extraction stops the run loudly rather than auditing half a document in silence.

## Call it from your own AI

9 PHC is a separate program on purpose: your AI writes at full speed, then calls the audit and gets findings back. Nothing is baked into generation, so nothing slows generation down. The audit ships as a command-line program and as an agent tool (`run_9phc_audit`) that any AI system can invoke — hand it a finished draft, get back the verdict report and structured findings. The findings format and the calling pattern are documented in `docs/AGENT.md`.

## The live record

9 PHC has been run live against real documents throughout its
build — three demonstration briefs carrying planted defects it is
never told about, and one unscripted brief written half an hour
before its run. It scores 6/6 on the planted sets across all three
briefs, caught an invented citation and an invented tablet
catalogue number cold on the unscripted brief, and has recorded
zero false corrections in its last five runs. The complete record —
every run, its score, its spend — is in `docs/RUN-RECORD.md`.

## Documentation

- `docs/HOW-IT-WORKS.md` — the full account: pipeline, the nine
  checks, the verdict rules and gates, the survival engineering.
- `docs/RUN-RECORD.md` — every live run, with scores and spend.
- `docs/OPERATING.md` — running it: the command line, the demo
  stage, costs, troubleshooting.
- `docs/AGENT.md` — calling 9 PHC from an agent; the findings
  format.

## License

Open source, MIT License (see `LICENSE`). Anybody may use it: run your AI's research through the checker before the work carries your name.

Built for the Meta Global AI Developer Hackathon (Oct 26 – Nov 4, 2026), Indie track.
