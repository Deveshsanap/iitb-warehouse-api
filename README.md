# Warehouse Management System — API

Django REST Framework API for the IIT Bombay design-round Warehouse
Management System (see the UI repository for `README.md`, `DESIGN.md`
and `AI_USAGE.md`). A 5×5 warehouse grid (A1–E5); A1 is the transfer
point, the other 24 locations each hold at most one pallet. Technicians
load/unload pallets, auditors inspect occupancy on a dashboard, admins
manage users. Auth is JWT.

## Supported runtime

- Python **3.12** (developed and verified on Python 3.12.3)
- Django 5.1, Django REST Framework 3.15, djangorestframework-simplejwt 5.3,
  django-cors-headers 4.6 (pinned in `requirements.txt`)

## Setup

```bash
python3.12 -m venv /tmp/iitb-venv-api   # or any venv location outside the repo
source /tmp/iitb-venv-api/bin/activate
pip install -r requirements.txt
python manage.py migrate --noinput
python manage.py seed_demo
python manage.py runserver 127.0.0.1:8000 --noreload
```

`seed_demo` is idempotent: run it as many times as you like — it never
duplicates demo users, locations, the shuttle, history snapshots or
sample pallets, and never deletes non-demo data.

## Environment variables

| Variable | Default | Notes |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` (or `SECRET_KEY`) | dev-only placeholder | Set a long random value in production/hosted deploys. |
| `DJANGO_DEBUG` (or `DEBUG`) | `False` | Set `True` for local development. |
| `DJANGO_ALLOWED_HOSTS` (or `ALLOWED_HOSTS`) | `127.0.0.1,localhost` | Comma-separated. |
| `CORS_ALLOWED_ORIGINS` | `http://127.0.0.1:5173,http://localhost:5173` | Comma-separated; set to the hosted UI origin when deployed. |
| `SQLITE_PATH` | `<repo root>/db.sqlite3` | SQLite file path (honoured for local evaluation). |
| `EVAL_ADMIN_USERNAME` / `EVAL_ADMIN_PASSWORD` | `demo_admin` | Demo admin account for `seed_demo`. |
| `EVAL_AUDITOR_USERNAME` / `EVAL_AUDITOR_PASSWORD` | `demo_auditor` | Demo auditor account. |
| `EVAL_TECHNICIAN_USERNAME` / `EVAL_TECHNICIAN_PASSWORD` | `demo_technician` | Demo technician account. |

Demo credentials: when the `EVAL_*` variables are absent, `seed_demo`
uses the demo username as both username and password (local dev only).
The evaluator supplies real, distinct passwords via `EVAL_*`; **never
put real passwords in the repo, docs or test logs.** Hosted deploys use
a persistent relational database (e.g. Postgres) instead of SQLite;
the models and API are unchanged.

## Demo accounts (usernames only — passwords are supplied separately)

| Username | Role |
| --- | --- |
| `demo_admin` | admin |
| `demo_auditor` | auditor |
| `demo_technician` | technician |

## Endpoints

All `/api/` endpoints except login require a JWT
(`Authorization: Bearer <access token>`). Login returns `access`,
`refresh` and `user: {username, role}`.

| Method & path | Roles | Description |
| --- | --- | --- |
| `GET /health/` | none (public) | `{"status": "ok"}` — readiness check. |
| `POST /api/auth/login/` | public | `{username, password}` → `{access, refresh, user}`. Wrong credentials → 401. |
| `GET /api/map/` | any authenticated | `{"locations": [{code, is_transfer_point, occupied, pallet: null \| {pallet_number, barcode, item, quantity}} × 25]}` (codes A1–E5). |
| `POST /api/load/` | technician, admin | `{pallet_number, barcode, item, quantity, destination}` → 201 with the created pallet (`location` = destination code, plus `location_detail`). 400 `{"detail": ...}` when: destination is A1, destination code invalid, destination occupied, pallet number already exists, quantity ≤ 0 (or missing/invalid), or a required field is missing. |
| `POST /api/unload/` | technician, admin | `{location}` → 200 `{"detail": ..., "location": {...}}`. The pallet's location is set to null (removed from stock, row kept for history). 400 when the location is free, is A1, or the code is invalid. |
| `GET /api/shuttle/` | any authenticated | `{"identifier", "status", "battery_percent"}` from the DB (seeded `SH-01`, `idle`, `87`). |
| `GET /api/dashboard/` | auditor, admin | `{"occupied", "free", "history": [{date, occupied, free} × 7 days], "pallets": [...]}` — `pallets` are the currently stocked pallets with their location. |
| `GET /api/admin/users/` | admin | List users with roles. |
| `POST /api/admin/users/` | admin | `{username, password, role}` → 201. |
| `PATCH /api/admin/users/<id>/` | admin | `{role and/or password}`. |
| `DELETE /api/admin/users/<id>/` | admin | 204. Refused (400) when deleting the last admin or your own account; demoting the last admin is likewise refused. |

Wrong role → 403; no/invalid token → 401.

## Design decisions (brief leaves these open)

- **Occupancy is derived, never stored:** a location is occupied iff a
  pallet points at it. One pallet per storage location is enforced by
  the load check (and a location holds at most one pallet by
  construction — `Location.pallet` returns the single related pallet).
- **Unload keeps the pallet row** with `location = null`, so history is
  preserved; the pallet is out of stock and no longer counts as
  occupied. `pallet_number` is unique across all time (never reused),
  which is why a load with an already-used number is rejected even
  after that pallet was unloaded.
- **A1 never holds a stored pallet:** loading to A1 is a 400, and
  unloading A1 itself is a 400 (unload a storage location; the pallet
  conceptually returns through A1 and leaves stock).
- **Operations complete immediately:** no shuttle movement simulation
  or animation, per the brief. The shuttle row is read-only via the API
  (no status-edit endpoint); its values come from the database.
- **History is sample data:** the dashboard's 7-day history covers the
  6 days before today with fixed deterministic values
  (`[2, 4, 3, 5, 4, 6]` occupied out of 24) plus today, which the seed
  sets to the actual current stocked count — so the chart's last point
  always agrees with the live occupied/free counts. `free = 24 − occupied`.
- **Auditor is read-only everywhere:** the only write endpoints (load,
  unload, user admin) require technician/admin or admin, so an auditor
  gets 403 on all of them.
- **Users without a Profile** (e.g. created via Django admin) default
  to the technician role on first login.

## Verification (run 27 Nov 2026, local)

```bash
python manage.py check
python manage.py migrate --noinput
python manage.py seed_demo            # run twice: no duplicate demo users
python manage.py runserver 127.0.0.1:8000 --noreload
curl http://127.0.0.1:8000/health/
# login as each demo role, GET /api/map/, POST /api/load/ then
# POST /api/unload/ the same location, GET /api/shuttle/,
# GET /api/dashboard/ as auditor; 403s: auditor POST /api/load/,
# technician GET /api/dashboard/, and 401 unauthenticated GET /api/map/
```

All checks passed on 27 Nov 2026 (see the build report for exact
commands and outputs). No test suite is bundled with the API repo yet —
Playwright end-to-end tests live in the UI repository and exercise this
API over HTTP.

## Known limitations

- SQLite locally; hosted deploys should use Postgres (set
  `DATABASE_URL`-style config at deploy time — not yet wired; Day 2).
- No pagination on the admin user list (fine at this scale).
- No shuttle status editing, battery simulation or hardware integration
  (explicitly out of scope per the brief).
