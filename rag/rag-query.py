#!/usr/bin/env python3
"""
Chroma RAG Query Tool
Query your indexed Hermes projects and skills locally.

Usage:
  python rag-query.py "your search query"                  # searches project logs (default)
  python rag-query.py --skills "your search query"          # searches installed skills
  python rag-query.py --collection hermes-skills "query"    # explicit collection name
"""

import sys
import chromadb
from pathlib import Path

rag_dir = Path(__file__).parent / "rag-index"
client = chromadb.PersistentClient(path=str(rag_dir))


def search(collection_name, query, top_k=5):
    try:
        collection = client.get_collection(name=collection_name)
    except Exception:
        print(f"Collection '{collection_name}' not found. Run rag-index.py first.")
        return

    results = collection.query(query_texts=[query], n_results=top_k)

    if not results['documents'] or not results['documents'][0]:
        print(f"No results found for: {query}")
        return

    print(f"\n=== RAG Search Results for: '{query}' (collection: {collection_name}) ===\n")

    for i, (doc, meta, dist) in enumerate(
        zip(results['documents'][0],
            results['metadatas'][0],
            results['distances'][0])
    ):
        label = meta.get('project') or meta.get('skill') or meta.get('source', '?')
        print(f"[Result {i+1}] Source: {meta.get('source', '?')} | {label}")
        print(f"Relevance Score: {1 - dist:.2%}")
        print(f"Content:\n{doc[:400]}...\n")
        print("-" * 80 + "\n")


if __name__ == "__main__":
    args = sys.argv[1:]
    collection_name = "hermes-projects"

    if "--skills" in args:
        collection_name = "hermes-skills"
        args.remove("--skills")
    elif "--collection" in args:
        idx = args.index("--collection")
        collection_name = args[idx + 1]
        del args[idx:idx + 2]

    if not args:
        print(__doc__)
        sys.exit(1)

    query = " ".join(args)
    search(collection_name, query)
