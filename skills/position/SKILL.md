---
name: position
description: Check spatial positions, edge-to-edge distances, and distance matrix
args: "<room-name> [--gap id1 id2] [--matrix]"
---

# Position / Distances

Query spatial positions and distances between items in a room.

## Modes

### Default: All positions
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/room_spatial.py rooms/<room-name>.yaml
```
Shows absolute (x, y) coordinates for all items, plus footprint summary.

### Gap between two items (`--gap`)
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/room_spatial.py rooms/<room-name>.yaml --gap <item1> <item2>
```
Shows edge-to-edge distance between two specific items. Both items need dimensions.

### Full distance matrix (`--matrix`)
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/room_spatial.py rooms/<room-name>.yaml --matrix
```
Shows all pairwise edge-to-edge distances between furniture/built-ins, plus distances to walls. Sorted by distance (closest first).

## Notes

- Coordinates: origin (0,0) at SW corner, X=East, Y=North, units=cm.
- Edge-to-edge = gap between closest edges of bounding boxes (not center-to-center).
- Items without dimensions (lights, outlets) appear in positions but not in gap/matrix.
- Use `--matrix` to check circulation clearances (aim for 60-80cm walkways).
