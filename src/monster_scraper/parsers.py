"""Pure functions that turn monsterenergy.com HTML into data.

Nothing in this module performs I/O, which keeps it fully testable offline
against saved HTML fixtures (see ``tests/fixtures``).
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urljoin, urlsplit

from selectolax.lexbor import LexborHTMLParser, LexborNode

from monster_scraper.models import Callout, Drink

BASE_URL = "https://www.monsterenergy.com"

_LOCALE_HREF = re.compile(r"^(?:https?://www\.monsterenergy\.com)?/([a-z]{2}-[a-z]{2})/$")
_DRINK_PATH = re.compile(
    r"^/(?P<locale>[a-z]{2}-[a-z]{2})/energy-drinks/(?P<category>[^/]+)/(?P<slug>[^/]+)/$"
)


class ParseError(ValueError):
    """Raised when a page does not look like what the parser expects."""


class EmptyProductError(ParseError):
    """Raised for product pages the site publishes without any content."""


def _text(node: LexborNode | None, *, deep: bool = True) -> str:
    """Visible text of ``node`` with all whitespace runs collapsed to single spaces."""
    if node is None:
        return ""
    # Join text nodes with a space so words around inline tags (<b>, <br>…) don't merge.
    return " ".join(node.text(deep=deep, separator=" ").split())


def _attr(node: LexborNode | None, name: str) -> str:
    return (node.attributes.get(name) or "").strip() if node is not None else ""


def _hrefs(html: str) -> list[str]:
    tree = LexborHTMLParser(html)
    return [href for a in tree.css("a[href]") if (href := a.attributes.get("href"))]


def parse_locales(html: str) -> list[str]:
    """Extract every locale code (e.g. ``en-gb``) from the home page's country selector."""
    return sorted({m[1] for href in _hrefs(html) if (m := _LOCALE_HREF.match(href))})


def parse_drink_links(html: str) -> list[str]:
    """Extract absolute product-page URLs from an ``/<locale>/energy-drinks/`` listing page.

    Category landing pages (``/<locale>/energy-drinks/<category>/``) are excluded.
    """
    links = set()
    for href in _hrefs(html):
        url = urljoin(BASE_URL, href)
        if url.startswith(BASE_URL) and _DRINK_PATH.match(urlsplit(url).path):
            links.add(url)
    return sorted(links)


def split_drink_url(url: str) -> tuple[str, str, str]:
    """Return ``(locale, category_slug, slug)`` for a product-page URL."""
    match = _DRINK_PATH.match(unquote(urlsplit(url).path))
    if match is None:
        raise ParseError(f"Not a product URL: {url}")
    return match["locale"], match["category"], match["slug"]


def parse_drink(html: str, url: str) -> Drink:
    """Parse a product page into a :class:`Drink`."""
    locale, category_slug, slug = split_drink_url(url)
    tree = LexborHTMLParser(html)

    main = tree.css_first("section.product-main")
    if main is None:
        raise ParseError(f"No product found on page: {url}")
    name = _text(main.css_first("h1.product-name"))
    if not name:
        # Some locales list products whose page is an empty template (blank title and name).
        raise EmptyProductError(f"Product page is empty: {url}")

    description = _text(main.css_first("p.product-description-desktop")) or _text(
        main.css_first("p.product-description")
    )
    callouts = tuple(
        Callout(value=_text(node, deep=False), label=_text(node.css_first("span")))
        for node in main.css(".product-callouts .callout-content")
    )
    category = _text(tree.css_first("#product-nav option[selected]")) or (
        category_slug.replace("-", " ").title()
    )

    return Drink(
        id=f"{locale}/{category_slug}/{slug}",
        locale=locale,
        category=category,
        category_slug=category_slug,
        slug=slug,
        name=name,
        flavor=_text(main.css_first("h2.product-flavor"), deep=False),
        description=description,
        note=_text(main.css_first("p.product-note")),
        image_url=_attr(main.css_first("img.can"), "src"),
        logo_url=_attr(main.css_first(".product-logo img"), "src"),
        url=url,
        callouts=callouts,
    )
