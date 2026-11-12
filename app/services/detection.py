"""
Invoice Detective AI — Detection Engine.

Deterministic, explainable checks for duplicates, arithmetic errors,
missing fields, suspicious amounts, and GST format validation.
"""

import json
import re
import unicodedata
from decimal import Decimal, ROUND_HALF_UP
from difflib import SequenceMatcher
from statistics import median
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import DuplicateDetection, Invoice, Finding, LineItem


# Default rounding tolerance for arithmetic checks (in currency units)
DEFAULT_ROUNDING_TOLERANCE = Decimal("1.00")


def _decimal(value: object) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _rounded(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _dump_json(value: object) -> str:
    return json.dumps(value, default=float)


def normalize_vendor_name(name: Optional[str]) -> Optional[str]:
    """Normalize Unicode, punctuation, and spacing without stripping legal name parts."""
    if not name:
        return None
    normalized = unicodedata.normalize("NFKC", name).casefold()
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.split()) or None


def normalize_invoice_number(number: Optional[str]) -> Optional[str]:
    """Normalize an invoice number for comparison."""
    if not number:
        return None

    normalized = number.lower().strip()
    for _ in range(2):
        normalized = re.sub(
            r'^(?:invoice|inv|bill|receipt|po|purchase\s*order)[\s#:\-._]*',
            '',
            normalized,
            flags=re.IGNORECASE,
        )
    normalized = re.sub(r'[^a-z0-9]+', '', normalized)
    return normalized or None


def run_all_checks(invoice: Invoice, db: Session, tolerance: float = DEFAULT_ROUNDING_TOLERANCE) -> list[Finding]:
    """
    Run all detection checks on an invoice and create Finding records.

    Returns list of created Finding objects.
    """
    # Delete existing findings for this invoice (for re-analysis)
    db.query(Finding).filter(Finding.invoice_id == invoice.id).delete()
    db.flush()

    findings = []

    findings.extend(check_duplicate_hash(invoice, db))
    findings.extend(check_duplicate_number(invoice, db))
    findings.extend(check_potential_duplicates(invoice, db))
    findings.extend(check_arithmetic(invoice, db, tolerance))
    findings.extend(check_tax_calculation(invoice, tolerance))
    findings.extend(check_missing_fields(invoice))
    findings.extend(check_suspicious_amounts(invoice))
    findings.extend(check_unusual_amounts(invoice, db))
    findings.extend(check_gst_format(invoice))

    db.query(DuplicateDetection).filter(
        DuplicateDetection.source_invoice_id == invoice.id
    ).delete(synchronize_session=False)
    confidence_by_type = {
        "duplicate_hash": 1.0,
        "duplicate_number": 0.9,
        "potential_duplicate": 0.7,
    }
    for finding in findings:
        if finding.finding_type not in confidence_by_type or finding.related_invoice_id is None:
            continue
        evidence = json.loads(finding.evidence or "{}")
        db.add(DuplicateDetection(
            source_invoice_id=invoice.id,
            matched_invoice_id=finding.related_invoice_id,
            attempted_file_hash=invoice.file_hash,
            match_type=finding.finding_type,
            confidence=evidence.get("confidence", confidence_by_type[finding.finding_type]),
            evidence=finding.evidence or "{}",
        ))

    # Persist all findings
    for finding in findings:
        db.add(finding)

    db.commit()
    return findings


def check_duplicate_hash(invoice: Invoice, db: Session) -> list[Finding]:
    """Check for exact file duplicates by SHA-256 hash."""
    findings = []

    duplicates = db.query(Invoice).filter(
        Invoice.file_hash == invoice.file_hash,
        Invoice.id != invoice.id,
        Invoice.workspace_id == invoice.workspace_id,
    ).all()

    for dup in duplicates:
        findings.append(Finding(
            invoice_id=invoice.id,
            related_invoice_id=dup.id,
            finding_type="duplicate_hash",
            severity="high",
            title="Exact Duplicate File Detected",
            description=(
                f"This file is an exact duplicate of invoice #{dup.id} "
                f"({dup.original_filename}). Both files have identical content (SHA-256 hash match)."
            ),
            affected_fields=json.dumps(["file_hash"]),
            evidence=json.dumps({
                "hash": invoice.file_hash,
                "matching_invoice_id": dup.id,
                "matching_filename": dup.original_filename,
                "match_type": "exact_file_hash",
            }),
        ))

    return findings


