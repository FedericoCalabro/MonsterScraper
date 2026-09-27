import asyncio
from dataclasses import replace
from io import BytesIO

from PIL import Image

from monster_scraper.client import FetchError
from monster_scraper.parsers import BASE_URL
from monster_scraper.pipeline import (
    discover_links,
    discover_locales,
    download_images,
    image_path_for,
    scrape_drinks,
)

EN_GB_MANGO = f"{BASE_URL}/en-gb/energy-drinks/juiced-monster/mango-loco/"
CS_CZ_KHAOTIC = f"{BASE_URL}/cs-cz/energy-drinks/juiced-monster/khaotic/"
EN_GB_MISSING = f"{BASE_URL}/en-gb/energy-drinks/juiced-monster/gone/"


class FakeClient:
    """Stands in for HttpClient, serving canned responses keyed by URL."""

    def __init__(self, pages: dict[str, str] | None = None, files: dict[str, bytes] | None = None):
        self.pages = pages or {}
        self.files = files or {}
        self.requested: list[str] = []

    async def get_text(self, url: str) -> tuple[str, str]:
        self.requested.append(url)
        if url not in self.pages:
            raise FetchError(f"HTTP 404 for {url}", status=404)
        return url, self.pages[url]

    async def get_bytes(self, url: str) -> bytes:
        self.requested.append(url)
        if url not in self.files:
            raise FetchError(f"HTTP 404 for {url}", status=404)
        return self.files[url]


def png(width: int, height: int) -> bytes:
    buffer = BytesIO()
    Image.new("RGBA", (width, height)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_discover_locales(fixture_html):
    client = FakeClient({f"{BASE_URL}/": fixture_html("home.html")})

    assert len(asyncio.run(discover_locales(client))) == 110


def test_discover_links_skips_missing_and_redirected_locales(fixture_html):
    listing = fixture_html("listing_en-gb.html")
    client = FakeClient(
        {
            f"{BASE_URL}/en-gb/energy-drinks/": listing,
            # e.g. a locale that silently serves (redirects to) the en-gb catalogue
            f"{BASE_URL}/en-ie/energy-drinks/": listing,
        }
    )
    progress: list[None] = []

    links = asyncio.run(
        discover_links(
            client, ["en-gb", "en-ie", "xx-xx"], on_progress=lambda: progress.append(None)
        )
    )

    assert len(links) == 35
    assert all(url.startswith(f"{BASE_URL}/en-gb/") for url in links)
    assert len(progress) == 3


def test_scrape_drinks_sorts_drinks_and_classifies_failures(fixture_html):
    blank = f"{BASE_URL}/en-gb/energy-drinks/juiced-monster/blank/"
    dead = f"{BASE_URL}/en-gb/energy-drinks/juiced-monster/dead/"
    client = FakeClient(
        {
            EN_GB_MANGO: fixture_html("product_en-gb_mango-loco.html"),
            CS_CZ_KHAOTIC: fixture_html("product_cs-cz_khaotic.html"),
            EN_GB_MISSING: "<html><body>Unexpected markup</body></html>",
            blank: '<section class="product-main"><h1 class="product-name"></h1></section>',
        }
    )

    result = asyncio.run(
        scrape_drinks(client, [EN_GB_MANGO, EN_GB_MISSING, blank, CS_CZ_KHAOTIC, dead])
    )

    assert [d.id for d in result.drinks] == [
        "cs-cz/juiced-monster/khaotic",
        "en-gb/juiced-monster/mango-loco",
    ]
    assert result.unavailable == [blank, dead]
    assert result.failed == [EN_GB_MISSING]


def test_download_images_dedupes_and_resizes(fixture_html, tmp_path):
    pages = {EN_GB_MANGO: fixture_html("product_en-gb_mango-loco.html")}
    drinks = asyncio.run(scrape_drinks(FakeClient(pages), [EN_GB_MANGO])).drinks
    mango = drinks[0]
    # Same artwork reused by a second locale, plus one drink whose image is gone.
    twin = replace(mango, id="en-ie/juiced-monster/mango-loco", locale="en-ie")
    broken = replace(mango, id="en-mt/juiced-monster/mango-loco", image_url="https://cdn/gone.png")
    client = FakeClient(files={mango.image_url: png(800, 1600)})

    result = asyncio.run(download_images(client, [mango, twin, broken], tmp_path, max_width=100))

    assert client.requested.count(mango.image_url) == 1
    assert result[0].image_path == image_path_for(mango).as_posix()
    assert result[1].image_path == image_path_for(twin).as_posix()
    assert result[2].image_path is None
    with Image.open(tmp_path / result[0].image_path) as image:
        assert image.size == (100, 200)
    assert (tmp_path / result[1].image_path).exists()
