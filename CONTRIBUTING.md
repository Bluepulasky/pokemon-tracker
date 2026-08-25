# Working on this codebase

## Rules that are not negotiable

1. **All SQL lives in `PokemonRepo`.** Route handlers and services call the repo and get
   dicts back. This is spec §22/§31 and the reason the data layer is testable.
2. **External data never overwrites user data.** The importer touches `official_sets` and
   `cards` only. Personal sets, collection items and photos are the user's.
3. **Completion is counted over slots, not cards.** If you write a query that counts
   `collection_items` to measure progress, it is wrong — see `PLAN.md` §2.1.
4. **"No price" is not "€0".** Unpriced things return `None` and render as `—`.

## Setup

```bash
make install
make bootstrap
make test
```

## Adding a price/catalog source

Implement the three methods in `tombot/services/sources/base.py` and register it in
`sources/__init__.py`. The importer and pricing service talk only to that interface.
`TCGdex` is the obvious next one — it carries Spanish card names, which the current
source does not.

## Schema changes

Edit `tombot/services/schema.sql`, bump `SCHEMA_VERSION` in `repository.py`, and add a
migration path. Every statement is `IF NOT EXISTS`, so `init-db` is safe to re-run, but
it will not alter existing columns.

## Tests

`tests/test_completion.py` pins the semantics that are easy to break. If you change how
slots, variants or quantities interact, that file should fail before you change it.
