"""How many error reports a home sends, so one looping error can't use up the month's quota."""

from __future__ import annotations

HOUR = 3600
DAY = 24 * HOUR

# Enough to see a problem and how often it comes back
PER_ERROR_PER_DAY = 5
PER_HOME_PER_HOUR = 20
PER_HOME_PER_DAY = 50


class ErrorLimit:
    """Counted in memory, so a restart starts over."""

    def __init__(self) -> None:
        self._day_started = 0.0
        self._hour_started = 0.0
        self._today = 0
        self._this_hour = 0
        self._by_error: dict[str, int] = {}

    def _roll(self, now: float) -> None:
        if now - self._day_started >= DAY:
            self._day_started = now
            self._today = 0
            self._by_error = {}
        if now - self._hour_started >= HOUR:
            self._hour_started = now
            self._this_hour = 0

    def spent(self, now: float) -> bool:
        """Whether the home has none left, before any work goes into reading a report."""
        self._roll(now)
        return self._today >= PER_HOME_PER_DAY or self._this_hour >= PER_HOME_PER_HOUR

    def take(self, error: str, now: float) -> bool:
        """Whether this report can go, counting it if so."""
        if self.spent(now) or self._by_error.get(error, 0) >= PER_ERROR_PER_DAY:
            return False
        self._by_error[error] = self._by_error.get(error, 0) + 1
        self._today += 1
        self._this_hour += 1
        return True
