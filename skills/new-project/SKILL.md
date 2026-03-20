---
name: new-project
description: Scaffold a new interior design project from templates
args: "<project-name>"
---

# New Project

Create a new interior design project with all required files.

## Steps

1. Parse the project name from the argument. If no name given, ask the user.

2. Copy the template directory to create the project:
   ```bash
   cp -r ${CLAUDE_PLUGIN_ROOT}/templates/ <project-name>/
   ```

3. The new project will contain:
   - `CLAUDE.md` — design rules and conventions
   - `brief.yaml` — client profile template (fill in first)
   - `apartment.yaml` — apartment layout template
   - `rooms/_template.yaml` — room specification template
   - `registry/_template.yaml` — product registry template
   - `design-checklist.yaml` — design integration checklist
   - `workflow.md` — data collection workflow

4. Tell the user to start by filling in `brief.yaml` (their north star), then `apartment.yaml`.

## Notes

- The CLAUDE.md contains all design conventions and coordinate system rules.
- brief.yaml should be filled by the client — keep it high-level.
- For each room, copy `rooms/_template.yaml` to `rooms/<room-name>.yaml`.
- For each product candidate, copy `registry/_template.yaml` to `registry/<category>/<item>.yaml`.
