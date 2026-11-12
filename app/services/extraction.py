"""
Invoice Detective AI — Invoice Data Extraction Service.

Extracts structured data from PDFs and images using PyMuPDF and optional OCR.
"""

import re
import shutil
from decimal import Decimal, InvalidOperation
from io import BytesIO
from datetime import datetime
from typing import Optional
from pathlib import Path

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    from PIL import Image
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False


def extract_text_from_pdf(file_path: str, tesseract_path: Optional[str] = None) -> dict:
    """
    Extract text from a PDF file using PyMuPDF.

    Returns:
        Dict with 'text', 'page_count', 'method', 'error'.
    """
    if not PYMUPDF_AVAILABLE:
        return {
            "text": "",
            "page_count": 0,
            "method": "none",
            "error": "PyMuPDF is not installed. Cannot extract text from PDFs.",
        }

    try:
        with fitz.open(file_path) as doc:
            if doc.needs_pass:
                return {
                    "text": "",
                    "page_count": doc.page_count,
                    "method": "pymupdf",
                    "error": "PDF is encrypted or password-protected. Password entry is not supported.",
                }
            text_parts = [page.get_text() for page in doc]
            page_count = doc.page_count

        full_text = "\n".join(text_parts).strip()
        if not full_text:
            resolved_path = _resolve_tesseract_path(tesseract_path)
            if resolved_path and PILLOW_AVAILABLE:
                try:
                    import pytesseract
                    pytesseract.pytesseract.tesseract_cmd = resolved_path
                    with fitz.open(file_path) as doc:
                        ocr_parts = []
                        for page in doc:
                            image_bytes = page.get_pixmap(matrix=fitz.Matrix(2, 2)).tobytes("png")
                            with Image.open(BytesIO(image_bytes)) as image:
                                ocr_parts.append(pytesseract.image_to_string(image))
                    full_text = "\n".join(ocr_parts).strip()
                    if full_text:
                        return {
                            "text": full_text,
                            "page_count": page_count,
                            "method": "pymupdf+tesseract",
                            "error": None,
                        }
                except Exception as e:
                    return {
                        "text": "",
                        "page_count": page_count,
                        "method": "pymupdf+tesseract",
                        "error": f"Local OCR failed ({type(e).__name__}). Check the Tesseract installation.",
                    }
            return {
                "text": "",
                "page_count": page_count,
                "method": "pymupdf",
                "error": (
                    "No text could be extracted. The PDF may be scanned/image-based. "
                    "Configure local Tesseract OCR to process scanned PDFs."
                ),
            }

        return {
            "text": full_text,
            "page_count": len(text_parts),
            "method": "pymupdf",
            "error": None,
        }
    except Exception as e:
        return {
            "text": "",
            "page_count": 0,
            "method": "pymupdf",
            "error": f"Failed to read PDF: {type(e).__name__}",
        }


def _resolve_tesseract_path(configured_path: Optional[str]) -> Optional[str]:
    if configured_path:
        candidate = Path(configured_path)
        if candidate.is_file():
            return str(candidate)
        resolved = shutil.which(configured_path)
        if resolved:
            return resolved
        return configured_path
    return shutil.which("tesseract")


def extract_text_from_image(file_path: str, tesseract_path: Optional[str] = None) -> dict:
    """
    Extract text from an image file using OCR (Tesseract) if available.

    Returns:
        Dict with 'text', 'method', 'error'.
    """
    resolved_path = _resolve_tesseract_path(tesseract_path)
    if not resolved_path:
        return {
            "text": "",
            "method": "none",
            "error": "OCR is not configured. Set TESSERACT_PATH in .env to enable text extraction from images.",
        }
    if not PILLOW_AVAILABLE:
        return {
            "text": "",
            "method": "none",
            "error": "Pillow is not installed. Cannot prepare the image for OCR.",
        }
    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = resolved_path
        with Image.open(file_path) as image:
            image.load()
            text = pytesseract.image_to_string(image)
        return {
            "text": text.strip(),
            "method": "tesseract",
            "error": None if text.strip() else "OCR produced no text from the image.",
        }
    except Exception as e:
        return {
            "text": "",
            "method": "tesseract",
            "error": f"OCR failed ({type(e).__name__}). Check the Tesseract installation and configured path.",
        }


