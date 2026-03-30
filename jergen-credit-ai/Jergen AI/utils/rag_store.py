"""
RAG vector-store utilities using ChromaDB (local persistent mode).

Manages ingestion of reference dispute-letter templates from the
``Agent RAGs/`` directory and similarity retrieval at query time.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import chromadb

logger = logging.getLogger(__name__)


# ── Store Initialization ─────────────────────────────────────────────────────

def init_store(
    persist_dir: str | Path,
    collection_name: str = "dispute_letter_templates",
) -> chromadb.Collection:
    """Create or load a persistent ChromaDB collection.

    Args:
        persist_dir: Directory for ChromaDB's persistent storage files.
        collection_name: Name of the vector collection.

    Returns:
        A ``chromadb.Collection`` ready for upsert / query operations.
    """
    persist_dir = Path(persist_dir)
    persist_dir.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(persist_dir))
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )
    logger.info(
        "ChromaDB collection '%s' loaded (%d existing documents).",
        collection_name,
        collection.count(),
    )
    return collection


# ── Document Ingestion ───────────────────────────────────────────────────────

def _read_file_text(file_path: Path) -> str:
    """Read text content from a supported file format (.txt, .md, .docx, .pdf)."""
    suffix = file_path.suffix.lower()

    if suffix == ".txt":
        return file_path.read_text(encoding="utf-8", errors="ignore")

    if suffix == ".md":
        return file_path.read_text(encoding="utf-8", errors="ignore")

    if suffix == ".docx":
        from docx import Document

        doc = Document(str(file_path))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

    if suffix == ".pdf":
        from utils.pdf_utils import extract_text_from_pdf

        return extract_text_from_pdf(file_path)

    logger.warning("Unsupported file type skipped: %s", file_path)
    return ""


def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Split text into overlapping chunks by approximate word count.

    Args:
        text: Source text to chunk.
        chunk_size: Target number of words per chunk.
        overlap: Number of overlapping words between consecutive chunks.

    Returns:
        List of text chunks.
    """
    words = text.split()
    if len(words) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start += chunk_size - overlap

    return chunks


def ingest_reference_docs(
    collection: chromadb.Collection,
    docs_path: str | Path,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> int:
    """Read all reference documents from a folder, chunk them, and upsert into ChromaDB.

    Supported file types: ``.txt``, ``.docx``, ``.pdf``

    Args:
        collection: Target ChromaDB collection.
        docs_path: Path to the directory containing reference templates.
        chunk_size: Words per chunk.
        chunk_overlap: Overlapping words between chunks.

    Returns:
        Number of chunks upserted.
    """
    docs_path = Path(docs_path)
    if not docs_path.exists():
        logger.warning("RAG docs path does not exist: %s", docs_path)
        return 0

    supported = (".txt", ".md", ".docx", ".pdf")
    files = [
        f for f in docs_path.rglob("*") if f.suffix.lower() in supported and f.is_file()
    ]

    if not files:
        logger.warning("No supported documents found in %s", docs_path)
        return 0

    all_chunks: list[str] = []
    all_ids: list[str] = []
    all_metadata: list[dict] = []

    for file_path in files:
        text = _read_file_text(file_path)
        if not text.strip():
            continue

        chunks = _chunk_text(text, chunk_size, chunk_overlap)
        for i, chunk in enumerate(chunks):
            doc_id = f"{file_path.stem}_chunk_{i}"
            all_chunks.append(chunk)
            all_ids.append(doc_id)
            all_metadata.append({
                "source_file": file_path.name,
                "chunk_index": i,
            })

    if all_chunks:
        collection.upsert(
            ids=all_ids,
            documents=all_chunks,
            metadatas=all_metadata,
        )
        logger.info("Upserted %d chunks from %d files.", len(all_chunks), len(files))

    return len(all_chunks)


# ── Query ────────────────────────────────────────────────────────────────────

def query(
    collection: chromadb.Collection,
    query_text: str,
    n_results: int = 3,
) -> list[str]:
    """Retrieve the most relevant reference-letter chunks for a query.

    Args:
        collection: The ChromaDB collection to search.
        query_text: Natural-language query describing the letter context.
        n_results: Number of top results to return.

    Returns:
        List of the top-k document chunk strings, ordered by relevance.
    """
    if collection.count() == 0:
        logger.warning("RAG collection is empty — no templates to retrieve.")
        return []

    results = collection.query(
        query_texts=[query_text],
        n_results=min(n_results, collection.count()),
    )

    documents: list[str] = []
    if results and results.get("documents"):
        documents = results["documents"][0]  # first query's results

    logger.info("RAG query returned %d chunks.", len(documents))
    return documents
