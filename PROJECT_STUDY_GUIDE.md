# Personal Productivity Assistant — Complete Study Guide

> **Purpose of this file**: A self-contained reference you can paste into any AI chatbot to get targeted help studying this codebase. It covers the "what", "why", and "how" of every major decision in this project.

---

## 1. What Is This Project?

A **local-first, AI-assisted personal productivity backend** built as a learning project in Python. It manages:

- Tasks, projects, tags, and task dependencies
- Habits and habit completion tracking (with streak computation)
- Pomodoro focus sessions
- Reminders and scheduling
- Notifications
- AI assistant conversations with tool-calling (the AI can actually create tasks, check habits, etc.)
- Long-term AI memory (persistent facts the assistant remembers across sessions)
- A sandboxed file workspace the AI can read/write
- Real-time weather fetching via SSRF-safe external HTTP client
- **Streaming AI responses** via Server-Sent Events (SSE)
- A full **web dashboard UI** served as static files

**It is NOT**:
- A multi-user SaaS app (single local user only)
- A mobile app (REST API + web dashboard only)
- Production-hardened (it's a learning project with deliberate, documented tradeoffs)

**Key design philosophy**: Every decision is documented with a "why", not just a "what". The project is built phase-by-phase, adding only what's needed per phase — no speculative features.

---

## 2. Tech Stack

### Runtime & Language
| Technology | Version | Role | Why |
|---|---|---|---|
| **Python** | ≥ 3.11 | Primary language | Modern type hints (X \| Y, match), standard library improvements |
| **FastAPI** | 0.111–0.115 | HTTP API framework | Automatic OpenAPI docs, native Pydantic integration, type-driven routing |
| **Uvicorn** | 0.29+ | ASGI server | FastAPI's recommended production-grade server |
| **SQLAlchemy** | 2.0+ | ORM + DB abstraction | Type-safe 2.0 API, keeps DB swappable (SQLite now, PostgreSQL later) |
| **SQLite** | (stdlib) | Local database | Zero-config, single-file, perfect for a single-user local app |
| **Pydantic** | ≥ 2.7 | Schema validation | FastAPI's request/response models; also used for config via pydantic-settings |
| **pydantic-settings** | ≥ 2.2 | Config management | Typed, validated settings from .env files; already a Pydantic project so zero new dependency family |
| **httpx** | ≥ 0.27 | HTTP client | Used by FastAPI's test client AND for outbound AI/external API calls |

### Dev Tooling
| Tool | Role |
|---|---|
| **pytest** | Test runner (407 tests across 52 test files covering every layer) |
| **ruff** | Linter + formatter (replaces flake8 + black + isort; fast, one tool) |
| **alembic** | DB migrations (commented out in requirements.txt, activated only at first non-additive schema change) |

### AI Layer
The AI layer supports multiple backends through a single abstraction:
- **MockAIProvider** — deterministic keyword-triggered responses, no API key needed, used in CI/tests
- **OpenAICompatibleProvider** — works with OpenAI, Groq, Ollama, vLLM, or any OpenAI-compatible endpoint

Both providers implement both `generate()` (blocking) and `generate_stream()` (SSE/streaming).

Current default: **Groq** (qwen/qwen3.8-27b model), configurable via .env.

---

## 3. Project Structure

```
personal-assistant/
├── app/                        # All application code
│   ├── core/                   # Shared infrastructure (config, events, permissions)
│   ├── storage/                # SQLAlchemy engine, session factory, ALL ORM models
│   ├── tasks/                  # Task domain: schemas, repository, service, exceptions
│   ├── projects/               # Project domain (same structure as tasks)
│   ├── habits/                 # Habit + completion + streak pure functions
│   ├── pomodoro/               # Pomodoro session domain
│   ├── reminders/              # Reminder domain
│   ├── scheduling/             # ScheduleItem domain
│   ├── notifications/          # Notification domain
│   ├── conversations/          # Chat conversation + message transcript persistence
│   ├── memories/               # Long-term AI memory (separate from chat history)
│   ├── files/                  # Sandboxed file workspace service
│   ├── planning/               # Placeholder package (daily planner logic lives in app/ai/planner.py)
│   ├── ai/                     # LLM abstraction, tool registry, assistant core
│   │   ├── provider.py         # AIProvider base class + Mock + OpenAI-compatible (blocking + streaming)
│   │   ├── assistant.py        # AssistantCore: orchestrates tool loops, streaming (SSE), context
│   │   ├── context.py          # ContextBuilder: injects memories + recent tasks into system prompt
│   │   ├── planner.py          # DailyPlanner: deterministic daily plan suggestions
│   │   └── tools/              # Tool registry + all tool implementations
│   │       ├── base.py         # BaseTool abstract class
│   │       ├── registry.py     # ToolRegistry: registers and executes tools
│   │       └── implementations.py  # All ~35 concrete tool classes (~1,100 lines)
│   ├── external/               # SSRF-safe outbound HTTP client
│   │   ├── client.py           # ExternalHttpClient (domain allowlist + DNS guard, uses stdlib urllib)
│   │   └── weather.py          # WeatherService using Open-Meteo (no API key required)
│   ├── integrations/           # Future: OS-level notification dispatch, calendars (stub)
│   ├── voice/                  # Placeholder: speech-to-text / text-to-speech (stub only)
│   └── interfaces/             # FastAPI app entry point + all API routers + static web UI
│       ├── main.py             # App bootstrap, exception handlers, router registration
│       ├── api/                # One router file per domain resource
│       │   ├── tasks.py, projects.py, habits.py, pomodoro.py
│       │   ├── reminders.py, schedule.py, notifications.py, tags.py
│       │   ├── conversations.py    # includes ?stream=true SSE endpoint
│       │   ├── memories.py, files.py
│       │   └── ai_config.py    # GET/POST /ai/mode (online/offline toggle)
│       └── static/             # Web dashboard served at /
│           ├── index.html      # Single-page app (~38 KB) with sections for every domain
│           ├── css/style.css   # Custom dark-mode CSS (CSS variables, no Tailwind)
│           └── js/app.js       # Vanilla JS SPA (~100 KB) — navigation, API calls, chat UI, SSE
├── tests/                      # 52 pytest test files, 407 tests — one per layer/resource
├── scripts/
│   └── seed_mock_data.py       # Seeds dev DB with demo tasks/habits/reminders on first startup
├── data/                       # SQLite DB (assistant.db) + AI file workspace/
├── docs/
│   └── architecture.md         # The canonical decision log (read this!)
├── requirements.txt            # Minimal — only what the current phase needs
├── pyproject.toml              # Project metadata + pytest + ruff config
└── .env.example                # Template for all environment variables
```

---

## 4. Layered Architecture (The Dependency Rule)

This is the most important concept in the project. The layers are strictly one-directional:

```
app.interfaces  (FastAPI routes, web UI static files)
       ↓
app.ai          (LLM abstraction, tool registry, assistant core, streaming)
       ↓
domain packages (app.tasks, app.projects, app.habits, app.pomodoro,
                 app.reminders, app.scheduling, app.notifications,
                 app.conversations, app.memories, app.files)
       ↓
app.storage     (SQLAlchemy engine, session, ORM models)
       ↓
app.core        (config, events bus, permissions — NO domain imports)
```

**Why this matters**:
- Domain packages NEVER import from app.interfaces — testable without a web server, reusable from CLI/voice.
- app.core has NO domain dependencies — it's the foundation every interface shares.
- Business logic (validation, cross-entity rules) lives in service classes, never in FastAPI routes.

### Within each domain package, there's another sub-layering:
```
exceptions.py   → plain Python exceptions (no FastAPI, no SQLAlchemy)
schemas.py      → Pydantic models for request/response
repository.py   → dumb CRUD against SQLAlchemy (no business rules)
service.py      → business rules, raises domain exceptions
```

Routes in app.interfaces.api.* translate domain exceptions to HTTP status codes in one place (e.g., TaskNotFoundError → 404).

---

## 5. Database Design

**All ORM models live in one file**: app/storage/models.py. This is intentional — it prevents cross-package model imports and keeps the full schema visible in one place.

### Core Tables

| Table | Key Fields | Notes |
|---|---|---|
| projects | id, name, description, color, created_at, archived_at | Soft-delete via archived_at |
| tasks | id, project_id→Project, title, status, priority(1-4), deadline, created_at, updated_at, completed_at | status enum: todo/in_progress/done/cancelled |
| task_dependencies | task_id, depends_on_task_id | Composite PK; cycle detection via Python BFS |
| tags | id, name(unique) | Simple |
| task_tags | task_id, tag_id | Plain association table (no mapped class) |
| habits | id, name, frequency, target_count, created_at, archived_at | frequency enum: daily/weekly/monthly |
| habit_completions | id, habit_id, completed_at, completed_date | completed_date stored column for unique constraint |
| pomodoro_sessions | id, task_id, started_at, ended_at, interrupted, duration_seconds | task_id SET NULL on delete |
| reminders | id, task_id, remind_at, message, fired_at, created_at | Past remind_at allowed |
| schedule_items | id, title, starts_at, ends_at, task_id | Conflicts detected, not blocked |
| notifications | id, title, body, created_at, read_at, source | Data-only; no OS dispatch yet |
| conversations | id, started_at, title | Chat session container |
| messages | id, conversation_id, role, content, created_at, tool_calls, tool_call_id, name | Raw transcript |
| memories | id, content, category, created_at, source_message_id, archived_at | Curated long-term facts |

### Migration Strategy
- **Base.metadata.create_all()** at startup — creates missing tables, leaves existing ones alone.
- **Narrow additive patches** for adding nullable columns to existing tables.
- **Alembic** commented out in requirements.txt — activated only at the first non-additive schema change.

---

## 6. Key Design Decisions (and Why)

### 6.1 Priority as Integer (1–4), Not Enum
- Lower number = more urgent (1=Critical, 4=Low)
- Enforced via CheckConstraint in DB + Pydantic Field(ge=1, le=4)
- Integer allows simple `ORDER BY priority ASC` for "most urgent first"

### 6.2 Habit Streaks Are Always Recomputed, Never Cached
- HabitCompletion rows are the source of truth
- Every GET /habits/{id}/statistics recomputes via pure Python in app/habits/streak.py
- **Why**: A cached streak counter can silently drift. A recomputed one is always consistent with its inputs.

### 6.3 Task Dependency Cycle Detection in Python BFS
- SQL has no clean way to express "no cycles across this whole edge set" as a constraint
- Solution: BFS from the proposed depends_on_task_id; if it reaches task_id, reject
- **Why not recursive SQL CTE**: The graph is small and BFS is far more readable and testable

### 6.4 Schedule Conflicts Are Detected, Not Blocked
- POST /schedule does NOT check for overlaps before inserting
- GET /schedule/conflicts exists for caller to query
- **Why**: Real calendar apps allow double-booking — overlap is frequently intentional

### 6.5 PUT Is Partial Update (Not Full Replacement)
- TaskUpdate, HabitUpdate, etc. have all-optional fields
- Only fields the client sends are applied: `model_dump(exclude_unset=True)`
- **Why**: A true REST PUT would require resending all fields to avoid accidentally nulling them

### 6.6 TaskNotFoundError Is a Plain Python Exception, Not HTTPException
- app.tasks has ZERO FastAPI imports
- The translation to HTTP 404 happens in exactly one place: app/interfaces/main.py
- **Why**: Keeps the domain package independently testable and reusable

### 6.7 Reminder Firing Is Idempotent (No Error on Second Fire)
- Calling POST /reminders/{id}/fire on an already-fired reminder is a no-op, not an error
- **Why**: The eventual caller is an automated polling process — safe to call twice after a retry

### 6.8 Archiving Never Deletes Data
- Archiving a project → only sets archived_at; tasks keep their project_id unchanged
- **Why**: History and statistics would be corrupted by hard-deletes

### 6.9 Database URL Is Absolute Path
- Default is `sqlite:////absolute/path/to/data/assistant.db`
- **Why**: A cwd-relative path silently resolves to a different file depending on launch location

### 6.10 Dependencies Are Added Phase-by-Phase
- requirements.txt only contains what the current phase actually imports
- **Why**: No speculative dependencies; `pip install -r requirements.txt` installs exactly what runs

---

## 7. The AI System (Phases 4–8)

### How the AI Works (Tool-Calling Loop)

```
User message
    → AssistantCore.handle_user_message()  (or handle_user_message_stream() for SSE)
    → Build system prompt (inject memories via ContextBuilder + daily plan via DailyPlanner)
    → Load conversation history from DB
    → Call LLM (MockAIProvider or OpenAICompatibleProvider)
    → LLM responds with either:
        a) Text → save as assistant message → return
        b) Tool calls → execute each via ToolRegistry → save results → loop (max 5 iterations)
```

**The AI never executes arbitrary code**. It can only request named tool calls. Each tool call goes through:
1. ToolRegistry.execute_tool() — looks up the tool by name
2. PermissionChecker.check() — enforces scope (READ/WRITE/DESTRUCTIVE)
3. Tool function — calls domain service, returns structured result

### Streaming (Phase 8 — SSE)
`handle_user_message_stream()` is a generator that yields Server-Sent Events:
- `{"event": "delta", "content": "..."}` — streamed text tokens
- `{"event": "status", "stage": "tool_call", "name": "...", "arguments": {...}}` — before each tool runs
- `{"event": "tool_result", "name": "...", "result": {...}}` — after each tool completes
- `{"event": "done", "message": {...}, "message_id": N}` — final persisted message

The conversations API route exposes this via `POST /conversations/{id}/messages?stream=true` which returns a `StreamingResponse` with `media_type="text/event-stream"`. The frontend JS connects using `fetch` + `ReadableStream`, parsing SSE lines in real time.

### PermissionScope System
| Scope | Always Allowed? | Notes |
|---|---|---|
| READ | Yes | Viewing tasks, reading files, search |
| WRITE | Yes | Creating/updating data |
| DESTRUCTIVE | No | Requires authorized=True set by the trusted interface layer |
| EXTERNAL | Yes | Security enforced at HTTP client layer (domain allowlist + SSRF guard) |

For destructive operations, the API checks `data.authorize_destructive` or detects confirmation language ("yes", "confirm", "proceed", "delete it") in the user text via regex. The AI model **cannot** set this flag.

### AI Providers
- **Mock**: keyword-triggered deterministic responses. No API key. Used in tests.
- **OpenAI-compatible**: any server with OpenAI's chat completions API — OpenAI, Groq, Ollama, vLLM, etc.
- Configured via .env: `AI_PROVIDER`, `AI_MODEL`, `AI_BASE_URL`, `AI_API_KEY`
- Both providers implement `generate_stream()` which yields `{"type": "delta", ...}` + `{"type": "response", ...}` items

### Tool Registry (~35 tools in app/ai/tools/implementations.py)
- **Task tools**: create_task, update_task, list_tasks, search_tasks, complete_task, delete_task
- **Project tools**: create_project, list_projects, archive_project, delete_project
- **Habit tools**: create_habit, complete_habit, get_habit_statistics, delete_habit
- **Pomodoro tools**: start_pomodoro, end_pomodoro, delete_pomodoro_session
- **Reminder tools**: create_reminder, list_reminders, delete_reminder
- **Schedule tools**: create_schedule_item, list_schedule, delete_schedule_item
- **Notification tools**: list_notifications, mark_notification_read
- **Memory tools**: remember_information, list_memories, search_memories, update_memory, delete_memory
- **File tools**: list_workspace_files, read_workspace_file, create_workspace_file, update_workspace_file, search_workspace_files, delete_workspace_file
- **Weather tool**: get_current_weather (via SSRF-safe ExternalHttpClient → Open-Meteo API; no API key required)

### Long-Term Memory vs. Chat History
Two separate tables by design:
- **messages** = raw conversation transcript (every turn, verbatim)
- **memories** = curated facts the assistant extracts and stores ("User prefers morning tasks")

ContextBuilder does a keyword search against memories using the current user input, injecting the most relevant ones into the system prompt — so the AI "remembers" facts without cramming the entire history into the context window.

### Intelligent Task Creation Fallback
`AssistantCore` has regex-based intent parsing (`_extract_task_creation_intent`) that intercepts "create a task named X with high priority"-style messages. If the LLM returns no tool call (e.g., with local models), the assistant falls back to directly calling `create_task`. This is a pragmatic workaround for smaller/less reliable models.

---

## 8. The Sandboxed File Workspace (Phase 6)

The AI can read/write files, but **only inside data/workspace/**. app.files.FileService is the sole access path. It enforces:
- Rejects absolute paths, Windows drive paths (C:\), path traversal (../)
- Rejects symlinks escaping the root
- Limits recursive scan depth (default: 10 levels)
- Limits file read/write size (default: 1 MB)
- Limits search results (default: 100 entries)

Events (files.created, files.overwritten, files.deleted) are published to app.core.events.file_events.

---

## 9. The Event Bus (app.core.events)

A minimal synchronous publish/subscribe mechanism:

```python
event_bus.subscribe("task.completed", my_handler)
event_bus.publish("task.completed", {"task_id": 42})
```

**Why it exists**: Without it, app.tasks would need to import app.notifications, app.habits, etc. to trigger side effects — making modules coupled and hard to test in isolation.

**Deliberately NOT**: a message queue, async framework, or third-party library.

Three buses exist: `event_bus` (general), `file_events`, `external_events`.

---

## 10. The External HTTP Client (Phase 7)

`app.external.client` is an SSRF-safe HTTP client wrapper around `urllib` (stdlib, no extra dependency):
- **Domain allowlist**: only exact hostnames in `Settings.external_allowed_domains` are reachable
- **DNS guard**: resolves hostname before connecting; blocks private IP ranges (127.x, 10.x, 192.168.x, etc.)
- Limits response body size (default: 1 MB)
- Configurable timeout (default: 10 seconds)
- Publishes to `external_events` bus on every request attempt

`app.external.weather.WeatherService` wraps the client: geocoding (lat/lon lookup) → weather data fetch from Open-Meteo — zero API key required.

---

## 11. The Web Dashboard (Phase 3)

A fully functional **single-page web app** served at `/` from `app/interfaces/static/`:
- **index.html** (~38 KB): sections/tabs for Dashboard, Tasks, Projects, Habits, Pomodoro, Reminders, Schedule, Notifications, Chat, Memories, Files
- **css/style.css**: custom dark-mode CSS with CSS variables (`--bg-primary`, etc.)
- **js/app.js** (~100 KB, vanilla JS):
  - `initNavigation()` — tab routing
  - `checkActivePomodoroSession()` + floating Pomodoro widget (bottom-right)
  - Chat UI with **SSE streaming** support (reads `?stream=true` endpoint in real time)
  - `renderToolActionCard()` — renders tool call results as clickable UI cards that navigate to the relevant tab
  - Voice input via browser `SpeechRecognition` API (`toggleVoiceInput()`, microphone button `#chat-mic-btn`)
  - Toast notifications positioned at top (to avoid overlapping the bottom-right Pomodoro widget)

The server auto-seeds demo data (`scripts/seed_mock_data.py`) on first startup (skipped when `PYTEST_CURRENT_TEST` is set).

---

## 12. Configuration System (app.core.config)

Everything is configured through a single `Settings` object (Pydantic BaseSettings):

```python
settings = get_settings()   # cached singleton (lru_cache)
settings.database_url       # absolute SQLite path
settings.ai_provider        # "mock" | "openai" | "groq" | "ollama" | ...
settings.ai_model           # model name passed to provider
settings.workspace_dir      # sandboxed file workspace path
```

Reads from environment variables or .env file. Tests construct `Settings(...)` directly with overrides.

---

## 13. Testing Strategy

**52 test files, 407 tests**, structured to match the layered architecture:

| Test file pattern | What it tests |
|---|---|
| test_*_service.py | Domain service business rules (no HTTP, uses DB via conftest fixtures) |
| test_*_repository.py | Repository CRUD (direct DB, no services) |
| test_*_api.py | FastAPI routes end-to-end via TestClient |
| test_habit_streak.py | Pure functions with no DB at all |
| test_permissions.py | Permission system with no DB or HTTP |
| test_events.py | Event bus with no DB or HTTP |
| test_ai_*.py | AI assistant, tool execution, context, memory |
| test_external_client.py | SSRF-safe HTTP client (monkeypatches DNS) |
| test_streaming.py | Phase 8: SSE streaming (provider stream, AssistantCore stream, SSE endpoint) |
| test_frontend.py | Phase 3: web dashboard static file serving, HTML/CSS/JS structure |
| test_universal_delete_*.py | Universal delete tools across all domains |
| test_assistant_task_creation.py | Task creation intent parsing + fallback logic |

conftest.py provides:
- An in-memory SQLite test database (`:memory:`)
- A fresh TestClient per test
- An isolated `tmp_path`-based file workspace

Tests marked `@pytest.mark.live` make real external network calls and are excluded in CI.

---

## 14. API Endpoints Summary

All routes are at http://127.0.0.1:8000/. Interactive docs at /docs (Swagger UI).

### Resources & Methods
| Resource | Endpoints |
|---|---|
| Projects | POST/GET /projects, GET/PUT /projects/{id}, POST /projects/{id}/archive |
| Tasks | POST/GET /tasks, GET/PUT/DELETE /tasks/{id} |
| Task Tags | GET /tasks/{id}/tags, POST/DELETE /tasks/{id}/tags/{tag_id} |
| Task Dependencies | GET/POST /tasks/{id}/dependencies, DELETE /tasks/{id}/dependencies/{dep_id} |
| Tags | POST/GET /tags |
| Habits | POST/GET /habits, GET/PUT /habits/{id}, POST /habits/{id}/archive, POST /habits/{id}/complete, GET /habits/{id}/history, GET /habits/{id}/statistics |
| Pomodoro | POST/GET /pomodoro, GET /pomodoro/{id}, POST /pomodoro/{id}/end |
| Reminders | POST/GET /reminders, GET/PUT/DELETE /reminders/{id}, POST /reminders/{id}/fire |
| Schedule | POST/GET /schedule, GET /schedule/conflicts, GET/PUT/DELETE /schedule/{id} |
| Notifications | POST/GET /notifications, GET /notifications/{id}, POST /notifications/{id}/read, POST /notifications/{id}/unread |
| Conversations | POST/GET /conversations, GET/DELETE /conversations/{id}, GET/POST /conversations/{id}/messages |
| Conversations (SSE) | POST /conversations/{id}/messages?stream=true → SSE text/event-stream |
| Memories | POST/GET /memories, GET /memories/search, GET/PUT/DELETE /memories/{id}, POST /memories/{id}/archive |
| Files | GET /files, GET /files/read, POST /files/write, DELETE /files |
| AI Config | GET/POST /ai/mode (switch online/offline at runtime) |
| Web UI | GET / → serves static/index.html |
| Health | GET /health → {"status": "ok"} |

---

## 15. Development Phases (Project History)

| Phase | What Was Built |
|---|---|
| **0** | Project scaffold, config (pydantic-settings), event bus, permissions model |
| **0.2** | SQLAlchemy storage layer, Task CRUD API (FastAPI + SQLite) |
| **1** | Projects, Tags, TaskDependencies (cycle detection), Task filtering/search |
| **2** | Habits + streaks, Pomodoro sessions, Reminders, ScheduleItems, Notifications |
| **3** | Web dashboard (index.html + style.css + app.js), static file serving, seed script |
| **4** | AI assistant: provider abstraction, tool registry, conversation persistence, chat API |
| **5** | Long-term memory (memories table), ContextBuilder, DailyPlanner, Memories API |
| **6** | Sandboxed file workspace, file tools for AI, destructive permission gating |
| **7** | External HTTP client (SSRF-safe), WeatherService, get_current_weather AI tool |
| **8** | SSE streaming: `generate_stream()` on providers, `handle_user_message_stream()` in AssistantCore, SSE endpoint, frontend SSE consumer, voice input via browser SpeechRecognition |

---

## 16. Business Rules Quick Reference

| Rule | Where Enforced |
|---|---|
| Task cannot be done while a direct dependency is not done | TaskService.update_task |
| Dependency self-loop rejected (400) | TaskDependencyService |
| Dependency cycle rejected (409) — BFS algorithm | TaskDependencyService |
| Task project_id must reference a non-archived project | TaskService |
| Archiving a project never touches its tasks | ProjectService.archive_project |
| Habit allows at most 1 completion per calendar day | HabitService + DB UniqueConstraint |
| Pomodoro session can only be ended once (409 on second end) | PomodoroService |
| Schedule conflicts detected, not blocked | ScheduleService |
| Past remind_at accepted | ReminderService (intentional) |
| Reminder firing is idempotent | ReminderService |
| Notification read/unread toggle is idempotent | NotificationService |
| File operations sandboxed to data/workspace/ | FileService |
| Destructive file/tool actions require explicit authorization | PermissionChecker + FileService |
| Tag names must be unique | TagService + DB UNIQUE constraint |
| Tag attach/detach are idempotent | TagService |
| AI message size limit: 12,000 characters | AssistantCore |
| AI tool loop capped at 5 iterations | AssistantCore |
| External HTTP requests restricted to allowlisted domains | ExternalHttpClient |
| Streaming SSE: delta/status/tool_result/done events emitted in order | AssistantCore.handle_user_message_stream |
| Destructive authorization: regex on user text OR authorize_destructive flag | conversations API route |

---

## 17. Common Patterns to Study

### Service Layer Pattern (every domain uses this)

```python
# Repository: dumb CRUD, no business rules
class TaskRepository:
    def get(self, session, task_id) -> Task | None: ...
    def create(self, session, data) -> Task: ...

# Service: business rules, raises domain exceptions
class TaskService:
    def update_task(self, session, task_id, data):
        task = self.repo.get(session, task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        # ... business rule checks ...
        return self.repo.update(session, task, data)
```

### Exception Translation (one place, in interfaces/main.py)

```python
@app.exception_handler(TaskNotFoundError)
def task_not_found(request, exc):
    return JSONResponse(status_code=404, content={"detail": str(exc)})
```

### Partial Update with Pydantic

```python
class TaskUpdate(BaseModel):
    title: str | None = None
    status: TaskStatus | None = None
    priority: int | None = Field(None, ge=1, le=4)

# In service:
update_data = task_update.model_dump(exclude_unset=True)  # only sent fields
```

### Idempotent Operations

```python
def mark_fired(self, session, reminder_id) -> Reminder:
    reminder = self._get_or_raise(session, reminder_id)
    if reminder.fired_at is None:   # only set if not already fired
        reminder.fired_at = datetime.utcnow()
        session.commit()
    return reminder   # return current state regardless
```

### SSE Streaming Pattern

```python
# Provider: yields deltas then a final response object
def generate_stream(self, messages, tools=None) -> Iterator[dict]:
    for chunk in streaming_api_call(...):
        yield {"type": "delta", "content": chunk_text}
    yield {"type": "response", "response": AIResponse(...)}

# AssistantCore: translates provider items to SSE events
def handle_user_message_stream(self, conversation_id, user_content):
    for item in self.provider.generate_stream(messages, tools=schemas):
        if item["type"] == "delta":
            yield {"event": "delta", "content": item["content"]}
    yield {"event": "done", "message": saved_msg.model_dump(), "message_id": saved_msg.id}

# FastAPI route: wraps generator in StreamingResponse
def sse_generator():
    for event in assistant.handle_user_message_stream(conv_id, text):
        yield f"data: {json.dumps(event)}\n\n"
return StreamingResponse(sse_generator(), media_type="text/event-stream")
```

---

## 18. Setup & Running

```bash
# 1. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env: set AI_PROVIDER, AI_API_KEY, etc.

# 4. Run the API server (creates DB automatically on first start; seeds mock data)
.venv/bin/uvicorn app.interfaces.main:app --reload

# 5. Access
# Web dashboard:    http://127.0.0.1:8000/
# Interactive docs: http://127.0.0.1:8000/docs
# Health check:     http://127.0.0.1:8000/health

# 6. Run tests
.venv/bin/pytest -v
# → 407 tests collected across 52 files
```

### AI Provider Configuration Options

```bash
# Offline (no API key, no network): use mock
AI_PROVIDER=mock

# Cloud via Groq (fast, free tier)
AI_PROVIDER=groq
AI_BASE_URL=https://api.groq.com/openai/v1
AI_MODEL=qwen/qwen3.8-27b
AI_API_KEY=gsk_your_key_here

# Local Ollama
AI_PROVIDER=openai
AI_BASE_URL=http://localhost:11434/v1
AI_MODEL=llama3
AI_API_KEY=ollama

# OpenAI
AI_PROVIDER=openai
AI_BASE_URL=https://api.openai.com/v1
AI_MODEL=gpt-4o-mini
AI_API_KEY=sk-your_key_here
```

---

## 19. Files Worth Reading First (Recommended Order)

1. **docs/architecture.md** — the canonical decision log; explains every major choice
2. **app/core/config.py** — how config works, why lru_cache, why absolute DB path
3. **app/core/permissions.py** — the permission model (READ/WRITE/DESTRUCTIVE/EXTERNAL)
4. **app/core/events.py** — the event bus (why it exists, how pub/sub works)
5. **app/storage/models.py** — all ORM models in one place; read the docstrings
6. **app/tasks/service.py** — the canonical example of a service class with business rules
7. **app/habits/streak.py** — pure functions for streak computation (no DB, easily testable)
8. **app/ai/provider.py** — MockAIProvider + OpenAICompatibleProvider; blocking and streaming
9. **app/ai/assistant.py** — `handle_user_message()` + `handle_user_message_stream()`; the tool loop
10. **app/ai/tools/implementations.py** — all AI tools; how they call domain services
11. **app/external/client.py** — SSRF-safe HTTP client; domain allowlist + DNS guard
12. **app/external/weather.py** — WeatherService: geocoding + Open-Meteo fetch
13. **app/files/service.py** — sandbox enforcement; how path safety works
14. **app/interfaces/main.py** — FastAPI app, exception handlers, router registration, static files
15. **app/interfaces/api/conversations.py** — SSE streaming endpoint (`?stream=true`)
16. **app/interfaces/static/js/app.js** — frontend SSE consumer, tool action cards, voice input
17. **tests/conftest.py** — how tests are isolated (in-memory DB, tmp workspace)
18. **tests/test_streaming.py** — how SSE streaming is tested end-to-end
