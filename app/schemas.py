"""
Invoice Detective AI — Pydantic v2 Schemas.

Request/response models for all API endpoints.
"""

from datetime import date, datetime
from decimal import Decimal
import re
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator


# ---------------------------------------------------------------------------
# Line Items
# ---------------------------------------------------------------------------

class LineItemBase(BaseModel):
    """Base schema for invoice line items."""
    description: Optional[str] = Field(None, max_length=500)
    quantity: Optional[Decimal] = Field(None, ge=0, max_digits=20, decimal_places=6, allow_inf_nan=False)
    unit_price: Optional[Decimal] = Field(None, ge=0, max_digits=20, decimal_places=4, allow_inf_nan=False)
    amount: Optional[Decimal] = Field(None, ge=0, max_digits=20, decimal_places=4, allow_inf_nan=False)
    item_order: int = Field(0, ge=0)


class LineItemCreate(LineItemBase):
    """Schema for creating a line item."""
    pass


class LineItemResponse(LineItemBase):
    """Schema for returning a line item."""
    id: int
    invoice_id: int

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

class FindingResponse(BaseModel):
    """Schema for returning an audit finding."""
    id: int
    invoice_id: int
    related_invoice_id: Optional[int] = None
    finding_type: str
    severity: str
    title: str
    description: str
    suggested_action: str
    affected_fields: Optional[list[str]] = None
    evidence: Optional[dict[str, Any]] = None
    review_status: str = "needs_review"
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FindingStatusUpdate(BaseModel):
    """Schema for updating a finding's review status."""
    review_status: str = Field(..., pattern=r"^(needs_review|reviewed|resolved)$")


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------

class InvoiceBase(BaseModel):
    """Base schema for invoices."""
    vendor_name: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    currency: str = "INR"
    vendor_address: Optional[str] = None
    subtotal: Optional[Decimal] = Field(None, max_digits=20, decimal_places=4, allow_inf_nan=False)
    tax_amount: Optional[Decimal] = Field(None, max_digits=20, decimal_places=4, allow_inf_nan=False)
    tax_rate: Optional[Decimal] = Field(None, ge=0, le=100, max_digits=7, decimal_places=4, allow_inf_nan=False)
    discount_amount: Optional[Decimal] = Field(None, ge=0, max_digits=20, decimal_places=4, allow_inf_nan=False)
    total_amount: Optional[Decimal] = Field(None, max_digits=20, decimal_places=4, allow_inf_nan=False)
    gstin: Optional[str] = None
    notes: Optional[str] = None


class InvoiceCreate(InvoiceBase):
    """Schema for creating an invoice (used internally after upload)."""
    file_hash: str
    original_filename: str
    stored_filename: str
    file_size: int
    file_type: str
    raw_extracted_text: Optional[str] = None
    extraction_confidence: str = "low"


class InvoiceUpdate(BaseModel):
    """Schema for user-editable invoice fields."""
    vendor_name: Optional[str] = Field(None, max_length=255)
    invoice_number: Optional[str] = Field(None, max_length=100)
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    currency: Optional[str] = Field(None, max_length=10)
    vendor_address: Optional[str] = Field(None, max_length=5000)
    subtotal: Optional[Decimal] = Field(None, max_digits=20, decimal_places=4, allow_inf_nan=False)
    tax_amount: Optional[Decimal] = Field(None, max_digits=20, decimal_places=4, allow_inf_nan=False)
    tax_rate: Optional[Decimal] = Field(None, ge=0, le=100, max_digits=7, decimal_places=4, allow_inf_nan=False)
    discount_amount: Optional[Decimal] = Field(None, ge=0, max_digits=20, decimal_places=4, allow_inf_nan=False)
    total_amount: Optional[Decimal] = Field(None, max_digits=20, decimal_places=4, allow_inf_nan=False)
    gstin: Optional[str] = Field(None, max_length=15)
    notes: Optional[str] = Field(None, max_length=5000)
    review_status: Optional[str] = Field(None, pattern=r"^(needs_review|reviewed|resolved)$")
    line_items: Optional[list[LineItemCreate]] = Field(None, max_length=500)


