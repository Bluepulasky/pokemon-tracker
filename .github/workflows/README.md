# CI

Two jobs, both on every pull request and every push to `main`.

## `tests`

1. **Import the application.** Every test drives `PokemonRepo` directly, so
   nothing imported the API layer — a syntax error in `tombot/api/catalog.py`
   once passed the entire suite. This imports the app the way gunicorn does.
2. **Run the suite with a coverage floor.** The floor is the level coverage is
   already at, not a target: it stops coverage sliding backwards and should be
   raised as gaps close.

The suite is hermetic — no network, no clock, no shared fixtures — so a failure
is a real regression rather than a flake.

## `image`

Covers the deployment surface the tests cannot reach:

- the image builds
- every CLI command registers (a command that fails to import is invisible to
  pytest, and the container's entrypoint calls several of them)
- `scripts/entrypoint.sh` is executable — losing that bit breaks every container
  and nothing else would notice
- the container boots and `/api/healthz` reports `ok: true`

The health check asserts on the **payload**, not the status code. A booting
container answers 200 well before the schema exists.

## Raising the coverage floor

`--cov-fail-under` lives in `ci.yml`. Current gaps, worst first: `tombot/api/*`
and `tombot/cli/__init__.py` are near zero, `pricing.py` and `setbuilder.py` are
low. Those are where regressions have actually happened.
