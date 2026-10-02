"""
Coffee Shop Application Server Runner
Illy-Style Specialty Coffee Shop Management System
"""
import sys
import argparse
import logging
import os
from app.main import create_app
from app.core.database import init_db
from app.core.database import get_db
from seed import seed_database

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

def main():
    parser = argparse.ArgumentParser(description="Illy Specialty Coffee Shop Web System")
    parser.add_argument("--host", default=None, help="Host address to bind")
    parser.add_argument("--port", type=int, default=None, help="Port to listen on")
    parser.add_argument("--seed", action="store_true", help="Seed database with realistic initial menu and users")
    parser.add_argument("--init-db", action="store_true", help="Initialize schema tables only")
    args = parser.parse_args()

    if args.init_db:
        print("Initializing database...")
        init_db()
        print("Database initialized.")
        sys.exit(0)

    if args.seed:
        print("Seeding database...")
        seed_database()
        print("Database seeded.")
        sys.exit(0)

    app = create_app()
    with get_db() as conn:
        settings = {row["key"]: row["value"] for row in conn.execute(
            "SELECT key, value FROM system_settings WHERE key IN ('server_host', 'server_port')"
        ).fetchall()}
    host = args.host or settings.get("server_host", "127.0.0.1")
    port = args.port or int(settings.get("server_port", 8000))
    if host not in {"127.0.0.1", "localhost", "::1"} and not os.environ.get("COFFEE_ALLOW_REMOTE_DEMO") == "1":
        raise RuntimeError(
            "Remote binding is disabled by default. Use a local host or explicitly set "
            "COFFEE_ALLOW_REMOTE_DEMO=1 after configuring unique credentials and TLS."
        )
    print("=" * 60)
    print("  ILLY SPECIALTY COFFEE SHOP - İDARƏETMƏ VƏ NƏZARƏT SİSTEMİ")
    print(f"  URL: http://localhost:{port} və ya http://{host}:{port}")
    print("=" * 60)
    app.run(host=host, port=port, debug=False)

if __name__ == "__main__":
    main()
