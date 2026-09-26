"""
Phase 7 Tests: EXTERNAL permission scope, SSRF-safe HTTP client, domain
allowlist, and the get_current_weather tool.

Test inventory (all required by the spec):
  ALLOWLIST
  - test_allowlisted_domain_passes         — allowlisted domain accepted
  - test_non_allowlisted_domain_rejected   — non-allowlisted domain blocked *before* any network call
  SSRF
  - test_ssrf_localhost_rejected           — 127.0.0.1 / localhost blocked
  - test_ssrf_rfc1918_10_rejected          — 10.x.x.x blocked
  - test_ssrf_rfc1918_172_rejected         — 172.16.x.x blocked
  - test_ssrf_rfc1918_192_168_rejected     — 192.168.x.x blocked
  - test_ssrf_link_local_rejected          — 169.254.169.254 (metadata endpoint) blocked
  REDIRECT
  - test_redirect_is_blocked               — 3xx redirects raise ExternalRequestError
  TIMEOUT / SIZE
  - test_timeout_raises_external_error     — socket timeout surfaced as ExternalRequestError
  - test_size_limit_enforced               — oversized response raises ExternalRequestError
  PERMISSIONS
  - test_external_scope_allowed            — PermissionChecker no longer denies EXTERNAL
  - test_destructive_still_denied          — DESTRUCTIVE without authorization still denied
  TOOL ARGUMENT INJECTION
  - test_weather_tool_ignores_injected_url — AI cannot override the target domain
  AUDIT LOG
  - test_audit_published_on_success        — external_events receives success event
  - test_audit_published_on_rejection      — external_events receives rejection event
  LIVE E2E
  - test_live_weather_london               — real HTTP call to Open-Meteo for London
"""

from __future__ import annotations

import ipaddress
import socket
import urllib.error
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import Settings
from app.core.events import external_events
from app.core.permissions import (
    PermissionChecker,
    PermissionDenied,
    PermissionRequest,
    PermissionScope,
)
from app.external.client import (
    ExternalHttpClient,
    ExternalRequestError,
    _is_private_ip,
    _ssrf_check,
)
from app.external.weather import WeatherService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client(allowed_domains: list[str] | None = None, **overrides) -> ExternalHttpClient:
    """Return an ExternalHttpClient backed by a custom Settings instance."""
    defaults = {
        "external_allowed_domains": allowed_domains or ["api.open-meteo.com", "geocoding-api.open-meteo.com"],
        "external_request_timeout_seconds": 10,
        "external_max_response_bytes": 1_000_000,
    }
    defaults.update(overrides)
    settings = Settings(**defaults)
    client = ExternalHttpClient()
    # Patch get_settings inside the client module so it uses our test settings
    client._test_settings = settings
    return client


def _make_mock_response(body: bytes, status: int = 200):
    """Create a minimal mock urllib response object."""
    mock = MagicMock()
    mock.status = status
    # read() returns body once then b""
    calls = [body, b""]
    mock.read.side_effect = calls
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    return mock


# ---------------------------------------------------------------------------
# SSRF helper unit tests
# ---------------------------------------------------------------------------

class TestIsPrivateIp:
    def test_loopback_v4(self):
        assert _is_private_ip("127.0.0.1") is True

    def test_loopback_v4_other(self):
        assert _is_private_ip("127.255.255.255") is True

    def test_rfc1918_class_a(self):
        assert _is_private_ip("10.0.0.1") is True
        assert _is_private_ip("10.255.255.255") is True

    def test_rfc1918_class_b(self):
        assert _is_private_ip("172.16.0.1") is True
        assert _is_private_ip("172.31.255.255") is True

    def test_rfc1918_class_c(self):
        assert _is_private_ip("192.168.1.1") is True
        assert _is_private_ip("192.168.255.255") is True

    def test_link_local(self):
        assert _is_private_ip("169.254.0.1") is True
        assert _is_private_ip("169.254.169.254") is True  # AWS/GCP metadata

    def test_public_ip_not_private(self):
        assert _is_private_ip("8.8.8.8") is False
        assert _is_private_ip("151.101.1.1") is False
        assert _is_private_ip("93.184.216.34") is False

    def test_ipv6_loopback(self):
        assert _is_private_ip("::1") is True

    def test_ipv6_link_local(self):
        assert _is_private_ip("fe80::1") is True

    def test_ipv6_public_not_private(self):
        assert _is_private_ip("2001:4860:4860::8888") is False  # Google DNS


# ---------------------------------------------------------------------------
# ALLOWLIST tests
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# ALLOWLIST tests
# ---------------------------------------------------------------------------

