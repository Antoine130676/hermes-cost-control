#!/usr/bin/env python3
"""Evaluate the policy assistant against two question sets.

  golden.json   questions used while building and tuning the retrieval rules and cut-offs
  heldout.json  questions written before tuning and never used for it

For questions that have an answer in the policies:
  hit@1 / hit@3   the right section is ranked first / in the top three
  confident       the assistant answered (strong evidence)
  not refused     it answered or at least suggested the closest sections (it never said "I can't find this")
For out-of-scope questions:
  wrongly confident   must be zero: a confident answer to a question the policies do not cover is the worst failure
  refused             refused outright (suggesting closest sections instead is acceptable but weaker)

It exits non-zero when a score falls below the thresholds, so a policy edit that breaks the assistant is caught.

  python evaluate.py            # per-question table and both summaries
  python evaluate.py --quiet    # summaries only
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import assistant  # noqa: E402

# "wrongly_confident" must stay 0 for both sets. The held-out ranking guard is looser than the tuning set on purpose.
THRESHOLDS = {"golden": {"hit@3": 0.90, "not_refused": 0.90, "max_wrongly_confident": 0},
              "heldout": {"hit@3": 0.70, "not_refused": 0.70, "max_wrongly_confident": 0}}


def evaluate(path, policies_dir=None):
    index = assistant.Index(assistant.load_chunks(policies_dir or assistant.DEFAULT_POLICIES))
    items = json.loads(Path(path).read_text(encoding="utf-8"))["questions"]
    rows, ins, outs = [], [], []
    for item in items:
        res = assistant.answer(item["question"], index)
        ranked = [f"{c.source} > {c.heading}" for _, c in index.search(res["question_redacted"], 3)]
        if item.get("out_of_scope"):
            outs.append(res["status"])
            ok = res["status"] != "answered"
            rows.append(("out", ok, item["question"], f"{res['status']} (coverage {res['coverage']})"))
        else:
            top1 = bool(ranked) and ranked[0] == item["expected"]
            ins.append((top1, item["expected"] in ranked, res["status"]))
            rows.append(("in", top1, item["question"], f"{res['status']:9} {ranked[0] if ranked else '(nothing found)'}"))
    n = len(ins)
    return {
        "questions": len(items),
        "hit@1": sum(a for a, _, _ in ins) / n,
        "hit@3": sum(b for _, b, _ in ins) / n,
        "confident": sum(s == "answered" for _, _, s in ins) / n,
        "not_refused": sum(s != "refused" for _, _, s in ins) / n,
        "wrongly_confident": sum(s == "answered" for s in outs),
        "out_refused": sum(s == "refused" for s in outs),
        "out_total": len(outs),
    }, rows


def main(argv=None):
    quiet = "--quiet" in (argv if argv is not None else sys.argv[1:])
    status = 0
    for name in ("golden", "heldout"):
        s, rows = evaluate(HERE / f"{name}.json")
        print(f"== {name}.json  ({s['questions']} questions)")
        if not quiet:
            for kind, ok, question, got in rows:
                print(f"{'PASS' if ok else 'MISS'}  [{kind:3}] {question[:54]:54}  ->  {got}")
        print("answerable: hit@1 {:.0%} | hit@3 {:.0%} | confident {:.0%} | not refused {:.0%}".format(
            s["hit@1"], s["hit@3"], s["confident"], s["not_refused"]))
        print("out-of-scope: wrongly confident {} of {} | refused {} of {}\n".format(
            s["wrongly_confident"], s["out_total"], s["out_refused"], s["out_total"]))
        t = THRESHOLDS[name]
        failed = []
        if s["hit@3"] < t["hit@3"]:
            failed.append(f"hit@3 needs {t['hit@3']:.0%}")
        if s["not_refused"] < t["not_refused"]:
            failed.append(f"not refused needs {t['not_refused']:.0%}")
        if s["wrongly_confident"] > t["max_wrongly_confident"]:
            failed.append("an out-of-scope question got a confident answer")
        if failed:
            print(f"BELOW THRESHOLD ({name}): " + "; ".join(failed) + "\n")
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main())
