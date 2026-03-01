# Architecture Guide

## 1. Project Goal

BlastExtractor is a small scraping platform for collecting public information from websites and storing it in a structured database.

It solves four practical problems:

1. Websites are inconsistent. Each site has its own HTML, links, and page structure.
2. Raw pages are hard to search. The project converts page content into typed records such as jobs, news, and exam results.
3. Repeated crawling can create duplicates. The project uses hashing and upsert logic so the same page is updated instead of inserted again.
4. New websites should be easy to add. The crawler engine is generic, and each website is plugged in through a `SiteAdapter`.

In simple terms, the project separates:

- the crawling engine
- the website-specific scraping logic
- the database tables for different kinds of content
- the API layer for reading stored data

## 2. High-Level Architecture

```text
                     +----------------------+
                     |   CLI / Scheduler    |
                     | python -m app...     |
                     +----------+-----------+
                                |
                                v
                     +----------------------+
                     | Generic Crawl Runner |
                     | app/crawler/run.py   |
                     +----------+-----------+
                                |
                  registry lookup|browser setup
                                v
                 +-----------------------------+
                 | SiteAdapter Implementation  |
                 | ajira / news_stub / exam... |
                 +-------------+---------------+
                               |
                 discover()    | fetch_details()
                               v
                 +-----------------------------+
                 | Typed Pydantic Models       |
                 | JobRecord / NewsRecord /    |
                 | ExamRecord                  |
                 +-------------+---------------+
                               |
                               v
                 +-----------------------------+
                 | DB Upsert Functions         |
                 | app/db/...                  |
                 +-------------+---------------+
                               |
                               v
                 +-----------------------------+
                 | SQLAlchemy Tables           |
                 | job_postings                |
                 | news_articles               |
                 | exam_results                |
                 +-------------+---------------+
                               |
                               v
                     +----------------------+
                     | FastAPI API          |
                     | app/api/main.py      |
                     +----------------------+
```

## 3. End-to-End Algorithm of a Crawl Run

The main crawl entry point is:

```bash
python -m app.crawler.run --site ajira --once
```

Here is the full flow.

### Step 1: CLI parsing

`app/crawler/run.py` reads command-line arguments:

- `--site` chooses the adapter from the registry
- `--once` runs one crawl cycle and exits
- `--concurrency` controls how many detail pages are fetched at the same time
- `--export-jsonl` optionally writes all fetched records to a JSONL file

If `--once` is missing, the current runner stops with an error. This keeps the command simple and explicit.

### Step 2: Registry lookup

The runner calls `get_adapter(site_name)` from `app/sites/registry.py`.

The registry is just a dictionary:

```text
site name -> adapter class
```

Examples:

- `ajira` -> `AjiraPortalAdapter`
- `citizen_news` -> `TheCitizenNewsAdapter`
- `mwananchi_news` -> `MwananchiNewsAdapter`
- `zoom_jobs` -> `ZoomTanzaniaJobsAdapter`
- `bmz_exams` -> `ZanzibarBMZExamAdapter`
- `necta_exams` -> `NectaExamAdapter`
- `news_stub` -> `GenericNewsStubAdapter`
- `exam_stub` -> `GenericExamStubAdapter`

This means the crawler engine does not need `if site == "ajira"` logic. It asks the registry for the adapter and works with that class.

### Step 3: Browser and context creation

Some adapters need a browser. Others do not.

If `adapter_cls.requires_browser` is `True`, the runner opens a shared Playwright browser context using `app/crawler/browser.py`.

That context is configured for speed:

- runs in headless mode if enabled in config
- blocks images, fonts, and media files
- uses realistic browser headers such as `User-Agent` and `Accept-Language`
- sets the browser timezone from config
- reuses one browser and one context for the whole crawl run
- sets default timeouts

This is important because launching a browser for every page would be slow.

### Step 4: Adapter creation

The runner creates the adapter instance and passes shared dependencies:

- `browser_context`
- `session_factory`

This is dependency injection in a simple form. The adapter receives what it needs instead of creating everything by itself.

### Step 5: `adapter.discover()`

The runner calls `discover()`.

This method finds candidate pages to crawl. It usually:

- opens a listing page
- extracts links
- creates typed `Stub` objects

