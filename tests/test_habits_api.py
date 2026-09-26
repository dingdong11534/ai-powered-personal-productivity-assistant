"""Tests for the /habits HTTP API (app.interfaces.api.habits).

Run with: pytest tests/test_habits_api.py -v
"""


def test_create_habit_returns_201(client):
    response = client.post(
        "/habits", json={"name": "Drink water", "frequency": "daily", "target_count": 3}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Drink water"
    assert body["frequency"] == "daily"
    assert body["target_count"] == 3
    assert body["archived_at"] is None


def test_create_habit_requires_name(client):
    response = client.post("/habits", json={"frequency": "daily"})

    assert response.status_code == 422


def test_create_habit_rejects_invalid_frequency(client):
    response = client.post("/habits", json={"name": "Habit", "frequency": "hourly"})

    assert response.status_code == 422


def test_create_habit_rejects_target_count_out_of_range(client):
    response = client.post(
        "/habits", json={"name": "Habit", "frequency": "daily", "target_count": 0}
    )
    assert response.status_code == 422

    response = client.post(
        "/habits", json={"name": "Habit", "frequency": "daily", "target_count": 101}
    )
    assert response.status_code == 422


def test_list_habits_returns_created_habits(client):
    client.post("/habits", json={"name": "A", "frequency": "daily"})
    client.post("/habits", json={"name": "B", "frequency": "weekly"})

    response = client.get("/habits")

    names = {h["name"] for h in response.json()}
    assert names == {"A", "B"}


def test_get_habit_missing_returns_404(client):
    response = client.get("/habits/999999")

    assert response.status_code == 404


def test_update_habit_changes_given_fields(client):
    created = client.post("/habits", json={"name": "Old", "frequency": "daily"}).json()

    response = client.put(f"/habits/{created['id']}", json={"name": "New"})

    assert response.status_code == 200
    assert response.json()["name"] == "New"


def test_archive_habit_sets_archived_at(client):
    created = client.post("/habits", json={"name": "Habit", "frequency": "daily"}).json()

    response = client.post(f"/habits/{created['id']}/archive")

    assert response.status_code == 200
    assert response.json()["archived_at"] is not None


def test_complete_habit_with_no_body_records_now(client):
    created = client.post("/habits", json={"name": "Habit", "frequency": "daily"}).json()

    response = client.post(f"/habits/{created['id']}/complete")

    assert response.status_code == 201
    assert response.json()["habit_id"] == created["id"]


def test_complete_habit_twice_same_day_returns_409(client):
    created = client.post("/habits", json={"name": "Habit", "frequency": "daily"}).json()
    client.post(
        f"/habits/{created['id']}/complete", json={"completed_at": "2026-08-16T09:00:00"}
    )

    response = client.post(
        f"/habits/{created['id']}/complete", json={"completed_at": "2026-08-16T20:00:00"}
    )

    assert response.status_code == 409


def test_complete_archived_habit_returns_409(client):
    created = client.post("/habits", json={"name": "Habit", "frequency": "daily"}).json()
    client.post(f"/habits/{created['id']}/archive")

    response = client.post(f"/habits/{created['id']}/complete")

    assert response.status_code == 409


def test_complete_missing_habit_returns_404(client):
    response = client.post("/habits/999999/complete")

    assert response.status_code == 404


def test_habit_history_returns_completions(client):
    created = client.post("/habits", json={"name": "Habit", "frequency": "daily"}).json()
    client.post(
        f"/habits/{created['id']}/complete", json={"completed_at": "2026-08-15T09:00:00"}
    )
    client.post(
        f"/habits/{created['id']}/complete", json={"completed_at": "2026-08-16T09:00:00"}
    )

    response = client.get(f"/habits/{created['id']}/history")

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_habit_statistics_returns_computed_values(client):
    created = client.post("/habits", json={"name": "Habit", "frequency": "daily"}).json()
    client.post(f"/habits/{created['id']}/complete")

    response = client.get(f"/habits/{created['id']}/statistics")

    assert response.status_code == 200
    body = response.json()
    assert body["total_completions"] == 1
    assert body["current_streak"] == 1


def test_habit_statistics_missing_habit_returns_404(client):
    response = client.get("/habits/999999/statistics")

    assert response.status_code == 404


def test_unarchive_habit_clears_archived_at(client):
    created = client.post("/habits", json={"name": "Running", "frequency": "daily"}).json()
    client.post(f"/habits/{created['id']}/archive")

    # Unarchive
    response = client.post(f"/habits/{created['id']}/unarchive")
    assert response.status_code == 200
    assert response.json()["archived_at"] is None


def test_unarchive_missing_habit_returns_404(client):
    response = client.post("/habits/999999/unarchive")
    assert response.status_code == 404
