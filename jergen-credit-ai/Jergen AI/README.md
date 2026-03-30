# Jergen AI — Credit Dispute Letter Generator

> **AI-powered, FCRA-compliant credit dispute letters in minutes.**
> Reads raw credit report PDFs, identifies disputable items, validates them through a guardrail agent, and produces professionally formatted DOCX + PDF letters — one per bureau — ready to mail.

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Pipeline Stages](#pipeline-stages)
- [RAG Knowledge Bases](#rag-knowledge-bases)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Data Schemas](#data-schemas)
- [Output Format](#output-format)
- [Technical Reference](#technical-reference)
- [Legal Disclaimer](#legal-disclaimer)
- [License](#license)

---

## Overview

### Prompt Security
- Production-grade legal prompts are intentionally excluded from source control.
- Prompt constants in repository code are abstract placeholders.
- Full drafting and guardrail prompts are sourced from private environment configuration and/or secure database storage.

Jergen AI automates the most labour-intensive part of credit repair: writing bureau dispute letters. Given one, two, or three credit report PDFs (Experian, Equifax, TransUnion), the system:

1. **Extracts** all personal information, trade lines, payment histories, and hard inquiries using Claude.
2. **Evaluates** each item against FCRA eligibility rules — Jaro-Winkler fuzzy matching for creditor names, 45-day rate-shopping windows for inquiry attribution, and a deterministic audit log for every decision.
3. **Validates** the dispute list through a guardrail agent that checks for frivolous claims, irrelevant disputes, and risk flags before any letter is written.
4. **Drafts** bureau-specific letters via a 3-prompt RAG + Claude pipeline — separate section drafts for late payments (§1681i) and hard inquiries (§1681b), then a final assembly pass — saved as DOCX and PDF.

---

## Key Features

| Feature | Detail |
|---|---|
| **Multi-bureau support** | Processes Experian, Equifax, and TransUnion in one run |
| **Filename-first bureau detection** | Parses bureau from PDF filename; falls back to keyword frequency scoring |
| **Jaro-Winkler fuzzy matching** | 0.92 similarity threshold for creditor name normalisation |
| **FCRA §1681b inquiry attribution** | 30/45-day rate-shopping window logic to link inquiries to accounts |
| **Immutable audit log** | SHA-256 chained JSONL log of every filter decision |
| **Guardrail agent** | Soft checks for frivolous/irrelevant disputes and HIGH_RISK flags before drafting |
| **3-prompt drafting pipeline** | Separate Claude calls for late-payment sections, inquiry sections, and final assembly |
| **RAG-augmented writing** | Writer RAG, Filter RAG, and Guardrail RAG inject domain knowledge into every prompt |
| **Section headings** | Bold ALL-CAPS headings in the output document for readability |
| **Address/phone cleanup section** | Automatically included in every letter (FCRA §1681e(b)) |
| **Phone number popup** | GUI dialog collects current phone at runtime if not supplied via CLI |
| **DOCX + PDF output** | Word document + PDF conversion via Microsoft Word COM |
| **Keep-together paragraphs** | Prevents any paragraph from splitting across a page break |

---

## Architecture

```
Input PDFs (1–3)
     │
     ▼
┌─────────────────────────────────────┐
│  Stage 1 · DataExtraction Agent     │  pdfminer → Claude (parse JSON)
│  PersonalInfo · CreditAccount[]     │
│  HardInquiry[]  per bureau          │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│  Stage 2 · Evaluation Agent         │  Filter RAG + Claude
│  Jaro-Winkler fuzzy match           │
│  FCRA §1681b 30/45-day windows      │
│  SHA-256 immutable audit log        │
│  → NegativeItem[] + QualifyingInquiry[] per bureau
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│  Stage 3 · Validation Agent         │  Guardrail RAG + Claude
│  Frivolous / irrelevant / risk      │
│  checks (soft — warnings, not halt) │
│  ValidationCheckRecord provenance   │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│  Stage 4 · Drafting Agent           │  Writer RAG + Claude (3 calls/bureau)
│  Prompt 1 · Late-payment sections   │  FCRA §1681i
│  Prompt 2 · Inquiry sections        │  FCRA §1681b
│  Prompt 3 · Full letter assembly    │
│  → DOCX + PDF per bureau            │
└─────────────────────────────────────┘
```

**LLM:** `claude-sonnet-4-20250514` (Claude 4.5 Sonnet) via Anthropic API  
**Vector DB:** ChromaDB (persistent, local)  
**PDF parsing:** pdfminer via `pdf_utils.py`  
**Document generation:** python-docx + docx2pdf (Windows Word COM)

---

## Pipeline Stages

### Stage 1 — Data Extraction (`agents/DataExtraction_Agent.py`)

- Extracts text from each PDF via pdfminer.
- Detects bureau from filename first (`equifax`, `experian`, `transunion`), falls back to keyword-frequency scoring.
- Three Claude calls per bureau: `parse_personal_info`, `parse_accounts`, `parse_inquiries`.
- All prompts use `.replace()` injection (not `.format()`) to avoid `KeyError` from JSON examples in prompt templates.
- Returns `ExtractionResult` per bureau with `PersonalInfo`, `CreditAccount[]`, and `HardInquiry[]`.

### Stage 2 — Evaluation / Filtering (`agents/Evaluation_Agent.py`)

- Iterates every `CreditAccount` and flags negative marks (late payments, charge-offs, collections).
- Creditor names are normalised via `CREDITOR_ABBREVIATIONS` dict (62 entries: JPMCB → Chase, CAPONE → Capital One, etc.) before Jaro-Winkler comparison.
- Hard inquiry attribution: compares inquiry date to account open dates within configurable windows (30-day standard, 45-day rate-shopping for auto/mortgage).
- Every decision is written to an `ImmutableLogger` — SHA-256 chained JSONL audit log in `audit_logs/`.
- Produces `EvaluationResult` containing `NegativeItem[]` and `QualifyingInquiry[]`.

### Stage 3 — Validation (`agents/Validation_Agent.py`)

- Three soft-check methods per bureau's dispute list:
  - `_check_frivolous` — flags disputes with no supporting evidence.
  - `_check_irrelevant` — flags items that have no legitimate FCRA basis.
  - `_check_risk` — assigns `DisputeRiskLevel` (SAFE / WARNING / HIGH_RISK).
- Uses Guardrail RAG to retrieve FCRA-specialised validation knowledge.
- Records `ValidationCheckRecord` entries with full provenance (source, confidence, rag_chunk_id).
- Raises `ValidationError` (halts pipeline) only on hard FALSE_POSITIVE detection; soft warnings are logged and passed through.

### Stage 4 — Drafting (`agents/Drafting_Agent.py`)

Three Claude calls per bureau:

1. **`_draft_late_payment_sections`** — One paragraph per negative account citing FCRA §1681i. Demands reinvestigation and furnisher ledger proof.
2. **`_draft_inquiry_sections`** — One paragraph per qualifying inquiry citing FCRA §1681b. Demands written proof of permissible purpose or deletion.
3. **`_assemble_letter`** — Full letter assembly from pre-drafted sections. Injects: ADDRESS AND PHONE NUMBER UPDATE section (§1681e(b)), LATE PAYMENT DISPUTES section, HARD INQUIRY DISPUTES section.

All three sections have bold ALL-CAPS headings in the final document. "Respectfully," appears exactly once — added by `doc_writer.py`, never by Claude.

`_extract_json_from_answer` uses a 5-tier fallback parser with `_sanitize_json_newlines()` to handle literal newlines Claude writes inside JSON string values.

---

## RAG Knowledge Bases

Located in `Agent RAGs/`. Each subdirectory is ingested into a dedicated ChromaDB collection.

| Collection | Directory | Purpose |
|---|---|---|
| `filter_rag` | `Agent RAGs/Filter RAG/` | FCRA dispute eligibility, inquiry attribution windows, fuzzy matching best practices |
| `guardrail_rag` | `Agent RAGs/Guardrail RAG/` | Frivolous dispute detection, data provenance patterns, deterministic validation |
| `writer_rag` | `Agent RAGs/Writer RAG/` | Bureau compliance and routing, letter formatting, FCRA citation patterns |

Parser RAG (`parser_rag`) is also present but reserved for future structured extraction enhancement.

Ingest with:
```bash
python main.py ingest-rag
```

---

## Prerequisites

- **Python 3.11+**
- **Microsoft Windows** (PDF conversion uses Word COM via `docx2pdf`)
- **Microsoft Word** installed (required for `.docx` → `.pdf` conversion)
- **Anthropic API key** with active credits

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/your-username/jergen-ai.git
cd jergen-ai

# 2. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1       # PowerShell
# or
.venv\Scripts\activate.bat       # Command Prompt

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy the environment template and add your API key
copy .env.example .env
# Edit .env and set ANTHROPIC_API_KEY=your_key_here

# 5. Ingest the RAG knowledge bases (one-time setup)
python main.py ingest-rag
```

---

## Configuration

Copy `.env.example` to `.env` and set:

```env
ANTHROPIC_API_KEY=sk-ant-...
```

All other settings are in `config.py`:

| Setting | Default | Purpose |
|---|---|---|
| `MODEL_NAME` | `claude-sonnet-4-20250514` | Claude model used for all LLM calls |
| `MAX_TOKENS` | `16384` | Token limit for extraction, evaluation, validation |
| `DRAFTING_MAX_TOKENS` | `16384` | Token limit for the final letter assembly call |
| `SECTION_MAX_TOKENS` | `4096` | Token limit for each section draft (late-payment / inquiry) |
| `TEMPERATURE` | `0.2` | Low temperature for deterministic extraction |
| `DRAFTING_TEMPERATURE` | `0.5` | Slightly higher for natural letter writing |
| `RAG_TOP_K` | `3` | Number of RAG chunks retrieved per query |
| `RAG_CHUNK_SIZE` | `500` | Token size per RAG chunk |
| `RAG_CHUNK_OVERLAP` | `50` | Overlap between adjacent chunks |

---

## Usage

### Generate dispute letters

```powershell
# With 3 separate bureau PDFs
python main.py generate `
  --client "[CLIENT_NAME]" `
  --reports "Input Reports\[CLIENT_FOLDER]\equifax.pdf" `
           "Input Reports\[CLIENT_FOLDER]\experian.pdf" `
           "Input Reports\[CLIENT_FOLDER]\transunion.pdf"
```

A popup dialog will ask for the client's **current phone number** (digits only, e.g. `5558675309`).  
Type it and click OK, or leave blank to omit it from the letters.

To skip the popup by passing it directly:

```powershell
python main.py generate `
  --client "[CLIENT_NAME]" `
  --phone 5558675309 `
  --reports "Input Reports\[CLIENT_FOLDER]\equifax.pdf" `
           "Input Reports\[CLIENT_FOLDER]\experian.pdf" `
           "Input Reports\[CLIENT_FOLDER]\transunion.pdf"
```

### Single combined PDF

```powershell
python main.py generate --client "[CLIENT_NAME]" --reports "Input Reports\[CLIENT_FOLDER]\combined.pdf"
```

### Re-ingest RAG knowledge bases

```powershell
python main.py ingest-rag
```

Run this any time you add or update documents in the `Agent RAGs/` directories.

### Output

Letters are saved to `Dispute Letters/{client_name}/`:

```
Dispute Letters/
  [CLIENT_FOLDER]/
    Experian_Dispute_Letter_20260301.docx
    Experian_Dispute_Letter_20260301.pdf
    Equifax_Dispute_Letter_20260301.docx
    Equifax_Dispute_Letter_20260301.pdf
    TransUnion_Dispute_Letter_20260301.docx
    TransUnion_Dispute_Letter_20260301.pdf
```

---

## Project Structure

```
jergen-ai/
├── main.py                         # CLI entry point & pipeline orchestrator
├── config.py                       # All settings (paths, model params, bureau addresses)
├── requirements.txt                # Python dependencies
├── .env.example                    # Environment variable template
│
├── agents/
│   ├── DataExtraction_Agent.py     # Stage 1 — PDF → structured JSON via Claude
│   ├── Evaluation_Agent.py         # Stage 2 — filter negatives & qualifying inquiries
│   ├── Validation_Agent.py         # Stage 3 — guardrail QA checks
│   └── Drafting_Agent.py           # Stage 4 — RAG + Claude letter generation
│
├── models/
│   └── schemas.py                  # Pydantic v2 data models (all shared types)
│
├── utils/
│   ├── pdf_utils.py                # pdfminer PDF text extraction + bureau splitting
│   ├── rag_store.py                # ChromaDB init, ingest, and query helpers
│   └── doc_writer.py               # python-docx DOCX builder + PDF converter
│
├── Agent RAGs/
│   ├── Filter RAG/                 # FCRA eligibility + fuzzy matching knowledge
│   ├── Guardrail RAG/              # Dispute validation + provenance patterns
│   ├── Writer RAG/                 # Letter formatting + compliance knowledge
│   └── Parser RAG/                 # (Reserved) Structured extraction knowledge
│
├── Input Reports/                  # Drop client PDF reports here (gitignored)
│   └── {ClientName}/
│       ├── equifax.pdf
│       ├── experian.pdf
│       └── transunion.pdf
│
├── Dispute Letters/                # Generated letters output here (gitignored)
│   └── {ClientName}/
│
├── audit_logs/                     # SHA-256 chained filter audit logs (gitignored)
└── chroma_db/                      # ChromaDB persistent vector store (gitignored)
```

---

## Data Schemas

All Pydantic v2 models live in `models/schemas.py`.

### Core extraction models

| Model | Description |
|---|---|
| `PersonalInfo` | Full name, current address, SSN last 4, DOB, phone, email |
| `CreditAccount` | Account name, number, type, status, bureau, payment history |
| `PaymentHistory` | Month, year, `PaymentStatus` enum (OK, LATE_30, LATE_60, LATE_90, CHARGE_OFF, etc.) |
| `HardInquiry` | Creditor name, inquiry date, bureau |
| `ExtractionResult` | Complete result for one bureau (PersonalInfo + accounts + inquiries) |

### Evaluation models

| Model | Description |
|---|---|
| `NegativeItem` | A `CreditAccount` with negative marks + dispute reason |
| `QualifyingInquiry` | A `HardInquiry` that passed attribution checks + dispute reason |
| `EvaluationResult` | Per-bureau list of negatives and qualifying inquiries |
| `FilterAuditEntry` | Frozen, 22-field audit entry with SHA-256 chain |

### Validation models

| Model | Description |
|---|---|
| `DisputeRiskLevel` | Enum: `SAFE` / `WARNING` / `HIGH_RISK` |
| `ValidationCheckRecord` | Provenance record: check type, result, confidence, RAG chunk ID |
| `ValidationResult` | Verified negatives, verified inquiries, warnings list, provenance records |

### Output models

| Model | Description |
|---|---|
| `DisputeLetter` | Bureau name, letter body, DOCX path, PDF path |

---

## Technical Reference

### Prompt injection pattern

All prompts use `.replace()` with named sentinel tokens (e.g. `{$BUREAU}`, `{$WRITER_RAG_CONTEXT}`) instead of Python's `.format()`. This prevents `KeyError` from JSON examples in prompt bodies that contain curly braces.

### JSON extraction fallback chain

`_extract_json_from_answer()` in `Drafting_Agent.py` uses a 5-tier fallback:
1. Parse JSON inside `<answer>` tags as-is
2. Sanitize literal newlines inside `<answer>` block, then parse
3. Parse full response text as-is
4. Sanitize full response text, then parse
5. Regex-find first `{...}` block, sanitize, then parse

`_sanitize_json_newlines()` does a character-by-character pass replacing bare `\n` / `\r` inside JSON string values with their escaped equivalents.

### Bureau detection priority

1. **Filename-based** — `detect_bureau_from_filename()` checks for `equifax`, `experian`, `transunion` in the PDF filename (case-insensitive).
2. **Text-frequency scoring** — `detect_bureau_from_text()` counts regex matches per bureau name and takes the highest.
3. **Position fallback** — assigns the next unoccupied bureau slot if both methods fail.

### Audit log format

Each entry in `audit_logs/filter_audit_log_YYYYMMDD_HHMMSS.jsonl` is a `FilterAuditEntry` with:
- `entry_id` (UUID)
- `chain_hash` (SHA-256 of previous entry + current content)
- `bureau`, `item_type`, `item_name`, `decision`, `reason`
- 17 additional fields covering dates, scores, and matching details

### Section heading rendering

`doc_writer.py` detects ALL-CAPS heading blocks (2–10 words, ≤ 80 chars, only letters/spaces/`&`) and renders them as **bold 12pt** with `14pt` space above. Body paragraphs are `11pt` with `12pt` space after and `4pt` before. All paragraphs use `keep_together=True`.

---

## Legal Disclaimer

This software is intended as a **drafting aid only**. Generated letters cite the Fair Credit Reporting Act (FCRA) and Fair Debt Collection Practices Act (FDCPA) statutes. Users are solely responsible for:

- Verifying the accuracy of all dispute claims before mailing.
- Ensuring compliance with applicable federal and state law.
- Obtaining qualified legal advice where appropriate.

The authors make no warranties, express or implied, regarding the legal sufficiency or effectiveness of any generated letter.

---

## License

MIT License — see [LICENSE](LICENSE) for full text.
