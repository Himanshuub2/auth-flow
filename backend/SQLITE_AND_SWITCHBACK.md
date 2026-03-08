# SQLite (local/testing) and switching back to PostgreSQL

## Using SQLite (no cloud DB yet)

1. **Install deps** (includes `aiosqlite`):
   ```bash
   pip install -r requirements.txt
   ```

2. **Set connection string** in `backend/.env`:
   ```env
   DATABASE_URL=sqlite+aiosqlite:///./event_flow.db
   ```

3. **Run the SQLite migration** (separate branch from PostgreSQL). Ensure `DATABASE_URL` in `.env` is the SQLite URL above, then:
   ```bash
   cd backend
   alembic upgrade sqlite@head
   ```
   (If you see "Can't locate revision 0003_...", you're still pointed at a PostgreSQL DB or an old DB file; use a new `.db` file or set `DATABASE_URL` in `.env` to the SQLite URL.)

4. **Start the API**:
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0
   ```

The DB file is created in the current directory (e.g. `backend/event_flow.db`). It is ignored by git.

### Default test user (SQLite migration)

The SQLite migration inserts a default user for testing:

- **Email:** `divyanshu@test.com`
- **Password:** `test123`
- **Name:** divyanshu (is_admin = true)

Use this to log in via `/api/events/login` without registering.

### Skip login for testing (optional)

To call protected endpoints without sending a token:

1. In `backend/.env` add:
   ```env
   TESTING_SKIP_AUTH=true
   ```
2. The app will treat requests without a Bearer token as the default user (`divyanshu@test.com`) when that user exists in the DB.

Leave `TESTING_SKIP_AUTH` unset or `false` in production.

---

## Switching back to PostgreSQL (e.g. cloud creds)

No code removal needed. Everything is conditional on `DATABASE_URL`.

1. **Set PostgreSQL URL** in `backend/.env`:
   ```env
   DATABASE_URL=postgresql+asyncpg://user:password@host:5432/dbname
   ```
   (Use your cloud provider’s connection string.)

2. **Run PostgreSQL migrations** (default branch):
   ```bash
   cd backend
   alembic upgrade head
   ```
   This uses the original `0001_combined_init_events_documents.py` migration (schemas, enums, etc.). Do **not** run `alembic upgrade sqlite@head` when using PostgreSQL.

3. **Start the API** as usual. The app will use PostgreSQL.

---

## Optional: remove SQLite support later

If you no longer want SQLite at all:

- **Delete** `alembic/versions/0001_sqlite_init.py`.
- **Delete** `app/db_utils.py`.
- **Revert** model and config changes to use fixed `schema=`, `JSONB`, `ARRAY`, and table names (no `events_table()`, `json_type()`, etc.), and remove `aiosqlite` from `requirements.txt` and the SQLite branch from `alembic/env.py`.

Until then, leaving the current setup in place only affects behavior when `DATABASE_URL` contains `sqlite`; with a PostgreSQL URL, the app behaves as before.