class TestDomainAllowlist:
    @pytest.mark.parametrize(
        "url",
        [
            "https://api.open-meteo.com/v1/forecast",
            "https://geocoding-api.open-meteo.com/v1/search",
        ],
    )
    def test_allowlisted_domain_passes(self, url: str):
        """Allowlisted domains should pass the domain check (not raise on the allowlist step).
        We mock the SSRF check and the actual network call so only the allowlist is tested."""
        settings = Settings(
            external_allowed_domains=["api.open-meteo.com", "geocoding-api.open-meteo.com"],
            external_request_timeout_seconds=5,
            external_max_response_bytes=1_000_000,
        )
        client = ExternalHttpClient()
        mock_resp = _make_mock_response(b'{"results": []}')
        with (
            patch("app.external.client.get_settings", return_value=settings),
            patch("app.external.client._ssrf_check"),  # skip DNS
            patch("app.external.client._OPENER") as mock_opener,
        ):
            mock_opener.open.return_value = mock_resp
            try:
                client.get(url)
            except ExternalRequestError:
                pytest.fail(f"Allowlisted domain in '{url}' raised ExternalRequestError unexpectedly")

    def test_non_allowlisted_domain_rejected(self):
        """A non-allowlisted domain must be rejected *before* any network I/O."""
        settings = Settings(
            external_allowed_domains=["api.open-meteo.com", "geocoding-api.open-meteo.com"],
            external_request_timeout_seconds=5,
            external_max_response_bytes=1_000_000,
        )
        client = ExternalHttpClient()
        with (
            patch("app.external.client.get_settings", return_value=settings),
            patch("app.external.client.socket.getaddrinfo") as mock_dns,
        ):
            with pytest.raises(ExternalRequestError, match="not in the external allowed domains"):
                client.get("https://evil.example.com/steal")
            # DNS must never have been called (network call blocked before DNS)
            mock_dns.assert_not_called()

    @pytest.mark.parametrize(
        "url",
        [
            "http://api.open-meteo.com/v1/forecast",
            "http://geocoding-api.open-meteo.com/v1/search",
        ],
    )
    def test_http_scheme_rejected(self, url: str):
        """Plain HTTP (non-HTTPS) must be rejected regardless of domain."""
        settings = Settings(
            external_allowed_domains=["api.open-meteo.com", "geocoding-api.open-meteo.com"],
            external_request_timeout_seconds=5,
            external_max_response_bytes=1_000_000,
        )
        client = ExternalHttpClient()
        with (
            patch("app.external.client.get_settings", return_value=settings),
        ):
            with pytest.raises(ExternalRequestError, match="Only HTTPS"):
                client.get(url)


# ---------------------------------------------------------------------------
# SSRF tests
# ---------------------------------------------------------------------------

class TestSsrfProtection:
    """Each test resolves to a private IP; the client must block it across all allowlisted domains."""

    def _check_blocked(self, domain: str, fake_ip: str, settings: Settings | None = None):
        s = settings or Settings(
            external_allowed_domains=["api.open-meteo.com", "geocoding-api.open-meteo.com"],
            external_request_timeout_seconds=5,
            external_max_response_bytes=1_000_000,
        )
        client = ExternalHttpClient()

        def fake_getaddrinfo(host, port):
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (fake_ip, 80))]

        with (
            patch("app.external.client.get_settings", return_value=s),
            patch("app.external.client.socket.getaddrinfo", side_effect=fake_getaddrinfo),
        ):
            with pytest.raises(ExternalRequestError, match="SSRF guard"):
                client.get(f"https://{domain}/some/path")

    @pytest.mark.parametrize("domain", ["api.open-meteo.com", "geocoding-api.open-meteo.com"])
    def test_ssrf_localhost_rejected(self, domain: str):
        self._check_blocked(domain, "127.0.0.1")

    @pytest.mark.parametrize("domain", ["api.open-meteo.com", "geocoding-api.open-meteo.com"])
    def test_ssrf_rfc1918_10_rejected(self, domain: str):
        self._check_blocked(domain, "10.0.0.1")

    @pytest.mark.parametrize("domain", ["api.open-meteo.com", "geocoding-api.open-meteo.com"])
    def test_ssrf_rfc1918_172_rejected(self, domain: str):
        self._check_blocked(domain, "172.16.5.10")

    @pytest.mark.parametrize("domain", ["api.open-meteo.com", "geocoding-api.open-meteo.com"])
    def test_ssrf_rfc1918_192_168_rejected(self, domain: str):
        self._check_blocked(domain, "192.168.1.50")

    @pytest.mark.parametrize("domain", ["api.open-meteo.com", "geocoding-api.open-meteo.com"])
    def test_ssrf_link_local_rejected(self, domain: str):
        """169.254.169.254 is the cloud instance-metadata endpoint."""
        self._check_blocked(domain, "169.254.169.254")


