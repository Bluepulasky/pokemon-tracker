"""Background jobs triggered from the UI.

The maintenance actions — refreshing prices, rebuilding the catalog — take
minutes and talk to a flaky upstream. Running them inside a request would hold a
worker open long past any sensible timeout, so they run on a thread and the page
polls for the result.

One at a time, deliberately: two concurrent catalog rebuilds would race on the
same rows for no benefit.
"""
from __future__ import annotations

import logging
import threading
import traceback
from datetime import datetime, timezone

log = logging.getLogger(__name__)


class JobRunner:
    def __init__(self):
        self._lock = threading.Lock()
        self._state: dict = {"name": None, "status": "idle", "started_at": None,
                             "finished_at": None, "result": None, "error": None}

    def status(self) -> dict:
        with self._lock:
            return dict(self._state)

    def start(self, name: str, fn) -> tuple[bool, dict]:
        """Begin a job unless one is already running. Returns (started, status)."""
        with self._lock:
            if self._state["status"] == "running":
                return False, dict(self._state)
            self._state = {
                "name": name, "status": "running",
                "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "finished_at": None, "result": None, "error": None,
            }

        def run():
            try:
                result = fn()
                self._finish(status="done", result=result)
            except Exception as e:                       # noqa: BLE001
                # A failed job must leave a readable reason rather than sticking
                # on "running" forever.
                log.error("job %s failed: %s\n%s", name, e, traceback.format_exc())
                self._finish(status="failed", error=str(e))

        threading.Thread(target=run, name=f"job-{name}", daemon=True).start()
        return True, self.status()

    def _finish(self, status: str, result=None, error=None) -> None:
        with self._lock:
            self._state.update(
                status=status, result=result, error=error,
                finished_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )
