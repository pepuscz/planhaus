#!/usr/bin/env python3
"""
planhaus Catalog MCP Server
============================
FastMCP stdio server exposing catalog_search, catalog_get and catalog_stats.
Runs on the host machine (not in the Cowork VM), solving VirtioFS/proxy issues.

DB path resolution (all tools): explicit db_path param → CATALOG_DB_PATH env
(set via .mcp.json from ${user_config.catalog_db_path}) → ./catalog_vector_db
under the current working directory.
"""

import json
import os
import statistics
import sys
from collections import Counter


# Self-bootstrap: install deps into PYTHONPATH target if missing.
# Must fail FAST with a clear JSON error if pip fails — never a bare traceback.
def _ensure_deps():
    paths = os.environ.get("PYTHONPATH", "").split(":")
    lib_path = paths[0] if paths and paths[0] else None
    if not lib_path:
        return
    # Add lib_path to sys.path so imports work
    if lib_path not in sys.path:
        sys.path.insert(0, lib_path)
    # Check if deps are importable
    try:
        import chromadb  # noqa: F401
        import mcp  # noqa: F401
        return
    except ImportError:
        pass

    import subprocess
    try:
        os.makedirs(lib_path, exist_ok=True)
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q",
             "--target", lib_path,
             "chromadb>=0.4.0", "mcp>=1.0.0"],
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "pip failed").strip()[-800:])
    except Exception as e:
        # stderr: stdout is the MCP stdio protocol channel
        print(json.dumps({
            "error": "Failed to install catalog dependencies (chromadb, mcp)",
            "detail": str(e)[:800],
            "hint": f"Install manually: {sys.executable} -m pip install --target '{lib_path}' chromadb mcp",
        }), file=sys.stderr)
        sys.exit(1)


_ensure_deps()

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as e:
    print(json.dumps({
        "error": "MCP SDK not available",
        "detail": str(e),
        "hint": f"Install manually: {sys.executable} -m pip install mcp chromadb",
    }), file=sys.stderr)
    sys.exit(1)

# Lazy-import catalog_vectordb (PYTHONPATH includes the scripts/catalog dir)
_db_cache: dict = {}


def _resolve_db_path(db_path: str | None) -> tuple[str | None, list[str]]:
    """Resolve the catalog DB directory.

    Order: explicit param → CATALOG_DB_PATH env → ./catalog_vector_db (cwd).
    Returns (resolved_path_or_None, attempted_paths).
    """
    candidates: list[tuple[str, str]] = []
    if db_path:
        candidates.append(("db_path param", db_path))
    env = os.environ.get("CATALOG_DB_PATH", "").strip()
    if env:
        candidates.append(("CATALOG_DB_PATH env", env))
    candidates.append(("cwd fallback", os.path.join(os.getcwd(), "catalog_vector_db")))

    attempted = []
    for label, cand in candidates:
        cand = os.path.expanduser(cand)
        attempted.append(f"{label}: {cand}")
        if os.path.isdir(cand):
            return cand, attempted
    return None, attempted


def _get_db_or_error(db_path: str | None):
    """Returns (db, None) on success or (None, error_json_string)."""
    resolved, attempted = _resolve_db_path(db_path)
    if resolved is None:
        return None, json.dumps({
            "error": "Catalog database not found",
            "attempted_paths": attempted,
            "hint": ("Build it with 'python catalog_vectordb.py build', set the "
                     "catalog_db_path plugin setting (CATALOG_DB_PATH env), or "
                     "pass db_path explicitly."),
        })
    if resolved not in _db_cache:
        from catalog_vectordb import CatalogVectorDB
        _db_cache[resolved] = CatalogVectorDB(db_path=resolved)
    return _db_cache[resolved], None


def _db_is_current(db) -> bool:
    """True when the DB carries the current v2 metadata stamp."""
    try:
        import catalog_vectordb
        return db._read_db_version() >= catalog_vectordb.DB_VERSION
    except Exception:
        return True  # never let the version probe break a query


_REBUILD_HINT = ("catalog DB predates v2 — category/style/color/material/dimension "
                 "filters match nothing and similarity values are unreliable until "
                 "you rebuild: python catalog_vectordb.py build --force")


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


