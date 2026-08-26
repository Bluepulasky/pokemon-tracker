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


def get_version() -> str:
    return os.environ.get("APP_VERSION") or _from_git() or "unknown"


VERSION = get_version()
