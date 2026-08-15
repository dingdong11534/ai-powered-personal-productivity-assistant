# Personal Productivity Assistant

A local, modular, AI-assisted personal productivity system: tasks,
projects, habits, scheduling, and (eventually) a controlled AI agent with
voice interaction. See `docs/architecture.md` for the full architecture
and database schema proposal, and the project brief for the phase-by-phase
build plan.

**Status:** Phase 0.2 — database foundation (SQLite + SQLAlchemy) and the
first domain module, Task, with a full CRUD API. No AI, habits,
scheduling, voice, or frontend yet.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

## Running the tests

```bash
pytest
```

`tests/test_events.py` and `tests/test_permissions.py` depend only on the
standard library and this project's own code. Everything else
(`test_config.py`, `test_task_repository.py`, `test_task_service.py`,
`test_tasks_api.py`) requires the full `requirements.txt` to be
installed.

## Running the API

```bash
uvicorn app.interfaces.main:app --reload
```

Then visit `http://127.0.0.1:8000/docs` for interactive API docs
(Swagger UI, generated automatically by FastAPI from the route type
hints and Pydantic schemas), or `http://127.0.0.1:8000/health` for a
liveness check. On startup, tables are created automatically in
`data/assistant.db` (SQLite) if they don't already exist.

Endpoints:

| Method | Path          | Description        |
|--------|---------------|---------------------|
| POST   | `/tasks`      | Create a task       |
| GET    | `/tasks`      | List tasks          |
| GET    | `/tasks/{id}` | Get one task        |
| PUT    | `/tasks/{id}` | Partially update a task |
| DELETE | `/tasks/{id}` | Delete a task        |

## Project layout

```
app/
  core/          orchestration, config, events, permissions — see app/core/__init__.py
  tasks/         task domain: exceptions, schemas, repository, service   (Phase 0.2 — done for Task)
  habits/        habit tracking domain logic           (Phase 2)
  scheduling/    reminders / Pomodoro / scheduling      (Phase 2)
  planning/      daily planning & prioritization        (Phase 5)
  ai/            LLM abstraction & tool-calling         (Phase 4)
  storage/       SQLAlchemy engine/session + models     (Phase 0.2 — done for Task)
  files/         sandboxed assistant file tools         (Phase 6)
  integrations/  external API adapters                  (Phase 7)
  voice/         speech-to-text / text-to-speech         (Phase 8)
  interfaces/    FastAPI app + routes (api/tasks.py)     (Phase 0.2 — done for Task)
tests/           pytest suite: conftest.py fixtures + one file per layer/resource
data/            local SQLite DB (assistant.db) + (later) the assistant's file workspace
docs/            architecture notes, schema proposal
```

Each subpackage's `__init__.py` explains what it will contain and why it's
separated the way it is — read those before adding code to a module for
the first time.

## Design principles this project holds itself to

- The AI layer requests actions via structured tool calls only. It never
  executes arbitrary AI-generated code or shell commands.
- Domain logic (`app.tasks`, `app.habits`, ...) never imports from
  `app.interfaces` — it stays usable from tests, a future CLI, and voice
  without change.
- Sensitive/destructive actions are gated through
  `app.core.permissions`, not ad hoc checks scattered per feature.
- No dependency is added before a phase actually needs it — see the table
  in `docs/architecture.md`.
