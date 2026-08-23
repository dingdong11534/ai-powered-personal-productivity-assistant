"""Tests for the /notifications HTTP API (app.interfaces.api.notifications).

Run with: pytest tests/test_notifications_api.py -v
"""


def test_create_notification_returns_201(client):
    response = client.post(
        "/notifications", json={"title": "Reminder fired", "body": "Call the dentist"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Reminder fired"
    assert body["read_at"] is None


def test_create_notification_requires_title(client):
    response = client.post("/notifications", json={"body": "no title"})

    assert response.status_code == 422


def test_get_notification_missing_returns_404(client):
    response = client.get("/notifications/999999")

    assert response.status_code == 404


def test_list_notifications_unread_only(client):
    unread = client.post("/notifications", json={"title": "Unread"}).json()
    read = client.post("/notifications", json={"title": "Will be read"}).json()
    client.post(f"/notifications/{read['id']}/read")

    response = client.get("/notifications?unread_only=true")

    ids = {n["id"] for n in response.json()}
    assert ids == {unread["id"]}


def test_mark_notification_read(client):
    created = client.post("/notifications", json={"title": "x"}).json()

    response = client.post(f"/notifications/{created['id']}/read")

    assert response.status_code == 200
    assert response.json()["read_at"] is not None


def test_mark_notification_unread(client):
    created = client.post("/notifications", json={"title": "x"}).json()
    client.post(f"/notifications/{created['id']}/read")

    response = client.post(f"/notifications/{created['id']}/unread")

    assert response.status_code == 200
    assert response.json()["read_at"] is None
