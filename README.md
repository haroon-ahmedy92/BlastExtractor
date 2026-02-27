# BlastExtractor

Production-lean Python 3.12 scaffold for a web crawler + FastAPI service.

## Requirements

- Python 3.12
- [`uv`](https://docs.astral.sh/uv/)
- MySQL 8+

## Setup

```bash
cp .env.example .env
make install
uv run python -m app.db.init
```

Ensure the MySQL database in `DATABASE_URL` already exists (default: `blastextractor`).

## Run API

```bash
make run-api
```

Health endpoint:

- `GET http://localhost:8000/health`

## Run crawler (Ajira)

```bash
make crawl-ajira
PYTHONPATH=src python -m app.crawler.crawl_ajira --once --export jobs.jsonl
```

## Run scheduler

Run one incremental scheduler cycle:

```bash
PYTHONPATH=src python -m app.scheduler.run --once
```

Run the long-lived scheduler locally:

```bash
PYTHONPATH=src python -m app.scheduler.run
```

The scheduler always refreshes the Ajira listing page, then only fetches detail pages for new jobs, jobs whose listing metadata changed, or jobs that have not been refreshed within `SCHEDULER_REFRESH_AFTER_DAYS` days. By default it runs every 30 minutes and uses a filesystem lock at `SCHEDULER_LOCK_PATH` to prevent overlapping scheduler processes.

## Run as a service

Example `systemd` unit:

```ini
[Unit]
Description=BlastExtractor scheduler
After=network.target mysql.service

[Service]
Type=simple
WorkingDirectory=/home/haroon/ONGOING/BlastExtractor
Environment=PYTHONPATH=src
ExecStart=/usr/bin/python -m app.scheduler.run
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Adjust the Python path and working directory for your host. If you use a virtual environment, point `ExecStart` at that interpreter. Override `SCHEDULER_INTERVAL_MINUTES`, `SCHEDULER_REFRESH_AFTER_DAYS`, and `SCHEDULER_LOCK_PATH` in the service environment when needed.

## Quality checks

```bash
make lint
make test
```

## Project layout

```text
src/
  app/
    api/
    crawler/
    db/
    sites/
    models/
tests/
```