def check_duplicate_number(invoice: Invoice, db: Session) -> list[Finding]:
    """Check for same vendor + normalized invoice number."""
    findings = []

    if not invoice.invoice_number or not invoice.vendor_name:
        return findings

    normalized = normalize_invoice_number(invoice.invoice_number)
    if not normalized:
        return findings

    normalized_vendor = normalize_vendor_name(invoice.vendor_name)
    candidates = db.query(Invoice).filter(
        Invoice.id != invoice.id,
        Invoice.vendor_name.isnot(None),
        Invoice.invoice_number.isnot(None),
        Invoice.workspace_id == invoice.workspace_id,
    ).all()

    for candidate in candidates:
        if (candidate.vendor_name and
            normalize_vendor_name(candidate.vendor_name) == normalized_vendor and
            normalize_invoice_number(candidate.invoice_number) == normalized):

            findings.append(Finding(
                invoice_id=invoice.id,
                related_invoice_id=candidate.id,
                finding_type="duplicate_number",
                severity="high",
                title="Duplicate Invoice Number from Same Vendor",
                description=(
                    f"Invoice number '{invoice.invoice_number}' from vendor '{invoice.vendor_name}' "
                    f"matches invoice #{candidate.id} ('{candidate.invoice_number}' from '{candidate.vendor_name}'). "
                    "This may indicate a duplicate submission."
                ),
                affected_fields=json.dumps(["invoice_number", "vendor_name"]),
                evidence=json.dumps({
                    "this_invoice_number": invoice.invoice_number,
                    "matching_invoice_id": candidate.id,
                    "matching_invoice_number": candidate.invoice_number,
                    "vendor": invoice.vendor_name,
                    "match_type": "vendor_and_number",
                }),
            ))

    return findings


def check_potential_duplicates(invoice: Invoice, db: Session) -> list[Finding]:
    """Find explainable near-matches only when currency and multiple signals agree."""
    findings = []

    if not invoice.vendor_name or invoice.total_amount is None:
        return findings

    # Find invoices with same vendor and similar total
    candidates = db.query(Invoice).filter(
        Invoice.id != invoice.id,
        Invoice.vendor_name.isnot(None),
        Invoice.total_amount.isnot(None),
        Invoice.workspace_id == invoice.workspace_id,
    ).all()

    for candidate in candidates:
        if not candidate.vendor_name or candidate.total_amount is None:
            continue
        if (candidate.currency or "").strip().upper() != (invoice.currency or "").strip().upper():
            continue

        vendor_name = normalize_vendor_name(invoice.vendor_name) or ""
        candidate_vendor = normalize_vendor_name(candidate.vendor_name) or ""
        vendor_similarity = SequenceMatcher(None, vendor_name, candidate_vendor).ratio()
        if vendor_similarity < 0.85:
            continue

        amount = _decimal(invoice.total_amount)
        candidate_amount = _decimal(candidate.total_amount)
        amount_difference = abs(candidate_amount - amount)
        amount_tolerance = max(Decimal("0.01"), max(abs(amount), abs(candidate_amount)) * Decimal("0.02"))
        amount_match = amount_difference <= amount_tolerance
        if not amount_match:
            continue

        invoice_number = normalize_invoice_number(invoice.invoice_number)
        candidate_number = normalize_invoice_number(candidate.invoice_number)
        number_similarity = (
            SequenceMatcher(None, invoice_number, candidate_number).ratio()
            if invoice_number and candidate_number
            else 0.0
        )
        number_match = number_similarity >= 0.8

        date_match = False
        date_info = "dates not available for comparison"
        if invoice.invoice_date and candidate.invoice_date:
            day_diff = abs((invoice.invoice_date - candidate.invoice_date).days)
            date_match = day_diff <= 30
            date_info = f"{day_diff} days apart"
        elif invoice.invoice_date is not None or candidate.invoice_date is not None:
            date_info = "date available on only one invoice"

        if not date_match and not number_match:
            continue

        amount_similarity = 1 - float(amount_difference / max(abs(amount), abs(candidate_amount), Decimal("0.01")))
        confidence = round(
            vendor_similarity * 0.45
            + amount_similarity * 0.30
            + (0.15 if date_match else 0)
            + number_similarity * 0.10,
            2,
        )

        existing = db.query(Finding).filter(
            Finding.invoice_id == invoice.id,
            Finding.related_invoice_id == candidate.id,
            Finding.finding_type.in_(["duplicate_hash", "duplicate_number"]),
        ).first()

        if not existing:
            findings.append(Finding(
                invoice_id=invoice.id,
                related_invoice_id=candidate.id,
                finding_type="potential_duplicate",
                severity="medium",
                title="Potential Duplicate Invoice",
                description=(
                    f"This invoice from '{invoice.vendor_name}' for {invoice.total_amount} {invoice.currency} "
                    f"closely matches invoice #{candidate.id} from '{candidate.vendor_name}' "
                    f"for {candidate.total_amount} {candidate.currency} ({date_info}). "
                    "Please review whether this is a legitimate separate invoice."
                ),
                affected_fields=json.dumps(["vendor_name", "total_amount", "invoice_date", "currency"]),
                evidence=_dump_json({
                    "this_vendor": invoice.vendor_name,
                    "this_amount": invoice.total_amount,
                    "this_currency": invoice.currency,
                    "this_date": str(invoice.invoice_date) if invoice.invoice_date else None,
                    "matching_invoice_id": candidate.id,
                    "matching_vendor": candidate.vendor_name,
                    "matching_amount": candidate.total_amount,
                    "matching_currency": candidate.currency,
                    "matching_date": str(candidate.invoice_date) if candidate.invoice_date else None,
                    "date_proximity": date_info,
                    "vendor_similarity": round(vendor_similarity, 2),
                    "amount_difference": amount_difference,
                    "amount_tolerance": amount_tolerance,
                    "invoice_number_similarity": round(number_similarity, 2),
                    "confidence": confidence,
                    "match_type": "vendor_amount_date_number_currency",
                }),
            ))

    return findings