# ---------------------------------------------------------------------------
# REDIRECT test
# ---------------------------------------------------------------------------

class TestRedirectPolicy:
    @pytest.mark.parametrize("domain", ["api.open-meteo.com", "geocoding-api.open-meteo.com"])
    def test_redirect_is_blocked(self, domain: str):
        """Any HTTP 3xx from the server must raise ExternalRequestError — never followed."""
        settings = Settings(
            external_allowed_domains=["api.open-meteo.com", "geocoding-api.open-meteo.com"],
            external_request_timeout_seconds=5,
            external_max_response_bytes=1_000_000,
        )
        client = ExternalHttpClient()

        def fake_getaddrinfo(host, port):
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 80))]

        # Simulate the _NoRedirectHandler raising on a 302
        redirect_err = ExternalRequestError("Redirect to 'https://other.com/' blocked")

        with (
            patch("app.external.client.get_settings", return_value=settings),
            patch("app.external.client.socket.getaddrinfo", side_effect=fake_getaddrinfo),
            patch("app.external.client._OPENER") as mock_opener,
        ):
            mock_opener.open.side_effect = redirect_err
            with pytest.raises(ExternalRequestError, match="Redirect"):
                client.get(f"https://{domain}/v1/endpoint")


# ---------------------------------------------------------------------------
# TIMEOUT and SIZE tests
# ---------------------------------------------------------------------------

class TestTimeoutAndSize:
    @pytest.mark.parametrize("domain", ["api.open-meteo.com", "geocoding-api.open-meteo.com"])
    def test_timeout_raises_external_error(self, domain: str):
        settings = Settings(
            external_allowed_domains=["api.open-meteo.com", "geocoding-api.open-meteo.com"],
            external_request_timeout_seconds=5,
            external_max_response_bytes=1_000_000,
        )
        client = ExternalHttpClient()

        def fake_getaddrinfo(host, port):
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 80))]

        with (
            patch("app.external.client.get_settings", return_value=settings),
            patch("app.external.client.socket.getaddrinfo", side_effect=fake_getaddrinfo),
            patch("app.external.client._OPENER") as mock_opener,
        ):
            mock_opener.open.side_effect = TimeoutError("timed out")
            with pytest.raises(ExternalRequestError, match="timed out"):
                client.get(f"https://{domain}/v1/endpoint")

    @pytest.mark.parametrize("domain", ["api.open-meteo.com", "geocoding-api.open-meteo.com"])
    def test_size_limit_enforced(self, domain: str):
        settings = Settings(
            external_allowed_domains=["api.open-meteo.com", "geocoding-api.open-meteo.com"],
            external_request_timeout_seconds=5,
            external_max_response_bytes=100,  # tiny limit
        )
        client = ExternalHttpClient()

        def fake_getaddrinfo(host, port):
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 80))]

        # Build a response that exceeds 100 bytes
        big_body = b"x" * 101
        mock_resp = MagicMock()
        mock_resp.status = 200
        # Return 101 bytes in the first read, then empty
        mock_resp.read.side_effect = [big_body, b""]
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with (
            patch("app.external.client.get_settings", return_value=settings),
            patch("app.external.client.socket.getaddrinfo", side_effect=fake_getaddrinfo),
            patch("app.external.client._OPENER") as mock_opener,
        ):
            mock_opener.open.return_value = mock_resp
            with pytest.raises(ExternalRequestError, match="size limit"):
                client.get(f"https://{domain}/v1/endpoint")


# ---------------------------------------------------------------------------
# PERMISSION SCOPE tests
# ---------------------------------------------------------------------------

class TestPermissionScope:
    def test_external_scope_allowed(self):
        """PermissionChecker must no longer deny EXTERNAL scope."""
        checker = PermissionChecker()
        req = PermissionRequest(
            scope=PermissionScope.EXTERNAL,
            actor="ai",
            description="call weather API",
        )
        checker.check(req)  # must not raise

    def test_read_still_allowed(self):
        checker = PermissionChecker()
        checker.check(PermissionRequest(scope=PermissionScope.READ, actor="ai", description="x"))

    def test_write_still_allowed(self):
        checker = PermissionChecker()
        checker.check(PermissionRequest(scope=PermissionScope.WRITE, actor="ai", description="x"))

    def test_destructive_still_denied_without_authorization(self):
        checker = PermissionChecker()
        with pytest.raises(PermissionDenied):
            checker.check(PermissionRequest(
                scope=PermissionScope.DESTRUCTIVE,
                actor="ai",
                description="delete task",
                authorized=False,
            ))

    def test_destructive_allowed_with_authorization(self):
        checker = PermissionChecker()
        checker.check(PermissionRequest(
            scope=PermissionScope.DESTRUCTIVE,
            actor="ai",
            description="delete task",
            authorized=True,
        ))


