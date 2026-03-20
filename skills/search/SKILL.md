---
name: search
description: Search the product catalog database for furniture and decor
args: "\"<query>\" [--source sweeek|kavehome|zarahome] [--max-price N]"
---

# Search Product Catalog

Semantic vector search across the product catalog database.

## Prerequisites

The catalog database (`catalog_vector_db/` directory) must exist in the project folder. It is NOT included with the plugin — the user builds it from their own crawled product data.

## Steps

1. Install chromadb if not available:
   ```bash
   python3 -c "import chromadb" 2>/dev/null || pip install -q chromadb
   ```

2. Find the catalog database in the project directory:
   ```bash
   DB_PATH=$(find /sessions/*/mnt -name "catalog_vector_db" -type d 2>/dev/null | head -1)
   if [ -z "$DB_PATH" ]; then
     DB_PATH=$(find . -name "catalog_vector_db" -type d 2>/dev/null | head -1)
   fi
   ```
   If not found, tell the user they need to build it first (see Notes below).

3. Run the query:
   ```bash
   CATALOG_DB_PATH="$DB_PATH" python3 ${CLAUDE_PLUGIN_ROOT}/scripts/catalog/query_catalog.py "<query>"
   ```

   Optional flags:
   - `--max-price N` — filter by maximum price in EUR
   - `-s sweeek|kavehome|zarahome` — filter by catalog source
   - `-n 10` — number of results (default: 5)
   - `--json` — machine-readable output
   - `--full` — include full product data

4. Present results with: name, price, source, match %, URL.

## Notes

- The database includes a bundled ONNX embedding model for offline use — no network access needed at query time.
- First query per session takes 30-60s to load the vector DB.
- To build a new database (requires internet + crawled product data):
  ```bash
  python3 ${CLAUDE_PLUGIN_ROOT}/scripts/catalog/catalog_vectordb.py build
  ```
  This indexes products AND caches the embedding model for offline use.
