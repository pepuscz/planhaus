---
name: search
description: Search the product catalog database for furniture and decor
args: "\"<query>\" [--source sweeek|kavehome|zarahome] [--max-price N]"
---

# Search Product Catalog

Query the vector database for products matching a natural language description.

## Steps

1. Run the catalog query tool:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/catalog/query_catalog.py "<query>" --max-price <N>
   ```

   Optional flags:
   - `--max-price N` — filter by maximum price in EUR
   - `-s sweeek|kavehome|zarahome` — filter by catalog source
   - `-n 10` — number of results (default: 5)
   - `--json` — machine-readable output
   - `--full` — include full product data

2. If the database is not found or empty, tell the user:
   - The catalog DB is not included with the plugin (it's user data)
   - They can build one: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/catalog/catalog_vectordb.py build --source <data.json>`
   - Or install catalog deps first: `pip install -r ${CLAUDE_PLUGIN_ROOT}/scripts/catalog/requirements.txt`

3. Present results with: name, price, source, match %, URL.

## Notes

- First query per session takes 30-60s to load the vector DB.
- Requires chromadb (`/planhaus:setup` with catalog option).
- The DB is built from crawled product data that the user provides.
