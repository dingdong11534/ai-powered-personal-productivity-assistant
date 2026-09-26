"""
SSRF-safe, domain-allowlisted HTTP client for controlled external integrations.

SECURITY MODEL
--------------
This module is the ONLY authorised code path for outbound HTTP requests
in the entire application. All other modules must call ExternalHttpClient;
direct use of urllib, requests, or httpx anywhere else is prohibited.

Two-layer defence against SSRF (Server-Side Request Forgery):

1. Domain allowlist (app/core/config.py: external_allowed_domains)
   Checked against the *hostname* in the URL before any network I/O.
   Exact match only — "api.example.com" does NOT allow "evil.api.example.com".

2. DNS SSRF guard: after the domain is allowed, we resolve it to an IP and
   reject any address in:
   - Loopback:       127.0.0.0/8
   - Private:        10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16
   - Link-local:     169.254.0.0/16  (includes cloud metadata 169.254.169.254)
   - IPv6 loopback:  ::1
   - IPv6 link-local: fe80::/10
   This blocks DNS-rebinding attacks and misconfigured allowlisted records.

REDIRECT POLICY
---------------
Redirects are *disabled entirely*. urllib's default redirect handler is removed.
A redirect (HTTP 3xx) from an allowlisted endpoint raises ExternalRequestError.
Rationale: re-validating a redirect target requires another DNS resolution and
allowlist check; disabling is simpler, equally safe, and the tools we're building
don't need redirects.

CREDENTIAL INJECTION EXTENSION POINT
--------------------------------------
ExternalHttpClient.__init__ accepts an optional `credentials` dict that is
merged into request headers. This is a reserved extension point for Phase 8+
credential handling. Credentials must NEVER come from AI tool arguments —
they must be sourced from server-side config/env only.

AUDIT LOGGING
-------------
Every request attempt (success, allowlist rejection, SSRF rejection, timeout,
size limit) is published to `external_events` (EventBus) with the keys:
  method, domain, url_path, status, outcome, error_detail (optional)
Full response bodies are never logged.
"""

from __future__ import annotations

import ipaddress
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from app.core.config import get_settings
from app.core.events import external_events


class ExternalRequestError(Exception):
    """Raised when an outbound request is blocked or fails."""


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Override that turns any HTTP 3xx into an ExternalRequestError."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ExternalRequestError(
            f"Redirect to '{newurl}' blocked — redirects are disabled for "
            "external requests. The server must respond directly without redirecting."
        )


# Module-level opener with redirect handler replaced so redirects never silently follow.
_OPENER = urllib.request.build_opener(_NoRedirectHandler())


# Private IP ranges to block (SSRF guard)
_BLOCKED_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.ip_network("127.0.0.0/8"),       # Loopback
    ipaddress.ip_network("10.0.0.0/8"),         # RFC1918 Class A
    ipaddress.ip_network("172.16.0.0/12"),      # RFC1918 Class B
    ipaddress.ip_network("192.168.0.0/16"),     # RFC1918 Class C
    ipaddress.ip_network("169.254.0.0/16"),     # Link-local (incl. 169.254.169.254 metadata)
    ipaddress.ip_network("0.0.0.0/8"),          # "This" network
    ipaddress.ip_network("::1/128"),            # IPv6 loopback
    ipaddress.ip_network("fe80::/10"),          # IPv6 link-local
    ipaddress.ip_network("fc00::/7"),           # IPv6 ULA
]


def _is_private_ip(address: str) -> bool:
    """Return True if `address` falls in any private/loopback/link-local range."""
    try:
        ip = ipaddress.ip_address(address)
        return any(ip in net for net in _BLOCKED_NETWORKS)
    except ValueError:
        # Unparseable address — treat as private to be safe
        return True


def _ssrf_check(hostname: str) -> None:
    """Resolve `hostname` and raise ExternalRequestError if any resolved IP is private.

    Uses getaddrinfo so it covers both IPv4 and IPv6.
    """
    try:
        results = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise ExternalRequestError(
            f"DNS resolution failed for '{hostname}': {e}"
        ) from e

    for _family, _type, _proto, _canonname, sockaddr in results:
        ip_str = sockaddr[0]
        if _is_private_ip(ip_str):
            raise ExternalRequestError(
                f"SSRF guard: hostname '{hostname}' resolved to private/reserved "
                f"address '{ip_str}' — request blocked."
            )


