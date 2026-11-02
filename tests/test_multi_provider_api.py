"""Tests for multi-provider AI model selection and configuration APIs."""

from fastapi.testclient import TestClient


def test_ai_status_providers_catalog(client: TestClient):
    res = client.get("/ai/status")
    assert res.status_code == 200
    data = res.json()
    assert "providers" in data
    providers = data["providers"]
    assert "openai" in providers
    assert "gemini" in providers
    assert "groq" in providers
    assert "grok" in providers
    assert "offline" in providers

    openai_info = providers["openai"]
    assert "ChatGPT" in openai_info["label"]
    assert "gpt-4o-mini" in openai_info["models"]
    assert openai_info["base_url"] == "https://api.openai.com/v1"


def test_ai_config_switch_to_openai(client: TestClient):
    req_body = {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "api_key": "sk-test-openai-key-12345678",
        "base_url": "https://api.openai.com/v1",
        "persist": False,
    }
    res = client.post("/ai/config", json=req_body)
    assert res.status_code == 200
    data = res.json()
    assert data["active_provider"] == "openai"
    assert data["active_model"] == "gpt-4o-mini"
    assert data["is_online"] is True
    assert data["mode"] == "online"
    assert data["providers"]["openai"]["has_key"] is True


def test_ai_config_switch_to_offline(client: TestClient):
    req_body = {
        "provider": "offline",
        "model": "qwen2.5:1.5b",
        "persist": False,
    }
    res = client.post("/ai/config", json=req_body)
    assert res.status_code == 200
    data = res.json()
    assert data["active_provider"] == "ollama"
    assert data["is_online"] is False
    assert data["mode"] == "offline"


def test_ai_offline_mode_restricted_to_admin(client: TestClient):
    """Regular non-admin users should get 403 when trying to switch to offline mode."""
    # Register and login a regular user
    client.post("/api/auth/register", json={"username": "regular_joe", "password": "123"})
    login = client.post("/api/auth/login", json={"username": "regular_joe", "password": "123"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Regular user attempt via /ai/config
    res = client.post(
        "/ai/config",
        json={"provider": "offline", "model": "qwen2.5:1.5b", "persist": False},
        headers=headers,
    )
    assert res.status_code == 403
    assert "Only administrators can switch to or configure the offline model" in res.json()["detail"]

    # Regular user attempt via /ai/mode
    res_mode = client.post(
        "/ai/mode",
        json={"mode": "offline"},
        headers=headers,
    )
    assert res_mode.status_code == 403
    assert "Only administrators can switch to or configure the offline model" in res_mode.json()["detail"]


def test_ai_connection_test_endpoint(client: TestClient):
    res = client.post(
        "/ai/test",
        json={"provider": "mock", "model": "mock", "api_key": "mock-key"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "latency_ms" in data