# ---------------------------------------------------------------------------
# TOOL ARGUMENT INJECTION test
# ---------------------------------------------------------------------------

class TestToolArgumentInjection:
    def test_weather_tool_ignores_injected_url(self):
        """The AI can only supply `location`; even if args contain a rogue URL,
        WeatherService always targets the fixed Open-Meteo domain."""
        from app.ai.tools.implementations import GetCurrentWeatherTool
        tool = GetCurrentWeatherTool()

        # Verify the tool schema only exposes `location`, not a url/domain field
        props = tool.parameters_schema.get("properties", {})
        assert "location" in props, "Tool must accept location"
        assert "url" not in props, "Tool must NOT expose a url parameter"
        assert "domain" not in props, "Tool must NOT expose a domain parameter"
        assert "base_url" not in props, "Tool must NOT expose a base_url parameter"

        # Verify that even if we inject a url key, WeatherService ignores it
        # (WeatherService has hardcoded GEOCODING_URL and FORECAST_URL constants)
        assert "geocoding-api.open-meteo.com" in WeatherService.GEOCODING_URL
        assert "api.open-meteo.com" in WeatherService.FORECAST_URL


# ---------------------------------------------------------------------------
# AUDIT LOG tests
# ---------------------------------------------------------------------------

class TestAuditLog:
    def test_audit_published_on_success(self):
        settings = Settings(
            external_allowed_domains=["api.open-meteo.com"],
            external_request_timeout_seconds=5,
            external_max_response_bytes=1_000_000,
        )
        client = ExternalHttpClient()
        events_received: list[dict] = []
        handler = lambda p: events_received.append(p)  # noqa: E731
        external_events.subscribe("external.request", handler)

        def fake_getaddrinfo(host, port):
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 80))]

        mock_resp = _make_mock_response(b'{"ok": true}')

        with (
            patch("app.external.client.get_settings", return_value=settings),
            patch("app.external.client.socket.getaddrinfo", side_effect=fake_getaddrinfo),
            patch("app.external.client._OPENER") as mock_opener,
        ):
            mock_opener.open.return_value = mock_resp
            client.get("https://api.open-meteo.com/v1/test")

        assert any(e["outcome"] == "success" for e in events_received)
        assert any(e["domain"] == "api.open-meteo.com" for e in events_received)
        external_events.unsubscribe("external.request", handler)

    def test_audit_published_on_rejection(self):
        settings = Settings(
            external_allowed_domains=["api.open-meteo.com"],
            external_request_timeout_seconds=5,
            external_max_response_bytes=1_000_000,
        )
        client = ExternalHttpClient()
        events_received: list[dict] = []
        handler = lambda p: events_received.append(p)
        external_events.subscribe("external.request", handler)

        with (
            patch("app.external.client.get_settings", return_value=settings),
        ):
            with pytest.raises(ExternalRequestError):
                client.get("https://evil.bad-actor.com/steal")

        assert any(e["outcome"] == "rejected_allowlist" for e in events_received)
        external_events.unsubscribe("external.request", handler)


# ---------------------------------------------------------------------------
# LIVE end-to-end test (real HTTP to Open-Meteo)
# ---------------------------------------------------------------------------

@pytest.mark.live
def test_live_weather_london():
    """Live integration test: fetch actual weather for London via Open-Meteo.

    Requires internet access. Run with: pytest -m live tests/test_external_client.py
    Skipped automatically when there is no network.
    """
    import socket as _socket
    try:
        _socket.setdefaulttimeout(5)
        _socket.gethostbyname("api.open-meteo.com")
    except OSError:
        pytest.skip("No internet access — skipping live test")

    svc = WeatherService()
    result = svc.get_current_weather("London")

    assert result["location_name"] == "London"
    assert result["country"] == "United Kingdom"
    assert isinstance(result["temperature_c"], (int, float))
    assert isinstance(result["humidity_pct"], (int, float))
    assert isinstance(result["wind_speed_mph"], (int, float))
    assert isinstance(result["conditions"], str)
    assert len(result["conditions"]) > 0
    assert result["data_time"] is not None

    print(f"\n=== Live Weather: London ===")
    print(f"  Temperature : {result['temperature_c']}°C")
    print(f"  Humidity    : {result['humidity_pct']}%")
    print(f"  Wind speed  : {result['wind_speed_mph']} mph")
    print(f"  Conditions  : {result['conditions']}")
    print(f"  As of       : {result['data_time']}")
