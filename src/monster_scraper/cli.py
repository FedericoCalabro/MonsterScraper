"""Command-line interface."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from monster_scraper import __version__
from monster_scraper.client import HttpClient
from monster_scraper.models import Drink
from monster_scraper.parsers import split_drink_url
from monster_scraper.pipeline import (
    discover_links,
    discover_locales,
    download_images,
    scrape_drinks,
    unique_image_count,
)
from monster_scraper.storage import read_lines, write_csv, write_json, write_lines

LOCALES_FILE = "locales.txt"
LINKS_FILE = "links.txt"
DRINKS_JSON = "drinks.json"
DRINKS_CSV = "drinks.csv"

_LOCALE = re.compile(r"^[a-z]{2}-[a-z]{2}$")

console = Console(stderr=True)
log = logging.getLogger("monster_scraper")

app = typer.Typer(
    help="Scrape every Monster Energy can listed on monsterenergy.com, across all locales.",
    no_args_is_help=True,
    add_completion=False,
)


def _normalise_locales(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    locales = sorted({value.strip().lower() for value in values})
    if invalid := [locale for locale in locales if not _LOCALE.match(locale)]:
        raise typer.BadParameter(f"expected codes like 'en-gb', got: {', '.join(invalid)}")
    return locales


OutDir = Annotated[
    Path,
    typer.Option("--out", "-o", help="Directory for all output files.", file_okay=False),
]
LocaleFilter = Annotated[
    list[str] | None,
    typer.Option(
        "--locale",
        "-l",
        help="Only scrape this locale, e.g. en-gb. Repeat for several.",
        callback=_normalise_locales,
        show_default=False,
    ),
]
Concurrency = Annotated[
    int,
    typer.Option("--concurrency", "-c", min=1, max=16, help="Maximum parallel requests."),
]
Refresh = Annotated[
    bool,
    typer.Option("--refresh", help="Ignore cached locales.txt / links.txt and discover again."),
]
Images = Annotated[bool, typer.Option("--images", help="Download can images into <out>/images.")]
ImageWidth = Annotated[
    int | None,
    typer.Option(
        "--image-width",
        min=1,
        help="Downscale downloaded images to this width in pixels.",
        show_default=False,
    ),
]
Csv = Annotated[bool, typer.Option("--csv", help="Also write drinks.csv next to drinks.json.")]
Verbose = Annotated[bool, typer.Option("--verbose", "-v", help="Show debug logging.")]


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"monster-scraper {__version__}")
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version", callback=_version_callback, is_eager=True, help="Show version and exit."
        ),
    ] = False,
) -> None:
    """Scrape every Monster Energy can listed on monsterenergy.com, across all locales."""


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, show_path=False)],
        force=True,
    )
    log.setLevel(logging.DEBUG if verbose else logging.INFO)


@contextmanager
def _progress(description: str, total: int) -> Iterator[Callable[[], None]]:
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(description, total=total)
        yield lambda: progress.advance(task)


# --------------------------------------------------------------------------- stages


async def _locales_stage(client: HttpClient, out: Path, *, refresh: bool) -> list[str]:
    path = out / LOCALES_FILE
    if path.exists() and not refresh:
        locales = read_lines(path)
        log.info("Using %d cached locales from %s", len(locales), path)
        return locales

    with console.status("Discovering locales…"):
        locales = await discover_locales(client)
    write_lines(path, locales)
    log.info("Found %d locales → %s", len(locales), path)
    return locales


async def _links_stage(
    client: HttpClient, out: Path, locales: list[str] | None, *, refresh: bool
) -> list[str]:
    if locales is None:
        locales = await _locales_stage(client, out, refresh=refresh)

    with _progress("Listing pages", len(locales)) as advance:
        links = await discover_links(client, locales, on_progress=advance)

    path = out / LINKS_FILE
    write_lines(path, links)
    locale_count = len({split_drink_url(url)[0] for url in links})
    log.info(
        "Found %d drink pages in %d of %d locale(s) → %s",
        len(links),
        locale_count,
        len(locales),
        path,
    )
    return links


def _save_drinks(out: Path, drinks: list[Drink], *, csv: bool) -> None:
    write_json(out / DRINKS_JSON, drinks)
    if csv:
        write_csv(out / DRINKS_CSV, drinks)


async def _drinks_stage(
    client: HttpClient,
    out: Path,
    locales: list[str] | None,
    *,
    refresh: bool,
    images: bool,
    image_width: int | None,
    csv: bool,
) -> None:
    links: list[str] = []
    path = out / LINKS_FILE
    if path.exists() and not refresh:
        links = read_lines(path)
        if locales is not None:
            links = [url for url in links if split_drink_url(url)[0] in locales]
        if links:
            log.info("Using %d cached drink pages from %s", len(links), path)
    if not links:
        links = await _links_stage(client, out, locales, refresh=refresh)

    with _progress("Drink pages", len(links)) as advance:
        result = await scrape_drinks(client, links, on_progress=advance)
    drinks = result.drinks
    if not drinks:
        # Most likely blocked or offline: don't clobber results from a previous run.
        log.error("No drinks could be scraped; existing output was left untouched")
        raise typer.Exit(1)

    # Save before the slow, optional image stage so an interrupted or failed download can't lose
    # the metadata. It is saved again once the image paths are known.
    _save_drinks(out, drinks, csv=csv)
    if images:
        with _progress("Can images", unique_image_count(drinks)) as advance:
            drinks = await download_images(
                client, drinks, out, max_width=image_width, on_progress=advance
            )
        _save_drinks(out, drinks, csv=csv)

    locale_count = len({drink.locale for drink in drinks})
    log.info(
        "Scraped %d drinks across %d locale(s) → %s", len(drinks), locale_count, out / DRINKS_JSON
    )
    if result.unavailable:
        log.info(
            "Skipped %d listed page(s) that are empty or missing on the site (-v to list them)",
            len(result.unavailable),
        )
    if result.failed:
        log.warning("%d page(s) could not be scraped, see warnings above", len(result.failed))


# ------------------------------------------------------------------------- commands


@app.command("locales")
def locales_command(
    out: OutDir = Path("output"),
    concurrency: Concurrency = 4,
    verbose: Verbose = False,
) -> None:
    """Discover every locale and write them to <out>/locales.txt."""
    _setup_logging(verbose)

    async def go() -> None:
        async with HttpClient(concurrency=concurrency) as client:
            await _locales_stage(client, out, refresh=True)

    asyncio.run(go())


@app.command("links")
def links_command(
    locale: LocaleFilter = None,
    out: OutDir = Path("output"),
    concurrency: Concurrency = 4,
    refresh: Refresh = False,
    verbose: Verbose = False,
) -> None:
    """Discover every drink page and write them to <out>/links.txt."""
    _setup_logging(verbose)

    async def go() -> None:
        async with HttpClient(concurrency=concurrency) as client:
            await _links_stage(client, out, locale, refresh=refresh)

    asyncio.run(go())


@app.command("drinks")
def drinks_command(
    locale: LocaleFilter = None,
    out: OutDir = Path("output"),
    images: Images = False,
    image_width: ImageWidth = None,
    csv: Csv = False,
    concurrency: Concurrency = 4,
    refresh: Refresh = False,
    verbose: Verbose = False,
) -> None:
    """Scrape every drink page into <out>/drinks.json, reusing cached links when present."""
    _setup_logging(verbose)

    async def go() -> None:
        async with HttpClient(concurrency=concurrency) as client:
            await _drinks_stage(
                client,
                out,
                locale,
                refresh=refresh,
                images=images,
                image_width=image_width,
                csv=csv,
            )

    asyncio.run(go())


@app.command("run")
def run_command(
    locale: LocaleFilter = None,
    out: OutDir = Path("output"),
    images: Images = False,
    image_width: ImageWidth = None,
    csv: Csv = False,
    concurrency: Concurrency = 4,
    verbose: Verbose = False,
) -> None:
    """Run every stage from scratch: locales → links → drinks (→ images)."""
    drinks_command(
        locale=locale,
        out=out,
        images=images,
        image_width=image_width,
        csv=csv,
        concurrency=concurrency,
        refresh=True,
        verbose=verbose,
    )
