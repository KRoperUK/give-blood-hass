"""Tests for the numeric, date and attribute-budget safety helpers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from custom_components.nhs_give_blood.const import ATTR_TRUNCATED, MAX_STATE_LENGTH
from custom_components.nhs_give_blood.helpers import (
    limit_attributes,
    safe_datetime,
    safe_number,
    safe_state,
)


class TestSafeNumber:
    """Numeric coercion."""

    @pytest.mark.parametrize(("value", "expected"), [(5, 5), (5.5, 5.5), ("5.5", 5.5), ("-3", -3.0), (0, 0)])
    def test_accepts_numbers_and_numeric_strings(self, value: Any, expected: float) -> None:
        assert safe_number(value) == expected

    @pytest.mark.parametrize("value", [None, "", "abc", [], {}, object()])
    def test_rejects_non_numbers(self, value: Any) -> None:
        assert safe_number(value) is None

    @pytest.mark.parametrize("value", [True, False])
    def test_rejects_booleans(self, value: bool) -> None:
        """``True`` is numerically 1, and reporting 1 would hide a payload change."""
        assert safe_number(value) is None


class TestSafeDatetime:
    """Datetime validation."""

    def test_accepts_an_aware_datetime(self) -> None:
        value = datetime(2026, 10, 8, 17, 30, tzinfo=UTC)
        assert safe_datetime(value) == value

    def test_rejects_a_naive_datetime(self) -> None:
        """A naive value would be read as UTC and silently shift the shown time."""
        assert safe_datetime(datetime(2026, 10, 8, 17, 30)) is None  # noqa: DTZ001

    @pytest.mark.parametrize("value", [None, "2026-10-08T17:30:00", 1234567890, []])
    def test_rejects_non_datetimes(self, value: Any) -> None:
        assert safe_datetime(value) is None


class TestSafeState:
    """State coercion within Home Assistant's 255-character limit."""

    def test_passes_short_strings_through(self) -> None:
        assert safe_state("A-") == "A-"

    def test_strips_whitespace(self) -> None:
        assert safe_state("  A-  ") == "A-"

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_empty_values_become_none(self, value: Any) -> None:
        assert safe_state(value) is None

    def test_coerces_non_strings(self) -> None:
        assert safe_state(15) == "15"

    def test_truncates_rather_than_dropping(self) -> None:
        """A clipped venue name is more useful than `unknown`."""
        result = safe_state("x" * 400)
        assert result is not None
        assert len(result) == MAX_STATE_LENGTH
        assert result.endswith("…")


class TestLimitAttributes:
    """The recorder discards the whole attribute blob above 16,384 bytes."""

    @staticmethod
    def _size(payload: dict[str, Any]) -> int:
        return len(json.dumps(payload, default=str).encode())

    def test_small_payloads_pass_through_untouched(self) -> None:
        payload = {"venue": "Hall", "items": [1, 2, 3]}
        assert limit_attributes(payload, shrinkable=("items",)) == payload

    def test_no_truncation_flag_when_nothing_was_removed(self) -> None:
        assert ATTR_TRUNCATED not in limit_attributes({"a": 1})

    def test_halves_a_shrinkable_list_until_it_fits(self) -> None:
        payload = {"items": [{"text": "x" * 100} for _ in range(500)]}
        result = limit_attributes(payload, shrinkable=("items",), budget=2000)

        assert self._size(result) <= 2000
        assert 0 < len(result["items"]) < 500
        assert result[ATTR_TRUNCATED] is True

    def test_shrinks_the_largest_list_first(self) -> None:
        payload = {
            "small": [{"v": "x" * 10} for _ in range(5)],
            "large": [{"v": "x" * 100} for _ in range(200)],
        }
        result = limit_attributes(payload, shrinkable=("small", "large"), budget=3000)

        assert len(result.get("large", [])) < 200
        assert len(result["small"]) == 5, "the small list did not need touching"

    def test_scalars_survive_truncation(self) -> None:
        """Losing a long list is recoverable; losing every attribute is not."""
        payload = {
            "venue": "Example Donor Centre",
            "procedure": "Platelet",
            "items": [{"v": "x" * 100} for _ in range(500)],
        }
        result = limit_attributes(payload, shrinkable=("items",), budget=1000)

        assert result["venue"] == "Example Donor Centre"
        assert result["procedure"] == "Platelet"
        assert self._size(result) <= 1000

    def test_drops_structured_values_when_nothing_is_shrinkable(self) -> None:
        """Better to shed one key than have the recorder discard the lot."""
        payload = {"scalar": "keep", "blob": {"text": "x" * 5000}}
        result = limit_attributes(payload, shrinkable=(), budget=500)

        assert result["scalar"] == "keep"
        assert "blob" not in result
        assert result[ATTR_TRUNCATED] is True

    def test_an_empty_shrinkable_list_is_not_an_infinite_loop(self) -> None:
        payload = {"items": [], "blob": "x" * 5000}
        result = limit_attributes(payload, shrinkable=("items",), budget=500)

        assert isinstance(result, dict)

    def test_result_is_always_serialisable(self) -> None:
        payload = {"when": datetime(2026, 10, 8, tzinfo=UTC), "items": list(range(5000))}
        result = limit_attributes(payload, shrinkable=("items",), budget=1000)

        json.dumps(result, default=str)

    def test_the_default_budget_leaves_recorder_headroom(self) -> None:
        """Home Assistant adds its own keys after this runs."""
        from custom_components.nhs_give_blood.const import ATTRIBUTE_BYTE_BUDGET

        assert ATTRIBUTE_BYTE_BUDGET < 16384
