import asyncio
from dataclasses import dataclass, field

import pytest
from curl_cffi.requests.exceptions import Timeout

from monster_scraper import client as client_module
from monster_scraper.client import FetchError, HttpClient


@dataclass
class FakeResponse:
    status_code: int
    text: str = ""
    url: str = "https://www.monsterenergy.com/"
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def content(self) -> bytes:
        return self.text.encode()


class FakeSession:
    """Replays a scripted sequence of responses (or exceptions)."""

    def __init__(self, *responses: FakeResponse | Exception):
        self.responses = list(responses)
        self.calls = 0

    async def get(self, url: str) -> FakeResponse:
        self.calls += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture
def sleeps(monkeypatch) -> list[float]:
    """Record every asyncio.sleep in the client instead of actually waiting."""
    recorded: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        recorded.append(seconds)

    monkeypatch.setattr(client_module.asyncio, "sleep", fake_sleep)
    return recorded


def fetch(session: FakeSession, **kwargs) -> tuple[str, str]:
    http = HttpClient(delay=0, **kwargs)
    http._session = session  # type: ignore[assignment]
    return asyncio.run(http.get_text("https://www.monsterenergy.com/"))


def test_returns_final_url_and_text(sleeps):
    session = FakeSession(FakeResponse(200, "<html/>", url="https://www.monsterenergy.com/it-it/"))

    assert fetch(session) == ("https://www.monsterenergy.com/it-it/", "<html/>")
    assert session.calls == 1


def test_retries_transient_errors_with_backoff(sleeps):
    session = FakeSession(Timeout("slow"), FakeResponse(503), FakeResponse(200, "ok"))

    assert fetch(session, retries=3)[1] == "ok"
    assert session.calls == 3
    assert [s for s in sleeps if s >= 1] == [4, 8]


def test_honours_retry_after_header(sleeps):
    session = FakeSession(FakeResponse(429, headers={"Retry-After": "7"}), FakeResponse(200, "ok"))

    assert fetch(session)[1] == "ok"
    assert 7 in sleeps


def test_rate_limit_pauses_and_slows_down_every_worker(sleeps):
    http = HttpClient(delay=0.5)
    http._session = FakeSession(FakeResponse(429), FakeResponse(200, "a"), FakeResponse(200, "b"))

    async def go() -> list[str]:
        first = await http.get_text("https://www.monsterenergy.com/a")
        second = await http.get_text("https://www.monsterenergy.com/b")
        return [first[1], second[1]]

    assert asyncio.run(go()) == ["a", "b"]
    assert http._delay == 0.75
    # The next attempt waits out the shared cooldown before hitting the site again.
    assert sum(1 for s in sleeps if s > 3) >= 2


def test_does_not_retry_client_errors(sleeps):
    session = FakeSession(FakeResponse(404))

    with pytest.raises(FetchError) as info:
        fetch(session)
    assert info.value.status == 404
    assert session.calls == 1


def test_gives_up_after_max_retries(sleeps):
    session = FakeSession(FakeResponse(429), FakeResponse(429))

    with pytest.raises(FetchError, match="after 2 attempts") as info:
        fetch(session, retries=2)
    assert info.value.status == 429


def test_requires_context_manager():
    with pytest.raises(RuntimeError, match="context manager"):
        asyncio.run(HttpClient().get_text("https://www.monsterenergy.com/"))
