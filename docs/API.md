# Illy API reference

The local Flask server exposes JSON endpoints under `/api`. Start it with
`python run.py --host 127.0.0.1 --port 8000`. Protected endpoints require:

```http
Authorization: Bearer <JWT>
Content-Type: application/json
```

Errors use `{ "error": "..." }`. Roles are enforced server-side: `barista`,
`admin`, and `developer`. IDs in path parameters are integers.

## Public and setup

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | SQLite/application health check |
| GET | `/api/branches` | List branches |
| POST | `/api/branches` | Create a branch (admin/developer) |
| GET | `/api/setup/status` | Read first-run setup state |
| POST | `/api/setup/complete` | Complete one-time local/demo setup |
| GET | `/api/license/status` | Read license state |
| POST | `/api/license/activate` | Activate a license |

## Authentication and users

| Method | Endpoint | Body/query | Purpose |
|---|---|---|---|
| GET | `/api/auth/profiles` | — | List selectable login profiles |
| POST | `/api/auth/login-profile` | `{ profile_id, password }` | Login by profile |
| POST | `/api/auth/login-other` | `{ username, password }` | Login by username |
| GET | `/api/auth/me` | — | Current authenticated user |
| POST | `/api/auth/forgot-password` | `{ identifier }` | Start email/local reset flow |
| POST | `/api/auth/reset-password` | `{ token, password }` | Set a new password |
| PUT | `/api/auth/profile` | Profile/password fields | Update own profile |
| PUT | `/api/users/me/language` | `{ language }` | Save own language |
| PUT | `/api/users/me/preferences` | Theme/font/avatar fields | Save own preferences |
| GET | `/api/users` | — | List users (admin/developer) |
| POST | `/api/users` | User fields | Create a user |
| PUT | `/api/users/{id}` | User fields | Update a user |
| DELETE | `/api/users/{id}` | — | Delete/deactivate a user |
| GET/POST | `/api/admin/mail-settings` | SMTP fields | Read/save reset-mail settings |

## Alerts, products, recipes, and stock

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/alerts` | List active stock/business alerts |
| POST | `/api/alerts/{id}/acknowledge` | Acknowledge an alert |
| GET | `/api/products` | List products with variants |
| POST | `/api/products` | Create product and optional initial variants |
| PUT | `/api/products/{id}` | Update product |
| DELETE | `/api/products/{id}` | Delete product, variants, recipes, shortcuts |
| POST | `/api/products/{id}/variants` | Add a variant (`name`, positive `price`, optional `sku`) |
| DELETE | `/api/products/variants/{id}` | Delete one variant and its recipes |
| POST | `/api/products/reorder` | Reorder catalog products |
| GET | `/api/recipes/{variant_id}` | Read variant ingredients |
| POST | `/api/recipes/{variant_id}` | Replace ingredients (`ingredients` array) |
| DELETE | `/api/recipes/{recipe_id}` | Delete one recipe ingredient |
| DELETE | `/api/recipes/variant/{variant_id}` | Clear a variant recipe |
| GET | `/api/stock` | List raw materials and stock levels |
| POST | `/api/stock` | Create raw material |
| PUT | `/api/stock/{id}` | Update raw material |
| DELETE | `/api/stock/{id}` | Delete raw material |
| POST | `/api/stock/{id}/restock` | Add stock (`quantity`, optional `notes`) |
| GET | `/api/reports/stock-depletion` | Stock depletion projection |

## POS, orders, shifts, and inventory

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/orders` | Create an order; server validates catalog prices |
| GET | `/api/orders/recent` | Recent orders |
| GET | `/api/orders/{id}/ticket` | Render/read order ticket data |
| POST | `/api/orders/{id}/cancel` | Cancel an order |
| GET, POST | `/api/cash-movements` | List or record till movements (`direction`: `in`/`out`, amount, debt flags, shift and note) |
| GET/POST | `/api/shortcuts` | Read/create user shortcuts |
| POST | `/api/shortcuts/add` | Add a variant shortcut |
| PUT/DELETE | `/api/shortcuts/{id}` | Update/delete shortcut |
| POST | `/api/shortcuts/reorder` | Reorder shortcuts |
| GET | `/api/icons/presets` | List built-in product icons |
| POST | `/api/upload` | Upload a validated same-origin icon |
| GET | `/api/shifts/active` | Current open shift |
| POST | `/api/shifts/open` | Open a shift |
| GET | `/api/shifts` | List shifts |
| POST | `/api/shifts/{id}/close` | Close a shift |
| POST | `/api/inventory/start` | Start physical count |
| GET/PUT | `/api/inventory/{id}` | Read/update count |
| POST | `/api/inventory/{id}/confirm` | Confirm count |
| GET | `/api/inventory` | List inventory counts |

## Reports and automation

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/orders` | Create a validated sale |
| GET | `/api/reports/overview` | KPI overview |
| GET | `/api/reports/sales?period=daily|weekly|monthly|yearly|all&date=YYYY-MM-DD` | Calendar-aware summary and zero-filled chart series |
| GET | `/api/reports/end-of-day?preset=today|yesterday|this_week|last_week|this_month` | Detailed reconciliation; use `preset=custom&start=YYYY-MM-DD&end=YYYY-MM-DD` for a custom range |
| GET | `/api/reports/daily` | Daily sales |
| GET | `/api/reports/hourly` | Hourly sales |
| GET | `/api/reports/top-products` | Best-selling products |
| GET | `/api/reports/baristas` | Barista results |
| GET | `/api/reports/employees/{id}` | Employee report |
| GET | `/api/reports/depletion` | Material depletion |
| GET | `/api/reports/export` | Export report |
| GET | `/api/ml/recommendations` | Operational recommendations |
| GET | `/api/ml/metrics` | ML metrics |
| GET/POST | `/api/retention` | Read/save retention policy |
| POST | `/api/retention/run` | Run retention cleanup |

## Synchronization, developer, and backup

| Method | Endpoint | Purpose |
|---|---|---|
| GET/POST | `/api/sync/config` | Read/save synchronization settings |
| POST | `/api/sync/test` | Test configured sync |
| POST | `/api/sync/now` | Run one synchronization |
| POST | `/api/sync/all` | Synchronize all supported data |
| GET | `/api/sync/download-package` | Download sync package |
| GET | `/api/developer/diagnostics` | Runtime diagnostics |
| POST | `/api/developer/branding` | Update branding |
| POST | `/api/developer/encryption` | Configure encryption |
| POST | `/api/developer/compression` | Configure compression |
| GET/POST | `/api/backup` | List/create backup |
| GET | `/api/backup/integrity` | Check backup/database integrity |
| POST | `/api/backup/vacuum` | Compact database |
| POST | `/api/backup/restore` | Restore an approved backup |
| GET/PUT | `/api/developer/network-settings` | Read/update local network settings |
| GET | `/api/developer/audit-logs` | Query audit logs |
| POST | `/api/developer/generate-key` | Generate a developer key |
| GET | `/api/developer/export/sql` | Export SQL |
| GET | `/api/developer/export/json` | Export JSON |
| GET | `/api/developer/export/txt` | Export text |

## Security notes

Keep the server bound to `127.0.0.1` for demo/local use. Do not put JWTs or
application secrets in browser code. Product prices and discounts are checked
on the server; clients must treat API responses as authoritative.
