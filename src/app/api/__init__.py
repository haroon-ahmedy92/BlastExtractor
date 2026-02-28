"""HTTP API package for reading stored crawl results.

The main FastAPI application lives in :mod:`app.api.main`. The API sits after
the crawl flow: adapters write structured records into the database, and this
package exposes those records to clients.
"""
