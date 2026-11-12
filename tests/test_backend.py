import json
import io
from datetime import date
from decimal import Decimal
from pathlib import Path

import fitz
import pytest
from PIL import Image
from sqlalchemy import create_engine, inspect, text
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, _connect_args, get_db
from app.main import app
from app.models import DuplicateDetection, Finding, Invoice, LineItem
from app.security import require_loopback_auth_request
from app.services.detection import (
    check_arithmetic,
    check_duplicate_number,
    check_potential_duplicates,
    normalize_invoice_number,
    run_all_checks,
)
from app.services.extraction import extract_text_from_image, extract_text_from_pdf, parse_invoice_text
from app.utils.csv_export import generate_invoice_report_csv
from app.utils.file_handler import delete_stored_file, validate_file


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


class DummyUpload:
    def __init__(self, filename, content_type, payload):
        self.filename = filename
        self.content_type = content_type
        self._payload = payload

    async def read(self):
        return self._payload


@pytest.mark.asyncio
async def test_validate_file_rejects_unsupported_type():
    fake = DummyUpload("bad.txt", "text/plain", b"hello")
    with pytest.raises(Exception):
        await validate_file(fake, 10 * 1024 * 1024)


def test_parse_invoice_text_extracts_fields():
    sample = """
    Acme Solutions Pvt Ltd
    Invoice # INV-1024
    Invoice Date: 2024-08-18
    Due Date: 2024-09-02
    GSTIN: 27AABCA1234F1ZP
    Subtotal: 1500.00
    Tax: 270.00
    Total: 1770.00
    """
    parsed = parse_invoice_text(sample)
    assert parsed["vendor_name"] == "Acme Solutions Pvt Ltd"
    assert parsed["invoice_number"] == "INV-1024"
    assert parsed["total_amount"] == 1770.0
    assert parsed["gstin"] == "27AABCA1234F1ZP"


def test_decimal_extraction_captures_discount_address_and_negative_amount():
    parsed = parse_invoice_text(
        "Northwind Trading\n"
        "Vendor Address: 12 Market Street\n"
        "Subtotal: 100.00\n"
        "Tax: 10.00\n"
        "Discount: 5.25\n"
        "Total: 104.75"
    )
    assert str(parsed["subtotal"]) == "100.00"
    assert str(parsed["discount_amount"]) == "5.25"
    assert parsed["vendor_address"] == "12 Market Street"
    assert parse_invoice_text("Total: (10.50)")["total_amount"] == -10.5


def test_database_connection_options_are_driver_specific():
    assert _connect_args("sqlite:///./test.db") == {"check_same_thread": False}
    assert _connect_args("postgresql://user:pass@localhost/invoices") == {}