For Ajira, `discover()` reads the vacancies listing and returns `JobStub` items.

A stub is intentionally small. It normally contains:

- the URL
- a title if available
- a few metadata fields from the listing page

The stub is enough to decide what detail pages exist, but not enough to store the final record.

### Step 6: Concurrency and `fetch_details()`

After discovery, the runner processes stubs concurrently.

It uses `asyncio.Semaphore` to limit how many detail pages are fetched at the same time. This prevents:

- opening too many pages at once
- using too much memory
- overloading the target site

For each stub, the runner does:

1. `adapter.fetch_details(stub)`
2. `adapter.upsert(record)`

If one stub fails, the error is logged and the run continues for the remaining stubs.

### Step 7: Hashing and upsert

`fetch_details()` returns a typed record such as:

- `JobRecord`
- `NewsRecord`
- `ExamRecord`

Each record includes a `content_hash`.

The content hash is a fingerprint of the important content fields. It helps answer a simple question:

```text
Did the page content actually change?
```

The adapter then passes the record to its own `upsert()` method. That method writes to exactly one table.

Current mapping:

- job adapters write to `job_postings`
- news adapters write to `news_articles`
- exam adapters write to `exam_results`

The upsert logic follows this pattern:

1. Look up the existing row by unique key, usually `source_url`
2. If no row exists, insert a new row
3. If a row exists, update `last_seen`
4. If the stored `content_hash` is different, update the changed fields and mark the action as `updated`
5. If the hash is the same, keep the content and mark the action as `unchanged`

This prevents duplicate records and gives a useful summary of what changed during the run.

### Step 8: Final report summary

At the end, the runner prints a short report:

- `discovered`
- `inserted`
- `updated`
- `unchanged`
- `failed`
- `duration_seconds`

If `--export-jsonl` was provided, it also writes the full fetched records to a JSON Lines file.

## 4. Plugin Architecture

### What a `SiteAdapter` is

A `SiteAdapter` is the contract every site plugin must follow.

The base class lives in `src/app/sites/base.py`.

Each adapter must define:

- `site_name`
- `content_type`
- `discover()`
- `fetch_details(stub)`
- `upsert(record)`

In plain English:

- `discover()` finds pages
- `fetch_details()` reads one page and builds a typed record
- `upsert()` saves that record into the correct database table

The generic crawler runner knows only this interface. It does not know site-specific HTML or business rules.

### How the registry works

The registry lives in `src/app/sites/registry.py`.

It stores adapter classes in a global dictionary called `REGISTRY`.

When an adapter module is imported, it registers itself with a simple call:

```python
register_adapter("ajira", AjiraPortalAdapter)
```

Later, the runner asks:

```python
adapter_cls = get_adapter("ajira")
```

This keeps site-specific code out of the crawler engine.

### What “content_type tables” means

The project stores different types of content in different SQL tables.

That is what “content_type tables” means.

Current content types:

- `jobs`
- `news`
- `exams`

Current tables:

- `job_postings`
- `news_articles`
- `exam_results`

Why this matters:

- jobs have fields like `institution` and `deadline_date`
- news articles have fields like `author` and `published_at`
- exam results have fields like `centre_code`, `centre_name`, and `results_json`

If all content lived in one big table, many columns would be empty or confusing. Separate tables keep the data easier to understand and query.

## 5. Folder Structure and Responsibilities

### `src/app/api`

This folder contains the FastAPI application.

Responsibility:

- expose HTTP endpoints
- read from the database
- return Pydantic response models

Current example:

- `GET /health`
- `GET /jobs`
- `GET /jobs/{id}`

### `src/app/crawler`

This folder contains the generic crawling runtime.

Responsibility:

- parse crawl CLI arguments
- create the browser context
- run adapters
- control concurrency
- export JSONL
- print crawl reports

Important files:

- `run.py` for the generic runner
- `browser.py` for shared Playwright setup

### `src/app/db`

This folder contains database setup and persistence logic.

Responsibility:

- create the SQLAlchemy engine and sessions
- initialize tables
- upsert rows into each content table

Important files:

- `session.py` for engine, session, and `init_db()`
- `job_postings.py`
- `news_articles.py`
- `exam_results.py`

### `src/app/models`

