#!/usr/bin/env bash
# Parse the front-end the way the browser does.
#
# `node --check file.js` validates as CommonJS, and the CommonJS wrapper
# supplies a closing brace — so a function missing its own `}` passes here and
# fails in the browser with "Unexpected end of input" at the last line. Copying
# to .mjs forces module parsing, which is what the app actually uses.
set -euo pipefail
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
status=0
for f in static/js/*.js; do
    cp "$f" "$tmp/$(basename "${f%.js}").mjs"
    if node --check "$tmp/$(basename "${f%.js}").mjs" 2>/dev/null; then
        echo "  ok      $f"
    else
        echo "  BROKEN  $f"
        node --check "$tmp/$(basename "${f%.js}").mjs" 2>&1 | head -3 | sed 's/^/          /'
        status=1
    fi
done
exit $status
