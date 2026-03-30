"""
PDF text-extraction helpers using pdfplumber.

Provides utilities to pull raw text and table data from credit-report PDFs,
handling multi-page documents and common formatting quirks.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pdfplumber

logger = logging.getLogger(__name__)


def extract_text_from_pdf(pdf_path: str | Path) -> str:
    """Extract all text content from a PDF file, page by page.

    Args:
        pdf_path: Absolute or relative path to the PDF file.

    Returns:
        Concatenated text from every page, separated by page markers.

    Raises:
        FileNotFoundError: If the PDF does not exist at the given path.
        pdfplumber.pdfminer.pdfparser.PDFSyntaxError: If the file is not a valid PDF.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    pages_text: list[str] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            tables = page.extract_tables() or []

            # Append any table rows that weren't captured in the text extraction
            table_text_parts: list[str] = []
            for table in tables:
                for row in table:
                    cleaned = [cell.strip() if cell else "" for cell in row]
                    table_text_parts.append(" | ".join(cleaned))

            combined = text
            if table_text_parts:
                combined += "\n[TABLE DATA]\n" + "\n".join(table_text_parts)

            pages_text.append(f"--- PAGE {page_num} ---\n{combined}")
            logger.debug("Extracted page %d (%d chars)", page_num, len(combined))

    full_text = "\n\n".join(pages_text)
    logger.info(
        "Extracted %d pages (%d total chars) from %s",
        len(pages_text),
        len(full_text),
        pdf_path.name,
    )
    return full_text


def split_combined_report(raw_text: str) -> dict[str, str]:
    """Attempt to split a combined 3-bureau report into per-bureau sections.

    Uses common header patterns found in combined credit reports to identify
    where each bureau's section begins. Falls back to returning the full text
    under a 'Combined' key if no bureau headers are detected.

    Args:
        raw_text: Full text extracted from a combined credit report PDF.

    Returns:
        Dict mapping bureau name → the raw text section for that bureau.
    """
    import re

    bureau_patterns: dict[str, str] = {
        "Experian": r"(?i)(experian\s*(credit\s*)?report|experian\s*section)",
        "Equifax": r"(?i)(equifax\s*(credit\s*)?report|equifax\s*section)",
        "TransUnion": r"(?i)(trans\s*union\s*(credit\s*)?report|trans\s*union\s*section)",
    }

    # Find start positions for each bureau section
    positions: list[tuple[int, str]] = []
    for bureau, pattern in bureau_patterns.items():
        match = re.search(pattern, raw_text)
        if match:
            positions.append((match.start(), bureau))

    if len(positions) < 2:
        # Cannot reliably split — return full text as combined
        logger.warning(
            "Could not detect separate bureau sections; treating as combined report."
        )
        return {"Combined": raw_text}

    # Sort by position in text
    positions.sort(key=lambda x: x[0])

    sections: dict[str, str] = {}
    for i, (start, bureau) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(raw_text)
        sections[bureau] = raw_text[start:end].strip()

    logger.info("Split combined report into sections: %s", list(sections.keys()))
    return sections