def _collect_metadatas(collection, max_items: int = 20000, page: int = 500) -> list[dict]:
    """Page through collection metadata (bounded) for facet computation."""
    metas: list[dict] = []
    offset = 0
    while offset < max_items:
        res = collection.get(include=["metadatas"], limit=page, offset=offset)
        batch = res.get("metadatas") or []
        if not batch:
            break
        metas.extend(batch)
        if len(batch) < page:
            break
        offset += len(batch)
    return metas


# --- MCP Server ---

mcp_server = FastMCP("planhaus-catalog")


@mcp_server.tool()
def catalog_search(
    query: str,
    db_path: str | None = None,
    n: int = 5,
    source: str | None = None,
    max_price: float | None = None,
    min_price: float | None = None,
    min_rating: float | None = None,
    category: str | None = None,
    style: str | None = None,
    color_family: str | None = None,
    material: str | None = None,
    max_width: float | None = None,
    max_depth: float | None = None,
    max_height: float | None = None,
) -> str:
    """Search the product catalog using natural language plus hard filters.

    Returns a JSON array of slim results (id, name, source, price, similarity,
    category, primary_material, color_family, style, dimensions, image_urls).
    Use catalog_get with the returned ids for full product data.

    Args:
        query: Natural language search text (e.g. "grey sofa for small living room")
        db_path: Absolute path to the catalog_vector_db/ directory on the host.
            Optional — falls back to the CATALOG_DB_PATH env var (plugin
            setting), then ./catalog_vector_db under the current directory.
        n: Number of results to return (default 5)
        source: Filter by retailer: sweeek, kavehome, or zarahome
        max_price: Maximum price in EUR
        min_price: Minimum price in EUR
        min_rating: Minimum rating (0-5; only sweeek has ratings)
        category: Controlled vocab: sofa, armchair, dining_table, dining_chair,
            coffee_table, side_table, bed, nightstand, wardrobe, dresser,
            bookshelf, rug, floor_lamp, table_lamp, pendant, mirror, decor,
            outdoor, other
        style: Controlled vocab (only set after catalog enrichment):
            scandinavian, midcentury, modern, industrial, rustic, traditional,
            coastal, japandi, mediterranean, bohemian, eclectic
        color_family: Controlled vocab: white, cream, beige, grey, charcoal,
            black, brown, natural_wood, green, blue, terracotta, pink, yellow,
            multicolor
        material: Primary material: oak, walnut, pine, rattan, metal, glass,
            boucle, linen, velvet, leather, marble, ceramic, other
        max_width: Maximum width in cm. Items with unknown dimensions still
            pass but are flagged "dims_unknown": true — verify before placing.
        max_depth: Maximum depth in cm (same unknown-dims behavior)
        max_height: Maximum height in cm (same unknown-dims behavior)
    """
    db, err = _get_db_or_error(db_path)
    if err:
        return err

    if db.collection.count() == 0:
        return json.dumps({"error": "Database is empty. Build it first with: python catalog_vectordb.py build"})

    # A pre-v2 DB has none of the enriched metadata: refuse filtered queries
    # loudly instead of returning a silent empty array.
    if not _db_is_current(db):
        if any(f is not None for f in (category, style, color_family, material,
                                       max_width, max_depth, max_height)):
            return json.dumps({"error": _REBUILD_HINT})
        results = db.query(query_text=query, n_results=n, source=source,
                           max_price=max_price, min_price=min_price,
                           min_rating=min_rating)
        for r in results:
            full = r.pop("full_product", {})
            r["image_urls"] = _extract_image_urls(full)
        return json.dumps({"warning": _REBUILD_HINT, "results": results},
                          ensure_ascii=False)

    results = db.query(
        query_text=query,
        n_results=n,
        source=source,
        max_price=max_price,
        min_price=min_price,
        min_rating=min_rating,
        category=category,
        style=style,
        color_family=color_family,
        material=material,
        max_width=max_width,
        max_depth=max_depth,
        max_height=max_height,
    )

    # Slim down: extract image_urls, drop full_product
    output = []
    for r in results:
        full = r.pop("full_product", {})
        r["image_urls"] = _extract_image_urls(full)
        output.append(r)

    return json.dumps(output, ensure_ascii=False)


