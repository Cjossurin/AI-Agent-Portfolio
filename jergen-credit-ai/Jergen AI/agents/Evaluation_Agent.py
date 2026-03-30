"""
Evaluation Agent — *The Filter*

Pipeline position: 2 of 4
Input:  list[ExtractionResult]
Output: dict[str, EvaluationResult] — keyed by bureau name

Matching stack (per RAG-recommended best practices):
  1. Exact match after normalization          -> method="exact"
  2. Abbreviation dictionary lookup           -> method="abbrev"
  3. Jaro-Winkler >= 0.92 (jellyfish, C impl) -> method="jaro"
  4. Jaro-Winkler in [0.85, 0.92) -> LLM disambiguation -> method="llm"
  5. Score < 0.85                             -> method="no-match"

Time-window logic (FCRA Section 604):
  - 30-day primary window  (most cases)
  - 60-day extended window (slow reporters, manual underwriting)
  - Inquiry attributed -> NOT disputable

Every decision is written to an append-only SHA-256-chained audit log.
Agent is fully backward-compatible: if no Anthropic client is supplied,
LLM steps are skipped and grey-zone matches default to "no-match".
"""

from __future__ import annotations

import calendar
import hashlib
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import config
from prompt_templates import (
    JERGEN_AUDIT_EXPLANATION_PROMPT,
    JERGEN_DISAMBIGUATION_PROMPT,
    JERGEN_RATIONALE_PROMPT,
)
from models.schemas import (
    CreditAccount,
    DisputePublicRecord,
    ExtractionResult,
    EvaluationResult,
    FilterAuditEntry,
    HardInquiry,
    NegativeItem,
    PaymentHistory,
    PublicRecord,
    PublicRecordType,
    QualifyingInquiry,
    NEGATIVE_STATUSES,
)
from utils.rag_store import query as rag_query

logger = logging.getLogger(__name__)

# Thresholds (RAG benchmarks: 99.1% precision / 96.5% recall at 0.92)
_JW_MATCH_THRESHOLD: float = 0.92
_JW_GREY_ZONE_LOW: float = 0.85        # [0.85, 0.92) -> LLM disambiguation
_PRIMARY_WINDOW_DAYS: int = 30
_EXTENDED_WINDOW_DAYS: int = 60

# Legal-form suffixes to strip during normalization
_SUFFIXES: list[str] = sorted(
    [
        "national association", "federal savings bank", "federal credit union",
        "state bank", "savings bank", "credit union", "financial services",
        "financial group", "financial corp", "financial inc", "financial",
        "bank usa", "bank na", "bank n.a", "bank", "mortgage servicing",
        "mortgage corp", "mortgage inc", "mortgage", "auto finance",
        "auto loan", "card services", "card", "services llc", "services inc",
        "services", "holdings llc", "holdings inc", "holdings", "funding llc",
        "funding inc", "funding", "lending llc", "lending", "trust co",
        "trust", "corp", "co.", "co", "inc.", "inc", "llc", "ltd", "na",
        "n.a.", "fsb", "fcu",
    ],
    key=len,
    reverse=True,
)

