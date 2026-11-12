"""
Invoice Detective AI — Purchase Order Comparison Service.

Compares invoice data against purchase order details.
"""

import json
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session

from app.models import Invoice, Finding, PurchaseOrderComparison, LineItem
from app.schemas import PurchaseOrderInput


def _dump_json(value: object) -> str:
    return json.dumps(value, default=float)


def _decimal(value: object) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def compare_po_to_invoice(
    invoice: Invoice,
    po_data: PurchaseOrderInput,
    db: Session,
) -> PurchaseOrderComparison:
    """
    Compare purchase order data against an invoice.

    Creates findings for any mismatches found.
    """
    comparison_results = []
    findings = []
    currency_match = True

    if po_data.po_currency:
        if invoice.currency:
            currency_match = po_data.po_currency.strip().upper() == invoice.currency.strip().upper()
            comparison_results.append({
                "field": "currency",
                "po_value": po_data.po_currency,
                "invoice_value": invoice.currency,
                "match": currency_match,
            })
            if not currency_match:
                findings.append(Finding(
                    invoice_id=invoice.id,
                    finding_type="po_mismatch",
                    severity="high",
                    title="Currency Mismatch with Purchase Order",
                    description=(
                        f"PO currency '{po_data.po_currency}' does not match "
                        f"invoice currency '{invoice.currency}'. Amounts were not compared."
                    ),
                    affected_fields=json.dumps(["currency", "total_amount"]),
                    evidence=_dump_json({
                        "po_currency": po_data.po_currency,
                        "invoice_currency": invoice.currency,
                        "po_number": po_data.po_number,
                    }),
                ))
        else:
            comparison_results.append({
                "field": "currency",
                "status": "unavailable",
                "reason": "Invoice currency is missing.",
            })

    # Compare vendor
    if po_data.po_vendor and invoice.vendor_name:
        vendor_match = po_data.po_vendor.lower().strip() == invoice.vendor_name.lower().strip()
        comparison_results.append({
            "field": "vendor",
            "po_value": po_data.po_vendor,
            "invoice_value": invoice.vendor_name,
            "match": vendor_match,
        })
        if not vendor_match:
            findings.append(Finding(
                invoice_id=invoice.id,
                finding_type="po_mismatch",
                severity="high",
                title="Vendor Name Mismatch with Purchase Order",
                description=(
                    f"PO vendor '{po_data.po_vendor}' does not match "
                    f"invoice vendor '{invoice.vendor_name}'."
                ),
                affected_fields=json.dumps(["vendor_name"]),
                evidence=json.dumps({
                    "po_vendor": po_data.po_vendor,
                    "invoice_vendor": invoice.vendor_name,
                    "po_number": po_data.po_number,
                }),
            ))
    elif po_data.po_vendor or invoice.vendor_name:
        comparison_results.append({
            "field": "vendor",
            "status": "unavailable",
            "reason": "One or both vendor names missing.",
        })

    # Compare total
    if po_data.po_total is not None and invoice.total_amount is not None and currency_match:
        po_total = _decimal(po_data.po_total)
        invoice_total = _decimal(invoice.total_amount)
        total_diff = abs(po_total - invoice_total)
        total_match = total_diff < Decimal("0.01")
        comparison_results.append({
            "field": "total",
            "po_value": po_total,
            "invoice_value": invoice_total,
            "match": total_match,
            "difference": round(total_diff, 2),
        })
        if not total_match:
            severity = (
                "high"
                if po_total == 0 or total_diff > abs(po_total) * Decimal("0.1")
                else "medium"
            )
            findings.append(Finding(
                invoice_id=invoice.id,
                finding_type="po_mismatch",
                severity=severity,
                title="Total Amount Mismatch with Purchase Order",
                description=(
                    f"PO total ({po_data.po_total}) differs from "
                    f"invoice total ({invoice.total_amount}) by {total_diff:.2f}."
                ),
                affected_fields=json.dumps(["total_amount"]),
                evidence=_dump_json({
                    "po_total": po_total,
                    "invoice_total": invoice_total,
                    "difference": round(total_diff, 2),
                    "po_number": po_data.po_number,
                }),
            ))
    elif not currency_match:
        comparison_results.append({
            "field": "total",
            "status": "not_compared",
            "reason": "Currencies do not match.",
        })
    elif po_data.po_total is not None or invoice.total_amount is not None:
        comparison_results.append({
            "field": "total",
            "status": "unavailable",
            "reason": "One or both totals missing.",
        })

    # Compare line items
    if po_data.po_line_items and len(po_data.po_line_items) > 0:
        invoice_items = db.query(LineItem).filter(
            LineItem.invoice_id == invoice.id
        ).order_by(LineItem.item_order).all()

        if invoice_items:
            line_item_results = _compare_line_items(
                po_data.po_line_items, invoice_items, invoice.id
            )
            comparison_results.extend(line_item_results["comparisons"])
            findings.extend(line_item_results["findings"])
        else:
            comparison_results.append({
                "field": "line_items",
                "status": "unavailable",
                "reason": "No line items found on invoice for comparison.",
            })

    # Save comparison record
    po_comparison = PurchaseOrderComparison(
        invoice_id=invoice.id,
        po_number=po_data.po_number,
        po_vendor=po_data.po_vendor,
        po_currency=po_data.po_currency,
        po_total=po_data.po_total,
        po_line_items=_dump_json([item.model_dump() for item in po_data.po_line_items]) if po_data.po_line_items else None,
        comparison_result=_dump_json(comparison_results),
    )
    db.add(po_comparison)

    # Save findings
    for finding in findings:
        db.add(finding)

    db.commit()
    db.refresh(po_comparison)

    return po_comparison


