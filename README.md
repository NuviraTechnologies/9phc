# 9-Point Hallucination Calibration (9 PHC)

A post-research audit program. Paste in a finished piece of AI-assisted research — a draft, a report, a set of claims with citations. 9 PHC extracts every checkable claim, runs each one through nine verification checks, and returns a verdict report: every claim **Verified**, **Corrected**, or **Held — unverified**, with receipts.

It is not a detector (it does not guess whether AI wrote something) and it is not a guardrail (it does not block output). It audits what was said, fixes what is wrong, and shows the receipts.

## Quickstart

You need Python 3.10+ and your own Meta Model API key. Nothing else — the program is standard library only, no packages to install.

```bash
git clone <this repo> && cd 9phc
cp .env.example .env        # then put your key in .env
python3 run_audit.py demo/demo-brief.md --dry-run   # no key, no spend: watch the pipeline run
python3 run_audit.py your-document.md                   # a live audit, on your key
```

The report prints to the screen and lands beside your document as `<name>.audit.md`. Add `--json` for the structured findings (`<name>.audit.json`) that another program or AI agent can read.

## Bring your own key — how this works

9 PHC runs entirely on **your** API key, on **your** machine, against **your** account. There is no server of ours in the middle and no shared account behind it.

- The key lives in a `.env` file in your clone (copy `.env.example`), or in your environment as `META_API_KEY`. It is read at call time and sent only to `api.meta.ai`, as the bearer header on your own requests.
- The key is never written into a report, a findings file, or the spend ledger the program keeps beside your document.
- Get a key at [dev.meta.ai](https://dev.meta.ai). Meta requires a payment method on file before the first API call. The models used are `muse-spark-1.3` (extraction and evidence checks) and `muse-wonder-1.0` (source fidelity and the adversarial pass) — standard API mode only, never contributor mode.
- Source retrieval is free and keyless: citations are resolved against Crossref, DataCite, Open Library, OpenAlex, and Semantic Scholar before any model judges them.

**What a run costs you:** a typical short research brief (20–27 extracted claims) cost **$3.50–$7.20** at the prices recorded during the build (Muse Spark $1.25/$4.25 per million tokens in/out; Muse Wonder $4/$20) — that is an estimate from the project's own run record (`docs/RUN-RECORD.md`), not a price quote. Every run reports its own exact calls and tokens, keeps a per-call spend ledger beside your document, and a hard 1.5M-token ceiling inside the program stops a runaway run.

## The web version

`web/9phc.html` is the same calibration as a single web page: paste your text, paste your own key, run it in your browser. Calls go from your browser straight to the Meta Model API and the source registries — the page has no backend, and your key never leaves your browser. It is the version running on [nuviratechnologies.io](https://nuviratechnologies.io). One honest limit: the browser page cannot open arbitrary source pages the way the command-line program's retrieval layer can, so its registry dossiers are the evidence base; everything else — prompts, checks, gates, verdict rules — is the same.

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
9. **Adversarial pass** — a separate audit instance that did not produce the answer, running in a fresh context with a debunk mandate, tries to kill each surviving claim from outside sources.

**The independence rule:** the adversarial pass never shares a session or context with the work being audited. A model grading its own homework in the same conversation satisfies nothing.

## Source standard

Peer-reviewed sources and primary records only. A claim is Verified or Corrected on the strength of a peer-reviewed source or a primary record (the cited source itself, opened; an official catalogue or record) — or it is Held. Crowd-edited tertiary pages (Wikipedia and its kin) never settle a claim; at most they point toward a door.

## The three verdicts

- **Verified** — the claim stands; the backing source is named.
- **Corrected** — the claim was wrong; the report states what was wrong and what the record actually says.
- **Held — unverified** — the claim could not be settled from reachable sources. Stated plainly, with the unreachable door named. A calibration that cannot say "unverified" cannot make its "verified" mean anything.

## Built to fail plainly

A timed-out or failed model call never kills a run: the affected check reports unsettled and the claim degrades to Held, with the endpoint named. Long documents are chunked on paragraph boundaries so nothing is silently truncated; duplicate claims are removed before counting, so the confidence rating counts each claim once; a chunk that fails extraction stops the run loudly rather than auditing half a document in silence. Findings are checkpointed to disk after every claim, so a killed run resumes and pays only for what is missing.

## Call it from your own AI

9 PHC is a separate program on purpose: your AI writes at full speed, then calls the audit and gets findings back. Nothing is baked into generation, so nothing slows generation down. The audit ships as a command-line program and as an agent tool (`run_9phc_audit`) that any AI system can invoke — hand it a finished draft, get back the verdict report and structured findings. The findings format and the calling pattern are documented in `docs/AGENT.md`.

## The live record

9 PHC was run live against real documents throughout its build — three demonstration briefs carrying planted defects it is never told about, and one unscripted brief written half an hour before its run. It scores 6/6 on the planted sets across all three briefs, caught an invented citation and an invented tablet catalogue number cold on the unscripted brief, and recorded zero false corrections in its last five runs of the build. The complete record — every run, its score, its spend — is in `docs/RUN-RECORD.md`. The briefs themselves are in `demo/` (their answer keys are not published; the demo stays a fair test). Two test files (`tests/test_round3_guards.py`, `tests/test_round6_guards.py`) drive the project's own scorer against those held-back keys, so they cannot pass from this package alone — they are included for the record, and every other test passes from a clean clone.

## Documentation

- `docs/HOW-IT-WORKS.md` — the full account: pipeline, the nine checks, the verdict rules and gates, the survival engineering.
- `docs/OPERATING.md` — running it: setup, the command line, costs, reading a report, troubleshooting.
- `docs/RUN-RECORD.md` — every live run of the build, with scores and spend.
- `docs/AGENT.md` — calling 9 PHC from an agent; the findings format.
- `docs/integration.md` — the three ways to call it.

## License

Open source, MIT License (see `LICENSE`). Anybody may use it: run your AI's research through the calibration before the work carries your name.

By Richard Vigslist — Nuvira Technologies. Built for the Meta Global AI Developer Hackathon (Oct 26 – Nov 4, 2026), Indie track.
