#!/usr/bin/env python3
"""
planhaus Catalog MCP Server
============================
FastMCP stdio server exposing catalog_search and catalog_stats tools.
Runs on the host machine (not in the Cowork VM), solving VirtioFS/proxy issues.
"""

import json
import os
import sys

# Self-bootstrap: install deps into PYTHONPATH target if missing
def _ensure_deps():
    paths = os.environ.get("PYTHONPATH", "").split(":")
    lib_path = paths[0] if paths and paths[0] else None
    if lib_path:
        # Add lib_path to sys.path so imports work
        if lib_path not in sys.path:
            sys.path.insert(0, lib_path)
        # Check if chromadb is importable
        try:
            import chromadb  # noqa: F401
            import mcp  # noqa: F401
        except ImportError:
            import subprocess
            os.makedirs(lib_path, exist_ok=True)
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", "-q",
                "--target", lib_path,
                "chromadb>=0.4.0", "mcp>=1.0.0",
            ])

_ensure_deps()

from mcp.server.fastmcp import FastMCP

# Lazy-import catalog_vectordb (PYTHONPATH includes the scripts/catalog dir)
_db_cache: dict = {}

def _get_db(db_path: str):
    """Get or create a CatalogVectorDB instance, cached by path."""
    db_path = os.path.expanduser(db_path)
    if db_path not in _db_cache:
        from catalog_vectordb import CatalogVectorDB
        _db_cache[db_path] = CatalogVectorDB(db_path=db_path)
    return _db_cache[db_path]


def _extract_image_urls(full_product: dict) -> list[str]:
    """Extract image URLs from a product's full data across catalog schemas."""
    urls = []

    # Direct image fields
    for key in ("image_url", "image", "main_image", "thumbnail"):
        val = full_product.get(key)
        if isinstance(val, str) and val.startswith("http"):
            urls.append(val)

    # Image list fields
    for key in ("images", "image_urls", "gallery"):
        val = full_product.get(key)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, str) and item.startswith("http"):
                    urls.append(item)
                elif isinstance(item, dict):
                    for sub_key in ("url", "src", "href"):
                        u = item.get(sub_key, "")
                        if isinstance(u, str) and u.startswith("http"):
                            urls.append(u)

    # Color variants with images (sweeek pattern)
    for variant in full_product.get("color_variants") or []:
        if isinstance(variant, dict):
            img = variant.get("image_url") or variant.get("image", "")
            if isinstance(img, str) and img.startswith("http"):
                urls.append(img)

    return urls


# --- MCP Server ---

mcp_server = FastMCP("planhaus-catalog")


@mcp_server.tool()
def catalog_search(
    query: str,
    db_path: str,
    n: int = 5,
    source: str | None = None,
    max_price: float | None = None,
) -> str:
    """Search the product catalog using natural language.

    Args:
        query: Natural language search text (e.g. "grey sofa for small living room")
        db_path: Absolute path to the catalog_vector_db/ directory on the host
        n: Number of results to return (default 5)
        source: Filter by retailer: sweeek, kavehome, or zarahome
        max_price: Maximum price in EUR
    """
    db = _get_db(db_path)

    if db.collection.count() == 0:
        return json.dumps({"error": "Database is empty. Build it first with: python catalog_vectordb.py build"})

    results = db.query(
        query_text=query,
        n_results=n,
        source=source,
        max_price=max_price,
    )

    # Slim down: extract image_urls, drop full_product
    output = []
    for r in results:
        full = r.pop("full_product", {})
        r["image_urls"] = _extract_image_urls(full)
        output.append(r)

    return json.dumps(output, ensure_ascii=False)


@mcp_server.tool()
def catalog_stats(db_path: str) -> str:
    """Get product counts and database statistics.

    Args:
        db_path: Absolute path to the catalog_vector_db/ directory on the host
    """
    db = _get_db(db_path)
    stats = db.stats()
    return json.dumps(stats, ensure_ascii=False)


if __name__ == "__main__":
    mcp_server.run()
