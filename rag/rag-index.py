#!/usr/bin/env python3
"""
Hermes RAG Indexer
Builds/refreshes two local Chroma collections:
  - hermes-projects : client project logs and reports ($HERMES_PROJECTS_DIR/**/*.md, subfolders included)
  - hermes-skills   : installed Hermes skills ($HERMES_SKILLS_DIR/**/SKILL.md)

Fully local: uses ChromaDB's bundled DefaultEmbeddingFunction (all-MiniLM-L6-v2 ONNX),
no API calls, no Claude/OpenAI dependency. Safe to re-run any time to pick up new
or changed files -- each collection is fully rebuilt from disk on every run (the
corpus is small enough that a full rebuild is fast and avoids stale-chunk drift).

Usage:
  python rag-index.py                 # rebuild both collections
  python rag-index.py --projects-only # rebuild only client project logs
  python rag-index.py --skills-only   # rebuild only skills
"""

import os
import sys
import re
from pathlib import Path

import chromadb

PROJECTS_DIR = Path(os.environ.get("HERMES_PROJECTS_DIR", Path.home() / "hermes-projects"))
SKILLS_DIR = Path(os.environ.get("HERMES_SKILLS_DIR", Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share")) / "hermes" / "skills"))
RAG_DIR = Path(__file__).parent / "rag-index"

# Files/dirs under hermes-projects to skip (not client logs)
SKIP_NAMES = {"rag-index", "rag-query.py", "rag-index.py", "mydoner-redesign"}
SKIP_DIRS = {"rag-index", "tools", "mydoner-redesign", "node_modules", ".vercel", "assets", "templates"}

CHUNK_SIZE = 1500     # chars, used as fallback when a section has no headers
CHUNK_OVERLAP = 200


def split_by_headers(text: str, min_header_level: int = 2) -> list[str]:
    """Split markdown on ## (or deeper) headers. Falls back to the whole text
    as one chunk if no headers are found, or if a section is still huge."""
    pattern = re.compile(r"(?=^#{" + str(min_header_level) + r",6}\s)", re.MULTILINE)
    parts = [p.strip() for p in pattern.split(text) if p.strip()]
    if not parts:
        return [text.strip()] if text.strip() else []
    return parts


def fixed_chunks(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    if len(text) <= size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


def chunk_document(text: str) -> list[str]:
    """Header-aware chunking: split on ## headers first, then further split
    any section still too large into fixed-size overlapping chunks."""
    sections = split_by_headers(text)
    out = []
    for s in sections:
        if len(s) > CHUNK_SIZE * 1.5:
            out.extend(fixed_chunks(s))
        else:
            out.append(s)
    return out or ([text.strip()] if text.strip() else [])


def rebuild_projects_collection(client):
    print("Indexing client project logs...")
    try:
        client.delete_collection("hermes-projects")
    except Exception:
        pass
    collection = client.create_collection(name="hermes-projects")

    docs, metas, ids = [], [], []
    # Search subfolders too (client audits and reports live in <client>/audits, <client>/reports,
    # <client>/docs and personal/research). Skip generated, vendored or non-log folders.
    md_files = sorted(
        f for f in PROJECTS_DIR.rglob("*.md")
        if f.name not in SKIP_NAMES
        and not any(part in SKIP_DIRS for part in f.relative_to(PROJECTS_DIR).parts[:-1])
    )
    for f in md_files:
        rel = f.relative_to(PROJECTS_DIR).as_posix()
        text = f.read_text(encoding="utf-8", errors="ignore")
        chunks = chunk_document(text)
        top = rel.split("/")[0] if "/" in rel else "root"
        for i, chunk in enumerate(chunks):
            docs.append(chunk)
            metas.append({
                "source": rel,
                "project": top if "/" in rel else f.stem,
                "chunk_index": i,
            })
            ids.append(f"{rel}__{i}")
        print(f"  {rel}: {len(chunks)} chunk(s)")

    if docs:
        collection.add(documents=docs, metadatas=metas, ids=ids)
    print(f"hermes-projects: {len(docs)} chunks from {len(md_files)} files\n")
    return len(docs), len(md_files)


def rebuild_skills_collection(client):
    print("Indexing installed skills...")
    try:
        client.delete_collection("hermes-skills")
    except Exception:
        pass
    collection = client.create_collection(name="hermes-skills")

    docs, metas, ids = [], [], []
    skill_files = sorted(SKILLS_DIR.glob("**/SKILL.md"))
    for f in skill_files:
        try:
            rel = f.relative_to(SKILLS_DIR)
        except ValueError:
            rel = f
        parts = rel.parts
        category = parts[0] if len(parts) > 1 else "uncategorized"
        skill_name = parts[-2] if len(parts) >= 2 else f.stem

        text = f.read_text(encoding="utf-8", errors="ignore")
        # Strip YAML frontmatter for cleaner embedding, keep it as metadata note
        text_body = re.sub(r"^---.*?---\s*", "", text, flags=re.DOTALL)
        chunks = chunk_document(text_body)
        for i, chunk in enumerate(chunks):
            docs.append(chunk)
            metas.append({
                "source": str(rel).replace("\\", "/"),
                "skill": skill_name,
                "category": category,
                "chunk_index": i,
            })
            ids.append(f"{category}__{skill_name}__{i}")
        print(f"  {rel}: {len(chunks)} chunk(s)")

    if docs:
        # Chroma add() in batches to avoid single huge calls on very large corpora
        BATCH = 200
        for start in range(0, len(docs), BATCH):
            end = start + BATCH
            collection.add(
                documents=docs[start:end],
                metadatas=metas[start:end],
                ids=ids[start:end],
            )
    print(f"hermes-skills: {len(docs)} chunks from {len(skill_files)} skill files\n")
    return len(docs), len(skill_files)


def main():
    args = sys.argv[1:]
    do_projects = "--skills-only" not in args
    do_skills = "--projects-only" not in args

    RAG_DIR.mkdir(exist_ok=True)
    client = chromadb.PersistentClient(path=str(RAG_DIR))

    total_chunks = 0
    if do_projects:
        c, _ = rebuild_projects_collection(client)
        total_chunks += c
    if do_skills:
        c, _ = rebuild_skills_collection(client)
        total_chunks += c

    print(f"Done. Total chunks indexed: {total_chunks}")
    print(f"Index location: {RAG_DIR}")


if __name__ == "__main__":
    main()
