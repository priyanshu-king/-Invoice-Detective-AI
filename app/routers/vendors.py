"""Workspace vendor intelligence derived from saved invoice records."""

from collections import defaultdict
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import DuplicateDetection, Invoice
from app.security import AuthenticatedPrincipal, get_current_principal


router = APIRouter(prefix="/vendors", tags=["vendors"])


@router.get("")
def list_vendor_intelligence(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    invoices = (
        db.query(Invoice)
        .options(selectinload(Invoice.line_items), selectinload(Invoice.findings))
        .filter(
            Invoice.workspace_id == principal.workspace_id,
            Invoice.vendor_name.isnot(None),
        )
        .order_by(Invoice.created_at.desc(), Invoice.id.desc())
        .all()
    )
    duplicate_counts = dict(
        db.query(DuplicateDetection.matched_invoice_id, func.count(DuplicateDetection.id))
        .join(Invoice, Invoice.id == DuplicateDetection.matched_invoice_id)
        .filter(Invoice.workspace_id == principal.workspace_id)
        .group_by(DuplicateDetection.matched_invoice_id)
        .all()
    )

    vendors: dict[str, dict[str, Any]] = {}
    for invoice in invoices:
        name = (invoice.vendor_name or "").strip()
        if not name:
            continue
        key = name.casefold()
        vendor = vendors.setdefault(key, {
            "name": name,
            "invoice_count": 0,
            "invoice_ids": [],
            "total_value_by_currency": defaultdict(lambda: Decimal("0.00")),
            "invoice_frequency": defaultdict(int),
            "findings_by_severity": defaultdict(int),
            "recent_findings": [],
            "price_history": defaultdict(list),
            "duplicate_matches": 0,
            "recent_invoices": [],
        })

        vendor["invoice_count"] += 1
        vendor["invoice_ids"].append(invoice.id)
        if invoice.total_amount is not None:
            currency = (invoice.currency or "INR").upper()
            vendor["total_value_by_currency"][currency] += Decimal(str(invoice.total_amount))
        if invoice.invoice_date:
            vendor["invoice_frequency"][invoice.invoice_date.strftime("%Y-%m")] += 1

        vendor["duplicate_matches"] += duplicate_counts.get(invoice.id, 0)
        for finding in invoice.findings or []:
            severity = (finding.severity or "unknown").lower()
            vendor["findings_by_severity"][severity] += 1
            vendor["recent_findings"].append({
                "invoice_id": invoice.id,
                "title": finding.title,
                "severity": severity,
                "created_at": finding.created_at.isoformat(),
            })

        invoice_date = invoice.invoice_date.isoformat() if invoice.invoice_date else None
        for item in invoice.line_items or []:
            description = (item.description or "").strip()
            if not description or item.unit_price is None:
                continue
            price_key = (description.casefold(), (invoice.currency or "INR").upper())
            vendor["price_history"][price_key].append({
                "description": description,
                "currency": (invoice.currency or "INR").upper(),
                "invoice_id": invoice.id,
                "date": invoice_date,
                "unit_price": float(item.unit_price),
            })

        vendor["recent_invoices"].append({
            "id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "invoice_date": invoice_date,
            "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
            "currency": invoice.currency,
            "total_amount": float(invoice.total_amount) if invoice.total_amount is not None else None,
            "review_status": invoice.review_status,
        })

    results = []
    for vendor in vendors.values():
        price_changes = []
        for entries in vendor["price_history"].values():
            ordered_entries = sorted(
                entries,
                key=lambda entry: (entry["date"] or "", entry["invoice_id"]),
            )
            distinct_prices = {round(float(entry["unit_price"]), 4) for entry in ordered_entries}
            if len(distinct_prices) > 1:
                price_changes.append({
                    "description": ordered_entries[0]["description"],
                    "currency": ordered_entries[0]["currency"],
                    "entries": ordered_entries,
                })

        results.append({
            "name": vendor["name"],
            "invoice_count": vendor["invoice_count"],
            "total_value_by_currency": [
                {"currency": currency, "amount": round(float(amount), 2)}
                for currency, amount in sorted(vendor["total_value_by_currency"].items())
            ],
            "invoice_frequency": [
                {"month": month, "count": count}
                for month, count in sorted(vendor["invoice_frequency"].items())
            ],
            "findings_by_severity": dict(vendor["findings_by_severity"]),
            "recent_findings": sorted(
                vendor["recent_findings"],
                key=lambda item: item["created_at"],
                reverse=True,
            )[:5],
            "duplicate_matches": vendor["duplicate_matches"],
            "price_changes": price_changes,
            "recent_invoices": vendor["recent_invoices"][:5],
            "contact_details_available": False,
            "payment_tracking_available": False,
        })

    return sorted(results, key=lambda vendor: (-vendor["invoice_count"], vendor["name"].casefold()))
