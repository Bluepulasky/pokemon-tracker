"""What build is running.

Diagnosing a report against a deployed instance means knowing which commit it is
serving. Without that, "it still shows the old price" is ambiguous between a bug
and an image that was never rebuilt.

Resolution order, most to least authoritative:
  1. APP_VERSION baked in at image build time
  2. git, when running from a checkout
  3. "unknown"
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _from_git() -> str | None:
    if not (_ROOT / ".git").exists():
        return None
    try:
        sha = subprocess.run(
            ["git", "-C", str(_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=3,
        )
        if sha.returncode != 0:
            return None
        dirty = subprocess.run(
            ["git", "-C", str(_ROOT), "status", "--porcelain"],
            capture_output=True, text=True, timeout=3,
        )
        suffix = "+dirty" if dirty.stdout.strip() else ""
        return sha.stdout.strip() + suffix
    except (OSError, subprocess.SubprocessError):
        return None


_git_cache: str | None | ellipsis = ...          # ... = not looked up yet


def get_version() -> str:
    """Resolved per call, so the environment is authoritative.

    A module-level constant frozen at import time reports whatever was set when
    the process started importing, which is not always what is running. The git
    lookup is cached because it shells out; the environment read is free.
    """
    global _git_cache
    baked = os.environ.get("APP_VERSION")
    if baked:
        return baked
    if _git_cache is ...:
        _git_cache = _from_git()
    return _git_cache or "unknown"
