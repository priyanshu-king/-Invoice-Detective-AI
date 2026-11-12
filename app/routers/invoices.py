import csv
import io
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.database import engine, get_db
from app.models import DuplicateDetection, Finding, Invoice, InvoiceActivity, LineItem
from app.schemas import InvoiceUpdate
from app.services.detection import run_all_checks
from app.services.extraction import extract_text_from_image, extract_text_from_pdf, parse_invoice_text
from app.services.po_comparison import compare_po_to_invoice
from app.schemas import DuplicateDetectionResponse, PurchaseOrderInput
from app.security import get_current_principal, get_current_workspace_id
from app.utils.csv_export import generate_invoice_report_csv, sanitize_csv_cell
from app.utils.file_handler import (
    compute_file_hash,
    delete_stored_file,
    generate_safe_filename,
    get_safe_file_path,
    validate_file,
)

router = APIRouter(tags=["invoices"], dependencies=[Depends(get_current_principal)])
health_router = APIRouter(tags=["health"])


def _api_number(value: Any) -> Optional[float]:
    return float(value) if value is not None else None


def _serialize_finding(finding: Finding) -> dict[str, Any]:
    return {
        "id": finding.id,
        "invoice_id": finding.invoice_id,
        "related_invoice_id": finding.related_invoice_id,
        "finding_type": finding.finding_type,
        "severity": finding.severity,
        "title": finding.title,
        "description": finding.description,
        "suggested_action": finding.suggested_action,
        "affected_fields": json.loads(finding.affected_fields) if finding.affected_fields else None,
        "evidence": json.loads(finding.evidence) if finding.evidence else None,
        "review_status": finding.review_status,
        "created_at": finding.created_at.isoformat(),
    }


def _record_invoice_activity(
    db: Session,
    invoice: Invoice,
    event_type: str,
    summary: str,
    changed_fields: list[str] | None = None,
) -> None:
    db.add(InvoiceActivity(
        workspace_id=invoice.workspace_id,
        invoice_id=invoice.id,
        event_type=event_type,
        summary=summary,
        changed_fields=json.dumps(changed_fields) if changed_fields else None,
    ))


def _serialize_invoice(invoice: Invoice) -> dict[str, Any]:
    line_items = [{
        "id": item.id,
        "invoice_id": item.invoice_id,
        "description": item.description,
        "quantity": _api_number(item.quantity),
        "unit_price": _api_number(item.unit_price),
        "amount": _api_number(item.amount),
        "item_order": item.item_order,
    } for item in (invoice.line_items or [])]

    findings = [_serialize_finding(item) for item in (invoice.findings or [])]

    return {
        "id": invoice.id,
        "vendor_name": invoice.vendor_name,
        "invoice_number": invoice.invoice_number,
        "invoice_date": invoice.invoice_date.isoformat() if invoice.invoice_date else None,
        "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
        "currency": invoice.currency,
        "subtotal": _api_number(invoice.subtotal),
        "tax_amount": _api_number(invoice.tax_amount),
        "tax_rate": _api_number(invoice.tax_rate),
        "total_amount": _api_number(invoice.total_amount),
        "discount_amount": _api_number(invoice.discount_amount),
        "vendor_address": invoice.vendor_address,
        "gstin": invoice.gstin,
        "raw_extracted_text": invoice.raw_extracted_text,
        "extraction_confidence": invoice.extraction_confidence,
        "extraction_method": invoice.extraction_method,
        "processing_status": invoice.processing_status,
        "processing_error": invoice.processing_error,
        "review_status": invoice.review_status,
        "is_confirmed": invoice.is_confirmed,
        "is_demo": invoice.is_demo,
        "notes": invoice.notes,
        "file_hash": invoice.file_hash,
        "original_filename": invoice.original_filename,
        "stored_filename": invoice.stored_filename,
        "file_size": invoice.file_size,
        "file_type": invoice.file_type,
        "created_at": invoice.created_at.isoformat(),
        "uploaded_at": invoice.created_at.isoformat(),
        "updated_at": invoice.updated_at.isoformat(),
        "line_items": line_items,
        "findings": findings,
    }


