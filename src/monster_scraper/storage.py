"""Reading and writing output files."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Sequence
from dataclasses import fields
from pathlib import Path

from monster_scraper.models import Drink


def read_lines(path: Path) -> list[str]:
    """Read non-empty, stripped lines from a text file."""
    return [line for raw in path.read_text(encoding="utf-8").splitlines() if (line := raw.strip())]


def write_lines(path: Path, lines: Iterable[str]) -> None:
    """Write one item per line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")


def write_bytes(path: Path, data: bytes) -> None:
    """Write binary data, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def write_json(path: Path, drinks: Sequence[Drink]) -> None:
    """Write drinks as a pretty-printed UTF-8 JSON array."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [drink.to_dict() for drink in drinks]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, drinks: Sequence[Drink]) -> None:
    """Write drinks as CSV, one row per drink with callouts flattened into one column."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=[f.name for f in fields(Drink)])
        writer.writeheader()
        writer.writerows(drink.to_row() for drink in drinks)
