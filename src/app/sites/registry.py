"""Registry of available site adapters.

The generic crawler runner asks this module for an adapter class based on the
``--site`` CLI argument. Importing the concrete adapter modules at the bottom
ensures they register themselves before lookup happens.
"""

from __future__ import annotations

from typing import TypeAlias

from app.sites.base import SiteAdapter

AdapterType: TypeAlias = type[SiteAdapter]

REGISTRY: dict[str, AdapterType] = {}


def register_adapter(site_name: str, adapter_cls: AdapterType) -> None:
    """Register a site adapter class under a CLI-visible name.

    Args:
        site_name: Name used by the runner and scheduler.
        adapter_cls: Adapter class implementing the site behavior.

    Returns:
        None
    """

    REGISTRY[site_name] = adapter_cls


def get_adapter(site_name: str) -> AdapterType:
    """Return a registered adapter class.

    Args:
        site_name: Name used in the CLI.

    Returns:
        AdapterType: Registered adapter class.

    Raises:
        KeyError: If the site name is not registered.
    """

    try:
        return REGISTRY[site_name]
    except KeyError as error:
        available = ", ".join(sorted(REGISTRY))
        raise KeyError(f"Unknown site '{site_name}'. Available: {available}") from error


import app.sites.ajira_portal  # noqa: E402,F401
import app.sites.exam_stub  # noqa: E402,F401
import app.sites.news_stub  # noqa: E402,F401
