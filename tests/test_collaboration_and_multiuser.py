"""Tests for multi-user project collaboration, task assignment requests,
unique user IDs, online status tracking, profile privacy, and 100k token limits.
"""

from __future__ import annotations

import uuid
import pytest
from starlette.testclient import TestClient

from app.interfaces.main import app
from app.storage.database import SessionLocal, create_all_tables
from app.storage.models import User


@pytest.fixture
def collab_client():
    create_all_tables()
    with TestClient(app) as test_client:
        yield test_client


def get_user_auth(client, username: str, password: str = "pass1234") -> dict:
    reg = client.post("/api/auth/register", json={"username": username, "password": password})
    if reg.status_code == 201:
        return reg.json()
    login = client.post("/api/auth/login", json={"username": username, "password": password})
    return login.json()


def test_unique_user_id_and_private_profile(collab_client):
    """Every user must have a unique ID, and public profile only exposes ID, username, online status."""
    u1_name = f"alice_{uuid.uuid4().hex[:6]}"
    u2_name = f"bob_{uuid.uuid4().hex[:6]}"
    r1 = get_user_auth(collab_client, u1_name)
    r2 = get_user_auth(collab_client, u2_name)

    u1_id = r1["user"]["id"]
    u2_id = r2["user"]["id"]
    assert u1_id != u2_id, "Each user must have a unique ID"

    # User 1 looks up User 2's profile
    u1_token = r1["access_token"]
    u1_headers = {"Authorization": f"Bearer {u1_token}"}

    prof_res = collab_client.get(f"/api/users/{u2_id}/profile", headers=u1_headers)
    assert prof_res.status_code == 200
    prof = prof_res.json()
    assert prof["id"] == u2_id
    assert prof["username"] == u2_name
    assert "is_online" in prof
    # Crucial privacy requirement: preferences, custom keys, habits are NOT in public profile!
    assert "custom_api_keys" not in prof
    assert "preferences" not in prof
    assert "password_hash" not in prof


def test_online_status_and_heartbeat(collab_client):
    """Users can update heartbeat, and online status is tracked and visible to admin & collaborators."""
    u_name = f"charlie_{uuid.uuid4().hex[:6]}"
    r = get_user_auth(collab_client, u_name)
    u_token = r["access_token"]
    u_headers = {"Authorization": f"Bearer {u_token}"}
    u_id = r["user"]["id"]

    # Call heartbeat
    hb_res = collab_client.post("/api/auth/heartbeat", headers=u_headers)
    assert hb_res.status_code == 200
    assert hb_res.json()["is_online"] is True

    # Admin checks user list and sees charlie is online
    kunal_login = collab_client.post("/api/auth/login", json={"username": "kunal", "password": "kunalreward34"}).json()
    admin_headers = {"Authorization": f"Bearer {kunal_login['access_token']}"}

    users_res = collab_client.get("/api/users", headers=admin_headers)
    assert users_res.status_code == 200
    users = users_res.json()
    charlie_entry = next((u for u in users if u["id"] == u_id), None)
    assert charlie_entry is not None
    assert charlie_entry["is_online"] is True


def test_project_collaboration_and_admin_delete_user(collab_client):
    """Users can be invited by ID, see invites, accept/reject, and admin can delete user from project."""
    u_alice = f"alice_collab_{uuid.uuid4().hex[:6]}"
    u_bob = f"bob_collab_{uuid.uuid4().hex[:6]}"
    r_alice = get_user_auth(collab_client, u_alice)
    alice_headers = {"Authorization": f"Bearer {r_alice['access_token']}"}

    r_bob = get_user_auth(collab_client, u_bob)
    bob_headers = {"Authorization": f"Bearer {r_bob['access_token']}"}
    bob_id = r_bob["user"]["id"]

    # Alice creates a project
    proj = collab_client.post("/projects", json={"name": "Mission Alpha"}, headers=alice_headers).json()
    proj_id = proj["id"]

    # Alice invites Bob using Bob's unique ID
    invite_res = collab_client.post(f"/projects/{proj_id}/invite", json={"user_id": bob_id}, headers=alice_headers)
    assert invite_res.status_code == 200, invite_res.text

    # Bob checks pending project invites
    bob_invites = collab_client.get("/projects/invites/pending", headers=bob_headers).json()
    assert len(bob_invites) >= 1
    target_invite = next((inv for inv in bob_invites if inv["project_id"] == proj_id), None)
    assert target_invite is not None
    assert target_invite["project_name"] == "Mission Alpha"

    # Bob accepts the invitation
    accept_res = collab_client.post(f"/projects/invites/{target_invite['id']}/accept", headers=bob_headers)
    assert accept_res.status_code == 200

    # Bob can now view project members and project details
    members = collab_client.get(f"/projects/{proj_id}/members", headers=bob_headers).json()
    member_ids = [m["user_id"] for m in members]
    assert bob_id in member_ids

    # Admin removes Bob from the project
    kunal_login = collab_client.post("/api/auth/login", json={"username": "kunal", "password": "kunalreward34"}).json()
    admin_headers = {"Authorization": f"Bearer {kunal_login['access_token']}"}

    del_res = collab_client.delete(f"/projects/{proj_id}/members/{bob_id}", headers=admin_headers)
    assert del_res.status_code == 200

    # Verify Bob is no longer a member
    members_after = collab_client.get(f"/projects/{proj_id}/members", headers=alice_headers).json()
    assert bob_id not in [m["user_id"] for m in members_after]


