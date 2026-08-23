"""Tests for ContextBuilder and DailyPlanner logic."""

from app.ai.context import ContextBuilder
from app.ai.planner import DailyPlanner
from app.habits.schemas import HabitCreate
from app.habits.service import HabitService
from app.tasks.schemas import TaskCreate
from app.tasks.service import TaskService


def test_context_builder(db_session):
    task_svc = TaskService(db_session)
    task_svc.create_task(TaskCreate(title="High Priority Task", priority=1))
    task_svc.create_task(TaskCreate(title="Low Priority Task", priority=4))

    builder = ContextBuilder()
    ctx = builder.build_context(db_session)

    assert "high_priority_tasks" in ctx
    assert len(ctx["high_priority_tasks"]) == 1
    assert ctx["high_priority_tasks"][0]["title"] == "High Priority Task"

    prompt_str = builder.format_context_prompt(db_session)
    assert "High Priority Task" in prompt_str


def test_daily_planner(db_session):
    task_svc = TaskService(db_session)
    task_svc.create_task(TaskCreate(title="Important Task", priority=1))

    habit_svc = HabitService(db_session)
    habit_svc.create_habit(HabitCreate(name="Read 20 mins", frequency="daily"))

    planner = DailyPlanner()
    plan = planner.generate_plan(db_session)

    assert len(plan["top_tasks_to_tackle"]) == 1
    assert plan["top_tasks_to_tackle"][0]["title"] == "Important Task"
    assert len(plan["habits_to_complete"]) == 1

    prompt_str = planner.format_plan_prompt(db_session)
    assert "DETERMINISTIC DAILY PLAN PROPOSAL" in prompt_str
    assert "Important Task" in prompt_str
