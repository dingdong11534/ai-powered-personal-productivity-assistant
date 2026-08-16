"""Tests for the /projects HTTP API (app.interfaces.api.projects).

Run with: pytest tests/test_projects_api.py -v
"""


def test_create_project_returns_201(client):
    response = client.post("/projects", json={"name": "Home Renovation", "color": "teal"})

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Home Renovation"
    assert body["color"] == "teal"
    assert body["archived_at"] is None
    assert "id" in body and "created_at" in body


def test_create_project_requires_name(client):
    response = client.post("/projects", json={"description": "no name"})

    assert response.status_code == 422


def test_list_projects_returns_created_projects(client):
    client.post("/projects", json={"name": "A"})
    client.post("/projects", json={"name": "B"})

    response = client.get("/projects")

    assert response.status_code == 200
    names = {p["name"] for p in response.json()}
    assert names == {"A", "B"}


def test_get_project_by_id(client):
    created = client.post("/projects", json={"name": "Find me"}).json()

    response = client.get(f"/projects/{created['id']}")

    assert response.status_code == 200
    assert response.json()["name"] == "Find me"


def test_get_project_missing_returns_404(client):
    response = client.get("/projects/999999")

    assert response.status_code == 404


def test_update_project_changes_given_fields(client):
    created = client.post("/projects", json={"name": "Old", "color": "red"}).json()

    response = client.put(f"/projects/{created['id']}", json={"name": "New"})

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "New"
    assert body["color"] == "red"  # untouched


def test_update_project_missing_returns_404(client):
    response = client.put("/projects/999999", json={"name": "x"})

    assert response.status_code == 404


def test_archive_project_sets_archived_at(client):
    created = client.post("/projects", json={"name": "Wrapping up"}).json()

    response = client.post(f"/projects/{created['id']}/archive")

    assert response.status_code == 200
    assert response.json()["archived_at"] is not None


def test_archive_project_missing_returns_404(client):
    response = client.post("/projects/999999/archive")

    assert response.status_code == 404


def test_list_projects_can_exclude_archived(client):
    active = client.post("/projects", json={"name": "Active"}).json()
    archived = client.post("/projects", json={"name": "Archived"}).json()
    client.post(f"/projects/{archived['id']}/archive")

    response = client.get("/projects?include_archived=false")

    ids = {p["id"] for p in response.json()}
    assert ids == {active["id"]}