def _serialize_duplicate_detection(detection: DuplicateDetection) -> dict[str, Any]:
    return {
        "id": detection.id,
        "source_invoice_id": detection.source_invoice_id,
        "matched_invoice_id": detection.matched_invoice_id,
        "attempted_file_hash": detection.attempted_file_hash,
        "match_type": detection.match_type,
        "confidence": detection.confidence,
        "evidence": json.loads(detection.evidence),
        "created_at": detection.created_at.isoformat(),
    }


def _storage_directory_info(directory: Path) -> dict[str, Any]:
    resolved = directory.resolve()
    if not resolved.exists():
        return {
            "path": str(resolved),
            "status": "not_created",
            "file_count": 0,
            "size_bytes": 0,
            "error": None,
        }
    if not resolved.is_dir():
        return {
            "path": str(resolved),
            "status": "unavailable",
            "file_count": 0,
            "size_bytes": 0,
            "error": "Configured storage path is not a directory.",
        }

    file_count = 0
    size_bytes = 0
    try:
        for item in resolved.rglob("*"):
            if item.is_symlink() or not item.is_file():
                continue
            file_count += 1
            size_bytes += item.stat().st_size
    except OSError:
        return {
            "path": str(resolved),
            "status": "unavailable",
            "file_count": file_count,
            "size_bytes": size_bytes,
            "error": "The storage directory could not be fully inspected.",
        }

    return {
        "path": str(resolved),
        "status": "available",
        "file_count": file_count,
        "size_bytes": size_bytes,
        "error": None,
    }


