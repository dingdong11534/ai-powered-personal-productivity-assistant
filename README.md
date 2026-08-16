# Personal Productivity Assistant

A local, modular, AI-assisted personal productivity system: tasks,
projects, habits, scheduling, and (eventually) a controlled AI agent with
voice interaction. See `docs/architecture.md` for the full architecture,
database schema, and the reasoning behind each design decision.

**Status:** Phase 1 — productivity engine foundation. Working today:
Projects (create/get/list/update/archive), Tasks (full CRUD) that can
belong to a Project, Tags (create/list/attach/detach), Task Dependencies
(with self-dependency rejection, cycle detection, and
dependency-blocked completion), and search/filtering over tasks. No AI,
habits, scheduling, notifications, voice, or frontend yet.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

## Running the tests

```bash
pytest -v
```

`tests/test_events.py` and `tests/test_permissions.py` depend only on the
standard library and this project's own code. Everything else requires
the full `requirements.txt` to be installed.

## Running the API

```bash
uvicorn app.interfaces.main:app --reload
```

Then visit `http://127.0.0.1:8000/docs` for interactive API docs
(Swagger UI, generated automatically by FastAPI from the route type
hints and Pydantic schemas), or `http://127.0.0.1:8000/health` for a
liveness check.

On startup, the app creates any missing tables in `data/assistant.db`
(SQLite), and — if you have a database from before Phase 1 — safely adds
the new `tasks.project_id` column to your existing `tasks` table without
touching any existing rows. See docs/architecture.md, section 5.8, for
exactly what this does and why it isn't Alembic (yet).

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

`GET /tasks` query parameters (all optional, combined with AND):
`status`, `priority` (1-4), `project_id`, `tag_id`, `deadline_before`,
`deadline_after`, `completed` (bool), `search` (substring match on
title/description), `skip`, `limit`.

### Business rules worth knowing

- **Priority** is 1-4: 1=Critical, 2=High, 3=Medium, 4=Low (lower number
  = more urgent).
- A task's `project_id` must reference an existing, **non-archived**
  project. Archiving a project never changes or hides its existing
  tasks — it only blocks *new* assignments to it.
- A task cannot be marked `done` while it has an unresolved (not-`done`)
  direct dependency — the API returns `409 Conflict`.
- Adding a dependency that would create a self-dependency (`400`) or a
  cycle (`409`) is rejected before it's written.

## Project layout

```
app/
  core/          orchestration, config, events, permissions
  projects/      project domain: exceptions, schemas, repository, service   (Phase 1)
  tasks/         task/tag/dependency domain logic — see app/tasks/__init__.py (Phase 0.2 + Phase 1)
  habits/        habit tracking domain logic           (Phase 2)
  scheduling/    reminders / Pomodoro / scheduling      (Phase 2)
  planning/      daily planning & prioritization        (Phase 5)
  ai/            LLM abstraction & tool-calling         (Phase 4)
  storage/       SQLAlchemy engine/session + models     (Phase 0.2 + Phase 1)
  files/         sandboxed assistant file tools         (Phase 6)
  integrations/  external API adapters                  (Phase 7)
  voice/         speech-to-text / text-to-speech         (Phase 8)
  interfaces/    FastAPI app + routes (api/tasks.py, api/tags.py, api/projects.py)
tests/           pytest suite: conftest.py fixtures + one file per layer/resource
data/            local SQLite DB (assistant.db) + (later) the assistant's file workspace
docs/            architecture notes, schema proposal, Phase 1 write-up
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
  other (e.g. `app.tasks` depends on `app.projects` to validate a task's
  project) when a business rule genuinely spans both — see
  `docs/architecture.md` section 5.2 for why that's a deliberate
  exception, not a crack in the layering.
- Business logic (validation, cross-entity rules, cycle detection) lives
  in the service layer, never in a FastAPI route and never written
  directly against SQLAlchemy from a route.
- Sensitive/destructive actions are gated through
  `app.core.permissions`, not ad hoc checks scattered per feature.
- No dependency is added before a phase actually needs it — see the table
  in `docs/architecture.md`.
