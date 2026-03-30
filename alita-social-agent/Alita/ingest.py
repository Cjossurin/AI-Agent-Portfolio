"""
Knowledge Ingestion Script
Automatically processes PDF, DOCX, and TXT files from knowledge_docs folder
and adds them to the RAG knowledge base.

Features:
- Incremental loading: Skip files already processed (no duplicates)
- Text chunking: Split large documents to fit context limits
- Robust error handling: Continue processing even if some files fail
"""
import os
import sys
from pathlib import Path

# Add paths for imports
sys.path.append('agents')
sys.path.append('utils')

from rag_system import RAGSystem
from file_reader import extract_pdf_text, extract_docx_text, extract_txt_text


def is_file_already_processed(rag: RAGSystem, filename: str, client_id: str) -> bool:
    """Check if a file has already been processed by querying Qdrant collection."""
    try:
        # Query for any points that have this filename as source
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        
        results = rag.qdrant_client.query_points(
            collection_name=rag.collection_name,
            query=[0.0] * 1536,  # Dummy vector for metadata-only search
            query_filter=Filter(
                must=[
                    FieldCondition(key="client_id", match=MatchValue(value=client_id)),
                    FieldCondition(key="source", match=MatchValue(value=filename))
                ]
            ),
            limit=1
        ).points
        
        return len(results) > 0
    except Exception as e:
        # If there's any error checking, assume file is not processed
        print(f"⚠️  Could not check if {filename} exists: {e}")
        return False


def chunk_text(text: str, chunk_size: int = 4000) -> list:
    """Split text into smaller chunks to avoid token limit errors."""
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size]
        chunks.append(chunk)
    
    return chunks


# File extraction functions moved to utils/file_reader.py


def process_documents(docs_folder: str = "knowledge_docs", client_id: str = "demo_client"):
    """
    Process all documents in the knowledge_docs folder.
    
    Args:
        docs_folder: Path to folder containing documents
        client_id: The client ID to associate with this knowledge
    """
    docs_path = Path(docs_folder)
    
    if not docs_path.exists():
        print(f"❌ Folder {docs_folder} does not exist!")
        print(f"💡 Creating folder: {docs_folder}")
        docs_path.mkdir(parents=True, exist_ok=True)
        print(f"✅ Created {docs_folder}. Please add your PDF/DOCX/TXT files there.")
        return
    
    # Get all supported files
    files = list(docs_path.glob("*.pdf")) + list(docs_path.glob("*.docx")) + list(docs_path.glob("*.txt"))
    
    if not files:
        print(f"⚠️  No PDF, DOCX, or TXT files found in {docs_folder}")
        print(f"💡 Add some files and run this script again.")
        return
    
    print(f"\n🚀 Starting document ingestion...")
    print(f"📂 Found {len(files)} files in {docs_folder}")
    print("="*60)
    
    # Initialize RAG system
    rag = RAGSystem()
    
    # Consolidated text for knowledge_base.txt
    consolidated_text = []
    processed_count = 0
    skipped_count = 0
    
    for file_path in files:
        file_name = file_path.name
        file_ext = file_path.suffix.lower()
        
        print(f"\n📄 Checking: {file_name}")
        
        # Check if file is already processed
        if is_file_already_processed(rag, file_name, client_id):
            print(f"⏭️ Skipping {file_name} - Already ingested.")
            skipped_count += 1
            continue
            
        print(f"📄 Processing: {file_name}")
        
        # Extract text based on file type
        if file_ext == ".pdf":
            text = extract_pdf_text(str(file_path))
        elif file_ext == ".docx":
            text = extract_docx_text(str(file_path))
        elif file_ext == ".txt":
            text = extract_txt_text(str(file_path))
        else:
            print(f"⚠️  Skipping unsupported file type: {file_ext}")
            continue
        
        if not text:
            print(f"⚠️  No text extracted from {file_name}")
            continue
        
        # Add separator and source info
        separator = f"\n\n{'='*60}\n--- Source: {file_name} ---\n{'='*60}\n\n"
        consolidated_text.append(separator + text)
        
        # Add to RAG system with chunking to avoid token limits
        try:
            text_chunks = chunk_text(text)
            chunks_added = 0
            
            for i, chunk in enumerate(text_chunks):
                try:
                    # Add source metadata for duplicate detection
                    rag.add_knowledge_with_source(text=chunk, client_id=client_id, source=file_name)
                    chunks_added += 1
                except Exception as chunk_error:
                    print(f"⚠️  Failed to add chunk {i+1}/{len(text_chunks)}: {chunk_error}")
                    continue
            
            if chunks_added > 0:
                processed_count += 1
                if len(text_chunks) > 1:
                    print(f"✅ Added to RAG knowledge base ({chunks_added}/{len(text_chunks)} chunks)")
                else:
                    print(f"✅ Added to RAG knowledge base")
            else:
                print(f"❌ Failed to add any chunks to RAG")
                
        except Exception as e:
            print(f"❌ Failed to add to RAG: {e}")
    
    # Write consolidated knowledge base
    if consolidated_text:
        output_file = "knowledge_base.txt"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("\n".join(consolidated_text))
        
        print("\n" + "="*60)
        print(f"✅ SUCCESS!")
        print(f"📊 Processed {processed_count}/{len(files)} files")
        if skipped_count > 0:
            print(f"⏭️ Skipped {skipped_count} files (already ingested)")
        print(f"💾 Consolidated knowledge saved to: {output_file}")
        print(f"🧠 Knowledge added to RAG vector store for client: {client_id}")
        print("="*60)
    else:
        print("\n" + "="*60)
        if skipped_count == len(files):
            print(f"ℹ️ All {len(files)} files already ingested - nothing new to process!")
            print(f"⏭️ Skipped {skipped_count} files (already ingested)")
        else:
            print("❌ No text was extracted from any files.")
        print("="*60)


if __name__ == "__main__":
    print("\n" + "🤖 ALITA KNOWLEDGE INGESTION SYSTEM ".center(60, "="))
    
    # You can change the client_id here if needed
    CLIENT_ID = "demo_client"
    
    process_documents(client_id=CLIENT_ID)
    
    print("\n💡 Next steps:")
    print("   1. Run your webhook receiver: python webhook_receiver.py")
    print("   2. The bot will use this knowledge to answer questions")
    print("   3. Add more files to knowledge_docs/ and run this script again")
    print("   4. The script will skip files already processed (incremental loading)\n")
