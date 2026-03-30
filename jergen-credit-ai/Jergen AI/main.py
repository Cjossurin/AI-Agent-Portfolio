"""
main.py — Pipeline Orchestrator for the Credit Dispute Letter Generator

Coordinates the four-agent pipeline:

  1. DataExtraction Agent  → Parse PDFs into structured JSON
  2. Evaluation Agent      → Filter for negative items & qualifying inquiries
  3. Validation Agent      → QA guardrail (halts on false positives)
  4. Drafting Agent        → RAG + Claude 4.5 Sonnet → DOCX + PDF letters

Usage:
  # 3 separate bureau reports
    python main.py --client "[CLIENT_NAME]" --reports experian.pdf equifax.pdf transunion.pdf

  # 1 combined report
    python main.py --client "[CLIENT_NAME]" --reports combined_report.pdf

  # Ingest RAG reference documents only (no dispute generation)
  python main.py ingest-rag
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from anthropic import Anthropic

import config
from agents.DataExtraction_Agent import DataExtractionAgent
from agents.Evaluation_Agent import EvaluationAgent
from agents.Validation_Agent import ValidationAgent, ValidationError
from agents.Drafting_Agent import DraftingAgent
from models.schemas import PersonalInfo
from utils.rag_store import init_store, ingest_reference_docs

# ── Logging setup ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-28s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


# ── Phone prompt popup ──────────────────────────────────────────────────

def _ask_phone_popup() -> str | None:
    """Show a small GUI dialog asking for the client's current phone number.

    Returns digits-only string (e.g. '5558675309'), or None if the user
    clicks Cancel or leaves the field blank.
    """
    try:
        import tkinter as tk
        from tkinter import simpledialog, messagebox

        root = tk.Tk()
        root.withdraw()   # hide the blank root window
        root.lift()
        root.attributes("-topmost", True)

        phone = simpledialog.askstring(
            title="Phone Number",
            prompt=(
                "Enter the client's current phone number\n"
                "(digits only, e.g.  5558675309):\n"
                "\nLeave blank to omit from the letter."
            ),
            parent=root,
        )
        root.destroy()

        if phone is None:          # user clicked Cancel
            return None
        digits = "".join(c for c in phone if c.isdigit())
        return digits if digits else None

    except Exception as exc:
        logger.warning("Phone popup failed (%s); continuing without phone.", exc)
        return None


# ── Pipeline class ───────────────────────────────────────────────────────────

class DisputePipeline:
    """Orchestrates the full dispute-letter generation pipeline.

    Initializes the Anthropic client, all four agents, and the RAG store,
    then drives data through the pipeline in sequence.

    Attributes:
        client_name: Name of the client (used for input/output folders).
        pdf_paths: Paths to 1 or 3 credit report PDFs.
        anthropic_client: Anthropic API client.
        rag_collection: ChromaDB collection with reference templates.
    """

    def __init__(
        self,
        client_name: str,
        pdf_paths: list[str],
        current_phone: str | None = None,
    ) -> None:
        """Set up the pipeline with all required components.

        Args:
            client_name: Client display name / folder name.
            pdf_paths: List of 1 (combined) or 3 (per-bureau) PDF paths.
            current_phone: Optional current phone number (digits only, e.g.
                5558675309). Added to the address/phone cleanup section.

        Raises:
            ValueError: If ANTHROPIC_API_KEY is not set.
        """
        if not config.ANTHROPIC_API_KEY:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set. "
                "Add it to the .env file or set the environment variable."
            )

        self.client_name = client_name
        self.pdf_paths = pdf_paths
        self.current_phone = current_phone

        # ── Anthropic client ─────────────────────────────────────────
        self.anthropic_client = Anthropic(api_key=config.ANTHROPIC_API_KEY)

        # ── RAG store (Writer Agent templates) ───────────────────────
        self.rag_collection = init_store(
            persist_dir=config.CHROMA_DB_DIR,
            collection_name=config.WRITER_RAG_COLLECTION,
        )

        # ── RAG store (filter knowledge) ─────────────────────────────
        self.filter_rag_collection = init_store(
            persist_dir=config.CHROMA_DB_DIR,
            collection_name=config.FILTER_RAG_COLLECTION,
        )

        # ── RAG store (guardrail knowledge) ──────────────────────────────
        self.guardrail_rag_collection = init_store(
            persist_dir=config.CHROMA_DB_DIR,
            collection_name=config.GUARDRAIL_RAG_COLLECTION,
        )

        # ── Agents ───────────────────────────────────────────────────
        self.extraction_agent = DataExtractionAgent(self.anthropic_client)
        self.evaluation_agent = EvaluationAgent(
            anthropic_client=self.anthropic_client,
            filter_rag_collection=self.filter_rag_collection,
        )
        self.validation_agent = ValidationAgent(
            anthropic_client=self.anthropic_client,
            guardrail_rag_collection=self.guardrail_rag_collection,
        )
        self.drafting_agent = DraftingAgent(
            self.anthropic_client, self.rag_collection
        )

        logger.info("Pipeline initialized for client: %s", client_name)

    def run(self) -> None:
        """Execute the full 4-stage pipeline.

        Stages:
          1. **Extract** — PDF → structured data (Claude-assisted parsing)
          2. **Evaluate** — filter negatives & qualifying inquiries
          3. **Validate** — assert no false positives (halts on failure)
          4. **Draft** — RAG + Claude → 3 dispute letters (DOCX + PDF)

        Raises:
            ValidationError: If the Validation Agent detects a positive
                account in the dispute list (pipeline halts).
        """
        separator = "=" * 70

        # ── Stage 1: Extraction ──────────────────────────────────────
        logger.info(separator)
        logger.info("STAGE 1 / 4 — DATA EXTRACTION")
        logger.info(separator)

        extraction_results = self.extraction_agent.run(self.pdf_paths)

        for result in extraction_results:
            logger.info(
                "  [%s] %d accounts, %d inquiries, %d public records extracted.",
                result.bureau_source,
                len(result.accounts),
                len(result.hard_inquiries),
                len(result.public_records),
            )

        # ── Stage 2: Evaluation ──────────────────────────────────────
        logger.info(separator)
        logger.info("STAGE 2 / 4 — EVALUATION (FILTERING)")
        logger.info(separator)

        evaluation_results = self.evaluation_agent.run(extraction_results)

        for bureau, eval_result in evaluation_results.items():
            logger.info(
                "  [%s] %d negative accounts, %d qualifying inquiries, "
                "%d disputable public records.",
                bureau,
                len(eval_result.negative_accounts),
                len(eval_result.qualifying_inquiries),
                len(eval_result.disputable_public_records),
            )

        # Check if there's anything to dispute
        total_items = sum(
            len(e.negative_accounts)
            + len(e.qualifying_inquiries)
            + len(e.disputable_public_records)
            for e in evaluation_results.values()
        )
        if total_items == 0:
            logger.info(
                "No negative accounts, qualifying inquiries, or public records "
                "found. No dispute letters will be generated."
            )
            return

        # ── Stage 3: Validation ──────────────────────────────────────
        logger.info(separator)
        logger.info("STAGE 3 / 4 — VALIDATION (QA GUARDRAIL)")
        logger.info(separator)

        try:
            validation_results = self.validation_agent.validate(
                evaluation_results, extraction_results
            )
        except ValidationError as exc:
            logger.error(separator)
            logger.error("PIPELINE HALTED — VALIDATION FAILURE")
            logger.error(separator)
            logger.error("  Bureau:  %s", exc.bureau)
            logger.error("  Account: %s", exc.account_name)
            logger.error("  Reason:  %s", exc.detail)
            logger.error(separator)
            raise

        for bureau, val_result in validation_results.items():
            status = "PASSED" if val_result.validation_passed else "FAILED"
            logger.info(
                "  [%s] Validation %s — %d negatives, %d inquiries, "
                "%d public records verified.",
                bureau,
                status,
                len(val_result.verified_negatives),
                len(val_result.verified_inquiries),
                len(val_result.verified_public_records),
            )

        # ── Stage 4: Drafting ────────────────────────────────────────
        logger.info(separator)
        logger.info("STAGE 4 / 4 — DRAFTING (RAG + CLAUDE)")
        logger.info(separator)

        # Use personal info from the first extraction
        personal_info = extraction_results[0].personal_info

        letters = self.drafting_agent.run(
            personal_info=personal_info,
            validated=validation_results,
            client_name=self.client_name,
            current_phone=self.current_phone,
        )

        # ── Summary ──────────────────────────────────────────────────
        logger.info(separator)
        logger.info("PIPELINE COMPLETE")
        logger.info(separator)

        client_output_dir = config.OUTPUT_DIR / self.client_name
        logger.info("OUTPUT FOLDER: %s", client_output_dir)

        if not letters:
            logger.warning(
                "No dispute letters were generated for '%s'. "
                "No negative items were found across any bureau.",
                self.client_name,
            )
            return

        logger.info(
            "Generated %d of 3 bureau dispute letter(s) for client '%s':",
            len(letters),
            self.client_name,
        )
        for i, letter in enumerate(letters, 1):
            logger.info("  Letter %d/3 — %s", i, letter.bureau)
            logger.info("    DOCX : %s", letter.docx_path)
            if letter.pdf_path:
                logger.info("    PDF  : %s", letter.pdf_path)
            else:
                logger.info("    PDF  : (skipped — Microsoft Word not found)")

        bureaus_done = {l.bureau for l in letters}
        missing = [b for b in config.BUREAUS if b not in bureaus_done]
        if missing:
            logger.info(
                "  Bureaus with no disputes (no letter sent): %s",
                ", ".join(missing),
            )


# ── RAG ingestion command ────────────────────────────────────────────────────

def ingest_rag_documents() -> None:
    """Ingest reference documents into all ChromaDB RAG collections.

    - Writer Agent knowledge base    → config.WRITER_RAG_COLLECTION
    - Filter Agent knowledge base    → config.FILTER_RAG_COLLECTION
    - Guardrail Agent knowledge base → config.GUARDRAIL_RAG_COLLECTION
    """
    # ── Writer RAG knowledge base ───────────────────────────────────
    logger.info("Ingesting Writer RAG knowledge from: %s", config.WRITER_RAG_DIR)
    collection = init_store(
        persist_dir=config.CHROMA_DB_DIR,
        collection_name=config.WRITER_RAG_COLLECTION,
    )
    count = ingest_reference_docs(
        collection=collection,
        docs_path=config.WRITER_RAG_DIR,
        chunk_size=config.RAG_CHUNK_SIZE,
        chunk_overlap=config.RAG_CHUNK_OVERLAP,
    )
    if count > 0:
        logger.info("Writer RAG: ingested %d chunks.", count)
    else:
        logger.warning("No Writer RAG documents found in: %s", config.WRITER_RAG_DIR)

    # ── Filter RAG knowledge base ────────────────────────────────────
    logger.info("Ingesting Filter RAG knowledge from: %s", config.FILTER_RAG_DIR)
    filter_collection = init_store(
        persist_dir=config.CHROMA_DB_DIR,
        collection_name=config.FILTER_RAG_COLLECTION,
    )
    filter_count = ingest_reference_docs(
        collection=filter_collection,
        docs_path=config.FILTER_RAG_DIR,
        chunk_size=config.RAG_CHUNK_SIZE,
        chunk_overlap=config.RAG_CHUNK_OVERLAP,
    )
    if filter_count > 0:
        logger.info("Filter RAG: ingested %d chunks.", filter_count)
    else:
        logger.warning("No Filter RAG documents found in: %s", config.FILTER_RAG_DIR)

    # ── Guardrail RAG knowledge base ─────────────────────────────────
    logger.info("Ingesting Guardrail RAG knowledge from: %s", config.GUARDRAIL_RAG_DIR)
    guardrail_collection = init_store(
        persist_dir=config.CHROMA_DB_DIR,
        collection_name=config.GUARDRAIL_RAG_COLLECTION,
    )
    guardrail_count = ingest_reference_docs(
        collection=guardrail_collection,
        docs_path=config.GUARDRAIL_RAG_DIR,
        chunk_size=config.RAG_CHUNK_SIZE,
        chunk_overlap=config.RAG_CHUNK_OVERLAP,
    )
    if guardrail_count > 0:
        logger.info("Guardrail RAG: ingested %d chunks.", guardrail_count)
    else:
        logger.warning("No Guardrail RAG documents found in: %s", config.GUARDRAIL_RAG_DIR)


# ── CLI entry point ──────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser.

    Returns:
        Configured argument parser.
    """
    parser = argparse.ArgumentParser(
        prog="credit-dispute-generator",
        description=(
            "Multi-agent credit dispute letter generator. "
            "Ingests credit report PDFs, identifies negative items, "
            "validates the dispute list, and drafts bureau-specific "
            "dispute letters using Claude 4.5 Sonnet + RAG."
        ),
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ── Generate command ─────────────────────────────────────────────
    gen_parser = subparsers.add_parser(
        "generate",
        help="Generate dispute letters from credit report PDFs.",
    )
    gen_parser.add_argument(
        "--client",
        required=True,
        help="Client name (used for input/output folder names).",
    )
    gen_parser.add_argument(
        "--reports",
        nargs="+",
        required=True,
        metavar="PDF",
        help=(
            "Path(s) to credit report PDF(s). Three modes supported:\n"
            "  1 PDF  — combined report containing all 3 bureaus\n"
            "  2 PDFs — two separate bureau reports (bureau auto-detected)\n"
            "  3 PDFs — one per bureau (Experian, Equifax, TransUnion)"
        ),
    )
    gen_parser.add_argument(
        "--phone",
        default=None,
        metavar="DIGITS",
        help=(
            "Current phone number, digits only (e.g. 5558675309). "
            "Adds an address/phone cleanup section to each letter requesting "
            "removal of all outdated addresses and phone numbers."
        ),
    )

    # ── Ingest RAG command ───────────────────────────────────────────
    subparsers.add_parser(
        "ingest-rag",
        help="Ingest reference letter templates into the RAG vector store.",
    )

    return parser


def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "ingest-rag":
        ingest_rag_documents()
        return

    if args.command == "generate":
        # Validate PDF count
        if not (1 <= len(args.reports) <= 3):
            logger.error(
                "Expected 1 combined PDF or 2–3 separate bureau PDFs, "
                "got %d. Accepted counts: 1, 2, or 3.",
                len(args.reports),
            )
            sys.exit(1)

        # Validate PDF paths exist
        for path in args.reports:
            if not Path(path).exists():
                logger.error("PDF not found: %s", path)
                sys.exit(1)

        # If --phone was not supplied on the CLI, ask via popup dialog
        if args.phone is None:
            args.phone = _ask_phone_popup()

        try:
            pipeline = DisputePipeline(
                client_name=args.client,
                pdf_paths=args.reports,
                current_phone=args.phone,
            )
            pipeline.run()
        except ValidationError as exc:
            logger.error("Aborting due to validation failure: %s", exc)
            sys.exit(2)
        except Exception as exc:
            logger.error("Pipeline failed: %s", exc, exc_info=True)
            sys.exit(1)


if __name__ == "__main__":
    main()
