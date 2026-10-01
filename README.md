# Nexus Support

A full-stack technical support knowledge search app built with FastAPI, SQLAlchemy, SQLite, and a responsive HTML/CSS/JavaScript dashboard. It includes grounded knowledge retrieval, optional Gemini embeddings and answer generation, user/agent/admin roles, document ingestion, and support ticket workflows.

## Features

- Email/password registration and login, Argon2 password hashes, signed bearer tokens, and role-based access.
- Natural-language search with error-message detection, category/technology/product/error/difficulty/tag/date filters, ranked source articles, and a clear no-match response.
- Optional Gemini embeddings for chunk-level cosine similarity, plus Gemini or Groq answer generation constrained to retrieved sources. Without a key, local lexical retrieval and knowledge-backed answers remain available.
- Knowledge articles seeded on first run, article authoring, and TXT/Markdown/PDF/DOCX text extraction with chunk storage.
- Tickets with priorities, statuses, agent assignment, comments, and resolved-case conversion to knowledge articles.
- Search history, popular queries, bookmarks, answer feedback, admin metrics/user-role management, and an agent queue view.
- SQLite by default; SQLAlchemy can target PostgreSQL with the included psycopg driver.

## Quick Start (Windows PowerShell)

Python 3.10+ is recommended.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and set `SECRET_KEY` to a long random value. To provision the first administrator on startup, set `ADMIN_EMAIL` and `ADMIN_PASSWORD` (at least 16 characters). Leave those unset for a regular user-only workspace. Register a user from the app, then sign in. An administrator can promote users to support agent or admin in the Admin console.

Start the app:

```powershell
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>. Interactive API documentation is at <http://127.0.0.1:8000/docs>. Sample technical articles are inserted automatically into an empty database.

## Configuration

| Variable | Purpose | Default |
| --- | --- | --- |
| `SECRET_KEY` | JWT signing secret; replace before deployment | Local development placeholder |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Bearer token lifetime | `720` |
| `DATABASE_URL` | SQLAlchemy connection string | `sqlite:///./support_knowledge.db` |
| `GEMINI_API_KEY` | Enables Gemini embeddings and answer generation; stays on the server | Empty (local retrieval) |
| `GEMINI_MODEL` | Gemini generation model | `gemini-2.5-flash` |
| `GROQ_API_KEY` | Enables Groq source-grounded chat answer generation; stays on the server | Empty |
| `GROQ_MODEL` | Groq chat model | `llama-3.3-70b-versatile` |
| `ADMIN_EMAIL` | Optional initial administrator email | Empty |
| `ADMIN_PASSWORD` | Optional initial administrator password, minimum 16 characters | Empty |

For PostgreSQL, use a SQLAlchemy URL such as `postgresql+psycopg://user:password@host:5432/database` and keep credentials in environment variables, not source control.

## Project Layout

```text
app/
  database.py       SQLAlchemy engine, session, and dependency
  main.py           FastAPI routes, validation, access control, and startup
  models.py         Users, articles/chunks, tickets/comments, searches, feedback, bookmarks
  security.py       Argon2 password hashing and JWT helpers
  seed.py           Sample knowledge articles
  services/rag.py   Chunking, optional Gemini embeddings/generation, hybrid retrieval
static/
  index.html        Dashboard views and dialogs
  styles.css        Responsive light/dark interface
  app.js            API client and dashboard interactions
requirements.txt
.env.example
```

## Data and Retrieval

The first run seeds sample guides for Python imports, Wi-Fi, HTTP 500, PostgreSQL timeouts, Windows storage, and phishing response. Uploaded documents are limited to 10 MB and accepted as TXT, Markdown, PDF, or DOCX. Extracted text is stored as an article and split into roughly 1,100-character passages in `article_chunks`; optional Gemini embedding vectors are stored alongside each passage in SQLite. Search combines passage cosine similarity with title/body term overlap. When Gemini is not configured or available, retrieval falls back to local lexical matching; Groq can still generate answers from those retrieved sources. Generated responses only receive the retrieved article context and must cite source numbers; the response includes source articles for review.

SQLite is the development database. SQLAlchemy models are kept separate from route handlers so a deployment can add Alembic migrations, PostgreSQL, or a dedicated vector store without moving the UI contract.

## Main API Routes

- `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me`
- `POST /api/search`, `GET /api/search/suggestions`, `GET /api/search/history`
- `GET/POST /api/articles`, `PUT/DELETE /api/articles/{id}`, `POST /api/articles/upload`
- `GET/POST /api/tickets`, `GET/PATCH /api/tickets/{id}`, `POST /api/tickets/{id}/knowledge`
- `POST /api/feedback`, `GET /api/bookmarks`, `POST/DELETE /api/bookmarks/{article_id}`
- `GET /api/admin/stats`, `GET /api/admin/users`, `PATCH /api/admin/users/{id}/role`
- `GET /api/agent/stats`, `GET /api/health`

Protected routes accept `Authorization: Bearer <token>`. Admin-only operations validate the user's database role on every request; clients cannot choose their own role during registration.

## Production Checklist

This repository is a project-ready starting point, not a hardened deployment by itself. Use HTTPS and a strong secret manager, set secure token/session policies, add login and upload rate limits, configure logging and backups, scan/sandbox uploaded files, add database migrations, and review retention/privacy requirements before handling real support data. The built-in local fallback is useful for demos; configure a Gemini key only if outbound processing of support text is permitted by your organization.
