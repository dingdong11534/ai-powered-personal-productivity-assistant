"""Context building module for selective retrieval of user state and relevant memory context."""

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.ai.tools.implementations import _to_dict
from app.habits.service import HabitService
from app.memories.service import MemoryService
from app.projects.service import ProjectService
from app.reminders.service import ReminderService
from app.scheduling.service import ScheduleService
from app.tasks.service import TaskService


class ContextBuilder:
    """Deliberately selects relevant structured information for the AI prompt."""

    def build_context(
        self,
        session: Session,
        query: str | None = None,
        is_local: bool = False,
        user_id: int | None = None,
    ) -> dict[str, Any]:
        task_svc = TaskService(session)
        habit_svc = HabitService(session)
        sched_svc = ScheduleService(session)
        memory_svc = MemoryService(session)
        project_svc = ProjectService(session)
        reminder_svc = ReminderService(session)

        limit_count = 5 if is_local else 10

        # Recent tasks (newest first, so index 0 is always the most recent task)
        all_recent = task_svc.list_tasks(limit=limit_count, user_id=user_id)

        # High priority pending tasks (1=Critical, 2=High)
        high_priority = task_svc.list_tasks(completed=False, user_id=user_id)
        high_priority = [t for t in high_priority if t.priority in (1, 2)][:limit_count]

        # Upcoming deadlines
        deadlines = [t for t in task_svc.list_tasks(completed=False, user_id=user_id) if t.deadline is not None]
        deadlines.sort(key=lambda t: t.deadline)
        deadlines = deadlines[:limit_count]

        # Active projects
        projects = project_svc.list_projects(include_archived=False, user_id=user_id)[:limit_count]

        # Upcoming reminders
        reminders = reminder_svc.list_upcoming_reminders(user_id=user_id)[:limit_count]

        # Active habits
        habits = habit_svc.list_habits(include_archived=False, user_id=user_id)[:limit_count]
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
        schedule_items = sched_svc.list_schedule_items(user_id=user_id)[:limit_count]

        # Relevant memories
        mem_limit = 2 if is_local else 5
        relevant_mems = memory_svc.retrieve_relevant_memories(query=query, limit=mem_limit, user_id=user_id)

        return {
            "recent_tasks": [_to_dict(t) for t in all_recent],
            "high_priority_tasks": [_to_dict(t) for t in high_priority],
            "upcoming_deadlines": [_to_dict(t) for t in deadlines],
            "projects": [_to_dict(p) for p in projects],
            "reminders": [_to_dict(r) for r in reminders],
            "habits": habit_summary,
            "schedule_items": [_to_dict(s) for s in schedule_items],
            "relevant_memories": [_to_dict(m) for m in relevant_mems],
        }

    def format_context_prompt(
        self,
        session: Session,
        query: str | None = None,
        is_local: bool = False,
        user_id: int | None = None,
    ) -> str:
        ctx = self.build_context(session, query=query, is_local=is_local, user_id=user_id)
        lines = ["=== CURRENT SYSTEM CONTEXT ==="]

        lines.append("\n-- Recent Tasks (Newest First) --")
        if ctx.get("recent_tasks"):
            for idx, t in enumerate(ctx["recent_tasks"]):
                tag = " [MOST RECENT TASK]" if idx == 0 else ""
                p_label = {1: "Critical", 2: "High", 3: "Medium", 4: "Low"}.get(t.get("priority"), str(t.get("priority")))
                lines.append(f"- [#{t['id']}] {t['title']} (Status: {t['status']}, Priority: {p_label}){tag}")
        else:
            lines.append("No tasks recorded.")

        lines.append("\n-- High Priority Pending Tasks --")
        if ctx["high_priority_tasks"]:
            for t in ctx["high_priority_tasks"]:
                lines.append(f"- [#{t['id']}] {t['title']} (Priority {t['priority']}, Status: {t['status']})")
        else:
            lines.append("No critical/high priority pending tasks.")

        lines.append("\n-- Active Projects --")
        if ctx.get("projects"):
            for p in ctx["projects"]:
                lines.append(f"- [#{p['id']}] {p['name']}")
        else:
            lines.append("No active projects.")

        lines.append("\n-- Upcoming Reminders --")
        if ctx.get("reminders"):
            for r in ctx["reminders"]:
                lines.append(f"- [#{r['id']}] {r['message']} (Remind at: {r.get('remind_at')})")
        else:
            lines.append("No pending reminders.")

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

        lines.append("\n-- Relevant Long-Term Memories --")
        if ctx["relevant_memories"]:
            for m in ctx["relevant_memories"]:
                lines.append(f"- [#{m['id']}] ({m['category']}) {m['content']}")
        else:
            lines.append("No relevant memories stored.")

        # Compact historical chat context (Token-efficient)
        chat_summaries = self.get_recent_conversations_summary(session, limit=2 if is_local else 3, user_id=user_id)
        if chat_summaries:
            lines.append("\n-- Recent Past Chats (Historical Context) --")
            for cs in chat_summaries:
                asst_snippet = f" -> Outcome: '{cs['last_assistant_outcome']}'" if cs["last_assistant_outcome"] else ""
                lines.append(f"- [Chat #{cs['id']}: \"{cs['title']}\"] User asked: '{cs['last_user_query']}'{asst_snippet}")

        return "\n".join(lines)

    def get_recent_conversations_summary(
        self, session: Session, limit: int = 3, user_id: int | None = None
    ) -> list[dict[str, Any]]:
        """Retrieve a token-efficient summary of recent conversation turns across past sessions."""
        try:
            from app.conversations.service import ConversationService
            conv_svc = ConversationService(session)
            convs = conv_svc.list_conversations(limit=limit, user_id=user_id)
            summaries: list[dict[str, Any]] = []
            for c in convs:
                msgs = conv_svc.get_messages(c.id)
                user_msgs = [m.content for m in msgs if m.role == "user" and m.content]
                asst_msgs = [m.content for m in msgs if m.role == "assistant" and m.content]
                if not user_msgs:
                    continue
                last_user = user_msgs[-1][:140].replace("\n", " ").strip()
                last_asst = asst_msgs[-1][:140].replace("\n", " ").strip() if asst_msgs else ""
                summaries.append({
                    "id": c.id,
                    "title": c.title or f"Chat #{c.id}",
                    "last_user_query": last_user,
                    "last_assistant_outcome": last_asst,
                })
            return summaries
        except Exception:
            return []

