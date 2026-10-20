"""Tests for the domain models: Pydantic should reject bad data loudly."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from incident_intel.domain import LogEvent, LogLevel, MetricName, MetricPoint, Priority

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)


def test_valid_metric_point_is_accepted() -> None:
    point = MetricPoint(timestamp=NOW, service="api-gateway", metric="error_rate", value=0.01)

    assert point.metric == MetricName.ERROR_RATE  # the string was converted to the enum


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        LogEvent(timestamp=NOW, service="x", level=LogLevel.INFO, message="hi", servcie="typo")


def test_timestamps_must_include_a_timezone() -> None:
    naive = datetime(2026, 9, 7, 12, 0)  # no tzinfo: ambiguous, so not allowed

    with pytest.raises(ValidationError):
        MetricPoint(timestamp=naive, service="x", metric=MetricName.CPU_PCT, value=1)


def test_negative_metric_values_are_rejected() -> None:
    with pytest.raises(ValidationError):
        MetricPoint(timestamp=NOW, service="x", metric=MetricName.CPU_PCT, value=-5)


def test_invalid_enum_values_are_rejected() -> None:
    with pytest.raises(ValidationError):
        LogEvent(timestamp=NOW, service="x", level="LOUD", message="hi")


def test_str_enums_compare_equal_to_plain_strings() -> None:
    assert Priority.P1 == "P1"
