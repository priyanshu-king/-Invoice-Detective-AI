from pathlib import Path
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import SessionLocal, init_db
from app.routers.auth import router as auth_router
from app.routers.invoices import health_router, router as invoice_router
from app.routers.purchase_orders import router as purchase_orders_router
from app.routers.reports import router as reports_router
from app.routers.settings import router as settings_router
from app.routers.vendors import router as vendors_router
from app.services.demo_data import seed_demo_data

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / settings.UPLOAD_DIR
REPORT_DIR = BASE_DIR / settings.REPORT_DIR

for directory in [UPLOAD_DIR, REPORT_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="Invoice Detective AI",
    version="1.0.0-mvp",
    description="Local invoice auditing and duplicate detection MVP for small businesses.",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(invoice_router, prefix="/api")
app.include_router(purchase_orders_router, prefix="/api")
app.include_router(reports_router, prefix="/api")
app.include_router(vendors_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(health_router, prefix="/api")


@app.on_event("startup")
def startup_event() -> None:
    init_db()
    os.makedirs(str(UPLOAD_DIR), exist_ok=True)
    os.makedirs(str(REPORT_DIR), exist_ok=True)
    db = SessionLocal()
    try:
        if settings.SEED_DEMO_DATA:
            seed_demo_data(db)
    finally:
        db.close()


@app.get("/health")
def health() -> dict:
    return {
        "status": "healthy",
        "version": "1.0.0-mvp",
        "environment": settings.APP_ENV,
    }


@app.get("/")
def root() -> dict:
    return {
        "app": "Invoice Detective AI",
        "status": "online",
        "docs": "/docs",
    }
