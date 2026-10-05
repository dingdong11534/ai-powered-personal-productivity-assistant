"""Tests for Phase 3 web dashboard static file serving.

Run with: pytest tests/test_frontend.py -v
"""

def test_root_index_page_returns_html(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Personal Productivity Assistant" in response.text
    assert 'id="section-dashboard"' in response.text


def test_static_css_file_is_served(client):
    response = client.get("/static/css/style.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]
    assert "--bg-primary" in response.text


def test_static_js_file_is_served(client):
    response = client.get("/static/js/app.js")
    assert response.status_code == 200
    assert ("application/javascript" in response.headers["content-type"] or "text/javascript" in response.headers["content-type"])
    assert "initNavigation" in response.text


def test_health_check_remains_functional(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_voice_input_elements_present(client):
    html_resp = client.get("/")
    assert html_resp.status_code == 200
    assert 'id="chat-mic-btn"' in html_resp.text
    assert 'toggleVoiceInput()' in html_resp.text

    js_resp = client.get("/static/js/app.js")
    assert js_resp.status_code == 200
    assert "toggleVoiceInput" in js_resp.text
    assert "SpeechRecognition" in js_resp.text
