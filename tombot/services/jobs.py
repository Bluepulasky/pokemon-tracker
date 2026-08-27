"""Background jobs triggered from the UI.

The maintenance actions — refreshing prices, rebuilding the catalog — take
minutes and talk to a flaky upstream. Running them inside a request would hold a
worker open long past any sensible timeout, so they run on a thread and the page
polls for the result.

One at a time, deliberately: two concurrent catalog rebuilds would race on the
same rows for no benefit.

The runner owns the application context. A worker thread starts with none, so
anything reaching for `current_app` — which is every service lookup — fails
immediately unless the context is pushed here. Leaving that to each caller is
how it broke: the route looked correct because it named `current_app`, but the
name resolved on the thread, where it is unbound.
"""
from __future__ import annotations

import logging
import threading
import traceback
from contextlib import nullcontext
from datetime import datetime, timezone

log = logging.getLogger(__name__)


class JobRunner:
    def __init__(self, app=None):
        self._app = app
        self._warn_if_multiprocess()
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
            ctx = self._app.app_context() if self._app is not None else nullcontext()
            try:
                with ctx:
                    try:
                        result = fn()
                        self._finish(status="done", result=result)
                    finally:
                        self._release_connection()
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

    def _release_connection(self) -> None:
        """Hand back this thread's SQLite connection.

        Connections are thread-local, so a job thread opens its own and would
        otherwise keep it — and its WAL read mark — alive until the process
        exits. Rare work, but the leak is unbounded across restarts.
        """
        if self._app is None:
            return
        try:
            self._app.extensions["repo"].close()
        except Exception:                                # noqa: BLE001
            log.warning("could not close the job connection", exc_info=True)

    @staticmethod
    def _warn_if_multiprocess() -> None:
        """Say so if this state is about to be split across processes.

        The status this runner reports, and its one-job-at-a-time rule, live in
        the memory of whichever process started the job. Run two workers and
        the other one answers "idle" to half the polls and starts a second job
        happily — which, with a metered price source, is billable.
        """
        import os

        workers = os.environ.get("WEB_CONCURRENCY")
        try:
            if workers and int(workers) > 1:
                log.warning(
                    "WEB_CONCURRENCY=%s: job status is per-process, so polls "
                    "will disagree and two maintenance jobs can run at once. "
                    "Use 1 worker and raise WEB_THREADS instead.", workers)
        except ValueError:
            pass
