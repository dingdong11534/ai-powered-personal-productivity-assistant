"""Tests for the /tasks HTTP API (app.interfaces.api.tasks).

Run with: pytest tests/test_tasks_api.py -v

Uses the `client` fixture (tests/conftest.py) — a real FastAPI TestClient
against the real app, with only the database swapped for an isolated
in-memory one. These are integration tests: they exercise routing,
Pydantic validation, TaskService, TaskRepository, and the ORM together,
the same path a real HTTP request takes.
"""


def test_create_task_returns_201_and_the_created_task(client):
    response = client.post("/tasks", json={"title": "Buy milk"})

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Buy milk"
    assert body["status"] == "todo"
    assert body["priority"] == 2
    assert "id" in body
    assert "created_at" in body
    assert "updated_at" in body


def test_create_task_requires_title(client):
    response = client.post("/tasks", json={"description": "no title"})

    assert response.status_code == 422


def test_create_task_rejects_priority_out_of_range(client):
    response = client.post("/tasks", json={"title": "x", "priority": 9})

    assert response.status_code == 422


def test_list_tasks_returns_created_tasks(client):
    client.post("/tasks", json={"title": "A"})
    client.post("/tasks", json={"title": "B"})

    response = client.get("/tasks")

    assert response.status_code == 200
    titles = {t["title"] for t in response.json()}
    assert titles == {"A", "B"}


def test_get_task_by_id(client):
    created = client.post("/tasks", json={"title": "Find me"}).json()

    response = client.get(f"/tasks/{created['id']}")

    assert response.status_code == 200
    assert response.json()["title"] == "Find me"


def test_get_task_missing_returns_404(client):
    response = client.get("/tasks/999999")

    assert response.status_code == 404
    assert "detail" in response.json()


def test_update_task_changes_given_fields(client):
    created = client.post("/tasks", json={"title": "Old"}).json()

    response = client.put(f"/tasks/{created['id']}", json={"title": "New", "status": "done"})

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "New"
    assert body["status"] == "done"


def test_update_task_missing_returns_404(client):
    response = client.put("/tasks/999999", json={"title": "x"})

    assert response.status_code == 404


def test_delete_task_then_get_returns_404(client):
    created = client.post("/tasks", json={"title": "Bye"}).json()

    delete_response = client.delete(f"/tasks/{created['id']}")
    assert delete_response.status_code == 204

    follow_up = client.get(f"/tasks/{created['id']}")
    assert follow_up.status_code == 404


def test_delete_task_missing_returns_404(client):
    response = client.delete("/tasks/999999")

    assert response.status_code == 404
