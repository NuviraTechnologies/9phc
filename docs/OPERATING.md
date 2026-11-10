# 9 PHC — operating guide

## Setup

1. Python 3.10 or newer. No packages to install — standard library only.
2. Your own Meta Model API key from [dev.meta.ai](https://dev.meta.ai). Meta requires a payment method on file before the first API call.
3. Put the key where the program reads it — the environment only:

```bash
cp .env.example .env   # then edit .env and set META_API_KEY
# or: export META_API_KEY=<your key>
```

The key is never written into any file the program produces: not the report, not the findings, not the spend ledger.

## Command line

```
python3 run_audit.py <document.md> [--title "…"] [--files notes.txt] [--json] [--fresh] [--dry-run]
```

- Prints the Markdown audit report; `--json` also writes the structured findings next to the document (`<name>.audit.json`).
- A spend ledger lands beside the document (`<name>.spend.jsonl`), one line per API call, appended at call time.
- A checkpoint file (`<name>.checkpoint.json`) exists only while a run is unfinished. Re-running the same command on the same document resumes it; `--fresh` discards the checkpoint and starts over.
- `--files notes.txt` feeds check 6 (the own-files sweep) your own prior files and outputs as plain text. Without it, check 6 does not run — a claim is never held on a technicality.
- `--dry-run` runs the whole pipeline against a scripted stand-in client: no key needed, nothing spent. The output is a shape demonstration, not an audit.
- Any AI agent can call it the same way; the findings JSON is the machine-readable result (see `docs/AGENT.md`).

## What a run costs

A typical short research brief (20–27 extracted claims) cost **$3.50–$7.20** at the prices recorded during the build (Muse Spark $1.25/$4.25 per million tokens in/out; Muse Wonder $4/$20). Treat that as an estimate, not a quote — prices are the provider's. The run's own summary reports its exact calls and tokens, and the ledger holds the per-call record. A hard 1.5M-token ceiling inside the client stops a runaway run.

## Reading a report

- **Verified** — every check passed, with receipts.
- **Corrected** — the record contradicts the claim; the correction printed is the one the receipts back.
- **Held — unverified** — not settled from reachable sources. The report's Held section is a work queue: each claim names the door (the source that would settle it). Work the queue and re-run; resume makes the re-run cheap — it pays only for claims whose verdicts are missing.
- **Document confidence** — the share of claims Verified, counted in code. Low confidence with a high catch rate is the normal shape for a document whose sources are thin in the registries: the program holds what it cannot settle rather than blessing it.

## The web version

`web/9phc.html` runs the same calibration in a browser: paste text, paste your own key, run. It calls the Meta Model API and the source registries directly from the browser; there is no backend, and the key stays in the page, in your browser. Its one limit against this command-line program: a browser cannot open arbitrary source pages, so the page's checks judge from the registry dossiers (Crossref, DataCite, Open Library, OpenAlex, Semantic Scholar) rather than fetched full text.

## Troubleshooting

- **"9 PHC needs your own Meta Model API key to run live"** — no key was found in the environment or in `.env`. Set one, or use `--dry-run`.
- **HTTP 402 from the API** — the account has no payment method on file or no usable balance. Add one at dev.meta.ai; do not keep retrying.
- **HTTP 400 naming a schema key** — the structured-output schema and the API disagree; the error body names the exact defect.
- **Many claims Held with registry doors named** — the registries could not be reached or hold nothing on those sources. A registry that cannot be reached is reported as unreached, never read as empty; check your connection and re-run (resume keeps it cheap).
