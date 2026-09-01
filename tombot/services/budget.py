"""A hard ceiling on requests to a metered API.

The tcggo plan allows 100 requests a day and bills the card for every request
beyond that. So this is not a politeness limiter that can be tuned later: going
over costs real money, and a loop over 1,104 cards would do it in seconds.

Three decisions follow from that:

* The count is **persisted**. An in-memory counter resets on every restart, and
  a container that restarts four times would quietly spend four times the cap.
* A request is **reserved before it is sent**, not counted after. If the process
  dies mid-flight the reservation still stands: over-counting wastes a request,
  under-counting spends money.
* The default cap sits **below** the real plan limit, so an off-by-one, a retry
  or a clock-skewed day boundary lands in the headroom rather than on the bill.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

log = logging.getLogger(__name__)


class BudgetExhausted(RuntimeError):
    """Raised instead of sending a request that would exceed the daily cap."""

    def __init__(self, provider: str, used: int, limit: int):
        self.provider, self.used, self.limit = provider, used, limit
        super().__init__(
            f"{provider}: daily request budget spent ({used}/{limit}). "
            f"It resets at 00:00 UTC; nothing was sent."
        )


def _today() -> str:
    # UTC, so the boundary does not move with the host's timezone.
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class RequestBudget:
    def __init__(self, repo, provider: str, limit: int, per_minute: int = 0,
                 sleep=time.sleep):
        self.repo = repo
        self.provider = provider
        self.limit = max(0, int(limit))
        # A second, softer cap: the plan also limits requests per minute. Unlike
        # the daily cap (money), going over this only earns a 429, so a burst
        # waits for a slot rather than failing.
        self.per_minute = max(0, int(per_minute))
        self._sleep = sleep          # injectable so tests don't actually wait

    def used(self, day: str | None = None) -> int:
        """Requests spent in the last 24 hours, not since midnight.

        The window rolls because the plan's own reset is not visible to us —
        RapidAPI reports usage as "Aug 27 - Aug 28", anchored to the
        subscription rather than to midnight. A calendar-day counter would
        permit the full cap twice across that boundary.
        """
        return self.repo.budget_used_in_window(self.provider)

    def remaining(self) -> int:
        return max(0, self.limit - self.used())

    def reserve(self, n: int = 1) -> int:
        """Claim n requests up front, or raise without sending anything.

        The check and the increment happen in one transaction so two threads
        cannot both see the last slot as free.
        """
        if n <= 0:
            return self.used()
        # Per-minute throttle first: wait (don't fail) for a slot to free. The
        # 60s window guarantees this returns — a slot cannot take longer to age
        # out — so there is no unbounded hang. Runs outside any transaction.
        if self.per_minute:
            for _ in range(120):          # safety stop; each wait is <= ~60s
                wait = self.repo.minute_window_wait(self.provider, self.per_minute, n)
                if wait <= 0:
                    break
                log.info("%s: per-minute cap reached, waiting %.1fs", self.provider, wait)
                self._sleep(min(wait, 5.0))
        used = self.repo.budget_reserve_window(self.provider, n, self.limit)
        if used is None:
            raise BudgetExhausted(self.provider, self.used(), self.limit)
        if self.limit and used >= self.limit * 0.8:
            log.warning("%s: %d of %d daily requests used", self.provider,
                        used, self.limit)
        return used

    def can_afford(self, n: int) -> bool:
        return self.remaining() >= n
