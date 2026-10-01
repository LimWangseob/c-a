"""proxy_manager.py

Thread-safe proxy pool manager for legitimate outbound routing, QA, and test automation.

Supported proxy URL schemes:
    http://
    https://
    socks5://
    socks5h://  (Requests/HTTPX; Playwright support may vary by browser/runtime)

Examples:
    manager = ProxyManager([
        "http://user:pass@127.0.0.1:8080",
        "socks5://127.0.0.1:1080",
    ])

    node = manager.get_proxy()
    if node:
        requests.get(
            "https://example.com",
            proxies=manager.to_requests(node),
            timeout=10,
        )

HTTPX (current API):
    import httpx
    node = manager.get_proxy()
    if node:
        with httpx.Client(**manager.to_httpx(node)) as client:
            response = client.get("https://example.com")

Playwright:
    browser = playwright.chromium.launch(
        proxy=manager.to_playwright(node)
    )

Notes:
- For Requests SOCKS support:  pip install "requests[socks]"
- For HTTPX SOCKS support:     pip install "httpx[socks]"
"""

from __future__ import annotations

import logging
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import unquote, urlparse, urlunparse

import requests


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
    """Metadata and health state for a single proxy endpoint."""

    raw_url: str = field(repr=False)
    protocol: str = field(init=False, default="")
    host: str = field(init=False, default="")
    port: int = field(init=False, default=0)
    username: Optional[str] = field(init=False, default=None)
    password: Optional[str] = field(init=False, default=None, repr=False)

    is_active: bool = True
    consecutive_failures: int = 0
    latency_ms: Optional[float] = None
    last_verified: float = 0.0
    last_error: Optional[str] = None
    success_count: int = 0
    failure_count: int = 0

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
            f"is_active={self.is_active}, "
            f"consecutive_failures={self.consecutive_failures}, "
            f"latency_ms={self.latency_ms}"
            ")"
        )


