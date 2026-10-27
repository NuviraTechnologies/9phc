# 9 PHC — operating guide

## Command line

```
python3 run_audit.py <document.md> [--title "…"] [--files notes.txt] [--json] [--fresh]
```

- Prints the Markdown audit report; `--json` also writes the
  structured findings next to the document (`<name>.audit.json`).
- A spend ledger lands beside the document (`<name>.spend.jsonl`),
  one line per API call, appended at call time.
- A checkpoint file (`<name>.checkpoint.json`) exists only while a
  run is unfinished. Re-running the same command on the same
  document resumes it — you will be asked; `--fresh` discards the
  checkpoint and starts over. (In the demo launcher,
  `python3 demo/launch.py <1|2|3>`, the same prompt appears.)
- Any AI agent can call it the same way; the findings JSON is the
  machine-readable result (see `docs/AGENT.md`).

## What a run costs

A typical short research brief (20–27 extracted claims) costs
**$3.50–$7.20** at hackathon-week prices (Muse Spark $1.25/$4.25
per million tokens in/out; Muse Wonder $4/$20). The run's own
summary reports its exact calls, tokens, and the ledger holds the
per-call record. A hard 1.5M-token ceiling inside the client stops
a runaway run.

## The demo stage (web)

- Serves the same engine over a web page: pick a brief (or paste a
  document), choose DRY (scripted client, $0, honestly labeled) or
  LIVE (real Meta models), and watch verdicts stream in.
- The stage is a presentation layer only — verdicts come from the
  engine's per-claim callback, never from playback.
- One run at a time; a second start is refused while one is live.
- **Arming LIVE:** open `/key-setup` behind the stage's login and
  paste the Meta Model API key once. It is written straight to the
  server's protected credential file (root-only, mode 600) and the
  stage re-reads it before every run — no restart, and the key
  never appears on the page again.
- Finished runs persist their findings under the stage's state
  directory; the hand-off panel on the page links the current
  run's findings and the command-line equivalent.

## Reading a report

- **Verified** — every check passed, with receipts.
- **Corrected** — the record contradicts the claim; the correction
  printed is the one the receipts back.
- **Held — unverified** — not settled from reachable sources. The
  report's Held section is a work queue: each claim names the door
  (the source that would settle it). Work the queue and re-run;
  resume makes the re-run cheap — it pays only for claims whose
  verdicts are missing.
- **Document confidence** — the share of claims Verified, counted
  in code. Low confidence with a high catch rate is the normal
  shape for a document whose sources are thin in the registries:
  the program holds what it cannot settle rather than blessing it.

## Troubleshooting

- *Run died mid-way (restart, crash).* Re-run the same command and
  accept the resume prompt. The ledger shows what the killed run
  burned; the checkpoint holds its finished verdicts.
- *A claim was Held that "should" verify.* Read its checks in the
  findings: the deciding check names what it could not reach. If
  the source is in a registry the program reads, a re-run may
  settle it (registries and network vary); if the door is a print
  source, the Held is the honest final state until that source is
  digitized or opened by hand.
- *A correction looks wrong.* Every correction carries its
  receipts in the findings — open them. A correction without a
  peer-reviewed or primary receipt behind it is never printed; if
  one appears, that is a bug — file the findings JSON with the
  report.
