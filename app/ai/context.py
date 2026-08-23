"""Context building module for selective retrieval of user state."""

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.ai.tools.implementations import _to_dict
from app.habits.service import HabitService
from app.scheduling.service import ScheduleService
from app.tasks.service import TaskService


class ContextBuilder:
    """Deliberately selects relevant structured information for the AI prompt."""

    def build_context(self, session: Session) -> dict[str, Any]:
        task_svc = TaskService(session)
        habit_svc = HabitService(session)
        sched_svc = ScheduleService(session)

        # High priority tasks (1=Critical, 2=High)
        high_priority = task_svc.list_tasks(completed=False)
        high_priority = [t for t in high_priority if t.priority in (1, 2)][:10]

        # Upcoming deadlines
        deadlines = [t for t in task_svc.list_tasks(completed=False) if t.deadline is not None]
        deadlines.sort(key=lambda t: t.deadline)
        deadlines = deadlines[:10]

        # Active habits
        habits = habit_svc.list_habits(include_archived=False)
        habit_summary = []
        for h in habits:
            stats = habit_svc.get_statistics(h.id)
            habit_summary.append({
                "id": h.id,
                "name": h.name,
                "frequency": h.frequency,
                "target_count": h.target_count,
                "current_streak": stats.current_streak,
            })

        # Today's schedule
        schedule_items = sched_svc.list_schedule_items()

        return {
            "high_priority_tasks": [_to_dict(t) for t in high_priority],
            "upcoming_deadlines": [_to_dict(t) for t in deadlines],
            "habits": habit_summary,
            "schedule_items": [_to_dict(s) for s in schedule_items],
        }

    def format_context_prompt(self, session: Session) -> str:
        ctx = self.build_context(session)
        lines = ["=== CURRENT SYSTEM CONTEXT ==="]

        lines.append("\n-- High Priority Pending Tasks --")
        if ctx["high_priority_tasks"]:
            for t in ctx["high_priority_tasks"]:
                lines.append(f"- [#{t['id']}] {t['title']} (Priority {t['priority']}, Status: {t['status']})")
        else:
            lines.append("No critical/high priority pending tasks.")

        lines.append("\n-- Upcoming Deadlines --")
        if ctx["upcoming_deadlines"]:
            for t in ctx["upcoming_deadlines"]:
                lines.append(f"- [#{t['id']}] {t['title']} (Due: {t['deadline']})")
        else:
            lines.append("No upcoming deadlines.")

        lines.append("\n-- Active Habits --")
        if ctx["habits"]:
            for h in ctx["habits"]:
                lines.append(f"- [#{h['id']}] {h['name']} ({h['frequency']}, Streak: {h['current_streak']} periods)")
        else:
            lines.append("No active habits.")

        lines.append("\n-- Today's Schedule --")
        if ctx["schedule_items"]:
            for s in ctx["schedule_items"]:
                lines.append(f"- [#{s['id']}] {s['title']} ({s['starts_at']} to {s['ends_at']})")
        else:
            lines.append("No scheduled blocks today.")

        return "\n".join(lines)
