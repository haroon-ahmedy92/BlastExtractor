# Repo Map Utility

`python -m app.tools.explain_repo` prints a fast, dependency-free overview of
the repository.

It is useful when you want a quick mental model before reading code.

## Command

Run it from the project root:

```bash
python -m app.tools.explain_repo
```

If you are not already using `PYTHONPATH=src`, run:

```bash
PYTHONPATH=src python -m app.tools.explain_repo
```

## What It Prints

The tool prints three sections.

### 1. File Tree

It prints a shallow tree of `src/app`, about 2 to 3 levels deep.

That helps you see the main folders quickly:

- `api`
- `crawler`
- `db`
- `models`
- `scheduler`
- `sites`
- `tools`

### 2. Module Summaries

For each Python module, it reads the module docstring and prints the first
line.

This gives you a quick answer to:

```text
What is this file for?
```

The tool reads source files directly and uses Python's built-in `ast` module,
so it does not need to import the project.

### 3. Crawl Flow

At the end, it prints a short ordered summary of the crawl path with function
names.

This is the main flow it points to:

1. `app.crawler.run.parse_args()`
2. `app.sites.registry.get_adapter()`
3. `app.crawler.run.run_site_once()`
4. `app.crawler.browser.browser_context()`
5. `adapter.discover()`
6. `app.crawler.run._run_adapter()`
7. `adapter.fetch_details()`
8. `compute_content_hash(...)`
9. `adapter.upsert(...)`
10. `app.crawler.run.print_report()`

## Why It Is Fast

The tool is intentionally simple.

It only:

- walks the `src/app` directory
- reads `.py` files
- parses docstrings with `ast`
- prints a small hardcoded crawl-flow summary

It does not:

- open the database
- launch Playwright
- import site adapters
- make network requests

## When To Use It

Use it when:

- you are new to the project
- you forgot where a module lives
- you want a quick overview before reading details
- you want to confirm the main crawl path
