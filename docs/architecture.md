# Architecture & Schema Proposal

This document captures the Phase 0 design decisions: the module
architecture, the initial database schema, and the reasoning behind both.
It is expected to be amended (not silently replaced) as later phases
reveal requirements Phase 0 couldn't know about.

## 1. Module architecture

See `app/__init__.py` and each subpackage's `__init__.py` for the
responsibility of each module. Summary of the dependency rule that keeps
this modular instead of tangled:

```
app.interfaces  →  app.ai, app.tasks, app.habits, app.scheduling, app.planning, app.files, app.integrations, app.voice
                          ↓ (all of these)
                     app.storage
                          ↓
                     app.core (config, events, permissions, assistant)
```

Arrows mean "depends on". Nothing below depends on anything above it.
Concretely:

- `app.core` has no dependency on any domain package. It's the seam every
  interface (web, AI, voice, future CLI) shares, so orchestration logic
  is written once.
- Domain packages (`app.tasks`, `app.habits`, ...) depend on `app.storage`
  for persistence but never on `app.interfaces` — this is what keeps them
  testable without spinning up FastAPI, and reusable from a future CLI or
  from voice without modification.
- `app.ai` requests actions as structured tool calls; it never executes
  arbitrary code, and every tool call still passes through
  `app.core.permissions` (see `PermissionChecker`) before touching data.

## 2. Database schema proposal

Not implemented yet — SQLAlchemy models arrive in Phase 1-2. This is the
relationship-level plan referenced when they're written, so table design
isn't improvised table-by-table.

**Core entities**

- `Project(id, name, description, color, created_at, archived_at)`
- `Task(id, project_id → Project, title, description, status, priority,
  deadline, created_at, updated_at, completed_at)`
  - `status`: enum (`todo`, `in_progress`, `done`, `cancelled`) rather than
    a free-text string, so invalid states are caught at write time.
  - `priority`: small integer scale (e.g. 1-4), not free text, so sorting
    and "top priority tasks" queries stay simple.
- `TaskDependency(task_id → Task, depends_on_task_id → Task)` — composite
  key on both columns; a task cannot be marked `done` while a dependency
  isn't `done` (enforced in `app.tasks` logic, not just the DB).
- `Tag(id, name, unique)`, `TaskTag(task_id → Task, tag_id → Tag)` — plain
  many-to-many join table.

**Habits**

- `Habit(id, name, frequency, target_count, created_at, archived_at)`
- `HabitCompletion(id, habit_id → Habit, completed_at)` — one row per
  completion rather than a boolean-per-day grid, so streak/statistics
  logic can be recomputed from history instead of needing separate
  incremental counters that can drift out of sync.

**Scheduling**

- `PomodoroSession(id, task_id → Task nullable, started_at, ended_at,
  interrupted: bool)`
- `Reminder(id, task_id → Task nullable, remind_at, message, fired_at
  nullable)`
- `ScheduleItem(id, title, starts_at, ends_at, task_id → Task nullable)`
- `Notification(id, title, body, created_at, read_at nullable, source)`

**AI / memory (Phase 4-5)**

- `Conversation(id, started_at, title)`
- `Message(id, conversation_id → Conversation, role, content, created_at)`
- `Memory(id, content, category, created_at, source_message_id → Message
  nullable)` — kept as a distinct table from `Message` deliberately: chat
  history is a transcript, long-term memory is curated/derived from it,
  and the spec asks for those to stay conceptually separate.

**Cross-cutting**

- `UserPreferences(id, key, value)` — simple key/value rather than a rigid
  columned table, since preferences will grow (theme, working hours,
  notification settings, default AI provider) and shouldn't require a
  migration per new preference.
- `ActivityLog(id, actor, action, target_type, target_id, detail, created_at)`
  — append-only audit trail, written to by `app.core.events` subscribers
  rather than scattered explicit calls, so no feature can "forget" to log.

**Deliberately deferred decisions**

- Exact index list: added when query patterns exist to measure against,
  not guessed at.
- Soft-delete vs hard-delete for `Task`/`Project`: leaning soft-delete
  (`archived_at`/similar) since the spec wants activity history and
  statistics, which a hard delete would corrupt — but this gets confirmed
  against real usage in Phase 1, not locked in Phase 0.
