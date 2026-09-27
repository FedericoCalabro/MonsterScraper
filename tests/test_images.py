from io import BytesIO

import pytest
from PIL import Image

from monster_scraper.images import to_png


def make_image(width: int, height: int, *, mode: str = "RGBA", fmt: str = "PNG") -> bytes:
    buffer = BytesIO()
    Image.new(mode, (width, height), "green").save(buffer, format=fmt)
    return buffer.getvalue()


def open_png(data: bytes) -> Image.Image:
    image = Image.open(BytesIO(data))
    assert image.format == "PNG"
    return image


def test_downscales_to_max_width_keeping_aspect_ratio():
    image = open_png(to_png(make_image(800, 2000), max_width=200))

    assert image.size == (200, 500)
    assert image.mode == "RGBA"


@pytest.mark.parametrize("max_width", [None, 1000])
def test_never_upscales(max_width):
    image = open_png(to_png(make_image(300, 600), max_width=max_width))

    assert image.size == (300, 600)


def test_converts_other_formats_to_png():
    image = open_png(to_png(make_image(100, 100, mode="CMYK", fmt="JPEG")))

    assert image.size == (100, 100)
    assert image.mode == "RGBA"
