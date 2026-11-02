"""Tests for user authentication, admin account defaults, and multi-user data isolation."""

import pytest
from starlette.testclient import TestClient

from app.interfaces.main import app
from app.storage.database import Base, create_all_tables, engine, get_db
from app.users.security import create_access_token


@pytest.fixture
def auth_client():
    create_all_tables()
    with TestClient(app) as c:
        yield c


def test_kunal_admin_login_success(auth_client):
    """Kunal should log in with password kunalreward34 and get admin role."""
    resp = auth_client.post(
        "/api/auth/login",
        json={"username": "kunal", "password": "kunalreward34"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["user"]["username"] == "kunal"
    assert data["user"]["role"] == "admin"
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_invalid_password(auth_client):
    """Wrong password should return 401 Unauthorized."""
    resp = auth_client.post(
        "/api/auth/login",
        json={"username": "kunal", "password": "wrongpassword"},
    )
    assert resp.status_code == 401
    assert "Invalid username or password" in resp.json()["detail"]


def test_register_new_user(auth_client):
    """Should be able to register a new user."""
    resp = auth_client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "password123"},
    )
    # Could be 201 or 409 if already exists
    if resp.status_code == 201:
        data = resp.json()
        assert data["user"]["username"] == "alice"
        assert data["user"]["role"] == "user"
        assert "access_token" in data


def test_user_data_isolation(auth_client):
    """Ensure tasks and habits created by kunal and alice are isolated."""
    # 1. Login kunal
    kunal_login = auth_client.post(
        "/api/auth/login",
        json={"username": "kunal", "password": "kunalreward34"},
    ).json()
    kunal_token = kunal_login["access_token"]
    kunal_headers = {"Authorization": f"Bearer {kunal_token}"}

    # 2. Register/login bob
    alice_reg = auth_client.post(
        "/api/auth/register",
        json={"username": "bob_tester", "password": "bobpassword123"},
    )
    if alice_reg.status_code == 201:
        bob_token = alice_reg.json()["access_token"]
    else:
        bob_login = auth_client.post(
            "/api/auth/login",
            json={"username": "bob_tester", "password": "bobpassword123"},
        ).json()
        bob_token = bob_login["access_token"]
    bob_headers = {"Authorization": f"Bearer {bob_token}"}

    # Kunal creates a task
    t_resp = auth_client.post(
        "/tasks",
        json={"title": "Kunal Secret Admin Task", "priority": 1},
        headers=kunal_headers,
    )
    assert t_resp.status_code == 201
    kunal_task_id = t_resp.json()["id"]

    # Bob creates a task
    b_resp = auth_client.post(
        "/tasks",
        json={"title": "Bob Personal Task", "priority": 2},
        headers=bob_headers,
    )
    assert b_resp.status_code == 201
    bob_task_id = b_resp.json()["id"]

    # Verify Kunal's tasks list contains kunal_task_id, but NOT bob_task_id
    k_tasks = auth_client.get("/tasks", headers=kunal_headers).json()
    k_ids = [t["id"] for t in k_tasks]
    assert kunal_task_id in k_ids
    assert bob_task_id not in k_ids

    # Verify Bob's tasks list contains bob_task_id, but NOT kunal_task_id
    b_tasks = auth_client.get("/tasks", headers=bob_headers).json()
    b_ids = [t["id"] for t in b_tasks]
    assert bob_task_id in b_ids
    assert kunal_task_id not in b_ids

    # Verify habit isolation
    h_kunal = auth_client.post(
        "/habits",
        json={"name": "Kunal Admin Meditation", "frequency": "daily", "target_count": 1},
        headers=kunal_headers,
    ).json()
    h_bob = auth_client.post(
        "/habits",
        json={"name": "Bob Running Habit", "frequency": "daily", "target_count": 1},
        headers=bob_headers,
    ).json()

    k_habits = auth_client.get("/habits", headers=kunal_headers).json()
    k_h_ids = [h["id"] for h in k_habits]
    assert h_kunal["id"] in k_h_ids
    assert h_bob["id"] not in k_h_ids

    b_habits = auth_client.get("/habits", headers=bob_headers).json()
    b_h_ids = [h["id"] for h in b_habits]
    assert h_bob["id"] in b_h_ids
    assert h_kunal["id"] not in b_h_ids


