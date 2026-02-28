# BlastExtractor

BlastExtractor is a teaching-friendly web crawling project built with Python, Playwright, SQLAlchemy, and FastAPI.

Its job is simple:

1. visit public websites
2. extract structured content
3. store that content in the right database table
4. expose stored data through an API

The project uses a plugin architecture. That means the crawler engine stays generic, while each website lives in its own adapter.

For the full system explanation, read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## What Problems This Project Solves

Many websites publish useful information, but they do not provide it in a clean API.

BlastExtractor helps by:

- turning messy HTML pages into structured records
- separating jobs, news, and exam results into different tables
- preventing duplicate inserts with hash-based upserts
- making new websites easy to add through adapters

## Main Ideas

- One generic crawl runner: `src/app/crawler/run.py`
- One adapter per site: `src/app/sites/`
- One content type per table:
  - `job_postings`
  - `news_articles`
  - `exam_results`
- One API app for reading stored data: `src/app/api/main.py`

Current registered adapters:

- `ajira` -> jobs -> `job_postings`
- `news_stub` -> news -> `news_articles`
- `exam_stub` -> exams -> `exam_results`

## Requirements

- Python 3.12
- [`uv`](https://docs.astral.sh/uv/)
- MySQL 8+ for normal use
- SQLite is fine for tests and small local experiments

## 1. Install Dependencies

```bash
cp .env.example .env
make install
```

If you prefer plain Python commands instead of `uv run`, set `PYTHONPATH=src` first or add it inline when running commands.

## 2. Initialize the Database

```bash
uv run python -m app.db.init
```

This creates all known tables:

- `job_postings`
- `news_articles`
- `exam_results`

## 3. Run the API

```bash
make run-api
```

Available endpoints:

- `GET /health`
- `GET /jobs`
- `GET /jobs/{id}`

Example:

```bash
curl "http://127.0.0.1:8000/jobs?source=ajira&limit=10"
```

## 4. Run the Crawler

Run the real Ajira adapter once:

```bash
uv run python -m app.crawler.run --site ajira --once
```

Run Ajira and export fetched records to JSONL:

```bash
uv run python -m app.crawler.run --site ajira --once --export-jsonl jobs.jsonl
```

Run the placeholder adapters:

```bash
uv run python -m app.crawler.run --site news_stub --once
uv run python -m app.crawler.run --site exam_stub --once
```

The stub adapters should complete successfully and usually report `discovered: 0`.

## 5. How a Crawl Run Works

At a high level, one crawl run does this:

1. Parse CLI options such as `--site` and `--concurrency`
2. Load the adapter class from the site registry
3. Create one shared Playwright browser context if the adapter needs a browser
4. Call `discover()` to find page stubs
5. Process stubs concurrently with `asyncio.Semaphore`
6. Call `fetch_details()` for each stub
7. Compute or use the record `content_hash`
8. Call `upsert()` to insert or update the right database row
9. Print a final summary report

The detailed version of this flow is documented in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## 6. Plugin Architecture

Each site is implemented as a `SiteAdapter`.

A `SiteAdapter` must define:

- `site_name`
- `content_type`
- `discover()`
- `fetch_details(stub)`
- `upsert(record)`

The crawler engine does not know anything about Ajira, news pages, or exam pages. It only knows how to run adapters that follow the shared interface.

This makes new sites mostly drop-in.

## 7. Folder Guide

Important folders:

- `src/app/api` for the FastAPI app
- `src/app/crawler` for the generic crawl runtime
- `src/app/db` for database setup and upsert logic
- `src/app/models` for Pydantic and SQLAlchemy models
- `src/app/sites` for site adapters
- `tests` for automated tests

The full folder explanation is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## 8. How To Add a New Site

Short version:

1. Create a new file in `src/app/sites/`
2. Subclass `SiteAdapter`
3. Choose one content type: `jobs`, `news`, or `exams`
4. Return typed stubs from `discover()`
5. Return a typed record from `fetch_details()`
6. Save with the correct upsert function in `upsert()`
7. Register the adapter
8. Add tests

The step-by-step checklist is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## 9. Scheduler

Run one scheduled Ajira cycle:

```bash
uv run python -m app.scheduler.run --once
```

Run the long-lived scheduler:

```bash
uv run python -m app.scheduler.run
```

The scheduler uses a lock to prevent overlapping runs and is documented in the README service section and architecture notes.

## 10. Development Checks

Run linting:

```bash
make lint
```

Run tests:

```bash
make test
```

## 11. Learning Path

If you are studying this project for the first time, read it in this order:

1. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
2. `src/app/crawler/run.py`
3. `src/app/sites/base.py`
4. `src/app/sites/registry.py`
5. `src/app/sites/ajira_portal.py`
6. `src/app/db/session.py`
7. `src/app/api/main.py`
