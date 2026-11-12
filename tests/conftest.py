import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", f"sqlite:///{ROOT / 'test_invoice_detective.db'}")
os.environ.setdefault("UPLOAD_DIR", str(ROOT / 'tests' / 'tmp_uploads'))
os.environ.setdefault("REPORT_DIR", str(ROOT / 'tests' / 'tmp_reports'))

from app.database import Base, engine

Base.metadata.create_all(bind=engine)
