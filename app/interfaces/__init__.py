"""
Interface layer — FastAPI routes and (later) web UI glue, CLI.

main.py  - constructs the FastAPI app, wires startup (table creation) and
           the TaskNotFoundError -> HTTP 404 translation, includes routers.
api/     - one router module per resource (api/tasks.py for now).

This is the only layer allowed to depend on everything else (core,
domain packages, ai, storage). Nothing outside app.interfaces should
import from it — that keeps domain logic usable from tests, a future
CLI, or voice, without pulling in FastAPI.

Routes themselves stay thin: parse the request (via a Pydantic schema,
handled automatically by FastAPI), call exactly one TaskService method,
return what it gives back. Anything more than that in a route function is
a sign the logic belongs in app.tasks.service instead.
"""
