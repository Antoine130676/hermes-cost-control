#!/usr/bin/env python3
"""
ask-local.py — Local-only RAG + Ollama answer pipeline. Zero Claude tokens.

Retrieves relevant chunks from the local Chroma index (hermes-projects or
hermes-skills) and asks a local Ollama model to answer using only that
context. Use this for lookup-style questions: "what did we find on X",
"what does skill Y say about Z", "what's the price/detail in project log W".

NOT suitable for: anything needing live browser/web access, image
generation, multi-step tool orchestration, or design/creative judgment
calls (redesign mockups, GSAP-vs-Motion decisions, industry reads) —
those need an agent with tools and reasoning, i.e. Claude in Hermes.

Usage:
  python ask-local.py "your question"                       # auto: tries hermes-projects then hermes-skills
  python ask-local.py --skills "your question"               # search skills collection only
  python ask-local.py --projects "your question"             # search project logs only
  python ask-local.py --model qwen3:14b "your question"      # pick a different local model
"""

import sys
import json
import urllib.request
from pathlib import Path

import chromadb

RAG_DIR = Path(__file__).parent / "rag-index"
OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen2.5:14b-instruct"


def retrieve(collection_name, query, top_k=4):
    client = chromadb.PersistentClient(path=str(RAG_DIR))
    try:
        collection = client.get_collection(name=collection_name)
    except Exception:
        return []
    results = collection.query(query_texts=[query], n_results=top_k)
    if not results['documents'] or not results['documents'][0]:
        return []
    out = []
    for doc, meta, dist in zip(results['documents'][0], results['metadatas'][0], results['distances'][0]):
        out.append({"text": doc, "meta": meta, "score": 1 - dist})
    return out


def ask_ollama(model, question, context_chunks):
    context_text = "\n\n---\n\n".join(
        f"[Source: {c['meta'].get('source', '?')}]\n{c['text']}" for c in context_chunks
    )
    prompt = (
        "Answer the question using ONLY the context below. "
        "If the context doesn't contain the answer, say so plainly — do not guess.\n\n"
        f"CONTEXT:\n{context_text}\n\n"
        f"QUESTION: {question}\n\n"
        "ANSWER:"
    )
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8")
    req = urllib.request.Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=550) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return result.get("response", "").strip()


def main():
    args = sys.argv[1:]
    model = DEFAULT_MODEL
    force_collection = None

    if "--model" in args:
        idx = args.index("--model")
        model = args[idx + 1]
        del args[idx:idx + 2]
    if "--skills" in args:
        force_collection = "hermes-skills"
        args.remove("--skills")
    elif "--projects" in args:
        force_collection = "hermes-projects"
        args.remove("--projects")

    if not args:
        print(__doc__)
        sys.exit(1)

    question = " ".join(args)

    if force_collection:
        chunks = retrieve(force_collection, question)
        used_collection = force_collection
    else:
        # auto mode: try projects first, fall back to skills if weak match
        chunks = retrieve("hermes-projects", question)
        used_collection = "hermes-projects"
        if not chunks or chunks[0]["score"] < 0.35:
            skill_chunks = retrieve("hermes-skills", question)
            if skill_chunks and (not chunks or skill_chunks[0]["score"] > chunks[0]["score"]):
                chunks = skill_chunks
                used_collection = "hermes-skills"

    if not chunks:
        print("[LOCAL] No relevant context found in either collection. This likely needs Claude — nothing local to ground an answer in.")
        sys.exit(0)

    print(f"[LOCAL: {model} | collection: {used_collection} | top match: {chunks[0]['score']:.0%}]\n")
    answer = ask_ollama(model, question, chunks)
    print(answer)
    print(f"\n--- sources: {', '.join(sorted(set(c['meta'].get('source', '?') for c in chunks)))} ---")


if __name__ == "__main__":
    main()