# Abbreviation dictionary (credit-bureau shorthand -> canonical form)
CREDITOR_ABBREVIATIONS: dict[str, str] = {
    "jpmcb":        "jp morgan chase",
    "jpmcb card":   "jp morgan chase",
    "chase":        "jp morgan chase",
    "capone":       "capital one",
    "cap one":      "capital one",
    "cap1":         "capital one",
    "amex":         "american express",
    "americanexpress": "american express",
    "bofa":         "bank of america",
    "bofana":       "bank of america",
    "bk of amer":   "bank of america",
    "wfhm":         "wells fargo",
    "wf":           "wells fargo",
    "wellsfargo":   "wells fargo",
    "wachovia":     "wells fargo",
    "citi":         "citibank",
    "citicards":    "citibank",
    "td bank":      "td bank usa",
    "usaa":         "usaa federal savings bank",
    "usaa fss":     "usaa federal savings bank",
    "navyfcu":      "navy federal credit union",
    "navy fcu":     "navy federal credit union",
    "penfed":       "pentagon federal credit union",
    "penfed cu":    "pentagon federal credit union",
    "discover fin": "discover",
    "discover fs":  "discover",
    "syncb":        "synchrony",
    "sync bank":    "synchrony",
    "synchrony bank": "synchrony",
    "syncb/ppc":    "synchrony",
    "syncb/amazon": "synchrony",
    "syncb/walmart": "synchrony",
    "syncb/gap":    "synchrony",
    "ge capital":   "synchrony",
    "comenity":     "comenity bank",
    "comenity cap": "comenity bank",
    "webbank":      "webbank",
    "gm fin":       "gm financial",
    "gmfinancial":  "gm financial",
    "ally":         "ally financial",
    "chrysler cap": "chrysler capital",
    "td auto":      "td auto finance",
    "dept of ed":   "department of education",
    "deptofed":     "department of education",
    "AES/pheaa":    "aes",
    "navient":      "navient",
    "fedloan":      "fedloan servicing",
    "sallie mae":   "sallie mae",
    "mr cooper":    "mr cooper",
    "ocwen":        "ocwen loan servicing",
    "loancare":     "loancare",
    "roundpoint":   "roundpoint mortgage",
    "target nb":    "target",
    "target national": "target",
    "tjx":          "tjx companies",
    "kohls":        "kohls",
    "macys":        "macys",
    "nordstrom":    "nordstrom",
    "amazon":       "amazon",
    "affirm":       "affirm",
    "klarna":       "klarna",
    "afterpay":     "afterpay",
}


# ─────────────────────────────────────────────────────────────────────────────
# SHA-256 Immutable Audit Logger
# ─────────────────────────────────────────────────────────────────────────────