def _compare_line_items(
    po_items: list,
    invoice_items: list,
    invoice_id: int,
) -> dict:
    """Compare PO line items against invoice line items."""
    comparisons = []
    findings = []

    for i, po_item in enumerate(po_items):
        po_desc = (po_item.description or "").lower().strip()
        matched = False

        for inv_item in invoice_items:
            inv_desc = (inv_item.description or "").lower().strip()

            # Simple matching by description similarity
            if po_desc and inv_desc and (po_desc in inv_desc or inv_desc in po_desc):
                matched = True
                item_comparison = {
                    "field": f"line_item_{i+1}",
                    "po_description": po_item.description,
                    "invoice_description": inv_item.description,
                    "matches": {},
                }

                # Compare quantity
                if po_item.quantity is not None and inv_item.quantity is not None:
                    po_quantity = _decimal(po_item.quantity)
                    invoice_quantity = _decimal(inv_item.quantity)
                    qty_match = abs(po_quantity - invoice_quantity) < Decimal("0.01")
                    item_comparison["matches"]["quantity"] = {
                        "po": po_quantity,
                        "invoice": invoice_quantity,
                        "match": qty_match,
                    }
                    if not qty_match:
                        findings.append(Finding(
                            invoice_id=invoice_id,
                            finding_type="po_mismatch",
                            severity="medium",
                            title=f"Quantity Mismatch: {po_item.description or 'Item'}",
                            description=(
                                f"PO quantity ({po_item.quantity}) differs from "
                                f"invoice quantity ({inv_item.quantity}) for '{po_item.description}'."
                            ),
                            affected_fields=json.dumps(["line_items"]),
                            evidence=_dump_json({
                                "item": po_item.description,
                                "po_quantity": po_quantity,
                                "invoice_quantity": invoice_quantity,
                            }),
                        ))

                # Compare unit price
                if po_item.unit_price is not None and inv_item.unit_price is not None:
                    po_unit_price = _decimal(po_item.unit_price)
                    invoice_unit_price = _decimal(inv_item.unit_price)
                    price_match = abs(po_unit_price - invoice_unit_price) < Decimal("0.01")
                    item_comparison["matches"]["unit_price"] = {
                        "po": po_unit_price,
                        "invoice": invoice_unit_price,
                        "match": price_match,
                    }
                    if not price_match:
                        findings.append(Finding(
                            invoice_id=invoice_id,
                            finding_type="po_mismatch",
                            severity="medium",
                            title=f"Unit Price Mismatch: {po_item.description or 'Item'}",
                            description=(
                                f"PO unit price ({po_item.unit_price}) differs from "
                                f"invoice unit price ({inv_item.unit_price}) for '{po_item.description}'."
                            ),
                            affected_fields=json.dumps(["line_items"]),
                            evidence=_dump_json({
                                "item": po_item.description,
                                "po_unit_price": po_unit_price,
                                "invoice_unit_price": invoice_unit_price,
                            }),
                        ))

                comparisons.append(item_comparison)
                break

        if not matched:
            comparisons.append({
                "field": f"line_item_{i+1}",
                "po_description": po_item.description,
                "status": "not_found_on_invoice",
            })
            findings.append(Finding(
                invoice_id=invoice_id,
                finding_type="po_mismatch",
                severity="low",
                title=f"PO Line Item Not Found on Invoice: {po_item.description or 'Item'}",
                description=(
                    f"PO line item '{po_item.description}' could not be matched "
                    f"to any invoice line item."
                ),
                affected_fields=json.dumps(["line_items"]),
                evidence=json.dumps({
                    "po_item": po_item.description,
                    "match_status": "not_found",
                }),
            ))

    return {"comparisons": comparisons, "findings": findings}
