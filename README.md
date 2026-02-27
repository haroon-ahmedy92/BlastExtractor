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
```

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
