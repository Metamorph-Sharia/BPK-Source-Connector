"""Is ingestion healthy? For schedulers and uptime checks (``bpk-connector health``)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from bpk_connector.domain.alerts import Severity


class Health(Enum):
    OK = 0
    WARNING = 1
    CRITICAL = 2

    @property
    def exit_code(self) -> int:
        return self.value


@dataclass(frozen=True)
class HealthResult:
    status: Health
    message: str


def check_health(
    last_success: datetime | None,
    last_worst: Severity | None,
    *,
    now: datetime,
    max_hours: float,
) -> HealthResult:
    if last_success is None:
        return HealthResult(Health.CRITICAL, "no successful run yet")
    hours = (now - last_success).total_seconds() / 3600
    if hours > max_hours:
        return HealthResult(Health.CRITICAL, f"last successful run {hours:.0f} hours ago (limit {max_hours:.0f})")
    if last_worst is not None and last_worst >= Severity.ERROR:
        return HealthResult(Health.CRITICAL, f"last run raised a {last_worst} alert")
    if last_worst is Severity.WARNING:
        return HealthResult(Health.WARNING, "last run raised a warning")
    return HealthResult(Health.OK, f"last successful run {hours:.0f} hours ago")