class InvoiceResponse(InvoiceBase):
    """Full invoice response with related objects."""
    id: int
    file_hash: str
    original_filename: str
    stored_filename: str
    file_size: int
    file_type: str
    raw_extracted_text: Optional[str] = None
    extraction_confidence: str = "low"
    extraction_method: Optional[str] = None
    processing_status: str = "completed"
    processing_error: Optional[str] = None
    review_status: str = "needs_review"
    is_confirmed: bool = False
    is_demo: bool = False
    created_at: datetime
    uploaded_at: datetime
    updated_at: datetime
    line_items: list[LineItemResponse] = []
    findings: list[FindingResponse] = []

    model_config = ConfigDict(from_attributes=True)


class InvoiceListResponse(BaseModel):
    """Paginated list of invoices."""
    items: list[InvoiceResponse]
    total: int
    page: int
    page_size: int


class DuplicateDetectionResponse(BaseModel):
    id: int
    source_invoice_id: Optional[int] = None
    matched_invoice_id: int
    attempted_file_hash: Optional[str] = None
    match_type: str
    confidence: float
    evidence: dict[str, Any]
    created_at: datetime


# ---------------------------------------------------------------------------
# Purchase Order
# ---------------------------------------------------------------------------

class POLineItem(BaseModel):
    """A single line item from a purchase order."""
    description: Optional[str] = None
    quantity: Optional[Decimal] = Field(None, max_digits=20, decimal_places=6, allow_inf_nan=False)
    unit_price: Optional[Decimal] = Field(None, max_digits=20, decimal_places=4, allow_inf_nan=False)
    amount: Optional[Decimal] = Field(None, max_digits=20, decimal_places=4, allow_inf_nan=False)


class PurchaseOrderInput(BaseModel):
    """Input schema for PO comparison."""
    po_number: Optional[str] = None
    po_vendor: Optional[str] = None
    po_currency: Optional[str] = None
    po_total: Optional[Decimal] = Field(None, max_digits=20, decimal_places=4, allow_inf_nan=False)
    po_line_items: list[POLineItem] = Field(default_factory=list)


class PurchaseOrderLineItemInput(BaseModel):
    """Validated line item for a saved purchase order."""

    description: str = Field(min_length=1, max_length=500)
    quantity: Decimal = Field(gt=0, max_digits=20, decimal_places=6, allow_inf_nan=False)
    unit_price: Decimal = Field(ge=0, max_digits=20, decimal_places=4, allow_inf_nan=False)

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Line item description cannot be empty.")
        return value


class PurchaseOrderWrite(BaseModel):
    """Create or replace a workspace purchase order."""

    po_number: str = Field(min_length=1, max_length=100)
    vendor_name: str = Field(min_length=1, max_length=255)
    currency: str = Field(min_length=3, max_length=3)
    order_date: date
    expected_delivery_date: Optional[date] = None
    tax_rate: Decimal = Field(0, ge=0, le=100, max_digits=7, decimal_places=4, allow_inf_nan=False)
    status: Literal["open", "fulfilled", "cancelled"] = "open"
    line_items: list[PurchaseOrderLineItemInput] = Field(min_length=1, max_length=200)

    @field_validator("po_number", "vendor_name")
    @classmethod
    def clean_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be empty.")
        return value

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", value):
            raise ValueError("Currency must be a three-letter ISO code.")
        return value


class PurchaseOrderComparisonResponse(BaseModel):
    """Response schema for PO comparison results."""
    id: int
    invoice_id: int
    po_number: Optional[str] = None
    po_vendor: Optional[str] = None
    po_currency: Optional[str] = None
    po_total: Optional[float] = None
    po_line_items: Optional[str] = None
    comparison_result: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class DashboardStats(BaseModel):
    """Dashboard summary statistics."""
    total_invoices: int = 0
    total_findings: int = 0
    findings_by_severity: dict[str, int] = {}
    findings_by_type: dict[str, int] = {}
    recent_invoices: list[InvoiceResponse] = []


