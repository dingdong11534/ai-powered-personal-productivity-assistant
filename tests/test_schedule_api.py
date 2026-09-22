"""Tests for the /schedule HTTP API (app.interfaces.api.schedule).

Run with: pytest tests/test_schedule_api.py -v
"""


def test_create_schedule_item_returns_201(client):
    response = client.post(
        "/schedule",
        json={
            "title": "Team meeting",
            "starts_at": "2026-08-16T09:00:00",
            "ends_at": "2026-08-16T10:00:00",
        },
    )

    assert response.status_code == 201
    assert response.json()["title"] == "Team meeting"


def test_create_schedule_item_invalid_range_returns_400(client):
    response = client.post(
        "/schedule",
        json={
            "title": "Bad",
            "starts_at": "2026-08-16T10:00:00",
            "ends_at": "2026-08-16T09:00:00",
        },
    )

    assert response.status_code == 400


def test_create_schedule_item_missing_task_returns_404(client):
    response = client.post(
        "/schedule",
        json={
            "title": "x",
            "starts_at": "2026-08-16T09:00:00",
            "ends_at": "2026-08-16T10:00:00",
            "task_id": 999999,
        },
    )

    assert response.status_code == 404


def test_get_schedule_item_missing_returns_404(client):
    response = client.get("/schedule/999999")

    assert response.status_code == 404


def test_update_schedule_item(client):
    created = client.post(
        "/schedule",
        json={
            "title": "Old",
            "starts_at": "2026-08-16T09:00:00",
            "ends_at": "2026-08-16T10:00:00",
        },
    ).json()

    response = client.put(f"/schedule/{created['id']}", json={"title": "New"})

    assert response.status_code == 200
    assert response.json()["title"] == "New"


def test_delete_schedule_item(client):
    created = client.post(
        "/schedule",
        json={
            "title": "x",
            "starts_at": "2026-08-16T09:00:00",
            "ends_at": "2026-08-16T10:00:00",
        },
    ).json()

    response = client.delete(f"/schedule/{created['id']}")
    assert response.status_code == 204

    follow_up = client.get(f"/schedule/{created['id']}")
    assert follow_up.status_code == 404


def test_conflicts_endpoint_reachable_and_correct(client):
    """Confirms the /schedule/conflicts static route is actually reached
    (not swallowed by /schedule/{item_id})."""
    created = client.post(
        "/schedule",
        json={
            "title": "First",
            "starts_at": "2026-08-16T09:00:00",
            "ends_at": "2026-08-16T10:00:00",
        },
    ).json()

    response = client.get(
        "/schedule/conflicts?starts_at=2026-08-16T09:30:00&ends_at=2026-08-16T10:30:00"
    )

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    assert ids == {created["id"]}


def test_conflicts_endpoint_empty_when_no_overlap(client):
    client.post(
        "/schedule",
        json={
            "title": "First",
            "starts_at": "2026-08-16T09:00:00",
            "ends_at": "2026-08-16T10:00:00",
        },
    )

    response = client.get(
        "/schedule/conflicts?starts_at=2026-08-16T11:00:00&ends_at=2026-08-16T12:00:00"
    )

    assert response.status_code == 200
    assert response.json() == []


def test_conflicts_endpoint_parameterless_returns_all_conflicts(client):
    """Verifies that calling /schedule/conflicts with no parameters returns 200 and all overlapping items."""
    first = client.post(
        "/schedule",
        json={
            "title": "Task 1",
            "starts_at": "2026-08-16T10:00:00",
            "ends_at": "2026-08-16T11:00:00",
        },
    ).json()

    second = client.post(
        "/schedule",
        json={
            "title": "Task 2",
            "starts_at": "2026-08-16T10:30:00",
            "ends_at": "2026-08-16T11:30:00",
        },
    ).json()

    # Parameterless call
    response = client.get("/schedule/conflicts")
    assert response.status_code == 200
    conflict_ids = {item["id"] for item in response.json()}
    assert first["id"] in conflict_ids
    assert second["id"] in conflict_ids
