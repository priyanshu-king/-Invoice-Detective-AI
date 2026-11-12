# Invoice Detective AI - Implementation Plan

## Current status
- Backend includes local authentication and workspace-scoped APIs for invoice upload/review, duplicate and arithmetic findings, purchase orders, vendor intelligence, reports, privacy exports, and persisted settings.
- Frontend is a React + TypeScript + Vite application connected to the local API. Unsupported integrations are presented as unavailable rather than simulated.
- SQLite initialization uses safe additive upgrades. Existing monetary columns are not rebuilt; audit and purchase-order calculations use `Decimal` in application logic and API responses remain JSON numbers for compatibility.
- OCR is local and optional: PyMuPDF handles embedded PDF text; Tesseract handles images and scanned PDFs only when installed/configured. Invoice data is not sent to an external OCR service.

## Phase 1: Project scaffolding and health checks
- Verify Python and Node environment.
- Install backend Python dependencies.
- Create a FastAPI app entrypoint and static configuration.
- Add health-check and startup validation endpoints.
- Confirm the backend starts successfully.
- Create the frontend Vite/React/TypeScript app and install dependencies.

## Phase 2: Database, upload pipeline, and extraction
- Complete SQLAlchemy database initialization.
- Implement secure upload validation, file hashing, and storage management.
- Add invoice parsing from PDFs/images and editable extraction review logic.
- Store uploaded file metadata and extracted values in SQLite.

## Phase 3: Duplicate detection and discrepancy engine
- Run deterministic duplicate checks and explainable findings.
- Add arithmetic validation, missing-field warnings, and GSTIN format checks.
- Store review findings with evidence and severity metadata.

## Phase 4: Dashboard, management, and reports
- Build invoice list/detail endpoints and dashboard stats.
- Add report generation (CSV) and optional PDF export.
- Support delete, reanalysis, and review-status updates.

## Phase 5: Privacy/security and integration
- Add strict validation, CORS, safe storage, and privacy notices.
- Connect the frontend to the backend via environment-aware API configuration.
- Confirm empty/error/loading states and demo-data labeling.

## Phase 6: Validation and documentation
- Run unit tests and API tests.
- Fix failures and produce a production frontend build.
- Update README and final deployment notes.

## Execution log
- [x] Environment inspect completed.
- [x] Backend dependencies and app bootstrap.
- [x] Frontend scaffolding.
- [x] Database + upload + parsing.
- [x] Detection engine and findings.
- [x] Dashboard, review workflow, and reports.
- [x] Expose the existing PO comparison service through the API and verify persisted mismatch findings.
- [x] Security/privacy and frontend integration.
- [x] Backend tests and frontend production build.
