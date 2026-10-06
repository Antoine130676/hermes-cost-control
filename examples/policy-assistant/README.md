# Policy assistant: a small, safe AI tool for an HR or Finance team

A working example of the kind of AI tool a business function can own: employees ask questions about the company's policies in plain language, and the assistant answers **from the policies themselves**, names the section it used, and says so when it does not know.

It runs on the standard library only, keeps everything on the local machine, and comes with an evaluation set and a handover guide so the team that owns the policies can run and maintain it without an engineer. The policies in this folder are fictional ("Example Co") and exist only for the demo.

## What it does

```
$ python assistant.py "How many days of vacation do I get and can I carry some over?"
Every full-time employee gets 25 working days of annual leave (holiday) per year. Up to five unused
days can be carried into the next year and must be used by 31 March.

Source: leave.md > Annual leave
Related sections: leave.md > Public holidays; leave.md > Requesting leave
```

```
$ python assistant.py "Can I fly business class to Singapore?"
I'm not sure these answer your question, so please confirm with the owning team. Closest sections:

  - expenses.md > Travel: Business class for flights over six hours needs director approval before booking.
  - expenses.md > Mileage: Use of a private car for approved business trips is paid at 0.30 euros per kilometre.
  - expenses.md > Corporate cards: Company cards are for business spend only.
```

```
$ python assistant.py "What is the best pizza topping?"
I can't find this in the policies, so I won't guess. Please ask the People team (leave, remote work) or the
Finance team (expenses, purchasing), or the Privacy team (data and AI tools).
```

Three outcomes, on purpose: **answer** when the evidence is strong, **suggest** the closest sections (labelled as unsure) when it is weaker, **refuse** when nothing relevant matches.

## Guardrails built in

| Guardrail | What it means for the team |
|---|---|
| Answers are the policy's own words with the section named | Nothing is invented, and every answer can be checked |
| It refuses instead of guessing | A wrong confident answer about leave or expenses is worse than "ask People" |
| Personal data in a question is redacted first | Emails, phone numbers, IBANs and long ID numbers are removed before anything else happens |
| The audit log never stores the question | It records that a question was asked, the outcome and the sections used, with only a short hash of the redacted text |
| Everything runs locally | No cloud calls and no dependencies. The optional `--llm` flag talks only to a local Ollama server |

## How well does it work? Measured, with its limits

`python evaluate.py` runs two sets of questions. **`golden.json`** (23 questions) was used while building and setting the cut-offs. **`heldout.json`** (13 questions) was written before tuning and was not used for it.

| | Tuning set | Held-out set |
|---|---|---|
| Right section ranked first | 95% | 100% |
| Right section in the top three | 100% | 100% |
| Answered with confidence | 63% | 60% |
| Answerable question never refused | 100% | 90% |
| Out-of-scope question answered confidently | **0 of 4** | **0 of 3** |

Read these numbers with care:
- **Synthetic data.** I wrote both the policies and the questions. Real policies are longer and messier, and real employees ask stranger questions. These figures show the design works, not that it would score the same on a real corpus.
- **Small sets.** 36 questions in total, so one question moves a score by several points. The one held-out miss ("Can I take unpaid time off for a few weeks?") shares too few words with the policy and was refused.
- **Roughly 60% confident answers.** The rest are suggestions. That is the price of never answering confidently outside the policies, and it is the number to improve with real questions.
- **Keyword retrieval with hand-written synonyms.** It does not understand paraphrase beyond that list. An embedding model would help; so would a bigger synonym list, which is the main thing a policy owner maintains.
- **The `--llm` answers are not covered by the evaluation.** The model only ever sees the retrieved excerpts and is told to refuse when they do not contain the answer, but I have not measured its faithfulness.
- Two fixes came out of reading real outputs rather than the scores: a redaction placeholder was making answerable questions look unanswerable, and a few missing filler words ("am", "been") lowered matches. Both now have tests.

## Run it

```bash
python assistant.py "How much can I spend on a client dinner?"
python evaluate.py                    # both question sets; exits non-zero if a score drops below its threshold
python -m unittest discover -s ../../tests    # the tests, including the evaluation thresholds
python assistant.py --llm "..."       # optional: a fluent, still cited answer from a local Ollama model
```

## Handing it to a team

[HANDOVER.md](HANDOVER.md) is written for the person who owns the policies, not for an engineer: how to update a policy, how to check nothing broke before publishing, how to read the audit log to find gaps in the policies, and which decisions need Privacy and Legal sign-off before a rollout.

## Files

| File | Purpose |
|---|---|
| `policies/*.md` | The fictional policies. One topic per `##` section |
| `assistant.py` | Retrieval, redaction, refusal, audit log, optional local model |
| `evaluate.py`, `golden.json`, `heldout.json` | The evaluation and its two question sets |
| `HANDOVER.md` | The owner's guide |
