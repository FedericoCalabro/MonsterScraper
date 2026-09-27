import re

import pytest

from monster_scraper.models import Callout
from monster_scraper.parsers import (
    BASE_URL,
    EmptyProductError,
    ParseError,
    parse_drink,
    parse_drink_links,
    parse_locales,
    split_drink_url,
)

EN_GB_MANGO = f"{BASE_URL}/en-gb/energy-drinks/juiced-monster/mango-loco/"
CS_CZ_KHAOTIC = f"{BASE_URL}/cs-cz/energy-drinks/juiced-monster/khaotic/"
EN_US_MANGO = f"{BASE_URL}/en-us/energy-drinks/juice-monster/mango-loco/"
CDN = "https://web-assests.monsterenergy.com/mnst"


class TestParseLocales:
    def test_finds_every_locale_in_country_selector(self, fixture_html):
        locales = parse_locales(fixture_html("home.html"))

        assert len(locales) == 110
        assert {"en-gb", "en-us", "cs-cz", "it-it", "ja-jp", "zh-tw"} <= set(locales)

    def test_returns_sorted_unique_codes(self, fixture_html):
        locales = parse_locales(fixture_html("home.html"))

        assert locales == sorted(set(locales))
        assert all(re.fullmatch(r"[a-z]{2}-[a-z]{2}", locale) for locale in locales)

    def test_ignores_non_locale_links(self):
        html = """
            <a href="/en-gb/">ok</a>
            <a href="https://www.monsterenergy.com/it-it/">ok</a>
            <a href="/en-gb/energy-drinks/">no</a>
            <a href="https://example.com/fr-fr/">no</a>
            <a href="/EN-GB/">no</a>
        """
        assert parse_locales(html) == ["en-gb", "it-it"]


class TestParseDrinkLinks:
    def test_finds_every_product_on_listing_page(self, fixture_html):
        links = parse_drink_links(fixture_html("listing_en-gb.html"))

        assert len(links) == 35
        assert EN_GB_MANGO in links
        assert links == sorted(set(links))

    def test_links_are_absolute_product_urls(self, fixture_html):
        for url in parse_drink_links(fixture_html("listing_en-gb.html")):
            assert url.startswith(f"{BASE_URL}/en-gb/energy-drinks/")
            assert split_drink_url(url)[0] == "en-gb"

    def test_excludes_category_and_foreign_links(self):
        html = """
            <a href="/en-gb/energy-drinks/">listing</a>
            <a href="/en-gb/energy-drinks/juiced-monster/">category</a>
            <a href="/en-gb/energy-drinks/juiced-monster/mango-loco/">product</a>
            <a href="/en-gb/energy-drinks/juiced-monster/mango-loco/">duplicate</a>
            <a href="https://example.com/en-gb/energy-drinks/juiced-monster/fake/">foreign</a>
        """
        assert parse_drink_links(html) == [EN_GB_MANGO]


class TestSplitDrinkUrl:
    def test_splits_locale_category_and_slug(self):
        assert split_drink_url(EN_US_MANGO) == ("en-us", "juice-monster", "mango-loco")

    def test_decodes_percent_encoded_slugs(self):
        url = f"{BASE_URL}/cs-cz/energy-drinks/monster-energy/origin%C3%A1ln%C3%AD-zelen%C3%BD/"
        assert split_drink_url(url) == ("cs-cz", "monster-energy", "originální-zelený")

    def test_rejects_non_product_urls(self):
        with pytest.raises(ParseError):
            split_drink_url(f"{BASE_URL}/en-gb/energy-drinks/juiced-monster/")