def check_arithmetic(
    invoice: Invoice, db: Session, tolerance: float = DEFAULT_ROUNDING_TOLERANCE
) -> list[Finding]:
    """Check arithmetic consistency of invoice amounts."""
    findings = []
    tolerance_amount = _decimal(tolerance)

    if (invoice.subtotal is not None and
        invoice.tax_amount is not None and
        invoice.total_amount is not None):

        subtotal = _decimal(invoice.subtotal)
        tax_amount = _decimal(invoice.tax_amount)
        discount_amount = _decimal(invoice.discount_amount or 0)
        total_amount = _decimal(invoice.total_amount)
        expected_total = subtotal + tax_amount - discount_amount
        diff = abs(expected_total - total_amount)

        if diff > tolerance_amount:
            affected_fields = ["subtotal", "tax_amount", "total_amount"]
            if discount_amount:
                affected_fields.append("discount_amount")
            findings.append(Finding(
                invoice_id=invoice.id,
                finding_type="arithmetic_error",
                severity="high",
                title="Invoice Total Does Not Match Its Components",
                description=(
                    f"Subtotal ({subtotal}) + Tax ({tax_amount}) - Discount ({discount_amount}) = "
                    f"{expected_total}, but the invoice total is {total_amount}. "
                    f"Difference: {diff:.2f} (tolerance: {tolerance_amount})."
                ),
                affected_fields=json.dumps(affected_fields),
                evidence=_dump_json({
                    "subtotal": subtotal,
                    "tax_amount": tax_amount,
                    "discount_amount": discount_amount,
                    "expected_total": _rounded(expected_total),
                    "actual_total": total_amount,
                    "difference": _rounded(diff),
                    "tolerance": tolerance_amount,
                }),
            ))

    # Check line item quantity * unit_price = amount
    line_items = db.query(LineItem).filter(LineItem.invoice_id == invoice.id).all()
    for item in line_items:
        if (item.quantity is not None and
            item.unit_price is not None and
            item.amount is not None):

            expected = _decimal(item.quantity) * _decimal(item.unit_price)
            actual_amount = _decimal(item.amount)
            diff = abs(expected - actual_amount)

            if diff > tolerance_amount:
                findings.append(Finding(
                    invoice_id=invoice.id,
                    finding_type="arithmetic_error",
                    severity="medium",
                    title=f"Line Item Calculation Mismatch: {item.description or 'Item'}",
                    description=(
                        f"Quantity ({item.quantity}) × Unit Price ({item.unit_price}) = "
                        f"{expected:.2f}, but line item amount is {actual_amount}. "
                        f"Difference: {diff:.2f}."
                    ),
                    affected_fields=json.dumps(["line_items"]),
                    evidence=_dump_json({
                        "line_item_id": item.id,
                        "description": item.description,
                        "quantity": item.quantity,
                        "unit_price": item.unit_price,
                        "expected_amount": _rounded(expected),
                        "actual_amount": actual_amount,
                        "difference": _rounded(diff),
                    }),
                ))

    # Check line items sum vs subtotal
    if line_items and invoice.subtotal is not None:
        items_with_amount = [i for i in line_items if i.amount is not None]
        if items_with_amount:
            items_sum = sum((_decimal(i.amount) for i in items_with_amount), Decimal("0"))
            subtotal = _decimal(invoice.subtotal)
            diff = abs(items_sum - subtotal)

            if diff > tolerance_amount:
                findings.append(Finding(
                    invoice_id=invoice.id,
                    finding_type="arithmetic_error",
                    severity="medium",
                    title="Line Items Sum Does Not Match Subtotal",
                    description=(
                        f"Sum of {len(items_with_amount)} line items = {items_sum:.2f}, "
                        f"but subtotal is {invoice.subtotal}. Difference: {diff:.2f}."
                    ),
                    affected_fields=json.dumps(["line_items", "subtotal"]),
                    evidence=_dump_json({
                        "line_items_count": len(items_with_amount),
                        "line_items_sum": _rounded(items_sum),
                        "subtotal": subtotal,
                        "difference": _rounded(diff),
                    }),
                ))

    return findings


