import asyncio
import json

import pytest

from monster_scraper.cli import DRINKS_JSON, LINKS_FILE, _drinks_stage
from monster_scraper.parsers import BASE_URL

EN_GB_MANGO = f"{BASE_URL}/en-gb/energy-drinks/juiced-monster/mango-loco/"


class CrashingImagesClient:
    """Serves product pages, but every image download blows up unexpectedly."""

    def __init__(self, pages: dict[str, str]):
        self.pages = pages

    async def get_text(self, url: str) -> tuple[str, str]:
        return url, self.pages[url]

    async def get_bytes(self, url: str) -> bytes:
        raise RuntimeError("connection reset")


def test_drinks_are_saved_before_images_are_downloaded(fixture_html, tmp_path):
    (tmp_path / LINKS_FILE).write_text(f"{EN_GB_MANGO}\n", encoding="utf-8")
    client = CrashingImagesClient({EN_GB_MANGO: fixture_html("product_en-gb_mango-loco.html")})

    with pytest.raises(RuntimeError):
        asyncio.run(
            _drinks_stage(
                client,
                tmp_path,
                None,
                refresh=False,
                images=True,
                image_width=None,
                csv=False,
            )
        )

    drinks = json.loads((tmp_path / DRINKS_JSON).read_text(encoding="utf-8"))
    assert [drink["id"] for drink in drinks] == ["en-gb/juiced-monster/mango-loco"]
    assert drinks[0]["name"] == "Juiced Monster Mango Loco"
