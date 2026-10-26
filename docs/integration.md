# Integration — "AI, access 9 PHC"

9 PHC is a separate program, not an overlay. Nothing sits inside a
model's generation loop, so nothing slows generation down. A person —
or an AI agent — hands 9 PHC a finished document and gets findings
back. The audit is the deliberate step *after* the work, the way peer
review comes after the paper.

## Three ways to call it

**Command line** (a person, a script, a pipeline):
```text
python3 run_audit.py <document.md> [--title "Title"] [--files own-files.txt] [--json]
```
Writes `<name>.audit.md` (the human report) and, with `--json`,
`<name>.audit.json` (the same findings as structured data).

**Agent tool** (any AI with tool calling): register the function in
`agent-tool-schema.json`. The agent passes the finished document text;
9 PHC returns verdicts with receipts — Verified, Corrected with the
record's own statement, or Held with the unreachable source named.

**Python**:
```python
from audit import MetaModelClient, audit_document_data
report_md, findings = audit_document_data(client, document_text, title)
```

## Speed, stated plainly
- Generation is never touched: zero added latency to any model's output.
- The audit itself parallelises across claims (default 4 workers), so
  a document's wall-clock cost is roughly its longest single claim,
  not the sum of all of them.
- The two mechanical checks (numbers, names) are deterministic code
  and effectively instant. Model calls are the only real cost, and
  they are bounded: nine short calls per claim.

## Who it is for
Research teams, newsrooms, labs, companies whose AI output carries a
human signature — and individual researchers doing deep work who need
to know which of their claims would survive an opponent.
