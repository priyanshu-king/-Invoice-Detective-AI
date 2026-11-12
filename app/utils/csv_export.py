"""
Invoice Detective AI — CSV Export Utility.

Generates CSV reports with proper escaping and formula injection protection.
"""

import csv
import io
from typing import Any


# Characters that could trigger formula execution in spreadsheet apps
FORMULA_TRIGGER_CHARS = {"=", "+", "-", "@", "\t", "\r"}


def sanitize_csv_cell(value: Any) -> str:
    """
    Sanitize a cell value to prevent CSV formula injection.

    Prefixes cells starting with dangerous characters with a single quote.
    """
    if value is None:
        return ""

    str_value = str(value)
    if not str_value:
        return ""

    if str_value[0] in FORMULA_TRIGGER_CHARS:
        return f"'{str_value}"

    return str_value


def generate_invoice_report_csv(
    invoices: list[dict], findings_map: dict[int, list[dict]]
) -> bytes:
    """
    Generate a CSV report of invoices and their findings.

    Args:
        invoices: List of invoice dicts.
        findings_map: Dict mapping invoice_id to list of finding dicts.

    Returns:
        UTF-8 encoded CSV bytes ready for streaming response.
    """
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)

    # Header row
    writer.writerow([
        "Invoice ID",
        "Vendor",
        "Invoice Number",
        "Invoice Date",
        "Subtotal",
        "Tax Amount",
        "Total Amount",
        "Currency",
        "Issue Types",
        "Severity",
        "Review Status",
        "Finding Details",
    ])

    for inv in invoices:
        inv_id = inv.get("id", "")
        inv_findings = findings_map.get(inv_id, [])

        if inv_findings:
            # One row per finding
            for finding in inv_findings:
                writer.writerow([
                    sanitize_csv_cell(inv_id),
                    sanitize_csv_cell(inv.get("vendor_name", "")),
                    sanitize_csv_cell(inv.get("invoice_number", "")),
                    sanitize_csv_cell(inv.get("invoice_date", "")),
                    sanitize_csv_cell(inv.get("subtotal", "")),
                    sanitize_csv_cell(inv.get("tax_amount", "")),
                    sanitize_csv_cell(inv.get("total_amount", "")),
                    sanitize_csv_cell(inv.get("currency", "")),
                    sanitize_csv_cell(finding.get("finding_type", "")),
                    sanitize_csv_cell(finding.get("severity", "")),
                    sanitize_csv_cell(inv.get("review_status", "")),
                    sanitize_csv_cell(finding.get("description", "")),
                ])
        else:
            # Invoice with no findings
            writer.writerow([
                sanitize_csv_cell(inv_id),
                sanitize_csv_cell(inv.get("vendor_name", "")),
                sanitize_csv_cell(inv.get("invoice_number", "")),
                sanitize_csv_cell(inv.get("invoice_date", "")),
                sanitize_csv_cell(inv.get("subtotal", "")),
                sanitize_csv_cell(inv.get("tax_amount", "")),
                sanitize_csv_cell(inv.get("total_amount", "")),
                sanitize_csv_cell(inv.get("currency", "")),
                sanitize_csv_cell(""),
                sanitize_csv_cell(""),
                sanitize_csv_cell(inv.get("review_status", "")),
                sanitize_csv_cell("No issues found"),
            ])

    content = output.getvalue()
    output.close()
    return content.encode("utf-8-sig")  # BOM for Excel compatibility
