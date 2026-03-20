---
name: validate
description: Validate room geometry — trace closure, area match, collision detection
args: "<room-name>"
---

# Validate Room

Check that a room's geometry is correct and furniture doesn't collide.

## Steps

1. Find and read the room YAML file (`rooms/<room-name>.yaml`).

2. Run the spatial tool to compute positions and check for issues:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/room_spatial.py rooms/<room-name>.yaml
   ```

3. Check the output for:
   - **Trace closure**: Does the wall trace return to origin? (MUST be true)
   - **Area match**: Is calculated area within 5% of official `area_m2`?
   - **Validation warnings**: Any items outside room bounds or overlapping?

4. Also verify in the YAML:
   - `validation.trace_closes` is `true`
   - `validation.area_matches` is `true`
   - `validation.area_difference_pct` is under 5

5. Report results clearly:
   - **PASS**: geometry valid, no collisions
   - **FAIL**: list each issue with details

## Notes

- Always validate before doing design work on a room.
- The tool checks floor-level collisions only — wall-mounted items (mount: wall) and surface items (on: base-id) are excluded.
- A passing validation means geometry is correct, NOT that the design is good.
