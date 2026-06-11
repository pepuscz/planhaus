---
name: migrate
description: Upgrade a pre-1.0 planhaus project to the 1.0 format — refresh injected docs, upgrade schemas, then retroactively derive the concept and zones the project implies and triage what the rules engine finds. Use when a project predates 1.0 (no concept.yaml, rooms without zones, stale project CLAUDE.md) or the user asks to migrate/upgrade a project.
when_to_use: A project scaffolded by planhaus 0.x — detectable by a missing concept.yaml, rooms with furniture but no zones, a free-text budget block in brief.yaml, or a project CLAUDE.md without the PHASE DISCIPLINE section. Not needed for new projects.
argument-hint: "[project-dir]"
allowed-tools: Bash(python3:*)
---

# Migrate Project (0.x → 1.0)

Old projects keep working without migration — every new field is optional and missing
data produces SKIP, never an error. Migration is worth it because it upgrades the
*reasoning*, not just the schema: the project gets a concept, zones, and a confrontation
with the rules engine that 0.x never had.

**Migration is re-thinking, not re-formatting.** The old layout encodes design decisions
nobody wrote down; your job is to make them explicit, then judge them.

## Step 0 — Inventory and mode

Read `brief.yaml`, `apartment.yaml`, every `rooms/*.yaml`, the registry, and the project's
own `CLAUDE.md`. Establish:

- **0.x markers**: no `concept.yaml`; rooms without `zones:`/`focal_point:`/`circulation:`;
  `budget: |` as free text; registry items missing `category`/`currency` or with
  `style: "string"` instead of a list; project CLAUDE.md without the PHASE DISCIPLINE section.
- **Project mode** — this decides how much you may move:
  - **Paper project** (nothing `purchased`/`installed`, or placeholder furniture): full
    re-think allowed; furniture moves freely.
  - **Furnished home** (items purchased/installed): derive, don't redesign. Propose moves
    (free), flag replacements (cost money) — and never present a replacement as a fix
    without saying so.

**Back up first.** If the project is a git repo, commit the pre-migration state; otherwise
copy it to `<project>-pre-1.0/`. Tell the user where the backup is.

## Step 1 — Refresh the injected docs

`CLAUDE.md`, `design-checklist.yaml`, and `workflow.md` were *copied* into the project at
scaffold time and contain pre-1.0 doctrine (hardcoded clearance numbers, no phase
discipline, old command list).

- If the project copy matches the old template (user never edited it): replace it with the
  current copy from `"${CLAUDE_PLUGIN_ROOT}/templates/"`.
- If the user edited it: merge — bring in the 1.0 sections (phase discipline, rule-ID
  citation, budget allocation, new fields) while preserving every user addition. Show the
  user what changed. Never silently drop their text.

## Step 2 — Mechanical schema upgrades

- `brief.yaml`: convert a free-text `budget: |` block into the mapping
  `budget: { total, currency, notes }` — the prose moves into `notes:` verbatim. If no
  number exists anywhere, ask the user (don't guess; `/planhaus:concept` needs it).
- Registry items: add `category` (controlled vocab — infer from the folder and the item),
  `currency` next to `price`, convert `style: "x"` → `style: [x]`. Add `palette_role`,
  `visual_weight`, `seat_height`, `lumens`/`color_temp_k` only where you can ground them in
  the item's actual specs; otherwise leave them out (no invented data).
- Room furniture/built-ins: add `type:` (controlled vocab — the engine targets checks by
  type; id-sniffing is the fallback, not the plan). Add `screen_diagonal_in` to TVs and
  `hang_height_cm` to pendants **from real product data** — these turn SKIPs into checks,
  which is the point of migrating. Model honestly: a window above a counter is
  `type: fixed`, not deleted.

## Step 3 — Re-think (the actual migration)

1. **Derive `concept.yaml` from evidence** — run `/planhaus:concept` in *reverse-engineering
   mode*: the palette and style come from what is actually installed (materials, colors,
   styles of the placed items) reconciled with the brief. Where reality contradicts the
   brief ("brief says warm minimalism, the room has chrome and glass"), record it as a
   finding for the user — don't paper over it and don't invent a fresh concept that
   disowns their purchases.
2. **Derive zones per room** — run `/planhaus:zone` in the same spirit: the zones, focal
   point, and circulation routes *already implied* by the existing layout get written down
   (`zones:`, `focal_point:` + why, `circulation:` with rule IDs). If the layout implies two
   competing focal points, that's a finding, not a choice you make silently.
3. **Confront the rules engine** — per room:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/room_spatial.py" rooms/<room>.yaml --check
   ```
   The old tool only checked collisions; expect new findings. Triage every one:
   - **ERROR, fixable by moving** → propose the move with design reasoning (paper project:
     apply it; furnished home: present it — moving furniture is free).
   - **ERROR baked into a purchase** (e.g. the sofa is simply too deep for the aisle) →
     document it in the room `notes:` as a known issue with a remediation idea and rough
     cost. Do not delete features or data from the model to silence the rule.
   - **WARN** → accept with a one-sentence trade-off in `notes:`, or fix.
   - **SKIP** → either supply the missing data now or leave the TODO visible.
4. **Re-render** every touched room (`--plot`) and read the floorplans critically — the
   visual check catches what the numbers don't.

## Step 4 — Report

Summarize: backup location; docs refreshed (merged or replaced); schema changes; the
derived concept in three sentences; a triage table of findings (fixed / accepted /
known-issue / TODO); and next steps — typically `/planhaus:select` for slots worth
upgrading and `/planhaus:light` if the lighting predates the 3-layer doctrine.

## Notes

- The catalog DB migrates separately: a v1 `catalog_vector_db/` needs
  `python3 catalog_vectordb.py build --force` (the tools detect this and say so).
- Migration is idempotent — re-running on a migrated project finds nothing to do.
- One room at a time is fine: migrate the most-used room first, prove the value, continue.
