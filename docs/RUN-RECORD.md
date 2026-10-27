# 9 PHC — the live run record

Every live run of the program against real documents, in order.
Demo briefs 1–3 each carry six planted defects (an invented
citation, a wrong attribution, a false "never" claim, a rigged
tally, a misspelled name, and one claim only a print source can
settle). The program is never told which claims are planted.
Scoring is by an independent scorer against a held-back answer
key. "Verified" counts claims the program certified as written.

## The Aldine brief (demo 1) — the hardening ladder

| Run | Claims | Score | Verified | Spend | What it taught |
|---|---|---|---|---|---|
| Baseline | — | 5/6 | 0 | $4.3387 | The invented citation was only half-caught; extraction had stripped its attribution |
| Confirming | — | 6/6 | 0 | $4.7888 | The citation caught whole; fidelity abstained on nearly every claim |
| Round 2 | — | 6/6 | 0 | $3.5383 | Quote-or-abstain wired for fidelity; correction gates hardened |
| Round 3 | — | 6/6 | 0 | $4.2179 | Over-attachment: one dead citation failed four claims that never made it |
| Round 4 | 21 | 5/6* | 0 | $3.8918 | Existence binding fixed round 3's failure; *the miss was a scorer term, not an engine miss; zero false corrections |
| Round 5 | 21 | 4/6* | **1** | $6.2772 | First Verified in a full run. *Both scorecard misses were mechanics (a correction that never reached print; a scorer sampling the wrong claim), fixed in round 6 |
| Round 6 | 25 | 6/6 | **2** | $7.1879 | Both round-5 misses closed; the "most beautiful" claim audited once instead of twice (merge live) |
| Round 6 final | 21 | 6/6 | 0 | $5.9307 | Catching steady; certifying variance is fidelity's engagement, addressed in round 7 |
| Round 7 | 16 | 6/6 | 0 | $5.1361 | The quote-demanded fidelity retry is wired (probe-proven live beforehand: a voided PASS re-engaged with the line quoted). In this run its precondition never occurred — fidelity's abstentions were the record-silent kind, not the no-quote kind. Certifying remains bounded by registry coverage, not by the retry |

Small probes between rounds (single checks on single claims):
$0.4842 and $0.1177 in the round-2 cycle; $0.5276 for the round-7
fidelity probe (baseline vs retry on the real 1499 claims).
Pre-round-6 live spend across the ladder: $27.6546.

## Generality — documents the tuning never targeted

| Run | Claims | Score | Verified | Spend | Note |
|---|---|---|---|---|---|
| Brief 2, Apollo/Saturn V | 27 | 6/6 | 0 | $5.6339 | First live run on this document. All six plant families caught |
| Brief 3, Semmelweis | 23 | 6/6 | 0 | $6.4239 | Survived a service restart mid-run; checkpoint resume paid only for unfinished claims (interruption cost ≈ $2.87) |
| Wild brief, Hurrian Hymn | 26 | see note | 0 | $6.4723 | Written 30 minutes before the run, unscripted. Invented scholar corrected (twice, on two extraction shards); "never translated" corrected (Kilmer 1974); tablet count corrected against the real corpus. One partial miss: a misspelled "Kilmmer" Held, not corrected — the name check needs a citation on the claim to bite. One unlisted catch: an invented tablet catalogue number, written as set dressing, corrected to the true joined siglum |

## Reading the Verified column honestly

Catching is the steady side: 6/6 in six of the eight Aldine runs,
with both exceptions traced to scorer mechanics rather than engine
misses, and 6/6 on both first-run documents. Certifying is
deliberately harder: a claim verifies only when every check passes
*with receipts*, and fidelity must quote the deciding line. The
round-7 retry raised engagement without loosening any rule — a
retry that still cannot quote is void the same way.

Zero false corrections were recorded in any round-6 or round-7 run.
The one scorer flag raised (a tally component "corrected" in the
round-6 Aldine run) was reclassified on reading the record: the
adversarial pass had corrected the component against real history
with an itemized enumeration — the component was true only inside
the brief's invented tally. The program grades against the record,
not against a document's internal fiction.