class ImmutableLogger:
    """Append-only, SHA-256-chained audit logger for Filter Agent decisions.

    Each entry hashes its own content + the previous entry hash,
    producing a tamper-evident chain (FCRA Section 1681e(b) compliance).
    """

    def __init__(self, output_dir: Optional[Path] = None) -> None:
        self._entries: list[FilterAuditEntry] = []
        self._last_hash: str = "GENESIS"
        self._output_dir = output_dir or (Path(config.BASE_DIR) / "audit_logs")
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._log_path: Optional[Path] = None

    @staticmethod
    def _hash_content(content: dict) -> str:
        serialized = json.dumps(content, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()

    def append(self, entry_data: dict) -> FilterAuditEntry:
        """Add a new entry to the chain and write it to the JSONL log file."""
        entry_data["previous_hash"] = self._last_hash
        entry_data["sha256_hash"] = self._hash_content(entry_data)

        entry = FilterAuditEntry(**entry_data)
        self._entries.append(entry)
        self._last_hash = entry.sha256_hash

        if self._log_path is None:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            self._log_path = self._output_dir / f"filter_audit_log_{ts}.jsonl"

        with self._log_path.open("a", encoding="utf-8") as fh:
            fh.write(entry.model_dump_json() + "\n")

        return entry

    @property
    def entries(self) -> list[FilterAuditEntry]:
        return list(self._entries)


# ─────────────────────────────────────────────────────────────────────────────
# Evaluation Agent
# ─────────────────────────────────────────────────────────────────────────────

class EvaluationAgent:
    """Filters credit report data for negative accounts and disputable inquiries.

    All creditor-name matching uses:
      normalization -> abbreviation lookup -> Jaro-Winkler @ 0.92 -> LLM grey-zone

    All attribution decisions (inquiry <-> account) are checked against
    30-day primary / 60-day extended time windows before qualifying.

    Every decision is recorded in an immutable SHA-256-chained audit log.
    """

    # ── Metaprompt-style prompt 1: Creditor Name Disambiguation ───────────────
        _DISAMBIGUATION_PROMPT = JERGEN_DISAMBIGUATION_PROMPT

    # ── Metaprompt-style prompt 2: Dispute Rationale Generation ───────────────
        _RATIONALE_PROMPT = JERGEN_RATIONALE_PROMPT

    # ── Metaprompt-style prompt 3: Audit Decision Explanation ─────────────────
        _AUDIT_EXPLANATION_PROMPT = JERGEN_AUDIT_EXPLANATION_PROMPT

    # ──────────────────────────────────────────────────────────────────────────

    def __init__(
        self,
        anthropic_client=None,
        filter_rag_collection=None,
    ) -> None:
        """
        Args:
            anthropic_client: Optional Anthropic client. When provided, LLM
                disambiguation and rationale-generation are enabled.
            filter_rag_collection: Optional ChromaDB collection for Filter RAG
                context injected into every LLM prompt.
        """
        self.client = anthropic_client
        self.filter_rag_collection = filter_rag_collection
        self.audit_logger = ImmutableLogger()

    # ── RAG helper ────────────────────────────────────────────────────────────

    def _get_filter_context(self, query_text: str) -> str:
        """Retrieve relevant Filter RAG chunks for a query."""
        if self.filter_rag_collection is None:
            return "(No Filter RAG context available.)"
        try:
            chunks = rag_query(
                self.filter_rag_collection,
                query_text,
                n_results=config.RAG_TOP_K,
            )
            if not chunks:
                return "(No relevant Filter RAG context found.)"
            return "\n\n---\n\n".join(chunks)
        except Exception as exc:
            logger.warning("Filter RAG query failed: %s", exc)
            return "(Filter RAG query error.)"

    # ── Claude call helper ────────────────────────────────────────────────────

    def _call_claude(self, system: str, user_content: str) -> str:
        """Call Claude with a system + user message. Returns response text."""
        if self.client is None:
            raise RuntimeError("Anthropic client is not configured.")
        response = self.client.messages.create(
            model=config.MODEL_NAME,
            max_tokens=512,
            temperature=0.1,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )
        return response.content[0].text

    @staticmethod
    def _extract_json_from_answer(response_text: str) -> dict:
        """Extract JSON object from <answer> tags (3-tier fallback)."""
        import json as _json
        # Tier 1: <answer> tags
        m = re.search(r"<answer>\s*([\s\S]*?)\s*</answer>", response_text, re.IGNORECASE)
        if m:
            try:
                return _json.loads(m.group(1).strip())
            except _json.JSONDecodeError:
                pass
        # Tier 2: raw parse
        try:
            return _json.loads(response_text)
        except _json.JSONDecodeError:
            pass
        # Tier 3: regex
        m2 = re.search(r"\{[\s\S]*\}", response_text)
        if m2:
            try:
                return _json.loads(m2.group())
            except _json.JSONDecodeError:
                pass
        raise ValueError(f"Could not extract JSON: {response_text[:300]}")

    # ── LLM actions ───────────────────────────────────────────────────────────

    def _disambiguate_via_llm(
        self, creditor_a: str, creditor_b: str, score: float
    ) -> tuple[bool, str, str]:
        """Call Claude to resolve a grey-zone creditor-name match (0.85-0.92).

        Returns:
            (match: bool, confidence: str, reason: str)
        """
        rag_ctx = self._get_filter_context(
            f"creditor name fuzzy matching disambiguation {creditor_a} {creditor_b}"
        )
        user_msg = (
            self._DISAMBIGUATION_PROMPT
            .replace("{$CREDITOR_A}", creditor_a)
            .replace("{$CREDITOR_B}", creditor_b)
            .replace("{$SCORE}", f"{score:.4f}")
            .replace("{$FILTER_RAG_CONTEXT}", rag_ctx)
        )
        try:
            raw = self._call_claude("You are a financial data analyst.", user_msg)
            result = self._extract_json_from_answer(raw)
            return (
                bool(result.get("match", False)),
                result.get("confidence", "low"),
                result.get("reason", "LLM disambiguation."),
            )
        except Exception as exc:
            logger.warning("LLM disambiguation failed (%s); defaulting to no-match.", exc)
            return False, "low", f"LLM disambiguation failed: {exc}"

    def _generate_dispute_reason(
        self,
        inquiry: HardInquiry,
        open_positive_accounts: list[CreditAccount],
    ) -> str:
        """Call Claude to generate an FCRA-compliant rationale for a qualifying inquiry."""
        acct_summary = (
            "\n".join(
                f"  - {a.account_name} (opened {a.date_opened or 'unknown'})"
                for a in open_positive_accounts[:10]
            )
            or "(none)"
        )
        rag_ctx = self._get_filter_context(
            f"FCRA section 604 hard inquiry dispute rationale {inquiry.creditor_name}"
        )
        user_msg = (
            self._RATIONALE_PROMPT
            .replace("{$CREDITOR_NAME}", inquiry.creditor_name)
            .replace("{$INQUIRY_DATE}", inquiry.inquiry_date or "unknown")
            .replace("{$BUREAU}", inquiry.bureau)
            .replace("{$OPEN_ACCOUNTS_SUMMARY}", acct_summary)
            .replace("{$FILTER_RAG_CONTEXT}", rag_ctx)
        )
        try:
            raw = self._call_claude("You are a credit dispute specialist.", user_msg)
            result = self._extract_json_from_answer(raw)
            return result.get("reason", "No matching open positive account found.")
        except Exception as exc:
            logger.warning("Rationale generation failed (%s); using default.", exc)
            return "No matching open positive account found under FCRA Section 604."

    def _explain_audit_decision(self, entry: FilterAuditEntry) -> str:
        """Call Claude to produce a human-readable compliance explanation for an audit entry."""
        rag_ctx = self._get_filter_context(
            "FCRA audit trail compliance explanation creditor matching inquiry attribution"
        )
        entry_json = entry.model_dump_json(indent=2)
        user_msg = (
            self._AUDIT_EXPLANATION_PROMPT
            .replace("{$AUDIT_ENTRY_JSON}", entry_json)
            .replace("{$FILTER_RAG_CONTEXT}", rag_ctx)
        )
        try:
            raw = self._call_claude(
                "You are a compliance documentation specialist.", user_msg
            )
            result = self._extract_json_from_answer(raw)
            return result.get("explanation", "Audit entry recorded.")
        except Exception as exc:
            logger.warning("Audit explanation failed (%s).", exc)
            return "Audit entry recorded. Automated explanation unavailable."

    # ── Normalization helpers ─────────────────────────────────────────────────

    @staticmethod
    def expand_abbreviations(name: str) -> str:
        """Expand known credit-bureau abbreviations in a creditor name.

        Checks the full string first, then applies word/phrase substitution.
        """
        lower = name.lower().strip()
        if lower in CREDITOR_ABBREVIATIONS:
            return CREDITOR_ABBREVIATIONS[lower]
        result = lower
        for abbrev, expansion in CREDITOR_ABBREVIATIONS.items():
            pattern = r"\b" + re.escape(abbrev) + r"\b"
            result = re.sub(pattern, expansion, result)
        return result

    @staticmethod
    def normalize_creditor_name(name: str) -> str:
        """Normalize a creditor name for comparison.

        Pipeline:
          1. Lowercase and expand abbreviations
          2. Remove punctuation (keep spaces)
          3. Remove legal suffixes (bank, llc, n.a., etc.)
          4. Collapse whitespace
        """
        if not name:
            return ""
        result = EvaluationAgent.expand_abbreviations(name.lower())
        result = re.sub(r"[^\w\s]", " ", result)
        for suffix in _SUFFIXES:
            pattern = r"\b" + re.escape(suffix) + r"\s*$"
            result = re.sub(pattern, "", result, flags=re.IGNORECASE).strip()
        result = re.sub(r"\s+", " ", result).strip()
        return result

    # ── Jaro-Winkler matching with audit trail ────────────────────────────────

    def _names_match_with_audit(
        self, name_a: str, name_b: str, correlation_id: str
    ) -> tuple[bool, FilterAuditEntry]:
        """Compare two creditor names via the 5-step matching stack.

        Returns:
            (match_result, audit_entry)
        """
        norm_a = self.normalize_creditor_name(name_a)
        norm_b = self.normalize_creditor_name(name_b)

        entry_base = {
            "entry_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "correlation_id": correlation_id,
            "creditor_a": name_a,
            "creditor_b": name_b,
            "normalized_a": norm_a,
            "normalized_b": norm_b,
            "abbreviation_hit": False,
            "jaro_winkler_score": None,
            "match_result": False,
            "match_method": "no-match",
            "llm_confidence": None,
            "llm_reason": None,
            "inquiry_date": None,
            "account_opened": None,
            "days_delta": None,
            "window_days_used": None,
            "attribution_result": None,
        }

        # Step 1: exact match after normalization
        if norm_a == norm_b:
            entry_base.update({"match_result": True, "match_method": "exact"})
            return True, self.audit_logger.append(entry_base)

        # Step 2: abbreviation expansion produced identical canonical forms
        exp_a = self.expand_abbreviations(name_a.lower())
        exp_b = self.expand_abbreviations(name_b.lower())
        if exp_a == exp_b and exp_a != name_a.lower():
            entry_base.update({
                "match_result": True,
                "match_method": "abbrev",
                "abbreviation_hit": True,
                "jaro_winkler_score": 1.0,
            })
            return True, self.audit_logger.append(entry_base)

        # Step 3 + 4: Jaro-Winkler (jellyfish C-impl, falls back to difflib)
        try:
            import jellyfish
            score = jellyfish.jaro_winkler_similarity(norm_a, norm_b)
        except ImportError:
            from difflib import SequenceMatcher
            score = SequenceMatcher(None, norm_a, norm_b).ratio()
            logger.warning("jellyfish unavailable -- using SequenceMatcher fallback.")

        entry_base["jaro_winkler_score"] = round(score, 6)

        if score >= _JW_MATCH_THRESHOLD:
            entry_base.update({"match_result": True, "match_method": "jaro"})
            return True, self.audit_logger.append(entry_base)

        if score >= _JW_GREY_ZONE_LOW and self.client is not None:
            match, confidence, reason = self._disambiguate_via_llm(name_a, name_b, score)
            entry_base.update({
                "match_result": match,
                "match_method": "llm",
                "llm_confidence": confidence,
                "llm_reason": reason,
            })
            return match, self.audit_logger.append(entry_base)

        # Step 5: no match
        entry_base.update({"match_result": False, "match_method": "no-match"})
        return False, self.audit_logger.append(entry_base)

    # ── Time-window attribution ───────────────────────────────────────────────

    @staticmethod
    def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
        """Parse a date string in multiple formats, return UTC midnight datetime."""
        if not date_str:
            return None
        formats = [
            "%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%d/%m/%Y",
            "%B %d, %Y", "%b %d, %Y", "%Y/%m/%d",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                return dt.replace(
                    hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
                )
            except ValueError:
                continue
        logger.debug("Could not parse date: %s", date_str)
        return None

    def is_inquiry_within_window(
        self,
        inquiry_date: Optional[str],
        account_opened: Optional[str],
        window_days: int = _PRIMARY_WINDOW_DAYS,
    ) -> tuple[bool, Optional[int]]:
        """Check if an inquiry falls within the attribution window of an account.

        The inquiry must precede or coincide with the account opening.

        Returns:
            (within_window: bool, days_delta: Optional[int])
        """
        inq_dt = self._parse_date(inquiry_date)
        open_dt = self._parse_date(account_opened)

        if inq_dt is None or open_dt is None:
            return False, None

        if inq_dt > open_dt:
            return False, (inq_dt - open_dt).days * -1

        delta = (open_dt - inq_dt).days
        return delta <= window_days, delta

    def _log_attribution(
        self,
        inquiry: HardInquiry,
        account: CreditAccount,
        within_primary: bool,
        within_extended: bool,
        days_delta: Optional[int],
        correlation_id: str,
    ) -> FilterAuditEntry:
        """Write a time-window attribution audit entry."""
        attribution = within_primary or within_extended
        window_used = (
            _PRIMARY_WINDOW_DAYS if within_primary
            else (_EXTENDED_WINDOW_DAYS if within_extended else None)
        )
        return self.audit_logger.append({
            "entry_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "correlation_id": correlation_id,
            "creditor_a": inquiry.creditor_name,
            "creditor_b": account.account_name,
            "normalized_a": self.normalize_creditor_name(inquiry.creditor_name),
            "normalized_b": self.normalize_creditor_name(account.account_name),
            "abbreviation_hit": False,
            "jaro_winkler_score": None,
            "match_result": True,
            "match_method": "jaro",
            "llm_confidence": None,
            "llm_reason": None,
            "inquiry_date": inquiry.inquiry_date,
            "account_opened": account.date_opened,
            "days_delta": days_delta,
            "window_days_used": window_used,
            "attribution_result": attribution,
        })

    # ── Core evaluation logic ─────────────────────────────────────────────────

    @staticmethod
    def _get_negative_marks(
        payment_history: list[PaymentHistory],
    ) -> list[PaymentHistory]:
        return [p for p in payment_history if p.status in NEGATIVE_STATUSES]

    @staticmethod
    def _build_reason(negative_marks: list[PaymentHistory]) -> str:
        parts = [
            f"{mark.status.value} ({calendar.month_abbr[mark.month]} {mark.year})"
            for mark in negative_marks
        ]
        count = len(negative_marks)
        label = "late payment" if count == 1 else "late payments"
        return f"{count} {label}: {', '.join(parts)}"

    def find_negative_accounts(
        self, accounts: list[CreditAccount]
    ) -> list[NegativeItem]:
        """Identify all accounts with any negative payment history."""
        negatives: list[NegativeItem] = []
        for account in accounts:
            bad_marks = self._get_negative_marks(account.payment_history)
            if bad_marks:
                reason = self._build_reason(bad_marks)
                negatives.append(
                    NegativeItem(
                        account=account,
                        negative_marks=bad_marks,
                        reason=reason,
                    )
                )
        logger.info(
            "Found %d negative account(s) out of %d total.",
            len(negatives),
            len(accounts),
        )
        return negatives

    def find_qualifying_inquiries(
        self,
        inquiries: list[HardInquiry],
        accounts: list[CreditAccount],
    ) -> list[QualifyingInquiry]:
        """Qualify hard inquiries for dispute.

        An inquiry is NOT disputable if:
          - Its creditor name matches an open positive account, AND
          - It falls within the 30-day primary OR 60-day extended window.

        All other inquiries qualify.
        """
        positive_open = [a for a in accounts if a.is_open and a.is_positive]
        qualifying: list[QualifyingInquiry] = []

        for inquiry in inquiries:
            correlation_id = str(uuid.uuid4())
            attributed = False

            for account in positive_open:
                is_match, _audit = self._names_match_with_audit(
                    inquiry.creditor_name, account.account_name, correlation_id
                )
                if not is_match:
                    continue

                within_primary, days_delta = self.is_inquiry_within_window(
                    inquiry.inquiry_date,
                    account.date_opened,
                    window_days=_PRIMARY_WINDOW_DAYS,
                )
                within_extended = False
                if not within_primary:
                    within_extended, days_delta = self.is_inquiry_within_window(
                        inquiry.inquiry_date,
                        account.date_opened,
                        window_days=_EXTENDED_WINDOW_DAYS,
                    )

                self._log_attribution(
                    inquiry, account, within_primary, within_extended,
                    days_delta, correlation_id,
                )

                if within_primary or within_extended:
                    attributed = True
                    break

            if not attributed:
                if self.client is not None:
                    reason = self._generate_dispute_reason(inquiry, positive_open)
                else:
                    reason = (
                        "No matching open positive account found under FCRA Section 604."
                    )
                qualifying.append(QualifyingInquiry(inquiry=inquiry, reason=reason))

        logger.info(
            "Qualified %d of %d hard inquiries for dispute.",
            len(qualifying),
            len(inquiries),
        )
        return qualifying

    # ── Public records evaluation ─────────────────────────────────────────

    _FCRA_SECTION_MAP: dict[PublicRecordType, str] = {
        PublicRecordType.BANKRUPTCY: "§1681c(a)(1)",
        PublicRecordType.JUDGMENT:   "§1681c(a)(2)",
        PublicRecordType.LIEN:       "§1681c(a)(3)",
    }

    def find_disputable_public_records(
        self, records: list[PublicRecord]
    ) -> list[DisputePublicRecord]:
        """Evaluate public records for disputability.

        Every present record qualifies for an accuracy dispute under
        FCRA §1681i. Records that have exceeded their FCRA §1681c
        retention window additionally qualify for mandatory deletion.

        Args:
            records: All public records extracted from one bureau.

        Returns:
            List of DisputePublicRecord items with FCRA-grounded reasons.
        """
        if not records:
            return []

        disputable: list[DisputePublicRecord] = []

        for record in records:
            section_ref = self._FCRA_SECTION_MAP.get(
                record.record_type, "§1681c"
            )
            limit_years = record.reporting_limit_years

            # Check retention window
            filing_dt = self._parse_date(record.filing_date)
            now = datetime.now(timezone.utc)
            years_on_file = None
            retention_expired = False
            if filing_dt:
                years_on_file = (now - filing_dt).days / 365.25
                if years_on_file >= limit_years:
                    retention_expired = True

            if retention_expired and years_on_file is not None:
                reason = (
                    f"This {record.record_type.value.lower()} has been on file "
                    f"for approximately {years_on_file:.1f} years, exceeding the "
                    f"FCRA {section_ref} maximum reporting period of "
                    f"{limit_years} years. This record must be deleted "
                    f"immediately pursuant to 15 U.S.C. {section_ref}."
                )
            else:
                reason = (
                    f"The consumer disputes the accuracy of this "
                    f"{record.record_type.value.lower()} under FCRA §1681i "
                    f"and requests a reinvestigation. The bureau must verify "
                    f"the accuracy of all reported details including filing "
                    f"date, status, and amount with the original source "
                    f"within 30 days or delete the entry."
                )

            disputable.append(
                DisputePublicRecord(record=record, reason=reason)
            )

        logger.info(
            "Found %d disputable public record(s) out of %d total.",
            len(disputable),
            len(records),
        )
        return disputable

    def run(
        self, extraction_results: list[ExtractionResult]
    ) -> dict[str, EvaluationResult]:
        """Evaluate all bureau extractions and return filtered dispute items."""
        results: dict[str, EvaluationResult] = {}

        for extraction in extraction_results:
            bureau = extraction.bureau_source
            logger.info("Evaluating %s ...", bureau)

            negative_accounts = self.find_negative_accounts(extraction.accounts)
            qualifying_inquiries = self.find_qualifying_inquiries(
                extraction.hard_inquiries, extraction.accounts
            )
            disputable_public_records = self.find_disputable_public_records(
                extraction.public_records
            )

            results[bureau] = EvaluationResult(
                negative_accounts=negative_accounts,
                qualifying_inquiries=qualifying_inquiries,
                disputable_public_records=disputable_public_records,
            )

        logger.info(
            "Evaluation complete. Audit log: %s",
            self.audit_logger._log_path or "(no decisions logged)",
        )
        return results
