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

## 5. Phase 1 — productivity engine foundation (implemented)

Adds `Project`, `Tag`/`task_tags`, and `TaskDependency` around the
existing Task system, without restructuring the Phase 0.2 layering.

### 5.1 Project entity

`app.projects` is a new top-level domain package (`exceptions.py`,
`schemas.py`, `repository.py`, `service.py`), mirroring `app.tasks`'s
internal layering. It's a separate package rather than folded into
`app.tasks` because Project is its own aggregate with its own lifecycle
(create / update / archive), not merely an attribute of Task.

CRUD surface matches the brief exactly: create, get, list, update,
archive — **no hard delete**. `ProjectRepository` has no `delete()`
method and the API has no `DELETE /projects/{id}` route, because nothing
calls for one; adding it "for completeness" would be exactly the kind of
premature feature the brief asks to avoid.

### 5.2 Task → Project relationship

`Task.project_id` is a nullable foreign key to `projects.id`
(`ondelete="SET NULL"`). Rules, enforced in `TaskService` (not in a
route, not in the database):

- A task may be created or updated with `project_id = null` — no project
  required.
- Setting `project_id` to a real project on create/update requires that
  project to **exist** (else `ProjectNotFoundError`, HTTP 404) and to be
  **active** (else `ArchivedProjectError`, HTTP 409) — you cannot newly
  attach work to an archived project.
- **Archiving a project never touches its tasks.** `ProjectService.archive_project`
  only sets `archived_at`; it never iterates or modifies `Task` rows.
  Tasks already assigned to a project keep their `project_id` after that
  project is archived, and remain fully readable/editable via
  `GET /tasks/{id}` and `PUT /tasks/{id}` exactly as before — the only
  behavior change is that the project can no longer be the target of a
  *new* assignment. This satisfies "deleting/archiving a project must
  not silently destroy its tasks" directly: nothing about a task changes
  when its project is archived.
- `Task.project_id`'s `ondelete="SET NULL"` is a defensive default for a
  code path the API doesn't currently expose (there's no way to hard
  -delete a `Project` through this application) — included so that if a
  project row were ever removed by any other means, tasks would become
  unassigned rather than orphaned or blocked.

### 5.3 Tag system

`Tag(id, name unique)` and `task_tags(task_id, tag_id)` — the latter a
plain SQLAlchemy `Table` (association table), not a mapped class, since
it carries no data beyond the two foreign keys. Its composite primary
key is what makes a duplicate attachment impossible at the DB level.

Business rules live in `app.tasks.tag_service.TagService`:
- Tag names are unique; creating a duplicate name raises
  `DuplicateTagError` (HTTP 409), checked before insert rather than
  relying on catching the DB's `UNIQUE` violation.
- Attach/detach are **idempotent**: attaching a tag a task already has,
  or detaching one it doesn't, succeeds silently rather than erroring.
  This was a deliberate simplicity choice — see `TagService`'s
  docstring — so a client never has to check current state before
  acting.
- `GET /tasks?tag_id=` filters via a join through `task_tags` (see
  `TaskRepository.list`).

Kept deliberately small per the brief's "do not overengineer" — no tag
colors, no tag hierarchies, no per-tag metadata.

### 5.4 Dependency system

`TaskDependency(task_id, depends_on_task_id)` — composite primary key
(same duplicate-prevention reasoning as `task_tags`), both foreign keys
`ondelete="CASCADE"` (deleting a task removes its own dependency edges,
since they're meaningless without it — this differs from the
`project_id` case, where the *other* side must survive).

All validation lives in `app.tasks.dependency_service.TaskDependencyService`,
**not** in a route or in the database (SQL has no clean way to express
"no cycles across this whole edge set" as a table constraint):

1. **Self-dependency rejected** (`task_id == depends_on_task_id`) →
   `SelfDependencyError`, HTTP 400 — the request is invalid as written,
   no server state could make it valid.
2. **Both tasks must exist** → `TaskNotFoundError`, HTTP 404.
3. **Duplicate edge rejected** → `DuplicateDependencyError`, HTTP 409 —
   checked explicitly before insert, same reasoning as tags.
