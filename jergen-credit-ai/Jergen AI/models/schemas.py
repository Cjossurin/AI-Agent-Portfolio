"""
Pydantic data models for every stage of the credit dispute pipeline.

These schemas define the data contracts passed between agents:
  Extraction  →  Evaluation  →  Validation  →  Drafting
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel, Field, computed_field


# ── Enums ────────────────────────────────────────────────────────────────────

class PaymentStatus(str, Enum):
    """Possible statuses for a single month of payment history."""
    OK = "OK"
    LATE_30 = "LATE_30"
    LATE_60 = "LATE_60"
    LATE_90 = "LATE_90"
    LATE_120 = "LATE_120"
    COLLECTION = "COLLECTION"
    CHARGE_OFF = "CHARGE_OFF"
    UNKNOWN = "UNKNOWN"


NEGATIVE_STATUSES: set[PaymentStatus] = {
    PaymentStatus.LATE_30,
    PaymentStatus.LATE_60,
    PaymentStatus.LATE_90,
    PaymentStatus.LATE_120,
    PaymentStatus.COLLECTION,
    PaymentStatus.CHARGE_OFF,
}


class PublicRecordType(str, Enum):
    """Types of public records found on credit reports."""
    BANKRUPTCY = "BANKRUPTCY"
    JUDGMENT = "JUDGMENT"
    LIEN = "LIEN"


# ── Personal Information ─────────────────────────────────────────────────────

class PersonalInfo(BaseModel):
    """Consumer's personal information extracted from a credit report."""

    full_name: str = Field(..., description="Consumer's full legal name")
    current_address: str = Field(..., description="Current mailing address")
    email: Optional[str] = Field(None, description="Email address if listed")
    phone: Optional[str] = Field(None, description="Phone number if listed")
    ssn_last4: Optional[str] = Field(
        None,
        description="Last 4 digits of SSN",
        min_length=4,
        max_length=4,
    )
    date_of_birth: Optional[str] = Field(
        None, description="Date of birth (MM/DD/YYYY)"
    )


# ── Payment History ──────────────────────────────────────────────────────────

class PaymentHistory(BaseModel):
    """A single month's payment record on an account."""

    month: int = Field(..., ge=1, le=12, description="Calendar month (1-12)")
    year: int = Field(..., ge=1970, description="Calendar year")
    status: PaymentStatus = Field(..., description="Payment status for the month")


# ── Credit Account ───────────────────────────────────────────────────────────

class CreditAccount(BaseModel):
    """A single trade-line / credit account as reported by a bureau."""

    account_name: str = Field(..., description="Creditor / account name")
    account_number_partial: Optional[str] = Field(
        None, description="Partial or masked account number"
    )
    bureau: str = Field(..., description="Reporting bureau (Experian, Equifax, TransUnion)")
    account_type: Optional[str] = Field(
        None, description="e.g. Revolving, Installment, Mortgage"
    )
    account_status: Optional[str] = Field(
        None, description="e.g. Open, Closed, Paid"
    )
    balance: Optional[float] = Field(None, description="Current balance in dollars")
    credit_limit: Optional[float] = Field(None, description="Credit limit in dollars")
    date_opened: Optional[str] = Field(None, description="Date the account was opened")
    date_closed: Optional[str] = Field(None, description="Date the account was closed, if applicable")
    payment_history: list[PaymentHistory] = Field(
        default_factory=list,
        description="Monthly payment history records",
    )

    @computed_field
    @property
    def is_positive(self) -> bool:
        """True if every recorded payment is OK (no negative marks)."""
        if not self.payment_history:
            return True
        return all(p.status == PaymentStatus.OK for p in self.payment_history)

    @computed_field
    @property
    def is_open(self) -> bool:
        """True if the account appears to be currently open."""
        if self.account_status:
            return self.account_status.lower() in ("open", "current", "active")
        return self.date_closed is None


# ── Hard Inquiry ─────────────────────────────────────────────────────────────

class HardInquiry(BaseModel):
    """A single hard inquiry recorded on the credit report."""

    creditor_name: str = Field(..., description="Name of the creditor that pulled credit")
    inquiry_date: Optional[str] = Field(None, description="Date of the inquiry")
    bureau: str = Field(..., description="Bureau reporting the inquiry")


# ── Public Record ────────────────────────────────────────────────────────────

_RESOLVED_STATUSES: set[str] = {
    "discharged", "satisfied", "released", "paid", "dismissed", "vacated",
}


