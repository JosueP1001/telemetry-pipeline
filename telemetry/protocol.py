"""Wire protocol: newline-delimited JSON messages over TCP."""
from __future__ import annotations

import json
import math

VALID_STATUSES = {"OK", "WARN", "FAULT"}
REQUIRED_FIELDS = {"device_id": str, "seq": int, "ts": (int, float),
                   "temperature_c": (int, float), "status": str}


def encode(message: dict) -> bytes:
    return (json.dumps(message, separators=(",", ":")) + "\n").encode()


def parse(line: bytes) -> dict:
    """Parse one line into a dict. Raises ValueError on bad JSON/shape."""
    try:
        obj = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"unparseable message: {exc}") from exc
    if not isinstance(obj, dict):
        raise ValueError("message must be a JSON object")
    return obj


def validate(msg: dict) -> str | None:
    """Return None if the message is valid, otherwise a short error string."""
    for field, types in REQUIRED_FIELDS.items():
        if field not in msg:
            return f"missing field: {field}"
        value = msg[field]
        if isinstance(value, bool) or not isinstance(value, types):
            return f"wrong type for field: {field}"
    if msg["seq"] < 0:
        return "seq must be non-negative"
    if not math.isfinite(msg["temperature_c"]) or not -90 <= msg["temperature_c"] <= 150:
        return "temperature_c out of range"
    if msg["status"] not in VALID_STATUSES:
        return "invalid status"
    if not msg["device_id"]:
        return "empty device_id"
    return None
