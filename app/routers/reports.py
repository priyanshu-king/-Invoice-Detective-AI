"""Filtered workspace invoice and audit reports."""

import csv
import io
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import DuplicateDetection, Invoice
from app.security import AuthenticatedPrincipal, get_current_principal
from app.utils.csv_export import sanitize_csv_cell


router = APIRouter(prefix="/reports", tags=["reports"])
REVIEW_STATUSES = {"needs_review", "reviewed", "resolved"}
REPORT_TYPES = {
    "invoice_summary",
    "monthly_audit",
    "duplicate_detection",
    "vendor_spending",
    "due_dates",
    "review_status",
}


def _filtered_invoices(
    db: Session,
    workspace_id: int,
    date_from: date | None,
    date_to: date | None,
    vendor: str | None,
    currency: str | None,
    review_status: str | None,
    report_type: str,
) -> list[Invoice]:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="Start date must not be after end date.")
    if review_status and review_status not in REVIEW_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid review status.")
    if report_type not in REPORT_TYPES:
        raise HTTPException(status_code=400, detail="Invalid report type.")
    if currency and not re.fullmatch(r"[A-Za-z]{3}", currency.strip()):
        raise HTTPException(status_code=400, detail="Currency must be a three-letter ISO code.")

    query = (
        db.query(Invoice)
        .options(selectinload(Invoice.findings), selectinload(Invoice.line_items))
        .filter(Invoice.workspace_id == workspace_id)
    )
    if date_from:
        query = query.filter(Invoice.invoice_date >= date_from)
    if date_to:
        query = query.filter(Invoice.invoice_date <= date_to)
    if vendor and vendor.strip():
        query = query.filter(Invoice.vendor_name.ilike(f"%{vendor.strip()}%"))
    if currency:
        query = query.filter(Invoice.currency == currency.strip().upper())
    if review_status:
        query = query.filter(Invoice.review_status == review_status)
    if report_type == "duplicate_detection":
        matched_invoice_ids = (
            db.query(DuplicateDetection.matched_invoice_id)
            .join(Invoice, Invoice.id == DuplicateDetection.matched_invoice_id)
            .filter(Invoice.workspace_id == workspace_id)
            .distinct()
        )
        query = query.filter(Invoice.id.in_(matched_invoice_ids))
    elif report_type == "vendor_spending":
        query = query.filter(Invoice.vendor_name.isnot(None), Invoice.total_amount.isnot(None))
    elif report_type == "due_dates":
        query = query.filter(Invoice.due_date.isnot(None))
    return query.order_by(Invoice.created_at.desc(), Invoice.id.desc()).all()


