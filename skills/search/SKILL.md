---
name: search
description: Search the product catalog database for furniture and decor
args: "\"<query>\" [--source sweeek|kavehome|zarahome] [--max-price N]"
---

# Search Product Catalog

Semantic vector search across the product catalog database.

## Prerequisites

- **chromadb**: Install if not available (`pip install chromadb`)
- **catalog_vector_db/**: Must exist in the project folder (not included with the plugin — user builds it from their own crawled product data)

## Important: ChromaDB needs a writable filesystem with file locking

ChromaDB uses SQLite internally, which requires write access and proper file locking. VirtioFS mounts (like the project directory in Cowork) do not support this. **Copy the database to the session's writable directory before querying.** Only needed once per session.

## Steps

1. Find `catalog_vector_db/` in the project directory.
2. Copy it to a writable location if running in a sandboxed VM (e.g., Cowork). The session root directory is writable.
3. Run the query with `CATALOG_DB_PATH` pointing to the writable copy:
   ```bash
   CATALOG_DB_PATH=<writable-db-path> python3 ${CLAUDE_PLUGIN_ROOT}/scripts/catalog/query_catalog.py "<query>"
   ```

   Optional flags:
   - `--max-price N` — filter by maximum price in EUR
   - `-s sweeek|kavehome|zarahome` — filter by catalog source
   - `-n 10` — number of results (default: 5)
   - `--json` — machine-readable output
   - `--full` — include full product data

4. Present results with: name, price, source, match %, URL.

## Notes

- The database includes a bundled ONNX embedding model (`onnx_model/` inside the DB directory) for offline use — no network access needed at query time.
- First query per session takes 30-60s to load the vector DB.
- To build a new database (requires internet + crawled product data):
  ```bash
  python3 ${CLAUDE_PLUGIN_ROOT}/scripts/catalog/catalog_vectordb.py build
  ```
