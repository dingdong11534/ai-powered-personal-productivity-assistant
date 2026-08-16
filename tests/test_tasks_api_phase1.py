"""Tests for the Phase 1 additions to the /tasks HTTP API: the
task<->project relationship, tags, dependencies, and search/filtering.

Run with: pytest tests/test_tasks_api_phase1.py -v

Pre-existing core CRUD tests from Phase 0.2 stay in
tests/test_tasks_api.py — this file only covers what's new.
"""


# --- Task <-> Project relationship ---


def test_create_task_with_project_id(client):
    project = client.post("/projects", json={"name": "Home Renovation"}).json()

    response = client.post(
        "/tasks", json={"title": "Buy paint", "project_id": project["id"]}
    )

    assert response.status_code == 201
    assert response.json()["project_id"] == project["id"]


def test_create_task_with_missing_project_id_returns_404(client):
    response = client.post("/tasks", json={"title": "Buy paint", "project_id": 999999})

    assert response.status_code == 404


def test_create_task_with_archived_project_id_returns_409(client):
    project = client.post("/projects", json={"name": "Old project"}).json()
    client.post(f"/projects/{project['id']}/archive")

    response = client.post(
        "/tasks", json={"title": "Buy paint", "project_id": project["id"]}
    )

    assert response.status_code == 409


def test_task_remains_accessible_after_its_project_is_archived(client):
    project = client.post("/projects", json={"name": "Wrapping up"}).json()
    task = client.post(
        "/tasks", json={"title": "Last task", "project_id": project["id"]}
    ).json()

    client.post(f"/projects/{project['id']}/archive")
    response = client.get(f"/tasks/{task['id']}")

    assert response.status_code == 200
    assert response.json()["project_id"] == project["id"]


def test_filter_tasks_by_project_id(client):
    project = client.post("/projects", json={"name": "P1"}).json()
    client.post("/tasks", json={"title": "In project", "project_id": project["id"]})
    client.post("/tasks", json={"title": "No project"})

    response = client.get(f"/tasks?project_id={project['id']}")

    titles = {t["title"] for t in response.json()}
    assert titles == {"In project"}


# --- Tags ---


def test_create_and_list_tags(client):
    client.post("/tags", json={"name": "urgent"})
    client.post("/tags", json={"name": "home"})

    response = client.get("/tags")

    names = {t["name"] for t in response.json()}
    assert names == {"urgent", "home"}


def test_create_duplicate_tag_returns_409(client):
    client.post("/tags", json={"name": "urgent"})

    response = client.post("/tags", json={"name": "urgent"})

    assert response.status_code == 409


def test_attach_tag_to_task(client):
    task = client.post("/tasks", json={"title": "Pay bills"}).json()
    tag = client.post("/tags", json={"name": "finance"}).json()

    response = client.post(f"/tasks/{task['id']}/tags/{tag['id']}")

    assert response.status_code == 200
    assert [t["name"] for t in response.json()["tags"]] == ["finance"]


def test_attach_tag_missing_task_returns_404(client):
    tag = client.post("/tags", json={"name": "finance"}).json()

    response = client.post(f"/tasks/999999/tags/{tag['id']}")

    assert response.status_code == 404


def test_attach_tag_missing_tag_returns_404(client):
    task = client.post("/tasks", json={"title": "Pay bills"}).json()

    response = client.post(f"/tasks/{task['id']}/tags/999999")

    assert response.status_code == 404


def test_detach_tag_from_task(client):
    task = client.post("/tasks", json={"title": "Pay bills"}).json()
    tag = client.post("/tags", json={"name": "finance"}).json()
    client.post(f"/tasks/{task['id']}/tags/{tag['id']}")

    response = client.delete(f"/tasks/{task['id']}/tags/{tag['id']}")

    assert response.status_code == 200
    assert response.json()["tags"] == []


def test_filter_tasks_by_tag(client):
    tag = client.post("/tags", json={"name": "finance"}).json()
    tagged = client.post("/tasks", json={"title": "Tagged"}).json()
    client.post("/tasks", json={"title": "Untagged"})
    client.post(f"/tasks/{tagged['id']}/tags/{tag['id']}")

    response = client.get(f"/tasks?tag_id={tag['id']}")

    titles = {t["title"] for t in response.json()}
    assert titles == {"Tagged"}


