# planhaus

Interior design plugin for Claude Cowork.

Spatial reasoning, room geometry validation, product catalog search, and 60-30-10 composition framework — all driven by YAML specs and Python tools.

## Install

```
/plugin install planhaus
```

## Quick Start

1. `/planhaus:setup` — install dependencies
2. `/planhaus:new-project my-apartment` — scaffold a project
3. Fill in `brief.yaml` (client profile) and `apartment.yaml` (layout)
4. Create rooms, validate: `/planhaus:validate living-room`
5. Position furniture, render: `/planhaus:render living-room`
6. Review coherence: `/planhaus:review apartment`

## Try the Demo

Open `sample-project/` to explore a complete example with 2 rooms and 10 registry items.

## Skills

| Skill | Purpose |
|-------|---------|
| `/planhaus:setup` | Install Python dependencies |
| `/planhaus:new-project` | Scaffold from templates |
| `/planhaus:render` | Render room floorplan PNG |
| `/planhaus:validate` | Validate room geometry |
| `/planhaus:position` | Check positions/distances |
| `/planhaus:search` | Query product catalog |
| `/planhaus:review` | Design integration checklist |
| `/planhaus:add-item` | Add product to registry |

## How It Works

- **Rooms** are defined in YAML with wall geometry (direction + length), furniture positions (wall-relative offsets), and design intent.
- **Registry** items describe products with dimensions, materials, and objective specs.
- The **spatial tool** (`scripts/room_spatial.py`) computes absolute coordinates, checks collisions, and renders floorplan PNGs.
- **Design rules** (60-30-10 composition, validation checklist) are injected via `CLAUDE.md` in each project.

## Product Catalog (Optional)

The plugin includes catalog search tools but not product data. Build your own:

```bash
pip install -r scripts/catalog/requirements.txt
python scripts/catalog/catalog_vectordb.py build --source <data.json>
```

## License

MIT