This folder contains both validation models and table models.

Responsibility:

- shared typed Pydantic models for stubs and records
- SQLAlchemy models for database tables
- normalization helpers such as whitespace cleanup and date parsing

Examples:

- `common.py` for shared base models and enums
- `jobs.py`, `news.py`, `exams.py` for typed crawl records
- `job_posting.py`, `news_article.py`, `exam_result.py` for SQLAlchemy tables

### `src/app/sites`

This folder contains site plugins.

Responsibility:

- all site-specific scraping logic
- mapping raw HTML into typed records
- registering adapters with the registry

Examples:

- `ajira_portal.py`
- `citizen_news.py`
- `mwananchi_news.py`
- `zoom_jobs.py`
- `bmz_exams.py`
- `necta_exams.py`
- `news_stub.py`
- `exam_stub.py`

### `tests`

This folder contains automated tests.

Responsibility:

- verify parsing logic
- verify persistence behavior
- verify API responses
- verify crawler runner behavior
- catch regressions when the code changes

Good tests are especially important in scraping projects because website HTML can change without warning.

## 6. Registered Adapters and Safe Run Patterns

The current adapters are:

- `ajira`: Ajira job postings
- `citizen_news`: The Citizen Tanzania news articles
- `mwananchi_news`: Mwananchi news articles, with graceful skip when blocked
- `zoom_jobs`: Zoom Tanzania job postings
- `bmz_exams`: Zanzibar BMZ exam-centre result pages
- `necta_exams`: NECTA centre result pages discovered from result index pages

### How each adapter works

`ajira`

- discovers vacancies from the Ajira listing page
- fetches one detail page per vacancy
- writes `JobRecord` rows into `job_postings`

`citizen_news`

- opens the Tanzania news listing page
- extracts article links and titles
- parses article detail pages for title, author, published date, section, and body
- writes `NewsRecord` rows into `news_articles`

`mwananchi_news`

- opens the Mwananchi homepage with browser-like headers and shared browser state
- extracts article links when the site allows navigation
- logs a structured `blocked` event and returns no stubs if the site blocks the crawler
- can be disabled with `MWANANCHI_ENABLED=false`
- writes `NewsRecord` rows into `news_articles`

`zoom_jobs`

- opens the Zoom Tanzania jobs listing
- follows pagination until `ZOOM_JOBS_MAX_PAGES` or until no new jobs appear
- parses job detail pages for company, job type, location, description, skills, and apply links
- writes `JobRecord` rows into `job_postings`

`bmz_exams`

- opens the BMZ schools landing page
- discovers exam-year index pages
- opens each exam index page and discovers centre result pages
- parses centre tables into structured JSON
- writes `ExamRecord` rows into `exam_results`

`necta_exams`

- opens NECTA exam view pages such as CSEE, ACSEE, PSLE, and FTNA
- discovers year-specific results index pages
- opens each results index and discovers centre result pages
- parses centre tables into structured JSON
- logs and skips blocked or unreachable pages instead of crashing the whole run
- writes `ExamRecord` rows into `exam_results`

### Safe CLI examples

Use these commands from the project root:

```bash
python -m app.crawler.run --site ajira --once --concurrency 3
python -m app.crawler.run --site citizen_news --once --concurrency 3
python -m app.crawler.run --site mwananchi_news --once --concurrency 2
python -m app.crawler.run --site zoom_jobs --once --concurrency 3
python -m app.crawler.run --site bmz_exams --once --concurrency 2 --limit 50
python -m app.crawler.run --site necta_exams --once --concurrency 2 --limit 50
```

Why the exam commands use `--limit`:

- exam sites can expose thousands of centre pages
- a smaller first run is safer and easier to validate
- you can increase the limit gradually once parsing is confirmed

### Known limitations

- Mwananchi may block non-human traffic even with Playwright and browser-like headers.
- NECTA entry pages may reset or block connections depending on network conditions.
- News layouts can change without notice, so selector drift is expected over time.

## 7. How To Add a New Site

Use this checklist.

### Step-by-step checklist

1. Decide the content type.
   Choose one of `jobs`, `news`, or `exams`.

2. Create a new adapter file in `src/app/sites/`.
   Example: `src/app/sites/ministry_news.py`

