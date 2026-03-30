# agents/rag_system.py
"""
Enhanced RAG Knowledge System
==============================
Production-ready retrieval-augmented generation system with:
- Batch document processing
- Advanced retrieval with metadata filtering
- Document management (CRUD operations)
- Hybrid search capabilities
- Category/tag support
- Duplicate detection
"""
import os
import hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, 
    VectorParams, 
    PointStruct, 
    Filter, 
    FieldCondition, 
    MatchValue,
    MatchAny,
    Range
)
from dotenv import load_dotenv

load_dotenv()


# Platform-best-practice posting frequencies — single source of truth
# Used by ContentCalendarOrchestrator and AgentScheduler
PLATFORM_DEFAULT_FREQUENCY: dict = {
    "instagram": 1,   # 1/day
    "facebook":  1,   # 1/day
    "tiktok":    2,   # 2-3/day
    "linkedin":  1,   # 1/day
    "twitter":   3,   # 3-5/day
    "threads":   1,   # 1-2/day
    "youtube":   1,   # 1/day (3-7/week is aggressive)
    "email":     1,
}


# ── Module-level Qdrant singleton ─────────────────────────────────────────────
# Only ONE QdrantClient(path=...) can hold the file-lock at a time.  Every
# RAGSystem() instance reuses the same client so we never get the
# "Storage folder already accessed" RuntimeError.
_qdrant_path = os.path.join("storage", "qdrant")
os.makedirs(_qdrant_path, exist_ok=True)
_shared_qdrant: QdrantClient = QdrantClient(path=_qdrant_path)


