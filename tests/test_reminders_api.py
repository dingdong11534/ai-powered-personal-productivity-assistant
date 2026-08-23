"""Tests for the /reminders HTTP API (app.interfaces.api.reminders).

Run with: pytest tests/test_reminders_api.py -v
"""


def test_create_reminder_returns_201(client):
    response = client.post(
        "/reminders", json={"remind_at": "2026-08-16T12:00:00", "message": "Call the dentist"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["message"] == "Call the dentist"
    assert body["fired_at"] is None


def test_create_reminder_requires_message(client):
    response = client.post("/reminders", json={"remind_at": "2026-08-16T12:00:00"})

    assert response.status_code == 422


def test_create_reminder_with_missing_task_returns_404(client):
    response = client.post(
        "/reminders",
        json={"task_id": 999999, "remind_at": "2026-08-16T12:00:00", "message": "x"},
    )

    assert response.status_code == 404


def test_get_reminder_missing_returns_404(client):
    response = client.get("/reminders/999999")

    assert response.status_code == 404


def test_update_reminder(client):
    created = client.post(
        "/reminders", json={"remind_at": "2026-08-16T12:00:00", "message": "Old"}
    ).json()

    response = client.put(f"/reminders/{created['id']}", json={"message": "New"})

    assert response.status_code == 200
    assert response.json()["message"] == "New"


def test_fire_reminder(client):
    created = client.post(
        "/reminders", json={"remind_at": "2026-08-16T12:00:00", "message": "x"}
    ).json()

    response = client.post(f"/reminders/{created['id']}/fire")

    assert response.status_code == 200
    assert response.json()["fired_at"] is not None


def test_fire_reminder_twice_is_idempotent(client):
    created = client.post(
        "/reminders", json={"remind_at": "2026-08-16T12:00:00", "message": "x"}
    ).json()
    client.post(f"/reminders/{created['id']}/fire")

    response = client.post(f"/reminders/{created['id']}/fire")

    assert response.status_code == 200


def test_delete_reminder(client):
    created = client.post(
        "/reminders", json={"remind_at": "2026-08-16T12:00:00", "message": "x"}
    ).json()

    response = client.delete(f"/reminders/{created['id']}")
    assert response.status_code == 204

    follow_up = client.get(f"/reminders/{created['id']}")
    assert follow_up.status_code == 404


def test_list_reminders_due_filter(client):
    client.post(
        "/reminders", json={"remind_at": "2020-01-01T00:00:00", "message": "Way in the past"}
    )
    client.post(
        "/reminders", json={"remind_at": "2099-01-01T00:00:00", "message": "Far future"}
    )

    response = client.get("/reminders?due=true")

    messages = {r["message"] for r in response.json()}
    assert messages == {"Way in the past"}


def test_list_reminders_upcoming_filter(client):
    client.post(
        "/reminders", json={"remind_at": "2020-01-01T00:00:00", "message": "Way in the past"}
    )
    client.post(
        "/reminders", json={"remind_at": "2099-01-01T00:00:00", "message": "Far future"}
    )

    response = client.get("/reminders?upcoming=true")

    messages = {r["message"] for r in response.json()}
    assert messages == {"Far future"}
