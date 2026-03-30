"""
Drafting Agent — *The Writer*

Single-prompt Writer-RAG pipeline that produces FCRA-compliant dispute
letters — one per bureau — using only the following legal frameworks:

  • Late-payment disputes  → FCRA 15 U.S.C. § 1681i
  • Hard-inquiry disputes  → FCRA 15 U.S.C. § 1681b
  • Public record disputes → FCRA 15 U.S.C. § 1681c + § 1681i

Letters are concise, direct, and system-friendly — no verbose legal
paragraphs per item, just clean section headings with bullet lists and
a single FCRA closing.  Tone: firm, professional, factual.

Pipeline position: **4 of 4** (final agent)

Input:
  • PersonalInfo                  — consumer details for letter header
  • dict[str, ValidationResult]  — verified dispute items per bureau
  • client_name                   — output directory naming

Output: list[DisputeLetter] — up to 3 letters saved as DOCX + PDF
"""

from __future__ import annotations

import json as _json
import logging
import re
from datetime import datetime
from pathlib import Path

import chromadb
from anthropic import Anthropic
from prompt_templates import JERGEN_DRAFTING_LETTER_PROMPT

import config
from models.schemas import (
    DisputeLetter,
    DisputePublicRecord,
    NegativeItem,
    PersonalInfo,
    QualifyingInquiry,
    ValidationResult,
)
from utils.doc_writer import write_docx, convert_to_pdf
from utils.rag_store import query as rag_query

logger = logging.getLogger(__name__)


