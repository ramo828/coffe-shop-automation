# Deployment

## Docker Compose (recommended)

1. Copy the example values below into a local `.env` file (never commit it):

```dotenv
COFFEE_APP_SECRET=replace-with-a-long-random-secret
DEV_MASTER_PASSWORD=replace-with-a-strong-password
COFFEE_PORT=8000
```

2. Build and start the service:

```bash
docker compose up -d --build
```

3. Verify readiness and logs:

```bash
curl http://localhost:8000/api/health
docker compose ps
docker compose logs -f coffee-shop
```

The named `coffee_data` volume persists the SQLite database, backups, and secret. Stop without deleting data with `docker compose down`; do not use `down -v` unless data loss is intended. The image runs as the unprivileged `coffee` user and exposes port 8000. Put an HTTPS reverse proxy in front of it for remote access.

## Pip installation

Python 3.12 or newer is supported. Create an isolated environment and install the pinned dependencies:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python run.py --init-db
python run.py --seed                 # optional demo data
python run.py --host 127.0.0.1 --port 8000
```

For production, set `COFFEE_ENV=production`, `COFFEE_APP_SECRET`, and `DEV_MASTER_PASSWORD` before starting. Run behind TLS termination and restrict filesystem permissions on `data/`.

## Operations and backups

Use `GET /api/health` for monitoring. Create and verify backups from the developer backup API or copy the persistent data volume while the service is stopped. Test restore procedures before relying on them. Rotate secrets through the deployment environment, not source control. SMTP and synchronization settings are optional environment variables documented in `app/core/config.py`.
