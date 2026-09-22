# Personal Productivity Assistant

A local, modular, AI-assisted personal productivity system: tasks,
projects, habits, scheduling, and (eventually) a controlled AI agent with
voice interaction. See `docs/architecture.md` for the full architecture,
database schema, and the reasoning behind each design decision.

**Status:** Phase 6 — Controlled File Workspace complete. In addition to the Phase 5 features, the assistant can work only within `data/workspace/`: list, search, read, create, update, and delete UTF-8 text files through the same sandboxed service used by the API and AI tools. Updates and deletes require explicit user authorization.

## Setup


```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

### Environment Configuration

The application is configured via environment variables or a `.env` file in the project root:

- `AI_PROVIDER`: Choose `mock` for local offline testing or `openai` for OpenAI / OpenAI-compatible APIs (Ollama, Groq, vLLM). Default: `mock`.
- `AI_MODEL`: Model name passed to the provider (e.g. `gpt-4o-mini`, `llama3`). Default: `gpt-4o-mini`.
- `AI_BASE_URL`: Base URL for OpenAI-compatible HTTP endpoint. Default: `https://api.openai.com/v1`.
- `AI_API_KEY`: API key for the AI provider.

## Running the tests

```bash
.venv/bin/pytest -v
```

`tests/test_events.py`, `tests/test_permissions.py`, and
`tests/test_habit_streak.py` depend only on the standard library and
this project's own code. Everything else requires the full
`requirements.txt` to be installed.

## Running the API

```bash
.venv/bin/uvicorn app.interfaces.main:app --reload
```

Then visit `http://127.0.0.1:8000/` for the web dashboard, `http://127.0.0.1:8000/docs` for interactive API docs
(Swagger UI, generated automatically by FastAPI from the route type
hints and Pydantic schemas), or `http://127.0.0.1:8000/health` for a
liveness check.


On startup, the app creates any missing tables in `data/assistant.db`
(SQLite). If you have a database from before Phase 1, it also safely
adds the `tasks.project_id` column to your existing `tasks` table
without touching any existing rows — see docs/architecture.md, sections
5.8 and 7.8, for exactly what this does and why Alembic isn't needed
yet.

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST   | `/projects` | Create a project |
| GET    | `/projects` | List projects (`?include_archived=false` to hide archived) |
| GET    | `/projects/{id}` | Get one project |
| PUT    | `/projects/{id}` | Partially update a project |
| POST   | `/projects/{id}/archive` | Archive a project (tasks are unaffected) |
| POST   | `/tasks` | Create a task (optionally with `project_id`) |
| GET    | `/tasks` | List/filter tasks — see query params below |
| GET    | `/tasks/{id}` | Get one task |
| PUT    | `/tasks/{id}` | Partially update a task |
| DELETE | `/tasks/{id}` | Delete a task |
| GET    | `/tasks/{id}/tags` | List a task's tags |
| POST   | `/tasks/{id}/tags/{tag_id}` | Attach a tag (idempotent) |
| DELETE | `/tasks/{id}/tags/{tag_id}` | Detach a tag (idempotent) |
| GET    | `/tasks/{id}/dependencies` | List a task's direct dependencies |
| POST   | `/tasks/{id}/dependencies` | Add a dependency (`{"depends_on_task_id": N}`) |
| DELETE | `/tasks/{id}/dependencies/{dep_id}` | Remove a dependency |
| POST   | `/tags` | Create a tag (unique name) |
| GET    | `/tags` | List all tags |
| POST   | `/habits` | Create a habit |
| GET    | `/habits` | List habits (`?include_archived=false`) |
| GET    | `/habits/{id}` | Get one habit |
| PUT    | `/habits/{id}` | Partially update a habit |
| POST   | `/habits/{id}/archive` | Archive a habit (history unaffected) |
| POST   | `/habits/{id}/complete` | Record a completion (body optional; defaults to now) |
| GET    | `/habits/{id}/history` | List a habit's completion history |
| GET    | `/habits/{id}/statistics` | Current streak, longest streak, completion rate |
| POST   | `/pomodoro` | Start a focus session (optional `task_id`) |
| GET    | `/pomodoro` | List sessions (`?task_id=` to filter) |
| GET    | `/pomodoro/{id}` | Get one session |
| POST   | `/pomodoro/{id}/end` | End a session (`{"interrupted": bool}`) |
| POST   | `/reminders` | Create a reminder |
| GET    | `/reminders` | List reminders (`?due=true` / `?upcoming=true`) |
| GET    | `/reminders/{id}` | Get one reminder |
| PUT    | `/reminders/{id}` | Partially update a reminder |
| POST   | `/reminders/{id}/fire` | Mark fired (idempotent) |
| DELETE | `/reminders/{id}` | Delete a reminder |
| POST   | `/schedule` | Create a schedule item |
| GET    | `/schedule` | List schedule items |
| GET    | `/schedule/conflicts` | Find overlapping items (`?starts_at=&ends_at=`) |
| GET    | `/schedule/{id}` | Get one schedule item |
| PUT    | `/schedule/{id}` | Partially update a schedule item |
| DELETE | `/schedule/{id}` | Delete a schedule item |
| POST   | `/notifications` | Create a notification |
| GET    | `/notifications` | List notifications (`?unread_only=true`) |
| GET    | `/notifications/{id}` | Get one notification |
| POST   | `/notifications/{id}/read` | Mark read (idempotent) |
| POST   | `/notifications/{id}/unread` | Mark unread (idempotent) |
| POST   | `/conversations` | Create a new chat session |
| GET    | `/conversations` | List chat sessions |
| GET    | `/conversations/{id}` | Get conversation details |
| DELETE | `/conversations/{id}` | Delete conversation and transcript |
| GET    | `/conversations/{id}/messages` | List conversation transcript |
| POST   | `/conversations/{id}/messages` | Send message and trigger AI Assistant |
| POST   | `/memories` | Create a long-term memory record |
| GET    | `/memories` | List active memories (`?category=&include_archived=false`) |
| GET    | `/memories/search` | Search memories by keyword (`?query=`) |
| GET    | `/memories/{id}` | Get a single memory record |
| PUT    | `/memories/{id}` | Update memory content or category |
| POST   | `/memories/{id}/archive` | Archive a memory record |
| DELETE | `/memories/{id}` | Permanently delete a memory record |
| GET | `/files` | List workspace files (`?sub_path=&search=`) |
| GET | `/files/read` | Read a UTF-8 workspace file (`?path=`) |
| POST | `/files/write` | Create or write a workspace file; overwrites require `confirm_destructive: true` |
| DELETE | `/files` | Delete a workspace path; requires `?confirm_destructive=true` |