class PublicRecord(BaseModel):
    """A single public record (bankruptcy, judgment, or lien) on a credit report."""

    record_type: PublicRecordType = Field(..., description="BANKRUPTCY, JUDGMENT, or LIEN")
    description: str = Field("", description="e.g. 'Chapter 7 Bankruptcy', 'Federal Tax Lien'")
    case_number: Optional[str] = Field(None, description="Court case or filing number")
    filing_date: Optional[str] = Field(None, description="Date filed (MM/DD/YYYY or YYYY-MM-DD)")
    court_or_agency: Optional[str] = Field(None, description="Court name or filing agency")
    amount: Optional[float] = Field(None, description="Dollar amount if reported")
    status: Optional[str] = Field(None, description="e.g. Discharged, Satisfied, Released, Filed")
    date_resolved: Optional[str] = Field(None, description="Date discharged/satisfied/released")
    bureau: str = Field(..., description="Reporting bureau")

    @computed_field
    @property
    def is_resolved(self) -> bool:
        """True if the record has been discharged, satisfied, released, etc."""
        if self.status:
            return self.status.strip().lower() in _RESOLVED_STATUSES
        return self.date_resolved is not None

    @computed_field
    @property
    def reporting_limit_years(self) -> int:
        """FCRA §1681c maximum reporting period in years.

        - Chapter 7/11 bankruptcy: 10 years
        - Chapter 13 bankruptcy:    7 years
        - Judgments:                 7 years
        - Tax liens (paid):          7 years
        - Tax liens (unpaid):       10 years (some bureaus voluntarily removed)
        """
        if self.record_type == PublicRecordType.BANKRUPTCY:
            desc_lower = self.description.lower() if self.description else ""
            if "13" in desc_lower:
                return 7
            return 10  # Ch 7, Ch 11, or unspecified
        if self.record_type == PublicRecordType.JUDGMENT:
            return 7
        # LIEN
        if self.is_resolved:
            return 7
        return 10


# ── Extraction Agent Output ──────────────────────────────────────────────────

class ExtractionResult(BaseModel):
    """Complete structured output from the DataExtraction Agent for one bureau."""

    personal_info: PersonalInfo
    accounts: list[CreditAccount] = Field(default_factory=list)
    hard_inquiries: list[HardInquiry] = Field(default_factory=list)
    public_records: list[PublicRecord] = Field(default_factory=list)
    bureau_source: str = Field(..., description="Which bureau this data came from")
    raw_text: str = Field("", description="Original extracted text for auditing")


# ── Evaluation Agent Output ──────────────────────────────────────────────────

class NegativeItem(BaseModel):
    """An account flagged as having negative payment history."""

    account: CreditAccount
    negative_marks: list[PaymentHistory] = Field(
        ..., description="The specific months with late / derogatory marks"
    )
    reason: str = Field(
        ...,
        description="Human-readable explanation (e.g. '2 late payments: 30-day Aug 2024, 60-day Sep 2024')",
    )


class QualifyingInquiry(BaseModel):
    """A hard inquiry that is NOT tied to any open, positive account."""

    inquiry: HardInquiry
    reason: str = Field(
        ...,
        description="Why this inquiry qualifies for dispute (e.g. 'No matching open positive account found')",
    )


class DisputePublicRecord(BaseModel):
    """A public record flagged for dispute (accuracy or retention window)."""

    record: PublicRecord
    reason: str = Field(
        ...,
        description="FCRA basis for dispute (e.g. '§1681c(a)(1) — bankruptcy exceeds 10-year reporting limit')",
    )


class EvaluationResult(BaseModel):
    """Filtered output from the Evaluation Agent for a single bureau."""

    negative_accounts: list[NegativeItem] = Field(default_factory=list)
    qualifying_inquiries: list[QualifyingInquiry] = Field(default_factory=list)
    disputable_public_records: list[DisputePublicRecord] = Field(default_factory=list)


# ── Validation Agent Output ──────────────────────────────────────────────────

class DisputeRiskLevel(str, Enum):
    """Risk classification assigned by the Validation Agent to a dispute item."""
    SAFE = "SAFE"              # All checks passed, no concerns
    WARNING = "WARNING"        # Soft issue noted but dispute may proceed with caution
    HIGH_RISK = "HIGH_RISK"    # LLM or rule flagged a significant compliance concern


