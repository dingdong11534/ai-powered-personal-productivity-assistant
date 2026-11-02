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


def test_pomodoro_floating_widget_and_naming_elements(client):
    html_resp = client.get("/")
    assert html_resp.status_code == 200
    assert 'id="floating-pomo-widget"' in html_resp.text
    assert 'id="pomo-session-name"' in html_resp.text

    js_resp = client.get("/static/js/app.js")
    assert js_resp.status_code == 200
    assert "checkActivePomodoroSession" in js_resp.text
    assert "floating-pomo-widget" in js_resp.text
    assert "navigateTo" in js_resp.text


def test_tool_action_cards_and_links_present(client):
    js_resp = client.get("/static/js/app.js")
    assert js_resp.status_code == 200
    assert "renderToolActionCard" in js_resp.text
    assert "create_reminder" in js_resp.text
    assert "create_schedule_item" in js_resp.text
    assert "create_habit" in js_resp.text
    assert "complete_habit" in js_resp.text
    assert "create_project" in js_resp.text
    assert "start_pomodoro" in js_resp.text
    assert "remember_information" in js_resp.text
    assert "tool-action-card" in js_resp.text
    assert "data-target-tab" in js_resp.text
    assert "data-target-query" in js_resp.text


def test_pomodoro_and_notifications_no_overlap(client):
    css_resp = client.get("/static/css/style.css")
    assert css_resp.status_code == 200
    css_text = css_resp.text

    # Verify toast-container is positioned at the top area to avoid overlapping bottom-right pomodoro widget
    assert ".toast-container" in css_text
    assert "top: calc(var(--topbar-height) + 1rem)" in css_text or "top:" in css_text
    assert ".floating-pomo-widget" in css_text
    assert "bottom: 24px" in css_text
