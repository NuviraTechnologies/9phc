#!/usr/bin/env python3
"""Checkpoint / resume / ledger tests — offline, scripted clients.

The armor's contract:
- a run killed mid-flight (a REAL process kill, in a child process)
  leaves a checkpoint holding every finished claim, and extraction is
  already paid for and saved;
- a resumed run pays only for the claims still missing;
- a checkpoint for a different document is ignored, never trusted;
- one claim's internal crash degrades that claim to Held — the run
  completes and loses nothing;
- a finished run removes its checkpoint;
- the spend ledger records every call at call time, cumulative.
"""
import json
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import audit  # noqa: E402
from audit import MetaModelClient, audit_document_data  # noqa: E402

CLAIMS = [{"text": f"Claim number {i} states a fact.", "claim_type": "factual",
           "citations": [], "aliases": [], "numbers": [], "components": []}
          for i in range(1, 5)]
PASS = json.dumps({"outcome": "pass", "note": "ok: “the record states it”", "door": "",
                   "correction": "", "evidence": []})
DOC = "Claim number 1 states a fact.\n\nClaim number 2 states a fact."

CHILD = textwrap.dedent("""
    import json, os, sys, time
    sys.path.insert(0, __SRC__)
    import audit
    from audit import audit_document_data

    CLAIMS = [{"text": f"Claim number {i} states a fact.", "claim_type": "factual",
               "citations": [], "aliases": [], "numbers": [], "components": []}
              for i in range(1, 5)]
    PASS = json.dumps({"outcome": "pass", "note": "ok: “the record states it”", "door": "",
                       "correction": "", "evidence": []})

    class FakeClient:
        def fresh(self): return self
        def complete(self, model, system, user, json_schema=None):
            if json_schema and json_schema.get("name") == "claim_extraction":
                return json.dumps({"claims": CLAIMS})
            return PASS
        def usage_snapshot(self): return {"api_calls": 0, "api_tokens": 0}

    real = audit.audit_claim
    def dying(client, claim, user_files=""):
        if claim.id > 2:
            time.sleep(1.0)          # claims 1-2 land and checkpoint first
            os._exit(137)           # the kill: no cleanup, no final write
        return real(client, claim, user_files)
    audit.audit_claim = dying
    audit_document_data(FakeClient(), __DOC__, "T", "", checkpoint_path=__CKPT__)
""")


class FakeClient:
    def __init__(self):
        self.calls = 0
        self.extractions = 0

    def fresh(self):
        return self

    def complete(self, model, system, user, json_schema=None):
        self.calls += 1
        if json_schema and json_schema.get("name") == "claim_extraction":
            self.extractions += 1
            return json.dumps({"claims": CLAIMS})
        return PASS

    def usage_snapshot(self):
        return {"api_calls": self.calls, "api_tokens": self.calls * 10}


def _run(client, ckpt, doc=DOC):
    return audit_document_data(client, doc, "T", "", checkpoint_path=ckpt)


def main() -> int:
    src_dir = str(Path(__file__).resolve().parent.parent / "src")
    with tempfile.TemporaryDirectory() as td:
        ckpt = Path(td) / "doc.checkpoint.json"

        # --- run A: a real kill after two claims -------------------------
        child = (CHILD.replace("__SRC__", repr(src_dir)).replace("__DOC__", repr(DOC)).replace("__CKPT__", repr(str(ckpt))))
        proc = subprocess.run([sys.executable, "-c", child],
                              capture_output=True, text=True, timeout=120)
        assert proc.returncode == 137, f"child should die by the kill, got {proc.returncode}: {proc.stderr[-400:]}"
        assert ckpt.exists(), "checkpoint must survive the kill"
        saved = json.loads(ckpt.read_text())
        assert len(saved["claims"]) == 4, "extraction is checkpointed"
        assert len(saved["verdicts"]) == 2, f"expected 2 verdicts saved, got {len(saved['verdicts'])}"

        # --- run B: resume pays only for what is missing -------------------
        client_b = FakeClient()
        seen = []
        real2 = audit.audit_claim

        def counting(client, claim, user_files=""):
            seen.append(claim.id)
            return real2(client, claim, user_files)

        audit.audit_claim = counting
        try:
            _, findings_b = _run(client_b, ckpt)
        finally:
            audit.audit_claim = real2
        assert client_b.extractions == 0, "resume must not re-buy extraction"
        assert sorted(seen) == [3, 4], f"resume audited {seen}, expected [3, 4]"
        assert findings_b["summary"]["claims"] == 4
        assert not ckpt.exists(), "a finished run removes its checkpoint"

        # --- run C: uninterrupted run agrees with the resumed one ---------
        _, findings_c = _run(FakeClient(), Path(td) / "c.checkpoint.json")
        assert findings_b["claims"] == findings_c["claims"], "resumed findings must equal a clean run's"
        assert findings_b["summary"]["confidence_percent"] == findings_c["summary"]["confidence_percent"]

        # --- run D: a foreign checkpoint is ignored -------------------------
        ckpt_d = Path(td) / "d.checkpoint.json"
        _run(FakeClient(), ckpt_d, doc=DOC)
        client_d = FakeClient()
        _run(client_d, ckpt_d, doc="A completely different document.")
        # Round 5: one fresh extraction is TWO passes (dual extraction
        # + union), so the counter reads 2 where it read 1 before.
        assert client_d.extractions == 2, "hash mismatch must mean a fresh extraction"

        # --- run E: one claim's crash degrades to Held, run completes -------
        real3 = audit.audit_claim

        def crashing(client, claim, user_files=""):
            if claim.id == 2:
                raise ValueError("boom")
            return real3(client, claim, user_files)

        audit.audit_claim = crashing
        try:
            _, findings_e = _run(FakeClient(), Path(td) / "e.checkpoint.json")
        finally:
            audit.audit_claim = real3
        by_id = {c["id"]: c for c in findings_e["claims"]}
        assert by_id[2]["verdict"] == "Held — unverified", by_id[2]
        assert "failed internally" in by_id[2]["held_reason"]
        # Claim 1 ran normally: receipt-less passes are Held by the
        # engine's own rule — the point is its reason is the ordinary
        # one, not the crash's.
        assert "no check produced a receipt" in by_id[1]["held_reason"]

        # --- ledger: every call on disk, cumulative -------------------------
        ledger = Path(td) / "spend.jsonl"
        mc = MetaModelClient()
        mc.attach_ledger(ledger)
        mc._record_usage("muse-spark-1.3", 100)
        mc._record_usage("muse-wonder-1.0", 250)
        lines = [json.loads(x) for x in ledger.read_text().splitlines()]
        assert [x["run_tokens"] for x in lines] == [100, 350], lines
        assert mc.usage_snapshot() == {"api_calls": 2, "api_tokens": 350}

    print("checkpoint: kill/resume/crash/ledger tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