class DraftingAgent:
    """Generates FCRA-compliant dispute letters via a single-prompt Writer-RAG call.

    Dispute data is formatted into concise bullet lists deterministically,
    then one Claude call assembles a clean, direct letter tailored to the
    specific credit file.  No verbose per-item legal paragraphs.

    Attributes:
        client: Anthropic API client.
        model: Model identifier from config.
        rag_collection: ChromaDB Writer RAG collection.
    """

    # ── Single letter-generation prompt ──────────────────────────────────────
     _LETTER_PROMPT = JERGEN_DRAFTING_LETTER_PROMPT

    # ── Constructor ───────────────────────────────────────────────────────────

    def __init__(
        self,
        anthropic_client: Anthropic,
        rag_collection: chromadb.Collection,
    ) -> None:
        """Initialize the Drafting Agent.

        Args:
            anthropic_client: Pre-configured Anthropic client.
            rag_collection: ChromaDB Writer RAG collection (writer_rag).
        """
        self.client = anthropic_client
        self.model = config.MODEL_NAME
        self.rag_collection = rag_collection

    # ── RAG + LLM helpers ─────────────────────────────────────────────────────

    def _get_writer_context(self, query_text: str) -> str:
        """Query the Writer RAG collection and return top-k chunks as one string."""
        if self.rag_collection is None:
            return "(No Writer RAG context available.)"
        try:
            chunks = rag_query(
                self.rag_collection,
                query_text=query_text,
                n_results=config.RAG_TOP_K,
            )
            if not chunks:
                return "(No relevant Writer RAG context found.)"
            logger.info("Writer RAG returned %d chunk(s).", len(chunks))
            return "\n\n---\n\n".join(chunks)
        except Exception as exc:
            logger.warning("Writer RAG query failed: %s", exc)
            return "(Writer RAG query error.)"

    def _call_claude(
        self,
        system: str,
        user_content: str,
        max_tokens: int = 3000,
    ) -> str:
        """Call Claude with system + user message; return response text."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=config.DRAFTING_TEMPERATURE,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )
        return response.content[0].text

    @staticmethod
    def _sanitize_json_newlines(s: str) -> str:
        """Escape literal newlines/carriage-returns that appear inside JSON string values.

        JSON requires newline characters within string values to be encoded as
        the two-character sequence \\n.  When Claude writes multi-paragraph prose
        directly inside a JSON string, the literal line-breaks make the JSON
        invalid.  This method performs a single character-by-character pass to
        replace those bare newlines with their escaped equivalents, leaving
        everything else (including already-escaped sequences) untouched.
        """
        result: list[str] = []
        in_string = False
        escape_next = False
        for ch in s:
            if escape_next:
                result.append(ch)
                escape_next = False
            elif ch == "\\":
                result.append(ch)
                escape_next = True
            elif ch == '"':
                in_string = not in_string
                result.append(ch)
            elif in_string and ch == "\n":
                result.append("\\n")
            elif in_string and ch == "\r":
                result.append("\\r")
            else:
                result.append(ch)
        return "".join(result)

    @staticmethod
    def _extract_json_from_answer(text: str) -> dict:
        """Extract JSON payload from <answer>…</answer> tags (5-tier fallback).

        Tier 1  – parse JSON inside <answer> tags as-is.
        Tier 2  – sanitize literal newlines inside the <answer> block, then parse.
        Tier 3  – parse the full response text as-is.
        Tier 4  – sanitize the full response text, then parse.
        Tier 5  – regex-find first {...} block, sanitize, then parse.
        """
        def _try(s: str) -> dict | None:
            try:
                return _json.loads(s)
            except _json.JSONDecodeError:
                return None

        sanitize = DraftingAgent._sanitize_json_newlines

        m = re.search(r"<answer>\s*([\s\S]*?)\s*</answer>", text, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip()
            result = _try(candidate) or _try(sanitize(candidate))
            if result is not None:
                return result

        result = _try(text) or _try(sanitize(text))
        if result is not None:
            return result

        m2 = re.search(r"\{[\s\S]*\}", text)
        if m2:
            result = _try(m2.group()) or _try(sanitize(m2.group()))
            if result is not None:
                return result

        raise ValueError(f"Could not parse JSON from response: {text[:300]}")

    # ── Section drafters ──────────────────────────────────────────────────────

    # ── Section formatters (deterministic, no Claude calls) ─────────────────

    @staticmethod
    def _format_late_payment_bullets(items: list[NegativeItem]) -> str:
        """Format negative accounts as concise bullet lines."""
        if not items:
            return ""
        lines: list[str] = []
        for item in items:
            acct = item.account
            name = acct.account_name
            num_part = f" (#{acct.account_number_partial})" if acct.account_number_partial else ""
            marks = ", ".join(
                f"{m.status.value.replace('_', ' ')} {m.month}/{m.year}"
                for m in item.negative_marks[:8]
            )
            lines.append(f"\u2022 {name}{num_part} \u2013 {marks}")
        return "\n".join(lines)

    @staticmethod
    def _format_inquiry_bullets(inquiries: list[QualifyingInquiry]) -> str:
        """Format hard inquiries as concise bullet lines."""
        if not inquiries:
            return ""
        lines: list[str] = []
        for qi in inquiries:
            name = qi.inquiry.creditor_name
            date = qi.inquiry.inquiry_date or "Unknown"
            lines.append(f"\u2022 {name} \u2013 {date}")
        return "\n".join(lines)

    @staticmethod
    def _format_public_record_bullets(records: list[DisputePublicRecord]) -> str:
        """Format public records as concise bullet lines."""
        if not records:
            return ""
        lines: list[str] = []
        for pr in records:
            rec = pr.record
            desc = rec.description or rec.record_type.value.title()
            date = rec.filing_date or "Unknown date"
            status = rec.status or "Unknown status"
            case = f" (Case #{rec.case_number})" if rec.case_number else ""
            lines.append(f"\u2022 {desc}{case} \u2013 Filed {date} \u2013 {status}")
        return "\n".join(lines)

    def _assemble_letter(
        self,
        bureau: str,
        consumer_name: str,
        dispute_data: str,
    ) -> str:
        """Single Claude call that assembles a concise, direct dispute letter."""
        rag_ctx = self._get_writer_context(
            f"credit dispute letter concise direct FCRA {bureau}"
        )
        user_msg = (
            self._LETTER_PROMPT
            .replace("{$WRITER_RAG_CONTEXT}", rag_ctx)
            .replace("{$BUREAU}", bureau)
            .replace("{$CONSUMER_NAME}", consumer_name)
            .replace("{$DISPUTE_DATA}", dispute_data)
        )
        logger.info("Generating concise letter for %s …", bureau)
        raw = self._call_claude(
            "You write concise credit dispute letters. Be direct. No fluff.",
            user_msg,
            max_tokens=config.DRAFTING_MAX_TOKENS,
        )
        result = self._extract_json_from_answer(raw)
        return result.get("letter_body", raw).strip()

    @staticmethod
    def _get_current_date() -> str:
        """Return the current date as a human-readable string.

        Dynamically generated at execution time.

        Returns:
            Date string like 'February 28, 2026'.
        """
        return datetime.now().strftime("%B %d, %Y")

    @staticmethod
    def _format_personal_block(personal_info: PersonalInfo) -> str:
        """Format the consumer's personal information for the letter header.

        Args:
            personal_info: Consumer details.

        Returns:
            Multi-line string block.
        """
        lines = [
            personal_info.full_name,
            personal_info.current_address,
        ]
        if personal_info.phone:
            lines.append(f"Phone: {personal_info.phone}")
        if personal_info.email:
            lines.append(f"Email: {personal_info.email}")
        if personal_info.ssn_last4:
            lines.append(f"SSN (last 4): ***-**-{personal_info.ssn_last4}")
        if personal_info.date_of_birth:
            lines.append(f"Date of Birth: {personal_info.date_of_birth}")
        return "\n".join(lines)

    @staticmethod
    def _format_negative_accounts(items: list[NegativeItem]) -> str:
        """Format the negative accounts into a readable list for the prompt.

        Args:
            items: Verified negative accounts.

        Returns:
            Numbered list string.
        """
        if not items:
            return "(No negative accounts to dispute.)"

        lines: list[str] = []
        for i, item in enumerate(items, 1):
            acct = item.account
            acct_num = acct.account_number_partial or "N/A"
            lines.append(
                f"{i}. Account: {acct.account_name}\n"
                f"   Account Number: {acct_num}\n"
                f"   Account Type: {acct.account_type or 'N/A'}\n"
                f"   Negative Marks: {item.reason}\n"
                f"   Requested Action: Remove the reported late payment(s)"
            )
        return "\n\n".join(lines)

    @staticmethod
    def _format_inquiries(inquiries: list[QualifyingInquiry]) -> str:
        """Format the qualifying inquiries into a readable list.

        Args:
            inquiries: Verified hard inquiries for dispute.

        Returns:
            Numbered list string.
        """
        if not inquiries:
            return "(No hard inquiries to dispute.)"

        lines: list[str] = []
        for i, qi in enumerate(inquiries, 1):
            inq = qi.inquiry
            date = inq.inquiry_date or "Unknown date"
            lines.append(
                f"{i}. Creditor: {inq.creditor_name}\n"
                f"   Inquiry Date: {date}\n"
                f"   Reason for Dispute: {qi.reason}\n"
                f"   Requested Action: Remove this unauthorized hard inquiry"
            )
        return "\n\n".join(lines)

    @staticmethod
    def _format_public_records(records: list[DisputePublicRecord]) -> str:
        """Format the public records into a readable list for the prompt."""
        if not records:
            return "(No public records to dispute.)"

        lines: list[str] = []
        for i, pr in enumerate(records, 1):
            rec = pr.record
            lines.append(
                f"{i}. Type: {rec.record_type.value}\n"
                f"   Description: {rec.description}\n"
                f"   Case Number: {rec.case_number or 'N/A'}\n"
                f"   Filing Date: {rec.filing_date or 'N/A'}\n"
                f"   Status: {rec.status or 'N/A'}\n"
                f"   Reason for Dispute: {pr.reason}\n"
                f"   Requested Action: Verify and delete if unverifiable"
            )
        return "\n\n".join(lines)

    @staticmethod
    def _build_address_phone_section(
        personal_info: PersonalInfo,
        current_phone: str | None,
    ) -> str:
        """Build a concise address/phone correction block for the dispute data."""
        address = personal_info.current_address or "my current address on file"

        lines = [f"Current address: {address}"]
        if current_phone:
            digits = "".join(c for c in current_phone if c.isdigit())
            if len(digits) == 10:
                phone_fmt = f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
            else:
                phone_fmt = current_phone
            lines.append(f"Phone: {phone_fmt}")

        return "\n".join(lines)

    def build_letter_context(
        self,
        bureau: str,
        personal_info: PersonalInfo,
        validation_result: ValidationResult,
    ) -> str:
        """Assemble the full prompt context for letter generation.

        Combines the consumer's information, date, bureau address,
        and all disputed items into a structured prompt.

        Args:
            bureau: Target bureau name.
            personal_info: Consumer's personal details.
            validation_result: Verified dispute items for this bureau.

        Returns:
            Complete user-prompt string for Claude.
        """
        current_date = self._get_current_date()
        bureau_address = config.BUREAU_ADDRESSES.get(bureau, bureau)
        personal_block = self._format_personal_block(personal_info)
        negatives = self._format_negative_accounts(
            validation_result.verified_negatives
        )
        inquiries = self._format_inquiries(
            validation_result.verified_inquiries
        )
        public_records = self._format_public_records(
            validation_result.verified_public_records
        )

        context = (
            f"LETTER DATE: {current_date}\n\n"
            f"CONSUMER INFORMATION:\n{personal_block}\n\n"
            f"RECIPIENT BUREAU:\n{bureau}\n{bureau_address}\n\n"
            f"DISPUTED NEGATIVE ACCOUNTS:\n{negatives}\n\n"
            f"DISPUTED HARD INQUIRIES:\n{inquiries}\n\n"
            f"DISPUTED PUBLIC RECORDS:\n{public_records}"
        )
        return context

    def query_rag_templates(self, bureau: str) -> list[str]:
        """Kept for backward compatibility — delegates to _get_writer_context."""
        ctx = self._get_writer_context(
            f"Credit dispute letter {bureau} FCRA late payments hard inquiries"
        )
        return [ctx] if ctx else []

    # ── Letter generation ────────────────────────────────────────────────

    def generate_letter(
        self,
        bureau: str,
        personal_info: PersonalInfo,
        validation_result: ValidationResult,
        current_phone: str | None = None,
    ) -> str:
        """Generate a concise, direct dispute letter with one Claude call.

        Formats all dispute data into structured bullet lists, then sends
        a single prompt to Claude to assemble a clean letter.

        Args:
            bureau: Target bureau name.
            personal_info: Consumer's personal details.
            validation_result: Verified dispute items for this bureau.
            current_phone: Optional current phone number (digits only).

        Returns:
            Finished letter body as plain text (no header, no sig block).
        """
        # Build structured dispute data for the prompt
        sections: list[str] = []

        # Address/phone correction
        address_block = self._build_address_phone_section(
            personal_info, current_phone
        )
        sections.append(f"ADDRESS CORRECTION:\n{address_block}")

        # Late payment disputes
        lp_bullets = self._format_late_payment_bullets(
            validation_result.verified_negatives
        )
        if lp_bullets:
            sections.append(f"LATE PAYMENT DISPUTES:\n{lp_bullets}")

        # Hard inquiry disputes
        inq_bullets = self._format_inquiry_bullets(
            validation_result.verified_inquiries
        )
        if inq_bullets:
            sections.append(f"UNAUTHORIZED HARD INQUIRIES:\n{inq_bullets}")

        # Public record disputes
        pr_bullets = self._format_public_record_bullets(
            validation_result.verified_public_records
        )
        if pr_bullets:
            sections.append(f"PUBLIC RECORDS DISPUTES:\n{pr_bullets}")

        dispute_data = "\n\n".join(sections)

        # Single Claude call to assemble the letter
        letter_body = self._assemble_letter(
            bureau=bureau,
            consumer_name=personal_info.full_name,
            dispute_data=dispute_data,
        )
        logger.info("Generated %s letter (%d chars).", bureau, len(letter_body))
        return letter_body

    # ── Save letter ──────────────────────────────────────────────────────

    def save_letter(
        self,
        bureau: str,
        content: str,
        personal_info: PersonalInfo,
        client_name: str,
    ) -> DisputeLetter:
        """Save a dispute letter as DOCX and PDF.

        Files are written to ``Dispute Letters/{client_name}/``.

        Args:
            bureau: Bureau name (used in filename).
            content: Full letter body text.
            personal_info: Consumer info for the document header.
            client_name: Client folder name.

        Returns:
            ``DisputeLetter`` model with file paths populated.
        """
        current_date = self._get_current_date()
        date_stamp = datetime.now().strftime("%Y%m%d")
        filename = f"{bureau}_Dispute_Letter_{date_stamp}"

        output_dir = config.OUTPUT_DIR / client_name
        output_dir.mkdir(parents=True, exist_ok=True)

        docx_path = output_dir / f"{filename}.docx"
        write_docx(
            content=content,
            output_path=docx_path,
            personal_info=personal_info,
            bureau=bureau,
            current_date=current_date,
        )

        # Attempt PDF conversion (requires Microsoft Word on Windows)
        pdf_path_str = ""
        try:
            pdf_path = convert_to_pdf(docx_path)
            pdf_path_str = str(pdf_path)
        except RuntimeError as exc:
            logger.warning(
                "PDF conversion skipped for %s: %s", bureau, exc
            )

        return DisputeLetter(
            bureau=bureau,
            content=content,
            docx_path=str(docx_path),
            pdf_path=pdf_path_str,
        )

    # ── Main entry point ─────────────────────────────────────────────────

    def run(
        self,
        personal_info: PersonalInfo,
        validated: dict[str, ValidationResult],
        client_name: str,
        current_phone: str | None = None,
    ) -> list[DisputeLetter]:
        """Generate and save exactly 3 dispute letters — one per bureau.

        A letter is produced for every bureau (Experian, Equifax, TransUnion)
        that has at least one verified negative account or qualifying inquiry.
        The client output folder ``Dispute Letters/{client_name}/`` is created
        automatically before any letters are written.

        Args:
            personal_info: Consumer's extracted personal information.
            validated: Validated dispute list per bureau.
            client_name: Client name used for the output sub-folder.
            current_phone: Optional current phone number (digits only).
                Passed to each letter's address/phone cleanup section.

        Returns:
            List of ``DisputeLetter`` models (one per bureau with items).
            Each entry carries the ``.docx_path`` and ``.pdf_path`` of the
            saved file inside ``Dispute Letters/{client_name}/``.
        """
        # ── Ensure client output folder exists before writing anything ──
        client_output_dir = config.OUTPUT_DIR / client_name
        client_output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(
            "Output folder ready: %s",
            client_output_dir,
        )

        letters: list[DisputeLetter] = []
        skipped: list[str] = []

        for bureau in config.BUREAUS:
            validation_result = validated.get(bureau)

            if validation_result is None:
                skipped.append(f"{bureau} (no report provided)")
                logger.info("  [%s] No report data — letter skipped.", bureau)
                continue

            # No disputable items on this bureau's report
            if (
                not validation_result.verified_negatives
                and not validation_result.verified_inquiries
                and not validation_result.verified_public_records
            ):
                skipped.append(f"{bureau} (no negative items found)")
                logger.info(
                    "  [%s] No negative accounts, qualifying inquiries, or "
                    "public records — no dispute needed for this bureau.", bureau
                )
                continue

            # Generate the full letter (single-prompt pipeline internally)
            content = self.generate_letter(
                bureau, personal_info, validation_result,
                current_phone=current_phone,
            )

            # 4. Save as DOCX + PDF inside Dispute Letters/{client_name}/
            letter = self.save_letter(
                bureau, content, personal_info, client_name
            )
            letters.append(letter)
            logger.info(
                "  [%s] Letter generated → %s",
                bureau,
                client_output_dir,
            )

        if skipped:
            logger.info(
                "Bureaus skipped (%d): %s", len(skipped), "; ".join(skipped)
            )

        logger.info(
            "Drafting complete: %d of 3 bureau letter(s) generated for '%s'.",
            len(letters),
            client_name,
        )
        return letters
