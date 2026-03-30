# Deep Research to Knowledge Base Feature

## Overview
This feature allows clients to submit a research query from their dashboard, receive AI-powered deep research results (with citations), and—after review—add the results directly to their knowledge base for RAG. If denied, clients can revise and resubmit their query.

## Feature Requirements

### 1. Client Dashboard UI
- **New Page/Route:** "Deep Research to Knowledge Base"
- **Form Elements:**
  - Multiline text input for research query
  - "Run Deep Research" button
  - Results preview area
  - "Add to Knowledge Base" and "Revise Query" buttons

### 2. Backend Endpoint
- Accepts research query from client
- Calls Claude API with deep research enabled
- Returns research results with citations
- Stores pending research in a `research_requests` table with `status="pending_review"`

### 3. Review Workflow
- Display research results in formatted preview (with citations/sources)
- "Approve" button: processes research through document pipeline (chunk, embed, add to Qdrant with client_id)
- "Deny & Revise" button: keeps form open with original query editable
- Track research status: `pending_review`, `approved`, `denied`

### 4. Database Schema
- Table: `research_requests`
- Columns: `id`, `client_id`, `query`, `results`, `status`, `created_at`, `approved_at`
- Index: (`client_id`, `status`)

### 5. RAG Pipeline Integration
- Treat approved research as a document source
- Tag with `source_type="deep_research"`
- Include original query in metadata for context

### 6. Architecture Guidance
- Follow existing document upload and review patterns
- Use existing RAG/document pipeline for chunking, embedding, and storage

---

## Implementation Steps
1. Add new dashboard page and form for research queries
2. Implement backend endpoint for research requests
3. Store and track research requests in DB
4. Add review/approval workflow
5. Integrate approved research into RAG pipeline
6. Update documentation and onboarding

---

## Example Workflow
1. Client submits research query
2. System returns research results with citations
3. Client reviews and approves/denies
4. Approved research is added to knowledge base and available for RAG

---

## Notes
- Ensure all research is reviewed before inclusion
- Store original query for context and traceability
- Use `source_type="deep_research"` for all approved research documents
