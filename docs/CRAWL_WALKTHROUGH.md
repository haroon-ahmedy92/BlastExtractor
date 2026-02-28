# Ajira Crawl Walkthrough

This document explains one Ajira crawl run as a short story.

The command we are following is:

```bash
python -m app.crawler.run --site ajira --once
```

If you want the runner to print one real stub and one real record during the
run, use:

```bash
python -m app.crawler.run --site ajira --once --debug
```

## The Story Starts at the CLI

You run the command.

The Python process enters `app/crawler/run.py`.
The runner reads the CLI arguments and learns four important things:

- the site name is `ajira`
- this is a one-time run because of `--once`
- concurrency will use the default value `4` unless you change it
- debug output is off unless you add `--debug`

At this point, the runner has not touched the website yet.
It only knows what kind of crawl you asked for.

## Step 1: Find the Right Adapter

The runner asks the registry:

```python
adapter_cls = get_adapter("ajira")
```

The registry returns `AjiraPortalAdapter`.

This is important because the generic runner still does not know anything
about Ajira HTML. It only knows that the adapter has the methods:

- `discover()`
- `fetch_details(stub)`
- `upsert(record)`

## Step 2: Prepare the Browser

Ajira needs a browser, so the runner opens one shared Playwright browser
context.

That context is reused during the run.
The crawler does not launch a brand-new browser for every page.

The browser setup also blocks large assets such as:

- images
- fonts
- media

That makes the run lighter and faster because the crawler mainly cares about
text and links.

## Step 3: Discover Job Listings

Now the adapter starts real crawl work.

It opens the Ajira vacancies listing page and parses the HTML into
`JobStub` objects.

A `JobStub` is a small summary of one listing.
It is enough to identify a detail page, but it does not yet contain the full
job description.

Example `JobStub`:

```json
{
  "url": "https://portal.ajira.go.tz/view-advert/12345",
  "title": "Tutorial Assistant - Computer Science",
  "discovered_at": "2026-02-28T10:15:00Z",
  "institution": "University of Example",
  "number_of_posts": 2,
  "deadline_date": "2026-03-15"
}
```

Chronologically, this is the first real data structure produced by the run.

If you use `--debug`, the runner prints the first discovered stub after
`discover()` finishes.

## Step 4: Apply Concurrency

The runner now has a list of stubs.

It does not process them one by one in a slow serial loop.
It uses an `asyncio.Semaphore` to allow a few detail pages to be fetched at
the same time.

In the current CLI, the default concurrency is `4`.

That means:

- up to 4 stubs can be inside `fetch_details()` at once
- the 5th stub waits until one of the first 4 finishes

Why this helps:

- it is faster than strictly one-by-one crawling
- it avoids opening too many pages at once
- it reduces the chance of overloading the target site
- it keeps memory use more predictable

Small mental model:

```text
Queue of stubs -> semaphore gate -> up to 4 active detail fetches
```

## Step 5: Fetch One Detail Page

For each stub, the adapter opens the detail page and extracts richer fields.

This is where the small `JobStub` becomes a full `JobRecord`.

The adapter parses things like:

- description text
- description HTML
- category
- location
- attachments
- structured fields such as remuneration or qualifications when present

Example `JobRecord`:

```json
{
  "source": "ajira",
  "source_url": "https://portal.ajira.go.tz/view-advert/12345",
  "title": "Tutorial Assistant - Computer Science",
  "content_hash": "8bc3d5b0d1c1e2b3a4f5678901234567890abcdeffedcba09876543210abcdef",
  "institution": "University of Example",
  "number_of_posts": 2,
  "deadline_date": "2026-03-15",
  "category": "Education",
  "location": "Dodoma",
  "description_text": "The employer is looking for qualified candidates...",
  "description_html": "<main><h1>Tutorial Assistant...</h1></main>",
  "attachments_json": {
    "links": [
      "https://portal.ajira.go.tz/storage/advert.pdf"
    ],
    "metadata": {
      "duty station": "Dodoma",
      "structured_fields": {
        "qualifications": "Bachelor degree in Computer Science",
        "duties": "Teaching, research, and student support"
      }
    }
  }
}
```

If you use `--debug`, the runner prints the first successfully fetched record.

## Step 6: Compute `content_hash`

Before saving the record, the adapter builds a normalized payload and hashes it.

The hash is based on meaningful content, not on random runtime values.

Short version of the idea:

```python
hash_payload = {
    "source_url": "...",
    "title": "...",
    "institution": "...",
    "description_text": "...",
    "attachments": [...],
    "metadata": {...},
}
```

Then the runner computes:

```python
sha256(json.dumps(hash_payload, sort_keys=True, ...))
```

Why this matters:

- if the page content is the same, the hash stays the same
- if the page content changes, the hash changes

This gives the database layer a clean way to decide whether a record is:

- new
- updated
- unchanged

## Step 7: Upsert into the Database

Now the adapter calls its `upsert()` method.

For Ajira, that goes to the `job_postings` table.

The upsert logic checks whether a row with the same `source_url` already
exists.

There are three outcomes.

### Case A: First time seeing this job

No row exists yet.

The code inserts a new row.

Example `UpsertResult`:

```json
{
  "action": "inserted",
  "record_id": 42
}
```

### Case B: Same job, same content

A row already exists and the stored `content_hash` matches the new one.

The code does not rewrite the content fields.
It only updates `last_seen`.

Example:

```json
{
  "action": "unchanged",
  "record_id": 42
}
```

### Case C: Same job, changed content

A row already exists, but the new `content_hash` is different.

The code updates the content fields and also updates `last_seen`.

Example:

```json
{
  "action": "updated",
  "record_id": 42
}
```

## Step 8: What Happens to `first_seen` and `last_seen`

These two timestamps tell a small history story.

### First crawl

The job is new.

```text
first_seen = now
last_seen  = now
```

### Second crawl, same content

The job already exists and nothing meaningful changed.

```text
first_seen = old value
last_seen  = new current time
```

`first_seen` stays as the original discovery time.
`last_seen` moves forward because the crawler confirmed the job still exists.

### Third crawl, content changed

The job still matches the same `source_url`, but the page content changed.

```text
first_seen = original value
last_seen  = new current time
content fields = updated
content_hash = updated
```

So:

- `first_seen` answers: "When did we first discover this job?"
- `last_seen` answers: "When did we most recently confirm or refresh this job?"

## Step 9: Finish the Run

After all stubs finish, the runner counts the outcomes.

The final report looks like this:

```text
Crawler Report
site: ajira
discovered: 25
inserted: 4
updated: 3
unchanged: 18
failed: 0
duration_seconds: 14.27
```

This is the end of one crawl run.

## One Short Timeline

Here is the whole run in one compact timeline:

1. You run `python -m app.crawler.run --site ajira --once`
2. The CLI parser reads your options
3. The registry returns `AjiraPortalAdapter`
4. The runner opens one shared browser context
5. `discover()` fetches the vacancies page
6. The adapter returns a list of `JobStub` items
7. The semaphore allows a limited number of concurrent detail fetches
8. `fetch_details()` turns each stub into a `JobRecord`
9. The adapter computes `content_hash`
10. `upsert()` inserts, updates, or leaves the row unchanged
11. `first_seen` and `last_seen` are maintained
12. The runner prints the final report

## Optional Debug Run

If you want to watch one real example during the crawl, use:

```bash
python -m app.crawler.run --site ajira --once --debug
```

That prints:

- one discovered `JobStub`
- one fetched `JobRecord`

This is useful when you are learning the crawl flow or debugging field
extraction without dumping every record in the run.
