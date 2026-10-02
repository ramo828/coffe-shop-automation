"""
System Configuration Module
Illy-Style Specialty Coffee Shop Management System
"""
import os
import secrets
import logging
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
IS_PRODUCTION = os.environ.get("COFFEE_ENV", "development").lower() == "production"
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True, parents=True)

# Database configuration
DB_PATH = DATA_DIR / "coffeeshop.db"
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(exist_ok=True, parents=True)

# Security & JWT settings
_configured_secret = os.environ.get("COFFEE_APP_SECRET")
_secret_file = DATA_DIR / ".app_secret"
if _configured_secret:
    APP_SECRET = _configured_secret
elif IS_PRODUCTION:
    raise RuntimeError("COFFEE_APP_SECRET must be set in production.")
else:
    try:
        APP_SECRET = _secret_file.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        APP_SECRET = secrets.token_urlsafe(48)
        _secret_file.write_text(APP_SECRET + "\n", encoding="utf-8")
        try:
            os.chmod(_secret_file, 0o600)
        except OSError:
            pass
    if not APP_SECRET:
        raise RuntimeError("Development application secret file is empty.")
SECRET_KEY = APP_SECRET
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("COFFEE_ACCESS_TOKEN_MINUTES", "60"))
INACTIVITY_TIMEOUT_MINUTES = 30  # Auto-lock session after 30 mins
PASSWORD_RESET_TOKEN_MINUTES = 15

# Optional password-reset mail/temporary remote access configuration.
# SMTP credentials are intentionally environment-driven by default. Admins may
# save them in the protected settings UI when a local deployment requires it.
SMTP_HOST = os.environ.get("COFFEE_SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("COFFEE_SMTP_PORT", "587"))
SMTP_USERNAME = os.environ.get("COFFEE_SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("COFFEE_SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("COFFEE_SMTP_FROM", SMTP_USERNAME)
SMTP_USE_TLS = os.environ.get("COFFEE_SMTP_USE_TLS", "1").lower() not in {"0", "false", "no"}
BORE_ENABLED = os.environ.get("COFFEE_BORE_ENABLED", "0").lower() in {"1", "true", "yes"}
BORE_BIN = os.environ.get("COFFEE_BORE_BIN", "bore")
BORE_SERVER = os.environ.get("COFFEE_BORE_SERVER", "bore.pub")
BORE_LOCAL_PORT = int(os.environ.get("COFFEE_BORE_LOCAL_PORT", "8000"))

# Trial & License settings
TRIAL_DURATION_DAYS = 7
LICENSE_SALT = f"{APP_SECRET}:license-salt"

# Multi-branch readiness
DEFAULT_BRANCH_ID = 1
DEFAULT_BRANCH_NAME = "Illy Specialty Coffee - Mərkəz Filial"
DEFAULT_BRANCH_CODE = "ILLY-BAKU-01"

# Developer bootstrap credentials.  The first development start creates a
# protected, random password file; no password is embedded in the source.
DEVELOPER_USERNAME = "developer"
DEVELOPER_PASSWORD_FILE = DATA_DIR / ".developer_password"
DEVELOPER_CODE_PASSWORD = os.environ.get("DEV_MASTER_PASSWORD")
DEVELOPER_PASSWORD_WAS_GENERATED = False
if not DEVELOPER_CODE_PASSWORD and IS_PRODUCTION:
    raise RuntimeError("DEV_MASTER_PASSWORD must be set in production.")
if not DEVELOPER_CODE_PASSWORD:
    try:
        DEVELOPER_CODE_PASSWORD = DEVELOPER_PASSWORD_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        DEVELOPER_CODE_PASSWORD = secrets.token_urlsafe(24)
        DEVELOPER_PASSWORD_WAS_GENERATED = True
        DEVELOPER_PASSWORD_FILE.write_text(DEVELOPER_CODE_PASSWORD + "\n", encoding="utf-8")
        try:
            os.chmod(DEVELOPER_PASSWORD_FILE, 0o600)
        except OSError:
            pass
        # Deliberately print only at first-run generation so operators can
        # capture the credential without it being logged on every startup.
        print(f"Initial developer password (save it securely): {DEVELOPER_CODE_PASSWORD}", flush=True)
if not DEVELOPER_CODE_PASSWORD:
    raise RuntimeError("Developer password file is empty.")

# Data Retention Options
RETENTION_POLICIES = ["1_week", "1_month", "1_year", "never"]
