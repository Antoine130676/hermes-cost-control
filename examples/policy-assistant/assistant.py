#!/usr/bin/env python3
"""Policy assistant: answers HR / Finance policy questions from a folder of markdown files.

Design choices (each one is a guardrail a business team can understand):
  1. Retrieval first. Answers are the policy's own words with the file and section named. Nothing is invented.
  2. It refuses when it cannot find the answer, and says who to ask instead of guessing.
  3. Personal data in a question (email, phone, IBAN, long numbers) is redacted before anything else happens.
  4. An audit log records that a question was asked, whether it was answered and from which sections, but never the question text.
  5. Everything runs locally. The optional --llm mode talks only to a local Ollama server. No cloud calls, no dependencies.

Usage:
  python assistant.py "How much can I spend on a client dinner?"
  python assistant.py --llm "How many days of holiday do I get?"   # fluent answer from a local model, still cited
"""

import argparse
import hashlib
import json
import math
import re
import sys
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_POLICIES = HERE / "policies"
DEFAULT_AUDIT = HERE / "audit.jsonl"
MIN_SCORE = 3.0          # below this top score the assistant refuses
MIN_COVERAGE = 0.60      # answer: the best section holds at least this share of the question's meaningful words (rare words weigh more)
SUGGEST_COVERAGE = 0.30  # suggest: weaker evidence, so show the closest sections and say we are unsure; below this, refuse
# Both cut-offs were chosen from the tuning set (golden.json) only; heldout.json was kept out of the decision.
REFUSAL = ("I can't find this in the policies, so I won't guess. "
           "Please ask the People team (leave, remote work) or the Finance team (expenses, purchasing), "
           "or the Privacy team (data and AI tools).")

STOPWORDS = set("""a an and are as at be but by can do does for from how i if in is it its me my of on or our so than that the their
there these they this to us was we what when where which who whom why will with would you your should could may might must shall
get got have has had need needs want about any some also into out up over under per
am were been being did doing done having hi hello hey please thanks thank just really very quite tell ask let""".split())
# Hand-written synonyms: words people use that the policies phrase differently. One word can expand to several.
# This list is the main thing a policy owner maintains (see HANDOVER.md).
SYNONYMS = {"vacation": "holiday leave", "holiday": "holiday leave", "pto": "leave", "euros": "eur", "euro": "eur",
            "dinner": "meal", "lunch": "meal", "taxi": "travel", "plane": "flight", "flights": "flight", "wfh": "remote",
            "home": "remote", "erase": "delete", "erasure": "delete", "presents": "gift", "sign": "sign approve",
            "notice": "notice ahead advance", "cafe": "public wifi", "coffee": "public wifi", "died": "death",
            "dies": "death", "die": "death", "passed": "death", "stolen": "lost stolen", "steal": "stolen",
            "money": "eur", "cost": "eur spend", "price": "eur spend"}
for _country in ("spain france germany italy portugal poland finland sweden norway denmark latvia lithuania estonia "
                 "netherlands belgium austria greece ireland croatia hungary romania bulgaria czechia slovakia "
                 "cyprus malta slovenia luxembourg").split():
    SYNONYMS[_country] = "abroad"


def stem(word):
    """A deliberately small stemmer, applied to both the policies and the question so they meet in the middle."""
    for suffix in ("ing", "ed", "ly", "al", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            word = word[: -len(suffix)]
            break
    if len(word) > 4 and word.endswith("e"):
        word = word[:-1]
    if len(word) > 3 and word.endswith("y"):
        word = word[:-1] + "i"
    return word


def tokenize(text):
    out = []
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        for part in SYNONYMS.get(w, w).split():
            if part in STOPWORDS or len(part) < 2:
                continue
            out.append(stem(part))
    return out


# ---------------------------------------------------------------- privacy: redact before anything else
PII_PATTERNS = [
    ("email", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}(?:\s?[A-Z0-9]{1,4})?\b")),
    ("phone", re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d")),
    ("number", re.compile(r"\b\d{9,}\b")),
]


def redact(text):
    """Return (redacted_text, sorted list of categories found). Never returns the original values."""
    found = set()
    for name, pattern in PII_PATTERNS:
        if pattern.search(text):
            found.add(name)
            text = pattern.sub(f"[{name} removed]", text)
    return text, sorted(found)


# ---------------------------------------------------------------- loading and chunking
class Chunk:
    def __init__(self, source, heading, text):
        self.source, self.heading, self.text = source, heading, text
        self.tokens = tokenize(heading) * 2 + tokenize(text)   # headings count double


def load_chunks(policies_dir):
    chunks = []
    for path in sorted(Path(policies_dir).glob("*.md")):
        heading, body = None, []

        def flush():
            if heading and "".join(body).strip():
                chunks.append(Chunk(path.name, heading, " ".join(b.strip() for b in body if b.strip())))

        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("## "):
                flush()
                heading, body = line[3:].strip(), []
            elif heading is not None:
                body.append(line)
        flush()
    return chunks


class Index:
    """BM25 ranking over section-sized chunks, standard library only."""

    def __init__(self, chunks, k1=1.4, b=0.75):
        self.chunks, self.k1, self.b = chunks, k1, b
        self.n = len(chunks)
        self.avg = sum(len(c.tokens) for c in chunks) / max(self.n, 1)
        df = Counter()
        for c in chunks:
            df.update(set(c.tokens))
        self.idf = {t: math.log(1 + (self.n - d + 0.5) / (d + 0.5)) for t, d in df.items()}
        self.max_idf = math.log(1 + (self.n + 0.5) / 0.5)      # weight of a word that appears in no policy at all
        self.tf = [Counter(c.tokens) for c in chunks]

    def coverage(self, query, chunk):
        """Share of the question's meaningful words that this section contains, rare words counting more.
        A word found in no policy at all counts fully against the match, so 'share price' cannot ride on 'year'."""
        q = set(tokenize(query))
        if not q:
            return 0.0
        present = set(chunk.tokens)
        total = sum(self.idf.get(t, self.max_idf) for t in q)
        return sum(self.idf[t] for t in q if t in present) / total

    def search(self, query, top_k=3):
        q = set(tokenize(query))
        scored = []
        for chunk, tf in zip(self.chunks, self.tf):
            length = len(chunk.tokens)
            score = 0.0
            for t in q:
                if t in tf:
                    f = tf[t]
                    score += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * length / self.avg))
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda s: s[0], reverse=True)
        return scored[:top_k]


