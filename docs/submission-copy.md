# Submission copy — draft (Richard approves before use)

**Project name:** 9-Point Hallucination Calibration (9 PHC)

**One line:** A post-research audit that runs nine checks over AI-assisted work — including the alias sweep, the own-files sweep, and an independent adversarial pass — and returns each claim Verified, Corrected, or Held unverified, with receipts.

**What it does**
You hand 9 PHC a finished piece of research — a draft, a report, a set of claims with citations. It extracts every checkable claim, verifies each one against peer-reviewed sources and primary records, and returns a report. Claims that stand are Verified, with the backing source named. Claims that are wrong are Corrected — the report states what was wrong and what the record actually says. Claims that cannot be settled from reachable sources are Held — unverified, stated plainly, with the unreachable source named.

**A layer any AI can call**
9 PHC is not an overlay and never sits inside a model's generation loop, so it costs generation nothing. It is a separate program with a tool interface: a researcher — or an AI agent — hands it finished work and gets findings back, the way peer review follows the paper rather than interrupting the writing. Claims audit in parallel, so the gauntlet's price is minutes of wall clock on the audit step, not latency in anyone's stream.

**Why it exists**
In October 2026, a published paper had to be withdrawn because its checks were all internal: the work agreed with itself, and was still wrong. One claim had already been answered in print, under another name for the same work, decades earlier. 9 PHC is the audit regime built from that failure. Its nine checks are: source existence, source fidelity, alias sweep, right-level check, secondary sweep, own-files sweep, numbers recomputed three times by deterministic code, names and identifiers letter-checked by deterministic code, and an adversarial pass.

**The independence rule**
The adversarial pass runs as a separate Muse Wonder instance in a fresh context, with a mandate to kill each claim. It never sees the producing session or its reasoning. A model grading its own homework in the same conversation satisfies nothing.

**The three tiers**
9 PHC does not claim to be the whole answer to AI truthfulness. Architecture-level constraints are tier one. Guard rails around generation are tier two. 9 PHC is tier three: the audit layer on top, for researchers who sign their work. It works on any model's output, and it strengthens both lower tiers by catching what they miss.

**Built with Meta AI**
Muse Spark 1.3 performs claim extraction (structured output) and the evidence checks. Muse Wonder 1.0 runs the adversarial pass and deep source reads. The two deterministic checks are plain code, deliberately: arithmetic and spelling are not opinions.