def check_tax_calculation(invoice: Invoice, tolerance: float = DEFAULT_ROUNDING_TOLERANCE) -> list[Finding]:
    """Compare tax with an explicitly stated rate; never infer a tax rate."""
    if invoice.subtotal is None or invoice.tax_amount is None or invoice.tax_rate is None:
        return []

    subtotal = _decimal(invoice.subtotal)
    tax_amount = _decimal(invoice.tax_amount)
    tax_rate = _decimal(invoice.tax_rate)
    expected_tax = _rounded(subtotal * tax_rate / Decimal("100"))
    difference = abs(expected_tax - tax_amount)
    tolerance_amount = _decimal(tolerance)
    if difference <= tolerance_amount:
        return []

    return [Finding(
        invoice_id=invoice.id,
        finding_type="tax_calculation_mismatch",
        severity="medium",
        title="Tax Amount Differs from Stated Rate",
        description=(
            f"The stated tax rate ({tax_rate}%) applied to subtotal ({subtotal}) "
            f"gives {expected_tax:.2f}, but the recorded tax is {tax_amount:.2f}. "
            f"Difference: {difference:.2f}; review this potential discrepancy."
        ),
        suggested_action="Check the stated tax rate, taxable base, and tax amount against the source invoice.",
        affected_fields=json.dumps(["tax_rate", "subtotal", "tax_amount"]),
        evidence=_dump_json({
            "stated_tax_rate": tax_rate,
            "subtotal": subtotal,
            "expected_tax": expected_tax,
            "actual_tax": tax_amount,
            "difference": _rounded(difference),
            "tolerance": tolerance_amount,
        }),
    )]


