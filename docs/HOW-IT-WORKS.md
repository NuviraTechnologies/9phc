# 9 PHC — how it works

**9-Point Hallucination Calibration (9 PHC)** is a post-research audit
program. You hand it a finished piece of AI-assisted research. It
extracts every checkable claim, runs each claim through nine checks
against the scholarly record, and returns every claim as **Verified**,
**Corrected**, or **Held — unverified**, with receipts.

It is not a text generator, not a fact-check overlay inside anyone's
chat, and not a detector that guesses whether text "sounds like AI."
It audits finished work, after the fact, against records a third
party can re-open.

## The three tiers

Richard's framing of where truth constraints can live:

- **Tier 1 — architecture.** Truth constraints built into a model's
  design. Available to the people who build the model.
- **Tier 2 — guardrails.** Rules wrapped around a system from
  outside it.
- **Tier 3 — post-research audit.** The finished output is checked
  against the record, claim by claim, by a separate program. This is
  the tier anyone can actually be given — and it is the tier 9 PHC
  occupies. It adds no latency to generation, because it runs after
  generation is done.

## The pipeline

1. **Extraction.** Muse Spark reads the document twice, in two
   independent passes. The union of the passes is taken: a claim
   either pass found is a claim the audit owes a verdict. Exact
   duplicates collapse; near-duplicates (the same statement in two
   phrasings) merge under a similarity rule with hard guards —
   claims whose stated numbers disagree never merge, and a swap of
   a capitalized name (Venice for Rome) blocks a merge that a swap
   of a verb (printed for published) does not.
2. **Retrieval before judgment.** Before any model judges a claim,
   the program gathers its dossier from real registries: Crossref
   and DataCite for the cited works, Open Library catalogue
   descriptions (admitted only behind a title-similarity gate, so a
   wrong book's description can never be read as this book's
   record), and two citation graphs — OpenAlex and Semantic Scholar —
   for the works that cite each source. What retrieval could not
   reach is named as unreached, never read as empty.
3. **The nine checks** (below), per claim, in parallel.
4. **Verdict resolution in code.** The rules in the next section are
   applied by the engine, not by a model's summary.
5. **Report + findings.** A Markdown report for a human reader and
   a structured findings document (JSON) for an agent caller: every
   claim, every check's outcome, note, door, and raw correction,
   every receipt, the Held work queue, and a run manifest carrying
   the audited document's SHA-256 hash — recompute the hash over
   the document and you can confirm the report is its audit.

## The nine checks

1. **Existence.** Does every source the claim leans on actually
   exist in the registries? An invented author or journal is flagged
   cold. Registry silence about a registry-class source (a journal
   article with volume and pages) is positive grounds; silence about
   a manuscript artifact settles nothing. A claim is failed over a
   dead citation only when the claim's own text leans on it — a
   citation attached from a neighboring sentence condemns nothing.
2. **Fidelity.** Does the cited source say what the claim says it
   says? Muse Wonder does the deep read. Under the
   **quote-or-abstain** rule, a fidelity verdict that quotes no line
   of the record is void — it never engaged. One retry is allowed,
   with the void explained and the quote demanded; a retry that
   still does not quote is void the same way.
3. **Alias sweep.** The subject is searched under all its names —
   other titles, other languages, catalogue labels. A "never
   translated" claim dies here when the translation exists under
   the work's other name.
4. **Right level.** Is the claim credited at the right level — the
   team, not the building; the press, not the printer; the edition,
   not the work?
5. **Secondary sweep.** The works that cite the source are read
   from the citation graphs. Later scholarship often names a
   source's edition, date, or error in one line.
6. **Own-files sweep.** When the caller provides their own files,
   the claim is checked against them. Runs only when files are
   actually provided — an inapplicable check must never hold a
   claim on a technicality.
7. **Numbers, recomputed.** Every stated total is rebuilt from its
   components in plain code, three times; the three runs must
   agree. No model arithmetic.
8. **Names and identifiers, letter-checked.** Names in the claim
   are compared letter by letter against the record's spelling;
   DOI strings are shape-checked in code.
9. **Adversarial pass.** A fresh Muse Wonder session that never saw
   the producing work receives the claim and the dossier with one
   mandate: kill it. A kill must name its settling source in its
   evidence, must be about the claim it condemns (a fluent note
   about a different paper degrades to unsettled at any length),
   and must not merely concede that its record is silent.

## The verdict rules (applied in code)

- **Corrected** — a check contradicted the claim, and the record
  supplies what is actually true, and that correction carries a
  receipt from a peer-reviewed source or a primary record.
  Corrections are claims too: an unbacked correction is never
  printed. Record-based corrections (checks 3–5) must name the
  correcting record in full — against dated evidence, a correction
  that names no year is dropped. Deterministic corrections (the
  rebuilt number, the record's spelling) print alone, never
  concatenated with model prose.
- **Held — unverified** — no contradiction settled the claim, but a
  deciding check could not settle it from reachable sources. Every
  Held claim names its **door**: the specific source that would
  settle it. Holding is a work queue, not a shelf. A claim whose
  checks contradicted it but whose correction was dropped or
  unbacked is Held as **contradicted-but-uncorrected** — the spine
  of the system: a FAIL is never quietly converted into a printed
  guess, and never quietly erased either.
- **Verified** — every applicable check passed, with at least one
  receipt from a peer-reviewed source or a primary record. Passes
  without receipts are Held. Tertiary sources (Wikipedia and its
  kin) may point, but they never settle: a claim supported only by
  tertiary receipts is Held.

**Document confidence** is the share of claims Verified, counted in
code from the verdicts and printed with its arithmetic. It is never
a per-claim probability and never a model's opinion.

## Survival engineering

An audit that dies with its process is worth nothing on a long
document, so:

- **Checkpointing.** Extraction and every finished claim's verdict
  are written to disk as they land (atomic replace). Checkpoint
  identity is the document's hash plus the title plus the hash of
  any user files; any doubt means a fresh run.
- **Resume.** A relaunched run reuses finished verdicts and pays
  only for the claims still missing. Proven under a real kill: a
  run cut down mid-flight by a service restart resumed and
  completed, and the interruption's whole cost was re-auditing the
  claims in flight at the moment of the kill.
- **Spend ledger.** Every API call appends a line to a per-document
  ledger at call time, priced later from the token counts. A killed
  run's burn is on disk, accounted to the token.
- **Token brake.** The client carries a hard 1.5M-token ceiling per
  run; crossing it stops the run rather than the budget.
- **One claim's failure is one claim's Held.** A crash inside a
  single claim's audit marks that claim Held with the failure as
  its door; the run completes.

## Who does what

- **Muse Spark** — extraction and the evidence checks.
- **Muse Wonder** — fidelity (the deep read) and the adversarial
  pass, always in a fresh session.
- **Code** — numbers, name spelling, DOI shape, verdict
  resolution, confidence arithmetic, checkpointing, the ledger.

Standard API mode only. The program never sees or stores the API
key: on the author's machine it reaches the API through a connector
whose credential lives in a secure vault; on the demo server the
key is pasted once into a protected setup page and written straight
to a root-only file the program reads.

## The demo stage

A web stage runs the same engine live in front of an audience:
claims stream in as their verdicts land, each card carrying its
verdict, its nine check results, its correction or its door, and
its receipts; a summary strip shows the document confidence, the
score against the brief's planted defects, the exact spend, and
the document's hash. A hand-off panel gives any AI agent the run's
findings address and the command-line call, so an agent can run
its own output through the same gauntlet.
