# Hermes Cost Control

[![tests](https://github.com/Antoine130676/hermes-cost-control/actions/workflows/tests.yml/badge.svg)](https://github.com/Antoine130676/hermes-cost-control/actions/workflows/tests.yml) [![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Guardrails for running AI agents without surprise bills: a provider lock and monitor, a tiered router that sends each task to the cheapest suitable model, and a fully local RAG setup (ChromaDB plus Ollama) that answers lookup questions with zero cloud tokens.

Built around Hermes Agent (by Nous Research) with Ollama as the local model runner. This repo contains my own scripts only; it does not include Hermes, Ollama or OmniRoute.

> **Status: working tools; routing savings not yet declared.** The routing and the guardrails are built and tested. The per-token price comparison below is measured and calculated from real usage. The saving the router delivers is a projection until I have a clean week of data. Nothing here claims a percentage saved by routing.

## Why I built it

Over 30 days my agent spend was about **$65** across two providers (Anthropic $33.85 and Nous Portal $31.47, read from the provider consoles on 6 Oct 2026). On 30 Sep a dropped connection made the agent **silently switch from Kimi to Claude** in the middle of a long session. The Anthropic spend over 28 to 30 Sep was about $21, and I cannot separate how much of it the switch alone caused. That incident drove the design: cheap by default, premium only on purpose, and an alarm when anything switches.

## How it fits together

```
request
   |
Smart router ---- classifies the task, picks a tier, logs the decision
   |-- FREE ------ simple terminal / file / network commands --> local Ollama model ($0)
   |-- CHEAP ----- search, research, audits ------------------> low-cost hosted model
   |-- EXPENSIVE - browser automation, sub-agents ------------> warned, alternative suggested
   |
Provider monitor - watches the agent log, blocks unapproved provider switches, alerts near a spend threshold
Cost tracker ----- estimates cost per model per request, with per-million-token pricing
   |
Local RAG -------- ChromaDB + local embeddings --> Ollama answers lookups, no cloud call
```

| Folder | What it does |
|---|---|
| [`router/`](router/router.py) | Classifies a natural-language request into FREE, CHEAP or EXPENSIVE_WARNING and logs each decision |
| [`cost/`](cost/) | Task classifier, per-model cost estimates and a guard script that warns before expensive operations |
| [`monitor/`](monitor/) | Watches the agent log for provider switches, blocks unapproved ones, alerts near a threshold |
| [`rag/`](rag/) | Builds a local Chroma index of project notes and agent skills, and answers questions from it with a local model |
| [`tests/`](tests/) | 13 tests for routing, cost estimates and path safety; run on Linux and Windows in CI |
| [`examples/policy-assistant/`](examples/policy-assistant/) | A small policy assistant for an HR or Finance team: cited answers, refusals, privacy redaction, an audit log, an evaluation set and a handover guide |

## What is measured so far

All figures are from my own usage over the last 30 days, read from the provider consoles on 6 Oct 2026. **Measured** means read from a provider page; **calculated** or **estimated** means derived.

| | Anthropic API (Claude) | Nous Portal (Kimi K2 Thinking) |
|---|---|---|
| Spend | $33.85 | $31.47 |
| Tokens | 101.9M (101.3M in, 0.5M out) | 93.7M (10.7M uncached in, 0.6M out, 82.4M cache reads) |
| Blended rate | about $0.33 per million tokens | about $0.34 per million tokens |

Combined: about **$65 on 196M tokens**. Hermes' own token counts agree with the Anthropic console to within 3%.

**Reading the per-token rates.** The Claude figure is a blend of Sonnet 5 and Haiku 4.5 (about two thirds and one third of tokens, from Hermes), and it includes cache writes, which Nous does not charge. Splitting it by that mix gives an estimated Sonnet-only rate of about $0.41 per million, so **Kimi K2 Thinking is roughly 17% cheaper per token than Sonnet 5**. Priced at Anthropic's published rates with no cache writes, the gap is 28%. I treat the true figure as somewhere between the two until the console is read grouped by model. The comparison assumes the two are comparable reasoning models; quality was not benchmarked here.

**A measured result.** Anthropic spend was **$0.00 from 1 Oct to 6 Oct**, after the provider lock went in. That is by design (the lock removes the other providers' keys), so it shows the lock works, not that cost fell.

**What is not declared yet**
- The saving the router delivers. Nous spend was about $27 of its $31.47 on 30 Sep and 1 Oct, then under $1 a day from 3 Oct, but the Nous balance was also nearly exhausted, so the drop cannot be credited to routing.
- The cost of the incident itself. The Anthropic console shows about $21 across 28 to 30 Sep, which covers the whole long session in which the switch happened, so the part caused by the switch alone is not separable.
- Usage grouped by model on the Anthropic side, and a full normal week with credits available. That is the measurement I will publish.

## The RAG part: a real before and after

The local lookup could not find client audit reports, because the indexer only read top-level markdown files and the reports live in subfolders. Same question, before and after the fix (index rebuilt to read subfolders):

| | Before | After |
|---|---|---|
| Project index | 55 chunks | 752 chunks from 55 files |
| Top retrieval match | -31% | 19% |
| Answer | "The context does not contain this information" | Lists the missing security headers (HSTS, X-Frame-Options, Content-Security-Policy) |

Honest limits: the answer was incomplete (it missed two of the headers), drew part of its text from a different report, and each local answer takes about two minutes on my current hardware. It suits lookups, not precise reporting.

## Example: a policy assistant for a business team

[`examples/policy-assistant/`](examples/policy-assistant/) shows the same ideas applied to a team that is not technical. Employees ask about HR or Finance policies; the assistant answers from the policies with the section named, says so when it is unsure, and refuses when nothing matches. Personal data is redacted from questions, the audit log never stores the question, and everything runs locally with no dependencies.

It has two evaluation sets, one used for tuning and one held out. On the held-out set the right section was ranked first for 100% of answerable questions, no out-of-scope question got a confident answer, and one answerable question was refused. The policies and questions are synthetic and the sets are small, so treat the figures as a demonstration of the method, not a benchmark; the README there lists the limits. A plain-language [handover guide](examples/policy-assistant/HANDOVER.md) covers how a team updates it, checks it and routes the privacy decisions before a rollout.

## Bugs the tests found

Writing the tests exposed three real bugs, all fixed here:
- An unknown model name crashed the cost estimate (the default pricing had no name).
- The cost router never recognised `curl -I`, because the pattern was uppercase and the input was lowercased.
- A bare `ls` with no arguments fell through to the cheap tier instead of the free one.

## Run it

```bash
python -m unittest discover -s tests          # routing, cost and path tests, no extra dependencies
python router/router.py "check example.com"   # see which tier a request would take
python cost/cost_router.py "curl -I https://example.com"
```

The RAG scripts need `chromadb` and a running Ollama with a model such as `qwen2.5:14b-instruct`:

```bash
export HERMES_PROJECTS_DIR=~/hermes-projects    # notes to index (all *.md, subfolders included)
export HERMES_SKILLS_DIR=~/hermes/skills        # SKILL.md files to index
python rag/rag-index.py
python rag/ask-local.py --projects "your question"
```

Everything runs locally. Indexes and logs are git-ignored, because they can contain private notes.

## Known limitations

- The cost router defines an "expensive" tier but does not act on it; the smart router handles the warning instead.
- Cost figures in the tracker are estimates and ignore cache pricing. Provider dashboards are the authority. Claude prices were checked against Anthropic's pricing page on 6 Oct 2026 and will drift.
- OmniRoute is configured as an extra routing gateway in my setup, but this repo does not depend on it.
- Local model answers are slow and sometimes mix sources.

## Next

1. Publish the measured weekly spend against the $65 baseline, once a full week with credits is in, and read the Anthropic console grouped by model.
2. Keep retrieval inside one client's notes when the question names that client.
3. Wire the expensive tier into the cost router.

## License

MIT, see [LICENSE](LICENSE).

## Author

Anthony D'Souza. Technical delivery leader building production AI agent pipelines. See also [geo-seo-agent-pipeline](https://github.com/Antoine130676/geo-seo-agent-pipeline).
