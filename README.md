# Event Flow Management System
<!-- comment -->
Multi-step event creation with revision tracking, media versioning, draft support, and applicability controls.

## Prerequisites

- Docker (for PostgreSQL)
- Python 3.11+
- Node.js 18+

## Quick Start

**Important:** Start the database first (step 1). If you start the backend without it, you'll get a connection refused error on port 5432.

### 1. Start the database

From the project root (`event-flow/`):

```bash
docker compose up -d
```

Wait a few seconds for PostgreSQL to be ready, then continue.

### 2. Start the backend

```bash
cd backend
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
# source venv/bin/activate

pip install -r requirements.txt

# Seed the database with reference data and a test user
python -m app.seed

# Run the server
uvicorn app.main:app --reload --port 8000
```

### 3. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

### 4. Login

Open http://localhost:5173 and log in with:

- **Email:** admin@eventflow.local
- **Password:** admin123

## API Documentation

Once the backend is running, visit http://localhost:8000/docs for the interactive Swagger UI.

## Architecture

- **Backend:** FastAPI + SQLAlchemy (async) + PostgreSQL
- **Frontend:** React + TypeScript + Vite
- **Storage:** Local filesystem (S3-ready via storage abstraction)

## Key Concepts

- **Revision:** A snapshot of event details. Any change to details or media creates a new revision.
- **Media Version:** Files are grouped by version number. Full-snapshot approach (each version stores all items).
- **Draft:** Events can be saved as drafts. Editing a published event creates a child draft linked via `draft_parent_id`.
- **Dedup:** Files are hashed (SHA256) on upload. Duplicate files are reused, not re-stored.
