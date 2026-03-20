# Data Collection

## Phase 1: From Plans (Remote)

- Official room areas (m²) - ground truth
- All wall dimensions (identify which wall each belongs to)
- Room shapes (draw ASCII)
- Door/window positions
- Room adjacencies - which rooms share walls

## Phase 2: On-Site

- Outlets (position, type, height)
- Switches
- Door swing directions
- Radiators, plumbing
- Verify dimensions that were unclear in plans

---

## Floor Plan Validation

### The Problem

LLMs see `4.90` and `3.40` and assume rectangle. But the room might be L-shaped!

### The Fix

1. **Draw first** - ASCII diagram with labeled corners (A, B, C...)
2. **Map dimensions to walls** - each measurement belongs to a wall
3. **Define walls** - direction (east/north/west/south) + length
4. **Trace closes?** - last wall must return to origin
5. **Area matches?** - calculated from walls ≈ official (±5%)

```yaml
# Example: L-shaped living room
ascii: |
  E──────────F
  │  Living  │
  D          │
  │──C       │
     │Kitchen│
     A───────B

walls:
  - id: A-B
    direction: east
    length: 340
  - id: B-F
    direction: north
    length: 651
  # ... continue around perimeter

validation:
  trace_closes: true
  calculated_area: 27.79
  area_difference_pct: 0
  area_matches: true
```

---

## Time Estimates

| Size | Plans | On-site |
|------|-------|---------|
| 1+kk | 30min | 1-2h |
| 2+kk | 1h | 2-3h |
| 3+kk | 1-2h | 3-4h |
