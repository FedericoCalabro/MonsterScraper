"""Image post-processing."""

from __future__ import annotations

from io import BytesIO

from PIL import Image

_PNG_MODES = frozenset({"1", "L", "LA", "P", "RGB", "RGBA"})


def to_png(data: bytes, max_width: int | None = None) -> bytes:
    """Re-encode an image as an optimised PNG, downscaling it to ``max_width`` if wider.

    The aspect ratio is preserved and images are never upscaled.
    """
    with Image.open(BytesIO(data)) as source:
        image = source if source.mode in _PNG_MODES else source.convert("RGBA")
        if max_width is not None and image.width > max_width:
            height = max(1, round(image.height * max_width / image.width))
            image = image.resize((max_width, height), Image.Resampling.LANCZOS)

        buffer = BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()