@mcp_server.tool()
def catalog_get(ids: list[str], db_path: str | None = None) -> str:
    """Get full product data for shortlisted catalog items (up to 20 ids).

    Use after catalog_search to judge candidates from rich data (descriptions,
    specifications, all variants) without re-querying. Returns a JSON object
    with "products" (full parsed product data + enriched metadata) and
    "missing_ids" for ids not found.

    Args:
        ids: Product ids from catalog_search results (max 20 per call; batch larger shortlists)
        db_path: Absolute path to the catalog_vector_db/ directory on the host.
            Optional — falls back to CATALOG_DB_PATH env, then ./catalog_vector_db.
    """
    db, err = _get_db_or_error(db_path)
    if err:
        return err

    if not ids:
        return json.dumps({"error": "No ids given"})

    ids = [i for i in dict.fromkeys(ids) if i]  # dedupe (chromadb rejects dups)
    if not ids:
        return json.dumps({"error": "No valid ids given"})
    truncated = len(ids) > 20
    ids = ids[:20]

    try:
        res = db.collection.get(ids=ids, include=["metadatas"])
    except Exception as e:
        return json.dumps({"error": f"catalog_get failed: {str(e)[:300]}"})
    found_ids = res.get("ids") or []
    metas = res.get("metadatas") or []

    products = []
    for pid, md in zip(found_ids, metas):
        md = md or {}
        try:
            full = json.loads(md.get("full_product", "{}"))
        except (ValueError, TypeError):
            full = {}
        products.append({
            "id": pid,
            "name": md.get("name", ""),
            "source": md.get("source", ""),
            "price": md.get("price", 0),
            "rating": md.get("rating", 0),
            "url": md.get("url", ""),
            "category": md.get("category", ""),
            "primary_material": md.get("primary_material", ""),
            "color_family": md.get("color_family", ""),
            "style": md.get("style", ""),
            "width_cm": md.get("width_cm", 0),
            "depth_cm": md.get("depth_cm", 0),
            "height_cm": md.get("height_cm", 0),
            "dims_estimated": bool(md.get("dims_estimated", False)),
            "seat_height_cm": md.get("seat_height_cm", 0),
            "colors": json.loads(md.get("colors", "[]")),
            "image_urls": _extract_image_urls(full),
            "full_product": full,
        })

    missing = [pid for pid in ids if pid not in set(found_ids)]
    out = {"products": products, "missing_ids": missing}
    if truncated:
        out["note"] = "ids list truncated to the first 20"
    return json.dumps(out, ensure_ascii=False)


@mcp_server.tool()
def catalog_stats(db_path: str | None = None) -> str:
    """Get catalog statistics: product counts, price range, and facets.

    Returns total products, counts by source, price min/max/median (EUR),
    and the top-10 category and color_family facets — useful for scoping
    queries before searching.

    Args:
        db_path: Absolute path to the catalog_vector_db/ directory on the host.
            Optional — falls back to CATALOG_DB_PATH env, then ./catalog_vector_db.
    """
    db, err = _get_db_or_error(db_path)
    if err:
        return err

    stats = db.stats()
    if not _db_is_current(db):
        stats["warning"] = _REBUILD_HINT

    metas = _collect_metadatas(db.collection)
    prices = sorted(
        float(m.get("price") or 0) for m in metas if float(m.get("price") or 0) > 0
    )
    if prices:
        stats["price"] = {
            "min": prices[0],
            "max": prices[-1],
            "median": statistics.median(prices),
        }
    else:
        stats["price"] = {}

    category_counts = Counter(
        m.get("category") for m in metas if m.get("category")
    )
    color_counts = Counter(
        m.get("color_family") for m in metas if m.get("color_family")
    )
    stats["top_categories"] = dict(category_counts.most_common(10))
    stats["top_color_families"] = dict(color_counts.most_common(10))
    if len(metas) < stats.get("total_products", 0):
        stats["facets_note"] = f"facets computed over the first {len(metas)} products"

    return json.dumps(stats, ensure_ascii=False)


if __name__ == "__main__":
    mcp_server.run()
