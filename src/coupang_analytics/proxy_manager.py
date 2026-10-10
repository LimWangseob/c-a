"""proxy_manager.py

Thread-safe proxy pool (URL normalization + load) for the rank-only proxy.

Supported proxy URL schemes:
    http://
    https://
    socks5://
    socks5h://

Usage (proxy_pool.load_manager): ``ProxyManager().load_from_file(path)`` / ``load_proxies([...])``
→ ``manager.proxies`` (``ProxyNode``: endpoint·redacted_url·is_active). Node selection = proxy_pool.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Iterable, List, Optional
from urllib.parse import unquote, urlparse, urlunparse


logger = logging.getLogger("ProxyManager")

_SUPPORTED_SCHEMES = {"http", "https", "socks5", "socks5h"}


class ProxyConfigurationError(ValueError):
    """Raised when a proxy URL or manager option is invalid."""


def _format_host_for_url(host: str) -> str:
    """Wrap IPv6 literals in brackets when reconstructing a URL authority."""
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host


def _normalize_proxy_url(value: str) -> str:
    """Validate and normalize a proxy URL without changing its credentials."""
    if not isinstance(value, str):
        raise ProxyConfigurationError("Proxy entry must be a string.")

    cleaned = value.strip()
    if not cleaned:
        raise ProxyConfigurationError("Proxy entry is empty.")

    if "://" not in cleaned:
        cleaned = f"http://{cleaned}"

    try:
        parsed = urlparse(cleaned)
        scheme = parsed.scheme.lower()
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ProxyConfigurationError("Proxy URL contains an invalid port or authority.") from exc

    if scheme not in _SUPPORTED_SCHEMES:
        raise ProxyConfigurationError(
            f"Unsupported proxy scheme '{scheme}'. "
            f"Supported: {', '.join(sorted(_SUPPORTED_SCHEMES))}."
        )
    if not host:
        raise ProxyConfigurationError("Proxy URL is missing a host.")
    if port is None:
        if scheme == "https":
            port = 443
        elif scheme in {"socks5", "socks5h"}:
            port = 1080
        else:
            port = 80
    if not 1 <= port <= 65535:
        raise ProxyConfigurationError("Proxy port must be between 1 and 65535.")

    # Proxy URLs normally should not contain application paths/queries/fragments.
    if parsed.path not in ("", "/") or parsed.params or parsed.query or parsed.fragment:
        raise ProxyConfigurationError(
            "Proxy URL must contain only scheme, credentials, host, and port."
        )

    userinfo = ""
    if parsed.username is not None:
        # Preserve encoded userinfo from the original netloc where possible by
        # rebuilding safely from parsed values. urllib.parse does not unquote
        # username/password properties automatically.
        username = parsed.username
        userinfo = username
        if parsed.password is not None:
            userinfo += f":{parsed.password}"
        userinfo += "@"

    authority = f"{userinfo}{_format_host_for_url(host)}:{port}"
    return urlunparse((scheme, authority, "", "", "", ""))


@dataclass
class ProxyNode:
    """Metadata for a single proxy endpoint (``is_active`` = selectable by proxy_pool)."""

    raw_url: str = field(repr=False)
    protocol: str = field(init=False, default="")
    host: str = field(init=False, default="")
    port: int = field(init=False, default=0)
    username: Optional[str] = field(init=False, default=None)
    password: Optional[str] = field(init=False, default=None, repr=False)

    is_active: bool = True

    def __post_init__(self) -> None:
        self.raw_url = _normalize_proxy_url(self.raw_url)
        parsed = urlparse(self.raw_url)

        self.protocol = parsed.scheme.lower()
        self.host = parsed.hostname or ""
        if parsed.port is not None:
            self.port = parsed.port
        elif self.protocol == "https":
            self.port = 443
        elif self.protocol in {"socks5", "socks5h"}:
            self.port = 1080
        else:
            self.port = 80
        self.username = unquote(parsed.username) if parsed.username is not None else None
        self.password = unquote(parsed.password) if parsed.password is not None else None

    @property
    def endpoint(self) -> str:
        """Credential-free endpoint identifier suitable for logs."""
        host = _format_host_for_url(self.host)
        return f"{self.protocol}://{host}:{self.port}"

    @property
    def redacted_url(self) -> str:
        """Proxy URL safe for logs and diagnostics."""
        if self.username is None:
            return self.endpoint
        host = _format_host_for_url(self.host)
        return f"{self.protocol}://***:***@{host}:{self.port}"

    def __repr__(self) -> str:
        return (
            "ProxyNode("
            f"url='{self.redacted_url}', "
            f"is_active={self.is_active}"
            ")"
        )


class ProxyManager:
    """Thread-safe proxy pool manager.

    The manager normalizes and de-duplicates proxy URLs into ``ProxyNode`` objects.
    """

    def __init__(
        self,
        proxy_list: Optional[Iterable[str]] = None,
    ) -> None:
        self._lock = threading.RLock()
        self.proxies: List[ProxyNode] = []
        self._known_urls: set[str] = set()

        if proxy_list:
            self.load_proxies(proxy_list)

    def __len__(self) -> int:
        with self._lock:
            return len(self.proxies)

    def load_proxies(self, proxy_list: Iterable[str], *, strict: bool = False) -> int:
        """Add proxy URLs to the pool.

        Duplicate normalized URLs are skipped. Invalid entries are logged and
        skipped unless ``strict=True``.

        Returns the number of newly added nodes.
        """
        added = 0
        invalid_count = 0
        duplicate_count = 0

        for value in proxy_list:
            try:
                node = ProxyNode(raw_url=value)
            except (ProxyConfigurationError, TypeError) as exc:
                invalid_count += 1
                if strict:
                    raise
                logger.warning("Skipped invalid proxy entry: %s", exc)
                continue

            with self._lock:
                if node.raw_url in self._known_urls:
                    duplicate_count += 1
                    continue
                self.proxies.append(node)
                self._known_urls.add(node.raw_url)
                added += 1

        logger.info(
            "Proxy load complete: added=%d, duplicate=%d, invalid=%d, total=%d",
            added,
            duplicate_count,
            invalid_count,
            len(self),
        )
        return added

    def load_from_file(self, filepath: str, *, strict: bool = False) -> int:
        """Load one proxy per line from a UTF-8 text file.

        Blank lines and lines whose first non-space character is ``#`` are
        ignored.
        """
        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"Proxy file not found: {filepath}")

        with open(filepath, "r", encoding="utf-8-sig") as file:
            lines = [
                line.strip()
                for line in file
                if line.strip() and not line.lstrip().startswith("#")
            ]
        return self.load_proxies(lines, strict=strict)


__all__ = [
    "ProxyConfigurationError",
    "ProxyNode",
    "ProxyManager",
]
