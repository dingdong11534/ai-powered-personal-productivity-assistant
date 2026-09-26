"""
Permission model.

WHAT THIS DOES (eventually)
-----------------------------
Defines the vocabulary of "sensitive action" the rest of the system will
use, and a `PermissionChecker` that decides whether a given action is
allowed to proceed. Right now, in Phase 0, this file only establishes the
*shape* of that system — an enum of permission scopes and a checker with
a single, obviously-safe default policy. It does almost nothing yet, on
purpose.

WHY IT EXISTS
-------------
The project spec is explicit that the AI layer must never directly execute
arbitrary actions — every AI-requested action has to pass through
validation. That validation needs a place to live that is:
- independent of *which* action is being requested (task update vs. file
  write vs. sending a notification), so new tools don't each reinvent
  their own ad hoc checks
- independent of *who* is asking (AI tool call vs. web UI vs. voice),
  so the same rule can't be bypassed by going through a different
  interface

Defining this scaffold in Phase 0, before there's anything to protect,
is intentional: Phase 6/7 (file tools, external integrations) will import
and depend on this rather than growing their own permission logic
in isolation, which is exactly the kind of thing that becomes very hard
to retrofit once ten call sites already have their own ad hoc checks.

WHAT IS *NOT* HERE YET (deliberately)
----------------------------------------
- No user-facing confirmation flow (that needs an interface to prompt
  through — Phase 3+).
- No per-action fine-grained rules (e.g. "confirm before deleting more
  than N tasks") — those get added when the action they protect exists.
- No persistence of granted/denied decisions.

Building those now, before Phase 1 even has a Task model, would be
guessing at requirements instead of responding to them.

HOW TO TEST
------------
See tests/test_permissions.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PermissionScope(str, Enum):
    """Categories of action the system can gate.

    Kept small and coarse-grained for now. Split a scope into finer-grained
    ones only when a concrete feature needs to distinguish them — e.g.
    FILE_READ vs FILE_WRITE will likely split further once Phase 6 defines
    the actual file tools.
    """

    READ = "read"  # non-destructive: viewing tasks, reading files, search
    WRITE = "write"  # creating/updating data: new task, edited habit
    DESTRUCTIVE = "destructive"  # deleting data, overwriting files
    EXTERNAL = "external"  # calls to external APIs (Phase 7)


@dataclass(frozen=True)
class PermissionRequest:
    """A single request to perform some scoped action.

    `actor` identifies who's asking (e.g. "ai", "web-ui", "cli") so that,
    later, policy can differ by actor without changing every call site —
    only PermissionChecker.check needs to know the rule changed.
    """

    scope: PermissionScope
    actor: str
    description: str
    authorized: bool = False


class PermissionDenied(Exception):
    """Raised when a PermissionRequest is not allowed to proceed."""


class PermissionChecker:
    """Decides whether a PermissionRequest is allowed.

    Scope policy:
    - READ, WRITE:    always allowed.
    - EXTERNAL:       allowed — security is enforced at the HTTP client layer
                      (domain allowlist + SSRF DNS guard in app.external.client),
                      not here. Requiring per-request user authorization for
                      benign network reads (like fetching weather) would be wrong
                      UX and adds no safety: the target domain is hardcoded in
                      tool code, and ExternalHttpClient rejects anything not in
                      the allowlist regardless of how the tool is called.
    - DESTRUCTIVE:    denied unless `request.authorized` is True (set only by the
                      trusted interface layer after explicit user confirmation).
    """

    def check(self, request: PermissionRequest) -> None:
        """Raise PermissionDenied if `request` is not allowed; else return None."""
        if request.scope is PermissionScope.DESTRUCTIVE and not request.authorized:
            raise PermissionDenied(
                f"{request.actor} requested destructive action "
                f"({request.description!r}) — explicit user authorization is required."
            )
