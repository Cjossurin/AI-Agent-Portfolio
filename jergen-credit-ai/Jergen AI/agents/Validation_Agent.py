"""
Validation Agent — *The Guardrail*

Pipeline position: 3 of 4

Input:
  - dict[str, EvaluationResult]  — from Evaluation Agent
  - list[ExtractionResult]       — from Extraction Agent (raw reference)

Output: dict[str, ValidationResult]  — verified dispute list per bureau

Validation stack (layered: hard stops first, soft checks second):

  LAYER 1 — Hard assertions (raise ValidationError → halt pipeline):
    1. assert_not_positive       — 100% positive accounts must never be disputed
    2. assert_has_negative_marks — negative_marks list must not be empty
    3. assert_dispute_goal       — reason must target payment history removal
    4. cross_reference_extraction — account must exist in raw extraction data

  LAYER 2 — Soft checks (log warnings, never halt):
    5. check_frivolous           — FCRA §611: substantially similar cross-bureau
    6. check_irrelevant          — reason must allege a factual inaccuracy
    7. check_positive_tradeline_risk — LLM risk assessment for aged open accounts

Every check is recorded in a ValidationCheckRecord provenance trail.
LLM-backed checks require an Anthropic client (optional — skipped if absent).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Optional

import config
from prompt_templates import (
    JERGEN_FRIVOLOUS_REVIEW_PROMPT,
    JERGEN_IRRELEVANT_REVIEW_PROMPT,
    JERGEN_RISK_ASSESSMENT_PROMPT,
)
from models.schemas import (
    CreditAccount,
    DisputePublicRecord,
    DisputeRiskLevel,
    EvaluationResult,
    ExtractionResult,
    NegativeItem,
    PublicRecord,
    QualifyingInquiry,
    ValidationCheckRecord,
    ValidationResult,
    NEGATIVE_STATUSES,
)
from utils.rag_store import query as rag_query

logger = logging.getLogger(__name__)


# ── Exception Hierarchy ──────────────────────────────────────────────────────

class ValidationError(Exception):
    """Hard stop — pipeline must not proceed to drafting when raised.

    Attributes:
        account_name: The offending account that triggered the error.
        bureau: Bureau under which the account was found.
        detail: Human-readable explanation of the failure.
    """

    def __init__(self, account_name: str, bureau: str, detail: str) -> None:
        self.account_name = account_name
        self.bureau = bureau
        self.detail = detail
        super().__init__(
            f"VALIDATION FAILED [{bureau}] — Account '{account_name}': {detail}"
        )


class FrivolousDisputeWarning(Exception):
    """Soft warning: dispute may be substantially similar to another in this run.

    Under FCRA §611 a CRA may terminate reinvestigation for disputes that are
    'substantially similar' to a previously investigated dispute. This warning
    flags cross-bureau duplicates within the current pipeline run. Non-fatal.
    """

    def __init__(self, account_name: str, bureau: str, similar_bureau: str, detail: str) -> None:
        self.account_name = account_name
        self.bureau = bureau
        self.similar_bureau = similar_bureau
        self.detail = detail
        super().__init__(f"FRIVOLOUS_WARNING [{bureau}] '{account_name}': {detail}")


class IrrelevantDisputeWarning(Exception):
    """Soft warning: dispute reason may not allege a factual inaccuracy.

    FCRA §611 allows CRAs to dismiss disputes that are 'irrelevant' — i.e., they
    do not concern the accuracy or completeness of reported information. Non-fatal.
    """

    def __init__(self, account_name: str, bureau: str, detail: str) -> None:
        self.account_name = account_name
        self.bureau = bureau
        self.detail = detail
        super().__init__(f"IRRELEVANT_WARNING [{bureau}] '{account_name}': {detail}")


class PositiveTradelineRiskWarning(Exception):
    """Soft warning: disputing this account carries a credit-score drop risk.

    Accounts with long positive histories contribute to 'age of credit history'
    and credit-mix in FICO/VantageScore. Disputing them risks account deletion
    and loss of score benefit. Non-fatal — records concern in provenance trail.
    """

    def __init__(self, account_name: str, bureau: str, risk_level: str, detail: str) -> None:
        self.account_name = account_name
        self.bureau = bureau
        self.risk_level = risk_level
        self.detail = detail
        super().__init__(f"TRADELINE_RISK [{bureau}] '{account_name}': {detail}")


class ValidationAgent:
    """Multi-layer QA guardrail with deterministic hard-stops and LLM soft-checks.

    Layer 1 — Hard assertions (raise ValidationError, halt pipeline):
      - assert_not_positive: 100% positive accounts must never be disputed
      - assert_has_negative_marks: dispute list must have specific negatives
      - assert_dispute_goal: reason must target payment history removal
      - cross_reference_extraction: account must exist in raw extraction

    Layer 2 — Soft checks (warnings, non-fatal, logged to provenance):
      - check_frivolous: FCRA §611 substantially-similar cross-bureau detection
      - check_irrelevant: reason must allege a factual inaccuracy
      - check_positive_tradeline_risk: LLM credit-score risk assessment

    All checks are recorded as ValidationCheckRecord provenance entries.
    LLM-backed checks require an Anthropic client (skipped when absent).
    """

    # ── Metaprompt-style prompt 1: Frivolous Dispute Review ───────────────────
        _FRIVOLOUS_REVIEW_PROMPT = JERGEN_FRIVOLOUS_REVIEW_PROMPT

    # ── Metaprompt-style prompt 2: Irrelevant Dispute Review ──────────────────
        _IRRELEVANT_REVIEW_PROMPT = JERGEN_IRRELEVANT_REVIEW_PROMPT

    # ── Metaprompt-style prompt 3: Positive Tradeline Risk Assessment ─────────
        _RISK_ASSESSMENT_PROMPT = JERGEN_RISK_ASSESSMENT_PROMPT

    # ──────────────────────────────────────────────────────────────────────────

    def __init__(
        self,
        anthropic_client=None,
        guardrail_rag_collection=None,
    ) -> None:
        """
        Args:
            anthropic_client: Optional Anthropic client. When provided, LLM-backed
                soft checks (frivolous, irrelevant, risk assessment) are enabled.
            guardrail_rag_collection: Optional ChromaDB collection for Guardrail RAG
                context injected into every LLM prompt.
        """
        self.client = anthropic_client
        self.guardrail_rag_collection = guardrail_rag_collection

    # ── RAG helper ────────────────────────────────────────────────────────────

    def _get_guardrail_context(self, query_text: str) -> str:
        """Retrieve relevant Guardrail RAG chunks for a query."""
        if self.guardrail_rag_collection is None:
            return "(No Guardrail RAG context available.)"
        try:
            chunks = rag_query(
                self.guardrail_rag_collection,
                query_text,
                n_results=config.RAG_TOP_K,
            )
            if not chunks:
                return "(No relevant Guardrail RAG context found.)"
            return "\n\n---\n\n".join(chunks)
        except Exception as exc:
            logger.warning("Guardrail RAG query failed: %s", exc)
            return "(Guardrail RAG query error.)"

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
        """Extract JSON from <answer> tags (3-tier fallback)."""
        import json as _json
        m = re.search(r"<answer>\s*([\s\S]*?)\s*</answer>", response_text, re.IGNORECASE)
        if m:
            try:
                return _json.loads(m.group(1).strip())
            except _json.JSONDecodeError:
                pass
        try:
            return _json.loads(response_text)
        except _json.JSONDecodeError:
            pass
        m2 = re.search(r"\{[\s\S]*\}", response_text)
        if m2:
            try:
                return _json.loads(m2.group())
            except _json.JSONDecodeError:
                pass
        raise ValueError(f"Could not extract JSON: {response_text[:300]}")

    # ── Provenance helper ─────────────────────────────────────────────────────

    @staticmethod
    def _record(
        check_name: str,
        account_name: str,
        bureau: str,
        passed: bool,
        detail: str = "",
        risk_level: DisputeRiskLevel = DisputeRiskLevel.SAFE,
        llm_assisted: bool = False,
        llm_confidence: Optional[str] = None,
    ) -> ValidationCheckRecord:
        """Create a ValidationCheckRecord for the audit trail."""
        return ValidationCheckRecord(
            check_name=check_name,
            account_name=account_name,
            bureau=bureau,
            passed=passed,
            risk_level=risk_level,
            detail=detail,
            llm_assisted=llm_assisted,
            llm_confidence=llm_confidence,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    # ── Soft checks (Layer 2) ─────────────────────────────────────────────────

    def check_frivolous(
        self,
        item: NegativeItem,
        bureau: str,
        all_verified_negatives: dict[str, list[NegativeItem]],
    ) -> ValidationCheckRecord:
        """FCRA §611 substantially-similar cross-bureau duplicate detection.

        Compares this item against all already-verified negatives from other
        bureaus in the current pipeline run. Uses SequenceMatcher for fast
        pre-screening at 0.85 ratio, then optionally escalates to LLM.

        Returns:
            ValidationCheckRecord with passed=True if no duplication found.
        """
        check = "check_frivolous"
        for other_bureau, other_items in all_verified_negatives.items():
            if other_bureau == bureau:
                continue
            for other_item in other_items:
                # Quick name similarity pre-screen
                name_score = SequenceMatcher(
                    None,
                    item.account.account_name.lower(),
                    other_item.account.account_name.lower(),
                ).ratio()
                if name_score < 0.75:
                    continue

                # Reason similarity pre-screen
                reason_score = SequenceMatcher(
                    None,
                    item.reason.lower(),
                    other_item.reason.lower(),
                ).ratio()

                # High similarity → deterministic flag
                if name_score >= 0.90 and reason_score >= 0.80:
                    detail = (
                        f"Substantially similar to {other_bureau} dispute for "
                        f"'{other_item.account.account_name}' "
                        f"(name sim={name_score:.2f}, reason sim={reason_score:.2f}). "
                        f"FCRA §611 frivolous-designation risk."
                    )
                    return self._record(
                        check, item.account.account_name, bureau,
                        passed=False,
                        risk_level=DisputeRiskLevel.WARNING,
                        detail=detail,
                    )

                # Grey zone → LLM escalation
                if (name_score >= 0.75 or reason_score >= 0.65) and self.client is not None:
                    rag_ctx = self._get_guardrail_context(
                        "FCRA section 611 frivolous dispute substantially similar"
                    )
                    user_msg = (
                        self._FRIVOLOUS_REVIEW_PROMPT
                        .replace("{$ACCOUNT_A}", other_item.account.account_name)
                        .replace("{$BUREAU_A}", other_bureau)
                        .replace("{$REASON_A}", other_item.reason)
                        .replace("{$ACCOUNT_B}", item.account.account_name)
                        .replace("{$BUREAU_B}", bureau)
                        .replace("{$REASON_B}", item.reason)
                        .replace("{$GUARDRAIL_RAG_CONTEXT}", rag_ctx)
                    )
                    try:
                        raw = self._call_claude(
                            "You are an FCRA compliance specialist.", user_msg
                        )
                        result = self._extract_json_from_answer(raw)
                        if result.get("substantially_similar", False):
                            return self._record(
                                check, item.account.account_name, bureau,
                                passed=False,
                                risk_level=DisputeRiskLevel.WARNING,
                                detail=f"LLM: {result.get('reason', 'Substantially similar.')}",
                                llm_assisted=True,
                                llm_confidence=result.get("confidence"),
                            )
                    except Exception as exc:
                        logger.warning("Frivolous LLM check failed: %s", exc)

        return self._record(check, item.account.account_name, bureau, passed=True)

    def check_irrelevant(
        self, item: NegativeItem, bureau: str
    ) -> ValidationCheckRecord:
        """Check whether the dispute reason actually alleges a factual inaccuracy.

        Fast deterministic pre-check first; LLM escalation for ambiguous cases.

        Returns:
            ValidationCheckRecord with passed=True if reason appears relevant.
        """
        check = "check_irrelevant"
        reason_lower = item.reason.lower()

        # Deterministic fast-pass: standard payment-inaccuracy keywords
        factual_keywords = [
            "inaccurate", "incorrect", "not mine", "not my account",
            "never late", "paid on time", "wrong", "error", "dispute",
            "late payment", "charge", "collection", "derogatory",
            "late", "payment",
        ]
        if any(kw in reason_lower for kw in factual_keywords):
            return self._record(check, item.account.account_name, bureau, passed=True)

        # Irrelevant-signal keywords (non-factual complaints)
        irrelevant_signals = [
            "i disagree", "unfair", "hardship", "remove all", "goodwill",
            "financial difficulty", "i don't like", "please delete",
        ]
        deterministic_irrelevant = any(kw in reason_lower for kw in irrelevant_signals)

        if deterministic_irrelevant and self.client is None:
            detail = (
                f"Reason '{item.reason[:120]}' may not allege a factual inaccuracy "
                f"under FCRA §611. No LLM check available."
            )
            return self._record(
                check, item.account.account_name, bureau,
                passed=False,
                risk_level=DisputeRiskLevel.WARNING,
                detail=detail,
            )

        if self.client is not None:
            neg_summary = "; ".join(
                f"{m.status.value} {m.month}/{m.year}"
                for m in item.negative_marks[:5]
            )
            rag_ctx = self._get_guardrail_context(
                "FCRA section 611 irrelevant dispute factual inaccuracy requirement"
            )
            user_msg = (
                self._IRRELEVANT_REVIEW_PROMPT
                .replace("{$ACCOUNT_NAME}", item.account.account_name)
                .replace("{$BUREAU}", bureau)
                .replace("{$REASON_TEXT}", item.reason)
                .replace("{$NEGATIVE_MARKS_SUMMARY}", neg_summary)
                .replace("{$GUARDRAIL_RAG_CONTEXT}", rag_ctx)
            )
            try:
                raw = self._call_claude(
                    "You are an FCRA compliance attorney.", user_msg
                )
                result = self._extract_json_from_answer(raw)
                if not result.get("relevant", True):
                    return self._record(
                        check, item.account.account_name, bureau,
                        passed=False,
                        risk_level=DisputeRiskLevel.WARNING,
                        detail=f"LLM: {result.get('reason', 'May be irrelevant.')}",
                        llm_assisted=True,
                        llm_confidence=result.get("confidence"),
                    )
                return self._record(
                    check, item.account.account_name, bureau,
                    passed=True, llm_assisted=True,
                    llm_confidence=result.get("confidence"),
                )
            except Exception as exc:
                logger.warning("Irrelevant LLM check failed: %s", exc)

        return self._record(check, item.account.account_name, bureau, passed=True)

    def check_positive_tradeline_risk(
        self, item: NegativeItem, bureau: str
    ) -> ValidationCheckRecord:
        """Assess credit-score risk of disputing an account with mixed history.

        Uses LLM when available; falls back to a heuristic based on
        positive-month ratio and account age.

        Returns:
            ValidationCheckRecord with risk_level=SAFE/WARNING/HIGH_RISK.
        """
        check = "check_positive_tradeline_risk"
        account = item.account

        total_months = len(account.payment_history)
        positive_months = sum(
            1 for p in account.payment_history
            if p.status.value == "OK"
        )
        negative_months = len(item.negative_marks)

        # Heuristic: if >80% positive and account is open, flag for review
        positive_ratio = positive_months / total_months if total_months > 0 else 0.0
        is_old_account = False
        if account.date_opened:
            try:
                from datetime import date as _date
                opened_parts = account.date_opened.replace("-", "/").split("/")
                year = int(opened_parts[-1]) if len(opened_parts[-1]) == 4 else int(opened_parts[0])
                age_years = (_date.today().year - year)
                is_old_account = age_years >= 5
            except Exception:
                pass

        if self.client is None:
            # Pure heuristic fallback
            if positive_ratio >= 0.85 and is_old_account and account.is_open:
                return self._record(
                    check, account.account_name, bureau,
                    passed=True,
                    risk_level=DisputeRiskLevel.HIGH_RISK,
                    detail=(
                        f"Account is open, >{int(positive_ratio*100)}% positive history, "
                        f"and appears old (>=5 years). Disputing risks account deletion "
                        f"and credit-age score impact."
                    ),
                )
            if positive_ratio >= 0.70 and account.is_open:
                return self._record(
                    check, account.account_name, bureau,
                    passed=True,
                    risk_level=DisputeRiskLevel.WARNING,
                    detail=(
                        f"Account is open with {int(positive_ratio*100)}% positive payment "
                        f"history. Deletion risk is moderate."
                    ),
                )
            return self._record(check, account.account_name, bureau, passed=True)

        # LLM-backed assessment
        neg_detail = "; ".join(
            f"{m.status.value} {m.month}/{m.year}"
            for m in item.negative_marks[:8]
        )
        rag_ctx = self._get_guardrail_context(
            "positive tradeline credit score risk age of credit history FICO VantageScore"
        )
        user_msg = (
            self._RISK_ASSESSMENT_PROMPT
            .replace("{$ACCOUNT_NAME}", account.account_name)
            .replace("{$BUREAU}", bureau)
            .replace("{$ACCOUNT_TYPE}", account.account_type or "Unknown")
            .replace("{$DATE_OPENED}", account.date_opened or "Unknown")
            .replace("{$ACCOUNT_STATUS}", account.account_status or "Unknown")
            .replace("{$BALANCE}", str(account.balance or 0))
            .replace("{$TOTAL_MONTHS}", str(total_months))
            .replace("{$POSITIVE_MONTHS}", str(positive_months))
            .replace("{$NEGATIVE_MONTHS}", str(negative_months))
            .replace("{$NEGATIVE_MARKS}", neg_detail)
            .replace("{$GUARDRAIL_RAG_CONTEXT}", rag_ctx)
        )
        try:
            raw = self._call_claude(
                "You are a certified credit repair counselor.", user_msg
            )
            result = self._extract_json_from_answer(raw)
            raw_risk = result.get("risk_level", "SAFE").upper()
            risk_map = {
                "SAFE": DisputeRiskLevel.SAFE,
                "WARNING": DisputeRiskLevel.WARNING,
                "HIGH_RISK": DisputeRiskLevel.HIGH_RISK,
            }
            risk_level = risk_map.get(raw_risk, DisputeRiskLevel.SAFE)
            return self._record(
                check, account.account_name, bureau,
                passed=True,
                risk_level=risk_level,
                detail=f"LLM: {result.get('reason', '')}",
                llm_assisted=True,
                llm_confidence=result.get("confidence"),
            )
        except Exception as exc:
            logger.warning("Risk assessment LLM check failed: %s", exc)
            return self._record(check, account.account_name, bureau, passed=True)

    # ── Assertion helpers ────────────────────────────────────────────────

    @staticmethod
    def _assert_not_positive(
        item: NegativeItem, bureau: str
    ) -> None:
        """Verify that the flagged account genuinely has negative marks.

        Cross-checks the account's full payment history (not just the
        negative_marks list) to ensure it is not 100 % positive.

        Args:
            item: A negative item from the Evaluation Agent.
            bureau: Bureau label for error reporting.

        Raises:
            ValidationError: If the account has only OK payment statuses.
        """
        account = item.account
        if account.is_positive:
            raise ValidationError(
                account_name=account.account_name,
                bureau=bureau,
                detail=(
                    "Account has a 100% positive payment history but was "
                    "included in the dispute list. This is a false positive "
                    "and must not be disputed."
                ),
            )

    @staticmethod
    def _assert_has_negative_marks(
        item: NegativeItem, bureau: str
    ) -> None:
        """Verify that the item actually contains negative payment entries.

        Args:
            item: A negative item from the Evaluation Agent.
            bureau: Bureau label for error reporting.

        Raises:
            ValidationError: If negative_marks list is empty.
        """
        if not item.negative_marks:
            raise ValidationError(
                account_name=item.account.account_name,
                bureau=bureau,
                detail=(
                    "Negative item has an empty negative_marks list. "
                    "Cannot dispute an account without specific derogatory marks."
                ),
            )

    @staticmethod
    def _assert_dispute_goal(
        item: NegativeItem, bureau: str
    ) -> None:
        """Verify the dispute reason targets removal of late payment history.

        The reason string must reference late payments or derogatory marks.
        This prevents accidentally disputing account ownership, balances,
        or other non-payment issues.

        Args:
            item: A negative item from the Evaluation Agent.
            bureau: Bureau label for error reporting.

        Raises:
            ValidationError: If the reason does not target payment history.
        """
        reason_lower = item.reason.lower()
        payment_keywords = [
            "late",
            "payment",
            "delinquent",
            "derogatory",
            "collection",
            "charge_off",
            "charge-off",
            "missed",
        ]

        if not any(kw in reason_lower for kw in payment_keywords):
            raise ValidationError(
                account_name=item.account.account_name,
                bureau=bureau,
                detail=(
                    f"Dispute reason '{item.reason}' does not target removal "
                    f"of negative payment history. All disputes must focus on "
                    f"late / derogatory payment marks."
                ),
            )

    @staticmethod
    def _cross_reference_with_extraction(
        item: NegativeItem,
        raw_accounts: list[CreditAccount],
        bureau: str,
    ) -> list[str]:
        """Cross-reference a negative item against the raw extraction data.

        Ensures the account actually exists in the original extraction and
        that the negative marks in the evaluation match the source data.

        Args:
            item: Negative item to verify.
            raw_accounts: All accounts from the Extraction Agent for this bureau.
            bureau: Bureau label.

        Returns:
            List of warning notes (empty if everything matches perfectly).

        Raises:
            ValidationError: If the account cannot be found in raw data.
        """
        notes: list[str] = []

        # Find the matching raw account
        matching_raw = [
            acct
            for acct in raw_accounts
            if acct.account_name == item.account.account_name
        ]

        if not matching_raw:
            raise ValidationError(
                account_name=item.account.account_name,
                bureau=bureau,
                detail=(
                    "Account in dispute list was NOT found in the original "
                    "extraction data. Possible data corruption between agents."
                ),
            )

        raw_account = matching_raw[0]

        # Verify the raw account also shows negative marks
        raw_negative_months = {
            (p.month, p.year)
            for p in raw_account.payment_history
            if p.status in NEGATIVE_STATUSES
        }
        eval_negative_months = {
            (p.month, p.year) for p in item.negative_marks
        }

        if not raw_negative_months:
            raise ValidationError(
                account_name=item.account.account_name,
                bureau=bureau,
                detail=(
                    "Raw extraction data shows NO negative marks for this "
                    "account, but the evaluation flagged it. Data mismatch."
                ),
            )

        extra = eval_negative_months - raw_negative_months
        if extra:
            notes.append(
                f"Warning: {len(extra)} negative mark(s) in evaluation "
                f"not found in raw extraction for '{item.account.account_name}'."
            )

        return notes

    # ── Public record hard assertions ─────────────────────────────────────

    @staticmethod
    def _assert_public_record_exists(
        item: DisputePublicRecord,
        raw_records: list[PublicRecord],
        bureau: str,
    ) -> None:
        """Verify the disputed public record exists in raw extraction data.

        Raises:
            ValidationError: If the record is not found in raw data.
        """
        for raw in raw_records:
            if (
                raw.record_type == item.record.record_type
                and raw.bureau == item.record.bureau
                and (
                    (raw.case_number and raw.case_number == item.record.case_number)
                    or raw.description == item.record.description
                    or raw.filing_date == item.record.filing_date
                )
            ):
                return
        raise ValidationError(
            account_name=f"{item.record.record_type.value}: {item.record.description}",
            bureau=bureau,
            detail=(
                "Public record in dispute list was NOT found in the original "
                "extraction data. Possible data corruption between agents."
            ),
        )

    def check_frivolous_public_record(
        self,
        item: DisputePublicRecord,
        bureau: str,
        all_verified_public_records: dict[str, list[DisputePublicRecord]],
    ) -> ValidationCheckRecord:
        """Cross-bureau duplicate detection for public records.

        Flags if the same public record (by case number or description) is
        being disputed across multiple bureaus in the same run.
        """
        for other_bureau, other_records in all_verified_public_records.items():
            if other_bureau == bureau:
                continue
            for other in other_records:
                if (
                    other.record.record_type == item.record.record_type
                    and other.record.case_number
                    and other.record.case_number == item.record.case_number
                ):
                    return self._record(
                        "check_frivolous_public_record",
                        f"{item.record.record_type.value}: {item.record.description}",
                        bureau,
                        passed=False,
                        risk_level=DisputeRiskLevel.WARNING,
                        detail=(
                            f"Same public record (case #{item.record.case_number}) "
                            f"already disputed under {other_bureau}. Cross-bureau "
                            f"duplicates may trigger FCRA §611 frivolous designation."
                        ),
                    )

                desc_score = SequenceMatcher(
                    None,
                    (item.record.description or "").lower(),
                    (other.record.description or "").lower(),
                ).ratio()
                if desc_score >= 0.85 and item.record.record_type == other.record.record_type:
                    return self._record(
                        "check_frivolous_public_record",
                        f"{item.record.record_type.value}: {item.record.description}",
                        bureau,
                        passed=False,
                        risk_level=DisputeRiskLevel.WARNING,
                        detail=(
                            f"Highly similar public record already disputed under "
                            f"{other_bureau} (similarity={desc_score:.2f}). "
                            f"May trigger FCRA §611 frivolous designation."
                        ),
                    )

        return self._record(
            "check_frivolous_public_record",
            f"{item.record.record_type.value}: {item.record.description}",
            bureau,
            passed=True,
        )

    # ── Main validation method ───────────────────────────────────────────

    def validate(
        self,
        evaluation: dict[str, EvaluationResult],
        extractions: list[ExtractionResult],
    ) -> dict[str, ValidationResult]:
        """Run all validation checks (hard assertions + LLM soft checks).

        Layer 1 — Hard assertions halt the pipeline on failure (ValidationError).
        Layer 2 — Soft checks (frivolous, irrelevant, positive-tradeline risk)
        collect warnings and provenance records without halting.

        Args:
            evaluation: Evaluation Agent's output, keyed by bureau.
            extractions: Raw Extraction Agent output (for cross-reference).

        Returns:
            Dict mapping ``bureau → ValidationResult`` with verified items,
            warnings, and provenance audit records.

        Raises:
            ValidationError: Hard assertion failure — halts the pipeline.
        """
        extraction_by_bureau: dict[str, ExtractionResult] = {
            e.bureau_source: e for e in extractions
        }

        # Build cross-bureau index for frivolous-check comparisons
        all_negatives_by_bureau: dict[str, list[NegativeItem]] = {
            bureau: list(er.negative_accounts)
            for bureau, er in evaluation.items()
        }

        validated: dict[str, ValidationResult] = {}

        for bureau, eval_result in evaluation.items():
            logger.info("Validating %s dispute list …", bureau)
            all_notes: list[str] = []
            all_warnings: list[str] = []
            all_prov: list[ValidationCheckRecord] = []

            raw_extraction = extraction_by_bureau.get(bureau)
            raw_accounts = raw_extraction.accounts if raw_extraction else []

            # ── Layer 1: Hard assertion checks ──────────────────────────────
            verified_negatives: list[NegativeItem] = []

            for item in eval_result.negative_accounts:
                acct = item.account.account_name

                # Assertion 1: NOT a purely positive account
                self._assert_not_positive(item, bureau)
                all_prov.append(
                    self._record("assert_not_positive", acct, bureau, passed=True)
                )

                # Assertion 2: Has actual negative marks
                self._assert_has_negative_marks(item, bureau)
                all_prov.append(
                    self._record("assert_has_negative_marks", acct, bureau, passed=True)
                )

                # Assertion 3: Dispute reason targets payment history
                self._assert_dispute_goal(item, bureau)
                all_prov.append(
                    self._record("assert_dispute_goal", acct, bureau, passed=True)
                )

                # Assertion 4: Cross-reference with raw extraction
                if raw_accounts:
                    notes = self._cross_reference_with_extraction(
                        item, raw_accounts, bureau
                    )
                    all_notes.extend(notes)
                    all_prov.append(
                        self._record(
                            "cross_reference_extraction", acct, bureau,
                            passed=True,
                            detail=" | ".join(notes) if notes else "Matched.",
                        )
                    )

                verified_negatives.append(item)
                logger.debug("  ✓ '%s' passed hard assertions.", acct)

            # ── Layer 2: Soft checks (non-fatal) ────────────────────────────
            other_bureaus_negatives = {
                k: v for k, v in all_negatives_by_bureau.items() if k != bureau
            }

            for item in verified_negatives:
                acct = item.account.account_name

                # Soft check 1: FCRA §611 frivolous detection
                try:
                    friv_rec = self.check_frivolous(item, bureau, other_bureaus_negatives)
                    all_prov.append(friv_rec)
                    if not friv_rec.passed:
                        msg = f"[FRIVOLOUS RISK] {acct} ({bureau}): {friv_rec.detail}"
                        all_warnings.append(msg)
                        logger.warning("  ⚠ %s", msg)
                except Exception as exc:
                    logger.warning("check_frivolous error for '%s': %s", acct, exc)

                # Soft check 2: Irrelevant dispute reason
                try:
                    irr_rec = self.check_irrelevant(item, bureau)
                    all_prov.append(irr_rec)
                    if not irr_rec.passed:
                        msg = f"[IRRELEVANT RISK] {acct} ({bureau}): {irr_rec.detail}"
                        all_warnings.append(msg)
                        logger.warning("  ⚠ %s", msg)
                except Exception as exc:
                    logger.warning("check_irrelevant error for '%s': %s", acct, exc)

                # Soft check 3: Positive tradeline credit-score risk
                try:
                    risk_rec = self.check_positive_tradeline_risk(item, bureau)
                    all_prov.append(risk_rec)
                    if risk_rec.risk_level in (
                        DisputeRiskLevel.WARNING, DisputeRiskLevel.HIGH_RISK
                    ):
                        msg = (
                            f"[TRADELINE RISK:{risk_rec.risk_level.value}] "
                            f"{acct} ({bureau}): {risk_rec.detail}"
                        )
                        all_warnings.append(msg)
                        logger.warning("  ⚠ %s", msg)
                except Exception as exc:
                    logger.warning(
                        "check_positive_tradeline_risk error for '%s': %s", acct, exc
                    )

            # ── Pass through qualifying inquiries ────────────────────────────
            verified_inquiries: list[QualifyingInquiry] = list(
                eval_result.qualifying_inquiries
            )

            # ── Public records: hard assertion + soft checks ─────────────────
            verified_public_records: list[DisputePublicRecord] = []
            raw_public_records = (
                raw_extraction.public_records if raw_extraction else []
            )

            # Build cross-bureau index for frivolous public record checks
            all_pub_records_by_bureau: dict[str, list[DisputePublicRecord]] = {
                b: list(er.disputable_public_records)
                for b, er in evaluation.items()
                if b != bureau
            }

            for pr_item in eval_result.disputable_public_records:
                pr_label = (
                    f"{pr_item.record.record_type.value}: "
                    f"{pr_item.record.description}"
                )

                # Hard assertion: exists in raw extraction
                if raw_public_records:
                    self._assert_public_record_exists(
                        pr_item, raw_public_records, bureau
                    )
                    all_prov.append(
                        self._record(
                            "assert_public_record_exists", pr_label, bureau,
                            passed=True,
                        )
                    )

                verified_public_records.append(pr_item)
                logger.debug("  ✓ '%s' passed hard assertions.", pr_label)

                # Soft check: frivolous cross-bureau duplicate
                try:
                    friv_rec = self.check_frivolous_public_record(
                        pr_item, bureau, all_pub_records_by_bureau
                    )
                    all_prov.append(friv_rec)
                    if not friv_rec.passed:
                        msg = f"[FRIVOLOUS PR RISK] {pr_label} ({bureau}): {friv_rec.detail}"
                        all_warnings.append(msg)
                        logger.warning("  ⚠ %s", msg)
                except Exception as exc:
                    logger.warning(
                        "check_frivolous_public_record error for '%s': %s",
                        pr_label, exc,
                    )

            validated[bureau] = ValidationResult(
                verified_negatives=verified_negatives,
                verified_inquiries=verified_inquiries,
                verified_public_records=verified_public_records,
                validation_passed=True,
                notes=all_notes,
                warnings=all_warnings,
                provenance=all_prov,
            )

            logger.info(
                "%s PASSED: %d negatives, %d inquiries, %d public records, "
                "%d warnings, %d provenance records.",
                bureau,
                len(verified_negatives),
                len(verified_inquiries),
                len(verified_public_records),
                len(all_warnings),
                len(all_prov),
            )

        return validated
