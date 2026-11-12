import io
from pathlib import Path
from datetime import datetime, timedelta

import fitz
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, engine, get_db
from app.main import app
from app.models import AuthSession, DuplicateDetection, Finding, Invoice
from app.security import hash_session_token, require_loopback_auth_request


@pytest.fixture
def unauthenticated_api_client(tmp_path, monkeypatch):
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    test_session = sessionmaker(bind=test_engine)
    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(upload_dir))

    def override_get_db():
        db = test_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_loopback_auth_request] = lambda: None
    client = TestClient(app)
    try:
        yield client
    finally:
        client.close()
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(require_loopback_auth_request, None)
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


@pytest.fixture
def api_client(unauthenticated_api_client):
    client = unauthenticated_api_client
    registration = client.post(
        "/api/auth/register",
        json={
            "email": "owner@example.test",
            "password": "local-test-password-2026",
            "workspace_name": "Test workspace",
        },
    )
    assert registration.status_code == 201, registration.text
    client.headers.update({
        "Authorization": f"Bearer {registration.json()['access_token']}",
    })
    return client


def make_pdf(text: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    for index, line in enumerate(text.splitlines()):
        page.insert_text((72, 72 + 20 * index), line)
    content = document.tobytes()
    document.close()
    return content


def make_invoice_pdf(invoice_number: str, total: str = "110.00", extra: str = "") -> bytes:
    return make_pdf(
        "\n".join(
            [
                "Vendor: Northwind Trading",
                f"Invoice # {invoice_number}",
                "Invoice Date: 2024-01-05",
                "Subtotal: 100.00",
                "Tax: 10.00",
                f"Total: {total}",
                extra,
            ]
        )
    )


def test_privacy_endpoint_reports_configured_local_storage_paths(api_client, tmp_path):
    response = api_client.get("/api/privacy")

    assert response.status_code == 200
    storage_location = response.json()["storage_location"]
    assert str((tmp_path / "uploads").resolve()) in storage_location
    assert str(Path(engine.url.database).resolve()) in storage_location
    assert response.json()["max_file_size_bytes"] == settings.max_file_size_bytes


def test_invoice_activity_tracks_changes_and_is_workspace_scoped(api_client):
    uploaded = api_client.post(
        "/api/invoices/upload",
        files={"file": ("activity-test.pdf", make_invoice_pdf("ACTIVITY-1", total="120.00"), "application/pdf")},
    )
    assert uploaded.status_code == 200, uploaded.text
    invoice_id = uploaded.json()["id"]

    activity = api_client.get(f"/api/invoices/{invoice_id}/activity")
    assert activity.status_code == 200
    assert activity.json()["items"][0]["event_type"] == "invoice_uploaded"
    assert activity.json()["items"][0]["changed_fields"] == []

    arithmetic_finding = next(
        item for item in uploaded.json()["findings"] if item["finding_type"] == "arithmetic_error"
    )
    reviewed = api_client.post(
        f"/api/invoices/{invoice_id}/findings/{arithmetic_finding['id']}/review",
        json={"review_status": "resolved"},
    )
    assert reviewed.status_code == 200, reviewed.text
    activity = api_client.get(f"/api/invoices/{invoice_id}/activity")
    assert activity.json()["items"][0]["event_type"] == "finding_reviewed"

    updated = api_client.patch(
        f"/api/invoices/{invoice_id}",
        json={"vendor_name": "Corrected Vendor", "notes": "Checked against source"},
    )
    assert updated.status_code == 200, updated.text
    activity = api_client.get(f"/api/invoices/{invoice_id}/activity")
    assert activity.status_code == 200
    latest = activity.json()["items"][0]
    assert latest["event_type"] == "invoice_updated"
    assert latest["summary"] == "Invoice details corrected"
    assert set(latest["changed_fields"]) == {"vendor_name", "notes"}

    other_workspace = api_client.post(
        "/api/auth/register",
        json={
            "email": "second-owner@example.test",
            "password": "another-local-test-password",
            "workspace_name": "Separate workspace",
        },
    )
    assert other_workspace.status_code == 201, other_workspace.text
    isolated = api_client.get(
        f"/api/invoices/{invoice_id}/activity",
        headers={"Authorization": f"Bearer {other_workspace.json()['access_token']}"},
    )
    assert isolated.status_code == 404


def test_workspace_settings_are_saved_and_returned_from_database(api_client):
    defaults = api_client.get("/api/settings")
    assert defaults.status_code == 200
    assert defaults.json()["default_currency"] == "INR"
    assert defaults.json()["appearance"] == "light"
    assert defaults.json()["authentication"]["password_management"].startswith("Password changes")

    updated = {
        "workspace_name": "  Northwind Finance  ",
        "business_name": "Northwind Trading",
        "default_currency": "usd",
        "date_format": "DD/MM/YYYY",
        "time_zone": "UTC",
        "language": "en",
        "default_tax_rate": 18,
        "invoice_number_prefix": "NW-",
        "default_review_status": "reviewed",
        "notify_audit_completion": False,
        "notify_duplicate_detection": True,
        "notify_failed_upload": False,
        "notify_review_reminders": True,
        "profile_display_name": "Finance Owner",
        "appearance": "dark",
    }

    saved = api_client.put("/api/settings", json=updated)
    assert saved.status_code == 200, saved.text
    assert saved.json()["workspace_name"] == "Northwind Finance"
    assert saved.json()["default_currency"] == "USD"
    assert saved.json()["notifications"] == {
        "audit_completion": False,
        "duplicate_detection": True,
        "failed_upload": False,
        "review_reminders": True,
    }
    assert saved.json()["profile"] == {
        "display_name": "Finance Owner",
        "email": "owner@example.test",
    }

    refreshed = api_client.get("/api/settings")
    assert refreshed.json() == saved.json()


def test_workspace_settings_reject_invalid_values(api_client):
    invalid = {
        "workspace_name": "Valid name",
        "default_currency": "US dollars",
        "time_zone": "Mars/Olympus",
        "default_tax_rate": 150,
        "appearance": "neon",
    }

    response = api_client.put("/api/settings", json=invalid)

    assert response.status_code == 422


def test_authentication_and_first_workspace_preserve_legacy_records(unauthenticated_api_client):
    session_generator = app.dependency_overrides[get_db]()
    db = next(session_generator)
    legacy_invoice = Invoice(
        file_hash="legacy-hash",
        original_filename="legacy.pdf",
        stored_filename="legacy.pdf",
        file_size=10,
        file_type=".pdf",
        vendor_name="Legacy Vendor",
    )
    db.add(legacy_invoice)
    db.commit()
    legacy_id = legacy_invoice.id
    session_generator.close()

    client = unauthenticated_api_client
    assert client.get("/health").status_code == 200
    assert client.get("/api/invoices").status_code == 401
    assert client.get("/api/privacy").status_code == 401
    assert client.get("/api/settings").status_code == 401

    registration = client.post(
        "/api/auth/register",
        json={
            "email": "FIRST@example.test",
            "password": "secure-local-password-2026",
            "workspace_name": "Legacy workspace",
        },
    )

    assert registration.status_code == 201
    token = registration.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    history = client.get("/api/invoices")
    assert history.status_code == 200
    assert history.json()["total"] == 1
    assert history.json()["items"][0]["id"] == legacy_id
    assert history.json()["items"][0]["vendor_name"] == "Legacy Vendor"
    assert client.get("/api/auth/me").json()["workspace"]["name"] == "Legacy workspace"

    session_generator = app.dependency_overrides[get_db]()
    db = next(session_generator)
    auth_session = db.query(AuthSession).one()
    assert auth_session.token_hash != token
    assert len(auth_session.token_hash) == 64
    session_generator.close()


def test_authentication_guard_rejects_non_loopback_clients(monkeypatch):
    from types import SimpleNamespace

    from fastapi import HTTPException

    from app.config import settings

    monkeypatch.setattr(settings, "HOST", "127.0.0.1")
    request = SimpleNamespace(client=SimpleNamespace(host="203.0.113.15"))

    with pytest.raises(HTTPException) as error:
        require_loopback_auth_request(request)

    assert error.value.status_code == 403


def test_invoice_apis_are_isolated_between_workspaces(api_client):
    first_upload = api_client.post(
        "/api/invoices/upload",
        files={"file": ("tenant-invoice.pdf", make_invoice_pdf("TENANT-1"), "application/pdf")},
    )
    assert first_upload.status_code == 200
    first_invoice = first_upload.json()
    first_token = api_client.headers["Authorization"]

    second_registration = api_client.post(
        "/api/auth/register",
        json={
            "email": "second@example.test",
            "password": "another-local-password-2026",
            "workspace_name": "Second workspace",
        },
    )
    assert second_registration.status_code == 201
    invalid_login = api_client.post(
        "/api/auth/login",
        json={"email": "second@example.test", "password": "wrong-password"},
    )
    assert invalid_login.status_code == 401
    valid_login = api_client.post(
        "/api/auth/login",
        json={"email": "second@example.test", "password": "another-local-password-2026"},
    )
    assert valid_login.status_code == 200
    second_token = valid_login.json()["access_token"]
    api_client.headers.update({"Authorization": f"Bearer {second_token}"})

    assert api_client.get("/api/dashboard").json()["total_invoices"] == 0
    assert api_client.get("/api/invoices").json()["total"] == 0
    assert api_client.get(f"/api/invoices/{first_invoice['id']}").status_code == 404
    assert api_client.get(f"/api/invoices/{first_invoice['id']}/file").status_code == 404
    assert api_client.get(f"/api/invoices/{first_invoice['id']}/findings").status_code == 404
    assert api_client.patch(
        f"/api/invoices/{first_invoice['id']}",
        json={"vendor_name": "Unauthorized edit"},
    ).status_code == 404
    assert api_client.delete(f"/api/invoices/{first_invoice['id']}").status_code == 404
    assert api_client.get(f"/api/findings?invoice_id={first_invoice['id']}").json()["total"] == 0
    assert api_client.get("/api/duplicate-detections").json() == []
    assert b"Northwind Trading" not in api_client.get("/api/reports/csv").content

    second_upload = api_client.post(
        "/api/invoices/upload",
        files={"file": ("same-content.pdf", make_invoice_pdf("TENANT-1"), "application/pdf")},
    )
    assert second_upload.status_code == 200
    assert not any(
        finding["finding_type"] in {"duplicate_hash", "duplicate_number", "potential_duplicate"}
        for finding in second_upload.json()["findings"]
    )
    assert api_client.get("/api/duplicate-detections").json() == []

    api_client.headers.update({"Authorization": first_token})
    assert api_client.get("/api/dashboard").json()["total_invoices"] == 1
    api_client.headers.update({"Authorization": f"Bearer {second_token}"})
    assert api_client.post("/api/auth/logout").json()["logged_out"] is True
    assert api_client.get("/api/invoices").status_code == 401

    expired_login = api_client.post(
        "/api/auth/login",
        json={"email": "second@example.test", "password": "another-local-password-2026"},
    )
    assert expired_login.status_code == 200
    expired_token = expired_login.json()["access_token"]
    session_generator = app.dependency_overrides[get_db]()
    db = next(session_generator)
    auth_session = db.query(AuthSession).filter(
        AuthSession.token_hash == hash_session_token(expired_token)
    ).one()
    auth_session.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    session_generator.close()
    api_client.headers.update({"Authorization": f"Bearer {expired_token}"})
    assert api_client.get("/api/invoices").status_code == 401


def test_sqlite_additive_upgrade_preserves_legacy_invoice(tmp_path):
    from sqlalchemy import text

    from app.database import apply_sqlite_additive_upgrades

    legacy_engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with legacy_engine.begin() as connection:
        connection.execute(text("CREATE TABLE workspaces (id INTEGER PRIMARY KEY)"))
        connection.execute(text(
            "CREATE TABLE invoices (id INTEGER PRIMARY KEY, vendor_name TEXT)"
        ))
        connection.execute(text("INSERT INTO invoices (id, vendor_name) VALUES (17, 'Old Vendor')"))
        connection.execute(text("CREATE TABLE findings (id INTEGER PRIMARY KEY)"))

    apply_sqlite_additive_upgrades(legacy_engine)

    with legacy_engine.connect() as connection:
        invoice = connection.execute(
            text("SELECT id, vendor_name, workspace_id FROM invoices WHERE id = 17")
        ).one()
        assert invoice == (17, "Old Vendor", None)
        assert connection.execute(text("SELECT count(*) FROM invoices")).scalar_one() == 1
    legacy_engine.dispose()


def test_upload_edit_duplicates_history_csv_and_delete(api_client, tmp_path):
    first_pdf = make_invoice_pdf("INV-100")
    upload = api_client.post(
        "/api/invoices/upload",
        files={"file": ("invoice-100.pdf", first_pdf, "application/pdf")},
    )
    assert upload.status_code == 200
    invoice = upload.json()
    invoice_id = invoice["id"]
    assert invoice["vendor_name"] == "Northwind Trading"
    assert invoice["invoice_number"] == "INV-100"
    assert invoice["subtotal"] == 100
    assert invoice["tax_amount"] == 10
    assert invoice["total_amount"] == 110
    assert (tmp_path / "uploads" / invoice["stored_filename"]).is_file()
    source_file = api_client.get(f"/api/invoices/{invoice_id}/file")
    assert source_file.status_code == 200
    assert source_file.headers["content-type"] == "application/pdf"
    assert source_file.headers["content-disposition"] == "inline"
    assert source_file.content == first_pdf

    exact_duplicate = api_client.post(
        "/api/invoices/upload",
        files={"file": ("same-content.pdf", first_pdf, "application/pdf")},
    )
    assert exact_duplicate.status_code == 409
    assert "duplicate" in exact_duplicate.json()["detail"].lower()
    duplicate_records = api_client.get("/api/duplicate-detections")
    assert duplicate_records.status_code == 200
    assert duplicate_records.json()[0]["match_type"] == "exact_file_hash"
    assert duplicate_records.json()[0]["matched_invoice_id"] == invoice_id

    same_number_pdf = make_invoice_pdf("INV-100", extra="Submission copy B")
    same_number = api_client.post(
        "/api/invoices/upload",
        files={"file": ("invoice-100-copy.pdf", same_number_pdf, "application/pdf")},
    )
    assert same_number.status_code == 200
    assert any(item["finding_type"] == "duplicate_number" for item in same_number.json()["findings"])

    similar_invoice = api_client.post(
        "/api/invoices/upload",
        files={
            "file": (
                "invoice-101.pdf",
                make_invoice_pdf("INV-101", extra="Separate invoice"),
                "application/pdf",
            )
        },
    )
    assert similar_invoice.status_code == 200
    assert any(item["finding_type"] == "potential_duplicate" for item in similar_invoice.json()["findings"])

    correction = api_client.patch(
        f"/api/invoices/{invoice_id}",
        json={
            "vendor_name": "Northwind Corrected",
            "total_amount": 125,
            "discount_amount": 5,
            "line_items": [{
                "description": "Service",
                "quantity": 2,
                "unit_price": 10,
                "amount": 25,
                "item_order": 0,
            }],
        },
    )
    assert correction.status_code == 200
    corrected = correction.json()
    assert corrected["vendor_name"] == "Northwind Corrected"
    assert corrected["total_amount"] == 125
    assert corrected["discount_amount"] == 5
    assert corrected["line_items"][0]["amount"] == 25
    assert any(item["finding_type"] == "arithmetic_error" for item in corrected["findings"])
    assert corrected["uploaded_at"] == corrected["created_at"]
    assert corrected["processing_status"] == "completed"
    assert all(item["suggested_action"] for item in corrected["findings"])

    findings = api_client.get(f"/api/invoices/{invoice_id}/findings")
    assert findings.status_code == 200
    assert any(item["finding_type"] == "arithmetic_error" for item in findings.json())

    history = api_client.get("/api/invoices?page=1&page_size=20")
    assert history.status_code == 200
    assert history.json()["total"] == 3
    assert any(item["id"] == invoice_id for item in history.json()["items"])
    dashboard = api_client.get("/api/dashboard")
    assert dashboard.status_code == 200
    assert dashboard.json()["invoices_by_status"]["needs_review"] == 3

    report = api_client.get("/api/reports/csv")
    assert report.status_code == 200
    assert report.headers["content-type"].startswith("text/csv")
    assert "attachment" in report.headers["content-disposition"]
    assert b"Northwind Corrected" in report.content

    stored_path = tmp_path / "uploads" / invoice["stored_filename"]
    deleted = api_client.delete(f"/api/invoices/{invoice_id}")
    assert deleted.status_code == 200
    assert deleted.json()["file_removed"] is True
    assert not stored_path.exists()
    assert api_client.get(f"/api/invoices/{invoice_id}").status_code == 404
    assert api_client.get(f"/api/invoices/{invoice_id}/file").status_code == 404


def test_dashboard_returns_real_currency_aware_workspace_metrics(api_client):
    workspace_id = api_client.get("/api/auth/me").json()["workspace"]["id"]
    session_generator = app.dependency_overrides[get_db]()
    db = next(session_generator)

    inr_invoice = Invoice(
        workspace_id=workspace_id,
        file_hash="a" * 64,
        original_filename="inr-invoice.pdf",
        stored_filename="inr-invoice.pdf",
        file_size=100,
        file_type=".pdf",
        vendor_name="Local Supplies",
        invoice_number="INR-1",
        currency="INR",
        total_amount=100,
    )
    usd_invoice = Invoice(
        workspace_id=workspace_id,
        file_hash="b" * 64,
        original_filename="usd-invoice.pdf",
        stored_filename="usd-invoice.pdf",
        file_size=100,
        file_type=".pdf",
        vendor_name="Global Supplies",
        invoice_number="USD-1",
        currency="USD",
        total_amount=50,
        review_status="reviewed",
    )
    db.add_all([inr_invoice, usd_invoice])
    db.flush()
    invoice_ids = {inr_invoice.id, usd_invoice.id}
    db.add_all([
        Finding(
            invoice_id=usd_invoice.id,
            related_invoice_id=inr_invoice.id,
            finding_type="potential_duplicate",
            severity="medium",
            title="Potential duplicate",
            description="Review matching invoice details.",
            evidence="{}",
        ),
        DuplicateDetection(
            matched_invoice_id=inr_invoice.id,
            attempted_file_hash="c" * 64,
            match_type="exact_file_hash",
            confidence=1.0,
            evidence="{}",
        ),
    ])
    db.commit()
    session_generator.close()

    response = api_client.get("/api/dashboard")
    assert response.status_code == 200
    dashboard = response.json()
    assert dashboard["total_invoices"] == 2
    assert dashboard["invoice_value_by_currency"] == [
        {"currency": "INR", "amount": 100.0},
        {"currency": "USD", "amount": 50.0},
    ]
    assert dashboard["potential_duplicate_value_by_currency"] == [
        {"currency": "INR", "amount": 100.0},
        {"currency": "USD", "amount": 50.0},
    ]
    assert sum(row["count"] for row in dashboard["invoice_volume_by_month"]) == 2
    assert {row["currency"] for row in dashboard["spend_by_month"]} == {"INR", "USD"}
    assert {(row["currency"], row["amount"]) for row in dashboard["spend_by_month"]} == {
        ("INR", 100.0),
        ("USD", 50.0),
    }
    assert {row["vendor"] for row in dashboard["vendor_spend"]} == {
        "Local Supplies",
        "Global Supplies",
    }
    assert {row["id"] for row in dashboard["recent_invoices"]} == invoice_ids
    assert dashboard["findings_by_severity"] == {"medium": 1}


def test_image_upload_without_ocr_is_explicit(api_client):
    image = Image.new("RGB", (40, 30), "white")
    content = io.BytesIO()
    image.save(content, format="PNG")

    response = api_client.post(
        "/api/invoices/upload",
        files={"file": ("invoice.png", content.getvalue(), "image/png")},
    )

    assert response.status_code == 200
    invoice = response.json()
    assert invoice["file_type"] == ".png"
    assert invoice["vendor_name"] is None
    assert "OCR is not configured" in invoice["notes"]
    assert invoice["processing_status"] == "failed"
    assert invoice["processing_error"] == invoice["notes"]
    assert invoice["extraction_method"] == "none"


def test_upload_rejects_unsupported_mismatched_and_oversized_files(api_client, monkeypatch):
    unsupported = api_client.post(
        "/api/invoices/upload",
        files={"file": ("invoice.txt", b"invoice", "text/plain")},
    )
    assert unsupported.status_code == 400
    unsupported_tsx = api_client.post(
        "/api/invoices/upload",
        files={"file": ("use-mobile.tsx", b"export function useMobile() {}", "text/plain")},
    )
    assert unsupported_tsx.status_code == 400

    mismatched = api_client.post(
        "/api/invoices/upload",
        files={"file": ("invoice.pdf", b"not a PDF", "application/pdf")},
    )
    assert mismatched.status_code == 400

    monkeypatch.setattr(settings, "MAX_FILE_SIZE_MB", 0)
    oversized = api_client.post(
        "/api/invoices/upload",
        files={"file": ("invoice.pdf", make_invoice_pdf("INV-900"), "application/pdf")},
    )
    assert oversized.status_code == 400
    assert "size exceeds" in oversized.json()["detail"].lower()


def test_scanned_pdf_is_not_reported_as_successfully_extracted(api_client):
    response = api_client.post(
        "/api/invoices/upload",
        files={"file": ("scanned.pdf", make_pdf(""), "application/pdf")},
    )

    assert response.status_code == 200
    invoice = response.json()
    assert invoice["processing_status"] == "failed"
    assert invoice["extraction_confidence"] == "none"
    assert "scanned/image-based" in invoice["processing_error"]


def test_malformed_pdf_is_retained_with_explicit_processing_error(api_client):
    response = api_client.post(
        "/api/invoices/upload",
        files={"file": ("malformed.pdf", b"%PDF-not-a-valid-document", "application/pdf")},
    )

    assert response.status_code == 200
    invoice = response.json()
    assert invoice["processing_status"] == "failed"
    assert invoice["raw_extracted_text"] == ""
    assert invoice["processing_error"].startswith("Failed to read PDF:")


def test_local_vite_origin_is_allowed_by_cors(api_client):
    response = api_client.options(
        "/api/dashboard",
        headers={
            "Origin": "http://localhost:5174",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5174"


def test_filtered_report_summary_and_csv_use_real_workspace_records(api_client):
    northwind = api_client.post(
        "/api/invoices/upload",
        files={
            "file": (
                "northwind.pdf",
                make_pdf(
                    "Vendor: Northwind Trading\nInvoice # NW-1\nInvoice Date: 2024-01-05\n"
                    "Subtotal: 100.00\nTax: 10.00\nTotal: 110.00"
                ),
                "application/pdf",
            )
        },
    )
    acme = api_client.post(
        "/api/invoices/upload",
        files={
            "file": (
                "acme.pdf",
                make_pdf(
                    "Vendor: Acme Services\nInvoice # AC-1\nInvoice Date: 2024-03-15\n"
                    "Subtotal: 200.00\nTax: 36.00\nTotal: 236.00"
                ),
                "application/pdf",
            )
        },
    )
    assert northwind.status_code == 200
    assert acme.status_code == 200

    params = {
        "date_from": "2024-03-01",
        "date_to": "2024-03-31",
        "vendor": "Acme",
        "currency": "INR",
        "review_status": "needs_review",
        "report_type": "vendor_spending",
    }
    summary = api_client.get("/api/reports/summary", params=params)
    assert summary.status_code == 200
    report = summary.json()
    assert report["invoice_count"] == 1
    assert report["total_value_by_currency"] == [{"currency": "INR", "amount": 236.0}]
    assert report["filters"]["report_type"] == "vendor_spending"
    assert report["items"][0]["vendor_name"] == "Acme Services"
    assert report["review_status_counts"] == {"needs_review": 1}

    csv_report = api_client.get("/api/reports/summary.csv", params=params)
    assert csv_report.status_code == 200
    assert csv_report.headers["content-type"].startswith("text/csv")
    assert b"Acme Services" in csv_report.content
    assert b"Northwind Trading" not in csv_report.content

    duplicates = api_client.get("/api/reports/summary", params={"report_type": "duplicate_detection"})
    assert duplicates.status_code == 200
    assert duplicates.json()["invoice_count"] == 0

    invalid_type = api_client.get("/api/reports/summary", params={"report_type": "unsupported"})
    assert invalid_type.status_code == 400

    invalid_range = api_client.get(
        "/api/reports/summary",
        params={"date_from": "2024-04-01", "date_to": "2024-03-01"},
    )
    assert invalid_range.status_code == 400
