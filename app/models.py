"""
Invoice Detective AI — SQLAlchemy ORM Models.
"""

from datetime import datetime, date as date_type
from sqlalchemy import (
    Column, Integer, String, Float, Numeric, Boolean, Text, Date, DateTime,
    ForeignKey, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    """Local account used to authenticate access to a workspace."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(254), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Workspace(Base):
    """Tenant boundary for invoices and related records."""

    __tablename__ = "workspaces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class WorkspaceMembership(Base):
    """A user's role in a workspace."""

    __tablename__ = "workspace_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "workspace_id", name="uq_membership_user_workspace"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(30), default="owner", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class WorkspacePreferences(Base):
    """Persisted invoice and workspace defaults for a single workspace."""

    __tablename__ = "workspace_preferences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(
        Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    business_name = Column(String(255), default="", nullable=False)
    default_currency = Column(String(3), default="INR", nullable=False)
    date_format = Column(String(20), default="YYYY-MM-DD", nullable=False)
    time_zone = Column(String(64), default="Asia/Kolkata", nullable=False)
    language = Column(String(10), default="en", nullable=False)
    default_tax_rate = Column(Float, nullable=True)
    invoice_number_prefix = Column(String(32), default="", nullable=False)
    default_review_status = Column(String(20), default="needs_review", nullable=False)
    notify_audit_completion = Column(Boolean, default=True, nullable=False)
    notify_duplicate_detection = Column(Boolean, default=True, nullable=False)
    notify_failed_upload = Column(Boolean, default=True, nullable=False)
    notify_review_reminders = Column(Boolean, default=False, nullable=False)


class UserPreferences(Base):
    """Persisted profile and appearance preferences for a local account."""

    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    display_name = Column(String(100), default="", nullable=False)
    appearance = Column(String(16), default="light", nullable=False)


class AuthSession(Base):
    """Hashed opaque bearer session; raw tokens are never persisted."""

    __tablename__ = "auth_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Invoice(Base):
    """Represents an uploaded invoice document."""

    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=True, index=True)
    file_hash = Column(String(64), index=True, nullable=False)
    original_filename = Column(String(255), nullable=False)
    stored_filename = Column(String(255), unique=True, nullable=False)
    file_size = Column(Integer, nullable=False)
    file_type = Column(String(50), nullable=False)

    # Extracted / user-edited fields
    vendor_name = Column(String(255), nullable=True)
    invoice_number = Column(String(100), nullable=True)
    invoice_date = Column(Date, nullable=True)
    due_date = Column(Date, nullable=True)
    currency = Column(String(10), default="INR", nullable=False)
    vendor_address = Column(Text, nullable=True)
    subtotal = Column(Numeric(20, 4), nullable=True)
    tax_amount = Column(Numeric(20, 4), nullable=True)
    tax_rate = Column(Numeric(7, 4), nullable=True)
    discount_amount = Column(Numeric(20, 4), nullable=True)
    total_amount = Column(Numeric(20, 4), nullable=True)
    gstin = Column(String(15), nullable=True)

    # Raw text
    raw_extracted_text = Column(Text, nullable=True)
    extraction_confidence = Column(String(20), default="low", nullable=False)
    extraction_method = Column(String(50), nullable=True)
    processing_status = Column(String(20), default="completed", nullable=False)
    processing_error = Column(Text, nullable=True)

    # Review workflow
    review_status = Column(String(20), default="needs_review", nullable=False)
    is_confirmed = Column(Boolean, default=False, nullable=False)
    is_demo = Column(Boolean, default=False, nullable=False)
    notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    line_items = relationship("LineItem", back_populates="invoice", cascade="all, delete-orphan")
    findings = relationship(
        "Finding",
        back_populates="invoice",
        foreign_keys="Finding.invoice_id",
        cascade="all, delete-orphan",
    )
    purchase_order_comparisons = relationship(
        "PurchaseOrderComparison", back_populates="invoice", cascade="all, delete-orphan"
    )
    activity_entries = relationship(
        "InvoiceActivity", back_populates="invoice", cascade="all, delete-orphan"
    )


