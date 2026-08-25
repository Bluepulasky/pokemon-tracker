.PHONY: help venv install bootstrap run dev test links prices snapshot monthly \
        docker docker-app docker-logs docker-stop docker-shell docker-prices bundle clean

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

docker:          ## Build and start (app + scheduler)
	docker compose up -d --build

docker-app:      ## Start only the web app, no scheduler
	docker compose up -d --build app

docker-logs:     ## Follow container logs
	docker compose logs -f

docker-stop:     ## Stop the containers
	docker compose down

docker-shell:    ## Shell inside the running container
	docker compose exec app bash

docker-prices:   ## Run a price refresh inside the container
	docker compose exec app flask prices

bundle:          ## Produce dist/*.bundle for handover
	./scripts/make-bundle.sh

clean:
	rm -rf .venv dist __pycache__ .pytest_cache
	find . -name '__pycache__' -type d -exec rm -rf {} +
