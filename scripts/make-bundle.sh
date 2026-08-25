#!/usr/bin/env bash
# Package the repo for handover as a single git bundle.
#
# A bundle carries the full commit history in one file, so the maintainer gets a
# real repository rather than a snapshot: he clones it, points origin at his own
# remote and pushes. Works over Syncthing, a USB stick, or scp.
set -euo pipefail

cd "$(dirname "$0")/.."
NAME="tombot-pokemon-tracker"
OUT="dist/${NAME}.bundle"

mkdir -p dist

if [[ -n "$(git status --porcelain)" ]]; then
  echo "warning: working tree has uncommitted changes; they will NOT be in the bundle" >&2
  git status --short >&2
fi

git bundle create "$OUT" --all
git bundle verify "$OUT" >/dev/null && echo "bundle verified"

shasum -a 256 "$OUT" | tee "${OUT}.sha256"

cat <<TXT

Created $OUT ($(du -h "$OUT" | cut -f1))

Give the maintainer these two files:
  $OUT
  ${OUT}.sha256

He then runs:
  shasum -a 256 -c ${NAME}.bundle.sha256
  git clone ${NAME}.bundle ${NAME}
  cd ${NAME}
  git remote set-url origin git@github.com:<his-user>/<his-repo>.git
  git push -u origin main
TXT
