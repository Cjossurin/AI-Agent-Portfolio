"""
DataExtraction Agent — *The Parser*

Ingests raw PDF credit reports and extracts all text into a structured
JSON format using pdfplumber for text extraction and Claude 4.5 Sonnet
for intelligent structuring of the unstructured text.

Pipeline position: **1 of 4** (first agent in the chain)

Input:  1 combined PDF  OR  3 separate bureau PDFs
Output: list[ExtractionResult] — one per bureau
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

import chromadb
from anthropic import Anthropic
from prompt_templates import (
    JERGEN_ACCOUNTS_PROMPT,
    JERGEN_INQUIRIES_PROMPT,
    JERGEN_PERSONAL_INFO_PROMPT,
    JERGEN_PUBLIC_RECORDS_PROMPT,
)

import config
from models.schemas import (
    PersonalInfo,
    CreditAccount,
    HardInquiry,
    PublicRecord,
    PublicRecordType,
    ExtractionResult,
    PaymentHistory,
    PaymentStatus,
)
from utils.pdf_utils import extract_text_from_pdf, split_combined_report
from utils.rag_store import query as rag_query

logger = logging.getLogger(__name__)


class DataExtractionAgent:
    """Extracts structured credit data from raw PDF reports via Claude 4.5 Sonnet.

    The agent uses pdfplumber for raw-text extraction, then injects semantically
    retrieved Parser RAG context into each Claude prompt using XML delimiters,
    a <scratchpad> reasoning block, few-shot <example> blocks, and an <answer>
    output gate — following Metaprompt production principles.

    Attributes:
        client: Anthropic API client instance.
        model:  Model identifier (Claude 4.5 Sonnet).
        parser_rag_collection: Optional ChromaDB collection for Parser RAG retrieval.
    """

    # ─────────────────────────────────────────────────────────────────────────
    # System prompts  (Metaprompt style: XML delimiters, scratchpad, few-shot,
    # answer-gated output)
    # ─────────────────────────────────────────────────────────────────────────

        _PERSONAL_INFO_PROMPT = JERGEN_PERSONAL_INFO_PROMPT

        _ACCOUNTS_PROMPT = JERGEN_ACCOUNTS_PROMPT

        _INQUIRIES_PROMPT = JERGEN_INQUIRIES_PROMPT
        _PUBLIC_RECORDS_PROMPT = JERGEN_PUBLIC_RECORDS_PROMPT
    # ── Constructor ──────────────────────────────────────────────────────

    def __init__(
        self,
        anthropic_client: Anthropic,
        parser_rag_collection: Optional[chromadb.Collection] = None,
    ) -> None:
        """Initialize the extraction agent.

        Args:
            anthropic_client: Pre-configured Anthropic client instance.
            parser_rag_collection: Optional ChromaDB collection for Parser RAG
                context retrieval. When provided, each extraction call queries
                the store for relevant bureau-parsing guidance.
        """
        self.client = anthropic_client
        self.model = config.MODEL_NAME
        self.parser_rag_collection = parser_rag_collection

    # ── RAG context retrieval ────────────────────────────────────────────

    def _get_parser_context(self, query_text: str) -> str:
        """Retrieve relevant Parser RAG chunks and format as context text.

        Args:
            query_text: Semantic query describing the extraction task.

        Returns:
            Concatenated context string, or placeholder if RAG not available.
        """
        if self.parser_rag_collection is None:
            return "(No parser RAG context available.)"
        try:
            chunks = rag_query(
                self.parser_rag_collection,
                query_text,
                n_results=config.RAG_TOP_K,
            )
            if not chunks:
                return "(No relevant parser RAG context found.)"
            return "\n\n---\n\n".join(chunks)
        except Exception as exc:
            logger.warning("Parser RAG query failed: %s", exc)
            return "(Parser RAG query error — proceeding without context.)"

    # ── JSON extraction helper ────────────────────────────────────────────

    def _extract_json(self, response_text: str, expect_array: bool = False) -> object:
        """Extract JSON from Claude response with 3-tier fallback.

        Tier 1: Content inside <answer>...</answer> tags.
        Tier 2: Raw json.loads on the full response.
        Tier 3: Regex search for the outermost { } or [ ] block.

        Args:
            response_text: Claude raw response string.
            expect_array:  True when expecting a JSON array, False for object.

        Returns:
            Parsed Python dict or list.

        Raises:
            ValueError: If no valid JSON could be extracted.
        """
        # Tier 1 — <answer> tags
        answer_match = re.search(
            r"<answer>\s*([\s\S]*?)\s*</answer>", response_text, re.IGNORECASE
        )
        if answer_match:
            candidate = answer_match.group(1).strip()
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        # Tier 2 — raw parse
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            pass

        # Tier 3 — regex extraction
        pattern = r"\[[\s\S]*\]" if expect_array else r"\{[\s\S]*\}"
        match = re.search(pattern, response_text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        raise ValueError(
            f"Could not extract valid JSON from Claude response "
            f"({'array' if expect_array else 'object'} expected):\n"
            f"{response_text[:500]}"
        )

    # ── Claude helper ────────────────────────────────────────────────────

    def _call_claude(self, system: str, user_content: str) -> str:
        """Send a prompt to Claude and return the response text."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=config.MAX_TOKENS,
            temperature=config.TEMPERATURE,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )
        return response.content[0].text

    # ── Parsing methods ──────────────────────────────────────────────────

    def parse_personal_info(self, raw_text: str) -> PersonalInfo:
        """Extract the consumer's personal information using Claude.

        Args:
            raw_text: Raw text extracted from the credit report PDF.

        Returns:
            Populated PersonalInfo model.
        """
        logger.info("Parsing personal information via Claude ...")
        rag_context = self._get_parser_context(
            "personal information fields name address SSN phone email "
            "date of birth bureau format header consumer identity section"
        )
        system_prompt = self._PERSONAL_INFO_PROMPT.replace("{rag_context}", rag_context)
        user_message = (
            "<credit_report_text>\n" + raw_text + "\n</credit_report_text>"
        )
        response_text = self._call_claude(system_prompt, user_message)
        data = self._extract_json(response_text, expect_array=False)
        return PersonalInfo(**data)

    def parse_accounts(self, raw_text: str, bureau: str) -> list[CreditAccount]:
        """Extract all credit accounts / trade lines using Claude.

        Args:
            raw_text: Raw text from one bureau's section of the report.
            bureau: Bureau name (Experian, Equifax, or TransUnion).

        Returns:
            List of CreditAccount models with payment histories.
        """
        logger.info("Parsing credit accounts for %s via Claude ...", bureau)
        rag_context = self._get_parser_context(
            f"{bureau} credit account trade line extraction payment history "
            "status normalization Metro2 codes pdfplumber table layout"
        )
        system_prompt = (
            self._ACCOUNTS_PROMPT
            .replace("{rag_context}", rag_context)
            .replace("{bureau}", bureau)
        )
        user_message = (
            "<credit_report_text>\n" + raw_text + "\n</credit_report_text>"
        )
        response_text = self._call_claude(system_prompt, user_message)
        raw_accounts = self._extract_json(response_text, expect_array=True)

        accounts: list[CreditAccount] = []
        for raw in raw_accounts:
            ph_entries: list[PaymentHistory] = []
            for entry in raw.get("payment_history", []):
                try:
                    status = PaymentStatus(entry.get("status", "UNKNOWN"))
                except ValueError:
                    status = PaymentStatus.UNKNOWN
                ph_entries.append(
                    PaymentHistory(
                        month=entry["month"],
                        year=entry["year"],
                        status=status,
                    )
                )
            raw["payment_history"] = ph_entries
            raw["bureau"] = bureau
            accounts.append(CreditAccount(**raw))

        logger.info("Extracted %d accounts from %s.", len(accounts), bureau)
        return accounts

    def parse_inquiries(self, raw_text: str, bureau: str) -> list[HardInquiry]:
        """Extract all hard inquiries using Claude.

        Args:
            raw_text: Raw text from one bureau's section of the report.
            bureau: Bureau name.

        Returns:
            List of HardInquiry models.
        """
        logger.info("Parsing hard inquiries for %s via Claude ...", bureau)
        rag_context = self._get_parser_context(
            f"{bureau} hard inquiry extraction Regular Inquiries section "
            "soft inquiry exclusion promotional account review date format"
        )
        system_prompt = (
            self._INQUIRIES_PROMPT
            .replace("{rag_context}", rag_context)
            .replace("{bureau}", bureau)
        )
        user_message = (
            "<credit_report_text>\n" + raw_text + "\n</credit_report_text>"
        )
        response_text = self._call_claude(system_prompt, user_message)
        raw_inquiries = self._extract_json(response_text, expect_array=True)

        inquiries = [
            HardInquiry(
                creditor_name=inq["creditor_name"],
                inquiry_date=inq.get("inquiry_date"),
                bureau=bureau,
            )
            for inq in raw_inquiries
        ]
        logger.info("Extracted %d hard inquiries from %s.", len(inquiries), bureau)
        return inquiries

    def parse_public_records(self, raw_text: str, bureau: str) -> list[PublicRecord]:
        """Extract all public records (bankruptcies, judgments, liens) using Claude.

        Args:
            raw_text: Raw text from one bureau's section of the report.
            bureau: Bureau name.

        Returns:
            List of PublicRecord models. Empty if none found on the report.
        """
        logger.info("Parsing public records for %s via Claude ...", bureau)
        rag_context = self._get_parser_context(
            f"{bureau} public records bankruptcy judgment lien extraction "
            "court filing date status discharged satisfied released"
        )
        system_prompt = (
            self._PUBLIC_RECORDS_PROMPT
            .replace("{rag_context}", rag_context)
            .replace("{bureau}", bureau)
        )
        user_message = (
            "<credit_report_text>\n" + raw_text + "\n</credit_report_text>"
        )
        response_text = self._call_claude(system_prompt, user_message)
        raw_records = self._extract_json(response_text, expect_array=True)

        records: list[PublicRecord] = []
        for raw in raw_records:
            try:
                record_type = PublicRecordType(raw.get("record_type", "BANKRUPTCY"))
            except ValueError:
                record_type = PublicRecordType.BANKRUPTCY
            raw["record_type"] = record_type
            raw["bureau"] = bureau
            records.append(PublicRecord(**raw))

        logger.info("Extracted %d public records from %s.", len(records), bureau)
        return records

    # ── Bureau auto-detection ────────────────────────────────────────────

    @staticmethod
    def detect_bureau_from_filename(path: str) -> str | None:
        """Detect bureau from the PDF filename before falling back to text scan.

        Args:
            path: Full or relative path to the PDF file.

        Returns:
            Bureau name ('Equifax', 'Experian', 'TransUnion') or None.
        """
        import os
        fname = os.path.basename(path).lower()
        if "equifax" in fname:
            return "Equifax"
        if "experian" in fname:
            return "Experian"
        if "transunion" in fname or "trans_union" in fname or "trans union" in fname:
            return "TransUnion"
        return None

    @staticmethod
    def detect_bureau_from_text(raw_text: str) -> str | None:
        """Identify which credit bureau a report belongs to via keyword scan.

        Args:
            raw_text: Full extracted text from a single PDF.

        Returns:
            Bureau name or None if undetected.
        """
        patterns: dict[str, str] = {
            "Experian":   r"(?i)\bexperian\b",
            "Equifax":    r"(?i)\bequifax\b",
            "TransUnion": r"(?i)\btrans\s*union\b",
        }
        scores: dict[str, int] = {}
        for bureau, pattern in patterns.items():
            scores[bureau] = len(re.findall(pattern, raw_text))

        best = max(scores, key=lambda b: scores[b])
        if scores[best] == 0:
            return None
        logger.debug("Bureau detection scores: %s → detected '%s'", scores, best)
        return best

    # ── Main entry point ─────────────────────────────────────────────────

    def run(self, pdf_paths: list[str]) -> list[ExtractionResult]:
        """Execute the full extraction pipeline.

        Accepts 1 combined PDF or 2-3 separate bureau PDFs.

        Args:
            pdf_paths: List of 1, 2, or 3 file paths to credit report PDFs.

        Returns:
            List of ExtractionResult — one per bureau detected.

        Raises:
            ValueError: If the number of PDFs is not between 1 and 3.
        """
        if not (1 <= len(pdf_paths) <= 3):
            raise ValueError(
                f"Expected 1 combined PDF or 2-3 separate bureau PDFs, "
                f"got {len(pdf_paths)}."
            )

        bureau_texts: dict[str, str] = {}

        if len(pdf_paths) == 1:
            logger.info("Processing 1 combined credit report ...")
            raw_text = extract_text_from_pdf(pdf_paths[0])
            bureau_texts = split_combined_report(raw_text)

            if "Combined" in bureau_texts:
                combined = bureau_texts.pop("Combined")
                for bureau in config.BUREAUS:
                    bureau_texts[bureau] = combined
        else:
            detected_bureaus: list[tuple[str, str]] = []
            used_bureaus: set[str] = set()

            for idx, path in enumerate(pdf_paths):
                logger.info(
                    "Extracting report %d/%d from %s ...", idx + 1, len(pdf_paths), path
                )
                text = extract_text_from_pdf(path)
                bureau = (
                    self.detect_bureau_from_filename(path)
                    or self.detect_bureau_from_text(text)
                )

                if bureau and bureau not in used_bureaus:
                    detected_bureaus.append((bureau, text))
                    used_bureaus.add(bureau)
                    logger.info("  → Detected bureau: %s", bureau)
                elif bureau and bureau in used_bureaus:
                    fallback = next(
                        (b for b in config.BUREAUS if b not in used_bureaus), None
                    )
                    if fallback:
                        logger.warning(
                            "  Bureau '%s' already mapped; assigning '%s' by fallback.",
                            bureau, fallback,
                        )
                        detected_bureaus.append((fallback, text))
                        used_bureaus.add(fallback)
                    else:
                        logger.warning(
                            "  Could not map report %d to a unique bureau — skipping.",
                            idx + 1,
                        )
                else:
                    fallback = next(
                        (b for b in config.BUREAUS if b not in used_bureaus), None
                    )
                    if fallback:
                        logger.warning(
                            "  Could not detect bureau for report %d; "
                            "assigning '%s' by position.",
                            idx + 1, fallback,
                        )
                        detected_bureaus.append((fallback, text))
                        used_bureaus.add(fallback)

            for bureau, text in detected_bureaus:
                bureau_texts[bureau] = text

        results: list[ExtractionResult] = []
        personal_info: PersonalInfo | None = None

        for bureau, text in bureau_texts.items():
            if personal_info is None:
                personal_info = self.parse_personal_info(text)

            accounts = self.parse_accounts(text, bureau)
            inquiries = self.parse_inquiries(text, bureau)
            public_records = self.parse_public_records(text, bureau)

            results.append(
                ExtractionResult(
                    personal_info=personal_info,
                    accounts=accounts,
                    hard_inquiries=inquiries,
                    public_records=public_records,
                    bureau_source=bureau,
                    raw_text=text,
                )
            )

        logger.info(
            "Extraction complete: %d bureau(s), %d total accounts, %d total inquiries, %d total public records.",
            len(results),
            sum(len(r.accounts) for r in results),
            sum(len(r.hard_inquiries) for r in results),
            sum(len(r.public_records) for r in results),
        )
        return results
