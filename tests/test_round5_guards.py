"""Round-5 guards, pinned (built after the round-4 live run):
- dual extraction + union: two extraction passes per chunk, merged —
  claims, citations and aliases unioned; numbers/components fill only
  when empty. Extraction variance across the live runs (18/16/16/14
  claims; citations 15/16 then 8/14) set each run's ceiling; the union
  is the deterministic blunting of that variance. One successful pass
  is a complete extraction; both failing stops the run loudly.
- correction completeness: checks 3, 4 and 5 carry the doctrine —
  name the record a correction rests on IN FULL — pinned as prompt
  text, with the rehearsal router needles verified intact.
Run: python3 tests/test_round5_guards.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from audit import extract_claims
from prompts import CHECK_PROMPTS

FAILURES = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILURES.append(name)


def _claim(text, citations=None, aliases=None, numbers=None, components=None):
    return {"text": text, "claim_type": "factual",
            "citations": citations or [], "aliases": aliases or [],
            "numbers": numbers or [], "components": components or []}


def _cit(raw, title=""):
    return {"raw": raw, "source_title": title, "identifier": "",
            "locator": ""}


PASS_A = [_claim("The shop output was fifty editions in all."),
          _claim("Aldus issued his octavo Virgil in 1501.")]
PASS_B = [_claim("The shop output was fifty editions in all.",
                 citations=[_cit("Some registry entry", "A Registry Record")],
                 numbers=["fifty editions"],
                 components=["eighteen Greek", "fifteen Latin",
                             "fourteen vernacular"]),
          _claim("The founder died in 1515.", aliases=["Aldo Manuzio"])]


class UnionStub:
    def __init__(self):
        self.calls = 0

    def fresh(self):
        return self

    def complete(self, model, system, user, json_schema=None):
        self.calls += 1
        return json.dumps({"claims": PASS_A if self.calls % 2 == 1 else PASS_B})


claims = extract_claims(UnionStub(), "A short document.")
texts = [c.text for c in claims]
check("union keeps claims found by either pass",
      len(claims) == 3 and "The founder died in 1515." in texts
      and "Aldus issued his octavo Virgil in 1501." in texts)
merged = next(c for c in claims if c.text.startswith("The shop output"))
check("a claim found by both passes keeps the citation either attached",
      len(merged.citations) == 1
      and merged.citations[0].source_title == "A Registry Record")
check("numbers/components fill from the pass that read them",
      merged.numbers == ["fifty editions"] and len(merged.components) == 3)
founder = next(c for c in claims if c.text.startswith("The founder"))
check("aliases union onto the merged claim set",
      founder.aliases == ["Aldo Manuzio"])


class FirstPassOnly:
    def __init__(self):
        self.calls = 0

    def fresh(self):
        return self

    def complete(self, model, system, user, json_schema=None):
        self.calls += 1
        if self.calls == 1:
            return json.dumps({"claims": PASS_A})
        raise RuntimeError("endpoint down")


claims = extract_claims(FirstPassOnly(), "A short document.")
check("one successful pass is a complete extraction",
      len(claims) == 2)


class AlwaysDown:
    def fresh(self):
        return self

    def complete(self, model, system, user, json_schema=None):
        raise RuntimeError("endpoint down")


try:
    extract_claims(AlwaysDown(), "A short document.")
    check("both passes failing stops the run loudly", False)
except RuntimeError:
    check("both passes failing stops the run loudly", True)


# ------------------------------------------------- completeness doctrine
for n, needle in ((3, "EVERY alias"), (4, "level it lives at"),
                  (5, "later works that cite")):
    mandate = CHECK_PROMPTS[n][1]
    check(f"check {n} mandate carries the completeness doctrine",
          "name that record IN FULL" in mandate)
    check(f"check {n} mandate keeps its rehearsal needle ({needle!r})",
          needle in mandate)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
    raise SystemExit(1)
print("ALL ROUND-5 GUARD TESTS PASS")
