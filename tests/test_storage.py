import csv
import json
from dataclasses import fields, replace

import pytest

from monster_scraper.models import Callout, Drink
from monster_scraper.storage import read_lines, write_csv, write_json, write_lines


@pytest.fixture
def drink() -> Drink:
    return Drink(
        id="cs-cz/juiced-monster/khaotic",
        locale="cs-cz",
        category="Juiced Monster",
        category_slug="juiced-monster",
        slug="khaotic",
        name="Juiced Monster Khaotic",
        flavor="Pomeranč, citrus",
        description="Energetický nápoj",
        note="Údaje jsou založeny na 500 ml",
        image_url="https://example.com/can.png",
        logo_url="https://example.com/logo.png",
        url="https://www.monsterenergy.com/cs-cz/energy-drinks/juiced-monster/khaotic/",
        callouts=(Callout("160 mg", "Kofein"), Callout("39 g", "Cukr")),
        image_path="images/cs-cz/juiced-monster/khaotic.png",
    )


def test_lines_round_trip(tmp_path):
    path = tmp_path / "nested" / "locales.txt"
    write_lines(path, ["en-gb", "it-it"])

    assert path.read_text(encoding="utf-8") == "en-gb\nit-it\n"
    assert read_lines(path) == ["en-gb", "it-it"]


def test_read_lines_skips_blank_lines(tmp_path):
    path = tmp_path / "links.txt"
    path.write_text("  a  \n\n b\n\n", encoding="utf-8")

    assert read_lines(path) == ["a", "b"]


def test_json_keeps_unicode_and_structure(tmp_path, drink):
    path = tmp_path / "drinks.json"
    write_json(path, [drink])

    raw = path.read_text(encoding="utf-8")
    assert "Pomeranč" in raw  # not \u-escaped
    data = json.loads(raw)
    assert data == [drink.to_dict()]
    assert data[0]["callouts"] == [
        {"value": "160 mg", "label": "Kofein"},
        {"value": "39 g", "label": "Cukr"},
    ]


def test_csv_flattens_callouts(tmp_path, drink):
    path = tmp_path / "drinks.csv"
    write_csv(path, [drink, replace(drink, callouts=(), image_path=None)])

    with path.open(encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        rows = list(reader)

    assert reader.fieldnames == [f.name for f in fields(Drink)]
    assert rows[0]["callouts"] == "160 mg Kofein; 39 g Cukr"
    assert rows[0]["flavor"] == "Pomeranč, citrus"
    assert rows[1]["callouts"] == ""
    assert rows[1]["image_path"] == ""