@health_router.get("/health")
def health_check(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return {
        "status": "healthy",
        "version": "1.0.0-mvp",
        "environment": settings.APP_ENV,
        "database": "sqlite",
    }


@router.get("/findings")
def list_findings(
    invoice_id: Optional[int] = Query(default=None, ge=1),
    severity: Optional[str] = Query(default=None),
    review_status: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    workspace_id: int = Depends(get_current_workspace_id),
) -> dict:
    query = db.query(Finding).join(Invoice, Finding.invoice_id == Invoice.id).filter(
        Invoice.workspace_id == workspace_id
    )
    if invoice_id is not None:
        query = query.filter(Finding.invoice_id == invoice_id)
    if severity:
        query = query.filter(Finding.severity == severity)
    if review_status:
        query = query.filter(Finding.review_status == review_status)

    total = query.count()
    findings = query.order_by(Finding.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [_serialize_finding(finding) for finding in findings],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/invoices/{invoice_id}/findings")
def list_invoice_findings(
    invoice_id: int,
    db: Session = Depends(get_db),
    workspace_id: int = Depends(get_current_workspace_id),
) -> list[dict[str, Any]]:
    invoice_exists = db.query(Invoice.id).filter(
        Invoice.id == invoice_id,
        Invoice.workspace_id == workspace_id,
    ).first()
    if not invoice_exists:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    findings = db.query(Finding).filter(
        Finding.invoice_id == invoice_id,
        Finding.invoice.has(Invoice.workspace_id == workspace_id),
    ).order_by(Finding.created_at.desc()).all()
    return [_serialize_finding(finding) for finding in findings]


@router.get("/duplicate-detections", response_model=list[DuplicateDetectionResponse])
def list_duplicate_detections(
    invoice_id: Optional[int] = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    workspace_id: int = Depends(get_current_workspace_id),
) -> list[dict[str, Any]]:
    workspace_invoice_ids = db.query(Invoice.id).filter(Invoice.workspace_id == workspace_id)
    query = db.query(DuplicateDetection).filter(
        DuplicateDetection.matched_invoice_id.in_(workspace_invoice_ids),
        or_(
            DuplicateDetection.source_invoice_id.is_(None),
            DuplicateDetection.source_invoice_id.in_(workspace_invoice_ids),
        ),
    )
    if invoice_id is not None:
        query = query.filter(
            (DuplicateDetection.source_invoice_id == invoice_id)
            | (DuplicateDetection.matched_invoice_id == invoice_id)
        )
    detections = query.order_by(DuplicateDetection.created_at.desc()).limit(limit).all()
    return [_serialize_duplicate_detection(detection) for detection in detections]


@router.get("/dashboard")
def dashboard(
    db: Session = Depends(get_db),
    workspace_id: int = Depends(get_current_workspace_id),
) -> dict:
    workspace_invoices = Invoice.workspace_id == workspace_id
    total_invoices = db.query(func.count(Invoice.id)).filter(
        workspace_invoices
    ).scalar() or 0
    total_findings = db.query(func.count(Finding.id)).join(
        Invoice, Finding.invoice_id == Invoice.id
    ).filter(workspace_invoices).scalar() or 0
    status_breakdown = db.query(
        Invoice.review_status,
        func.count(Invoice.id),
    ).filter(workspace_invoices).group_by(Invoice.review_status).all()
    severity_breakdown = db.query(Finding.severity, func.count(Finding.id)).join(
        Invoice, Finding.invoice_id == Invoice.id
    ).filter(workspace_invoices).group_by(Finding.severity).all()
    type_breakdown = db.query(Finding.finding_type, func.count(Finding.id)).join(
        Invoice, Finding.invoice_id == Invoice.id
    ).filter(workspace_invoices).group_by(Finding.finding_type).all()
    recent_invoices = db.query(Invoice).filter(
        workspace_invoices
    ).order_by(Invoice.created_at.desc()).limit(5).all()

    invoice_value_by_currency = db.query(
        Invoice.currency,
        func.sum(Invoice.total_amount),
    ).filter(
        workspace_invoices,
        Invoice.total_amount.isnot(None),
    ).group_by(Invoice.currency).order_by(Invoice.currency).all()

    duplicate_invoice_ids = db.query(
        Finding.invoice_id.label("invoice_id")
    ).join(
        Invoice, Finding.invoice_id == Invoice.id
    ).filter(
        workspace_invoices,
        Finding.finding_type.in_(["duplicate_hash", "duplicate_number", "potential_duplicate"]),
    ).union(
        db.query(DuplicateDetection.matched_invoice_id.label("invoice_id")).join(
            Invoice, DuplicateDetection.matched_invoice_id == Invoice.id
        ).filter(workspace_invoices)
    ).subquery()
    potential_duplicate_value_by_currency = db.query(
        Invoice.currency,
        func.sum(Invoice.total_amount),
    ).filter(
        workspace_invoices,
        Invoice.total_amount.isnot(None),
        Invoice.id.in_(db.query(duplicate_invoice_ids.c.invoice_id)),
    ).group_by(Invoice.currency).order_by(Invoice.currency).all()

    twelve_months_ago = datetime.utcnow() - timedelta(days=365)
    month = func.strftime("%Y-%m", Invoice.created_at)
    invoice_volume_by_month = db.query(
        month.label("month"),
        func.count(Invoice.id),
    ).filter(
        workspace_invoices,
        Invoice.created_at >= twelve_months_ago,
    ).group_by(month).order_by(month).all()
    spend_by_month = db.query(
        month.label("month"),
        Invoice.currency,
        func.sum(Invoice.total_amount),
    ).filter(
        workspace_invoices,
        Invoice.created_at >= twelve_months_ago,
        Invoice.total_amount.isnot(None),
    ).group_by(month, Invoice.currency).order_by(month, Invoice.currency).all()
    vendor_spend = db.query(
        func.coalesce(Invoice.vendor_name, "Unknown vendor").label("vendor"),
        Invoice.currency,
        func.sum(Invoice.total_amount),
        func.count(Invoice.id),
    ).filter(
        workspace_invoices,
        Invoice.total_amount.isnot(None),
    ).group_by(
        func.coalesce(Invoice.vendor_name, "Unknown vendor"),
        Invoice.currency,
    ).order_by(
        func.sum(Invoice.total_amount).desc(),
        func.coalesce(Invoice.vendor_name, "Unknown vendor"),
    ).limit(10).all()

    return {
        "total_invoices": total_invoices,
        "total_findings": total_findings,
        "invoices_by_status": {key: value for key, value in status_breakdown},
        "findings_by_severity": {key: value for key, value in severity_breakdown},
        "findings_by_type": {key: value for key, value in type_breakdown},
        "invoice_value_by_currency": [
            {"currency": currency, "amount": float(amount)}
            for currency, amount in invoice_value_by_currency
        ],
        "potential_duplicate_value_by_currency": [
            {"currency": currency, "amount": float(amount)}
            for currency, amount in potential_duplicate_value_by_currency
        ],
        "invoice_volume_by_month": [
            {"month": month_value, "count": count}
            for month_value, count in invoice_volume_by_month
        ],
        "spend_by_month": [
            {"month": month_value, "currency": currency, "amount": float(amount)}
            for month_value, currency, amount in spend_by_month
        ],
        "vendor_spend": [
            {
                "vendor": vendor,
                "currency": currency,
                "amount": float(amount),
                "invoice_count": count,
            }
            for vendor, currency, amount, count in vendor_spend
        ],
        "recent_invoices": [_serialize_invoice(invoice) for invoice in recent_invoices],
    }


@router.get("/invoices")
def list_invoices(
    search: Optional[str] = Query(default=None),
    review_status: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    workspace_id: int = Depends(get_current_workspace_id),
) -> dict:
    query = db.query(Invoice).options(
        selectinload(Invoice.line_items), selectinload(Invoice.findings)
    ).filter(Invoice.workspace_id == workspace_id)

    if search:
        query = query.filter(
            or_(
                Invoice.vendor_name.ilike(f"%{search}%"),
                Invoice.invoice_number.ilike(f"%{search}%"),
                Invoice.original_filename.ilike(f"%{search}%"),
            )
        )

    if review_status:
        query = query.filter(Invoice.review_status == review_status)

    total = query.count()
    invoices = query.order_by(Invoice.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "items": [_serialize_invoice(invoice) for invoice in invoices],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/invoices/{invoice_id}")
def get_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    workspace_id: int = Depends(get_current_workspace_id),
) -> dict:
    invoice = db.query(Invoice).options(
        selectinload(Invoice.line_items), selectinload(Invoice.findings)
    ).filter(
        Invoice.id == invoice_id,
        Invoice.workspace_id == workspace_id,
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    return _serialize_invoice(invoice)


@router.get("/invoices/{invoice_id}/activity")
def get_invoice_activity(
    invoice_id: int,
    db: Session = Depends(get_db),
    workspace_id: int = Depends(get_current_workspace_id),
) -> dict:
    invoice_exists = db.query(Invoice.id).filter(
        Invoice.id == invoice_id,
        Invoice.workspace_id == workspace_id,
    ).first()
    if not invoice_exists:
        raise HTTPException(status_code=404, detail="Invoice not found.")

    entries = db.query(InvoiceActivity).filter(
        InvoiceActivity.invoice_id == invoice_id,
        InvoiceActivity.workspace_id == workspace_id,
    ).order_by(InvoiceActivity.created_at.desc(), InvoiceActivity.id.desc()).all()
    return {
        "items": [{
            "id": entry.id,
            "event_type": entry.event_type,
            "summary": entry.summary,
            "changed_fields": json.loads(entry.changed_fields) if entry.changed_fields else [],
            "created_at": entry.created_at.isoformat(),
        } for entry in entries],
    }


@router.get("/invoices/{invoice_id}/file")
def get_invoice_file(
    invoice_id: int,
    db: Session = Depends(get_db),
    workspace_id: int = Depends(get_current_workspace_id),
) -> FileResponse:
    invoice = db.query(Invoice.id, Invoice.stored_filename, Invoice.file_type).filter(
        Invoice.id == invoice_id,
        Invoice.workspace_id == workspace_id,
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found.")

    upload_dir = str(Path(settings.UPLOAD_DIR).resolve())
    file_path = get_safe_file_path(invoice.stored_filename, upload_dir)
    if file_path is None:
        raise HTTPException(status_code=404, detail="Invoice file not found.")

    media_types = {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
    }
    media_type = media_types.get(invoice.file_type.lower())
    if media_type is None:
        raise HTTPException(status_code=404, detail="Invoice file not found.")

    return FileResponse(
        file_path,
        media_type=media_type,
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": "inline",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.patch("/invoices/{invoice_id}")
def update_invoice(
    invoice_id: int,
    payload: InvoiceUpdate,
    db: Session = Depends(get_db),
    workspace_id: int = Depends(get_current_workspace_id),
) -> dict:
    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.workspace_id == workspace_id,
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found.")

    updates = payload.model_dump(exclude_unset=True)
    line_items = updates.pop("line_items", None)
    changed_fields = []
    for field, value in updates.items():
        if getattr(invoice, field) != value:
            changed_fields.append(field)
        setattr(invoice, field, value)

    if line_items is not None:
        changed_fields.append("line_items")
        db.query(LineItem).filter(LineItem.invoice_id == invoice_id).delete(synchronize_session=False)
        db.add_all(LineItem(invoice_id=invoice_id, **item) for item in line_items)

    if changed_fields:
        _record_invoice_activity(
            db, invoice, "invoice_updated", "Invoice details corrected", changed_fields
        )
    run_all_checks(invoice, db)
    db.commit()
    db.refresh(invoice)
    return _serialize_invoice(invoice)


@router.post("/invoices/{invoice_id}/reanalyse")
def reanalyse_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    workspace_id: int = Depends(get_current_workspace_id),
) -> dict:
    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.workspace_id == workspace_id,
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found.")

    findings = run_all_checks(invoice, db)
    db.refresh(invoice)
    return {
        "invoice_id": invoice.id,
        "finding_count": len(findings),
        "findings": [_serialize_finding(f) for f in findings],
    }


@router.post("/invoices/{invoice_id}/purchase-order/compare")
def compare_purchase_order(
    invoice_id: int,
    payload: PurchaseOrderInput,
    db: Session = Depends(get_db),
    workspace_id: int = Depends(get_current_workspace_id),
) -> dict:
    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.workspace_id == workspace_id,
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found.")

    comparison = compare_po_to_invoice(invoice, payload, db)
    return {
        "id": comparison.id,
        "invoice_id": comparison.invoice_id,
        "po_number": comparison.po_number,
        "po_vendor": comparison.po_vendor,
        "po_currency": comparison.po_currency,
        "po_total": _api_number(comparison.po_total),
        "po_line_items": json.loads(comparison.po_line_items) if comparison.po_line_items else [],
        "comparison_result": json.loads(comparison.comparison_result) if comparison.comparison_result else [],
        "created_at": comparison.created_at.isoformat(),
    }


@router.post("/invoices/{invoice_id}/findings/{finding_id}/review")
def review_finding(
    invoice_id: int,
    finding_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    workspace_id: int = Depends(get_current_workspace_id),
) -> dict:
    finding = db.query(Finding).filter(
        Finding.id == finding_id,
        Finding.invoice_id == invoice_id,
        Finding.invoice.has(Invoice.workspace_id == workspace_id),
    ).first()
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found.")

    review_status = payload.get("review_status")
    if review_status not in {"needs_review", "reviewed", "resolved"}:
        raise HTTPException(status_code=400, detail="Invalid review status.")

    if finding.review_status != review_status:
        _record_invoice_activity(
            db,
            finding.invoice,
            "finding_reviewed",
            f"Finding marked {review_status.replace('_', ' ')}",
            ["finding_review_status"],
        )
    finding.review_status = review_status
    db.commit()
    return _serialize_finding(finding)


@router.post("/invoices/upload")
async def upload_invoice(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    workspace_id: int = Depends(get_current_workspace_id),
) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required.")

    ext, file_bytes = await validate_file(file, settings.max_file_size_bytes)
    file_hash = compute_file_hash(file_bytes)

    existing_invoice = db.query(Invoice).filter(
        Invoice.file_hash == file_hash,
        Invoice.workspace_id == workspace_id,
    ).first()
    if existing_invoice:
        db.add(DuplicateDetection(
            matched_invoice_id=existing_invoice.id,
            attempted_file_hash=file_hash,
            match_type="exact_file_hash",
            confidence=1.0,
            evidence=json.dumps({
                "match_type": "exact_file_hash",
                "matched_invoice_id": existing_invoice.id,
            }),
        ))
        db.commit()
        raise HTTPException(status_code=409, detail="This exact file is a duplicate of an invoice already in storage.")

    upload_dir = Path(settings.UPLOAD_DIR).resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_filename = generate_safe_filename(file.filename)
    stored_path = upload_dir / stored_filename
    stored_path.write_bytes(file_bytes)

    try:
        if ext == ".pdf":
            extraction_result = await run_in_threadpool(
                extract_text_from_pdf, str(stored_path), settings.TESSERACT_PATH
            )
        else:
            extraction_result = await run_in_threadpool(
                extract_text_from_image, str(stored_path), settings.TESSERACT_PATH
            )

        extracted = parse_invoice_text(extraction_result.get("text", "") or "")
        invoice = Invoice(
            workspace_id=workspace_id,
            file_hash=file_hash,
            original_filename=file.filename,
            stored_filename=stored_filename,
            file_size=len(file_bytes),
            file_type=ext,
            vendor_name=extracted.get("vendor_name"),
            invoice_number=extracted.get("invoice_number"),
            invoice_date=date.fromisoformat(extracted["invoice_date"]) if extracted.get("invoice_date") else None,
            due_date=date.fromisoformat(extracted["due_date"]) if extracted.get("due_date") else None,
            currency=extracted.get("currency", "INR"),
            vendor_address=extracted.get("vendor_address"),
            subtotal=extracted.get("subtotal"),
            tax_amount=extracted.get("tax_amount"),
            tax_rate=extracted.get("tax_rate"),
            discount_amount=extracted.get("discount_amount"),
            total_amount=extracted.get("total_amount"),
            gstin=extracted.get("gstin"),
            raw_extracted_text=extraction_result.get("text"),
            extraction_confidence=extracted.get("confidence", "low"),
            extraction_method=extraction_result.get("method"),
            processing_status="failed" if extraction_result.get("error") else "completed",
            processing_error=extraction_result.get("error"),
            review_status="needs_review",
            notes=extraction_result.get("error"),
        )
        db.add(invoice)
        db.flush()
        _record_invoice_activity(db, invoice, "invoice_uploaded", "Invoice uploaded")

        for index, item in enumerate(extracted.get("line_items", [])):
            db.add(LineItem(
                invoice_id=invoice.id,
                description=item.get("description"),
                quantity=item.get("quantity"),
                unit_price=item.get("unit_price"),
                amount=item.get("amount"),
                item_order=index,
            ))

        run_all_checks(invoice, db)
        db.commit()
        db.refresh(invoice)
        return _serialize_invoice(invoice)
    except Exception:
        db.rollback()
        if stored_path.exists():
            stored_path.unlink(missing_ok=True)
        raise


@router.delete("/invoices/{invoice_id}")
def delete_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    workspace_id: int = Depends(get_current_workspace_id),
) -> dict:
    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.workspace_id == workspace_id,
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found.")

    workspace_invoice_ids = db.query(Invoice.id).filter(Invoice.workspace_id == workspace_id)
    db.query(Finding).filter(
        Finding.related_invoice_id == invoice_id,
        Finding.invoice_id.in_(workspace_invoice_ids),
    ).delete(synchronize_session=False)
    db.query(DuplicateDetection).filter(
        DuplicateDetection.matched_invoice_id.in_(workspace_invoice_ids),
        or_(
            DuplicateDetection.source_invoice_id == invoice_id,
            DuplicateDetection.matched_invoice_id == invoice_id,
        ),
    ).delete(synchronize_session=False)
    file_deleted = delete_stored_file(invoice.stored_filename, str(Path(settings.UPLOAD_DIR).resolve()))
    db.delete(invoice)
    db.commit()

    return {
        "deleted": True,
        "invoice_id": invoice_id,
        "file_removed": file_deleted,
    }


@router.get("/privacy/export/invoices.csv")
@router.get("/reports/csv")
def export_csv(
    db: Session = Depends(get_db),
    workspace_id: int = Depends(get_current_workspace_id),
) -> Any:
    invoices = db.query(Invoice).options(
        selectinload(Invoice.findings)
    ).filter(Invoice.workspace_id == workspace_id).order_by(Invoice.created_at.desc()).all()
    rows = [_serialize_invoice(invoice) for invoice in invoices]
    findings_by_invoice = {invoice.id: [_serialize_finding(f) for f in invoice.findings] for invoice in invoices}
    csv_bytes = generate_invoice_report_csv(rows, findings_by_invoice)
    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="invoice-report.csv"'},
    )


@router.get("/privacy/export/findings.csv")
def export_findings_csv(
    db: Session = Depends(get_db),
    workspace_id: int = Depends(get_current_workspace_id),
) -> StreamingResponse:
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    writer.writerow([
        "Finding ID",
        "Invoice ID",
        "Vendor",
        "Invoice Number",
        "Type",
        "Severity",
        "Title",
        "Description",
        "Review Status",
        "Created At",
    ])
    findings = db.query(
        Finding.id,
        Finding.invoice_id,
        Invoice.vendor_name,
        Invoice.invoice_number,
        Finding.finding_type,
        Finding.severity,
        Finding.title,
        Finding.description,
        Finding.review_status,
        Finding.created_at,
    ).join(Invoice, Invoice.id == Finding.invoice_id).filter(
        Invoice.workspace_id == workspace_id
    ).order_by(Finding.created_at.desc()).all()
    for finding in findings:
        writer.writerow([sanitize_csv_cell(value) for value in finding])
    csv_bytes = output.getvalue().encode("utf-8-sig")
    output.close()
    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="audit-findings.csv"'},
    )


@router.get("/privacy")
def privacy_details(
    db: Session = Depends(get_db),
    workspace_id: int = Depends(get_current_workspace_id),
) -> dict:
    database_path = engine.url.database
    database_file = (
        Path(database_path).resolve()
        if database_path and database_path != ":memory:"
        else None
    )
    database_info = {
        "path": str(database_file) if database_file else "in-memory SQLite database",
        "status": "in_memory" if database_file is None else "available" if database_file.is_file() else "not_created",
        "size_bytes": database_file.stat().st_size if database_file and database_file.is_file() else 0,
    }
    uploads = _storage_directory_info(Path(settings.UPLOAD_DIR))
    reports = _storage_directory_info(Path(settings.REPORT_DIR))
    total_invoices = db.query(func.count(Invoice.id)).filter(
        Invoice.workspace_id == workspace_id
    ).scalar() or 0
    total_findings = db.query(func.count(Finding.id)).join(
        Invoice, Invoice.id == Finding.invoice_id
    ).filter(Invoice.workspace_id == workspace_id).scalar() or 0
    return {
        "data_stored": [
            "local account and workspace metadata",
            "invoice metadata",
            "vendor and invoice numbers",
            "financial totals and line items",
            "audit findings",
            "stored document file",
        ],
        "file_types_accepted": [".pdf", ".jpg", ".jpeg", ".png"],
        "max_file_size_bytes": settings.max_file_size_bytes,
        "storage_location": (
            f"Database: {database_info['path']}; "
            f"uploads: {uploads['path']}; "
            f"reports: {reports['path']}"
        ),
        "data_retention": "Local SQLite database + local file storage for the current development environment only.",
        "third_party_sharing": "Invoice contents are not sent to an external AI service by this application.",
        "external_ai_services": "None configured. PDF extraction is local; image OCR uses local Tesseract only when installed and configured.",
        "database": database_info,
        "uploads": uploads,
        "reports": reports,
        "workspace_data": {
            "invoice_count": total_invoices,
            "finding_count": total_findings,
        },
        "authentication": {
            "required": True,
            "scope": "Authenticated workspace-scoped bearer sessions",
            "session_lifetime_hours": 12,
            "password_hashing": "scrypt",
            "rate_limiting_enabled": False,
            "email_verification_enabled": False,
        },
        "data_management": {
            "invoice_metadata_export": "/api/privacy/export/invoices.csv",
            "audit_findings_export": "/api/privacy/export/findings.csv",
            "invoice_deletion": "Deleting an invoice removes its linked database records and its stored document when present.",
        },
    }
