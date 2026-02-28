"""Scheduler package for repeated crawl execution.

The scheduler wraps the generic crawler runner and triggers crawl cycles on a
fixed interval while preventing overlapping runs with a lock.
"""
