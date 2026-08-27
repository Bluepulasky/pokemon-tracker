# TomBot Pokémon Tracker — single-container image for a home server.
#
# Everything tunable is an environment variable so nothing here has to be edited
# to change a port, a worker count or where the data lives. See .env.example.

FROM python:3.12-slim

# libheif: pillow-heif needs it for iPhone HEIC uploads (PLAN.md §2.8).
# gosu: drop from root to the host user's uid so bind-mounted data/ and media/
#       do not end up owned by root on the host.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libheif1 \
        libjpeg62-turbo \
        zlib1g \
        gosu \
        tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FLASK_APP=app.py

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x /srv/scripts/entrypoint.sh

# Which commit this image was built from. .dockerignore excludes .git, so it has
# to be passed in — `make docker` does that. Without it the app reports
# "unknown", which is honest rather than wrong.
# Empty by default, not "unknown": a non-empty value here would shadow the
# .git mount that identifies the commit at run time.
ARG APP_VERSION=""
ENV APP_VERSION=$APP_VERSION

# Defaults. Every one is overridable at run time from .env / compose.
ENV DATA_DIR=/srv/data \
    MEDIA_DIR=/srv/media \
    PORT=8080 \
    WEB_CONCURRENCY=2 \
    WEB_THREADS=4 \
    WEB_TIMEOUT=120 \
    PUID=1000 \
    PGID=1000 \
    AUTO_BOOTSTRAP=1

EXPOSE 8080

# Uses $PORT so it keeps working when the port is changed. start-period is
# generous because the first boot imports ~1,100 cards from a flaky upstream.
HEALTHCHECK --interval=60s --timeout=10s --start-period=900s --retries=3 \
  CMD python -c "import os,urllib.request;urllib.request.urlopen(f\"http://127.0.0.1:{os.environ.get('PORT','8080')}/api/healthz\")"

# tini reaps zombies and forwards signals, so `docker compose stop` is clean.
ENTRYPOINT ["/usr/bin/tini", "--", "/srv/scripts/entrypoint.sh"]
CMD ["serve"]
