---
name: search
description: Search the product catalog database for furniture and decor
args: "\"<query>\" [--source sweeek|kavehome|zarahome] [--max-price N]"
---

# Search Product Catalog

Use the `catalog_search` MCP tool directly. Pass:
- **query**: natural language search text (e.g. "grey sofa for small living room")
- **db_path**: absolute path to `catalog_vector_db/` in the project directory
- **n**: number of results (default 5)
- **source** (optional): filter by retailer — `sweeek`, `kavehome`, or `zarahome`
- **max_price** (optional): maximum price in EUR

Results include: name, price, source, similarity score, URL, colors, and image_urls.

Use `catalog_stats` to check product counts and verify the database is loaded.

## Notes

- First call per session takes ~30s to load the vector DB; subsequent calls are instant.
- The MCP server runs on the host machine — no VirtioFS or proxy issues.
- The database (`catalog_vector_db/`) must exist in the project (built from crawled product data).