def test_task_assignment_requests_accept_and_reject(collab_client):
    """Tasks can be requested to users with notes. If rejected, they are NOT assigned to that task."""
    u_alice = f"alice_task_{uuid.uuid4().hex[:6]}"
    u_bob = f"bob_worker_{uuid.uuid4().hex[:6]}"
    r_alice = get_user_auth(collab_client, u_alice)
    alice_headers = {"Authorization": f"Bearer {r_alice['access_token']}"}

    r_bob = get_user_auth(collab_client, u_bob)
    bob_headers = {"Authorization": f"Bearer {r_bob['access_token']}"}
    bob_id = r_bob["user"]["id"]

    # Alice creates Task 1
    task1 = collab_client.post("/tasks", json={"title": "Design Database Schema", "priority": 1}, headers=alice_headers).json()
    task1_id = task1["id"]

    # Alice requests Bob to take Task 1 with notes
    req_res = collab_client.post(
        f"/tasks/{task1_id}/request-assign",
        json={"to_user_id": bob_id, "notes": "Please prioritize user isolation rules"},
        headers=alice_headers,
    )
    assert req_res.status_code == 200

    # Bob checks pending task requests
    bob_requests = collab_client.get("/tasks/requests/pending", headers=bob_headers).json()
    assert len(bob_requests) >= 1
    req_item = next((r for r in bob_requests if r["task_id"] == task1_id), None)
    assert req_item is not None
    assert req_item["notes"] == "Please prioritize user isolation rules"

    # Bob rejects Task 1 request
    reject_res = collab_client.post(f"/tasks/requests/{req_item['id']}/reject", headers=bob_headers)
    assert reject_res.status_code == 200

    # Verify Task 1 is NOT assigned to Bob
    task1_after = collab_client.get(f"/tasks/{task1_id}", headers=alice_headers).json()
    assert task1_after["assigned_user_id"] != bob_id

    # Alice creates Task 2 and requests Bob again
    task2 = collab_client.post("/tasks", json={"title": "Write API documentation", "priority": 3}, headers=alice_headers).json()
    task2_id = task2["id"]

    collab_client.post(
        f"/tasks/{task2_id}/request-assign",
        json={"to_user_id": bob_id, "notes": "Include swagger examples"},
        headers=alice_headers,
    )
    bob_requests_2 = collab_client.get("/tasks/requests/pending", headers=bob_headers).json()
    req_item_2 = next((r for r in bob_requests_2 if r["task_id"] == task2_id), None)
    assert req_item_2 is not None

    # Bob accepts Task 2 request
    accept_res = collab_client.post(f"/tasks/requests/{req_item_2['id']}/accept", headers=bob_headers)
    assert accept_res.status_code == 200

    # Verify Task 2 IS now assigned to Bob
    task2_after = collab_client.get(f"/tasks/{task2_id}", headers=alice_headers).json()
    assert task2_after["assigned_user_id"] == bob_id


def test_token_usage_limit_100k(collab_client):
    """User token usage is tracked up to 100,000 tokens and rejects further requests when reached."""
    u_name = f"token_tester_{uuid.uuid4().hex[:6]}"
    r_user = get_user_auth(collab_client, u_name)
    u_headers = {"Authorization": f"Bearer {r_user['access_token']}"}
    u_id = r_user["user"]["id"]

    # Create a conversation
    conv = collab_client.post("/conversations", json={"title": "Token Test"}, headers=u_headers).json()
    conv_id = conv["id"]

    # Manually simulate user hitting 100k tokens in DB
    with SessionLocal() as session:
        user_db = session.get(User, u_id)
        user_db.token_usage = 100_000
        session.commit()

    # Attempt to send message
    msg_res = collab_client.post(f"/conversations/{conv_id}/messages", json={"content": "Hello AI"}, headers=u_headers)
    assert msg_res.status_code == 200 or msg_res.status_code == 201
    resp = msg_res.json()
    assert "Token limit reached" in resp["content"]
