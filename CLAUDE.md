# planhaus development

Cowork plugin for interior design. Repo = the plugin itself (not a project using it).

## Structure

- `skills/*/SKILL.md` — 8 skills, invoked as `/planhaus:<name>` in Cowork
- `scripts/` — Python CLI tools (room_spatial.py, catalog/). Standalone, no code changes needed for plugin use.
- `templates/` — project scaffolding copied by `/planhaus:new-project`
- `templates/CLAUDE.md` — design rules injected into user projects (not this file)
- `sample-project/` — demo project ("Casa Sol"), used for testing skills
- `.claude-plugin/` — plugin.json (manifest) + marketplace.json (for Cowork install)
- `hooks/hooks.json` — SessionStart auto-installs pyyaml + matplotlib

## Key conventions

- Skills reference scripts via `${CLAUDE_PLUGIN_ROOT}/scripts/...`
- Coordinates: origin SW corner, X=East, Y=North, cm. Position uses two perpendicular walls + offsets.
- `plugin.json` author must be object `{"name": "..."}`, not string (Cowork validation)
- After changing sample-project rooms, regenerate PNGs: `python3 scripts/room_spatial.py sample-project/rooms/<room>.yaml --plot sample-project/rooms/<room>-floorplan.png`

## Testing

```bash
# Local CLI
claude --plugin-dir .

# In Cowork: install via marketplace pepuscz/planhaus
# Test in sample-project/
/planhaus:validate living-room
/planhaus:render living-room
```
