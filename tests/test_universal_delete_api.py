from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.storage.models import Habit, PomodoroSession, Project, Reminder, ScheduleItem, Task


def test_delete_project_api_endpoint(client: TestClient, db_session: Session):
    # Create project
    create_resp = client.post("/projects", json={"name": "API Project", "description": "Desc"})
    assert create_resp.status_code == 201
    proj_id = create_resp.json()["id"]

    # Create task linked to project
    task_resp = client.post("/tasks", json={"title": "Linked Task", "project_id": proj_id})
    assert task_resp.status_code == 201
    task_id = task_resp.json()["id"]

    # Delete project
    del_resp = client.delete(f"/projects/{proj_id}")
    assert del_resp.status_code == 204

    # Verify project is gone
    get_proj = client.get(f"/projects/{proj_id}")
    assert get_proj.status_code == 404

    # Verify task still exists and project_id is None
    get_task = client.get(f"/tasks/{task_id}")
    assert get_task.status_code == 200
    assert get_task.json()["project_id"] is None

    # Deleting nonexistent project gives 404
    del_again = client.delete(f"/projects/{proj_id}")
    assert del_again.status_code == 404


def test_delete_habit_api_endpoint(client: TestClient, db_session: Session):
    # Create habit
    create_resp = client.post("/habits", json={"name": "API Habit", "frequency": "daily", "target_count": 1})
    assert create_resp.status_code == 201
    habit_id = create_resp.json()["id"]

    # Delete habit
    del_resp = client.delete(f"/habits/{habit_id}")
    assert del_resp.status_code == 204

    # Verify habit is gone
    get_habit = client.get(f"/habits/{habit_id}")
    assert get_habit.status_code == 404

    # Deleting nonexistent habit gives 404
    del_again = client.delete(f"/habits/{habit_id}")
    assert del_again.status_code == 404


def test_delete_pomodoro_api_endpoint(client: TestClient, db_session: Session):
    # Start a pomodoro session
    start_resp = client.post("/pomodoro", json={})
    assert start_resp.status_code == 201
    session_id = start_resp.json()["id"]

    # Delete session
    del_resp = client.delete(f"/pomodoro/{session_id}")
    assert del_resp.status_code == 204

    # Check sessions list does not include it
    list_resp = client.get("/pomodoro")
    assert list_resp.status_code == 200
    session_ids = [s["id"] for s in list_resp.json()]
    assert session_id not in session_ids

    # Deleting nonexistent session gives 404
    del_again = client.delete(f"/pomodoro/{session_id}")
    assert del_again.status_code == 404