`GET /tasks` query parameters (all optional, combined with AND):
`status`, `priority` (1-4), `project_id`, `tag_id`, `deadline_before`,
`deadline_after`, `completed` (bool), `search` (substring match on
title/description), `skip`, `limit`.

### Business rules worth knowing

- **Priority** is 1-4: 1=Critical, 2=High, 3=Medium, 4=Low (lower number
  = more urgent).
- A task's `project_id` must reference an existing, **non-archived**
  project. Archiving a project never changes or hides its existing
  tasks — it only blocks *new* assignments to it. The same "archiving
  blocks new activity, never erases history" rule applies to Habits.
- A task cannot be marked `done` while it has an unresolved (not-`done`)
  direct dependency — `409`. Adding a dependency that would create a
  self-dependency (`400`) or a cycle (`409`) is rejected before it's
  written.
- A habit allows **at most one completion per calendar day**, regardless
  of frequency — `409` on a duplicate. Streaks and statistics are always
  recomputed from the completion history, never read from a cached
  counter.
- A Pomodoro session can only be ended once — `409` on a second `/end`.
- Reminders accept a `remind_at` in the past (useful for backfilling/
  testing); firing (`/fire`) and Notification read/unread toggling are
  **idempotent** — calling them again on an already-fired/already-read
  item just succeeds, it doesn't error.
- Schedule item conflicts are **detected, not blocked** — overlapping
  items are allowed to be created (matching how real calendar apps
  behave); use `GET /schedule/conflicts` to check beforehand.

## Project layout

```
app/
  core/           orchestration, config, events, permissions
  projects/       project domain: exceptions, schemas, repository, service   (Phase 1)
  tasks/          task/tag/dependency domain logic — see app/tasks/__init__.py (Phase 0.2 + 1)
  habits/         habits + completion history + streak/statistics (pure)      (Phase 2)
  pomodoro/       focus-session domain logic                                  (Phase 2)
  reminders/      reminder domain logic                                       (Phase 2)
  scheduling/     local schedule (ScheduleItem) domain logic                  (Phase 2)
  notifications/  notification record domain logic                           (Phase 2)
  planning/       daily planning & prioritization        (Phase 5)
  ai/             LLM abstraction & tool-calling         (Phase 4)
  storage/        SQLAlchemy engine/session + models     (Phase 0.2 + 1 + 2)
  files/          sandboxed workspace service + schemas + safety limits (Phase 6)
  integrations/   external API adapters + future OS-level notification dispatch (Phase 7)
  voice/          speech-to-text / text-to-speech         (Phase 8)
  interfaces/     FastAPI app + one router module per resource
tests/            pytest suite: conftest.py fixtures + one file per layer/resource
data/             local SQLite DB (assistant.db) + (later) the assistant's file workspace
docs/             architecture notes, schema proposal, Phase 1 and 2 write-ups
```

Each subpackage's `__init__.py` explains what it contains and why it's
separated the way it is — read those before adding code to a module for
the first time.

## Design principles this project holds itself to

- The AI layer requests actions via structured tool calls only. It never
  executes arbitrary AI-generated code or shell commands.
- Domain logic (`app.tasks`, `app.projects`, `app.habits`, ...) never
  imports from `app.interfaces` — it stays usable from tests, a future
  CLI, and voice without change. Domain packages *may* depend on each
  other (e.g. `app.tasks` depends on `app.projects`; `app.pomodoro`/
  `app.reminders`/`app.scheduling` depend on `app.tasks` to validate an
  optional `task_id`) when a business rule genuinely spans both — see
  `docs/architecture.md` section 5.2 for why that's a deliberate,
  one-way exception, not a crack in the layering.
- Business logic (validation, cross-entity rules, cycle/streak/conflict
  computation) lives in the service layer, never in a FastAPI route and
  never written directly against SQLAlchemy from a route.
- Sensitive/destructive actions are gated through
  `app.core.permissions`, not ad hoc checks scattered per feature.
- No dependency is added before a phase actually needs it — see the table
  in `docs/architecture.md`. Phase 2 added zero new dependencies.
