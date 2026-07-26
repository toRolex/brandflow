"""Shared pagination models for list endpoints.

Follow the contract defined in issue #354::

    {
      "items": [...],
      "total": <pre-slice count>,
      "page": <requested page>,
      "page_size": <requested page_size>
    }
"""

from __future__ import annotations

from typing import Any


def paginated(
    items: list[Any],
    total: int,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    """Build a paginated response dict.

    Returns the standard pagination envelope without Pydantic wrapping
    — items are already plain dicts so double-serialization is avoided.
    """
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def slice_indices(
    total: int,
    page: int,
    page_size: int,
) -> tuple[int, int]:
    """Return ``(start, end)`` slice indices for a given page.

    *end* is exclusive.  When *page* is beyond the last page the returned
    range is empty (start == end >= total).
    """
    start = (page - 1) * page_size
    if start >= total:
        return total, total
    return start, min(start + page_size, total)
