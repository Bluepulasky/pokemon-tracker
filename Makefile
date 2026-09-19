.PHONY: help venv install frontend run dev dev-ui lint test prices snapshot monthly \
        docker docker-app docker-logs docker-stop docker-shell \
        docker-initdb docker-prices \
        docker-demo docker-demo-clear bundle clean

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-14s %s\n", $$1, $$2}'

venv:            ## Create the virtualenv
	python3 -m venv .venv && .venv/bin/pip install -q --upgrade pip

install: venv    ## Install dependencies
	.venv/bin/pip install -r requirements.txt

# The React app (frontend/) compiles to frontend/dist, which Flask serves. Both
# rules are keyed on files, so `make run` rebuilds only when a source changed.
FRONTEND_SRC := $(shell find frontend/src frontend/public frontend/index.html \
                  frontend/vite.config.ts -type f 2>/dev/null)
NPM_STAMP := frontend/node_modules/.package-lock.json

$(NPM_STAMP): frontend/package.json frontend/package-lock.json
	cd frontend && npm ci
	@touch $@

frontend/dist/index.html: $(NPM_STAMP) $(FRONTEND_SRC)
	cd frontend && npm run build

frontend: frontend/dist/index.html ## Build the React app into frontend/dist

run: frontend    ## Serve on :8080 (gunicorn — same server the container uses)
	.venv/bin/gunicorn -w 2 --threads 4 -b 127.0.0.1:8080 --timeout 120 app:app

# Same URL as always (:8080). The frontend is rebuilt on every save; reload the
# page to see it. Ctrl-C stops both processes.
dev: frontend    ## Flask dev server + frontend rebuild-on-save, on :8080
	@trap 'kill 0' INT TERM EXIT; \
	(cd frontend && npm run watch) & \
	FLASK_APP=app.py FLASK_DEBUG=1 .venv/bin/flask run --port 8080

dev-ui: $(NPM_STAMP) ## Vite dev server with hot reload on :5173 (needs `make dev` or `make run` for the API)
	cd frontend && npm run dev

lint: $(NPM_STAMP) ## Typecheck, lint and format-check the frontend
	cd frontend && npm run check

test:            ## Run the test suite
	.venv/bin/python -m pytest tests/ -q

prices:          ## Refresh prices for cards in the collection
	FLASK_APP=app.py .venv/bin/flask prices

snapshot:        ## Write a collection snapshot
	FLASK_APP=app.py .venv/bin/flask snapshot

monthly:         ## prices + snapshot — what cron should call
	FLASK_APP=app.py .venv/bin/flask monthly

docker:          ## Build and start (app + scheduler), stamping the commit
	APP_VERSION=$$(git rev-parse --short HEAD 2>/dev/null || echo unknown) \
		docker compose up -d --build

docker-app:      ## Start only the web app, no scheduler
	docker compose up -d --build app

docker-logs:     ## Follow container logs
	docker compose logs -f

docker-stop:     ## Stop the containers
	docker compose down

# `docker compose exec` bypasses the entrypoint, so it would land as root and
# leave root-owned WAL files next to the database. Pass the same uid the server
# runs as.
DOCKER_EXEC = docker compose exec --user $$(id -u):$$(id -g)

docker-shell:    ## Shell inside the running container
	$(DOCKER_EXEC) app bash

docker-initdb:   ## Create/upgrade the schema only
	$(DOCKER_EXEC) app flask init-db

docker-prices:   ## Run a price refresh inside the container
	$(DOCKER_EXEC) app flask prices

docker-demo:     ## Fill the collection with sample cards to try the UI
	$(DOCKER_EXEC) app python scripts/demo_seed.py

docker-demo-clear: ## Remove ALL collection items/photos (keeps catalog + sets)
	$(DOCKER_EXEC) app python scripts/demo_seed.py --clear

bundle:          ## Produce dist/*.bundle for handover
	./scripts/make-bundle.sh

clean:
	rm -rf .venv dist __pycache__ .pytest_cache frontend/node_modules frontend/dist
	find . -name '__pycache__' -type d -exec rm -rf {} +