class RAGSystem:
    def __init__(self, collection_name="client_knowledge"):
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.qdrant_client = _shared_qdrant          # reuse process-wide client
        self.collection_name = collection_name
        self.embedding_dimension = 1536  # text-embedding-ada-002 dimension
        
        try:
            self.qdrant_client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=self.embedding_dimension, distance=Distance.COSINE)
            )
            print(f"[OK] Created collection: {collection_name}")
            # New collection on fresh deploy → rebuild from DB
            self._rebuild_from_db()
        except:
            pass  # collection already exists — expected on subsequent instances
    
    def _generate_id(self, text: str, client_id: str, source: str = "") -> int:
        """Generate stable ID from content hash."""
        content = f"{text}:{client_id}:{source}"
        return int(hashlib.md5(content.encode()).hexdigest(), 16) % (10 ** 8)

    def _rebuild_from_db(self):
        """
        Rebuild the Qdrant collection from PostgreSQL after a fresh deploy.
        Only runs when a new collection was just created (= empty Qdrant).
        """
        try:
            from database.db import SessionLocal
            from database.models import ClientKnowledgeEntry
            db = SessionLocal()
            try:
                rows = db.query(ClientKnowledgeEntry).all()
                if not rows:
                    print("  [RAG rebuild] No knowledge entries in DB — nothing to restore.")
                    return
                print(f"  [RAG rebuild] Restoring {len(rows)} knowledge entries from PostgreSQL…")
                # Batch embeddings in groups of 50 to avoid API limits
                batch_size = 50
                points = []
                for i in range(0, len(rows), batch_size):
                    batch = rows[i : i + batch_size]
                    texts = [r.text for r in batch]
                    try:
                        resp = self.openai_client.embeddings.create(
                            model="text-embedding-ada-002", input=texts
                        )
                        for j, row in enumerate(batch):
                            vector = resp.data[j].embedding
                            point_id = self._generate_id(row.text, row.client_id, row.source or "")
                            payload = {
                                "client_id": row.client_id,
                                "text": row.text,
                                "source": row.source or "manual",
                                "category": row.category or "general",
                                "tags": [],
                                "added_at": (row.added_at or datetime.utcnow()).isoformat(),
                                "char_count": len(row.text),
                                "word_count": len(row.text.split()),
                            }
                            points.append(PointStruct(id=point_id, vector=vector, payload=payload))
                    except Exception as be:
                        print(f"  [RAG rebuild] Embedding batch {i}-{i+batch_size} failed: {be}")
                if points:
                    self.qdrant_client.upsert(collection_name=self.collection_name, points=points)
                    print(f"  [RAG rebuild] ✅ Restored {len(points)} vectors into Qdrant.")
            finally:
                db.close()
        except Exception as e:
            print(f"  [RAG rebuild] Warning (non-fatal): {e}")
    
    def add_knowledge(
        self, 
        text: str, 
        client_id: str, 
        source: str = "manual",
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Add knowledge to Qdrant and PostgreSQL (dual-write).
        """
        print(f"[*] Adding knowledge from {source}...")
        
        # Generate embedding
        response = self.openai_client.embeddings.create(
            model="text-embedding-ada-002",
            input=text
        )
        vector = response.data[0].embedding
        
        # Build payload with rich metadata
        payload = {
            "client_id": client_id, 
            "text": text,
            "source": source,
            "category": category or "general",
            "tags": tags or [],
            "added_at": datetime.utcnow().isoformat(),
            "char_count": len(text),
            "word_count": len(text.split())
        }
        
        # Merge additional metadata
        if metadata:
            payload.update(metadata)
        
        point_id = self._generate_id(text, client_id, source)
        
        self.qdrant_client.upsert(
            collection_name=self.collection_name,
            points=[PointStruct(id=point_id, vector=vector, payload=payload)]
        )

        # Also persist to PostgreSQL so data survives Railway redeploys
        self._persist_to_db(client_id, text, source, category or "general")

        print(f"✅ Added knowledge (ID: {point_id}, category: {payload['category']})")
        return point_id

    @staticmethod
    def _persist_to_db(client_id: str, text: str, source: str, category: str):
        """Save knowledge entry to PostgreSQL for persistence across redeploys."""
        try:
            from database.db import SessionLocal
            from database.models import ClientKnowledgeEntry
            entry_id = hashlib.md5(f"{client_id}:{text[:200]}".encode()).hexdigest()[:32]
            db = SessionLocal()
            try:
                existing = db.query(ClientKnowledgeEntry).filter(
                    ClientKnowledgeEntry.id == entry_id
                ).first()
                if not existing:
                    db.add(ClientKnowledgeEntry(
                        id=entry_id,
                        client_id=client_id,
                        text=text,
                        source=source,
                        category=category,
                    ))
                    db.commit()
            finally:
                db.close()
        except Exception as e:
            print(f"⚠️  RAG DB persist failed (non-fatal): {e}")
    
    def add_knowledge_with_source(self, text: str, client_id: str, source: str):
        """
        Legacy method - kept for backward compatibility.
        Use add_knowledge() with source parameter instead.
        """
        return self.add_knowledge(text=text, client_id=client_id, source=source)
    
    def add_documents_batch(
        self,
        documents: List[Dict[str, Any]],
        client_id: str
    ) -> List[int]:
        """
        Batch process multiple documents efficiently.
        
        Args:
            documents: List of dicts with keys: text, source, category, tags, metadata
            client_id: Client identifier
            
        Returns:
            List of point IDs
        """
        print(f"📦 Batch processing {len(documents)} documents...")
        
        if not documents:
            return []
        
        # Generate all embeddings in one API call for efficiency
        texts = [doc["text"] for doc in documents]
        response = self.openai_client.embeddings.create(
            model="text-embedding-ada-002",
            input=texts
        )
        
        points = []
        point_ids = []
        
        for i, doc in enumerate(documents):
            vector = response.data[i].embedding
            point_id = self._generate_id(doc["text"], client_id, doc.get("source", ""))
            point_ids.append(point_id)
            
            payload = {
                "client_id": client_id,
                "text": doc["text"],
                "source": doc.get("source", "unknown"),
                "category": doc.get("category", "general"),
                "tags": doc.get("tags", []),
                "added_at": datetime.utcnow().isoformat(),
                "char_count": len(doc["text"]),
                "word_count": len(doc["text"].split())
            }
            
            if "metadata" in doc:
                payload.update(doc["metadata"])
            
            points.append(PointStruct(id=point_id, vector=vector, payload=payload))
        
        self.qdrant_client.upsert(
            collection_name=self.collection_name,
            points=points
        )

        # Persist all documents to PostgreSQL for redeploy safety
        for doc in documents:
            self._persist_to_db(
                client_id,
                doc["text"],
                doc.get("source", "unknown"),
                doc.get("category", "general"),
            )

        print(f"✅ Batch added {len(points)} documents")
        return point_ids
    
    def search(
        self, 
        query: str, 
        client_id: str, 
        limit: int = 3,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        source_filter: Optional[str] = None,
        score_threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Enhanced semantic search with filtering options.
        
        Args:
            query: Search query
            client_id: Client identifier
            limit: Maximum results to return
            category: Filter by category
            tags: Filter by tags (match any)
            source_filter: Filter by source
            score_threshold: Minimum similarity score (0-1)
            
        Returns:
            List of results with text, score, and metadata
        """
        print(f"🔍 Searching: '{query}' (category={category}, tags={tags})")
        
        # Generate query embedding
        response = self.openai_client.embeddings.create(
            model="text-embedding-ada-002",
            input=query
        )
        query_vector = response.data[0].embedding
        
        # Build filter conditions
        filter_conditions = [
            FieldCondition(key="client_id", match=MatchValue(value=client_id))
        ]
        
        if category:
            filter_conditions.append(
                FieldCondition(key="category", match=MatchValue(value=category))
            )
        
        if tags:
            filter_conditions.append(
                FieldCondition(key="tags", match=MatchAny(any=tags))
            )
        
        if source_filter:
            filter_conditions.append(
                FieldCondition(key="source", match=MatchValue(value=source_filter))
            )
        
        # Execute search
        results = self.qdrant_client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            query_filter=Filter(must=filter_conditions),
            limit=limit,
            score_threshold=score_threshold
        ).points
        
        # Format results with rich metadata
        found = []
        for r in results:
            found.append({
                "text": r.payload["text"],
                "score": r.score,
                "source": r.payload.get("source", "unknown"),
                "category": r.payload.get("category", "general"),
                "tags": r.payload.get("tags", []),
                "added_at": r.payload.get("added_at"),
                "id": r.id
            })
        
        print(f"✅ Found {len(found)} results")
        return found
    
    def retrieve_knowledge(
        self,
        query: str,
        client_id: str,
        limit: int = 5,
        **filters
    ) -> str:
        """
        Main retrieval method - returns formatted context string for AI.
        
        Args:
            query: User query or context
            client_id: Client identifier
            limit: Maximum results
            **filters: category, tags, source_filter, score_threshold
            
        Returns:
            Formatted string with retrieved knowledge
        """
        results = self.search(query, client_id, limit=limit, **filters)
        
        if not results:
            return "No relevant knowledge found."
        
        context_parts = []
        for i, result in enumerate(results, 1):
            context_parts.append(
                f"[{i}] ({result['category']}) {result['text']}\n"
                f"    Source: {result['source']} | Relevance: {result['score']:.2f}"
            )
        
        return "\n\n".join(context_parts)
    
    def list_documents(
        self,
        client_id: str,
        category: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        List all documents for a client with optional filtering.
        
        Args:
            client_id: Client identifier
            category: Optional category filter
            limit: Maximum documents to return
            
        Returns:
            List of document metadata
        """
        filter_conditions = [
            FieldCondition(key="client_id", match=MatchValue(value=client_id))
        ]
        
        if category:
            filter_conditions.append(
                FieldCondition(key="category", match=MatchValue(value=category))
            )
        
        # Scroll through collection to get all matching documents
        results, _ = self.qdrant_client.scroll(
            collection_name=self.collection_name,
            scroll_filter=Filter(must=filter_conditions),
            limit=limit,
            with_vectors=False
        )
        
        documents = []
        for point in results:
            documents.append({
                "id": point.id,
                "source": point.payload.get("source", "unknown"),
                "category": point.payload.get("category", "general"),
                "tags": point.payload.get("tags", []),
                "added_at": point.payload.get("added_at"),
                "char_count": point.payload.get("char_count", 0),
                "word_count": point.payload.get("word_count", 0),
                "text_preview": point.payload.get("text", "")[:100] + "..."
            })
        
        return documents
    
    def delete_document(self, point_id: int) -> bool:
        """Delete a specific document by ID."""
        try:
            self.qdrant_client.delete(
                collection_name=self.collection_name,
                points_selector=[point_id]
            )
            print(f"✅ Deleted document {point_id}")
            return True
        except Exception as e:
            print(f"❌ Failed to delete document {point_id}: {e}")
            return False
    
    def delete_by_source(self, client_id: str, source: str) -> int:
        """
        Delete all documents from a specific source.
        
        Args:
            client_id: Client identifier
            source: Source to delete
            
        Returns:
            Number of deleted documents
        """
        # First, find all documents with this source
        filter_conditions = [
            FieldCondition(key="client_id", match=MatchValue(value=client_id)),
            FieldCondition(key="source", match=MatchValue(value=source))
        ]
        
        results, _ = self.qdrant_client.scroll(
            collection_name=self.collection_name,
            scroll_filter=Filter(must=filter_conditions),
            limit=10000,
            with_vectors=False
        )
        
        if not results:
            print(f"⚠️  No documents found for source: {source}")
            return 0
        
        # Delete all matching point IDs
        point_ids = [point.id for point in results]
        self.qdrant_client.delete(
            collection_name=self.collection_name,
            points_selector=point_ids
        )
        
        print(f"✅ Deleted {len(point_ids)} documents from source: {source}")
        return len(point_ids)
    
    def update_document_metadata(
        self,
        point_id: int,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> bool:
        """
        Update document metadata without re-embedding.
        
        Args:
            point_id: Document ID
            category: New category
            tags: New tags
            
        Returns:
            Success status
        """
        try:
            # Build update payload
            update_payload = {}
            if category is not None:
                update_payload["category"] = category
            if tags is not None:
                update_payload["tags"] = tags
            
            if not update_payload:
                print("⚠️  No updates specified")
                return False
            
            # Update the point
            self.qdrant_client.set_payload(
                collection_name=self.collection_name,
                payload=update_payload,
                points=[point_id]
            )
            
            print(f"✅ Updated document {point_id}")
            return True
        except Exception as e:
            print(f"❌ Failed to update document {point_id}: {e}")
            return False
    
    def get_statistics(self, client_id: str) -> Dict[str, Any]:
        """
        Get knowledge base statistics for a client.
        
        Returns:
            Dict with total documents, categories, sources, etc.
        """
        documents = self.list_documents(client_id, limit=10000)
        
        if not documents:
            return {
                "total_documents": 0,
                "categories": {},
                "sources": [],
                "total_words": 0,
                "total_chars": 0
            }
        
        # Calculate statistics
        categories = {}
        sources = set()
        total_words = 0
        total_chars = 0
        
        for doc in documents:
            # Count by category
            cat = doc.get("category", "general")
            categories[cat] = categories.get(cat, 0) + 1
            
            # Collect sources
            sources.add(doc.get("source", "unknown"))
            
            # Sum word and char counts
            total_words += doc.get("word_count", 0)
            total_chars += doc.get("char_count", 0)
        
        return {
            "total_documents": len(documents),
            "categories": categories,
            "sources": sorted(list(sources)),
            "total_words": total_words,
            "total_chars": total_chars,
            "avg_words_per_doc": total_words // len(documents) if documents else 0
        }


if __name__ == "__main__":
    print("\n🧪 Testing Enhanced RAG System...\n")
    rag = RAGSystem()
    
    # Test 1: Add knowledge with categories
    print("=" * 60)
    print("TEST 1: Adding knowledge with categories")
    print("=" * 60)
    rag.add_knowledge(
        text="Our cruises start at $999 per person from Miami.",
        client_id="cruise_123",
        source="pricing_doc.pdf",
        category="pricing",
        tags=["cruises", "pricing", "miami"]
    )
    
    rag.add_knowledge(
        text="We offer 7-day Caribbean cruises with all-inclusive dining and entertainment.",
        client_id="cruise_123",
        source="services_doc.pdf",
        category="services",
        tags=["cruises", "caribbean", "dining"]
    )
    
    # Test 2: Batch processing
    print("\n" + "=" * 60)
    print("TEST 2: Batch document processing")
    print("=" * 60)
    docs = [
        {
            "text": "Free cancellation up to 30 days before departure.",
            "source": "policy_doc.pdf",
            "category": "policy",
            "tags": ["policy", "cancellation"]
        },
        {
            "text": "Book now and get 20% off your first cruise!",
            "source": "promotions.pdf",
            "category": "promotions",
            "tags": ["discount", "promotions"]
        }
    ]
    rag.add_documents_batch(docs, "cruise_123")
    
    # Test 3: Enhanced search with filters
    print("\n" + "=" * 60)
    print("TEST 3: Search with category filter")
    print("=" * 60)
    results = rag.search("How much do cruises cost?", "cruise_123", category="pricing")
    print(f"\n📊 Results: {len(results)}")
    for r in results:
        print(f"  • {r['text'][:80]}... (score: {r['score']:.3f}, category: {r['category']})")
    
    # Test 4: Retrieve knowledge (formatted context)
    print("\n" + "=" * 60)
    print("TEST 4: Retrieve formatted knowledge")
    print("=" * 60)
    context = rag.retrieve_knowledge("What services are included?", "cruise_123", limit=2)
    print(f"\n📄 Context:\n{context}")
    
    # Test 5: Document management
    print("\n" + "=" * 60)
    print("TEST 5: List and manage documents")
    print("=" * 60)
    documents = rag.list_documents("cruise_123")
    print(f"\n📋 Total documents: {len(documents)}")
    for doc in documents:
        print(f"  • {doc['source']} ({doc['category']}) - {doc['word_count']} words")
    
    # Test 6: Statistics
    print("\n" + "=" * 60)
    print("TEST 6: Knowledge base statistics")
    print("=" * 60)
    stats = rag.get_statistics("cruise_123")
    print(f"\n📊 Statistics:")
    print(f"  • Total documents: {stats['total_documents']}")
    print(f"  • Categories: {stats['categories']}")
    print(f"  • Sources: {len(stats['sources'])}")
    print(f"  • Total words: {stats['total_words']}")
    print(f"  • Avg words/doc: {stats['avg_words_per_doc']}")
    
    print("\n✅ All tests completed!")