def test_pdf_extraction_and_parse_works(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Vendor: BluePeak Systems\nInvoice # INV-505\nTotal: 1000.00\nDate: 2024-01-05")
    doc.save(pdf_path)
    doc.close()

    result = extract_text_from_pdf(str(pdf_path))
    assert result["error"] is None
    assert "BluePeak Systems" in result["text"]

    parsed = parse_invoice_text(result["text"])
    assert parsed["vendor_name"] == "BluePeak Systems"
    assert parsed["invoice_number"] == "INV-505"


def test_encrypted_pdf_is_reported_without_claiming_extraction(tmp_path):
    pdf_path = tmp_path / "encrypted.pdf"
    document = fitz.open()
    document.new_page()
    pdf_path.write_bytes(document.tobytes(
        encryption=fitz.PDF_ENCRYPT_AES_256,
        owner_pw="owner",
        user_pw="user",
    ))
    document.close()

    result = extract_text_from_pdf(str(pdf_path))
    assert result["text"] == ""
    assert result["error"] == "PDF is encrypted or password-protected. Password entry is not supported."


def test_explicit_tax_rates_parse_and_combined_cgst_sgst():
    parsed = parse_invoice_text(
        "Vendor: Northwind\nSubtotal: 100.00\nCGST 9%: 9.00\nSGST 9%: 9.00\nTotal: 118.00"
    )
    assert parsed["tax_rate"] == 18.0
    assert parsed["tax_amount"] == 18.0

    tax_only = parse_invoice_text("Vendor: Northwind\nSubtotal: 100.00\nTax Rate: 10%\nTax: 10.00")
    assert tax_only["tax_rate"] == 10.0


def test_configured_ocr_failure_is_explicit(tmp_path):
    image_path = tmp_path / "invoice.png"
    Image.new("RGB", (20, 20), "white").save(image_path)

    result = extract_text_from_image(str(image_path), str(tmp_path / "missing-tesseract.exe"))
    assert result["text"] == ""
    assert result["error"].startswith("OCR failed (TesseractNotFoundError)")


def test_duplicate_number_detection(db_session):
    first = Invoice(
        file_hash="hash1",
        original_filename="a.pdf",
        stored_filename="a.pdf",
        file_size=100,
        file_type=".pdf",
        vendor_name="Northwind",
        invoice_number="INV-300",
        invoice_date=date(2024, 1, 2),
        total_amount=1200.0,
        review_status="needs_review",
    )
    second = Invoice(
        file_hash="hash2",
        original_filename="b.pdf",
        stored_filename="b.pdf",
        file_size=120,
        file_type=".pdf",
        vendor_name="Northwind",
        invoice_number="INV-300",
        invoice_date=date(2024, 1, 3),
        total_amount=1200.0,
        review_status="needs_review",
    )
    db_session.add_all([first, second])
    db_session.flush()

    findings = check_duplicate_number(second, db_session)
    assert findings
    assert findings[0].finding_type == "duplicate_number"


def test_arithmetic_mismatch_detection(db_session):
    invoice = Invoice(
        file_hash="hash3",
        original_filename="c.pdf",
        stored_filename="c.pdf",
        file_size=100,
        file_type=".pdf",
        vendor_name="Harbor Co",
        invoice_number="INV-900",
        invoice_date=date(2024, 2, 2),
        subtotal=1000.0,
        tax_amount=200.0,
        total_amount=1500.0,
        review_status="needs_review",
    )
    db_session.add(invoice)
    db_session.flush()

    findings = check_arithmetic(invoice, db_session, tolerance=1.0)
    assert any(item.finding_type == "arithmetic_error" for item in findings)


def test_discount_is_included_in_decimal_arithmetic(db_session):
    invoice = Invoice(
        file_hash="discount-test",
        original_filename="discount.pdf",
        stored_filename="discount.pdf",
        file_size=100,
        file_type=".pdf",
        subtotal=Decimal("100.00"),
        tax_amount=Decimal("10.00"),
        discount_amount=Decimal("5.00"),
        total_amount=Decimal("105.00"),
    )
    db_session.add(invoice)
    db_session.flush()

    assert check_arithmetic(invoice, db_session, tolerance=0.01) == []
    invoice.total_amount = Decimal("106.00")
    findings = check_arithmetic(invoice, db_session, tolerance=0.01)
    arithmetic = next(item for item in findings if item.finding_type == "arithmetic_error")
    assert json.loads(arithmetic.evidence)["expected_total"] == 105.0
    assert "discount_amount" in json.loads(arithmetic.affected_fields)


def test_potential_duplicate_matching_requires_currency_and_uses_normalized_vendor(db_session):
    first = Invoice(
        file_hash="currency-match-a",
        original_filename="a.pdf",
        stored_filename="a.pdf",
        file_size=100,
        file_type=".pdf",
        vendor_name="Acme, Inc.",
        invoice_number="INV-1001",
        invoice_date=date(2024, 2, 1),
        currency="USD",
        total_amount=Decimal("100.00"),
    )
    second = Invoice(
        file_hash="currency-match-b",
        original_filename="b.pdf",
        stored_filename="b.pdf",
        file_size=100,
        file_type=".pdf",
        vendor_name="acme inc",
        invoice_number="INV-1002",
        invoice_date=date(2024, 2, 20),
        currency="USD",
        total_amount=Decimal("101.50"),
    )
    db_session.add_all([first, second])
    db_session.flush()

    findings = check_potential_duplicates(second, db_session)
    assert len(findings) == 1
    assert json.loads(findings[0].evidence)["confidence"] >= 0.7

    second.currency = "INR"
    assert check_potential_duplicates(second, db_session) == []


def test_tax_discrepancy_and_vendor_amount_outlier_are_review_findings(db_session):
    for index, total in enumerate((100.0, 110.0, 120.0)):
        db_session.add(Invoice(
            file_hash=f"history-{index}",
            original_filename=f"history-{index}.pdf",
            stored_filename=f"history-{index}.pdf",
            file_size=100,
            file_type=".pdf",
            vendor_name="Northwind",
            currency="USD",
            total_amount=total,
        ))
    db_session.flush()
    invoice = Invoice(
        file_hash="outlier",
        original_filename="outlier.pdf",
        stored_filename="outlier.pdf",
        file_size=100,
        file_type=".pdf",
        vendor_name="Northwind",
        currency="USD",
        subtotal=1000.0,
        tax_rate=10.0,
        tax_amount=200.0,
        total_amount=1200.0,
    )
    db_session.add(invoice)
    db_session.flush()

    findings = run_all_checks(invoice, db_session)
    findings_by_type = {finding.finding_type: finding for finding in findings}
    assert "tax_calculation_mismatch" in findings_by_type
    assert "unusual_amount" in findings_by_type
    assert findings_by_type["tax_calculation_mismatch"].suggested_action
    assert "review signal" in findings_by_type["unusual_amount"].description


def test_line_item_quantity_price_mismatch_is_evidence_based(db_session):
    invoice = Invoice(
        file_hash="line-item-test",
        original_filename="line-item.pdf",
        stored_filename="line-item.pdf",
        file_size=100,
        file_type=".pdf",
    )
    db_session.add(invoice)
    db_session.flush()
    db_session.add(LineItem(
        invoice_id=invoice.id,
        description="Service",
        quantity=3,
        unit_price=10,
        amount=25,
    ))
    db_session.flush()

    findings = check_arithmetic(invoice, db_session, tolerance=0.01)
    line_finding = next(item for item in findings if "Line Item Calculation" in item.title)
    assert json.loads(line_finding.evidence)["expected_amount"] == 30
    assert line_finding.affected_fields == '["line_items"]'


def test_stored_file_deletion_rejects_path_traversal(tmp_path):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    with pytest.raises(Exception):
        delete_stored_file("..\\outside.pdf", str(upload_dir))


def test_csv_export_escapes_formula_attack():
    rows = [{"id": 5, "vendor_name": "=cmd|", "invoice_number": "INV-1", "invoice_date": "2024-07-02", "subtotal": 100, "tax_amount": 10, "total_amount": 110, "currency": "USD", "review_status": "needs_review"}]
    findings_map = {5: [{"finding_type": "duplicate_number", "severity": "high", "description": "=SUM(1,2)"}]}

    csv_bytes = generate_invoice_report_csv(rows, findings_map)
    csv_text = csv_bytes.decode("utf-8-sig")
    assert "'=cmd|" in csv_text
    assert "'=SUM(1,2)" in csv_text


def test_normalize_invoice_number_handles_prefixes():
    assert normalize_invoice_number("Invoice # INV-987") == "987"
    assert normalize_invoice_number("  BILL-200 ") == "200"


def test_additive_sqlite_migration_preserves_existing_rows(tmp_path, monkeypatch):
    import app.database as database

    legacy_engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with legacy_engine.begin() as connection:
        connection.execute(text("CREATE TABLE invoices (id INTEGER PRIMARY KEY, legacy_value TEXT)"))
        connection.execute(text("INSERT INTO invoices (id, legacy_value) VALUES (7, 'keep-me')"))
        connection.execute(text("CREATE TABLE findings (id INTEGER PRIMARY KEY)"))

    monkeypatch.setattr(database, "engine", legacy_engine)
    database.init_db()
    database.init_db()

    with legacy_engine.connect() as connection:
        invoice = connection.execute(text(
            "SELECT id, legacy_value, processing_status, processing_error, tax_rate, "
            "vendor_address, discount_amount "
            "FROM invoices WHERE id = 7"
        )).one()
        assert invoice == (7, "keep-me", "completed", None, None, None, None)
        assert "suggested_action" in {column["name"] for column in inspect(connection).get_columns("findings")}
        assert connection.execute(text(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'duplicate_detections'"
        )).first()

    legacy_engine.dispose()


def test_invoice_record_persists_after_reopening_sqlite(tmp_path):
    database_path = tmp_path / "persistent.db"
    engine = create_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    session.add(Invoice(
        file_hash="persisted-test",
        original_filename="persisted.pdf",
        stored_filename="persisted.pdf",
        file_size=100,
        file_type=".pdf",
        vendor_name="Persistent Vendor",
    ))
    session.commit()
    session.close()
    engine.dispose()

    reopened = create_engine(f"sqlite:///{database_path}")
    reopened_session = sessionmaker(bind=reopened)()
    try:
        persisted = reopened_session.query(Invoice).one()
        assert persisted.vendor_name == "Persistent Vendor"
    finally:
        reopened_session.close()
    reopened.dispose()


def test_fastapi_startup_initializes_database_and_health_endpoints(tmp_path, monkeypatch):
    import app.database as database
    import app.main as main_module

    database_path = tmp_path / "startup.db"
    startup_engine = create_engine(f"sqlite:///{database_path}")
    startup_sessions = sessionmaker(bind=startup_engine)
    upload_dir = tmp_path / "uploads"
    report_dir = tmp_path / "reports"

    monkeypatch.setattr(database, "engine", startup_engine)
    monkeypatch.setattr(database, "SessionLocal", startup_sessions)
    monkeypatch.setattr(main_module, "SessionLocal", startup_sessions)
    monkeypatch.setattr(main_module, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(main_module, "REPORT_DIR", report_dir)
    monkeypatch.setattr(main_module.settings, "SEED_DEMO_DATA", False)

    try:
        with TestClient(main_module.app) as client:
            assert client.get("/").status_code == 200
            assert client.get("/health").json()["status"] == "healthy"
            assert client.get("/api/health").json()["status"] == "healthy"

        assert upload_dir.is_dir()
        assert report_dir.is_dir()
        assert {
            "invoices",
            "findings",
            "line_items",
            "duplicate_detections",
            "purchase_orders",
            "purchase_order_line_items",
        }.issubset(
            set(inspect(startup_engine).get_table_names())
        )
        assert database_path.exists()
    finally:
        startup_engine.dispose()


def test_purchase_order_comparison_endpoint_persists_mismatch_finding():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db_session = Session()
    invoice = Invoice(
        file_hash="po-test-hash",
        original_filename="invoice.pdf",
        stored_filename="invoice.pdf",
        file_size=100,
        file_type=".pdf",
        vendor_name="Acme Supplies",
        invoice_number="INV-42",
        total_amount=100.0,
    )
    db_session.add(invoice)
    db_session.commit()
    invoice_id = invoice.id

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_loopback_auth_request] = lambda: None
    try:
        client = TestClient(app)
        registration = client.post(
            "/api/auth/register",
            json={
                "email": "po-owner@example.test",
                "password": "local-test-password-2026",
                "workspace_name": "PO test workspace",
            },
        )
        assert registration.status_code == 201
        invoice.workspace_id = registration.json()["workspace"]["id"]
        db_session.commit()
        client.headers.update({
            "Authorization": f"Bearer {registration.json()['access_token']}",
        })
        response = client.post(
            f"/api/invoices/{invoice_id}/purchase-order/compare",
            json={"po_number": "PO-9", "po_vendor": "Acme Supplies", "po_total": 125.0},
        )

        assert response.status_code == 200
        comparison = response.json()
        assert comparison["po_number"] == "PO-9"
        total_result = next(
            result for result in comparison["comparison_result"]
            if result["field"] == "total"
        )
        assert total_result["match"] is False
        assert total_result["difference"] == 25.0
        finding = db_session.query(Finding).filter(
            Finding.invoice_id == invoice_id,
            Finding.finding_type == "po_mismatch",
        ).one()
        assert finding.severity == "high"
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(require_loopback_auth_request, None)
        db_session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_purchase_order_crud_comparison_and_workspace_isolation():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db_session = Session()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_loopback_auth_request] = lambda: None
    try:
        client = TestClient(app)
        first = client.post(
            "/api/auth/register",
            json={
                "email": "po-crud-owner@example.test",
                "password": "local-test-password-2026",
                "workspace_name": "PO CRUD test workspace",
            },
        )
        assert first.status_code == 201
        first_token = first.json()["access_token"]
        first_workspace_id = first.json()["workspace"]["id"]
        client.headers.update({"Authorization": f"Bearer {first_token}"})

        payload = {
            "po_number": "PO-2026-04",
            "vendor_name": "Acme Supplies",
            "currency": "inr",
            "order_date": "2026-04-15",
            "expected_delivery_date": "2026-05-01",
            "tax_rate": 18,
            "line_items": [
                {"description": "Paper", "quantity": 2, "unit_price": 15.25},
                {"description": "Ink", "quantity": 1, "unit_price": 10},
            ],
        }
        created = client.post("/api/purchase-orders", json=payload)
        assert created.status_code == 201
        purchase_order = created.json()
        assert purchase_order["currency"] == "INR"
        assert purchase_order["subtotal"] == 40.5
        assert purchase_order["tax_amount"] == 7.29
        assert purchase_order["total_amount"] == 47.79
        assert [item["amount"] for item in purchase_order["line_items"]] == [30.5, 10.0]
        assert client.get("/api/purchase-orders").json()[0]["id"] == purchase_order["id"]
        assert client.get(f"/api/purchase-orders/{purchase_order['id']}").status_code == 200

        duplicate = client.post("/api/purchase-orders", json=payload)
        assert duplicate.status_code == 409

        updated_payload = {
            **payload,
            "vendor_name": "Acme Paper",
            "status": "fulfilled",
            "line_items": [{"description": "Paper", "quantity": 4, "unit_price": 15.25}],
        }
        updated = client.put(
            f"/api/purchase-orders/{purchase_order['id']}",
            json=updated_payload,
        )
        assert updated.status_code == 200
        assert updated.json()["vendor_name"] == "Acme Paper"
        assert updated.json()["total_amount"] == 71.98
        assert updated.json()["status"] == "fulfilled"

        invoice = Invoice(
            workspace_id=first_workspace_id,
            file_hash="po-crud-invoice-hash",
            original_filename="po-invoice.pdf",
            stored_filename="po-invoice.pdf",
            file_size=100,
            file_type=".pdf",
            vendor_name="Acme Paper",
            invoice_number="INV-PO-1",
            currency="USD",
            total_amount=71.98,
        )
        db_session.add(invoice)
        db_session.commit()
        compared = client.post(
            f"/api/purchase-orders/{purchase_order['id']}/invoices/{invoice.id}/compare"
        )
        assert compared.status_code == 200
        comparison = compared.json()["comparison_result"]
        assert next(result for result in comparison if result["field"] == "currency")["match"] is False
        assert next(result for result in comparison if result["field"] == "total")["status"] == "not_compared"
        assert db_session.query(Finding).filter(
            Finding.invoice_id == invoice.id,
            Finding.title == "Currency Mismatch with Purchase Order",
        ).count() == 1

        second = client.post(
            "/api/auth/register",
            json={
                "email": "other-po-owner@example.test",
                "password": "local-test-password-2026",
                "workspace_name": "Other PO workspace",
            },
        )
        assert second.status_code == 201
        client.headers.update({"Authorization": f"Bearer {second.json()['access_token']}"})
        assert client.get("/api/purchase-orders").json() == []
        assert client.get(f"/api/purchase-orders/{purchase_order['id']}").status_code == 404
        assert client.delete(f"/api/purchase-orders/{purchase_order['id']}").status_code == 404

        client.headers.update({"Authorization": f"Bearer {first_token}"})
        deleted = client.delete(f"/api/purchase-orders/{purchase_order['id']}")
        assert deleted.status_code == 204
        assert client.get("/api/purchase-orders").json() == []
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(require_loopback_auth_request, None)
        db_session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_vendor_intelligence_uses_workspace_invoice_data_only():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db_session = Session()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_loopback_auth_request] = lambda: None
    try:
        client = TestClient(app)
        first = client.post(
            "/api/auth/register",
            json={
                "email": "vendor-owner@example.test",
                "password": "local-test-password-2026",
                "workspace_name": "Vendor test workspace",
            },
        )
        assert first.status_code == 201
        workspace_id = first.json()["workspace"]["id"]
        client.headers.update({"Authorization": f"Bearer {first.json()['access_token']}"})

        older_invoice = Invoice(
            workspace_id=workspace_id,
            file_hash="vendor-invoice-one",
            original_filename="vendor-one.pdf",
            stored_filename="vendor-one.pdf",
            file_size=100,
            file_type=".pdf",
            vendor_name="Acme Ltd",
            invoice_number="AC-1",
            invoice_date=date(2026, 1, 10),
            currency="INR",
            total_amount=100,
        )
        newer_invoice = Invoice(
            workspace_id=workspace_id,
            file_hash="vendor-invoice-two",
            original_filename="vendor-two.pdf",
            stored_filename="vendor-two.pdf",
            file_size=100,
            file_type=".pdf",
            vendor_name=" acme ltd ",
            invoice_number="AC-2",
            invoice_date=date(2026, 2, 10),
            currency="INR",
            total_amount=200,
        )
        db_session.add_all([older_invoice, newer_invoice])
        db_session.commit()
        db_session.add_all([
            LineItem(
                invoice_id=older_invoice.id,
                description="Widget",
                quantity=1,
                unit_price=10,
                amount=10,
                item_order=0,
            ),
            LineItem(
                invoice_id=newer_invoice.id,
                description="Widget",
                quantity=1,
                unit_price=12,
                amount=12,
                item_order=0,
            ),
            Finding(
                invoice_id=newer_invoice.id,
                finding_type="arithmetic",
                severity="medium",
                title="Arithmetic mismatch",
                description="Saved test evidence.",
            ),
            DuplicateDetection(
                source_invoice_id=newer_invoice.id,
                matched_invoice_id=older_invoice.id,
                match_type="potential",
                confidence=0.8,
                evidence="{}",
            ),
        ])
        db_session.commit()

        response = client.get("/api/vendors")
        assert response.status_code == 200
        vendors = response.json()
        assert len(vendors) == 1
        vendor = vendors[0]
        assert vendor["name"].strip().casefold() == "acme ltd"
        assert vendor["invoice_count"] == 2
        assert vendor["total_value_by_currency"] == [{"currency": "INR", "amount": 300.0}]
        assert vendor["invoice_frequency"] == [
            {"month": "2026-01", "count": 1},
            {"month": "2026-02", "count": 1},
        ]
        assert vendor["findings_by_severity"] == {"medium": 1}
        assert vendor["duplicate_matches"] == 1
        assert vendor["price_changes"][0]["entries"][0]["unit_price"] == 10
        assert vendor["price_changes"][0]["entries"][1]["unit_price"] == 12
        assert vendor["contact_details_available"] is False
        assert vendor["payment_tracking_available"] is False

        second = client.post(
            "/api/auth/register",
            json={
                "email": "other-vendor-owner@example.test",
                "password": "local-test-password-2026",
                "workspace_name": "Other vendor workspace",
            },
        )
        assert second.status_code == 201
        client.headers.update({"Authorization": f"Bearer {second.json()['access_token']}"})
        assert client.get("/api/vendors").json() == []
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(require_loopback_auth_request, None)
        db_session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