class ExternalHttpClient:
    """The single, authorised gateway for all outbound HTTP requests.

    Usage::

        client = ExternalHttpClient()
        data = client.get("https://api.open-meteo.com/v1/forecast",
                          params={"latitude": 51.5, "longitude": -0.1})

    Args:
        credentials: Optional dict of header key->value pairs injected into
                     every request (e.g. {"Authorization": "Bearer TOKEN"}).
                     Must be sourced from server-side config/env only —
                     never from AI tool arguments.
    """

    def __init__(self, credentials: dict[str, str] | None = None) -> None:
        self._credentials: dict[str, str] = credentials or {}

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | list | str:
        """Perform a SSRF-safe, allowlist-checked GET request.

        Returns parsed JSON (dict or list) or raw text string.
        Raises ExternalRequestError for any security rejection or network failure.
        """
        settings = get_settings()
        parsed = urllib.parse.urlparse(url)
        hostname = parsed.hostname or ""
        url_path = parsed.path or "/"

        # 1. Schema check — only https allowed
        if parsed.scheme != "https":
            self._audit("GET", hostname, url_path, None, "rejected_scheme",
                        f"Only HTTPS allowed; got '{parsed.scheme}'")
            raise ExternalRequestError(
                f"Only HTTPS URLs are allowed; got scheme '{parsed.scheme}'."
            )

        # 2. Domain allowlist check (exact hostname match only)
        allowed = list(settings.external_allowed_domains)
        if hostname not in allowed:
            self._audit("GET", hostname, url_path, None, "rejected_allowlist",
                        f"'{hostname}' not in allowlist {allowed}")
            raise ExternalRequestError(
                f"Domain '{hostname}' is not in the external allowed domains list. "
                f"Allowed: {allowed}"
            )

        # 3. SSRF DNS guard — resolve hostname and check resulting IP
        try:
            _ssrf_check(hostname)
        except ExternalRequestError as e:
            self._audit("GET", hostname, url_path, None, "rejected_ssrf", str(e))
            raise

        # 4. Build URL with query params
        if params:
            qs = urllib.parse.urlencode({k: str(v) for k, v in params.items()})
            full_url = f"{url}?{qs}" if "?" not in url else f"{url}&{qs}"
        else:
            full_url = url

        # 5. Build request headers
        headers: dict[str, str] = {
            "User-Agent": "PersonalProductivityAssistant/1.0 (+external-integration)",
            "Accept": "application/json",
        }
        headers.update(self._credentials)
        if extra_headers:
            headers.update(extra_headers)

        req = urllib.request.Request(full_url, headers=headers, method="GET")

        # 6. Execute with timeout + streaming size cap
        timeout = settings.external_request_timeout_seconds
        max_bytes = settings.external_max_response_bytes
        try:
            with _OPENER.open(req, timeout=timeout) as response:
                status = response.status

                # Read response in chunks; abort if size limit exceeded
                chunks: list[bytes] = []
                total = 0
                while True:
                    chunk = response.read(65536)  # 64 KiB per read
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        self._audit("GET", hostname, url_path, status, "rejected_size",
                                    f"Response exceeded {max_bytes} bytes")
                        raise ExternalRequestError(
                            f"Response from '{hostname}' exceeded the "
                            f"{max_bytes:,}-byte size limit — request aborted."
                        )
                    chunks.append(chunk)

                raw = b"".join(chunks)

        except ExternalRequestError:
            raise
        except TimeoutError as e:
            self._audit("GET", hostname, url_path, None, "timeout",
                        f"Timed out after {timeout}s")
            raise ExternalRequestError(
                f"Request to '{hostname}' timed out after {timeout} seconds."
            ) from e
        except urllib.error.HTTPError as e:
            self._audit("GET", hostname, url_path, e.code, "http_error", str(e))
            raise ExternalRequestError(
                f"HTTP {e.code} from '{hostname}': {e.reason}"
            ) from e
        except urllib.error.URLError as e:
            self._audit("GET", hostname, url_path, None, "url_error", str(e.reason))
            raise ExternalRequestError(
                f"Network error reaching '{hostname}': {e.reason}"
            ) from e

        # 7. Decode and parse
        try:
            decoded = raw.decode("utf-8")
            result: dict[str, Any] | list | str = json.loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError):
            result = raw.decode("utf-8", errors="replace")

        self._audit("GET", hostname, url_path, status, "success")
        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _audit(
        method: str,
        domain: str,
        url_path: str,
        status: int | None,
        outcome: str,
        error_detail: str | None = None,
    ) -> None:
        """Publish a structured audit record to external_events (no response body)."""
        payload: dict[str, Any] = {
            "method": method,
            "domain": domain,
            "url_path": url_path,
            "status": status,
            "outcome": outcome,
        }
        if error_detail:
            payload["error_detail"] = error_detail
        external_events.publish("external.request", payload)
