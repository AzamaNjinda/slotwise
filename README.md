# Slotwise

**Shared spaces, thoughtfully booked.** A full-stack portfolio application for reserving meeting rooms, desks, and creative studios.

Built by Azama Njinda with AI coding assistance. This is an independent demonstration project with fictional people and workspace data.

![Slotwise workspace dashboard](docs/desktop.jpg)

## What it does

- Search spaces by name or floor, filter by type, and see each day’s reservations.
- Book in the workspace’s time zone; the API stores timezone-aware timestamps.
- Prevent overlapping confirmed reservations, enforce capacity and opening hours, and allow adjacent bookings.
- Cancel your reservations; workspace managers can cancel any reservation in their workspace.
- Managers can add, edit, or archive spaces while preserving booking history.
- Isolate workspace data through server-side membership checks.
- Retry booking requests using an idempotency key without creating duplicates.
- Use session authentication with CSRF-protected login and writes.

## Stack

React 19 · TypeScript · Vite 8 · Django 5.2 · Django REST Framework · PostgreSQL · OpenAPI · GitHub Actions

```mermaid
flowchart LR
    Browser[React dashboard] -->|Same-origin session + CSRF| API[Django REST API]
    API --> Scope[Workspace membership checks]
    Scope --> Booking[Booking service / transaction]
    Booking -->|Lock resource row; check overlap| DB[(PostgreSQL)]
```

## Run locally

Requires Python 3.12+ and Node.js 24. PostgreSQL is recommended; SQLite is the default for a quick single-user preview.

From the repository root, on Windows PowerShell:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
cd backend
../.venv/Scripts/python.exe manage.py migrate
../.venv/Scripts/python.exe manage.py seed_demo --password 'Slotwise-demo-only!'
../.venv/Scripts/python.exe manage.py runserver 127.0.0.1:8000
```

On macOS/Linux, use `.venv/bin/python` instead of `.venv/Scripts/python.exe` (and `../.venv/bin/python` from `backend`).

In a second terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open **http://127.0.0.1:5173**. Vite proxies `/api` to Django on port 8000.

| Local demo account | Role |
| --- | --- |
| manager@example.invalid | Workspace manager |
| member@example.invalid | Workspace member |

Both use the password supplied to the seed command. The example password is disposable and intended only for local development. The command refuses to run with `DEBUG=false`, preserves existing passwords, and seeds bookings for the current workspace day. Run it again on another day to populate that day.

## PostgreSQL

Create an empty database and set `DATABASE_URL` before running migrations and tests. For example in PowerShell:

```powershell
$env:DATABASE_URL = 'postgres://slotwise:YOUR_LOCAL_PASSWORD@127.0.0.1:5432/slotwise'
```

Environment variables are read from the process; `.env` files are not loaded automatically. Never commit credentials.

## Verification

From `backend`, using your virtual environment’s Python:

```sh
python manage.py test bookings --verbosity 2
python manage.py makemigrations --check --dry-run
python manage.py spectacular --validate --fail-on-warn --file schema.yml
```

From `frontend`:

```sh
npm ci
npm run build
```

The API suite checks booking overlap, adjacent slots, workspace isolation, roles, cancellation, capacity, opening hours, idempotency, input validation, and CSRF login. A separate concurrent-request test runs only on PostgreSQL. CI provisions PostgreSQL 17 for that test; SQLite skips it because SQLite cannot provide equivalent row locks.

Interactive API reference: **http://127.0.0.1:8000/api/docs/**. Sign in through the web app first; API writes also require the session’s CSRF token.

| Endpoint | Purpose |
| --- | --- |
| GET /api/csrf/ | Obtain a CSRF token and cookie |
| POST /api/login/ | Sign in with username and password; returns rotated CSRF token |
| POST /api/logout/ | End the session |
| GET /api/session/ | Current user and accessible workspaces |
| GET, POST /api/resources/ | List spaces / manager creates a space |
| PATCH /api/resources/{id}/ | Manager edits or archives a space |
| GET /api/bookings/?date=YYYY-MM-DD | Reservations intersecting the workspace day |
| POST /api/bookings/ | Create a reservation |
| POST /api/bookings/{id}/cancel/ | Cancel an authorised reservation |
| GET /health/ | Database connectivity check |

Resource and booking endpoints accept `?workspace=UUID`. Omitting it selects the user’s first workspace. Access is always checked server-side.

## Engineering decisions and limits

**Concurrency.** API booking writes lock the resource row inside a database transaction before checking interval overlap. Cancellation and capacity changes acquire the same resource lock. This requires PostgreSQL for concurrent use. Direct SQL/ORM writes bypass the application overlap rule; no database exclusion constraint is claimed. The booking admin is read-only.

**Idempotency.** An optional `Idempotency-Key` header is scoped to the authenticated user. Repeating the same payload returns the existing booking; reusing the key with a different payload returns HTTP 409. Keys remain with booking history and are not automatically expired.

**Time zones.** The server combines a date and local clock times using the workspace IANA time zone. It rejects ambiguous and nonexistent times during daylight-saving transitions. Reservations must start and finish on the same local day and fit within opening hours.

**Permissions.** Members can view their workspace’s active spaces and team schedule, create bookings, and cancel their own reservations. Managers also manage resources and cancel others’ reservations. Accounts and workspace membership are provisioned through Django admin; this demo has no public registration or billing.

**Deployment boundary.** This repository is a development portfolio, not a production service. Before deploying: use PostgreSQL, a unique `SECRET_KEY`, `DEBUG=false`, explicit `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`, HTTPS with same-origin frontend/API routing, and a production WSGI server. Configure backups, monitoring, and shared rate limiting. The included in-process login throttle is not a distributed abuse-prevention system. The seed data and demo credentials must never be used for a production workspace.

**Deliberate scope.** No recurring bookings, email invitations, payments, or availability guarantees outside the server validation. Archived spaces retain existing bookings. The team schedule intentionally shares booking titles with members of the same workspace; do not store confidential meeting content in a demo.
