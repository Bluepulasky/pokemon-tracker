FROM python:3.12-slim

# pillow-heif needs libheif at runtime for iPhone HEIC uploads (PLAN.md §2.8).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libheif1 libjpeg62-turbo zlib1g \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# data/ and media/ are bind-mounted; a rebuild must never touch the DB or photos.
ENV DATA_DIR=/srv/data MEDIA_DIR=/srv/media HOST=0.0.0.0 PORT=8080
EXPOSE 8080

HEALTHCHECK --interval=60s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/api/healthz')"

# 2 workers is plenty for one user, and keeps SQLite writer contention low.
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8080", "--timeout", "120", "app:app"]
