---
name: review
description: Run design integration checklist for a room or the whole apartment
args: "<room-name|apartment>"
---

# Design Review

Assess design coherence using the integration checklist.

## Steps

1. Read the design checklist:
   ```
   ${CLAUDE_PLUGIN_ROOT}/templates/design-checklist.yaml
   ```

2. If reviewing a **single room** (`/planhaus:review living-room`):
   - Read `rooms/<room-name>.yaml`
   - Read the room's registry items
   - Run `/planhaus:position <room> --matrix` to get distances
   - Assess each `per_room` checklist item:
     - **Density**: Calculate floor coverage (furniture footprint / room area)
     - **Focal point**: Is there one clear visual anchor?
     - **Flow**: Are circulation paths clear (60-80cm minimum)?
     - **Light**: Sufficient lighting for the room's purpose?
     - **Breathing room**: Do key pieces have space around them?

3. If reviewing the **apartment** (`/planhaus:review apartment`):
   - Read `apartment.yaml` and all room files
   - Assess `per_apartment` checklist items:
     - **Material palette**: Count unique materials (aim for 3-5 main ones)
     - **Transitions**: Do adjacent rooms feel connected?
     - **Sightlines**: What's visible through openings?
     - **Style thread**: Is there a clear identity matching the brief?
     - **Hierarchy**: Does design emphasis match room importance?

4. End with the reflective questions from the checklist.

## Notes

- Review is qualitative design judgment, not just tool output.
- Reference specific items, positions, and measurements in your assessment.
- Flag conflicts and suggest specific improvements.