- Multi-user support: out of scope. Schema assumes a single local user;
  `UserPreferences` has no `user_id` for that reason.

## 3. Dependency proposal by phase

| Phase | New dependencies | Why not sooner |
|---|---|---|
| 0 | `pydantic`, `pydantic-settings`, `pytest`, `ruff` | Only config + tests exist yet. |
| 1-2 | `fastapi`, `uvicorn`, `sqlalchemy`, `alembic` | No API or DB until there's domain logic to expose/persist. |
| 4+ | `httpx` | No outbound AI/API calls until the AI layer exists. |
| 8 | STT/TTS libraries (TBD, evaluated against local-first constraint at the time) | Spec explicitly says not to implement voice early. |

`requirements.txt` lists later-phase dependencies as commented-out lines
at the point they'll be needed, rather than installing everything now —
so `pip install -r requirements.txt` at any phase installs exactly what
that phase's code actually imports.

## 3a. Phase 0.2 — database foundation and Task module (implemented)

Confirms/refines the Section 2 proposal now that it's real code:

- **Layering**: `app.storage` (SQLAlchemy engine/session/models) →
  `app.tasks.repository` (dumb CRUD) → `app.tasks.service` (business
  rules, raises `TaskNotFoundError`) → `app.interfaces.api.tasks` (FastAPI
  routes, translate domain exceptions to HTTP). Each layer only talks to
  the one directly below it.
- **Migrations deferred, not skipped**: tables are created via
  `Base.metadata.create_all()` at app startup rather than Alembic.
  Alembic is already in `requirements.txt` (commented out) and gets
  turned on the moment a schema change needs to preserve existing data —
  there's no data worth preserving yet. See `app/storage/__init__.py`.
- **`PUT` implemented as partial update**: `TaskUpdate`'s fields are all
  optional and only fields the client actually sent are applied
  (`model_dump(exclude_unset=True)` in `TaskService.update_task`).
  Documented as a deliberate deviation from strict REST PUT semantics —
  see `app/tasks/schemas.py`'s `TaskUpdate` docstring for the reasoning
  and the condition under which to revisit it.
- **Priority as a plain 1-4 integer** with a DB-level `CheckConstraint`,
  not an enum — chosen so ordering ("more urgent than") is a plain
  integer comparison. See `app/storage/models.py`.
- **`TaskNotFoundError` is a plain Python exception**, not
  `fastapi.HTTPException` — kept out of `app.tasks` entirely so that
  package has zero dependency on FastAPI. Translated to HTTP 404 in
  exactly one place: `app/interfaces/main.py`'s exception handler.
- **Default `DATABASE_URL` is an absolute path**, not a cwd-relative
  `sqlite:///./data/assistant.db` — the latter would silently resolve to
  a different file depending on the directory `uvicorn`/`pytest` happens
  to be launched from. See `app/core/config.py`.

## 4. Known risks / technical unknowns going into Phase 1

- **Task dependency cycles.** `TaskDependency` needs cycle detection
  before it can safely block "mark done while a dependency is open" —
  otherwise two tasks could depend on each other and both become
  permanently unblockable. Needs explicit handling in `app.tasks`, not
  just a DB foreign key.
- **SQLite concurrency.** SQLite handles concurrent writes from a single
  local process fine, but FastAPI + a future background scheduler (for
  reminders/notifications) writing from different tasks/threads at once
  is worth watching once Phase 2 adds the scheduler.
- **Recurring tasks' interaction with dependencies and Pomodoro history.**
  The spec asks for "recurring tasks where appropriate" without full
  detail — whether a recurring task is one `Task` row that resets, or a
  template that spawns new rows, changes how `TaskDependency` and
  `PomodoroSession` reference it. Decide in Phase 1 once basic Task CRUD
  exists to build the decision on top of.
- **AI provider abstraction leakiness.** Different providers' tool-calling
  formats aren't identical (OpenAI-style function calling vs. Anthropic
  tool use vs. what a local Ollama model can do at all). The Phase 4
  abstraction layer needs a concrete spike against at least two providers
  before the interface is trusted to be truly swappable.
