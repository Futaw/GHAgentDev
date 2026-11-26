"""Allowlisted failure classifications; never expose provider messages or details."""

import re


def classify_turn_error(error: object) -> str:
    message = error.get("message") if isinstance(error, dict) else None
    if isinstance(message, str) and (
        re.search(r"\binvalid_json_schema\b", message, re.IGNORECASE)
        or "invalid schema for response_format" in message.lower()
    ):
        return "invalid_output_schema"
    return "turn_failed"
