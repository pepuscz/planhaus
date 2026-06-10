# planhaus development

Cowork/Claude Code plugin for interior design. Repo = the plugin itself (not a project using it).

## Structure

- `docs/architecture.md` — single source of truth for schemas, rule IDs, skill contracts. Read it before changing anything.
- `skills/*/SKILL.md` — 15 skills, invoked as `/planhaus:<name>` (phases: brief → concept → zone → furnish → select → light → review, plus validate/render/position/search/add-item/enrich-catalog/new-project/setup)
- `agents/*.md` — 4 subagents: design-researcher, space-planner, furniture-curator, design-reviewer (fork target of `review`)
- `scripts/` — Python CLI tools (room_spatial.py, catalog/). Standalone, no code changes needed for plugin use.
- `scripts/rules/clearances.yaml` — canonical numeric rule table (CIRC-01, SEAT-01, …); the ONLY place clearance numbers live
- `templates/` — project scaffolding copied by `/planhaus:new-project` (incl. concept.yaml)
- `templates/CLAUDE.md` — design doctrine injected into user projects (not this file)
- `sample-project/` — demo project ("Casa Sol"), used for testing skills; must pass its own validation
- `.claude-plugin/` — plugin.json (manifest + userConfig) + marketplace.json (for Cowork install)
- `hooks/hooks.json` — documented nested schema: SessionStart (dep installs) + PostToolUse (`hooks/on_room_edit.py` auto-validates rooms/*.yaml after Write|Edit)
- `.mcp.json` — MCP server config: `planhaus-catalog` runs on host, exposes `catalog_search`, `catalog_get`, `catalog_stats`; `CATALOG_DB_PATH` from `${user_config.catalog_db_path}`

## Key conventions

- Skills reference scripts via `${CLAUDE_PLUGIN_ROOT}/scripts/...` (always quoted in shell: `"${CLAUDE_PLUGIN_ROOT}"`)
- Rule IDs: numeric checks live in `scripts/rules/clearances.yaml`; skills/templates cite `SEVERITY RULE-ID: detail` and never restate numbers
- Coordinates: origin SW corner, X=East, Y=North, cm. Position uses two perpendicular walls + offsets.
- New room YAML fields are all OPTIONAL (zones, focal_point, circulation, sightlines; type/zone on furniture; layer/color_temp_k/lumens on lighting) — old projects must keep working, missing data → SKIP not ERROR
- `plugin.json` author must be object `{"name": "..."}`, not string (Cowork validation)
- After changing sample-project rooms, regenerate PNGs: `python3 scripts/room_spatial.py sample-project/rooms/<room>.yaml --plot sample-project/rooms/<room>-floorplan.png`

## Testing

```bash
# Local CLI
claude --plugin-dir .

# Manifest/structure check (if available in your CLI version)
claude plugin validate . --strict

# Rules-engine smoke test (must produce zero ERRORs on sample project)
python3 scripts/room_spatial.py sample-project/rooms/living-room.yaml --check
python3 scripts/room_spatial.py sample-project/rooms/bedroom.yaml --check

# In Cowork: install via marketplace pepuscz/planhaus
# Test in sample-project/
/planhaus:validate living-room
/planhaus:render living-room
```

## Releasing

Cowork detects updates by comparing the `version` in `.claude-plugin/plugin.json`.

1. Bump `version` in `.claude-plugin/plugin.json` (semver: MAJOR.MINOR.PATCH)
2. Update `CHANGELOG.md`
3. Commit and push to main
4. In Cowork: plugin shows "Update" button when remote version > installed version

No version bump = no update visible to users. Always bump when pushing changes that affect skills, scripts, hooks, or templates.

Version guide:
- PATCH (1.0.x): bug fixes, typos, minor script tweaks
- MINOR (1.x.0): new skills, significant script changes, template updates
- MAJOR (x.0.0): breaking changes to project format or skill interfaces

The 1.0.0 release (this upgrade) is MAJOR: new workflow contract + project-format additions.
Release checklist for 1.0.0: `claude plugin validate . --strict`, `--check` on both sample
rooms, smoke-test in Cowork (hooks fire, MCP tools appear, forked review runs).
