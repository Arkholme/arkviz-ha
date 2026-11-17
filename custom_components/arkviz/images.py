"""What the art for art mode may be: an image of a known kind, small enough to send over the WebSocket, and only so many."""

from __future__ import annotations

import base64
import binascii
import re

# An image comes as base64 in one WebSocket message, and Home Assistant takes messages up to 4 MiB, so this leaves room.
# The browser shrinks each image to fit under 2 MiB before sending it.
MAX_BYTES = 5 * 1024 * 1024 // 2

# A few to choose between, as a frame on a wall changes rarely
MAX_IMAGES = 30

# The kinds kept, and the file extension each is kept with
TYPES = {"image/webp": "webp", "image/jpeg": "jpg", "image/png": "png"}

# Every image's id is made by new_id, so anything else asked for isn't one
ID = re.compile(r"^[0-9a-f]{32}$")


class Refused(Exception):
    """An image that isn't kept, with the code the WebSocket command answers with."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def sniff(data: bytes) -> str | None:
    """The kind of image the bytes are, read from how they start, or None."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def read_image(kind: str, encoded: str) -> bytes:
    """The image's bytes from base64, once they're known to be the kind they say and not too big."""
    if kind not in TYPES:
        raise Refused("not_an_image", "Only JPEG, PNG and WebP images are kept.")
    # Base64 is 4 characters for every 3 bytes, so a long one can be refused before decoding it
    if len(encoded) > (MAX_BYTES + 2) // 3 * 4:
        raise Refused("too_large", "That image is too big to keep.")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as err:
        raise Refused("not_an_image", "That isn't an image.") from err
    if sniff(data) != kind:
        raise Refused("not_an_image", "That isn't an image.")
    return data
