"""
Remote Packager Module
Generates a downloadable, self-contained Python Remote API server package as a ZIP archive
incorporating the current branch schema, settings, and endpoints.
"""
import io
import zipfile
import json
import logging
from app.core.database import get_db

logger = logging.getLogger(__name__)

REMOTE_SERVER_PY_TEMPLATE = '''"""
Illy Specialty Coffee - Remote Ingestion & Central Storage Server
Generated standalone receiver server for branch synchronization.
"""
from flask import Flask, request, jsonify
import sqlite3
import os

app = Flask(__name__)
DB_PATH = os.environ.get("REMOTE_DB_PATH", "remote_coffeeshop.db")
SECRET_TOKEN = os.environ.get("REMOTE_SYNC_TOKEN", "")
if not SECRET_TOKEN:
    raise RuntimeError("REMOTE_SYNC_TOKEN must be configured before starting the receiver")

def init_remote_db():
    conn = sqlite3.connect(DB_PATH)
    with open("schema.sql", "r") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({{"status": "ok", "server": "Illy Central Sync Receiver v1.0"}}), 200

@app.route("/api/sync/batch", methods=["POST"])
def sync_batch():
    auth = request.headers.get("Authorization", "")
    if SECRET_TOKEN and auth != f"Bearer {{SECRET_TOKEN}}":
        return jsonify({{"error": "Unauthorized sync attempt"}}), 401

    data = request.get_json(force=True) or {{}}
    records = data.get("records", [])

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    ingested = 0
    for r in records:
        table = r.get("table_name")
        rec_id = r.get("record_id")
        action = r.get("action")
        payload = r.get("payload_json", "{{}}")
        cursor.execute(
            """
            INSERT INTO sync_ingested_events (table_name, record_id, action, payload_json)
            VALUES (?, ?, ?, ?)
            """,
            (table, rec_id, action, payload),
        )
        ingested += 1
    conn.commit()
    conn.close()

    return jsonify({{"status": "success", "ingested_count": ingested}}), 200

if __name__ == "__main__":
    init_remote_db()
    port = int(os.environ.get("PORT", 8080))
    print("Starting Illy Remote Sync Server on port " + str(port) + "...")
    app.run(host="0.0.0.0", port=port)
'''

def generate_remote_code_zip() -> bytes:
    """Generate in-memory zip archive with complete remote server codebase and current schema."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL")
        ddl_statements = [row[0] for row in cursor.fetchall()]

        # Add ingestion events table to remote schema
        ddl_statements.append("""
        CREATE TABLE IF NOT EXISTS sync_ingested_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT NOT NULL,
            record_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        schema_sql = ";\n\n".join(ddl_statements) + ";\n"

        # Get current sync token
    server_code = REMOTE_SERVER_PY_TEMPLATE

    config_json = json.dumps({
        "server_title": "Illy Specialty Coffee Remote Server",
        "sync_token": "Set REMOTE_SYNC_TOKEN in the remote server environment",
        "recommended_port": 8080,
        "database_type": "sqlite_wal_or_postgresql",
    }, indent=2)

    readme_md = """# Illy Specialty Coffee - Remote Server Package

Bu paket lokal qəhvəxana sistemindən məlumatları uzaq mərkəzi serverə qəbul etmək üçün yaradılmışdır.

## Quraşdırma və Başlatma:

1. Asılılıqları quraşdırın:
```bash
pip install flask requests
```

2. Serveri başladın:
```bash
python server.py
```

Server standart olaraq `8080` portunda işə düşəcək və filialdan gələn sinxronizasiya sorğularını qəbul edəcək.

Təhlükəsizlik üçün token paketə yazılmır. Başlatmadan əvvəl eyni gizli tokeni təyin edin:
```bash
export REMOTE_SYNC_TOKEN='uzun-rastgele-sync-token'
python server.py
```
"""

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("server.py", server_code)
        zf.writestr("schema.sql", schema_sql)
        zf.writestr("remote_config.json", config_json)
        zf.writestr("requirements.txt", "flask>=3.0.0\nrequests>=2.30.0\n")
        zf.writestr("README.md", readme_md)

    zip_buffer.seek(0)
    return zip_buffer.getvalue()
