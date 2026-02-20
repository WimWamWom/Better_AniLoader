"""HTTP client with DNS‑over‑HTTPS resolution (Cloudflare 1.1.1.1).

Bypasses potential ISP DNS blocks on streaming sites by resolving
hostnames via Cloudflare's DoH endpoint and patching Python's
``socket.getaddrinfo`` to use cached results.
"""

from __future__ import annotations

import socket
from typing import Any, Dict
from urllib.parse import urlparse

import httpx

from core.constants import USER_AGENT
from core.logging_setup import get_logger

log = get_logger("http")

# ── DNS cache + monkey‑patch ──────────────────────────────────────────

_dns_cache: Dict[str, str] = {}
_original_getaddrinfo = socket.getaddrinfo


def _patched_getaddrinfo(
    host: str,
    port: Any,
    family: int = 0,
    type: int = 0,
    proto: int = 0,
    flags: int = 0,
):
    if host in _dns_cache:
        return _original_getaddrinfo(
            _dns_cache[host], port, family, type, proto, flags
        )
    return _original_getaddrinfo(host, port, family, type, proto, flags)


socket.getaddrinfo = _patched_getaddrinfo  # type: ignore[assignment]


def _resolve_via_cloudflare(hostname: str) -> str:
    """Resolve *hostname* via Cloudflare DNS‑over‑HTTPS.

    Returns the resolved IP or the original hostname on failure.
    """
    try:
        resp = httpx.get(
            "https://1.1.1.1/dns-query",
            params={"name": hostname, "type": "A"},
            headers={"accept": "application/dns-json"},
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        answers = data.get("Answer", [])
        if answers:
            ip = answers[0]["data"]
            log.debug("DNS resolved %s → %s (Cloudflare)", hostname, ip)
            return ip
    except Exception as exc:
        log.warning("Cloudflare DNS failed for %s: %s – falling back to system DNS", hostname, exc)
    return hostname


# ── Public client ─────────────────────────────────────────────────────

_DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
}


class HttpClient:
    """Thin wrapper around ``httpx.Client`` with per-request DoH resolution.

    Usage::

        client = HttpClient()
        resp = client.get("https://aniworld.to/anime/stream/one-piece")
    """

    def __init__(self, timeout: float = 15.0) -> None:
        self._client = httpx.Client(
            headers=_DEFAULT_HEADERS,
            timeout=timeout,
            follow_redirects=True,
        )

    # ── Core verbs ────────────────────────────────────────────────────

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        self._ensure_dns(url)
        return self._client.get(url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        self._ensure_dns(url)
        return self._client.post(url, **kwargs)

    def head(self, url: str, **kwargs: Any) -> httpx.Response:
        self._ensure_dns(url)
        return self._client.head(url, **kwargs)

    # ── Helpers ───────────────────────────────────────────────────────

    def _ensure_dns(self, url: str) -> None:
        hostname = urlparse(url).hostname
        if hostname and hostname not in _dns_cache:
            ip = _resolve_via_cloudflare(hostname)
            if ip != hostname:
                _dns_cache[hostname] = ip

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


# Module‑level singleton (lazily importable)
http = HttpClient()
