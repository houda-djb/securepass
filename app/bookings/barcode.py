"""A simple decorative barcode drawn from the booking reference (no real scanner format)."""
import hashlib


def bars(reference: str) -> list[tuple[int, int]]:
    """(x, width) pairs for the black bars. The same reference always gives the same bars."""
    digest = hashlib.sha256(reference.encode()).digest()
    result, x = [], 0
    for byte in digest[:24]:
        width = 1 + byte % 3
        if byte & 0x80:
            result.append((x, width))
        x += width + 1 + (byte >> 5) % 2
    return result


def total_width(items: list[tuple[int, int]]) -> int:
    return max((x + w for x, w in items), default=1)
