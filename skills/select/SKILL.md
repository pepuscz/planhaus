---
name: select
description: Multi-criteria furniture selection for a room slot — builds a slot brief from concept + room data, expands catalog queries, gates and scores candidates, presents a top-3 comparison
when_to_use: When choosing, buying, or shortlisting furniture for a slot ("find a sofa for the living room", "pick a dining table", "which coffee table should I get"). For raw catalog exploration use /planhaus:search instead.
argument-hint: "<room> <slot, e.g. sofa>"
allowed-tools: mcp__planhaus-catalog__catalog_search, mcp__planhaus-catalog__catalog_get, mcp__planhaus-catalog__catalog_stats, Bash(python3:*)
---

# Select Furniture (FF&E)

Phase 5 of the design process. The layout should already fix the slot's position and
dimensions (zones + placed anchors in the room YAML). Selection translates design intent
into a defensible top-3 — never "here are some search results".

Run `catalog_stats` once at the start to confirm the catalog DB is reachable.

## Step 1 — Build the slot brief (before ANY query)

Read:
- `rooms/<room>.yaml` — the slot's zone, intended anchor, neighbors, existing materials
- `concept.yaml` — style, palette, budget, material master list

Assemble the brief:

1. **Function / category** — the controlled catalog category for the slot
   (`sofa, armchair, dining_table, dining_chair, coffee_table, side_table, bed, nightstand,
   wardrobe, dresser, bookshelf, rug, floor_lamp, table_lamp, pendant, mirror, decor, outdoor, other`).

2. **Placement envelope** — max width/depth/height the slot allows. Get facts from the
   spatial tool, not by eyeballing:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/room_spatial.py" rooms/<room>.yaml --check --json
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/room_spatial.py" rooms/<room>.yaml --matrix
   ```
   Envelope = zone bounds minus the clearances the rules engine enforces (CIRC/SEAT/DIN/BED
   rules — cite rule IDs, don't restate numbers). If a placeholder item occupies the slot,
   its gaps in `--matrix` show the slack available.

3. **Budget line** = room budget × tier share ÷ number of items planned in that tier for
   the room. Tiers (from `concept.yaml` `budget.allocation`, default **anchor 60% /
   supporting 25% / accent 15%**):
   - **anchor**: sofa, bed, dining table
   - **supporting**: coffee table, chairs, rugs, lighting, storage
   - **accent**: decor, cushions, plants
   Room budget comes from `concept.yaml` `budget.rooms`; count planned items per tier from
   the room YAML / layout plan.

4. **Ergonomic band** by category — e.g. sofa/armchair seat height 43–48 cm; dining chair
   seat 45–50 cm under a 71–76 cm table; coffee table top within ~±5 cm of the sofa seat
   height; desk 72–76 cm. Derive other categories from standard ergonomic references.

5. **Style signals + palette role** — from `concept.yaml`: `style.primary/secondary`,
   the concrete `style.signals` (leg styles, line language, materials, era), `style.avoid`,
   and the slot's 60-30-10 palette role (dominant / secondary / accent) with its color
   families and materials.

If `concept.yaml` or zones are missing (old project), say which parts of the brief you
cannot build, ask the user for budget and style direction, and proceed with what exists.

## Step 2 — Query expansion

**Never search with one raw user phrase.** Write **3–5 distinct `catalog_search` queries**
that mix the concept's style signals with the function, plus material/color variants:

- "low-profile 3-seater sofa tapered wood legs"
- "linen sofa light oak frame minimal"
- "boucle compact sofa rounded edges"

On **every** query apply the structured filters:
- `category` — the slot's controlled category
- `max_width` / `max_depth` / `max_height` — from the placement envelope
- `max_price` = 1.2 × budget line
- optionally `style`, `color_family`, `material` to bias toward variants — but keep at
  least one query without the `style` filter (the catalog may be un-enriched)

Use `n` ≈ 8 per query. **Union + dedupe** the results into **10–20 candidates**, then call
`catalog_get(ids=[...])` on the shortlist to fetch full product data — gates and scores are
judged from the rich data, not the search snippets.

## Step 3 — Hard gates (eliminate, don't score)

Every elimination gets a stated reason. A candidate must pass ALL gates:

1. **Category** matches the slot.
2. **Physical fit** — footprint fits the zone AND leaves the rule-table clearances
   (the envelope from step 1). For candidates flagged `dims_unknown`, recover dimensions
   from the `catalog_get` full data; if still unverifiable, eliminate with reason
   "dimensions unverifiable".
3. **Price** ≤ 1.2× budget line. Survivors at 1.0–1.2× are flagged **"stretch"**.
4. **Ergonomic bounds** for seating (seat height within the band).

## Step 4 — Weighted scoring (0–100)

**Shuffle the surviving candidates into random order before judging** — position-bias
mitigation. Score each per criterion with a **one-line justification per criterion**:

| Criterion | Weight | What to judge |
|---|---|---|
| Proportion & dimensional fit | 25 | 2/3-rule targets vs wall and adjacent pieces (PROP-01/02), sensible use of the envelope |
| Style coherence | 25 | Signal-level: legs, materials, lines, era — match against `style.signals`. Adjacent styles score partial credit (e.g. the scandinavian≈japandi≈midcentury cluster); judge other adjacencies from shared signals |
| Material & palette fit | 20 | 12 pts: color family correct for the slot's 60-30-10 role. 8 pts: material repeats an existing room material |
| Ergonomics | 10 | Position within the band; depth/firmness/comfort signals |
| Quality / construction signals | 10 | Kiln-dried hardwood frame, 8-way hand-tied springs, high-density (HD) foam, solid wood vs particleboard |
| Budget fit | 10 | Peak at 0.8–1.0× line; taper to 0 at 1.2×; mild penalty below 0.5× for anchor slots |

**Never present embedding similarity as a quality score** — it is retrieval relevance only.

When selecting for **many slots**, delegate steps 3–4 to the `planhaus:furniture-curator`
subagent — one slot per invocation, passing the slot brief and the candidate ids.

## Step 5 — Present top 3

A comparison table per slot: per-criterion scores, total, price (with "stretch" flag where
applicable), key dimensions, URL — and **one trade-off sentence per candidate** (what you
give up by picking it).

When the user picks one → run `/planhaus:add-item` to register it with
`status: shortlisted`, carrying over the catalog metadata (category, style, color_family,
material, dimensions, price, url, image urls) so nothing is re-typed.

## Degrading gracefully

- **Un-enriched catalog** (style metadata empty): skip the `style` filter; judge style from
  name, description, and images via `catalog_get` instead — and tell the user that style
  was inferred from product data, not metadata. Suggest `/planhaus:enrich-catalog`.
- **No concept.yaml**: ask for style direction and budget before scoring; score what you
  can and mark unscored criteria explicitly.
- **No zones**: fall back to room dimensions + `--matrix` gaps for the envelope, and note
  that `/planhaus:zone` would make the fit check rigorous.
