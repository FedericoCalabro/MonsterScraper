"""Async HTTP client for monsterenergy.com.

The site sits behind bot protection that rejects plain HTTP clients (including
``cloudscraper``). ``curl_cffi`` impersonates a real Chrome TLS/HTTP2
fingerprint, which is enough to be served the regular pages.
"""

from __future__ import annotations

import asyncio
import logging
import random
from types import TracebackType
from typing import Self

from curl_cffi.curl import CurlError
from curl_cffi.requests import AsyncSession, Response

log = logging.getLogger(__name__)

RETRY_STATUSES = frozenset({403, 429, 500, 502, 503, 504})
MAX_BACKOFF = 60.0
MAX_DELAY = 5.0


class FetchError(RuntimeError):
    """Raised when a URL cannot be fetched. ``status`` is the last HTTP status, if any."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def _retry_after(response: Response) -> float | None:
    """Seconds requested by a ``Retry-After`` header (capped at a minute), if present."""
    value = (response.headers.get("Retry-After") or "").strip()
    return min(float(value), MAX_BACKOFF) if value.isdigit() else None


class HttpClient:
    """Polite, retrying, concurrency-limited HTTP client.

    When the site answers ``429 Too Many Requests`` every in-flight worker
    pauses, and the delay between requests grows for the rest of the run, so a
    long crawl settles at whatever rate the site tolerates.

    Use as an async context manager::

        async with HttpClient() as client:
            url, html = await client.get_text("https://www.monsterenergy.com/")
    """

    def __init__(
        self,
        *,
        concurrency: int = 4,
        delay: float = 0.5,
        retries: int = 5,
        timeout: float = 30.0,
        impersonate: str = "chrome",
    ) -> None:
        self._concurrency = concurrency
        self._delay = delay
        self._retries = retries
        self._timeout = timeout
        self._impersonate = impersonate
        self._semaphore = asyncio.Semaphore(concurrency)
        self._session: AsyncSession | None = None
        self._resume_at = 0.0  # event-loop time before which no request may start

    async def __aenter__(self) -> Self:
        self._session = AsyncSession(
            impersonate=self._impersonate,
            timeout=self._timeout,
            max_clients=self._concurrency,
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def get_text(self, url: str) -> tuple[str, str]:
        """Fetch ``url`` and return ``(final_url, html)`` after redirects."""
        response = await self._get(url)
        return str(response.url), response.text

    async def get_bytes(self, url: str) -> bytes:
        """Fetch ``url`` and return the raw response body."""
        response = await self._get(url)
        return response.content

    async def _get(self, url: str) -> Response:
        if self._session is None:
            raise RuntimeError("HttpClient must be used as an async context manager")

        error: Exception | None = None
        status: int | None = None
        for attempt in range(1, self._retries + 1):
            backoff = min(2.0 ** (attempt + 1), MAX_BACKOFF)  # 4s, 8s, 16s, …
            async with self._semaphore:
                await self._wait_for_cooldown()
                try:
                    response = await self._session.get(url)
                except CurlError as exc:
                    error, status = exc, None
                else:
                    status = response.status_code
                    if 200 <= status < 300:
                        return response
                    error = FetchError(f"HTTP {status} for {url}", status=status)
                    if status not in RETRY_STATUSES:
                        raise error
                    if status == 429:
                        backoff = _retry_after(response) or backoff
                        self._slow_down(backoff)
                finally:
                    # Space out requests on each slot so we never hammer the site.
                    await asyncio.sleep(self._delay * random.uniform(0.5, 1.5))

            if attempt < self._retries:
                log.debug(
                    "Attempt %d for %s failed (%s), retry in %gs", attempt, url, error, backoff
                )
                await asyncio.sleep(backoff)

        raise FetchError(
            f"Giving up on {url} after {self._retries} attempts: {error}", status=status
        ) from error

    async def _wait_for_cooldown(self) -> None:
        wait = self._resume_at - asyncio.get_running_loop().time()
        if wait > 0:
            await asyncio.sleep(wait)

    def _slow_down(self, pause: float) -> None:
        """Pause every worker for ``pause`` seconds and space out future requests more."""
        now = asyncio.get_running_loop().time()
        self._resume_at = max(self._resume_at, now + pause)
        if self._delay < MAX_DELAY:
            self._delay = min(max(self._delay * 1.5, 0.5), MAX_DELAY)
            log.info("Rate limited by the site, slowing down (%.1fs between requests)", self._delay)
