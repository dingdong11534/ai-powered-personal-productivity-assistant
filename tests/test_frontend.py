"""Tests for Phase 3 web dashboard static file serving.

Run with: pytest tests/test_frontend.py -v
"""

from fastapi.testclient import TestClient

from app.interfaces.main import app

client = TestClient(app)


def test_root_index_page_returns_html():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Personal Productivity Assistant" in response.text
    assert 'id="section-dashboard"' in response.text


def test_static_css_file_is_served():
    response = client.get("/static/css/style.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]
    assert "--bg-primary" in response.text


def test_static_js_file_is_served():
    response = client.get("/static/js/app.js")
    assert response.status_code == 200
    assert ("application/javascript" in response.headers["content-type"] or "text/javascript" in response.headers["content-type"])
    assert "initNavigation" in response.text


def test_health_check_remains_functional():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