def best_sentence(query, chunk):
    """The sentence of a section that shares the most meaningful words with the question."""
    q = set(tokenize(query))
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", chunk.text) if s.strip()]
    if not sentences:
        return chunk.text
    return max(sentences, key=lambda s: len(q & set(tokenize(s))))


def build_prompt(question, hits):
    """Prompt for the optional local model. It only ever sees the retrieved excerpts."""
    excerpts = "\n\n".join(f"[{c.source} > {c.heading}]\n{c.text}" for _, c in hits)
    return ("You answer questions about company policy using ONLY the excerpts below. "
            "If the excerpts do not contain the answer, reply exactly: I can't find this in the policies. "
            "Quote numbers exactly. Finish with the sources in square brackets.\n\n"
            f"EXCERPTS:\n{excerpts}\n\nQUESTION: {question}\n\nANSWER:")


def ask_local_model(prompt, model="qwen2.5:14b-instruct", url="http://localhost:11434/api/generate", timeout=300):
    body = json.dumps({"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0}}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())["response"].strip()


def audit(path, redacted_question, pii, status, sources, mode):
    """Append one line per question. The question text itself is never written, only a short hash of the redacted text."""
    entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "question_hash": hashlib.sha256(redacted_question.encode()).hexdigest()[:12],
             "pii_redacted": pii, "status": status, "sources": sources, "mode": mode}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def answer(question, index, top_k=3, min_score=MIN_SCORE, audit_path=None, mode="retrieval",
           min_coverage=MIN_COVERAGE, suggest_coverage=SUGGEST_COVERAGE):
    """Three outcomes: 'answered' (strong evidence), 'suggest' (closest sections, we are unsure) or 'refused'."""
    redacted, pii = redact(question)
    # the "[email removed]" placeholders must not take part in the search, or they count as unknown words
    query = re.sub(r"\[[a-z]+ removed\]", " ", redacted)
    hits = index.search(query, top_k)
    coverage = index.coverage(query, hits[0][1]) if hits else 0.0
    if hits and hits[0][0] >= min_score and coverage >= min_coverage:
        status = "answered"
    elif hits and hits[0][0] >= min_score and coverage >= suggest_coverage:
        status = "suggest"
    else:
        status = "refused"
    sources = [f"{c.source} > {c.heading}" for _, c in hits] if status != "refused" else []
    if audit_path:
        audit(audit_path, redacted, pii, status, sources, mode)
    return {"status": status, "answered": status == "answered", "coverage": round(coverage, 2),
            "question_redacted": redacted, "pii_redacted": pii,
            "hits": [(round(s, 2), c) for s, c in hits] if status != "refused" else [], "sources": sources}


def main(argv=None):
    p = argparse.ArgumentParser(description="Ask a question about the company policies.")
    p.add_argument("question")
    p.add_argument("--dir", default=str(DEFAULT_POLICIES))
    p.add_argument("--top-k", type=int, default=3)
    p.add_argument("--llm", action="store_true", help="phrase the answer with a local Ollama model (still cited)")
    p.add_argument("--model", default="qwen2.5:14b-instruct")
    p.add_argument("--no-audit", action="store_true")
    a = p.parse_args(argv)

    index = Index(load_chunks(a.dir))
    result = answer(a.question, index, a.top_k, audit_path=None if a.no_audit else DEFAULT_AUDIT,
                    mode="llm" if a.llm else "retrieval")
    if result["pii_redacted"]:
        print(f"(Personal data removed from your question: {', '.join(result['pii_redacted'])})\n")
    if result["status"] == "refused":
        print(REFUSAL)
        return 0
    if result["status"] == "suggest":
        print("I'm not sure these answer your question, so please confirm with the owning team. Closest sections:\n")
        for s, c in result["hits"]:
            print(f"  - {c.source} > {c.heading}: {best_sentence(result['question_redacted'], c)}")
        return 0
    if a.llm:
        try:
            print(ask_local_model(build_prompt(result["question_redacted"], [(s, c) for s, c in result["hits"]]), a.model))
            print()
        except Exception as e:  # local model not running: fall back to the policy text itself
            print(f"(Local model not available: {e}. Showing the policy text instead.)\n")
    score, top = result["hits"][0]
    if not a.llm:
        print(top.text + "\n")
    print(f"Source: {result['sources'][0]}")
    if len(result["sources"]) > 1:
        print("Related sections: " + "; ".join(result["sources"][1:]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
