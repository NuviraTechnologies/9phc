# Calling 9 PHC from an agent

9-Point Hallucination Calibration (9 PHC) is built to be called by
other AIs. The workflow it exists for: **an agent produces research,
then runs its own output through 9 PHC before the work carries
anybody's name.**

## The call

```
python3 run_audit.py <document.md> --json
```

Returns (stdout) the Markdown report; writes `<document>.audit.json`
— the findings — beside the document.

On the demo stage, the same findings for a finished run are served
at `/api/findings?id=<run_id>`, and the stage's hand-off panel
shows the exact call for the run on screen.

## The findings document

```json
{
  "program": "9-Point Hallucination Calibration (9 PHC)",
  "document": "<title>",
  "summary": {
    "claims": 21, "verified": 2, "corrected": 9,
    "held_unverified": 10, "confidence_percent": 10,
    "api_calls": 128, "api_tokens": 705802
  },
  "held_queue": [
    {"claim_id": 6, "text": "…", "doors": ["…"], "reason": "…"}
  ],
  "claims": [
    {
      "id": 1, "text": "…",
      "verdict": "Corrected",
      "correction": "what the record actually says",
      "held_reason": "",
      "checks": [
        {"number": 3, "name": "Alias sweep", "outcome": "fail",
         "note": "…", "door": "", "correction": "the check's raw correction"}
      ],
      "receipts": [
        {"source": "…", "class": "primary_record",
         "detail": "…", "reference": "DOI or catalogue id"}
      ]
    }
  ],
  "manifest": {
    "document_sha256": "…", "audited_at_utc": "…",
    "models": {"extraction_and_evidence": "muse-spark-1.3",
               "fidelity": "muse-wonder-1.0",
               "adversarial": "muse-wonder-1.0"}
  }
}
```

Verdicts are exactly `Verified`, `Corrected`, or `Held —
unverified`. Check outcomes are `pass`, `fail`, or `unsettled`.

## How an agent should use the result

- Treat every **Corrected** claim as a required edit: the
  correction is backed by the receipts listed with it.
- Treat every **Held** claim as unfinished work, not as falsehood:
  the `held_queue` names the door for each — the source that would
  settle it. Retrieve the door, or soften the claim to what the
  reachable record supports, and re-run; a resumed run pays only
  for the claims still missing verdicts.
- Quote the **document confidence** only as what it is: the share
  of claims that verified as written, counted in code — never as a
  probability about any single claim.
- Keep the **manifest hash** with the audited document: it ties
  the findings to the exact text that was audited.
