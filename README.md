# TomBot — Pokémon card collection tracker

Self-hosted, single-user web app to track a Pokémon card collection: which cards
you own, which you still need to complete a set, and what the collection is worth.

- **Backend:** Flask + SQLite (`tombot/`). Catalogue, images, Cardmarket printings
  and prices all come from **tcggo**, one set at a time, from Mantenimiento → Sets.
- **Frontend:** React + TypeScript + Tailwind CSS (`frontend/`), built with Vite
  and served by Flask.

`CLAUDE.md` is the detailed guide: architecture, data model, conventions.

## Run it with Docker (the normal way)

```
cp .env.example .env        # set TCGGO_API_KEY
docker compose up -d --build
```

Open <http://localhost:8090>. The image builds the frontend itself, so the host
needs neither Node nor Python. `make docker` does the same and stamps the commit
into the image; `make docker-logs`, `make docker-stop`, `make docker-shell` do
what they say.

After pulling new code: `docker compose up -d --build` again. The page itself is
never cached, so a reload picks up the new UI.

## Run it locally

Needs Python 3.12 and **Node 22**.

```
make install      # virtualenv + Python dependencies
make run          # builds the frontend if needed, serves on http://127.0.0.1:8080
```

| Command         | What it does                                                                         |
| --------------- | ------------------------------------------------------------------------------------ |
| `make run`      | Build the frontend when its sources changed, then serve on :8080 (gunicorn).          |
| `make dev`      | Flask debug server on :8080 **and** rebuild the frontend on every save. Reload to see a change. |
| `make dev-ui`   | Vite dev server on :5173 with hot reload. Needs `make dev` or `make run` for the API. |
| `make frontend` | Only build `frontend/dist`.                                                          |
| `make lint`     | Typecheck + ESLint + Prettier check on the frontend.                                 |
| `make test`     | The Python test suite.                                                               |

Starting Flask by hand (`flask run`, `waitress-serve app:app`) does **not** build
the frontend. Without a build, `/` answers 503 and tells you to run `make frontend`.

Run **one** instance against one database and one tcggo key: the key is metered,
and several instances overspend it.

## Working on the UI

```
frontend/src/
  api/          typed API client, response types, cache keys
  components/   shared building blocks: ui/, cards/, sets/, layout/, charts/
  context/      toast, API vocabularies, the card modal
  features/     one folder per page (dashboard, sets, collection, missing,
                maintenance, card-modal)
  hooks/  lib/  index.css (Tailwind + design tokens)
```

1. `make dev` (or `make dev-ui` for hot reload) and edit under `frontend/src`.
2. Reach for an existing component in `components/` before writing new markup.
3. `make lint` before pushing — CI fails on type errors, lint errors and
   unformatted code. `cd frontend && npm run format` fixes formatting.

Routes are hash-based (`#/sets`, `#/set/<id>`, `#/cartas?…`), so bookmarks and the
installed iOS home-screen app survive UI changes.

## Scheduled jobs and CLI

```
flask init-db     # create the schema (idempotent; the container runs it on start)
flask prices      # re-price the collection from imported products (no network)
flask snapshot    # write a snapshot for the history chart
flask monthly     # prices + snapshot
flask scheduler   # run that on a schedule (the `scheduler` container)
```

## CI

Every pull request runs three jobs: the Python tests, the frontend checks and
build, and a Docker image build that boots the container. See
`.github/workflows/README.md`.