def parse_invoice_text(text: str) -> dict:
    """
    Parse extracted text to identify invoice fields.

    Uses regex patterns to find common invoice data.
    Never invents values — returns None for anything not confidently found.

    Returns:
        Dict with extracted field values and confidence notes.
    """
    if not text or not text.strip():
        return {
            "vendor_name": None,
            "invoice_number": None,
            "invoice_date": None,
            "due_date": None,
            "currency": "INR",
            "subtotal": None,
            "tax_amount": None,
            "tax_rate": None,
            "discount_amount": None,
            "total_amount": None,
            "vendor_address": None,
            "gstin": None,
            "line_items": [],
            "confidence": "none",
            "extraction_notes": ["No text available for parsing."],
        }

    result = {
        "vendor_name": None,
        "invoice_number": None,
        "invoice_date": None,
        "due_date": None,
        "currency": "INR",
        "subtotal": None,
        "tax_amount": None,
        "tax_rate": None,
        "discount_amount": None,
        "total_amount": None,
        "vendor_address": None,
        "gstin": None,
        "line_items": [],
        "confidence": "low",
        "extraction_notes": [],
    }

    # --- Invoice Number ---
    inv_num_patterns = [
        r'(?:Invoice\s*(?:#|No\.?|Number)\s*[:\-]?\s*)([A-Za-z0-9\-\/]+)',
        r'(?:Inv\s*[#\-:]\s*)([A-Za-z0-9\-\/]+)',
        r'(?:Bill\s*(?:#|No\.?)\s*[:\-]?\s*)([A-Za-z0-9\-\/]+)',
        r'(?:Receipt\s*(?:#|No\.?)\s*[:\-]?\s*)([A-Za-z0-9\-\/]+)',
    ]
    for pattern in inv_num_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["invoice_number"] = match.group(1).strip()
            break

    # --- Dates ---
    date_patterns = [
        r'(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})',
        r'(\d{4}[\/\-\.]\d{1,2}[\/\-\.]\d{1,2})',
        r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{2,4})',
        r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{2,4})',
    ]

    # Try to find Invoice Date
    inv_date_match = re.search(
        r'(?:Invoice\s*Date|Date\s*of\s*Invoice|Dated?)\s*[:\-]?\s*' +
        r'(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}|\d{4}[\/\-\.]\d{1,2}[\/\-\.]\d{1,2}|\d{1,2}\s+\w+\s+\d{2,4})',
        text, re.IGNORECASE
    )
    if inv_date_match:
        result["invoice_date"] = _parse_date(inv_date_match.group(1))

    # Try to find Due Date
    due_date_match = re.search(
        r'(?:Due\s*Date|Payment\s*Due|Due\s*By)\s*[:\-]?\s*' +
        r'(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}|\d{4}[\/\-\.]\d{1,2}[\/\-\.]\d{1,2}|\d{1,2}\s+\w+\s+\d{2,4})',
        text, re.IGNORECASE
    )
    if due_date_match:
        result["due_date"] = _parse_date(due_date_match.group(1))

    # If no specific invoice date found, take first date in text
    if result["invoice_date"] is None:
        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result["invoice_date"] = _parse_date(match.group(1))
                if result["invoice_date"]:
                    result["extraction_notes"].append("Invoice date was inferred from first date found in text.")
                    break

    # --- Vendor Name ---
    vendor_patterns = [
        r'(?:From|Seller|Vendor|Company|Billed\s*By|Supplier)\s*[:\-]?\s*(.+?)(?:\n|$)',
    ]
    for pattern in vendor_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            vendor = match.group(1).strip()
            if vendor and len(vendor) > 1 and len(vendor) < 200:
                result["vendor_name"] = vendor
                break

    # If no vendor from label, try first non-empty line (often company name)
    if result["vendor_name"] is None:
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if lines:
            first_line = lines[0]
            # Only if it looks like a name (not a number, date, or keyword)
            if (len(first_line) > 2 and len(first_line) < 100
                    and not re.match(r'^[\d\.\-\/]+$', first_line)
                    and not re.match(r'^(invoice|bill|receipt|tax|date|to|from)', first_line, re.IGNORECASE)):
                result["vendor_name"] = first_line
                result["extraction_notes"].append("Vendor name inferred from first line of document.")

    address_match = re.search(
        r"(?:Vendor|Supplier|Company)?\s*Address\s*[:\-]\s*([^\r\n]{3,500})",
        text,
        re.IGNORECASE,
    )
    if address_match:
        result["vendor_address"] = address_match.group(1).strip()

    # --- GSTIN ---
    gstin_match = re.search(
        r'(?:GSTIN|GST\s*(?:No|Number|IN)\.?)\s*[:\-]?\s*([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z][Z][0-9A-Z])',
        text, re.IGNORECASE
    )
    if gstin_match:
        result["gstin"] = gstin_match.group(1).upper()
    else:
        # Try standalone GSTIN pattern
        gstin_standalone = re.search(
            r'\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z])\b',
            text
        )
        if gstin_standalone:
            result["gstin"] = gstin_standalone.group(1)

    # --- Amounts ---
    # Currency detection
    if re.search(r'[$]|USD|US\s*Dollar', text, re.IGNORECASE):
        result["currency"] = "USD"
    elif re.search(r'[€]|EUR', text, re.IGNORECASE):
        result["currency"] = "EUR"
    elif re.search(r'[£]|GBP', text, re.IGNORECASE):
        result["currency"] = "GBP"
    elif re.search(r'[₹]|INR|Rs\.?', text, re.IGNORECASE):
        result["currency"] = "INR"

    # Amount extraction
    amount_pattern = r'[\(\-+]?\s*[\d,]+(?:\.\d+)?\s*\)?'

    # Total
    total_patterns = [
        r'(?:Grand\s*Total|\bTotal\s*(?:Amount|Due|Payable)\b)\s*[:\-]?\s*[\$€£₹]?\s*(' + amount_pattern + ')',
        r'(?:\bAmount\s*(?:Due|Payable)\b)\s*[:\-]?\s*[\$€£₹]?\s*(' + amount_pattern + ')',
        r'(?:\bTotal\b)\s*[:\-]?\s*[\$€£₹]?\s*(' + amount_pattern + ')',
    ]
    for pattern in total_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["total_amount"] = _parse_amount(match.group(1))
            break

    # Subtotal
    subtotal_patterns = [
        r'(?:\bSub\s*Total\b|\bSubtotal\b)\s*[:\-]?\s*[\$€£₹]?\s*(' + amount_pattern + ')',
        r'(?:\bNet\s*Amount\b)\s*[:\-]?\s*[\$€£₹]?\s*(' + amount_pattern + ')',
    ]
    for pattern in subtotal_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["subtotal"] = _parse_amount(match.group(1))
            break

    discount_match = re.search(
        r"\b(?:Discount|Less\s*:\s*Discount)\b\s*[:\-]?\s*[\$€£₹]?\s*(" + amount_pattern + r")",
        text,
        re.IGNORECASE,
    )
    if discount_match:
        result["discount_amount"] = _parse_amount(discount_match.group(1))

    # Tax
    component_amounts = {}
    for label in ("CGST", "SGST"):
        for line in text.splitlines():
            if re.search(rf"\b{label}\b", line, re.IGNORECASE):
                matches = re.findall(r"(?<![\d.])(\d[\d,]*(?:\.\d{1,2})?)(?![\d.]|\s*%)", line)
                if matches:
                    component_amounts[label] = _parse_amount(matches[-1])
                    break

    if component_amounts.get("CGST") is not None and component_amounts.get("SGST") is not None:
        result["tax_amount"] = component_amounts["CGST"] + component_amounts["SGST"]
    else:
        tax_patterns = [
            r'(?:\bTotal\s+Tax\b|\bTax\b|\bGST\b|\bVAT\b|\bIGST\b)\s*(?:\(\d+(?:\.\d+)?%?\))?\s*[:\-]?\s*[\$€£₹]?\s*(' + amount_pattern + ')',
        ]
        for pattern in tax_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result["tax_amount"] = _parse_amount(match.group(1))
                break

    cgst_rate = re.search(r"\bCGST\b\s*(?:\(\s*)?(\d{1,2}(?:\.\d+)?)\s*%\s*\)?", text, re.IGNORECASE)
    sgst_rate = re.search(r"\bSGST\b\s*(?:\(\s*)?(\d{1,2}(?:\.\d+)?)\s*%\s*\)?", text, re.IGNORECASE)
    if cgst_rate and sgst_rate:
        result["tax_rate"] = Decimal(cgst_rate.group(1)) + Decimal(sgst_rate.group(1))
    else:
        tax_rate_match = re.search(
            r"\b(?:IGST|GST|VAT|Tax(?:\s+Rate)?)\b\s*:?\s*(?:\(\s*|@\s*)?(\d{1,2}(?:\.\d+)?)\s*%\s*\)?",
            text,
            re.IGNORECASE,
        )
        if tax_rate_match:
            result["tax_rate"] = Decimal(tax_rate_match.group(1))

    # --- Line Items ---
    result["line_items"] = _extract_line_items(text)

    # --- Confidence Assessment ---
    fields_found = sum(1 for k in ["vendor_name", "invoice_number", "invoice_date", "total_amount"]
                       if result.get(k) is not None)
    if fields_found >= 3:
        result["confidence"] = "high"
    elif fields_found >= 2:
        result["confidence"] = "medium"
    else:
        result["confidence"] = "low"

    return result


