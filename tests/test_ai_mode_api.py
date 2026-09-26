"""Tests for AI mode switching and status API endpoints."""

from fastapi.testclient import TestClient


def test_ai_mode_endpoints(client: TestClient):
    # 1. Get initial status
    res = client.get("/ai/mode")
    assert res.status_code == 200
    data = res.json()
    assert "mode" in data
    assert "online_provider" in data
    assert "offline_provider" in data

    # 2. Switch to offline mode
    res_off = client.post("/ai/mode", json={"mode": "offline"})
    assert res_off.status_code == 200
    data_off = res_off.json()
    assert data_off["mode"] == "offline"
    assert data_off["is_online"] is False
    assert data_off["active_provider"] == "ollama"

    # 3. Switch back to online mode
    res_on = client.post("/ai/mode", json={"mode": "online"})
    assert res_on.status_code == 200
    data_on = res_on.json()
    assert data_on["mode"] == "online"
    assert data_on["is_online"] is True
    assert data_on["active_provider"] in ("groq", "openai")
