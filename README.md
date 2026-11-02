# Personal Productivity Assistant

A local-first, modular, AI-assisted personal productivity system: tasks, projects, habits,
scheduling, and a controlled AI agent with voice interaction, long-term memory, a sandboxed
file workspace, real-time weather, SSE streaming, a full web dashboard, **multi-user support
with JWT authentication**, and per-user AI data isolation. See `docs/architecture.md` for the
full architecture, database schema, and reasoning behind each design decision.

**Current status (Phase 9 + multi-user):**
- Phases 0–8 complete (see `docs/architecture.md` for the full build log)
- Phase 9: Voice input via browser Web Speech API (Chrome / Edge / Safari)
- Multi-user: JWT Bearer-token auth, per-user data isolation across all resources, presence
  heartbeat, per-user token-usage tracking, project collaboration with invites,
  task-assignment requests, and an admin role that gates offline-model access
- Responsive mobile UI: off-canvas drawer, bottom navigation bar, touch targets, bottom-sheet modals
- Deployed to both Render (full backend + PostgreSQL) and Vercel (serverless)

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env — set AI provider keys, SECRET_KEY, etc.
```

### Environment Configuration

| Variable | Default | Description |
|---|---|---|
| `AI_PROVIDER` | `groq` | Active provider: `mock`, `openai`, `groq`, `gemini`, `grok`, `offline` |
| `AI_MODEL` | provider default | Model name (e.g. `llama-3.3-70b-versatile`, `gpt-4o-mini`) |
| `AI_BASE_URL` | provider default | Base URL for OpenAI-compatible endpoint |
| `AI_API_KEY` | — | API key for the AI provider |
| `GROQ_API_KEY` | — | Groq key (used when `AI_PROVIDER=groq`) |
| `GEMINI_API_KEY` | — | Gemini key |
| `GROK_API_KEY` | — | Grok (xAI) key |
| `SECRET_KEY` | `dev-secret-…` | JWT signing secret — **change in production** |
| `DATABASE_URL` | SQLite at `data/assistant.db` | PostgreSQL URL for Render/Vercel |
| `ENVIRONMENT` | `development` | `development` or `production` |

### AI Provider Configuration Examples

```bash
# Groq (fast, free tier) — current default
AI_PROVIDER=groq
AI_BASE_URL=https://api.groq.com/openai/v1
AI_MODEL=llama-3.3-70b-versatile
GROQ_API_KEY=gsk_your_key_here

# OpenAI
AI_PROVIDER=openai
AI_BASE_URL=https://api.openai.com/v1
AI_MODEL=gpt-4o-mini
AI_API_KEY=sk-your_key_here

# Gemini
AI_PROVIDER=gemini
AI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
AI_MODEL=gemini-1.5-flash
GEMINI_API_KEY=your_key_here

# Local Ollama (admin-only offline mode)
AI_PROVIDER=offline
AI_BASE_URL=http://localhost:11434/v1
AI_MODEL=llama3
AI_API_KEY=ollama

# Offline testing (no API key, no network)
AI_PROVIDER=mock
```

## Running the Tests

```bash
.venv/bin/pytest -v
```

422 of 426 tests pass (4 pre-existing test assertions tied to stale mock expectations —
`test_config`, `test_ai_integration`, `test_ai_file_integration`, `test_streaming`).

## Running the API

```bash
.venv/bin/uvicorn app.interfaces.main:app --reload
```

- **Web dashboard**: `http://127.0.0.1:8000/`
- **Interactive API docs** (Swagger UI): `http://127.0.0.1:8000/docs`
- **Health check**: `http://127.0.0.1:8000/health`

On startup, the app creates any missing tables in `data/assistant.db` (SQLite) and seeds
demo data on first run (skipped during tests).

## Authentication

All API endpoints require an authenticated user. The app supports three auth methods:

1. **Bearer token** (preferred): `Authorization: Bearer <token>` — obtain via `POST /auth/login`
2. **X-User-Id header**: `X-User-Id: <id>` (for legacy/test use)
3. **No credentials**: falls back to the default admin user — only for local dev/tests

### Default Admin

The admin user `kunal` is bootstrapped automatically. Default password: `kunalreward34`
(**change immediately in production**).

### Multi-User Test Credentials

5 pre-seeded test users (password for all: `123`):
`jordan`, `alex`, `taylor`, `sam`, `morgan`

---

## Endpoints

