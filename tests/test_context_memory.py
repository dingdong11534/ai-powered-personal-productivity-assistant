"""Unit tests for ContextBuilder and DailyPlanner memory integration."""

from app.ai.context import ContextBuilder
from app.ai.planner import DailyPlanner
from app.memories.schemas import MemoryCreate
from app.memories.service import MemoryService
from app.storage.models import MemoryCategory


def test_context_builder_with_memories(db_session):
    mem_svc = MemoryService(db_session)
    mem_svc.create_memory(MemoryCreate(content="User prefers working late at night", category=MemoryCategory.PREFERENCE))
    mem_svc.create_memory(MemoryCreate(content="Goal: Complete Phase 5", category=MemoryCategory.GOAL))

    builder = ContextBuilder()
    context = builder.build_context(db_session, query="night")
    assert len(context["relevant_memories"]) >= 1
    assert "late at night" in context["relevant_memories"][0]["content"]

    prompt_text = builder.format_context_prompt(db_session, query="night")
    assert "=== CURRENT SYSTEM CONTEXT ===" in prompt_text
    assert "-- Relevant Long-Term Memories --" in prompt_text
    assert "User prefers working late at night" in prompt_text


def test_daily_planner_with_memories(db_session):
    mem_svc = MemoryService(db_session)
    mem_svc.create_memory(MemoryCreate(content="User prefers 25-minute Pomodoro sessions", category=MemoryCategory.PREFERENCE))
    mem_svc.create_memory(MemoryCreate(content="Morning stretch routine before work", category=MemoryCategory.ROUTINE))

    planner = DailyPlanner()
    plan_dict = planner.generate_plan(db_session)
    assert len(plan_dict["user_preferences"]) == 1
    assert len(plan_dict["user_routines"]) == 1

    prompt_text = planner.format_plan_prompt(db_session)
    assert "User Preferences & Routines to Consider:" in prompt_text
    assert "[Pref] User prefers 25-minute Pomodoro sessions" in prompt_text
    assert "[Routine] Morning stretch routine before work" in prompt_text