def check_unusual_amounts(invoice: Invoice, db: Session) -> list[Finding]:
    """Flag large deviations from a vendor's own median after enough history exists."""
    if not invoice.vendor_name or invoice.total_amount is None or invoice.total_amount <= 0:
        return []

    prior_amounts = [
        amount
        for (amount,) in db.query(Invoice.total_amount).filter(
            Invoice.id != invoice.id,
            Invoice.workspace_id == invoice.workspace_id,
            func.lower(Invoice.vendor_name) == invoice.vendor_name.strip().lower(),
            Invoice.currency == invoice.currency,
            Invoice.total_amount.isnot(None),
            Invoice.total_amount > 0,
        ).all()
    ]
    if len(prior_amounts) < 3:
        return []

    baseline = _decimal(median(prior_amounts))
    ratio = _decimal(invoice.total_amount) / baseline
    if Decimal("0.2") < ratio < Decimal("5"):
        return []

    return [Finding(
        invoice_id=invoice.id,
        finding_type="unusual_amount",
        severity="medium",
        title="Invoice Amount Is Unusual for This Vendor",
        description=(
            f"This invoice total ({invoice.total_amount:.2f} {invoice.currency}) is "
            f"{ratio:.1f}× the vendor's median of {baseline:.2f} across "
            f"{len(prior_amounts)} earlier invoices. This is a review signal, not a fraud determination."
        ),
        suggested_action="Compare the amount with the invoice, contract, and prior invoices from this vendor.",
        affected_fields=json.dumps(["total_amount", "vendor_name", "currency"]),
        evidence=_dump_json({
            "invoice_total": invoice.total_amount,
            "vendor_median_total": baseline,
            "prior_invoice_count": len(prior_amounts),
            "ratio_to_median": round(ratio, 2),
            "review_thresholds": {"minimum_ratio": 0.2, "maximum_ratio": 5.0},
            "currency": invoice.currency,
        }),
    )]


def check_missing_fields(invoice: Invoice) -> list[Finding]:
    """Check for critical missing invoice fields."""
    findings = []

    critical_fields = {
        "vendor_name": "Vendor Name",
        "invoice_number": "Invoice Number",
        "invoice_date": "Invoice Date",
        "total_amount": "Total Amount",
    }

    important_fields = {
        "subtotal": "Subtotal",
        "tax_amount": "Tax Amount",
        "due_date": "Due Date",
    }

    missing_critical = []
    for field, label in critical_fields.items():
        if getattr(invoice, field, None) is None:
            missing_critical.append(label)

    missing_important = []
    for field, label in important_fields.items():
        if getattr(invoice, field, None) is None:
            missing_important.append(label)

    if missing_critical:
        findings.append(Finding(
            invoice_id=invoice.id,
            finding_type="missing_field",
            severity="high" if len(missing_critical) >= 2 else "medium",
            title=f"Missing Critical Fields: {', '.join(missing_critical)}",
            description=(
                f"The following critical invoice fields could not be extracted or are missing: "
                f"{', '.join(missing_critical)}. Please review and manually enter these values."
            ),
            affected_fields=json.dumps(list(critical_fields.keys())),
            evidence=json.dumps({
                "missing_fields": missing_critical,
                "severity_reason": "Critical fields are required for proper invoice tracking and audit.",
            }),
        ))

    if missing_important:
        findings.append(Finding(
            invoice_id=invoice.id,
            finding_type="missing_field",
            severity="low",
            title=f"Missing Fields: {', '.join(missing_important)}",
            description=(
                f"The following fields are not populated: {', '.join(missing_important)}. "
                f"While not critical, these fields improve audit accuracy."
            ),
            affected_fields=json.dumps(list(important_fields.keys())),
            evidence=json.dumps({
                "missing_fields": missing_important,
            }),
        ))

    return findings