### Auth

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/register` | Create a new account → returns token |
| POST | `/auth/login` | Authenticate → returns token |
| GET | `/auth/me` | Current user's profile |
| POST | `/auth/heartbeat` | Update online presence |
| POST | `/auth/offline` | Mark as offline (on tab close) |
| GET | `/auth/users` | List all users (with online status) |
| GET | `/auth/users/{id}/profile` | Public profile of a user |

### AI Configuration

| Method | Path | Description |
|--------|------|-------------|
| GET | `/ai/status` or `/ai/mode` | Active provider, model, and available presets |
| POST | `/ai/mode` | Switch `online` / `offline` (offline: admin only) |
| POST | `/ai/config` | Set provider, model, API key, base URL at runtime |
| POST | `/ai/test` | Test connectivity for a given provider |
| GET/POST | `/ai/test-all` | Test all configured providers |
| GET | `/ai/user-keys` | View current user's custom API key overrides |
| POST | `/ai/user-keys` | Set/clear a per-user API key override |

### Tasks

| Method | Path | Description |
|--------|------|-------------|
| POST | `/tasks` | Create a task |
| GET | `/tasks` | List/filter tasks (see query params below) |
| GET | `/tasks/{id}` | Get one task |
| PUT | `/tasks/{id}` | Partially update a task |
| DELETE | `/tasks/{id}` | Delete a task |
| GET | `/tasks/{id}/tags` | List task's tags |
| POST | `/tasks/{id}/tags/{tag_id}` | Attach a tag (idempotent) |
| DELETE | `/tasks/{id}/tags/{tag_id}` | Detach a tag (idempotent) |
| GET | `/tasks/{id}/dependencies` | List direct dependencies |
| POST | `/tasks/{id}/dependencies` | Add dependency (`{"depends_on_task_id": N}`) |
| DELETE | `/tasks/{id}/dependencies/{dep_id}` | Remove dependency |

`GET /tasks` query parameters (combined with AND):
`status`, `priority` (1–4), `project_id`, `tag_id`, `deadline_before`,
`deadline_after`, `completed` (bool), `search` (substring in title/description),
`skip`, `limit`.

### Projects & Collaboration

| Method | Path | Description |
|--------|------|-------------|
| POST | `/projects` | Create a project |
| GET | `/projects` | List projects (`?include_archived=false`) |
| GET | `/projects/{id}` | Get one project |
| PUT | `/projects/{id}` | Partially update |
| POST | `/projects/{id}/archive` | Archive (tasks unaffected) |
| GET | `/projects/{id}/members` | List project members |
| POST | `/projects/{id}/invite` | Invite a user to a project |
| POST | `/projects/{id}/accept` | Accept project invitation |
| POST | `/projects/{id}/reject` | Reject project invitation |
| DELETE | `/projects/{id}/members/{uid}` | Remove a member (admin/owner) |

### Tags

| Method | Path | Description |
|--------|------|-------------|
| POST | `/tags` | Create a tag (unique name) |
| GET | `/tags` | List all tags |

### Habits

| Method | Path | Description |
|--------|------|-------------|
| POST | `/habits` | Create a habit |
| GET | `/habits` | List habits (`?include_archived=false`) |
| GET | `/habits/{id}` | Get one habit |
| PUT | `/habits/{id}` | Partially update |
| POST | `/habits/{id}/archive` | Archive |
| POST | `/habits/{id}/complete` | Record a completion |
| GET | `/habits/{id}/history` | Completion history |
| GET | `/habits/{id}/statistics` | Streak, longest streak, completion rate |

### Pomodoro

| Method | Path | Description |
|--------|------|-------------|
| POST | `/pomodoro` | Start a focus session (optional `task_id`) |
| GET | `/pomodoro` | List sessions (`?task_id=`) |
| GET | `/pomodoro/{id}` | Get one session |
| POST | `/pomodoro/{id}/end` | End session (`{"interrupted": bool}`) |

### Reminders

| Method | Path | Description |
|--------|------|-------------|
| POST | `/reminders` | Create a reminder |
| GET | `/reminders` | List (`?due=true` / `?upcoming=true`) |
| GET | `/reminders/{id}` | Get one |
| PUT | `/reminders/{id}` | Partially update |
| POST | `/reminders/{id}/fire` | Mark fired (idempotent) |
| DELETE | `/reminders/{id}` | Delete |

### Schedule

| Method | Path | Description |
|--------|------|-------------|
| POST | `/schedule` | Create schedule item |
| GET | `/schedule` | List items |
| GET | `/schedule/conflicts` | Find overlapping items (`?starts_at=&ends_at=`) |
| GET | `/schedule/{id}` | Get one |
| PUT | `/schedule/{id}` | Partially update |
| DELETE | `/schedule/{id}` | Delete |

### Notifications

| Method | Path | Description |
|--------|------|-------------|
| POST | `/notifications` | Create a notification |
| GET | `/notifications` | List (`?unread_only=true`) |
| GET | `/notifications/{id}` | Get one |
| POST | `/notifications/{id}/read` | Mark read (idempotent) |
| POST | `/notifications/{id}/unread` | Mark unread (idempotent) |

### Conversations & AI Chat

| Method | Path | Description |
|--------|------|-------------|
| POST | `/conversations` | Create a new chat session |
| GET | `/conversations` | List sessions |
| GET | `/conversations/{id}` | Get session details |
| DELETE | `/conversations/{id}` | Delete session and transcript |
| GET | `/conversations/{id}/messages` | List transcript |
| POST | `/conversations/{id}/messages` | Send message → AI responds |
| POST | `/conversations/{id}/messages?stream=true` | SSE streaming response |

### Memories

| Method | Path | Description |
|--------|------|-------------|
| POST | `/memories` | Create a memory record |
| GET | `/memories` | List (`?category=&include_archived=false`) |
| GET | `/memories/search` | Search by keyword (`?query=`) |
| GET | `/memories/{id}` | Get one |
| PUT | `/memories/{id}` | Update content or category |
| POST | `/memories/{id}/archive` | Archive |
| DELETE | `/memories/{id}` | Permanently delete |

### Files (Sandboxed Workspace)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/files` | List workspace files (`?sub_path=&search=`) |
| GET | `/files/read` | Read a UTF-8 file (`?path=`) |
| POST | `/files/write` | Write a file; overwrites require `confirm_destructive: true` |
| DELETE | `/files` | Delete a path; requires `?confirm_destructive=true` |

