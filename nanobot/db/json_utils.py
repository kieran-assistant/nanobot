"""
Module Purpose: Centralized JSON/JSONB type normalization for database operations.

Responsibilities:
    - Provide a single source of truth for handling asyncpg's variable JSONB return types
    - Normalize JSONB data consistently across all database query sites
    - Prevent duplicate JSON decoding logic throughout the codebase

Dependencies:
    - json (standard library)
    - typing.Any (type hints)

Why this module exists:
    asyncpg sometimes returns JSONB columns as Python dicts, sometimes as JSON strings.
    Without this utility, every DB query site would need its own decoding logic,
    leading to inconsistency and potential bugs.
"""

from __future__ import annotations

import json
from typing import Any


# ---------- Public API ----------


def decode_jsonb(value: Any) -> Any:
    """
    Decode potential JSONB payloads returned as strings into Python objects.

    This function handles the variance in asyncpg's JSONB type handling:
    - If already a dict/list: return as-is (already decoded)
    - If a JSON string: attempt to parse into Python object
    - If parsing fails: return original string (graceful degradation)
    - If any other type: return as-is (unknown type handling)

    Args:
        value: Any - The JSONB value from database query

    Returns:
        Any - Decoded Python object (dict/list) or original value if undecodable
    """

    # Fast path: value is already a Python object (asyncpg auto-decoded)
    if isinstance(value, (dict, list)):
        return value

    # JSON string path: try to parse into Python object
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            # Parsing failed - return original string to avoid crashing
            return value

    # Unknown type path: return as-is (number, None, bool, etc.)
    return value