class TestParseDrink:
    def test_en_gb_product(self, fixture_html):
        drink = parse_drink(fixture_html("product_en-gb_mango-loco.html"), EN_GB_MANGO)

        assert drink.id == "en-gb/juiced-monster/mango-loco"
        assert drink.locale == "en-gb"
        assert drink.category == "Juiced Monster"
        assert drink.category_slug == "juiced-monster"
        assert drink.slug == "mango-loco"
        assert drink.name == "Juiced Monster Mango Loco"
        assert drink.flavor == "Juicy Mango"
        assert drink.description.startswith("Juiced Monster Mango Loco 500ml can")
        assert drink.note == "Figures based on 500ml and may vary per region"
        assert drink.callouts == (Callout("160mg", "Caffeine"), Callout("56g", "Sugar"))
        assert drink.image_url == f"{CDN}/92c232b6-c27e-487b-b3d6-11eaeb5226e6.png"
        assert drink.logo_url == f"{CDN}/b7c4f349-4cd7-48b5-8cfc-fe113f8882c6.png"
        assert drink.url == EN_GB_MANGO
        assert drink.image_path is None

    def test_localised_product(self, fixture_html):
        drink = parse_drink(fixture_html("product_cs-cz_khaotic.html"), CS_CZ_KHAOTIC)

        assert drink.id == "cs-cz/juiced-monster/khaotic"
        assert drink.name == "Juiced Monster Khaotic"
        assert drink.flavor == "Pomeranč, citrus"
        assert "Energetický Nápoj" in drink.description
        assert drink.note.startswith("Údaje jsou založeny na 500 ml")
        assert drink.callouts == (Callout("160 mg", "Kofein"), Callout("39 g", "Cukr"))
        assert drink.image_url == f"{CDN}/e9864922-170b-48b2-ba06-ecc1ab620c83.png"

    def test_us_product(self, fixture_html):
        drink = parse_drink(fixture_html("product_en-us_mango-loco.html"), EN_US_MANGO)

        assert drink.id == "en-us/juice-monster/mango-loco"
        assert drink.category == "Juice Monster"
        assert drink.name == "Juice Monster Mango Loco"
        assert drink.flavor == "Juicy Mango"
        assert drink.note == "Caffeine content based on 16 fl oz"
        assert drink.callouts == (Callout("150mg", "Caffeine"), Callout("250", "Calories"))

    def test_ignores_related_products_on_the_page(self, fixture_html):
        # The "More Flavours" carousel also uses `.product-name`; only the main product counts.
        drink = parse_drink(fixture_html("product_en-gb_mango-loco.html"), EN_GB_MANGO)

        assert drink.name == "Juiced Monster Mango Loco"

    def test_falls_back_to_slug_when_category_selector_is_missing(self):
        html = '<section class="product-main"><h1 class="product-name">Ultra</h1></section>'
        drink = parse_drink(html, f"{BASE_URL}/en-gb/energy-drinks/zero-sugar/ultra/")

        assert drink.category == "Zero Sugar"
        assert drink.flavor == ""
        assert drink.callouts == ()
        assert drink.image_url == ""

    def test_normalises_whitespace_and_inline_markup(self):
        html = """
            <section class="product-main">
              <h1 class="product-name">Zero- Sugar  Ultra
                 Strawberry Dreams</h1>
              <h2 class="product-flavor"><span class="profile">Flavour Profile</span>
                 Strawberry </h2>
              <p class="product-description-desktop">Light <b>and</b> crisp.<br>Zero sugar.</p>
            </section>
        """
        drink = parse_drink(html, f"{BASE_URL}/en-gb/energy-drinks/monster-ultra/strawberry/")

        assert drink.name == "Zero- Sugar Ultra Strawberry Dreams"
        assert drink.flavor == "Strawberry"
        assert drink.description == "Light and crisp. Zero sugar."

    def test_raises_on_non_product_page(self, fixture_html):
        with pytest.raises(ParseError, match="No product found") as info:
            parse_drink(fixture_html("listing_en-gb.html"), EN_GB_MANGO)
        assert not isinstance(info.value, EmptyProductError)

    def test_raises_empty_product_error_on_blank_template(self):
        html = '<section class="product-main"><h1 class="product-name"> </h1></section>'

        with pytest.raises(EmptyProductError):
            parse_drink(html, EN_GB_MANGO)