def _build_summary(
    db: Session,
    invoices: list[Invoice],
    date_from: date | None,
    date_to: date | None,
    vendor: str | None,
    currency: str | None,
    review_status: str | None,
    report_type: str,
) -> dict[str, Any]:
    invoice_ids = [invoice.id for invoice in invoices]
    duplicate_counts = {}
    if invoice_ids:
        duplicate_counts = dict(
            db.query(
                DuplicateDetection.matched_invoice_id,
                func.count(DuplicateDetection.id),
            )
            .filter(DuplicateDetection.matched_invoice_id.in_(invoice_ids))
            .group_by(DuplicateDetection.matched_invoice_id)
            .all()
        )

    totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    statuses: dict[str, int] = defaultdict(int)
    severities: dict[str, int] = defaultdict(int)
    monthly_volume: dict[str, int] = defaultdict(int)
    vendor_totals: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal("0.00"))
    items = []
    duplicate_invoice_count = 0

    for invoice in invoices:
        invoice_currency = (invoice.currency or "INR").upper()
        finding_count = len(invoice.findings or [])
        duplicate_count = duplicate_counts.get(invoice.id, 0)
        duplicate_invoice_count += duplicate_count
        statuses[invoice.review_status] += 1
        if invoice.total_amount is not None:
            amount = Decimal(str(invoice.total_amount))
            totals[invoice_currency] += amount
            vendor_name = (invoice.vendor_name or "Unknown vendor").strip()
            vendor_totals[(vendor_name, invoice_currency)] += amount
        if invoice.invoice_date:
            monthly_volume[invoice.invoice_date.strftime("%Y-%m")] += 1
        for finding in invoice.findings or []:
            severities[(finding.severity or "unknown").lower()] += 1
        items.append({
            "id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "vendor_name": invoice.vendor_name,
            "invoice_date": invoice.invoice_date.isoformat() if invoice.invoice_date else None,
            "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
            "currency": invoice_currency,
            "total_amount": float(invoice.total_amount) if invoice.total_amount is not None else None,
            "review_status": invoice.review_status,
            "finding_count": finding_count,
            "duplicate_matches": duplicate_count,
        })

    return {
        "filters": {
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
            "vendor": vendor,
            "currency": currency.strip().upper() if currency else None,
            "review_status": review_status,
            "report_type": report_type,
        },
        "invoice_count": len(invoices),
        "total_value_by_currency": [
            {"currency": key, "amount": round(float(value), 2)}
            for key, value in sorted(totals.items())
        ],
        "review_status_counts": dict(statuses),
        "findings_by_severity": dict(severities),
        "duplicate_matches": duplicate_invoice_count,
        "monthly_invoice_volume": [
            {"month": month, "count": count}
            for month, count in sorted(monthly_volume.items())
        ],
        "vendor_spending": [
            {"vendor": name, "currency": code, "amount": round(float(amount), 2)}
            for (name, code), amount in sorted(vendor_totals.items())
        ],
        "items": items,
    }


def _report_filters(
    date_from: date | None,
    date_to: date | None,
    vendor: str | None,
    currency: str | None,
    review_status: str | None,
    report_type: str,
) -> dict[str, Any]:
    return {
        "date_from": date_from,
        "date_to": date_to,
        "vendor": vendor,
        "currency": currency,
        "review_status": review_status,
        "report_type": report_type,
    }


@router.get("/summary")
def report_summary(
    date_from: date | None = None,
    date_to: date | None = None,
    vendor: str | None = Query(default=None, max_length=255),
    currency: str | None = Query(default=None, max_length=3),
    review_status: str | None = None,
    report_type: str = Query(default="invoice_summary", max_length=32),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    filters = _report_filters(date_from, date_to, vendor, currency, review_status, report_type)
    invoices = _filtered_invoices(db, principal.workspace_id, **filters)
    return _build_summary(db, invoices, **filters)


@router.get("/summary.csv")
def report_summary_csv(
    date_from: date | None = None,
    date_to: date | None = None,
    vendor: str | None = Query(default=None, max_length=255),
    currency: str | None = Query(default=None, max_length=3),
    review_status: str | None = None,
    report_type: str = Query(default="invoice_summary", max_length=32),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    filters = _report_filters(date_from, date_to, vendor, currency, review_status, report_type)
    invoices = _filtered_invoices(db, principal.workspace_id, **filters)
    summary = _build_summary(db, invoices, **filters)
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    writer.writerow([
        "Invoice ID",
        "Invoice Number",
        "Vendor",
        "Invoice Date",
        "Due Date",
        "Currency",
        "Total Amount",
        "Review Status",
        "Finding Count",
        "Duplicate Matches",
    ])
    for invoice in summary["items"]:
        writer.writerow([sanitize_csv_cell(invoice[field]) for field in (
            "id",
            "invoice_number",
            "vendor_name",
            "invoice_date",
            "due_date",
            "currency",
            "total_amount",
            "review_status",
            "finding_count",
            "duplicate_matches",
        )])
    csv_bytes = output.getvalue().encode("utf-8-sig")
    output.close()
    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="filtered-invoice-report.csv"'},
    )
