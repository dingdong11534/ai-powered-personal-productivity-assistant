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


def test_mark_all_read(client):
    n1 = client.post("/notifications", json={"title": "Bulk unread 1"}).json()
    n2 = client.post("/notifications", json={"title": "Bulk unread 2"}).json()

    response = client.post("/notifications/read-all")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["marked_read"] >= 2

    # Verify unread list is now empty of these
    unread_res = client.get("/notifications?unread_only=true")
    unread_ids = {n["id"] for n in unread_res.json()}
    assert n1["id"] not in unread_ids
    assert n2["id"] not in unread_ids


def test_search_notifications(client):
    n1 = client.post("/notifications", json={"title": "Alpha Notification Task", "body": None}).json()
    n2 = client.post("/notifications", json={"title": "Beta Notice", "body": "Contains secret keyword"}).json()

    # Search title with null body
    res1 = client.get("/notifications?search=Alpha")
    assert res1.status_code == 200
    ids1 = [n["id"] for n in res1.json()]
    assert n1["id"] in ids1
    assert n2["id"] not in ids1

    # Search body
    res2 = client.get("/notifications?search=secret")
    assert res2.status_code == 200
    ids2 = [n["id"] for n in res2.json()]
    assert n2["id"] in ids2
    assert n1["id"] not in ids2

