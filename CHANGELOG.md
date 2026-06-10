# Changelog

All notable changes to planhaus are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-06-10

Restructured around the professional design process (brief → concept → zoning →
circulation → layout → FF&E selection → lighting → review) instead of jumping straight
to furniture placement. See `docs/architecture.md` for the full contract.

### Added

- Skills: `brief`, `concept`, `zone`, `furnish`, `select`, `light`, `enrich-catalog` (8 → 15 skills).
- Agents (`agents/`): `design-researcher`, `space-planner`, `furniture-curator`,
  `design-reviewer` (forked by `/planhaus:review`).
- Rules engine: canonical, severity-tiered clearance table `scripts/rules/clearances.yaml`
  (CIRC/SEAT/DIN/BED/TV/KIT/DOOR/WIN/HEAT/LIGHT/PROP/RUG rules); `room_spatial.py --check --json`
  applies it and reports `SEVERITY RULE-ID: detail` findings plus skipped checks.
- Optional room YAML fields: `zones`, `focal_point`, `circulation` (with `rule:` IDs),
  `sightlines`; `type:`/`zone:` on furniture; `layer:`/`color_temp_k`/`lumens` on lighting.
- `templates/concept.yaml` — design concept template (narrative, style signals, 60-30-10
  palette roles, material master list, lighting philosophy, budget tier allocation
  anchor 60 / supporting 25 / accent 15, room hierarchy).
- Registry fields: `category`, `style` tags, `palette_role`, `visual_weight`, `mass`,
  `seat_height`, `lumens`, `color_temp_k`, `currency`, `rejected_reason`.
- `hooks/on_room_edit.py` — PostToolUse hook auto-validates `rooms/*.yaml` after Write/Edit
  (ERRORs block, WARNs surface as context, fails silently otherwise).
- Catalog: enriched filterable metadata (dims, category, material, color family, style),
  `catalog_get` MCP tool, richer `catalog_stats`, `enrich` export/import CLI,
  `CATALOG_DB_PATH` resolution via plugin user config (`catalog_db_path` in plugin.json).
- Multi-criteria selection rubric (slot brief → hard gates → weighted scores → top-3
  with per-criterion justification) in `select` + `furniture-curator`.
- `docs/architecture.md` — single source of truth for schemas, rule IDs, and conventions.
- This changelog.

### Changed

- All numeric clearances moved out of prose into `scripts/rules/clearances.yaml`; skills,
  templates, and checklist now cite rule IDs instead of restating numbers.
- `hooks/hooks.json` rewritten to the documented nested schema (SessionStart + PostToolUse,
  quoted `${CLAUDE_PLUGIN_ROOT}`/`${CLAUDE_PLUGIN_DATA}`, status messages).
- `templates/CLAUDE.md` doctrine: phase discipline rule, phase/skill table, budget
  allocation doctrine, rules-engine citation discipline.
- `templates/brief.yaml`: budget section now carries a numeric `total:` + `currency:`
  (concept derives tier allocation from it).
- `templates/design-checklist.yaml`: numeric target bands (floor coverage 20-40% living /
  30-50% bedroom), CIRC rule citations, lighting-layer and 60-30-10 palette-role checks.
- `templates/workflow.md`: 9-phase design process with artifacts and back-edges prepended.
- Skill frontmatter normalized (`argument-hint`, `allowed-tools`, `when_to_use`,
  `disable-model-invocation` where appropriate); `review` forks `design-reviewer`.
- Sample project (Casa Sol) upgraded to the new format and made exemplary (passes its
  own validation).
- `plugin.json`: v1.0.0, `displayName`, `homepage`/`repository`, `userConfig.catalog_db_path`.

### Fixed

- `templates/rooms/_template.yaml`: furniture placement examples were misindented under
  `accessories:` — restored under `furniture:`.

All new project-format fields are optional — projects created with 0.x keep working;
checks that need missing data are skipped and reported as such.

## [0.2.0]

### Added

- MCP server for catalog search (`planhaus-catalog`, runs on host, bypasses VM limits)
  exposing `catalog_search` and `catalog_stats`.
- ONNX embedding model bundled with the catalog DB for offline search.

### Changed

- Simplified `search` skill: explain constraints, let the agent handle mechanics.

### Fixed

- Read-only filesystem error in the Cowork VM (deps install to `${CLAUDE_PLUGIN_DATA}`).

## [0.1.1]

### Fixed

- Version metadata corrected to 0.1.1; release management documented in `CLAUDE.md`.

## [0.1.0]

### Added

- Initial release: 8 skills (`setup`, `new-project`, `validate`, `render`, `position`,
  `search`, `review`, `add-item`), `room_spatial.py` spatial tool, project templates,
  catalog tooling, sample project ("Casa Sol").
