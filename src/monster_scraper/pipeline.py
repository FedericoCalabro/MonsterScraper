"""The scraping pipeline: locales → listing pages → product pages → images.

Every stage takes an open :class:`HttpClient` and an optional ``on_progress``
callback, invoked once per processed item, so callers can drive a progress bar.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from pathlib import Path

from monster_scraper.client import FetchError, HttpClient
from monster_scraper.images import to_png
from monster_scraper.models import Drink
from monster_scraper.parsers import (
    BASE_URL,
    EmptyProductError,
    ParseError,
    parse_drink,
    parse_drink_links,
    parse_locales,
    split_drink_url,
)
from monster_scraper.storage import write_bytes

log = logging.getLogger(__name__)

ProgressCallback = Callable[[], object]


def _noop() -> None:
    pass


@dataclass(slots=True)
class ScrapeResult:
    drinks: list[Drink] = field(default_factory=list)
    #: Listed pages the site itself serves empty or as 404: nothing to retry.
    unavailable: list[str] = field(default_factory=list)
    #: Pages that failed for any other reason (network, rate limiting, unexpected markup).
    failed: list[str] = field(default_factory=list)


async def discover_locales(client: HttpClient) -> list[str]:
    """Return every locale offered by the site's country selector."""
    _, html = await client.get_text(f"{BASE_URL}/")
    return parse_locales(html)


async def discover_links(
    client: HttpClient,
    locales: Iterable[str],
    on_progress: ProgressCallback = _noop,
) -> list[str]:
    """Return the product-page URLs listed for each locale.

    Locales without an energy-drinks page, or whose page redirects to a
    different locale, contribute no links.
    """

    async def links_for(locale: str) -> list[str]:
        try:
            _, html = await client.get_text(f"{BASE_URL}/{locale}/energy-drinks/")
        except FetchError as exc:
            if exc.status == 404:  # Plenty of locales simply have no product catalogue.
                log.debug("No energy-drinks page for locale %s", locale)
            else:
                log.warning("Skipping locale %s: %s", locale, exc)
            return []
        finally:
            on_progress()
        links = [url for url in parse_drink_links(html) if split_drink_url(url)[0] == locale]
        if not links:
            log.debug("No drinks listed for locale %s", locale)
        return links

    results = await asyncio.gather(*(links_for(locale) for locale in locales))
    return sorted({url for links in results for url in links})


async def scrape_drinks(
    client: HttpClient,
    links: Iterable[str],
    on_progress: ProgressCallback = _noop,
) -> ScrapeResult:
    """Fetch and parse every product page, collecting failures instead of aborting."""

    async def scrape(url: str) -> Drink | FetchError | ParseError:
        try:
            final_url, html = await client.get_text(url)
            return parse_drink(html, final_url)
        except (FetchError, ParseError) as exc:
            return exc
        finally:
            on_progress()

    links = list(links)
    outcomes = await asyncio.gather(*(scrape(url) for url in links))

    result = ScrapeResult()
    by_id: dict[str, Drink] = {}
    for url, outcome in zip(links, outcomes, strict=True):
        if isinstance(outcome, Drink):
            # A renamed product can redirect to a URL we already scraped.
            by_id.setdefault(outcome.id, outcome)
        elif isinstance(outcome, EmptyProductError) or getattr(outcome, "status", None) == 404:
            log.debug("Unavailable on the site: %s (%s)", url, outcome)
            result.unavailable.append(url)
        else:
            log.warning("Skipping %s: %s", url, outcome)
            result.failed.append(url)
    result.drinks = sorted(by_id.values(), key=lambda d: d.id)
    return result


def image_path_for(drink: Drink) -> Path:
    """Relative path (inside the output directory) where a drink's can image is stored."""
    return Path("images", drink.locale, drink.category_slug, f"{drink.slug}.png")


async def download_images(
    client: HttpClient,
    drinks: Iterable[Drink],
    out_dir: Path,
    *,
    max_width: int | None = None,
    on_progress: ProgressCallback = _noop,
) -> list[Drink]:
    """Download each can image and return the drinks with ``image_path`` filled in.

    Many locales share the same artwork, so every unique image URL is only
    downloaded (and resized) once.
    """
    drinks = list(drinks)
    by_url: dict[str, list[Drink]] = defaultdict(list)
    for drink in drinks:
        if drink.image_url:
            by_url[drink.image_url].append(drink)

    async def download(url: str, group: list[Drink]) -> dict[str, str]:
        try:
            data = await client.get_bytes(url)
            png = await asyncio.to_thread(to_png, data, max_width)
        except (FetchError, OSError) as exc:
            log.warning("Skipping image %s: %s", url, exc)
            return {}
        finally:
            on_progress()

        paths = {}
        for drink in group:
            relative = image_path_for(drink)
            write_bytes(out_dir / relative, png)
            paths[drink.id] = relative.as_posix()
        return paths

    results = await asyncio.gather(*(download(url, group) for url, group in by_url.items()))
    saved = {drink_id: path for paths in results for drink_id, path in paths.items()}
    return [replace(drink, image_path=saved.get(drink.id)) for drink in drinks]


def unique_image_count(drinks: Iterable[Drink]) -> int:
    """Number of distinct image downloads :func:`download_images` will perform."""
    return len({drink.image_url for drink in drinks if drink.image_url})
