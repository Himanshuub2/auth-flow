# Database setup (Event-Flow)

Use this guide to set up PostgreSQL for the Event-Flow backend on a new machine or for a new team member.

## Prerequisites

- **Python 3.10+** with the project dependencies installed (`pip install -r requirements.txt` or `poetry install`)
- **PostgreSQL 12+** installed and running
- **Alembic** (included in project deps)

## Option A: Fresh database using the combined migration (recommended for new setups)

One migration file creates the full schema (`events` and `documents`) in one go.

### 1. Create an empty database

```bash
# Using psql (replace with your PostgreSQL user and DB name)
psql -U postgres -c "CREATE DATABASE event_flow_db;"

# Or with a specific user
psql -U postgres -c "CREATE USER event_flow_user WITH PASSWORD 'your_password';"
psql -U postgres -c "CREATE DATABASE event_flow_db OWNER event_flow_user;"
psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE event_flow_db TO event_flow_user;"
```

### 2. Set the database URL

Create a `.env` in the backend root (or set environment variables):

```env
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/event_flow_db
```

For a sync URL (e.g. for Alembic), use:

```env
# If your app uses asyncpg, Alembic often needs the sync driver
# Use the same host/db/user/password with psycopg2 for migrations:
DATABASE_URL=postgresql://user:password@localhost:5432/event_flow_db
```

Check `backend/app/config.py` (or `alembic.ini`) for the variable name your project uses (e.g. `DATABASE_URL` or `ALEMBIC_DATABASE_URL`).

### 3. Use only the combined migration

So that Alembic has a single “head” and runs only the combined migration:

- **Either:** In `backend/alembic/versions/`, **temporarily move** all migration files **except** `0001_combined_init_events_documents.py` into a subfolder (e.g. `_archive/`), or delete them if you do not need the historical chain.

- **Or:** If your repo is already set up to use only the combined migration, skip this step.

### 4. Run migrations

From the **backend** directory:

```bash
cd backend
alembic upgrade head
```

You should see Alembic run the single revision `0001_combined` and create schemas `events` and `documents` with all tables.

### 5. Verify

```bash
psql -U postgres -d event_flow_db -c "\dn"
psql -U postgres -d event_flow_db -c "\dt events.*"
psql -U postgres -d event_flow_db -c "\dt documents.*"
```

You should see schemas `events` and `documents` and their tables (e.g. `events.users`, `events.events`, `documents.documents`, etc.).

---

## Option B: Fresh database using the full migration chain

If you keep all existing migration files and want to run them in order:

1. Create an empty database (same as Option A, step 1).
2. Set `DATABASE_URL` (same as Option A, step 2).
3. From the backend directory run:

   ```bash
   cd backend
   alembic upgrade head
   ```

   This runs every migration from the first to the last. The final state is the same as Option A (schemas `events` and `documents` with the same tables and columns).

---

## Commands reference

| Task              | Command                    |
|-------------------|----------------------------|
| Apply all migrations | `alembic upgrade head`  |
| Show current revision | `alembic current`     |
| Show migration history | `alembic history`   |
| Downgrade one step | `alembic downgrade -1`    |
| Downgrade all      | `alembic downgrade base`  |

---

## Schema overview (after setup)

- **`events`**  
  - `users` – app users  
  - `events` – event records  
  - `event_revisions` – event revision snapshots  
  - `files` – event media (images/videos)

- **`documents`**  
  - `legislation`, `sub_legislation` – reference data (seeded)  
  - `documents` – document records  
  - `document_revisions` – document revision snapshots  
  - `files` – document attachments  

---

## Troubleshooting

- **“Multiple head revisions”**  
  You have more than one migration with `down_revision = None`. Use only the combined migration (Option A, step 3) or remove the combined file and use the chain (Option B).

- **“relation already exists” / “schema already exists”**  
  The database was partially created. Either drop and recreate the database and run migrations again, or fix objects by hand and run `alembic stamp head` to mark the DB as up to date.

- **Async vs sync URL**  
  If Alembic fails with an async driver error, switch to a sync URL in the env (e.g. `postgresql://` with `psycopg2`) for running migrations; the app can still use `postgresql+asyncpg://`.

- **Permission errors**  
  Ensure the DB user has `CREATE` on the database and can create schemas and tables (e.g. grant `CREATE` on schema `public` if Alembic creates schemas from there, or use a superuser for initial setup).
