# Invoice Detective AI

Invoice Detective AI is a local-development application for extracting invoice fields, highlighting duplicate or inconsistent entries, and keeping a review workflow in SQLite.

## Requirements

- Windows with Python 3.10+ and Node.js/npm
- Optional: Tesseract OCR for image-based invoices and scanned PDFs.

## Install

Run these commands from the project root (`D:\Invoice Detective AI`) in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Set-Location .\frontend
npm ci
Set-Location ..
```

The root `requirements.txt` pins backend and test dependencies. `frontend\package-lock.json` locks the Vite/React dependencies.

Optionally copy `.env.example` to `.env` to override local settings. Keep actual secrets in `.env`, which is ignored by Git. Demo-data seeding is disabled by default; set `SEED_DEMO_DATA=true` only when intentionally populating a disposable database with labeled examples.

## Start the application

Use two PowerShell terminals. Start the backend from the project root:

```powershell
Set-Location 'D:\Invoice Detective AI'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Start Vite from the frontend folder:

```powershell
Set-Location 'D:\Invoice Detective AI\frontend'
npm run dev
```

Vite uses port 5174 and refuses to silently select another port. The frontend calls `http://127.0.0.1:8000/api` by default. Override this with `VITE_API_BASE_URL` in the frontend environment if needed. Local Vite origins on ports 5173 and 5174 are allowed by the backend CORS configuration.

- Website: <http://localhost:5174/>
- API health: <http://127.0.0.1:8000/health>
- API documentation: <http://127.0.0.1:8000/docs>
- Invoice API prefix: `/api` (for example, `/api/invoices`)

## Local data

- SQLite database: `invoice_detective.db` in the project root
- Uploaded files: `uploads\`
- Reports: `reports\`

Relative paths are resolved from the directory where the backend is started. The application initializes missing database tables and applies additive SQLite column upgrades without dropping existing tables or records. On first account creation, previously unassigned invoices are associated with that account's workspace; records are preserved. Existing SQLite monetary columns are not rebuilt; calculations use decimal arithmetic after values are loaded, and the API keeps returning JSON numbers for compatibility.

The local UI starts at a sign-in screen. Use **Create a workspace** to create a local account, or sign in with an existing account. Registration and login require both a loopback-configured backend `HOST` and a loopback client connection. Each account receives a separate workspace.

## Invoice processing notes

- Uploads accept PDF, JPG/JPEG, and PNG, with extension, MIME, size, and signature checks.
- The upload form reads the configured size limit from the privacy endpoint (`MAX_FILE_SIZE_MB`, default 20 MB) and performs early extension/MIME checks; the backend remains authoritative.
- Text-based PDFs are read with PyMuPDF and fields are extracted using deterministic patterns; review and correct extracted values before relying on them.
- OCR for image uploads and scanned PDFs requires the Python wrapper (included in `requirements.txt`) and a local Tesseract executable.
- On Windows, install Tesseract using the [UB Mannheim Windows installer](https://github.com/UB-Mannheim/tesseract/wiki), then open a new PowerShell and verify it with `tesseract --version`. If it is not on `PATH`, set `TESSERACT_PATH` in `.env` to the full executable path (commonly `C:\Program Files\Tesseract-OCR\tesseract.exe`) and restart the backend.
- The backend uses only local OCR. When Tesseract is unavailable, the invoice remains saved with a failed extraction status and a clear error; no remote OCR service is contacted.
- Deterministic parsing captures common invoice fields, line items, discounts, and vendor address when labeled. Review extracted values before relying on them.
- Duplicate and arithmetic checks are deterministic review indicators, not fraud determinations. Exact duplicate uploads are rejected; potential matching records and check findings require human review.
- Extracted fields and line items can be corrected in the invoice review panel. Findings can be marked for review, and invoice records/files can be deleted from the local application.

## Dashboard and module availability

- Dashboard invoice totals and duplicate-flagged values are grouped by currency; monthly activity, vendor spend, review counts, and recent invoices come from the authenticated workspace database.
- CSV export is available for saved invoice records and findings. PDF reports are not implemented.
- Purchase orders support workspace-scoped CRUD and invoice comparison. Vendor intelligence is derived from saved workspace invoices; settings and privacy exports use saved local preferences and data. Contact details and payment tracking are not inferred from invoices.
- Filtered CSV reports are available. PDF reports, teams/invitations, external vendor verification, and live payment processing are not implemented.

## Privacy and security limits

- The API binds to loopback by default and stores the SQLite database, uploaded files, and reports on the local machine. The privacy panel reports the configured local storage paths.
- Passwords are hashed with scrypt; the database stores only SHA-256 hashes of random bearer tokens. Sessions expire after 12 hours and are revoked when the user signs out. The browser keeps the token in tab-scoped `sessionStorage`.
- Because page scripts can access `sessionStorage`, production deployment also requires a reviewed XSS/CSP strategy and safer session transport.
- Invoice, finding, duplicate, PO, dashboard, source-file, privacy, and CSV operations require a valid session and are scoped to the user's workspace.
- Invoice data is not sent to a third-party service by the application. Do not expose the development API or Vite server to a public or shared network.
- This is a local-development security foundation, not production-ready authentication. Email verification, password reset, rate limiting, MFA, workspace invitations, complete role-based permissions, production cookie/session controls, and an external security review are not implemented. Do not use it as a public SaaS service.
- Subscription and payment processing are not implemented. Do not add live payment credentials or treat client-side payment results as verified.
- Back up the database and uploaded files together before moving or cleaning local data. Deleting an invoice in the application removes its associated stored file and records.

## Tests and build

```powershell
Set-Location 'D:\Invoice Detective AI'
.\.venv\Scripts\python.exe -m pytest -q
Set-Location .\frontend
npm run build
```

There is no standalone frontend unit-test runner configured; the frontend is type-checked and production-built with the build command above. Backend integration tests use synthetic invoices and temporary SQLite databases.