def _parse_date(date_str: str) -> Optional[str]:
    """Attempt to parse various date formats. Returns ISO date string or None."""
    if not date_str:
        return None

    date_str = date_str.strip()
    formats = [
        "%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d", "%d-%m-%Y",
        "%d.%m.%Y", "%Y/%m/%d", "%d %B %Y", "%d %b %Y",
        "%B %d, %Y", "%b %d, %Y", "%d/%m/%y", "%m/%d/%y",
        "%B %d %Y", "%b %d %Y",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            # Sanity check: year should be reasonable
            if 1990 <= dt.year <= 2099:
                return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return None


def _parse_amount(amount_str: str) -> Optional[Decimal]:
    """Parse a monetary amount string without introducing binary float rounding."""
    if not amount_str:
        return None

    try:
        # Remove commas and spaces
        cleaned = amount_str.replace(",", "").replace(" ", "").strip()
        if cleaned.startswith("(") and cleaned.endswith(")"):
            cleaned = "-" + cleaned[1:-1]
        return Decimal(cleaned)
    except (InvalidOperation, ValueError, TypeError):
        return None


def _extract_line_items(text: str) -> list[dict]:
    """
    Try to extract line items from invoice text.

    Looks for patterns like: Description  Qty  Rate  Amount
    """
    line_items = []

    # Common line item pattern: description, number, number, number on same line
    # e.g., "Widget A    2    10.00    20.00"
    line_pattern = re.compile(
        r'^(.{3,50}?)\s+(-?\d+(?:\.\d+)?)\s+(-?[\d,]+(?:\.\d+)?)\s+(-?[\d,]+(?:\.\d+)?)\s*$',
        re.MULTILINE
    )

    for i, match in enumerate(line_pattern.finditer(text)):
        desc = match.group(1).strip()
        # Skip header-like rows
        if re.match(r'^(description|item|product|service|particular|s\.?\s*no|sr)', desc, re.IGNORECASE):
            continue

        qty = _parse_amount(match.group(2))
        unit_price = _parse_amount(match.group(3))
        amount = _parse_amount(match.group(4))

        if desc and (qty is not None or amount is not None):
            line_items.append({
                "description": desc,
                "quantity": qty,
                "unit_price": unit_price,
                "amount": amount,
                "item_order": i,
            })

    return line_items


def extract_invoice_data(file_path: str, file_type: str, tesseract_path: Optional[str] = None) -> dict:
    """
    Main extraction entry point. Routes to appropriate extractor based on file type.

    Returns:
        Dict with all extracted fields and metadata.
    """
    if file_type == ".pdf":
        extraction = extract_text_from_pdf(file_path, tesseract_path)
    elif file_type in (".jpg", ".jpeg", ".png"):
        extraction = extract_text_from_image(file_path, tesseract_path)
    else:
        return {
            "raw_text": "",
            "extraction_error": f"Unsupported file type: {file_type}",
            "parsed": parse_invoice_text(""),
        }

    parsed = parse_invoice_text(extraction.get("text", ""))

    return {
        "raw_text": extraction.get("text", ""),
        "extraction_method": extraction.get("method", "none"),
        "extraction_error": extraction.get("error"),
        "page_count": extraction.get("page_count", 0),
        "processing_status": "failed" if extraction.get("error") else "completed",
        "parsed": parsed,
    }
