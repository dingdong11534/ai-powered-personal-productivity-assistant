"""Deterministic application-driven daily planning generator."""

from datetime import datetime
from typing import Any
from sqlalchemy.orm import Session

from app.ai.tools.implementations import _to_dict
from app.habits.service import HabitService
from app.memories.service import MemoryService
from app.scheduling.service import ScheduleService
from app.storage.models import MemoryCategory
from app.tasks.service import TaskService


class DailyPlanner:
    """Computes a deterministic daily plan based on system state and user preferences."""

    def generate_plan(self, session: Session, user_id: int | None = None) -> dict[str, Any]:
        task_svc = TaskService(session)
        habit_svc = HabitService(session)
        sched_svc = ScheduleService(session)
        memory_svc = MemoryService(session)

        all_tasks = task_svc.list_tasks(completed=False, user_id=user_id)
        # Sort by priority ascending (1 = Critical), then deadline nullable
        all_tasks.sort(key=lambda t: (t.priority, t.deadline or datetime(9999, 12, 31)))

        top_tasks = all_tasks[:5]
        habits = habit_svc.list_habits(include_archived=False, user_id=user_id)
        schedule = sched_svc.list_schedule_items(user_id=user_id)

        prefs = memory_svc.list_memories(category=MemoryCategory.PREFERENCE, user_id=user_id)
        routines = memory_svc.list_memories(category=MemoryCategory.ROUTINE, user_id=user_id)

        plan_summary = {
            "top_tasks_to_tackle": [_to_dict(t) for t in top_tasks],
            "habits_to_complete": [_to_dict(h) for h in habits],
            "scheduled_time_blocks": [_to_dict(s) for s in schedule],
            "user_preferences": [_to_dict(p) for p in prefs],
            "user_routines": [_to_dict(r) for r in routines],
            "total_pending_tasks_count": len(all_tasks),
        }
        return plan_summary

    def format_plan_prompt(self, session: Session, user_id: int | None = None) -> str:
        plan = self.generate_plan(session, user_id=user_id)
        lines = ["=== DETERMINISTIC DAILY PLAN PROPOSAL ==="]
        lines.append(f"Total Pending Tasks: {plan['total_pending_tasks_count']}")

        lines.append("\nTop Recommended Tasks to Work On:")
        for t in plan["top_tasks_to_tackle"]:
            lines.append(f" 1. Task #{t['id']}: {t['title']} [Priority {t['priority']}]")

        lines.append("\nHabits to Complete Today:")
        for h in plan["habits_to_complete"]:
            lines.append(f" - Habit #{h['id']}: {h['name']} ({h['frequency']})")

        lines.append("\nScheduled Time Blocks:")
        for s in plan["scheduled_time_blocks"]:
            lines.append(f" - Block #{s['id']}: {s['title']} ({s['starts_at']} - {s['ends_at']})")

        if plan["user_preferences"] or plan["user_routines"]:
            lines.append("\nUser Preferences & Routines to Consider:")
            for p in plan["user_preferences"]:
                lines.append(f" - [Pref] {p['content']}")
            for r in plan["user_routines"]:
                lines.append(f" - [Routine] {r['content']}")

        return "\n".join(lines)

