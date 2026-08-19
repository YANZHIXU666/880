from __future__ import annotations

import base64
import zlib
from collections.abc import Iterable


def encode_seen(question_ids: Iterable[str], universe: Iterable[str]) -> str:
    ordered = sorted(set(universe))
    seen = set(question_ids)
    payload = bytearray((len(ordered) + 7) // 8)
    for index, question_id in enumerate(ordered):
        if question_id in seen:
            payload[index // 8] |= 1 << (index % 8)
    compressed = zlib.compress(bytes(payload), level=9)
    return base64.urlsafe_b64encode(compressed).decode("ascii").rstrip("=")


def decode_seen(token: str, universe: Iterable[str]) -> set[str]:
    ordered = sorted(set(universe))
    if not token:
        return set()
    try:
        padded = token + "=" * (-len(token) % 4)
        payload = zlib.decompress(base64.urlsafe_b64decode(padded))
    except (ValueError, zlib.error):
        return set()
    return {
        question_id
        for index, question_id in enumerate(ordered)
        if index // 8 < len(payload) and payload[index // 8] & (1 << (index % 8))
    }
