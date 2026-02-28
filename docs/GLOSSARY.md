# Glossary

## Adapter

An adapter is the site-specific plugin that knows how to crawl one website.
It implements the shared `SiteAdapter` interface and plugs into the generic
crawler runner.

## Stub

A stub is a lightweight item discovered from a listing page. It usually
contains a URL and a few small metadata fields, but not the full page content.

## Record

A record is the full normalized result returned after fetching a detail page.
Records are typed models such as `JobRecord`, `NewsRecord`, or `ExamRecord`.

## Upsert

Upsert means "insert or update". If the row does not exist yet, the code
inserts it. If it already exists, the code updates the existing row instead of
creating a duplicate.

## content_hash

`content_hash` is a stable fingerprint of the meaningful fields in a record.
It helps the crawler decide whether the page content changed since the last
time it was seen.

## Registry

The registry is the dictionary that maps a site name such as `ajira` to its
adapter class. The generic crawler runner uses it to load the right adapter.

## Semaphore

A semaphore is a concurrency limit. In this project, it controls how many
detail pages the crawler fetches at the same time.

## Context

Context usually means the shared Playwright browser context created for one
crawl run. Adapters reuse it to open pages efficiently instead of starting a
new browser every time.