4. **Cycle rejected** → `DependencyCycleError`, HTTP 409. Detected by a
   breadth-first search starting at the proposed `depends_on_task_id`,
   following existing dependency edges outward; if the search reaches
   `task_id`, the new edge would close a loop. Implemented in plain
   Python (not a recursive SQL CTE) because the graph is small
   (one user's tasks) and a BFS is far easier to read, test, and verify
   than a recursive query at this scale — see
   `TaskDependencyService`'s docstring for the full reasoning, and
   `tests/test_dependency_service.py` for cases covering direct 2-cycles,
   multi-hop (3-node) cycles, and non-cyclic diamond shapes (A depends on
   B and C; both depend on D — verified *not* to false-positive).

**Completion blocking**: `TaskService.update_task` checks, only when
`status` is being changed to `done`, whether the task has any *direct*
dependency that isn't `DONE` yet (`TaskDependencyRepository.get_unresolved_dependencies`).
If so, raises `UnresolvedDependencyError` (HTTP 409) instead of applying
the update. Checking only direct (one-hop) dependencies is sufficient
for the transitive case too: if A depends on B depends on C, and C isn't
done, B is blocked from completion by its own direct check on C; A is
separately blocked by its direct dependency on B, which can't become
`DONE` while B is blocked — so a multi-hop chain is enforced without this
check needing to walk the whole chain itself.

### 5.5 Search and filter

`TaskRepository.list()` gained optional, independent filter parameters:
`status`, `priority`, `project_id`, `tag_id`, `deadline_before`,
`deadline_after`, `completed` (a convenience layered on top of `status`:
`True` → `status == DONE`, `False` → `status != DONE`), and `search`
(case-insensitive substring match against `title` OR `description`, via
SQL `ILIKE`/`LIKE`). All are combined with AND when several are given.
Exposed as query parameters on `GET /tasks` — no new endpoint needed.

Deliberately not full-text search (no ranking, no tokenization, no
index) — a plain substring `LIKE` is the right scope for the current
data volume (a single local user's tasks); revisit if/when result
relevance or performance actually becomes a problem, not before.

### 5.6 Priority meaning

Unchanged 1-4 integer range and `CheckConstraint`, now with the meaning
made explicit: **1 = Critical, 2 = High, 3 = Medium, 4 = Low** — lower
number is more urgent (see `PRIORITY_LABELS` in `app.storage.models`).

The column's default remains `2` ("High") rather than being changed to
`3` ("Medium") under the new labels. This is a deliberate non-change:
altering the default would silently reinterpret what "the usual
priority" means for anyone who already has tasks created under the old,
undocumented meaning, without actually fixing anything for them (their
existing rows already say `2`, whatever that's labeled today). If a
lower ("Medium") default turns out to be more useful in practice, that's
a product decision to make deliberately in a later phase, not a side
effect of documenting the scale.

### 5.7 New API structure

```
/projects                          POST, GET
/projects/{id}                     GET, PUT
/projects/{id}/archive              POST

/tasks                              POST, GET (+ filters: status, priority,
                                      project_id, tag_id, deadline_before,
                                      deadline_after, completed, search)
/tasks/{id}                        GET, PUT, DELETE
/tasks/{id}/tags                   GET
/tasks/{id}/tags/{tag_id}          POST (attach), DELETE (detach)
/tasks/{id}/dependencies           GET, POST
/tasks/{id}/dependencies/{dep_id}  DELETE

/tags                               POST, GET
```

Tag *creation* (`POST /tags`, `GET /tags`) lives in
`app.interfaces.api.tags`, separate from the task router, since creating
a tag isn't an action on any particular task; attach/detach/list-for-task
stay nested under `/tasks/{id}/...` since they act on a task's
associations.

### 5.8 Migrations: still deferred, narrowed instead of ignored

Phase 0.2 deferred Alembic on the grounds that there was no existing
data worth preserving yet. Phase 1 is the first schema change that
actually touches that: it adds `project_id` to the **already-existing**
`tasks` table, and `Base.metadata.create_all()` only creates missing
tables — it never alters an existing one's columns. Left unaddressed,
anyone who ran the Phase 0.2 app locally would have a `tasks` table
without `project_id`, and every query built against the Phase 1 model
would fail against it.

Rather than adopting Alembic wholesale for this one change, or leaving
existing local databases broken, `app.storage.database` gained a narrow,
purpose-built function (`_ensure_task_project_id_column`) that:
1. Detects whether `tasks` exists and already has `project_id`.
2. If not, runs a plain `ALTER TABLE tasks ADD COLUMN project_id INTEGER
   REFERENCES projects(id)` — SQLite supports adding a nullable column
   with no default this way. Existing rows get `NULL`, which is exactly
   correct (`project_id` is nullable — "no project" and "we don't know"
   are the same value). No existing column's data is touched.
3. Is idempotent and a no-op on a fresh database (where `create_all()`
   already created `tasks` with the column) or a non-SQLite backend.

This was verified directly against SQLite semantics (create an old-shape
`tasks` table, run the patch, confirm the column is added, existing rows
are intact, and re-running is a safe no-op) before being adopted — see
the project's implementation notes for that check.

**This is intentionally narrow** — it solves exactly one class of
change (an added nullable column, no rename, no backfill, no dropped
column) and is not a general migration mechanism. The exact point to
introduce Alembic for real: **the first schema change that isn't purely
additive** — a column rename, a `NOT NULL` added to a column that
already has rows, a data transformation/backfill, or a dropped column.
None of those are expressible as an idempotent "detect and patch"
function the way an added nullable column is; they need real up/down
migration scripts with a tracked revision history. `alembic` is already
present, commented out, in `requirements.txt` for exactly that moment.

## 6. Known risks / technical unknowns going into Phase 2 (as identified at the end of Phase 1)

- **Alembic adoption debt.** Every Phase 1+ schema change so far has
  been additive (new tables, one new nullable column) and handled by the
  narrow patch described above. The first non-additive change will need
  Alembic set up from scratch, including the awkward step of reconciling
  it with databases that already exist untracked (via `alembic stamp`)
  — worth doing deliberately, not under time pressure from an unrelated
  feature.
- **`TaskDependencyRepository.get_unresolved_dependencies` is one-hop by
  design** (see 5.4) — correct for blocking completion, but if a future
  feature wants to *show* a task's full transitive dependency chain (not
  just decide if it's blocked), that needs its own traversal; the
  one-hop query shouldn't be stretched to answer a different question.
- **No cascade/warning when archiving a project with open tasks.**
  Archiving succeeds regardless of how many active tasks still reference
  it — there's no confirmation step or count-of-affected-tasks feedback.
  Acceptable for a single-user local app now; revisit if project
  archiving becomes a more consequential action later (e.g. once
  notifications exist and an archived project's tasks should stop
  generating reminders).
- **Tag/dependency N+1 queries.** `TaskRead.tags` and any future
  "show dependency chain" feature fetch relationships lazily per task;
  fine at current data volume, worth revisiting with eager loading
  (`selectinload`) if `GET /tasks` response times become noticeable with
  many tasks.
- **SQLite concurrency** (carried over from Phase 0.2, still unaddressed
  — no scheduler exists yet to make it concrete).
- **Recurring tasks' interaction with dependencies** (carried over from
  Phase 0.2 — still an open design question, now slightly more concrete
  since dependencies exist: would a recurring task's dependencies reset
  each cycle, or only apply to the first instance?).

## 7. Phase 2 — habit, time, and reminder management (implemented)

Adds five new entities around the existing Task system: `Habit` +
`HabitCompletion`, `PomodoroSession`, `Reminder`, `ScheduleItem`, and
`Notification`. No AI, voice, frontend, or external integrations — pure
backend domain logic and API, same as every prior phase.

### 7.1 Package structure: one domain package per resource, not one "scheduling" package

Phase 0's original architecture sketch grouped Pomodoro, Reminders, and
Scheduling under a single `app.scheduling` package. That's been
superseded: Phase 2 gives each its own top-level package
(`app.habits`, `app.pomodoro`, `app.reminders`, `app.scheduling` —
repurposed for `ScheduleItem` only — and `app.notifications`), mirroring
the pattern already established by `app.projects` and `app.tasks`'s
internal tag/dependency split. Reasoning: the Phase 2 brief itself asks
for four independent route groups (`/pomodoro`, `/reminders`,
`/schedule`, `/notifications`), each with its own CRUD and its own
business rules; cramming three unrelated aggregates into one package
would just be the "giant manager class" anti-pattern one level up, at
the package instead of the class level.

### 7.2 Habit tracking

`Habit(id, name, frequency, target_count, created_at, archived_at)` and
`HabitCompletion(id, habit_id, completed_at, completed_date)`.

**The completion history is authoritative — there is no stored streak
number anywhere.** Every streak/statistics read fetches
`HabitCompletion` rows and recomputes from scratch (`app.habits.streak`,
pure functions, no database) rather than incrementing/decrementing a
cached counter. This was an explicit requirement in the brief and is
worth restating as a design principle: a cached streak can silently
drift from reality (a missed decrement, a bug in an edge case); a
recomputed one cannot, by construction, be wrong relative to the data
it's computed from — the only way to get a wrong streak is a wrong
*algorithm*, not stale cached state. The trade-off is recomputing on
every read instead of an O(1) lookup, which is the right trade at a
single local user's data volume.

**Streak algorithm.** A habit's timeline is divided into periods by
frequency (calendar day / ISO week / calendar month). A period is
"satisfied" if it has >= `target_count` completions. The current streak
counts consecutive satisfied periods walking backward from today, with
one exception: today's own period doesn't break the streak if
unsatisfied (it may simply not be over yet) — every period before
today's does need to be satisfied, or the streak stops there. Verified
against 9+ scenarios (consecutive days, a gap breaking the streak,
today-not-done-yet not breaking it, multi-week/month periods, a
year-boundary month rollover, and a defensive guard against
`today < created_date`) before being wired into `HabitService` — see
`tests/test_habit_streak.py`, which exercises the pure function
directly with no database.

**Duplicate completions**: rejected per calendar day, regardless of
frequency (`DuplicateCompletionError`, HTTP 409) — a weekly habit with
`target_count=3` still only gets one completion credited per day, not
three from the same day logged three times. Enforced twice: a
service-level check before insert (clear domain error), and a DB-level
`UniqueConstraint("habit_id", "completed_date")` as backstop —
`completed_date` is a plain stored column (set once from
`completed_at.date()`, never updated) rather than a SQL expression
index, to keep this to patterns already used elsewhere in the project
(see `app.storage.models.HabitCompletion`'s docstring for the fuller
reasoning).

**Archived habits**: same rule as archived Projects — archiving blocks
*new* completions (`ArchivedHabitError`, HTTP 409) but never hides or
alters existing history; a habit's completions, streak, and statistics
remain fully readable after archiving.

**Invalid `target_count`**: `CheckConstraint(1-100)` at the DB layer,
`Field(ge=1, le=100)` in the Pydantic schema. `frequency` is a native
enum column — an invalid value is a 422 from Pydantic before it ever
reaches the service.

### 7.3 Pomodoro sessions

`PomodoroSession(id, task_id, started_at, ended_at, interrupted,
duration_seconds)`. `task_id` uses `ondelete="SET NULL"` — a session is
a historical record that should outlive the task it was for, not be
deleted alongside it (same reasoning as `Task.project_id`).

A session can only be ended once (`SessionAlreadyEndedError`, HTTP 409).
"End normally" and "interrupt" are the same operation
(`POST /pomodoro/{id}/end`) differing only in an `interrupted: bool`
flag in the body — not two endpoints — since both are the identical
state transition (`ended_at` gets set, `duration_seconds` gets
computed) and duplicating the endpoint for a boolean difference would
be exactly the kind of "duplicate abstraction" the brief asks to avoid.
`duration_seconds` is computed and stored at end time (not recomputed
from `ended_at - started_at` on every read).

### 7.4 Reminders

`Reminder(id, task_id, remind_at, message, fired_at, created_at)`.
`created_at` isn't in the brief's suggested field list but was added
for consistency with every other entity in the project.

**Past `remind_at` is accepted, not rejected.** A reminder is just a
timestamp + message; rejecting a past time would only get in the way of
legitimate use (backfilling, testing, clock skew), and "is this
overdue" is already answered separately by `list_due_reminders`.

**Firing is idempotent.** `mark_fired` on an already-fired reminder is a
no-op that returns the current state, not an error — there is no
`ReminderAlreadyFiredError`. This is deliberate: the eventual caller of
this method is an automated dispatch/polling process (not built this
phase — see 7.7), and such a process needs to be safe to call twice on
the same reminder (e.g. after a retry) without crashing.

`GET /reminders?due=true` and `?upcoming=true` are the "identify due
reminders" / "list upcoming reminders" capabilities from the brief,
implemented as query parameters rather than new top-level routes, to
stay close to the brief's suggested route shape
(`/reminders`, `/reminders/{id}`).

### 7.5 Scheduling

`ScheduleItem(id, title, starts_at, ends_at, task_id)`, with a DB
`CheckConstraint("ends_at > starts_at")` behind the same validation in
`ScheduleService`.

**Conflicts are detected, not blocked.** `create_schedule_item` does
not call the conflict-detection query and does not reject an
overlapping item — this mirrors how real calendar tools behave (Google
Calendar, Outlook, etc. all allow double-booking and just surface it,
rather than refusing the second event). Overlap is frequently
intentional (a task block inside a longer meeting, a tentative
placeholder), and a hard block would need an escape hatch ("create
anyway") the brief didn't ask for. `ScheduleService.find_conflicts` is
its own directly-testable method and is reachable via
`GET /schedule/conflicts?starts_at=&ends_at=` as a query a caller can
run before or after creating something. If a stricter policy is wanted
later, that's a small, deliberate change to `create_schedule_item`, not
a default assumed now.

**Route-ordering note**: `/schedule/conflicts` is registered *before*
`/schedule/{item_id}` in `app/interfaces/api/schedule.py`. FastAPI
matches routes in registration order, and `{item_id}` would otherwise
greedily match the literal path segment "conflicts" as a string before
its own `int` conversion fails — a real gotcha, called out explicitly
in that file's module docstring and covered by
`tests/test_schedule_api.py::test_conflicts_endpoint_reachable_and_correct`.

### 7.6 Notifications

`Notification(id, title, body, created_at, read_at, source)`. The
thinnest service in the project — creation and read/unread toggling
(`mark_read`/`mark_unread`, both idempotent, same reasoning as
`Reminder.mark_fired`) have no business rules beyond "does it exist".

**Deliberately just a data record.** No OS-level desktop notification
dispatch (Linux D-Bus/`notify-send`, Windows toast, macOS
`NSUserNotification`) exists anywhere in this phase — the brief
explicitly excludes it. `app.notifications`'s package docstring
documents the intended seam: a future adapter belongs in
`app.integrations`, reading `Notification` rows and dispatching them to
the OS, kept separate so the core domain never depends on which
operating system the app happens to run on.

**No automatic Reminder -> Notification linkage.** Firing a reminder
does not create a Notification, and nothing polls for due reminders
automatically — see 7.8 below. Wiring that up is a natural next step but
was deliberately left out this phase to avoid adding a background
scheduler/polling loop, which is a meaningfully different kind of
component (a long-running process, not a request-scoped one) than
anything built so far, and wasn't asked for.

### 7.7 New API structure

```
/habits                             POST, GET
/habits/{id}                        GET, PUT
/habits/{id}/archive                 POST
/habits/{id}/complete                POST
/habits/{id}/history                 GET
/habits/{id}/statistics              GET

/pomodoro                           POST, GET (+ ?task_id filter)
/pomodoro/{id}                      GET
/pomodoro/{id}/end                   POST ({"interrupted": bool})

/reminders                          POST, GET (+ ?due / ?upcoming)
/reminders/{id}                     GET, PUT, DELETE
/reminders/{id}/fire                 POST

/schedule                           POST, GET
/schedule/conflicts                  GET (?starts_at=&ends_at=&exclude_id=)
/schedule/{id}                      GET, PUT, DELETE

/notifications                      POST, GET (+ ?unread_only)
/notifications/{id}                 GET
/notifications/{id}/read             POST
/notifications/{id}/unread           POST
```

### 7.8 Migrations: no patch needed this phase

Every Phase 2 table (`habits`, `habit_completions`, `pomodoro_sessions`,
`reminders`, `schedule_items`, `notifications`) is brand new — nothing
about any *existing* table (`tasks`, `projects`, `tags`, ...) changed
shape. `Base.metadata.create_all()` creates missing tables and leaves
existing ones alone, which is exactly sufficient here: unlike Phase 1
(which added a column to the already-existing `tasks` table and needed
the narrow additive patch in `app.storage.database`), there is nothing
for that patch — or Alembic — to do this time. `create_all_tables()`
runs its Phase 1 patch check regardless (it's a cheap, idempotent
no-op when the column already exists), so nothing needed to change
there either.

This doesn't retire the Alembic question — see the "Known risks going
into Phase 3" list below and section 5.8 above for the still-standing
trigger condition (the first non-additive schema change).

## 8. Known limitations / technical debt going into Phase 3

- **No background scheduler/dispatcher.** `list_due_reminders` and
  `mark_fired` exist, but nothing calls them automatically — a reminder
  becoming "due" doesn't do anything on its own. The same is true for
  turning a fired reminder into a `Notification`. Building this needs a
  genuinely different kind of component (a long-running polling loop or
  an async task scheduler), which is a deliberate scope boundary for
  Phase 2, not an oversight.
- **No desktop notification dispatch**, per the brief — `app.notifications`
  is data-only; see 7.6 for the intended future seam in
  `app.integrations`.
- **Schedule conflicts are informational only** — see 7.5. Revisit if a
  stricter double-booking policy turns out to be wanted.
- **Habit statistics recompute from full history on every read.** Fine
  at a single local user's scale; would need indexing/caching
  consideration if `HabitCompletion` rows grew very large (years of
  daily data across many habits) — not a concern yet.
- **Alembic adoption debt persists** (carried over from Phase 1, still
  unaddressed — Phase 2 didn't need it either; see 5.8 and 7.8 for the
  exact trigger condition).
- **`TaskDependencyRepository.get_unresolved_dependencies` is one-hop by
  design** (carried over from Phase 1, still accurate).
- **Tag/dependency N+1 queries** (carried over from Phase 1, still
  accurate — now joined by Habit completion history and Pomodoro/
  Reminder/ScheduleItem lists as other places that fetch per-row without
  eager loading; none of these are a problem yet at current data
  volumes).
- **SQLite concurrency** (carried over from Phase 0.2 — a background
  scheduler, whenever it's built, is exactly the point this becomes
  concrete rather than theoretical).

## 9. Phase 4 Architecture — AI Assistant

Phase 4 introduces a text-based AI assistant core that operates over the productivity application's domain services using structured, validated tool execution.

### 9.1 Key Components & Architecture Seam

1. **Single AssistantCore Seam (`app.core.assistant` & `app.ai.assistant`)**:
   - `app.ai.assistant.AssistantCore` is the single canonical orchestrator for AI tool loops and message handling.
   - `app.core.assistant.AssistantCore` re-exports `app.ai.assistant.AssistantCore` to maintain a single core seam for all present and future interfaces (Web API, Voice, CLI) without duplicating logic.

2. **AI Provider Abstraction (`app.ai.provider`)**:
   - `AIProvider` base class with `MockAIProvider` (offline-first, deterministic keyword triggers) and `OpenAICompatibleProvider` (for OpenAI, Groq, Ollama, vLLM, etc.).
   - Factory `get_ai_provider()` instantiates the configured provider based on `AI_PROVIDER`, `AI_MODEL`, `AI_BASE_URL`, and `AI_API_KEY`.
   - Comprehensive error handling wraps provider connection failures cleanly in user-visible responses without crashing the server.

3. **Persistent Conversation System (`app.conversations`)**:
   - Stores conversations (`conversations`) and transcripts (`messages`) in SQLite.
   - Preserves message histories across application reboots.

4. **Tool Registry & Validation (`app.ai.tools`)**:
   - Standard domain tools covering Tasks, Projects, Habits, Pomodoro, Reminders, Schedule, and Notifications.
   - Enforces scope checking via `PermissionChecker` before executing domain services.
   - Tool arguments are parsed and validated via structured Pydantic schemas; arbitrary code execution is strictly prohibited.

5. **Assistant Core Engine (`app.ai.assistant`)**:
   - Orchestrates conversation history, injects system context (`ContextBuilder`) and deterministic daily plan suggestions (`DailyPlanner`).
   - Executes multi-turn tool loops with a max iteration limit of 5 to prevent runaway loops.

6. **Web Chat Interface (`app.interfaces.static`)**:
   - Dedicated AI Assistant view in the local web dashboard for real-time chat, conversation management, and tool call visibility.

### 9.2 Schema Safety & Database Migration Policy

- **Current Schema Safety**: Phase 4 added two new tables (`conversations` and `messages`), both fully additive with default table creation via `Base.metadata.create_all()`. Existing user data in Phase 0-3 tables remained completely untouched.
- **Phase 5 Schema Readiness**: Phase 5 will add the `memories` table for long-term AI memory persistence. This change is also purely additive.
- **Alembic Trigger Condition**: Alembic migrations remain deferred until the first non-additive schema change (e.g. column renames, altering existing column types, dropping columns, or adding `NOT NULL` constraints to existing populated tables). Alembic is already specified in `requirements.txt` ready for activation when required.


