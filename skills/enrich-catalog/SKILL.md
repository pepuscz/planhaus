---
name: enrich-catalog
description: Enrich the catalog database with style metadata (and fix color/material) by classifying exported products and importing the results
argument-hint: "[category]"
allowed-tools: Bash(python3:*)
---

# Enrich Catalog Metadata

The catalog's `style` field is empty until enriched — the build-time normalizers can map
category/color/material from structured data, but style is a judgment call. This skill
drives the `enrich` CLI: export products missing style, classify them yourself, import the
results. No re-embedding happens — only metadata is updated in place.

Run where the catalog DB lives (the directory containing `catalog_vector_db/`), with
chromadb installed. In Cowork the host-side MCP server owns the DB; run this skill in
local Claude Code on that host machine instead.

## Steps

1. **Export** products missing style:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/catalog/catalog_vectordb.py" enrich export --missing style --out pending.jsonl
   ```
   Each line: `id`, `name`, `category`, description excerpt.

2. **Classify in batches of ~30 lines.** Read a batch, judge each product's `style` from
   the controlled vocab:

   `scandinavian, midcentury, modern, industrial, rustic, traditional, coastal, japandi,
   mediterranean, bohemian, eclectic`

   Judge from name/category/description signals — leg style (tapered light wood →
   scandinavian/midcentury; hairpin/black metal → industrial; turned/carved →
   traditional), line language (low-slung straight → midcentury; curved minimal →
   modern/japandi; ornate → traditional), materials (rattan/jute → coastal/bohemian;
   raw pine/reclaimed wood → rustic; terracotta/wrought iron → mediterranean).

   **When truly ambiguous, leave `style` empty rather than guessing** — wrong metadata
   silently corrupts every later filtered search; missing metadata just falls back to
   judgment at selection time.

3. Optionally **fix `color_family` / `primary_material`** in the same pass when the
   build-time mapping is clearly wrong for a product you're already looking at.

4. **Write `enriched.jsonl`** — one JSON object per line:
   ```json
   {"id": "...", "style": "japandi"}
   {"id": "...", "style": "midcentury", "color_family": "natural_wood"}
   {"id": "...", "style": ""}
   ```
   Optional override keys: `color_family`, `primary_material`, `leg_style`.

5. **Import**:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/catalog/catalog_vectordb.py" enrich import --in enriched.jsonl
   ```

6. **Report counts**: exported / classified / left empty, plus a per-style breakdown.
   Spot-check with `catalog_search` using a `style` filter.

## Notes

- Runtime scales with catalog size — thousands of products means many batches. Work
  **one category at a time** (group the exported JSONL lines by their `category` field,
  or pass a category as the argument and enrich just those), and import after each
  category so progress persists if you stop.
- A category's products share signals (all sofas, all rugs) — judging them together is
  faster and more consistent than mixed batches.
- Re-running is safe: `--missing style` only exports products still unclassified, so
  deliberately-empty styles will re-export — skip ids you already judged ambiguous.