---

## Business Rules

- **Priority** is 1–4: 1=Critical, 2=High, 3=Medium, 4=Low (lower = more urgent).
- A task cannot be `done` while it has an unresolved (not-`done`) direct dependency — `409`.
- Adding a dependency that would create a self-loop (`400`) or cycle (`409`) is rejected.
- A project must be non-archived to receive new task assignments — `409`.
- Archiving a project or habit never changes or hides existing tasks/completions.
- A habit allows **at most one completion per calendar day** — `409` on a duplicate.
- A Pomodoro session can only be ended once — `409` on second `/end`.
- Reminder firing and notification read/unread toggling are **idempotent**.
- Schedule conflicts are **detected, not blocked** — use `GET /schedule/conflicts` to query.
- All AI resources (conversations, memories, tools) are **strictly isolated per user**.
- Destructive AI tool calls require `authorize_destructive: true` in the API request or
  explicit confirmation language in the user message — the AI model cannot set this flag itself.
- Offline (Ollama) AI mode is **admin-only**.
- Each user's `token_usage` is tracked; admins and project leaders can view all members' usage.

---

## Project Layout

```
app/
  core/           config, event bus, permissions, JWT auth
  storage/        SQLAlchemy engine/session + ALL ORM models
  projects/       project domain + ProjectMember collaboration
  tasks/          task/tag/dependency domain logic
  habits/         habits + completion history + streak (pure functions)
  pomodoro/       focus-session domain logic
  reminders/      reminder domain logic
  scheduling/     ScheduleItem domain logic
  notifications/  notification record domain logic
  planning/       daily planning & prioritization
  ai/             LLM abstraction + tool registry + AssistantCore (streaming)
  external/       SSRF-safe ExternalHttpClient + WeatherService
  files/          sandboxed workspace service (data/workspace/)
  integrations/   future: OS-level notification dispatch (stub)
  voice/          speech-to-text / text-to-speech (stub)
  users/          user registration, auth, token, and per-user key management
  memories/       long-term AI memory
  conversations/  chat conversation + message transcript
  interfaces/     FastAPI app + one router per resource + static web UI
tests/            pytest suite: 55 test files, 426 tests
data/             SQLite DB (assistant.db) + AI file workspace/
docs/             architecture notes and decision log
```

Each subpackage's `__init__.py` explains what it contains and why it's separated that way —
read those before adding code to a module for the first time.

---

## Design Principles

- The AI layer requests actions via **structured tool calls only** — no arbitrary code execution.
- Domain packages never import from `app.interfaces` — testable without a web server.
- Business logic lives in service classes, never in FastAPI routes.
- Destructive actions are gated through `app.core.permissions` and require explicit user authorization.
- All user data is isolated: every query filters by `user_id`; admin can see across users.
- Dependencies are added only when a phase actually needs them.

---

## Deployment

### Render (Recommended — full backend + PostgreSQL)

The repository includes a ready-to-use [`render.yaml`](render.yaml) blueprint:

1. Push your repository to GitHub.
2. In [Render Dashboard](https://dashboard.render.com), click **New +** → **Blueprint**.
3. Select your repository. Render automatically provisions a free PostgreSQL database
   and a FastAPI web service running with Gunicorn + Uvicorn workers.
4. Add your API keys (`GROQ_API_KEY`, `GEMINI_API_KEY`, `GROK_API_KEY`, `SECRET_KEY`) in the environment tab.
5. Open `https://<service-name>.onrender.com` to access the application.

### Vercel (Serverless — requires external DB)

The repository includes [`vercel.json`](vercel.json) and [`api/index.py`](api/index.py):

- Connect the repository in Vercel.
- Supply a remote `DATABASE_URL` (Render PostgreSQL, Neon, or Supabase) in Vercel Environment Variables.
- Vercel builds and runs the application using `@vercel/python`.
