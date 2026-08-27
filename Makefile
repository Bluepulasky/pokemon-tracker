.PHONY: help venv install bootstrap run dev test links prices snapshot monthly \
        docker docker-app docker-logs docker-stop docker-shell \
        docker-bootstrap docker-initdb docker-sets docker-prices docker-links \
        docker-demo docker-demo-clear bundle clean

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-14s %s\n", $$1, $$2}'

venv:            ## Create the virtualenv
	python3 -m venv .venv && .venv/bin/pip install -q --upgrade pip

install: venv    ## Install dependencies
	.venv/bin/pip install -r requirements.txt

bootstrap:       ## init-db + import catalog + seed personal sets (first run)
	FLASK_APP=app.py .venv/bin/flask bootstrap

run:             ## Serve on :8080 (gunicorn — same server the container uses)
	.venv/bin/gunicorn -w 2 --threads 4 -b 127.0.0.1:8080 --timeout 120 app:app

dev:             ## Flask dev server with auto-reload (single-process; use for debugging only)
	FLASK_APP=app.py FLASK_DEBUG=1 .venv/bin/flask run --port 8080

test:            ## Run the test suite
	.venv/bin/python -m pytest tests/ -q

links:           ## Resolve Cardmarket product URLs (resumable)
	FLASK_APP=app.py .venv/bin/flask resolve-links

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

docker-bootstrap: ## Re-run schema + catalog + sets + links in the container (idempotent)
	$(DOCKER_EXEC) app flask bootstrap

docker-initdb:   ## Create/upgrade the schema only
	$(DOCKER_EXEC) app flask init-db

docker-sets:     ## Rebuild the personal sets from seed_sets.py rules
	$(DOCKER_EXEC) app flask seed-sets

docker-prices:   ## Run a price refresh inside the container
	$(DOCKER_EXEC) app flask prices

docker-links:    ## Resolve Cardmarket links inside the container
	$(DOCKER_EXEC) app flask resolve-links

docker-demo:     ## Fill the collection with sample cards to try the UI
	$(DOCKER_EXEC) app python scripts/demo_seed.py

docker-demo-clear: ## Remove ALL collection items/photos (keeps catalog + sets)
	$(DOCKER_EXEC) app python scripts/demo_seed.py --clear

bundle:          ## Produce dist/*.bundle for handover
	./scripts/make-bundle.sh

clean:
	rm -rf .venv dist __pycache__ .pytest_cache
	find . -name '__pycache__' -type d -exec rm -rf {} +
