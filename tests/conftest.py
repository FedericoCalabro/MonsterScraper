from collections.abc import Callable
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_html() -> Callable[[str], str]:
    """Return a loader for the saved HTML pages in ``tests/fixtures``."""

    def load(name: str) -> str:
        return (FIXTURES / name).read_text(encoding="utf-8")

    return load