def test_cross_user_access_forbidden_and_admin_override(auth_client):
    """Regular users cannot access or modify other users' items (403 Forbidden), but admin can."""
    # 1. Admin login (kunal)
    kunal_login = auth_client.post(
        "/api/auth/login",
        json={"username": "kunal", "password": "kunalreward34"},
    ).json()
    k_headers = {"Authorization": f"Bearer {kunal_login['access_token']}"}

    # 2. Regular user 1 (user_alice)
    reg_u1 = auth_client.post(
        "/api/auth/register",
        json={"username": "user_alice", "password": "password123"},
    )
    t1 = reg_u1.json()["access_token"] if reg_u1.status_code == 201 else auth_client.post("/api/auth/login", json={"username": "user_alice", "password": "password123"}).json()["access_token"]
    u1_headers = {"Authorization": f"Bearer {t1}"}

    # 3. Regular user 2 (user_bob)
    reg_u2 = auth_client.post(
        "/api/auth/register",
        json={"username": "user_bob", "password": "password123"},
    )
    t2 = reg_u2.json()["access_token"] if reg_u2.status_code == 201 else auth_client.post("/api/auth/login", json={"username": "user_bob", "password": "password123"}).json()["access_token"]
    u2_headers = {"Authorization": f"Bearer {t2}"}

    # User 1 creates task, project, habit
    t_res = auth_client.post("/tasks", json={"title": "Alice Task", "priority": 2}, headers=u1_headers).json()
    alice_task_id = t_res["id"]

    p_res = auth_client.post("/projects", json={"name": "Alice Secret Project"}, headers=u1_headers).json()
    alice_proj_id = p_res["id"]

    h_res = auth_client.post("/habits", json={"name": "Alice Meditation", "frequency": "daily", "target_count": 1}, headers=u1_headers).json()
    alice_habit_id = h_res["id"]


    # User 2 attempts to GET, UPDATE, DELETE Alice's task -> 403 Forbidden
    res_get = auth_client.get(f"/tasks/{alice_task_id}", headers=u2_headers)
    assert res_get.status_code == 403, res_get.text
    assert "Access denied" in res_get.json()["detail"]

    res_put = auth_client.put(f"/tasks/{alice_task_id}", json={"title": "Hacked Title"}, headers=u2_headers)
    assert res_put.status_code == 403

    res_del = auth_client.delete(f"/tasks/{alice_task_id}", headers=u2_headers)
    assert res_del.status_code == 403

    # User 2 attempts to GET, UPDATE, DELETE Alice's project -> 403 Forbidden
    res_p_get = auth_client.get(f"/projects/{alice_proj_id}", headers=u2_headers)
    assert res_p_get.status_code == 403

    res_p_del = auth_client.delete(f"/projects/{alice_proj_id}", headers=u2_headers)
    assert res_p_del.status_code == 403

    # User 2 attempts to complete Alice's habit -> 403 Forbidden
    res_h_comp = auth_client.post(f"/habits/{alice_habit_id}/complete", headers=u2_headers)
    assert res_h_comp.status_code == 403

    # ADMIN (Kunal) CAN access, view, and modify Alice's data
    k_get = auth_client.get(f"/tasks/{alice_task_id}", headers=k_headers)
    assert k_get.status_code == 200
    assert k_get.json()["title"] == "Alice Task"

    k_p_get = auth_client.get(f"/projects/{alice_proj_id}", headers=k_headers)
    assert k_p_get.status_code == 200

    k_h_get = auth_client.get(f"/habits/{alice_habit_id}", headers=k_headers)
    assert k_h_get.status_code == 200


def test_user_custom_api_keys_and_default_keys(auth_client):
    """Users inherit system default keys by default, and can set/clear their own custom keys."""
    # 1. Register user_carol
    reg_c = auth_client.post("/api/auth/register", json={"username": "user_carol", "password": "password123"})
    token_c = reg_c.json()["access_token"] if reg_c.status_code == 201 else auth_client.post("/api/auth/login", json={"username": "user_carol", "password": "password123"}).json()["access_token"]
    c_headers = {"Authorization": f"Bearer {token_c}"}

    # Check status: default keys active, has_custom_key is False
    status_c = auth_client.get("/ai/status", headers=c_headers).json()
    openai_info = status_c["providers"]["openai"]
    assert openai_info["has_custom_key"] is False

    # Carol sets custom API key for OpenAI
    set_res = auth_client.post(
        "/ai/user-keys",
        json={"provider": "openai", "api_key": "sk-carol-custom-key-12345"},
        headers=c_headers,
    )
    assert set_res.status_code == 200
    assert set_res.json()["has_custom_key"] is True

    # Check that Carol's status now shows custom key active
    keys_c = auth_client.get("/ai/user-keys", headers=c_headers).json()
    assert "openai" in keys_c["configured_providers"]
    assert keys_c["status"]["providers"]["openai"]["has_custom_key"] is True

    # Register user_dave -> Dave still has default keys, NOT Carol's custom key
    reg_d = auth_client.post("/api/auth/register", json={"username": "user_dave", "password": "password123"})
    token_d = reg_d.json()["access_token"] if reg_d.status_code == 201 else auth_client.post("/api/auth/login", json={"username": "user_dave", "password": "password123"}).json()["access_token"]
    d_headers = {"Authorization": f"Bearer {token_d}"}

    keys_d = auth_client.get("/ai/user-keys", headers=d_headers).json()
    assert "openai" not in keys_d["configured_providers"]
    assert keys_d["status"]["providers"]["openai"]["has_custom_key"] is False

    # Carol clears her custom key -> reverts to default system key
    clear_res = auth_client.post(
        "/ai/user-keys",
        json={"provider": "openai", "api_key": ""},
        headers=c_headers,
    )
    assert clear_res.status_code == 200
    assert clear_res.json()["has_custom_key"] is False

