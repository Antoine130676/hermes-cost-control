# Handover guide: running the policy assistant yourself

For the person (or team) who owns the policies: People, Finance, or whoever answers the same questions again and again. You do not need to write code. You edit text files and run one check.

## What it is, in one paragraph
Employees ask a question. The assistant finds the section of your policies that best matches and shows it, with the file and section name. If it is unsure it shows the closest sections and says it is unsure. If nothing matches it says it cannot find the answer and tells the person who to ask. It never makes up an answer, and it never stores what people typed.

## Who owns what
| Thing | Owner |
|---|---|
| The policy text | You (People / Finance / Privacy, per file) |
| The check questions (`golden.json`) | You, with help from whoever fields the questions today |
| The tool itself (`assistant.py`) | The IT partner who set it up |
| Anything involving personal data, retention or legal wording | Privacy and Legal (see the checklist below) |

## Update a policy
1. Open the file in `policies/` (they are plain text; any editor works).
2. Keep **one topic per section**, and keep each section heading starting with `## `. The heading is part of how the assistant finds the section, so make it say what the section is about ("Sick leave", not "Section 3").
3. Use the words people actually use. If employees say "vacation" and the policy says "annual leave", either mention both in the text or ask your IT partner to add the word to the synonym list.
4. Save, then run the check below **before** telling anyone the change is live.

## Check nothing broke (about 10 seconds)
Run `python evaluate.py`. It asks about 36 sample questions and prints two summaries.
- **"wrongly confident" must be 0.** That means it never gave a confident answer to something the policies do not cover. If this is not 0, do not publish; ask your IT partner.
- **"not refused" should stay at 90% or more.** If it drops, your edit probably changed a heading or removed words people use.
- If the check fails, the message says which score dropped. Undo your last edit and try again, or ask your IT partner.

## Teach it the questions people really ask
Every time a real question is answered badly, add it to `golden.json` with the section that should answer it, then run the check. Over a few weeks this becomes your own test of what matters. Questions you add to `golden.json` while fixing something are no longer an independent test; keep writing fresh questions in `heldout.json` for that.

## Read the audit log (once a week)
`audit.jsonl` has one line per question: when, the outcome (`answered`, `suggest`, `refused`), the sections used, and which kinds of personal data were removed. It does **not** contain the question. Look for:
- many `refused` or `suggest` outcomes: your policies may not cover something people keep asking about. That is a gap to fill, and the most useful thing the log tells you.
- many `pii_redacted` entries: people are pasting personal data into questions. Remind them not to.

## What the assistant must never do
- Answer from anything other than your policies.
- Give a confident answer when the evidence is weak.
- Keep the text people typed, or send it outside this machine.

If you ever see it do any of these, stop using it and tell your IT partner.

## Before a wider rollout: route these to Privacy and Legal
The assistant works with employees' questions, so these are decisions for the people who own that risk, not for the builder:
1. **Retention of the audit log.** How long may it be kept, and who may read it?
2. **Whether questions can contain personal data.** The assistant removes obvious patterns (emails, phone numbers, IBANs, long numbers), but names and free text can still get through. Is that acceptable, or does the rollout need training and a warning on the entry screen?
3. **Where it runs and what, if anything, leaves the machine.** In the standard setup nothing does. If anyone switches on the optional language-model mode, confirm which model it is, where it runs, and that it only ever sees policy excerpts.
4. **Who may edit the policies,** and how a change is approved before it goes live.
5. **What it must say to employees.** For example, that it is a convenience and the policy text is the authority.

Get a named approver for each item before the first pilot.

## Suggested pilot
1. Pick one function (for example Finance) and one policy.
2. Collect 30 to 50 real questions from the last month (from email or chat), remove personal data, and put them in `golden.json` with the right section.
3. Run the check first. The result is your honest starting point for **that** policy, not the demo's.
4. Run it for two weeks with one team. Read the audit log weekly.
5. Decide with the team: extend, change, or stop. If the confident-answer rate is low, the fix is usually better section headings and a longer synonym list, not a more powerful model.
