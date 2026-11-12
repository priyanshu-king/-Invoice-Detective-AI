"""
Invoice Detective AI — Demo Data Seeder.

Creates labeled demo invoices and findings for initial app exploration.
All demo data is clearly marked with is_demo=True.
"""

import json
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session

from app.models import Invoice, LineItem, Finding


def seed_demo_data(db: Session) -> bool:
    """
    Seed demo data if none exists.

    Returns True if data was seeded, False if it already existed.
    """
    # Check if demo data already exists
    existing = db.query(Invoice).filter(Invoice.is_demo == True).first()
    if existing:
        return False

    today = date.today()

    # Demo invoices
    demos = [
        {
            "invoice": Invoice(
                file_hash="demo_hash_001_" + "a" * 50,
                original_filename="[DEMO] acme_corp_inv_1001.pdf",
                stored_filename="demo_acme_001.pdf",
                file_size=45000,
                file_type=".pdf",
                vendor_name="Acme Corporation",
                invoice_number="INV-1001",
                invoice_date=today - timedelta(days=15),
                due_date=today + timedelta(days=15),
                currency="INR",
                subtotal=10000.00,
                tax_amount=1800.00,
                total_amount=11800.00,
                gstin="27AABCA1234F1ZP",
                extraction_confidence="high",
                review_status="needs_review",
                is_confirmed=True,
                is_demo=True,
                notes="[DEMO DATA] Sample invoice from Acme Corporation.",
            ),
            "line_items": [
                LineItem(description="Widget A - Premium", quantity=10, unit_price=500.00, amount=5000.00, item_order=0),
                LineItem(description="Widget B - Standard", quantity=20, unit_price=250.00, amount=5000.00, item_order=1),
            ],
        },
        {
            "invoice": Invoice(
                file_hash="demo_hash_002_" + "b" * 50,
                original_filename="[DEMO] globex_inv_2023.pdf",
                stored_filename="demo_globex_002.pdf",
                file_size=32000,
                file_type=".pdf",
                vendor_name="Globex Industries",
                invoice_number="GLX-2023-045",
                invoice_date=today - timedelta(days=10),
                due_date=today + timedelta(days=20),
                currency="INR",
                subtotal=25000.00,
                tax_amount=4500.00,
                total_amount=30000.00,  # Intentional arithmetic error: 25000+4500=29500 != 30000
                gstin="29AABCG5678H1Z5",
                extraction_confidence="high",
                review_status="needs_review",
                is_confirmed=True,
                is_demo=True,
                notes="[DEMO DATA] This invoice has an intentional arithmetic discrepancy for demonstration.",
            ),
            "line_items": [
                LineItem(description="Consulting Service - Q4", quantity=1, unit_price=15000.00, amount=15000.00, item_order=0),
                LineItem(description="Software License", quantity=5, unit_price=2000.00, amount=10000.00, item_order=1),
            ],
        },
        {
            "invoice": Invoice(
                file_hash="demo_hash_003_" + "c" * 50,
                original_filename="[DEMO] acme_corp_inv_1001_dup.pdf",
                stored_filename="demo_acme_003.pdf",
                file_size=45000,
                file_type=".pdf",
                vendor_name="Acme Corporation",
                invoice_number="INV-1001",  # Same as first — duplicate number
                invoice_date=today - timedelta(days=15),
                due_date=today + timedelta(days=15),
                currency="INR",
                subtotal=10000.00,
                tax_amount=1800.00,
                total_amount=11800.00,
                gstin="27AABCA1234F1ZP",
                extraction_confidence="high",
                review_status="needs_review",
                is_confirmed=True,
                is_demo=True,
                notes="[DEMO DATA] Duplicate invoice number for demonstration.",
            ),
            "line_items": [
                LineItem(description="Widget A - Premium", quantity=10, unit_price=500.00, amount=5000.00, item_order=0),
                LineItem(description="Widget B - Standard", quantity=20, unit_price=250.00, amount=5000.00, item_order=1),
            ],
        },
        {
            "invoice": Invoice(
                file_hash="demo_hash_004_" + "d" * 50,
                original_filename="[DEMO] initech_inv_789.pdf",
                stored_filename="demo_initech_004.pdf",
                file_size=28000,
                file_type=".pdf",
                vendor_name="Initech Solutions",
                invoice_number="INT-789",
                invoice_date=today - timedelta(days=5),
                due_date=today + timedelta(days=25),
                currency="USD",
                subtotal=None,  # Missing subtotal
                tax_amount=None,  # Missing tax
                total_amount=5500.00,
                gstin=None,
                extraction_confidence="low",
                review_status="needs_review",
                is_confirmed=False,
                is_demo=True,
                notes="[DEMO DATA] Invoice with missing fields for demonstration.",
            ),
            "line_items": [],
        },
        {
            "invoice": Invoice(
                file_hash="demo_hash_005_" + "e" * 50,
                original_filename="[DEMO] stark_ind_inv_456.pdf",
                stored_filename="demo_stark_005.pdf",
                file_size=55000,
                file_type=".pdf",
                vendor_name="Stark Industries",
                invoice_number="SI-2023-456",
                invoice_date=today - timedelta(days=3),
                due_date=today + timedelta(days=27),
                currency="INR",
                subtotal=100000.00,
                tax_amount=18000.00,
                total_amount=118000.00,
                gstin="07AABCS1234M1Z",  # Invalid GSTIN (14 chars instead of 15)
                extraction_confidence="medium",
                review_status="reviewed",
                is_confirmed=True,
                is_demo=True,
                notes="[DEMO DATA] Invoice with invalid GSTIN format for demonstration.",
            ),
            "line_items": [
                LineItem(description="Arc Reactor Component", quantity=2, unit_price=40000.00, amount=80000.00, item_order=0),
                LineItem(description="Vibranium Alloy Plate", quantity=1, unit_price=20000.00, amount=20000.00, item_order=1),
            ],
        },
    ]

    # Insert demo data
    for demo in demos:
        inv = demo["invoice"]
        db.add(inv)
        db.flush()

        for item in demo["line_items"]:
            item.invoice_id = inv.id
            db.add(item)

    db.commit()

    # Now create findings for demo invoices
    _create_demo_findings(db)

    return True


def _create_demo_findings(db: Session):
    """Create findings for demo invoices by running detection logic."""
    from app.services.detection import run_all_checks

    demo_invoices = db.query(Invoice).filter(Invoice.is_demo == True).all()
    for inv in demo_invoices:
        run_all_checks(inv, db)
