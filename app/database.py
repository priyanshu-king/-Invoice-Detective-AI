"""
Invoice Detective AI — Database Setup.

SQLAlchemy 2.0 synchronous setup with SQLite.
"""

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import settings


def _connect_args(database_url: str) -> dict[str, bool]:
    """Return only connection options supported by the configured database driver."""
    if make_url(database_url).get_backend_name() == "sqlite":
        return {"check_same_thread": False}
    return {}


engine = create_engine(settings.DATABASE_URL, connect_args=_connect_args(settings.DATABASE_URL), echo=False)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass


def get_db():
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def apply_sqlite_additive_upgrades(target_engine=engine) -> None:
    """Apply safe, additive SQLite column upgrades without removing stored data."""
    if target_engine.dialect.name != "sqlite":
        return

    additions = {
        "invoices": {
            "workspace_id": "INTEGER REFERENCES workspaces(id)",
            "tax_rate": "FLOAT",
            "vendor_address": "TEXT",
            "discount_amount": "NUMERIC(20, 4)",
            "extraction_method": "VARCHAR(50)",
            "processing_status": "VARCHAR(20) NOT NULL DEFAULT 'completed'",
            "processing_error": "TEXT",
        },
        "findings": {
            "suggested_action": (
                "TEXT NOT NULL DEFAULT 'Review the source invoice and supporting records. "
                "Correct inaccurate fields, then mark the finding reviewed or resolved.'"
            ),
        },
        "purchase_order_comparisons": {
            "po_currency": "VARCHAR(3)",
        },
        "purchase_orders": {
            "order_date": "DATE",
            "tax_rate": "FLOAT NOT NULL DEFAULT 0",
        },
        "purchase_order_line_items": {
            "amount": "NUMERIC(20, 4)",
        },
    }

    with target_engine.begin() as connection:
        inspector = inspect(connection)
        for table_name, columns in additions.items():
            if not inspector.has_table(table_name):
                continue
            existing = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, definition in columns.items():
                if column_name not in existing:
                    connection.execute(text(
                        f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {definition}'
                    ))
                    existing.add(column_name)
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_invoices_workspace_id ON invoices(workspace_id)"
        ))


def init_db() -> None:
    """Create missing tables and apply safe, additive SQLite column upgrades."""
    Base.metadata.create_all(bind=engine)
    apply_sqlite_additive_upgrades(engine)
