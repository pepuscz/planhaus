---
name: render
description: Render a room floorplan PNG from its YAML specification
args: "<room-name>"
---

# Render Room Floorplan

Generate a visual floor plan PNG for a room.

## Steps

1. Find the room YAML file. Look for:
   - `rooms/<room-name>.yaml` in the current project directory
   - Or the exact path if the user provides one

2. Run the spatial tool to generate the floorplan:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/room_spatial.py rooms/<room-name>.yaml --plot rooms/<room-name>-floorplan.png
   ```

3. Read the generated PNG and show it to the user.

4. Report any warnings from the tool output (collisions, out-of-bounds items).

## Notes

- The tool requires `pyyaml` and `matplotlib`. Run `/planhaus:setup` first if not installed.
- The PNG shows: room outline, furniture bounding boxes, windows, openings, outlets, lighting.
- Directional items (sofa, bed, TV) show a red arrow indicating facing direction.
- Re-render after any changes to room YAML.