class InvoiceActivity(Base):
    """Workspace-scoped record of review actions on an invoice."""

    __tablename__ = "invoice_activity"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(
        Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invoice_id = Column(
        Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type = Column(String(40), nullable=False)
    summary = Column(String(255), nullable=False)
    changed_fields = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    invoice = relationship("Invoice", back_populates="activity_entries")


class LineItem(Base):
    """A single line item on an invoice."""

    __tablename__ = "line_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)
    description = Column(String(500), nullable=True)
    quantity = Column(Numeric(20, 6), nullable=True)
    unit_price = Column(Numeric(20, 4), nullable=True)
    amount = Column(Numeric(20, 4), nullable=True)
    item_order = Column(Integer, default=0, nullable=False)

    # Relationship
    invoice = relationship("Invoice", back_populates="line_items")


class Finding(Base):
    """An audit finding / issue detected on an invoice."""

    __tablename__ = "findings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)
    related_invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True)

    finding_type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    suggested_action = Column(
        Text,
        default="Review the source invoice and supporting records. Correct inaccurate fields, then mark the finding reviewed or resolved.",
        nullable=False,
    )
    affected_fields = Column(Text, nullable=True)  # JSON string of field names
    evidence = Column(Text, nullable=True)  # JSON string of evidence details

    review_status = Column(String(20), default="needs_review", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    invoice = relationship("Invoice", back_populates="findings", foreign_keys=[invoice_id])
    related_invoice = relationship("Invoice", foreign_keys=[related_invoice_id])


class PurchaseOrderComparison(Base):
    """Purchase order comparison result for an invoice."""

    __tablename__ = "purchase_order_comparisons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)
    po_number = Column(String(100), nullable=True)
    po_vendor = Column(String(255), nullable=True)
    po_currency = Column(String(3), nullable=True)
    po_total = Column(Numeric(20, 4), nullable=True)
    po_line_items = Column(Text, nullable=True)  # JSON
    comparison_result = Column(Text, nullable=True)  # JSON
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationship
    invoice = relationship("Invoice", back_populates="purchase_order_comparisons")


class PurchaseOrder(Base):
    """Workspace-scoped purchase order."""

    __tablename__ = "purchase_orders"
    __table_args__ = (
        UniqueConstraint("workspace_id", "po_number", name="uq_purchase_order_workspace_number"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    po_number = Column(String(100), nullable=False)
    vendor_name = Column(String(255), nullable=False)
    currency = Column(String(3), nullable=False, default="INR")
    total_amount = Column(Numeric(20, 4), nullable=False, default=0)
    order_date = Column(Date, nullable=True)
    expected_delivery_date = Column(Date, nullable=True)
    tax_rate = Column(Numeric(7, 4), nullable=False, default=0)
    status = Column(String(20), nullable=False, default="open")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    line_items = relationship(
        "PurchaseOrderLineItem",
        back_populates="purchase_order",
        cascade="all, delete-orphan",
        order_by="PurchaseOrderLineItem.item_order",
    )


class PurchaseOrderLineItem(Base):
    """A line item belonging to a saved purchase order."""

    __tablename__ = "purchase_order_line_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    purchase_order_id = Column(
        Integer, ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description = Column(String(500), nullable=False)
    quantity = Column(Numeric(20, 6), nullable=False)
    unit_price = Column(Numeric(20, 4), nullable=False)
    amount = Column(Numeric(20, 4), nullable=False)
    item_order = Column(Integer, nullable=False, default=0)

    purchase_order = relationship("PurchaseOrder", back_populates="line_items")


class DuplicateDetection(Base):
    """Persisted duplicate match, including rejected exact-duplicate uploads."""

    __tablename__ = "duplicate_detections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True, index=True)
    matched_invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)
    attempted_file_hash = Column(String(64), nullable=True, index=True)
    match_type = Column(String(50), nullable=False)
    confidence = Column(Float, nullable=False)
    evidence = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
