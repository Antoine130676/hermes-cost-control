# Hermes Cost Control

[![tests](https://github.com/Antoine130676/hermes-cost-control/actions/workflows/tests.yml/badge.svg)](https://github.com/Antoine130676/hermes-cost-control/actions/workflows/tests.yml) [![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Guardrails for running AI agents without surprise bills: a provider lock and monitor, a tiered router that sends each task to the cheapest suitable model, and a fully local RAG setup (ChromaDB plus Ollama) that answers lookup questions with zero cloud tokens.

Built around Hermes Agent (by Nous Research) with Ollama as the local model runner. This repo contains my own scripts only; it does not include Hermes, Ollama or OmniRoute.

> **Status: working tools; routing savings not yet declared.** The routing and the guardrails are built and tested. The per-token price comparison below is measured and calculated from real usage. The saving the router delivers is a projection until I have a clean week of data. Nothing here claims a percentage saved by routing.

## Why I built it

Over 30 days my agent spend was about **$64** (Anthropic $33.86 and Nous Portal $30.16, read from the provider dashboards on 3 Oct 2026). On 30 Sep a dropped connection made the agent **silently fail over from a cheap model to a premium one** mid-request, which cost an unexpected **$23.35**. That incident drove the design: cheap by default, premium only on purpose, and an alarm when anything switches.

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

## What is measured so far

All figures are from my own usage. **Measured** means read from a provider page; **calculated** means derived from measured tokens and published prices.

**Nous Portal, last 30 days (usage page, read 6 Oct 2026), Kimi K2 Thinking:**

| | |
|---|---|
| Spend | $31.47 (measured) |
| Tokens | 93.7M: 10.7M uncached input, 0.6M output, 82.4M cache reads, no cache writes (measured) |
| Blended rate | about **$0.34 per million tokens**; 88% of tokens are cache reads (calculated) |

**Same tokens, priced at Anthropic's published rates** (Sonnet 5: $2 in, $10 out, $0.20 cache read), calculated:

| Model | Cost for the same 93.7M tokens | Per million |
|---|---|---|
| Kimi K2 Thinking on Nous | $31.47 (measured) | $0.34 |
| Claude Sonnet 5 | $43.84 | $0.47 |

Kimi K2 Thinking is about **28% cheaper per token than Sonnet 5** on this token mix. The comparison treats the two as comparable reasoning models. Quality was not benchmarked here, and Claude cache writes are ignored, which makes the Sonnet figure slightly low.

**What is not declared yet**
- The saving from the router and guardrails. Spend dropped sharply after the routing began (the Nous chart shows about $27 of the $31.47 on 30 Sep and 1 Oct, the day of the provider-switch incident, then under $1 a day from 3 Oct), but the account balance was also nearly exhausted, so the drop cannot be credited to routing.
- The Anthropic side. I have not yet read the usage by model from the Anthropic console.
- A full normal week with credits available. That is the measurement I will publish.

## The RAG part: a real before and after

The local lookup could not find client audit reports, because the indexer only read top-level markdown files and the reports live in subfolders. Same question, before and after the fix (index rebuilt to read subfolders):

| | Before | After |
|---|---|---|
| Project index | 55 chunks | 752 chunks from 55 files |
| Top retrieval match | -31% | 19% |
| Answer | "The context does not contain this information" | Lists the missing security headers (HSTS, X-Frame-Options, Content-Security-Policy) |

Honest limits: the answer was incomplete (it missed two of the headers), drew part of its text from a different report, and each local answer takes about two minutes on my current hardware. It suits lookups, not precise reporting.

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

1. Publish the measured weekly spend against the $64 baseline, once a full week is in.
2. Keep retrieval inside one client's notes when the question names that client.
3. Wire the expensive tier into the cost router.

## License

MIT, see [LICENSE](LICENSE).

## Author

Anthony D'Souza. Technical delivery leader building production AI agent pipelines. See also [geo-seo-agent-pipeline](https://github.com/Antoine130676/geo-seo-agent-pipeline).
