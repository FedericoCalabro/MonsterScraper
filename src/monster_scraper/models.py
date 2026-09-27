"""Data models for scraped drinks."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Callout:
    """A highlighted figure on a product page, e.g. ``160mg`` / ``Caffeine``."""

    value: str
    label: str

    def __str__(self) -> str:
        return f"{self.value} {self.label}".strip()


@dataclass(frozen=True, slots=True)
class Drink:
    """A single can as listed on one locale of monsterenergy.com."""

    id: str
    locale: str
    category: str
    category_slug: str
    slug: str
    name: str
    flavor: str
    description: str
    note: str
    image_url: str
    logo_url: str
    url: str
    callouts: tuple[Callout, ...] = field(default_factory=tuple)
    image_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        data = asdict(self)
        data["callouts"] = [asdict(c) for c in self.callouts]
        return data

    def to_row(self) -> dict[str, str]:
        """Return a flat representation suitable for CSV output."""
        data = self.to_dict()
        data["callouts"] = "; ".join(str(c) for c in self.callouts)
        data["image_path"] = self.image_path or ""
        return data