def check_suspicious_amounts(invoice: Invoice) -> list[Finding]:
    """Check for suspicious monetary amounts."""
    findings = []

    # Negative total
    if invoice.total_amount is not None and invoice.total_amount < 0:
        findings.append(Finding(
            invoice_id=invoice.id,
            finding_type="suspicious_amount",
            severity="medium",
            title="Negative Invoice Total",
            description=(
                f"Invoice total is negative ({invoice.total_amount}). "
                "This may indicate a credit note or data entry error. Please verify."
            ),
            affected_fields=json.dumps(["total_amount"]),
            evidence=_dump_json({"total_amount": invoice.total_amount}),
        ))

    # Zero total with line items
    if invoice.total_amount is not None and invoice.total_amount == 0:
        findings.append(Finding(
            invoice_id=invoice.id,
            finding_type="suspicious_amount",
            severity="low",
            title="Zero Invoice Total",
            description=(
                "Invoice total is zero. This may be a proforma, draft, or data entry error."
            ),
            affected_fields=json.dumps(["total_amount"]),
            evidence=json.dumps({"total_amount": 0}),
        ))

    # Negative subtotal
    if invoice.subtotal is not None and invoice.subtotal < 0:
        findings.append(Finding(
            invoice_id=invoice.id,
            finding_type="suspicious_amount",
            severity="medium",
            title="Negative Subtotal",
            description=f"Subtotal is negative ({invoice.subtotal}). Please verify.",
            affected_fields=json.dumps(["subtotal"]),
            evidence=_dump_json({"subtotal": invoice.subtotal}),
        ))

    for field, label in (
        ("tax_amount", "Tax Amount"),
        ("discount_amount", "Discount Amount"),
    ):
        value = getattr(invoice, field, None)
        if value is not None and value < 0:
            findings.append(Finding(
                invoice_id=invoice.id,
                finding_type="suspicious_amount",
                severity="medium",
                title=f"Negative {label}",
                description=f"{label} is negative ({value}). Please verify the extracted value.",
                affected_fields=json.dumps([field]),
                evidence=_dump_json({field: value}),
            ))

    for item in getattr(invoice, "line_items", []):
        negative_fields = [
            field for field in ("quantity", "unit_price", "amount")
            if getattr(item, field, None) is not None and getattr(item, field) < 0
        ]
        if negative_fields:
            findings.append(Finding(
                invoice_id=invoice.id,
                finding_type="suspicious_amount",
                severity="medium",
                title=f"Negative Line Item Value: {item.description or 'Item'}",
                description=(
                    "A line item contains a negative quantity, unit price, or amount. "
                    "This may represent a credit adjustment or an extraction error; verify the source."
                ),
                affected_fields=json.dumps(["line_items"]),
                evidence=_dump_json({
                    "line_item_id": item.id,
                    "description": item.description,
                    "negative_fields": negative_fields,
                    "values": {field: getattr(item, field) for field in negative_fields},
                }),
            ))

    # Tax exceeds subtotal
    if (invoice.tax_amount is not None and invoice.subtotal is not None
            and invoice.subtotal > 0 and invoice.tax_amount > invoice.subtotal):
        findings.append(Finding(
            invoice_id=invoice.id,
            finding_type="suspicious_amount",
            severity="medium",
            title="Tax Amount Exceeds Subtotal",
            description=(
                f"Tax ({invoice.tax_amount}) is greater than subtotal ({invoice.subtotal}). "
                "This is unusual and may indicate a data entry error."
            ),
            affected_fields=json.dumps(["tax_amount", "subtotal"]),
            evidence=_dump_json({
                "tax_amount": invoice.tax_amount,
                "subtotal": invoice.subtotal,
            }),
        ))

    return findings


def check_gst_format(invoice: Invoice) -> list[Finding]:
    """Validate GSTIN format if present."""
    findings = []

    if not invoice.gstin:
        return findings

    gstin = invoice.gstin.strip().upper()

    # GSTIN format: 2-digit state code + 10-char PAN + 1 entity + Z + 1 check digit
    # Pattern: [0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]
    gstin_pattern = re.compile(r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]$')

    if not gstin_pattern.match(gstin):
        findings.append(Finding(
            invoice_id=invoice.id,
            finding_type="gst_format_error",
            severity="medium",
            title="Invalid GSTIN Format",
            description=(
                f"GSTIN '{gstin}' does not match the expected 15-character format. "
                "Expected pattern: 2-digit state code + 10-character PAN + entity number + 'Z' + check digit. "
                "Note: This check validates format only and does not verify GST registration status."
            ),
            affected_fields=json.dumps(["gstin"]),
            evidence=json.dumps({
                "gstin": gstin,
                "expected_format": "NNXXXXXNNNNX_Z_",
                "length": len(gstin),
                "note": "Format check only — does not verify registration, tax status, or compliance.",
            }),
        ))

    # Valid state codes (1-37 plus special)
    if gstin_pattern.match(gstin):
        state_code = int(gstin[:2])
        if state_code < 1 or state_code > 37:
            findings.append(Finding(
                invoice_id=invoice.id,
                finding_type="gst_format_error",
                severity="low",
                title="Unusual GSTIN State Code",
                description=(
                    f"GSTIN state code '{gstin[:2]}' is outside the standard range (01-37). "
                    "This may indicate an incorrect GSTIN."
                ),
                affected_fields=json.dumps(["gstin"]),
                evidence=json.dumps({
                    "gstin": gstin,
                    "state_code": gstin[:2],
                }),
            ))

    return findings
