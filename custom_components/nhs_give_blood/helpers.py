"""Shared safety helpers.

Three hazards get handled here rather than at every call site:

* **The recorder's attribute limit.** Home Assistant silently drops an entity's
  entire attribute dict when the serialised JSON exceeds 16,384 bytes. Nothing is
  logged and the entity looks healthy in memory — the attributes are just gone
  after a restart.
* **The 255-character state limit.** A state longer than that is rejected. Venue
  names and message titles are the realistic offenders.
* **Missing or malformed upstream values.** Every field in this API is optional in
  practice, so numeric and date accessors must degrade to ``None`` rather than
  raise inside a property that Home Assistant calls on every state write.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from .const import ATTR_TRUNCATED, ATTRIBUTE_BYTE_BUDGET, MAX_STATE_LENGTH

_LOGGER = logging.getLogger(__name__)


def safe_number(value: Any) -> float | int | None:
    """Return ``value`` as a number, or ``None`` if it isn't one.

    Booleans are rejected: ``True`` is numerically 1 in Python, but a boolean
    arriving where a measurement is expected means the payload changed shape, and
    reporting 1 would hide that.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value)
    except TypeError, ValueError:
        return None


def safe_datetime(value: Any) -> datetime | None:
    """Return ``value`` if it is a timezone-aware datetime, else ``None``.

    A naive datetime reaching a ``timestamp`` sensor would be interpreted as UTC
    and silently shift the displayed time, so it is rejected rather than guessed
    at. The library already localises everything it returns.
    """
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        _LOGGER.debug("Discarding naive datetime %s; expected an aware value", value)
        return None
    return value


def safe_state(value: Any) -> str | None:
    """Coerce a value to a state string within Home Assistant's length limit."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) <= MAX_STATE_LENGTH:
        return text
    # Truncate rather than drop: a clipped venue name is still useful, whereas
    # `unknown` tells the user nothing.
    return text[: MAX_STATE_LENGTH - 1] + "…"


def _byte_size(payload: Mapping[str, Any]) -> int:
    """Serialised size of an attribute mapping, as the recorder measures it."""
    try:
        return len(json.dumps(payload, default=str).encode())
    except TypeError, ValueError:  # pragma: no cover - default=str handles most
        return ATTRIBUTE_BYTE_BUDGET + 1


def limit_attributes(
    attributes: dict[str, Any],
    *,
    shrinkable: tuple[str, ...] = (),
    budget: int = ATTRIBUTE_BYTE_BUDGET,
) -> dict[str, Any]:
    """Return ``attributes`` trimmed to fit the recorder's attribute limit.

    List-valued keys named in ``shrinkable`` are halved repeatedly, largest
    first, until the payload fits. If that isn't enough they are dropped
    entirely. An :data:`ATTR_TRUNCATED` flag is added whenever anything was
    removed, so a dashboard can say so rather than quietly showing a short list.

    Preferring truncation over dropping the whole dict is deliberate: losing one
    long list is recoverable, losing every attribute on the entity is not.
    """
    if _byte_size(attributes) <= budget:
        return attributes

    result = dict(attributes)
    truncated = False

    while _byte_size(result) > budget:
        candidates = [key for key in shrinkable if isinstance(result.get(key), list) and result[key]]
        if not candidates:
            break
        largest = max(candidates, key=lambda key: len(result[key]))
        items: list[Any] = result[largest]
        keep = len(items) // 2
        result[largest] = items[:keep]
        truncated = True
        if keep == 0:
            del result[largest]

    if _byte_size(result) > budget:
        # Nothing shrinkable left and still over budget: shed the non-scalars
        # rather than let the recorder discard the lot.
        for key in list(result):
            if isinstance(result[key], (list, dict)):
                del result[key]
                truncated = True
            if _byte_size(result) <= budget:
                break
        _LOGGER.debug("Attribute payload exceeded %s bytes; dropped structured values", budget)

    if truncated:
        result[ATTR_TRUNCATED] = True
    return result
