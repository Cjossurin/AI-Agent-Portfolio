"""
Persistent Knowledge Base System
================================
An enhanced RAG system with persistent storage for deep research and client knowledge.

STORAGE:
- Uses file-based persistence (knowledge_store.json)
- Survives restarts, deployable to production
- Tagged documents for easy retrieval

USAGE:
    # Add research files
    python agents/knowledge_base.py add "path/to/research.txt" --tag "instagram_algorithm"
    
    # Search knowledge
    python agents/knowledge_base.py search "Instagram engagement tactics"
    
    # List all documents
    python agents/knowledge_base.py list
    
    # Ingest entire folder
    python agents/knowledge_base.py ingest "path/to/folder" --tag "deep_research"
"""

import os
import json
import hashlib
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv
import numpy as np

load_dotenv()

# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class KnowledgeDocument:
    """A single document in the knowledge base"""
    doc_id: str
    text: str
    embedding: List[float]
    tags: List[str]
    source_file: Optional[str]
    client_id: str
    created_at: str
    chunk_index: int = 0
    total_chunks: int = 1
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'KnowledgeDocument':
        return cls(**data)


# =============================================================================
# KNOWLEDGE BASE
# =============================================================================

class KnowledgeBase:
    """
    Persistent knowledge base with vector search.
    
    Features:
    - File-based persistence (JSON)
    - OpenAI embeddings for semantic search
    - Tag-based filtering
    - Automatic chunking for large documents
    - Source tracking for deduplication
    """
    
    CHUNK_SIZE = 1500  # Characters per chunk
    CHUNK_OVERLAP = 200  # Overlap between chunks
    
    def __init__(self, storage_path: str = None):
        """Initialize the knowledge base"""
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Default storage path in the project's storage directory
        if storage_path is None:
            base_dir = Path(__file__).parent.parent
            storage_path = base_dir / "storage" / "knowledge_base.json"
        
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing documents
        self.documents: List[KnowledgeDocument] = []
        self._load()
        
        print(f"📚 Knowledge Base initialized")
        print(f"   Storage: {self.storage_path}")
        print(f"   Documents: {len(self.documents)}")
    
    def _load(self):
        """Load documents from storage — JSON file first, then DB rebuild if empty."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.documents = [KnowledgeDocument.from_dict(d) for d in data]
            except (json.JSONDecodeError, KeyError) as e:
                print(f"⚠️ Error loading knowledge base: {e}")
                self.documents = []
        # If file was missing/empty (fresh deploy), try DB rebuild
        if not self.documents:
            self._rebuild_from_db()
    
    def _rebuild_from_db(self):
        """Rebuild knowledge base from ClientKnowledgeEntry rows after a fresh deploy."""
        try:
            from database.db import SessionLocal
            from database.models import ClientKnowledgeEntry
            db = SessionLocal()
            try:
                rows = db.query(ClientKnowledgeEntry).all()
                if not rows:
                    return
                print(f"  [KnowledgeBase rebuild] Restoring {len(rows)} docs from PostgreSQL…")
                for row in rows:
                    try:
                        embedding = self._generate_embedding(row.text)
                        doc = KnowledgeDocument(
                            doc_id=row.id,
                            text=row.text,
                            embedding=embedding,
                            tags=[row.category or "general"],
                            source_file=row.source or "database",
                            client_id=row.client_id,
                            created_at=(row.added_at or datetime.utcnow()).isoformat(),
                        )
                        self.documents.append(doc)
                    except Exception as e:
                        print(f"  [KnowledgeBase rebuild] Skipping entry {row.id}: {e}")
                if self.documents:
                    self._save()
                    print(f"  [KnowledgeBase rebuild] ✅ Restored {len(self.documents)} documents.")
            finally:
                db.close()
        except Exception as e:
            print(f"  [KnowledgeBase rebuild] Warning: {e}")

    def _save(self):
        """Save documents to JSON file and persist source text to DB."""
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump([d.to_dict() for d in self.documents], f, indent=2)
        # Also persist raw text to PostgreSQL for redeploy safety
        self._persist_docs_to_db()

    def _persist_docs_to_db(self):
        """Persist document source text to PostgreSQL (without embeddings)."""
        try:
            from database.db import SessionLocal
            from database.models import ClientKnowledgeEntry
            db = SessionLocal()
            try:
                for doc in self.documents:
                    entry_id = hashlib.md5(
                        f"{doc.client_id}:{doc.text[:200]}".encode()
                    ).hexdigest()[:32]
                    existing = db.query(ClientKnowledgeEntry).filter(
                        ClientKnowledgeEntry.id == entry_id
                    ).first()
                    if not existing:
                        db.add(ClientKnowledgeEntry(
                            id=entry_id,
                            client_id=doc.client_id,
                            text=doc.text,
                            source=doc.source_file or "knowledge_base",
                            category=(doc.tags[0] if doc.tags else "general"),
                        ))
                db.commit()
            finally:
                db.close()
        except Exception as e:
            print(f"⚠️  KnowledgeBase DB persist warning: {e}")
    
    def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding using OpenAI"""
        response = self.openai_client.embeddings.create(
            model="text-embedding-ada-002",
            input=text[:8000]  # Truncate to avoid token limits
        )
        return response.data[0].embedding
    
    def _generate_doc_id(self, text: str, source: str, chunk_index: int) -> str:
        """Generate unique document ID"""
        content = f"{text[:500]}{source}{chunk_index}"
        return hashlib.md5(content.encode()).hexdigest()[:16]
    
    def _chunk_text(self, text: str) -> List[str]:
        """Split text into overlapping chunks"""
        if len(text) <= self.CHUNK_SIZE:
            return [text]
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + self.CHUNK_SIZE
            
            # Try to break at a paragraph or sentence
            if end < len(text):
                # Look for paragraph break
                para_break = text.rfind('\n\n', start, end)
                if para_break > start + self.CHUNK_SIZE // 2:
                    end = para_break + 2
                else:
                    # Look for sentence break
                    sent_break = text.rfind('. ', start, end)
                    if sent_break > start + self.CHUNK_SIZE // 2:
                        end = sent_break + 2
            
            chunks.append(text[start:end].strip())
            start = end - self.CHUNK_OVERLAP
        
        return [c for c in chunks if c]  # Remove empty chunks
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        a = np.array(vec1)
        b = np.array(vec2)
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
    
    # =============================================================================
    # PUBLIC METHODS
    # =============================================================================
    
    def add_document(
        self,
        text: str,
        tags: List[str],
        client_id: str = "global",
        source_file: Optional[str] = None
    ) -> List[str]:
        """
        Add a document to the knowledge base.
        
        Args:
            text: Document text
            tags: List of tags for categorization
            client_id: Client identifier (use "global" for shared research)
            source_file: Original file path (for deduplication)
        
        Returns:
            List of document IDs created
        """
        # Check for duplicates
        if source_file:
            existing = [d for d in self.documents if d.source_file == source_file]
            if existing:
                print(f"⚠️ Document already exists: {source_file}")
                return [d.doc_id for d in existing]
        
        # Chunk the document
        chunks = self._chunk_text(text)
        total_chunks = len(chunks)
        doc_ids = []
        
        print(f"📄 Adding document ({total_chunks} chunks)...")
        
        for i, chunk in enumerate(chunks):
            # Generate embedding
            embedding = self._generate_embedding(chunk)
            
            # Create document
            doc_id = self._generate_doc_id(chunk, source_file or "", i)
            doc = KnowledgeDocument(
                doc_id=doc_id,
                text=chunk,
                embedding=embedding,
                tags=tags,
                source_file=source_file,
                client_id=client_id,
                created_at=datetime.now().isoformat(),
                chunk_index=i,
                total_chunks=total_chunks
            )
            
            self.documents.append(doc)
            doc_ids.append(doc_id)
            
            if total_chunks > 1:
                print(f"   Chunk {i+1}/{total_chunks} added")
        
        self._save()
        print(f"✅ Added document: {len(doc_ids)} chunks")
        return doc_ids
    
    def add_file(
        self,
        file_path: str,
        tags: List[str],
        client_id: str = "global"
    ) -> List[str]:
        """
        Add a file to the knowledge base.
        
        Args:
            file_path: Path to the file
            tags: List of tags for categorization
            client_id: Client identifier
        
        Returns:
            List of document IDs created
        """
        path = Path(file_path)
        
        if not path.exists():
            print(f"❌ File not found: {file_path}")
            return []
        
        print(f"\n📁 Adding file: {path.name}")
        
        # Read file content
        try:
            with open(path, 'r', encoding='utf-8') as f:
                text = f.read()
        except UnicodeDecodeError:
            with open(path, 'r', encoding='latin-1') as f:
                text = f.read()
        
        if not text.strip():
            print(f"⚠️ File is empty: {file_path}")
            return []
        
        return self.add_document(
            text=text,
            tags=tags,
            client_id=client_id,
            source_file=str(path.absolute())
        )
    
    def add_folder(
        self,
        folder_path: str,
        tags: List[str],
        client_id: str = "global",
        extensions: List[str] = None
    ) -> Dict[str, List[str]]:
        """
        Add all files from a folder to the knowledge base.
        
        Args:
            folder_path: Path to the folder
            tags: Tags to apply to all files
            client_id: Client identifier
            extensions: File extensions to include (default: .txt, .md)
        
        Returns:
            Dict mapping filenames to their document IDs
        """
        if extensions is None:
            extensions = ['.txt', '.md']
        
        folder = Path(folder_path)
        
        if not folder.exists():
            print(f"❌ Folder not found: {folder_path}")
            return {}
        
        print(f"\n📂 Ingesting folder: {folder}")
        print(f"   Extensions: {extensions}")
        print(f"   Tags: {tags}")
        
        results = {}
        files = [f for f in folder.iterdir() if f.suffix.lower() in extensions]
        
        print(f"   Found {len(files)} files\n")
        
        for i, file in enumerate(files, 1):
            print(f"[{i}/{len(files)}] Processing: {file.name}")
            
            # Auto-generate tag from filename
            file_tag = file.stem.lower().replace(' ', '_').replace('-', '_')
            file_tags = tags + [file_tag]
            
            doc_ids = self.add_file(str(file), file_tags, client_id)
            results[file.name] = doc_ids
        
        print(f"\n✅ Ingested {len(results)} files")
        return results
    
    def search(
        self,
        query: str,
        client_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search the knowledge base.
        
        Args:
            query: Search query
            client_id: Filter by client (None = search all)
            tags: Filter by tags (None = search all)
            limit: Maximum results to return
        
        Returns:
            List of matching documents with scores
        """
        if not self.documents:
            print("⚠️ Knowledge base is empty")
            return []
        
        print(f"🔍 Searching: '{query[:50]}...'")
        
        # Generate query embedding
        query_embedding = self._generate_embedding(query)
        
        # Filter documents
        candidates = self.documents
        
        if client_id:
            candidates = [d for d in candidates if d.client_id == client_id or d.client_id == "global"]
        
        if tags:
            candidates = [d for d in candidates if any(t in d.tags for t in tags)]
        
        if not candidates:
            print("⚠️ No matching documents found")
            return []
        
        # Calculate similarities
        results = []
        for doc in candidates:
            score = self._cosine_similarity(query_embedding, doc.embedding)
            results.append({
                "doc_id": doc.doc_id,
                "text": doc.text,
                "tags": doc.tags,
                "source_file": doc.source_file,
                "score": score,
                "client_id": doc.client_id
            })
        
        # Sort by score and limit
        results.sort(key=lambda x: x["score"], reverse=True)
        results = results[:limit]
        
        print(f"✅ Found {len(results)} results")
        return results
    
    def search_by_tag(self, tag: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get all documents with a specific tag"""
        results = [
            {
                "doc_id": d.doc_id,
                "text": d.text[:200] + "...",
                "tags": d.tags,
                "source_file": d.source_file
            }
            for d in self.documents if tag in d.tags
        ]
        return results[:limit]
    
    def list_documents(self) -> List[Dict[str, Any]]:
        """List all documents in the knowledge base"""
        # Group by source file
        sources = {}
        for doc in self.documents:
            source = doc.source_file or "inline"
            if source not in sources:
                sources[source] = {
                    "source": source,
                    "chunks": 0,
                    "tags": set(),
                    "client_id": doc.client_id,
                    "created_at": doc.created_at
                }
            sources[source]["chunks"] += 1
            sources[source]["tags"].update(doc.tags)
        
        # Convert to list
        return [
            {
                "source": s["source"],
                "chunks": s["chunks"],
                "tags": list(s["tags"]),
                "client_id": s["client_id"],
                "created_at": s["created_at"]
            }
            for s in sources.values()
        ]
    
    def list_tags(self) -> Dict[str, int]:
        """List all tags and their document counts"""
        tags = {}
        for doc in self.documents:
            for tag in doc.tags:
                tags[tag] = tags.get(tag, 0) + 1
        return dict(sorted(tags.items(), key=lambda x: x[1], reverse=True))
    
    def delete_by_source(self, source_file: str) -> int:
        """Delete all documents from a specific source file"""
        original_count = len(self.documents)
        self.documents = [d for d in self.documents if d.source_file != source_file]
        deleted = original_count - len(self.documents)
        
        if deleted > 0:
            self._save()
            print(f"🗑️ Deleted {deleted} chunks from: {source_file}")
        
        return deleted
    
    def delete_by_tag(self, tag: str) -> int:
        """Delete all documents with a specific tag"""
        original_count = len(self.documents)
        self.documents = [d for d in self.documents if tag not in d.tags]
        deleted = original_count - len(self.documents)
        
        if deleted > 0:
            self._save()
            print(f"🗑️ Deleted {deleted} chunks with tag: {tag}")
        
        return deleted
    
    def clear(self):
        """Clear all documents from the knowledge base"""
        self.documents = []
        self._save()
        print("🗑️ Knowledge base cleared")
    
    def stats(self) -> Dict[str, Any]:
        """Get knowledge base statistics"""
        return {
            "total_documents": len(self.documents),
            "total_sources": len(set(d.source_file for d in self.documents if d.source_file)),
            "total_tags": len(self.list_tags()),
            "storage_path": str(self.storage_path),
            "storage_size_kb": self.storage_path.stat().st_size / 1024 if self.storage_path.exists() else 0
        }


# =============================================================================
# CLI INTERFACE
# =============================================================================

def main():
    """Command-line interface for the knowledge base"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Knowledge Base Management")
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Add file command
    add_parser = subparsers.add_parser("add", help="Add a file to the knowledge base")
    add_parser.add_argument("file", help="Path to the file")
    add_parser.add_argument("--tags", "-t", nargs="+", default=["research"], help="Tags for the document")
    add_parser.add_argument("--client", "-c", default="global", help="Client ID")
    
    # Ingest folder command
    ingest_parser = subparsers.add_parser("ingest", help="Ingest all files from a folder")
    ingest_parser.add_argument("folder", help="Path to the folder")
    ingest_parser.add_argument("--tags", "-t", nargs="+", default=["deep_research"], help="Tags for all documents")
    ingest_parser.add_argument("--client", "-c", default="global", help="Client ID")
    
    # Search command
    search_parser = subparsers.add_parser("search", help="Search the knowledge base")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--tags", "-t", nargs="+", help="Filter by tags")
    search_parser.add_argument("--limit", "-l", type=int, default=5, help="Maximum results")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List all documents")
    
    # Tags command
    tags_parser = subparsers.add_parser("tags", help="List all tags")
    
    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Show knowledge base statistics")
    
    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete documents")
    delete_parser.add_argument("--source", help="Delete by source file")
    delete_parser.add_argument("--tag", help="Delete by tag")
    
    # Clear command
    clear_parser = subparsers.add_parser("clear", help="Clear all documents")
    
    args = parser.parse_args()
    
    # Initialize knowledge base
    kb = KnowledgeBase()
    
    if args.command == "add":
        kb.add_file(args.file, args.tags, args.client)
    
    elif args.command == "ingest":
        kb.add_folder(args.folder, args.tags, args.client)
    
    elif args.command == "search":
        results = kb.search(args.query, tags=args.tags, limit=args.limit)
        print("\n📊 Search Results:")
        for i, r in enumerate(results, 1):
            print(f"\n{i}. [Score: {r['score']:.3f}] Tags: {r['tags']}")
            print(f"   {r['text'][:300]}...")
    
    elif args.command == "list":
        docs = kb.list_documents()
        print("\n📚 Documents in Knowledge Base:")
        for d in docs:
            source_name = Path(d["source"]).name if d["source"] != "inline" else "inline"
            print(f"  • {source_name} ({d['chunks']} chunks) - Tags: {d['tags']}")
    
    elif args.command == "tags":
        tags = kb.list_tags()
        print("\n🏷️ Tags:")
        for tag, count in tags.items():
            print(f"  • {tag}: {count} documents")
    
    elif args.command == "stats":
        stats = kb.stats()
        print("\n📊 Knowledge Base Statistics:")
        for key, value in stats.items():
            print(f"  • {key}: {value}")
    
    elif args.command == "delete":
        if args.source:
            kb.delete_by_source(args.source)
        elif args.tag:
            kb.delete_by_tag(args.tag)
        else:
            print("Specify --source or --tag")
    
    elif args.command == "clear":
        confirm = input("⚠️ This will delete ALL documents. Type 'yes' to confirm: ")
        if confirm.lower() == "yes":
            kb.clear()
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