class RecentActivity(BaseModel):
    """Recent activity for the dashboard."""
    recent_invoices: list[InvoiceResponse] = []
    recent_findings: list[FindingResponse] = []


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

class ReportRequest(BaseModel):
    """Request schema for generating reports."""
    format: str = "csv"
    include_findings: bool = True
    review_status_filter: Optional[str] = None


class ReportSummary(BaseModel):
    """Summary stats for the report page."""
    total_invoices: int = 0
    reviewed_count: int = 0
    needs_review_count: int = 0
    resolved_count: int = 0
    total_findings: int = 0
    high_severity_count: int = 0
    medium_severity_count: int = 0
    low_severity_count: int = 0
    total_amount_sum: Optional[float] = None


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "healthy"
    version: str = "1.0.0-mvp"
    environment: str = "development"


class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=12, max_length=128)
    workspace_name: str = Field("My workspace", min_length=1, max_length=100)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("Enter a valid email address.")
        return normalized

    @field_validator("workspace_name")
    @classmethod
    def normalize_workspace_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Enter a workspace name.")
        return normalized


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("Enter a valid email address.")
        return normalized


class AuthenticatedUserResponse(BaseModel):
    id: int
    email: str
    role: str


class AuthenticatedWorkspaceResponse(BaseModel):
    id: int
    name: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: AuthenticatedUserResponse
    workspace: AuthenticatedWorkspaceResponse


class WorkspaceSettingsUpdate(BaseModel):
    workspace_name: str = Field(..., min_length=1, max_length=100)
    business_name: str = Field("", max_length=255)
    default_currency: str = Field("INR", min_length=3, max_length=3)
    date_format: str = Field("YYYY-MM-DD", pattern=r"^(YYYY-MM-DD|DD/MM/YYYY|MM/DD/YYYY)$")
    time_zone: str = Field("Asia/Kolkata", pattern=r"^(Asia/Kolkata|UTC|Europe/London|America/New_York|Asia/Singapore)$")
    language: str = Field("en", pattern=r"^(en|hi)$")
    default_tax_rate: Optional[float] = Field(None, ge=0, le=100, allow_inf_nan=False)
    invoice_number_prefix: str = Field("", max_length=32)
    default_review_status: str = Field("needs_review", pattern=r"^(needs_review|reviewed)$")
    notify_audit_completion: bool = True
    notify_duplicate_detection: bool = True
    notify_failed_upload: bool = True
    notify_review_reminders: bool = False
    profile_display_name: str = Field("", max_length=100)
    appearance: str = Field("light", pattern=r"^(light|dark|system)$")

    @field_validator("workspace_name")
    @classmethod
    def normalize_workspace_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Workspace name cannot be blank.")
        return normalized

    @field_validator("business_name", "invoice_number_prefix", "profile_display_name")
    @classmethod
    def trim_optional_names(cls, value: str) -> str:
        return value.strip()

    @field_validator("default_currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", normalized):
            raise ValueError("Enter a three-letter currency code.")
        return normalized


class ErrorResponse(BaseModel):
    """Standard error response."""
    detail: str
    error_code: Optional[str] = None


class PrivacyInfo(BaseModel):
    """Privacy information response."""
    data_stored: list[str]
    file_types_accepted: list[str]
    storage_location: str
    data_retention: str
    third_party_sharing: str


class StorageStats(BaseModel):
    """Storage statistics response."""
    total_invoices: int = 0
    total_file_size_bytes: int = 0
    total_file_size_mb: float = 0.0
    database_size_bytes: int = 0
    database_size_mb: float = 0.0


class PurgeConfirmation(BaseModel):
    """Double confirmation for data purge."""
    confirm: bool = False
    confirm_text: str = ""
