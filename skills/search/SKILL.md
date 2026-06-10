---
name: search
description: Raw product catalog access — semantic search with structured filters, full product lookup, and database stats via the planhaus-catalog MCP tools
when_to_use: For direct catalog exploration ("any rattan armchairs?", "sofas under 800"). For choosing furniture for a room slot use /planhaus:select.
argument-hint: "\"<query>\" [filters]"
allowed-tools: mcp__planhaus-catalog__catalog_search, mcp__planhaus-catalog__catalog_get, mcp__planhaus-catalog__catalog_stats
---

# Search Product Catalog

Thin manual for the three `planhaus-catalog` MCP tools. **For design-driven selection use
`/planhaus:select`** — it builds a slot brief, expands queries, and gates/scores candidates
against the design concept. Raw search is for exploration: checking what the catalog holds,
verifying coverage, spot-checking prices.

## `catalog_search`

Semantic search over the product catalog.

- **query** (required): natural language text (e.g. "grey sofa for small living room")
- **db_path** (optional): absolute path to `catalog_vector_db/` on the host. Resolution
  order: explicit param → `CATALOG_DB_PATH` env var (set from the plugin's
  `catalog_db_path` user config via `.mcp.json`) → `./catalog_vector_db` under the cwd.
  On failure the error lists the attempted paths.
- **n**: number of results (default 5)
- **source**: retailer filter — `sweeek`, `kavehome`, or `zarahome`
- **max_price** / **min_price**: price bounds in EUR
- **min_rating**: minimum product rating
- **category**: controlled vocab — `sofa, armchair, dining_table, dining_chair,
  coffee_table, side_table, bed, nightstand, wardrobe, dresser, bookshelf, rug, floor_lamp,
  table_lamp, pendant, mirror, decor, outdoor, other`
- **style**: controlled vocab — `scandinavian, midcentury, modern, industrial, rustic,
  traditional, coastal, japandi, mediterranean, bohemian, eclectic`. Empty until the DB is
  enriched (`/planhaus:enrich-catalog`) — filtering on it before enrichment returns nothing.
- **color_family**: `white, cream, beige, grey, charcoal, black, brown, natural_wood,
  green, blue, terracotta, pink, yellow, multicolor`
- **material**: `oak, walnut, pine, rattan, metal, glass, boucle, linen, velvet, leather,
  marble, ceramic, other`
- **max_width** / **max_depth** / **max_height**: dimension caps in cm. Products with
  unknown dimensions pass these filters but come back flagged `dims_unknown` — verify
  before relying on them.

Results include: id, name, price, source, cosine similarity, URL, colors, image_urls,
and the metadata fields above. Similarity is retrieval relevance, not product quality.

## `catalog_get`

- **ids** (required): list of product ids (from search results)
- **db_path** (optional): same resolution as above

Returns full product data for the given ids — use after search to judge a shortlist from
rich data (descriptions, variants, specs) without re-querying.

## `catalog_stats`

- **db_path** (optional): same resolution as above

Returns product counts per source, price ranges, and category/color facets. Use it to
verify the database is loaded and see what's actually in it before filtering.

## Notes

- First call per session takes ~30s to load the vector DB; subsequent calls are instant.
- The MCP server runs on the host machine — no VirtioFS or proxy issues in Cowork.
- The database (`catalog_vector_db/`) must exist (built from crawled product data with
  `catalog_vectordb.py build`). If tools error on the path, set the `catalog_db_path`
  plugin config or pass `db_path` explicitly.
