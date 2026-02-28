"""CLI utility that prints a quick map of the repository.

This module scans ``src/app`` without importing project modules, extracts the
first line of each module docstring, prints a shallow file tree, and ends with
a short crawl-flow summary that points to the main function names.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = REPO_ROOT / "src" / "app"
MAX_TREE_DEPTH = 2


def iter_python_files(root: Path) -> list[Path]:
    """Return sorted Python source files under the given root.

    Args:
        root: Directory to scan.

    Returns:
        list[Path]: Sorted Python files, excluding cache directories.
    """

    return sorted(
        path
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def read_module_summary(path: Path) -> str:
    """Extract the first line of a module docstring.

    Args:
        path: Python source file path.

    Returns:
        str: First docstring line, or a fallback message if absent.
    """

    source = path.read_text(encoding="utf-8")
    module = ast.parse(source, filename=str(path))
    docstring = ast.get_docstring(module)
    if not docstring:
        return "(no module docstring)"
    return docstring.strip().splitlines()[0]


def build_tree_lines(root: Path, max_depth: int = MAX_TREE_DEPTH) -> list[str]:
    """Build a shallow file tree for the repository.

    Args:
        root: Directory to render.
        max_depth: Maximum nesting depth relative to ``root``.

    Returns:
        list[str]: Human-readable tree lines.
    """

    lines = [root.name + "/"]
    for path in sorted(root.rglob("*")):
        if "__pycache__" in path.parts:
            continue
        relative = path.relative_to(root)
        depth = len(relative.parts) - 1
        if depth > max_depth:
            continue
        indent = "  " * len(relative.parts)
        suffix = "/" if path.is_dir() else ""
        lines.append(f"{indent}{relative.name}{suffix}")
    return lines


def build_module_summary_lines(root: Path) -> list[str]:
    """Build module summary lines for all Python files.

    Args:
        root: Directory containing Python modules.

    Returns:
        list[str]: Summary lines in ``path: summary`` format.
    """

    lines: list[str] = []
    for path in iter_python_files(root):
        relative_path = path.relative_to(root)
        lines.append(f"{relative_path}: {read_module_summary(path)}")
    return lines


def build_crawl_flow_lines() -> list[str]:
    """Return a short crawl flow summary with function names.

    Returns:
        list[str]: Ordered crawl-flow lines.
    """

    return [
        "1. app.crawler.run.parse_args() reads --site, --once, --concurrency, --debug",
        "2. app.sites.registry.get_adapter(site_name) returns the adapter class",
        "3. app.crawler.run.run_site_once() calls app.db.session.init_db()",
        "4. app.crawler.browser.browser_context() creates one shared Playwright context",
        "5. adapter.discover() returns stub models such as JobStub",
        "6. app.crawler.run._run_adapter() limits detail fetches with asyncio.Semaphore",
        "7. adapter.fetch_details(stub) returns a full record such as JobRecord",
        "8. app.sites.ajira_portal.compute_content_hash(payload) fingerprints content",
        "9. adapter.upsert(record) calls a DB helper such as upsert_job_posting()",
        "10. app.crawler.run.print_report() prints discovered/inserted/updated/unchanged/failed",
    ]


def main() -> None:
    """Print the repository map to standard output.

    Returns:
        None
    """

    print("BlastExtractor Repo Map")
    print()
    print("File Tree")
    for line in build_tree_lines(APP_ROOT):
        print(line)

    print()
    print("Module Summaries")
    for line in build_module_summary_lines(APP_ROOT):
        print(line)

    print()
    print("Crawl Flow")
    for line in build_crawl_flow_lines():
        print(line)


if __name__ == "__main__":
    main()
