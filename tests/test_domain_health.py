"""Health for schedulers and uptime checks: exit 0 ok, 1 warning, 2 critical."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from bpk_connector.domain.alerts import Severity
from bpk_connector.domain.health import Health, check_health

NOW = datetime(2026, 10, 14, 6, 0, tzinfo=UTC)


def test_a_recent_clean_run_is_healthy() -> None:
    assert check_health(NOW - timedelta(hours=20), Severity.INFO, now=NOW, max_hours=36).status is Health.OK


def test_no_successful_run_within_the_limit_is_critical() -> None:
    result = check_health(NOW - timedelta(hours=40), None, now=NOW, max_hours=36)

    assert result.status is Health.CRITICAL and "40" in result.message


def test_never_run_is_critical() -> None:
    assert check_health(None, None, now=NOW, max_hours=36).status is Health.CRITICAL


def test_the_last_runs_worst_alert_sets_the_status() -> None:
    recent = NOW - timedelta(hours=1)

    assert check_health(recent, Severity.WARNING, now=NOW, max_hours=36).status is Health.WARNING
    assert check_health(recent, Severity.ERROR, now=NOW, max_hours=36).status is Health.CRITICAL
    assert Health.CRITICAL.exit_code == 2


def test_a_machine_missing_required_tools_is_critical_whatever_the_last_run_did() -> None:
    result = check_health(
        NOW - timedelta(hours=1),
        None,
        now=NOW,
        max_hours=36,
        environment_problems=["Tesseract has no 'ind' language data"],
    )

    assert result.status is Health.CRITICAL and "ind" in result.message