# --- Dependencies ---


def test_add_dependency_between_tasks(client):
    a = client.post("/tasks", json={"title": "A"}).json()
    b = client.post("/tasks", json={"title": "B"}).json()

    response = client.post(
        f"/tasks/{b['id']}/dependencies", json={"depends_on_task_id": a["id"]}
    )

    assert response.status_code == 201


def test_add_self_dependency_returns_400(client):
    a = client.post("/tasks", json={"title": "A"}).json()

    response = client.post(
        f"/tasks/{a['id']}/dependencies", json={"depends_on_task_id": a["id"]}
    )

    assert response.status_code == 400


def test_add_dependency_cycle_returns_409(client):
    a = client.post("/tasks", json={"title": "A"}).json()
    b = client.post("/tasks", json={"title": "B"}).json()
    client.post(f"/tasks/{b['id']}/dependencies", json={"depends_on_task_id": a["id"]})

    response = client.post(
        f"/tasks/{a['id']}/dependencies", json={"depends_on_task_id": b["id"]}
    )

    assert response.status_code == 409


def test_add_duplicate_dependency_returns_409(client):
    a = client.post("/tasks", json={"title": "A"}).json()
    b = client.post("/tasks", json={"title": "B"}).json()
    client.post(f"/tasks/{b['id']}/dependencies", json={"depends_on_task_id": a["id"]})

    response = client.post(
        f"/tasks/{b['id']}/dependencies", json={"depends_on_task_id": a["id"]}
    )

    assert response.status_code == 409


def test_list_dependencies_for_task(client):
    a = client.post("/tasks", json={"title": "A"}).json()
    b = client.post("/tasks", json={"title": "B"}).json()
    client.post(f"/tasks/{b['id']}/dependencies", json={"depends_on_task_id": a["id"]})

    response = client.get(f"/tasks/{b['id']}/dependencies")

    assert response.json() == [a["id"]]


def test_remove_dependency(client):
    a = client.post("/tasks", json={"title": "A"}).json()
    b = client.post("/tasks", json={"title": "B"}).json()
    client.post(f"/tasks/{b['id']}/dependencies", json={"depends_on_task_id": a["id"]})

    response = client.delete(f"/tasks/{b['id']}/dependencies/{a['id']}")

    assert response.status_code == 204
    assert client.get(f"/tasks/{b['id']}/dependencies").json() == []


def test_completing_task_with_unresolved_dependency_returns_409(client):
    a = client.post("/tasks", json={"title": "A"}).json()
    b = client.post("/tasks", json={"title": "B"}).json()
    client.post(f"/tasks/{b['id']}/dependencies", json={"depends_on_task_id": a["id"]})

    response = client.put(f"/tasks/{b['id']}", json={"status": "done"})

    assert response.status_code == 409


def test_completing_task_after_dependency_resolved_succeeds(client):
    a = client.post("/tasks", json={"title": "A"}).json()
    b = client.post("/tasks", json={"title": "B"}).json()
    client.post(f"/tasks/{b['id']}/dependencies", json={"depends_on_task_id": a["id"]})

    client.put(f"/tasks/{a['id']}", json={"status": "done"})
    response = client.put(f"/tasks/{b['id']}", json={"status": "done"})

    assert response.status_code == 200
    assert response.json()["status"] == "done"


# --- Search ---


def test_search_tasks_by_title(client):
    client.post("/tasks", json={"title": "Buy groceries"})
    client.post("/tasks", json={"title": "Clean house"})

    response = client.get("/tasks?search=groceries")

    titles = {t["title"] for t in response.json()}
    assert titles == {"Buy groceries"}


def test_filter_tasks_by_completed(client):
    client.post("/tasks", json={"title": "Still open"})
    done = client.post("/tasks", json={"title": "Finished"}).json()
    client.put(f"/tasks/{done['id']}", json={"status": "done"})

    response = client.get("/tasks?completed=true")

    titles = {t["title"] for t in response.json()}
    assert titles == {"Finished"}
