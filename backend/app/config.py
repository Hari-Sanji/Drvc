"""Application configuration. Secrets and connection strings come from environment variables."""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

_env = BASE_DIR / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        if "=" in _line and not _line.lstrip().startswith("#"):
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))
DATA_DIR = Path(os.getenv("DRCV_DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

STORAGE_DIR = Path(os.getenv("DRCV_STORAGE_DIR", DATA_DIR / "storage"))
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

DEMO_FILES_DIR = BASE_DIR / "demo_files"
FRONTEND_DIST = Path(os.getenv("DRCV_FRONTEND_DIST", BASE_DIR.parent / "frontend" / "dist"))

# PostgreSQL is the primary database: postgresql+psycopg://user:pass@host:5432/drcv
# If DATABASE_URL is not set, a local SQLite file is used so the app runs with zero setup.
DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{(DATA_DIR / 'drcv.db').as_posix()}"
# Hosting platforms (Render, Railway, Heroku...) hand out "postgres://" or "postgresql://" URLs; use the psycopg3 driver.
for _old in ("postgres://", "postgresql://"):
    if DATABASE_URL.startswith(_old):
        DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len(_old):]
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)


def _load_secret() -> str:
    env = os.getenv("DRCV_SECRET_KEY")
    if env:
        return env
    # No hardcoded secret: generate once per installation and keep it in the data dir.
    path = DATA_DIR / ".secret_key"
    if path.exists():
        return path.read_text().strip()
    key = secrets.token_urlsafe(48)
    path.write_text(key)
    return key


SECRET_KEY = _load_secret()
JWT_ALGORITHM = "HS256"
TOKEN_TTL_HOURS = int(os.getenv("DRCV_TOKEN_TTL_HOURS", "12"))
REMEMBER_TTL_HOURS = int(os.getenv("DRCV_REMEMBER_TTL_HOURS", str(24 * 7)))

MAX_UPLOAD_MB = int(os.getenv("DRCV_MAX_UPLOAD_MB", "20"))
ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".docx", ".txt"}

CORS_ORIGINS = [o.strip() for o in os.getenv("DRCV_CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
