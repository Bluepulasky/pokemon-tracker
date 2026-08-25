.PHONY: help venv install bootstrap run test prices snapshot monthly docker bundle clean

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-14s %s\n", $$1, $$2}'

venv:            ## Create the virtualenv
	python3 -m venv .venv && .venv/bin/pip install -q --upgrade pip

install: venv    ## Install dependencies
	.venv/bin/pip install -r requirements.txt

bootstrap:       ## init-db + import catalog + seed personal sets (first run)
	FLASK_APP=app.py .venv/bin/flask bootstrap

run:             ## Start the dev server on :8080
	FLASK_APP=app.py .venv/bin/flask run --port 8080

test:            ## Run the test suite
	.venv/bin/python -m pytest tests/ -q

prices:          ## Refresh prices for cards in the collection
	FLASK_APP=app.py .venv/bin/flask prices

snapshot:        ## Write a collection snapshot
	FLASK_APP=app.py .venv/bin/flask snapshot

monthly:         ## prices + snapshot — what cron should call
	FLASK_APP=app.py .venv/bin/flask monthly

docker:          ## Build and start via docker compose
	docker compose up -d --build

bundle:          ## Produce dist/*.bundle for handover
	./scripts/make-bundle.sh

clean:
	rm -rf .venv dist __pycache__ .pytest_cache
	find . -name '__pycache__' -type d -exec rm -rf {} +