3. Subclass `SiteAdapter`.
   Set:
   - `site_name`
   - `content_type`
   - `requires_browser`

4. Pick the correct models.
   Use:
   - `JobStub` and `JobRecord` for jobs
   - `NewsStub` and `NewsRecord` for news
   - `ExamStub` and `ExamRecord` for exams

5. Implement `discover()`.
   Return a list of typed stubs.

6. Implement `fetch_details(stub)`.
   Open the detail page, extract fields, normalize values, and compute a `content_hash`.

7. Implement `upsert(record)`.
   Call the correct DB function for the content type.

8. Register the adapter.
   Add a `register_adapter(...)` call in the adapter module, or import it from `registry.py`.

9. Run the crawler locally.

```bash
python -m app.crawler.run --site your_site_name --once
```

10. Add tests.
    At minimum, test:
    - parsing
    - hash behavior
    - insert vs update vs unchanged behavior

### Small mental model

If you are adding a new site, you should only need to touch:

- one new adapter file
- one registry entry
- tests for that adapter

The generic runner should not need site-specific changes.

## 8. Common Failure Points and Debugging Tips

### 1. Selector changes

Problem:
The target website changes its HTML, class names, or page layout.

Symptoms:

- `discover()` returns zero stubs
- fields such as title or deadline become empty
- parsing tests start failing

What to do:

- inspect the live HTML again
- compare the old selectors with the current page
- add fallback selectors where possible
- write parsing tests using saved HTML samples

Ajira is a good example of this kind of risk. If the listing page changes, the adapter may still run but discover zero jobs.
The same risk applies to The Citizen, Mwananchi, Zoom, BMZ, and NECTA selectors.

### 2. Timeouts

Problem:
The page loads too slowly, or important elements appear after the timeout limit.

Symptoms:

- Playwright timeout errors
- random failures during discovery or detail fetching

What to do:

- check `browser_timeout_ms` in config
- verify that the site is reachable
- wait for a more reliable selector
- reduce concurrency if the site or machine is under load

### 3. Blocked requests

Problem:
The browser context blocks images, fonts, and media for speed. A site may unexpectedly depend on one of these requests or on JavaScript that loads late.

Symptoms:

- page looks incomplete
- some data never appears
- a selector exists in the browser manually but not during the crawl

What to do:

- temporarily disable or relax request blocking in `app/crawler/browser.py`
- inspect network behavior
- confirm whether the data is in the initial HTML or loaded later by JavaScript
- remember that Mwananchi may block even when the page is valid in a normal browser

### 4. Database uniqueness errors

Problem:
Two records try to use the same unique key, or the adapter chooses the wrong deduplication field.

Symptoms:

- insert failures
- duplicate-key database errors
- the same real-world record appears more than once under different URLs

What to do:

- check the table unique constraints
- make sure `source_url` is stable and normalized
- if a site needs a different unique rule, design it clearly before coding
- confirm that `content_hash` is used only for change detection, not as the primary identifier
- for BMZ and NECTA, keep centre URLs stable and avoid inventing synthetic keys unless needed

### 5. Bad normalization

Problem:
Whitespace, dates, or text formatting are inconsistent.

Symptoms:

- content hashes change too often
- records update even when the page did not really change

What to do:

- normalize whitespace before hashing
- parse dates into consistent formats
- avoid hashing values that are noisy or irrelevant

## 9. Glossary

**Adapter**
Code that knows how to crawl one website.

**API**
The HTTP interface used by other programs or frontends to read stored data.

**Content type**
A category of stored information, such as jobs, news, or exams.

**Crawler**
The part of the system that visits websites and extracts data.

**Discover**
The step that finds candidate detail pages, usually from a listing page.

**Fetch details**
The step that opens one discovered page and extracts the full record.

**Hash**
A short fingerprint of content. It helps detect whether a record changed.

**JSONL**
JSON Lines. A file format where each line is one JSON object.

**Pydantic model**
A Python class used for validation and clean structured data.

**Registry**
The map that connects a site name like `ajira` to an adapter class.

**SiteAdapter**
The abstract base class that every site plugin must follow.

**Stub**
A small record discovered from a listing page before full details are fetched.

**Upsert**
Insert a new row if it does not exist, otherwise update the existing row.
