"""Workspace-scoped purchase order management and invoice comparison."""

import json
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Invoice, PurchaseOrder, PurchaseOrderLineItem
from app.schemas import POLineItem, PurchaseOrderInput, PurchaseOrderWrite
from app.security import AuthenticatedPrincipal, get_current_principal
from app.services.po_comparison import compare_po_to_invoice


router = APIRouter(prefix="/purchase-orders", tags=["purchase-orders"])


def _serialize_purchase_order(order: PurchaseOrder) -> dict[str, Any]:
    subtotal = sum((Decimal(str(item.amount)) for item in order.line_items), Decimal("0.0000"))
    tax_amount = (subtotal * Decimal(str(order.tax_rate or 0)) / Decimal("100")).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )
    return {
        "id": order.id,
        "po_number": order.po_number,
        "vendor_name": order.vendor_name,
        "currency": order.currency,
        "subtotal": float(subtotal),
        "tax_rate": float(order.tax_rate),
        "tax_amount": float(tax_amount),
        "total_amount": float(order.total_amount),
        "order_date": order.order_date.isoformat() if order.order_date else None,
        "expected_delivery_date": (
            order.expected_delivery_date.isoformat() if order.expected_delivery_date else None
        ),
        "status": order.status,
        "line_items": [
            {
                "id": item.id,
                "description": item.description,
                "quantity": float(item.quantity),
                "unit_price": float(item.unit_price),
                "amount": float(item.amount),
                "item_order": item.item_order,
            }
            for item in order.line_items
        ],
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat(),
    }


def _replace_line_items(order: PurchaseOrder, payload: PurchaseOrderWrite) -> None:
    order.line_items.clear()
    total = Decimal("0.0000")
    for index, item in enumerate(payload.line_items):
        amount = Decimal(str(item.quantity)) * Decimal(str(item.unit_price))
        amount = amount.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        total += amount
        order.line_items.append(PurchaseOrderLineItem(
            description=item.description,
            quantity=item.quantity,
            unit_price=item.unit_price,
            amount=amount,
            item_order=index,
        ))
    subtotal = total.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    tax_amount = (
        subtotal * Decimal(str(order.tax_rate or 0)) / Decimal("100")
    ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    order.total_amount = subtotal + tax_amount


def _get_purchase_order(db: Session, workspace_id: int, purchase_order_id: int) -> PurchaseOrder:
    order = (
        db.query(PurchaseOrder)
        .options(selectinload(PurchaseOrder.line_items))
        .filter(
            PurchaseOrder.id == purchase_order_id,
            PurchaseOrder.workspace_id == workspace_id,
        )
        .first()
    )
    if order is None:
        raise HTTPException(status_code=404, detail="Purchase order not found.")
    return order


@router.get("")
def list_purchase_orders(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    orders = (
        db.query(PurchaseOrder)
        .options(selectinload(PurchaseOrder.line_items))
        .filter(PurchaseOrder.workspace_id == principal.workspace_id)
        .order_by(PurchaseOrder.created_at.desc(), PurchaseOrder.id.desc())
        .all()
    )
    return [_serialize_purchase_order(order) for order in orders]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_purchase_order(
    payload: PurchaseOrderWrite,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    order = PurchaseOrder(
        workspace_id=principal.workspace_id,
        po_number=payload.po_number,
        vendor_name=payload.vendor_name,
        currency=payload.currency,
        order_date=payload.order_date,
        expected_delivery_date=payload.expected_delivery_date,
        tax_rate=payload.tax_rate,
        status=payload.status,
    )
    _replace_line_items(order, payload)
    db.add(order)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A purchase order with this number already exists in this workspace.",
        ) from error
    db.refresh(order)
    return _serialize_purchase_order(order)


@router.get("/{purchase_order_id}")
def get_purchase_order(
    purchase_order_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return _serialize_purchase_order(
        _get_purchase_order(db, principal.workspace_id, purchase_order_id)
    )


@router.put("/{purchase_order_id}")
def update_purchase_order(
    purchase_order_id: int,
    payload: PurchaseOrderWrite,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    order = _get_purchase_order(db, principal.workspace_id, purchase_order_id)
    order.po_number = payload.po_number
    order.vendor_name = payload.vendor_name
    order.currency = payload.currency
    order.order_date = payload.order_date
    order.expected_delivery_date = payload.expected_delivery_date
    order.tax_rate = payload.tax_rate
    order.status = payload.status
    _replace_line_items(order, payload)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A purchase order with this number already exists in this workspace.",
        ) from error
    db.refresh(order)
    return _serialize_purchase_order(order)


@router.delete("/{purchase_order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_purchase_order(
    purchase_order_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> Response:
    order = _get_purchase_order(db, principal.workspace_id, purchase_order_id)
    db.delete(order)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{purchase_order_id}/invoices/{invoice_id}/compare")
def compare_saved_purchase_order(
    purchase_order_id: int,
    invoice_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    order = _get_purchase_order(db, principal.workspace_id, purchase_order_id)
    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.workspace_id == principal.workspace_id,
    ).first()
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found.")

    comparison = compare_po_to_invoice(
        invoice,
        PurchaseOrderInput(
            po_number=order.po_number,
            po_vendor=order.vendor_name,
            po_currency=order.currency,
            po_total=order.total_amount,
            po_line_items=[
                POLineItem(
                    description=item.description,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    amount=item.amount,
                )
                for item in order.line_items
            ],
        ),
        db,
    )
    return {
        "id": comparison.id,
        "invoice_id": comparison.invoice_id,
        "po_number": comparison.po_number,
        "po_vendor": comparison.po_vendor,
        "po_currency": comparison.po_currency,
        "po_total": float(comparison.po_total) if comparison.po_total is not None else None,
        "po_line_items": json.loads(comparison.po_line_items) if comparison.po_line_items else [],
        "comparison_result": (
            json.loads(comparison.comparison_result) if comparison.comparison_result else []
        ),
        "created_at": comparison.created_at.isoformat(),
    }