class ProxyManager:
    """Thread-safe proxy pool manager.

    The manager selects active proxies, tracks health, and emits library-specific
    configuration structures for Requests, HTTPX, and Playwright.
    """

    def __init__(
        self,
        proxy_list: Optional[Iterable[str]] = None,
        max_failures: int = 3,
        strategy: str = "round_robin",
        verify_url: str = "https://httpbin.org/ip",
    ) -> None:
        if max_failures < 1:
            raise ProxyConfigurationError("max_failures must be >= 1.")
        if strategy not in {"round_robin", "random"}:
            raise ProxyConfigurationError(
                "strategy must be either 'round_robin' or 'random'."
            )
        if not verify_url.startswith(("http://", "https://")):
            raise ProxyConfigurationError("verify_url must be an HTTP(S) URL.")

        self.max_failures = max_failures
        self.strategy = strategy
        self.verify_url = verify_url

        self._lock = threading.RLock()
        self._index = 0
        self.proxies: List[ProxyNode] = []
        self._known_urls: set[str] = set()

        if proxy_list:
            self.load_proxies(proxy_list)

    def __len__(self) -> int:
        with self._lock:
            return len(self.proxies)

    @property
    def active_count(self) -> int:
        with self._lock:
            return sum(1 for p in self.proxies if p.is_active)

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

    def get_proxy(self) -> Optional[ProxyNode]:
        """Return one active proxy according to the configured strategy."""
        with self._lock:
            active_pool = [p for p in self.proxies if p.is_active]
            if not active_pool:
                logger.warning("No active proxies available in pool.")
                return None

            if self.strategy == "random":
                return random.choice(active_pool)

            node = active_pool[self._index % len(active_pool)]
            self._index = (self._index + 1) % max(len(active_pool), 1)
            return node

    def report_status(
        self,
        proxy_node: ProxyNode,
        success: bool,
        *,
        latency_ms: Optional[float] = None,
        error: Optional[str] = None,
    ) -> None:
        """Update a node's health state from the result of a real request."""
        with self._lock:
            if success:
                proxy_node.consecutive_failures = 0
                proxy_node.is_active = True
                proxy_node.success_count += 1
                proxy_node.last_error = None
                if latency_ms is not None:
                    proxy_node.latency_ms = round(float(latency_ms), 2)
            else:
                proxy_node.consecutive_failures += 1
                proxy_node.failure_count += 1
                proxy_node.last_error = error
                if proxy_node.consecutive_failures >= self.max_failures:
                    if proxy_node.is_active:
                        logger.warning(
                            "Proxy deactivated after %d consecutive failures: %s",
                            proxy_node.consecutive_failures,
                            proxy_node.endpoint,
                        )
                    proxy_node.is_active = False

    def verify_proxy(
        self,
        node: ProxyNode,
        timeout: float = 5.0,
        *,
        verify_tls: bool = True,
    ) -> bool:
        """Health-check one proxy and record its request latency.

        The check uses an explicit per-request proxy configuration and disables
        Requests' environment-proxy inheritance to avoid accidental interference
        from HTTP_PROXY/HTTPS_PROXY settings on the host machine.
        """
        if timeout <= 0:
            raise ValueError("timeout must be > 0.")

        start = time.perf_counter()
        try:
            with requests.Session() as session:
                session.trust_env = False
                response = session.get(
                    self.verify_url,
                    proxies=self.to_requests(node),
                    timeout=timeout,
                    verify=verify_tls,
                )
                response.raise_for_status()

            latency_ms = (time.perf_counter() - start) * 1000.0
            now = time.time()
            with self._lock:
                node.last_verified = now
            self.report_status(node, True, latency_ms=latency_ms)
            return True

        except requests.RequestException as exc:
            with self._lock:
                node.last_verified = time.time()
            self.report_status(
                node,
                False,
                error=f"{exc.__class__.__name__}: {exc}",
            )
            logger.debug("Proxy verification failed for %s: %s", node.endpoint, exc)
            return False

        except Exception as exc:  # Defensive: optional SOCKS dependency, adapters, etc.
            with self._lock:
                node.last_verified = time.time()
            self.report_status(
                node,
                False,
                error=f"{exc.__class__.__name__}: {exc}",
            )
            logger.debug("Unexpected proxy verification error for %s: %s", node.endpoint, exc)
            return False

    def check_all(
        self,
        timeout: float = 5.0,
        *,
        max_workers: int = 8,
        include_inactive: bool = True,
        verify_tls: bool = True,
    ) -> Dict[str, int]:
        """Verify the pool, optionally in parallel.

        Inactive nodes are included by default so a recovered proxy can become
        active again after a successful check.

        Returns: ``{"checked": N, "healthy": N, "unhealthy": N, "active": N}``
        """
        if max_workers < 1:
            raise ValueError("max_workers must be >= 1.")

        with self._lock:
            nodes = [
                p for p in self.proxies if include_inactive or p.is_active
            ]

        if not nodes:
            return {"checked": 0, "healthy": 0, "unhealthy": 0, "active": self.active_count}

        healthy = 0
        worker_count = min(max_workers, len(nodes))
        logger.info("Starting proxy health check: nodes=%d, workers=%d", len(nodes), worker_count)

        if worker_count == 1:
            results = [
                self.verify_proxy(node, timeout=timeout, verify_tls=verify_tls)
                for node in nodes
            ]
            healthy = sum(results)
        else:
            with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="proxy-check") as pool:
                futures = {
                    pool.submit(
                        self.verify_proxy,
                        node,
                        timeout,
                        verify_tls=verify_tls,
                    ): node
                    for node in nodes
                }
                for future in as_completed(futures):
                    try:
                        if future.result():
                            healthy += 1
                    except Exception as exc:  # verify_proxy should absorb request errors
                        node = futures[future]
                        logger.error("Health-check worker failed for %s: %s", node.endpoint, exc)

        result = {
            "checked": len(nodes),
            "healthy": healthy,
            "unhealthy": len(nodes) - healthy,
            "active": self.active_count,
        }
        logger.info("Proxy health check complete: %s", result)
        return result

    def prune_unhealthy(
        self,
        timeout: float = 5.0,
        *,
        max_workers: int = 8,
    ) -> Dict[str, int]:
        """Backward-compatible alias for ``check_all``.

        Note that nodes are deactivated only after ``max_failures`` consecutive
        failures; this method does not physically remove nodes from the list.
        """
        return self.check_all(
            timeout=timeout,
            max_workers=max_workers,
            include_inactive=True,
        )

    def remove_inactive(self) -> int:
        """Physically remove currently inactive nodes from the pool."""
        with self._lock:
            before = len(self.proxies)
            self.proxies = [p for p in self.proxies if p.is_active]
            self._known_urls = {p.raw_url for p in self.proxies}
            self._index = 0
            return before - len(self.proxies)

    def reset_health(self, *, activate_all: bool = True) -> None:
        """Reset health counters, optionally reactivating every node."""
        with self._lock:
            for node in self.proxies:
                node.consecutive_failures = 0
                node.last_error = None
                if activate_all:
                    node.is_active = True

    def snapshot(self) -> List[Dict[str, Any]]:
        """Return a credential-safe health snapshot for UI/logging/metrics."""
        with self._lock:
            return [
                {
                    "proxy": node.redacted_url,
                    "protocol": node.protocol,
                    "host": node.host,
                    "port": node.port,
                    "is_active": node.is_active,
                    "consecutive_failures": node.consecutive_failures,
                    "latency_ms": node.latency_ms,
                    "last_verified": node.last_verified,
                    "last_error": node.last_error,
                    "success_count": node.success_count,
                    "failure_count": node.failure_count,
                }
                for node in self.proxies
            ]

    # ------------------------------------------------------------------
    # Library adapters
    # ------------------------------------------------------------------
    @staticmethod
    def to_requests(node: ProxyNode) -> Dict[str, str]:
        """Return Requests-compatible ``proxies=...`` mapping."""
        return {
            "http": node.raw_url,
            "https": node.raw_url,
        }

    @staticmethod
    def to_httpx(node: ProxyNode) -> Dict[str, str]:
        """Return kwargs for current HTTPX ``Client``/top-level APIs.

        Usage::

            with httpx.Client(**ProxyManager.to_httpx(node)) as client:
                ...

        For advanced per-scheme/domain routing, construct HTTPX ``mounts`` with
        ``httpx.HTTPTransport(proxy=node.raw_url)`` in application code.
        """
        return {"proxy": node.raw_url}

    @staticmethod
    def httpx_proxy_url(node: ProxyNode) -> str:
        """Return only the raw proxy URL for ``httpx.Client(proxy=...)``."""
        return node.raw_url

    @staticmethod
    def to_playwright(
        node: ProxyNode,
        *,
        bypass: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return Playwright-compatible proxy configuration."""
        server = f"{node.protocol}://{_format_host_for_url(node.host)}:{node.port}"
        payload: Dict[str, Any] = {"server": server}

        if node.username is not None:
            payload["username"] = node.username
        if node.password is not None:
            payload["password"] = node.password
        if bypass:
            payload["bypass"] = bypass

        return payload


__all__ = [
    "ProxyConfigurationError",
    "ProxyNode",
    "ProxyManager",
]
