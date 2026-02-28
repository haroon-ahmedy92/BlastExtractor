"""Site adapter package.

Each module in this package contains scraping logic for one website. During a
crawl run the generic runner loads an adapter from the registry and delegates
site-specific work to that adapter.
"""