class ValidationCheckRecord(BaseModel):
    """Provenance record for a single validation check on a dispute item.

    One record is created per check per item, forming a complete audit trail
    of every decision made by the Validation Agent (FCRA §611 compliance).
    """

    check_name: str = Field(..., description="Name of the validation rule (e.g. 'assert_not_positive')")
    account_name: str = Field(..., description="Account or creditor name being checked")
    bureau: str = Field(..., description="Bureau context for this check")
    passed: bool = Field(..., description="True if the check passed without issue")
    risk_level: DisputeRiskLevel = Field(
        DisputeRiskLevel.SAFE,
        description="Risk classification for this check result",
    )
    detail: str = Field("", description="Human-readable detail or warning message")
    llm_assisted: bool = Field(
        False, description="True if this check involved an LLM call"
    )
    llm_confidence: Optional[Literal["high", "medium", "low"]] = Field(
        None, description="LLM confidence level when llm_assisted=True"
    )
    timestamp: str = Field(..., description="ISO-8601 UTC timestamp of when the check ran")


class ValidationResult(BaseModel):
    """QA-verified dispute list from the Validation Agent for a single bureau."""

    verified_negatives: list[NegativeItem] = Field(default_factory=list)
    verified_inquiries: list[QualifyingInquiry] = Field(default_factory=list)
    verified_public_records: list[DisputePublicRecord] = Field(default_factory=list)
    validation_passed: bool = Field(
        ..., description="True if all hard assertions passed"
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Hard-stop warnings generated during validation",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Soft warnings (non-fatal): frivolous/irrelevant/risk flags",
    )
    provenance: list[ValidationCheckRecord] = Field(
        default_factory=list,
        description="Full audit trail of every validation check performed",
    )


# ── Drafting Agent Output ────────────────────────────────────────────────────

class DisputeLetter(BaseModel):
    """A generated dispute letter and its output file paths."""

    bureau: str = Field(..., description="Target bureau")
    content: str = Field(..., description="Full text of the dispute letter")
    docx_path: str = Field("", description="Path to the generated .docx file")
    pdf_path: str = Field("", description="Path to the generated .pdf file")


# ── Filter Agent Audit Trail ─────────────────────────────────────────────────

class FilterAuditEntry(BaseModel):
    """Immutable, SHA-256-chained audit record produced by the Evaluation Agent
    for every creditor-name match decision and inquiry attribution decision.

    Follows FCRA §611 requirements: deterministic, append-only, 7-year retention.
    """

    model_config = {"frozen": True}

    # Identity
    entry_id: str = Field(..., description="UUID for this log entry")
    timestamp: str = Field(..., description="ISO-8601 UTC timestamp with microseconds")
    correlation_id: str = Field(..., description="Shared ID grouping related entries")

    # Name-matching fields
    creditor_a: str = Field(..., description="Raw creditor name A (inquiry side)")
    creditor_b: str = Field(..., description="Raw creditor name B (account side)")
    normalized_a: str = Field(..., description="Normalized form of creditor_a")
    normalized_b: str = Field(..., description="Normalized form of creditor_b")
    abbreviation_hit: bool = Field(
        False, description="True if an abbreviation dictionary lookup resolved the match"
    )
    jaro_winkler_score: Optional[float] = Field(
        None, description="Jaro-Winkler score (0-1), None if resolved before fuzzy step"
    )
    match_result: bool = Field(..., description="Final boolean: are these the same creditor?")
    match_method: Literal["exact", "abbrev", "jaro", "llm", "no-match"] = Field(
        ..., description="Which resolution step produced the final answer"
    )
    llm_confidence: Optional[Literal["high", "medium", "low"]] = Field(
        None, description="LLM-reported confidence when match_method='llm'"
    )
    llm_reason: Optional[str] = Field(
        None, description="LLM-provided explanation when match_method='llm'"
    )

    # Time-window fields (only populated for inquiry attribution decisions)
    inquiry_date: Optional[str] = Field(None, description="Date of the hard inquiry (MM/DD/YYYY or ISO)")
    account_opened: Optional[str] = Field(None, description="Date the matched account was opened")
    days_delta: Optional[int] = Field(
        None, description="Calendar days between inquiry and account opening"
    )
    window_days_used: Optional[int] = Field(
        None, description="Which attribution window was applied (30 or 60)"
    )
    attribution_result: Optional[bool] = Field(
        None, description="True = inquiry attributed to account (not disputable)"
    )

    # Audit chain
    sha256_hash: str = Field(..., description="SHA-256 of this entry's content")
    previous_hash: str = Field(
        "GENESIS", description="SHA-256 of the immediately preceding entry (GENESIS for first)"
    )
