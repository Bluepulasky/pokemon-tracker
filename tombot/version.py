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


def _from_git_files() -> str | None:
    """Read the commit straight out of .git, without needing the git binary.

    The container has no git installed, and shelling out would not help anyway.
    Reading the files works wherever the metadata is present, which is what makes
    the stamp appear without anyone remembering to pass a build argument.
    """
    head = _ROOT / ".git" / "HEAD"
    if not head.exists():
        return None
    try:
        ref = head.read_text().strip()
        if not ref.startswith("ref: "):
            return ref[:7]                      # detached HEAD holds the sha itself
        name = ref[5:]

        loose = _ROOT / ".git" / name
        if loose.exists():
            return loose.read_text().strip()[:7]

        # A repository that has been packed keeps its refs in one file instead.
        packed = _ROOT / ".git" / "packed-refs"
        if packed.exists():
            for line in packed.read_text().splitlines():
                if line.startswith("#") or " " not in line:
                    continue
                sha, _, refname = line.partition(" ")
                if refname.strip() == name:
                    return sha[:7]
    except OSError:
        return None
    return None


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
    # "unknown" is a placeholder, not a version. Accepting it would shadow the
    # mounted .git and report nothing useful -- which is exactly what happened
    # when the Dockerfile defaulted the build argument to that string.
    baked = (os.environ.get("APP_VERSION") or "").strip()
    if baked and baked != "unknown":
        return baked
    if _git_cache is ...:
        # The binary first (it can report a dirty tree), then the files, which
        # are all the container has.
        _git_cache = _from_git() or _from_git_files()
    return _git_cache or "unknown"
