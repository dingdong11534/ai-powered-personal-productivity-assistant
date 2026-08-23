"""Tests for the /pomodoro HTTP API (app.interfaces.api.pomodoro).

Run with: pytest tests/test_pomodoro_api.py -v
"""


def test_start_session_with_no_body(client):
    response = client.post("/pomodoro")

    assert response.status_code == 201
    body = response.json()
    assert body["task_id"] is None
    assert body["ended_at"] is None


def test_start_session_with_task_id(client):
    task = client.post("/tasks", json={"title": "Focus task"}).json()

    response = client.post("/pomodoro", json={"task_id": task["id"]})

    assert response.status_code == 201
    assert response.json()["task_id"] == task["id"]


def test_start_session_with_missing_task_returns_404(client):
    response = client.post("/pomodoro", json={"task_id": 999999})

    assert response.status_code == 404


def test_get_session_missing_returns_404(client):
    response = client.get("/pomodoro/999999")

    assert response.status_code == 404


def test_end_session(client):
    session = client.post("/pomodoro").json()

    response = client.post(f"/pomodoro/{session['id']}/end")

    assert response.status_code == 200
    body = response.json()
    assert body["ended_at"] is not None
    assert body["duration_seconds"] is not None
    assert body["interrupted"] is False


def test_end_session_interrupted(client):
    session = client.post("/pomodoro").json()

    response = client.post(f"/pomodoro/{session['id']}/end", json={"interrupted": True})

    assert response.status_code == 200
    assert response.json()["interrupted"] is True


def test_end_session_twice_returns_409(client):
    session = client.post("/pomodoro").json()
    client.post(f"/pomodoro/{session['id']}/end")

    response = client.post(f"/pomodoro/{session['id']}/end")

    assert response.status_code == 409


def test_list_sessions_filter_by_task(client):
    task = client.post("/tasks", json={"title": "Focus task"}).json()
    client.post("/pomodoro", json={"task_id": task["id"]})
    client.post("/pomodoro")

    response = client.get(f"/pomodoro?task_id={task['id']}")

    sessions = response.json()
    assert len(sessions) == 1
    assert sessions[0]["task_id"] == task["id"]
