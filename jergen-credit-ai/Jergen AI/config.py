"""
Central configuration for the Credit Dispute Letter Generator.

Loads environment variables and defines project-wide constants
for paths, model settings, and API configuration.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ── Load .env ────────────────────────────────────────────────────────────────
load_dotenv()

# ── API Configuration ────────────────────────────────────────────────────────
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
MODEL_NAME: str = "claude-sonnet-4-20250514"  # Claude 4.5 Sonnet

# ── Model Parameters ─────────────────────────────────────────────────────────
MAX_TOKENS: int = 16384            # General cap (extraction, evaluation, validation)
DRAFTING_MAX_TOKENS: int = 16384   # Assembly call — letters can be long
SECTION_MAX_TOKENS: int = 4096     # Per-section drafts (late-payment / inquiry blocks)
TEMPERATURE: float = 0.2          # Low temperature for deterministic extraction
DRAFTING_TEMPERATURE: float = 0.5  # Slightly higher for letter writing creativity

# ── Project Paths ─────────────────────────────────────────────────────────────
BASE_DIR: Path = Path(__file__).resolve().parent
INPUT_DIR: Path = BASE_DIR / "Input Reports"
OUTPUT_DIR: Path = BASE_DIR / "Dispute Letters"
RAG_DIR: Path = BASE_DIR / "Agent RAGs"
CHROMA_DB_DIR: Path = BASE_DIR / "chroma_db"

# ── RAG Settings ──────────────────────────────────────────────────────────────
RAG_COLLECTION_NAME: str = "dispute_letter_templates"  # legacy (kept for reference)
PARSER_RAG_COLLECTION: str = "parser_rag"
FILTER_RAG_COLLECTION: str = "filter_rag"
GUARDRAIL_RAG_COLLECTION: str = "guardrail_rag"
WRITER_RAG_COLLECTION: str = "writer_rag"
RAG_CHUNK_SIZE: int = 500       # tokens per chunk
RAG_CHUNK_OVERLAP: int = 50     # overlap between chunks
RAG_TOP_K: int = 3              # number of retrieved chunks

# ── Per-Agent RAG Dirs ────────────────────────────────────────────────────────
PARSER_RAG_DIR: Path = RAG_DIR / "Parser RAG"
FILTER_RAG_DIR: Path = RAG_DIR / "Filter RAG"
WRITER_RAG_DIR: Path = RAG_DIR / "Writer RAG"
GUARDRAIL_RAG_DIR: Path = RAG_DIR / "Guardrail RAG"

# ── Bureau Constants ──────────────────────────────────────────────────────────
BUREAUS: list[str] = ["Experian", "Equifax", "TransUnion"]

BUREAU_ADDRESSES: dict[str, str] = {
    "Experian": (
        "Experian\n"
        "P.O. Box 4500\n"
        "Allen, TX 75013"
    ),
    "Equifax": (
        "Equifax Information Services LLC\n"
        "P.O. Box 740256\n"
        "Atlanta, GA 30374-0256"
    ),
    "TransUnion": (
        "TransUnion LLC\n"
        "Consumer Dispute Center\n"
        "P.O. Box 2000\n"
        "Chester, PA 19016"
    ),
}
