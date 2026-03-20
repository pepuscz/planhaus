#!/usr/bin/env python3
"""
Room Spatial Tool - Compute absolute positions from wall-relative YAML.

Usage:
  python room_spatial.py <room.yaml>                         # All positions
  python room_spatial.py <room.yaml> --view x,y              # View from point to edges
  python room_spatial.py <room.yaml> --gap item1 item2       # Edge-to-edge distance
  python room_spatial.py <room.yaml> --matrix                # All edge-to-edge distances
  python room_spatial.py <room.yaml> --plot [output.png]     # Floor plan image

--view:   distance from a POINT to object edges (use for viewpoints)
--gap:    distance EDGE-TO-EDGE between two items (use for furniture gaps)
--matrix: all pairwise edge-to-edge distances (furniture/built-ins only)
"""

import yaml
import sys
import math
from pathlib import Path

DIRECTIONS = {
    'north': (0, 1),
    'south': (0, -1),
    'east': (1, 0),
    'west': (-1, 0),
}

def trace_corners(walls):
    """Trace walls to compute corner coordinates. Origin at first corner."""
    # Get first corner name from first wall
    first_wall = walls[0]['id']
    first_corner = first_wall.split('-')[0]
    
    corners = {first_corner: (0, 0)}
    pos = [0, 0]
    
    for wall in walls:
        wall_id = wall['id']
        start, end = wall_id.split('-')
        dx, dy = DIRECTIONS[wall['direction']]
        length = wall['length']
        
        pos[0] += dx * length
        pos[1] += dy * length
        
        # Don't overwrite origin
        if end != first_corner:
            corners[end] = tuple(pos)
    
    # Check closure
    closure_gap = math.sqrt(pos[0]**2 + pos[1]**2)
    if closure_gap > 1:
        print(f"# WARNING: Trace doesn't close! Gap: {closure_gap:.0f}cm")
    
    return corners

def resolve_position(pos, corners, item_id=None):
    """Convert wall-relative position to absolute (x, y).
    
    Position is defined by two PERPENDICULAR reference walls and offsets.
    - offset[0] = perpendicular distance from wall[0] INTO the room
    - offset[1] = perpendicular distance from wall[1] INTO the room
    
    Walls trace clockwise around room, so "into room" = left of wall direction.
    Walls MUST be perpendicular - parallel walls cannot define a unique position.
    """
    if isinstance(pos, dict):
        if 'wall' in pos and 'offset' in pos:
            walls = pos['wall']
            offsets = pos['offset']
            
            # Wall 1
            w1_start, w1_end = walls[0].split('-')
            w1_s = corners[w1_start]
            w1_e = corners[w1_end]
            w1_vec = (w1_e[0] - w1_s[0], w1_e[1] - w1_s[1])
            w1_len = math.sqrt(w1_vec[0]**2 + w1_vec[1]**2)
            # Perpendicular into room = rotate 90° counterclockwise
            w1_perp = (-w1_vec[1]/w1_len, w1_vec[0]/w1_len)
            
            # Wall 2
            w2_start, w2_end = walls[1].split('-')
            w2_s = corners[w2_start]
            w2_e = corners[w2_end]
            w2_vec = (w2_e[0] - w2_s[0], w2_e[1] - w2_s[1])
            w2_len = math.sqrt(w2_vec[0]**2 + w2_vec[1]**2)
            w2_perp = (-w2_vec[1]/w2_len, w2_vec[0]/w2_len)
            
            # Check if walls are perpendicular (dot product ≈ 0)
            dot = (w1_vec[0] * w2_vec[0] + w1_vec[1] * w2_vec[1]) / (w1_len * w2_len)
            
            if abs(dot) > 0.1:
                # Walls are parallel - INVALID per spec
                name = item_id or "unknown"
                print(f"# WARNING: {name} uses parallel walls {walls} - position undefined!")
                return None
            
            # Walls are perpendicular - use intersection of offset lines
            # Wall1 is vertical (N-S) → sets x; Wall1 is horizontal (E-W) → sets y
            x, y = 0, 0
            
            if abs(w1_vec[0]) < 0.1:  # Wall1 vertical, sets x
                x = w1_s[0] + w1_perp[0] * offsets[0]
            else:  # Wall1 horizontal, sets y
                y = w1_s[1] + w1_perp[1] * offsets[0]
            
            if abs(w2_vec[0]) < 0.1:  # Wall2 vertical, sets x
                x = w2_s[0] + w2_perp[0] * offsets[1]
            else:  # Wall2 horizontal, sets y
                y = w2_s[1] + w2_perp[1] * offsets[1]
            
            return (round(x), round(y))
    
    return None

def load_room(path):
    """Load and parse room YAML."""
    with open(path) as f:
        return yaml.safe_load(f)

def load_registry(room_path, registry_path):
    """Load registry YAML relative to room file's project root."""
    if not registry_path:
        return None
    # Find project root (parent of 'rooms' directory)
    room_file = Path(room_path)
    project_root = room_file.parent.parent
    full_path = project_root / registry_path
    if full_path.exists():
        with open(full_path) as f:
            return yaml.safe_load(f)
    return None

def vec_to_axis(vec):
    """Convert unit vector to axis label (N-S or E-W)."""
    if abs(vec[1]) > abs(vec[0]):
        return 'N-S'  # primarily vertical
    else:
        return 'E-W'  # primarily horizontal

def vec_to_cardinal(vec):
    """Convert unit vector to cardinal direction (north/south/east/west)."""
    if abs(vec[1]) > abs(vec[0]):
        return 'north' if vec[1] > 0 else 'south'
    else:
        return 'east' if vec[0] > 0 else 'west'

def get_wall_directions(walls_ref, corners):
    """Get unit vectors for wall pair. Returns (along, perp, width_axis, facing)."""
    w1_start, w1_end = walls_ref[0].split('-')
    w1_vec = (
        corners[w1_end][0] - corners[w1_start][0],
        corners[w1_end][1] - corners[w1_start][1]
    )
    w1_len = math.sqrt(w1_vec[0]**2 + w1_vec[1]**2)
    along = (w1_vec[0]/w1_len, w1_vec[1]/w1_len)
    
    # Perpendicular (rotate 90° counterclockwise for "into room")
    perp = (-along[1], along[0])
    
    # Width axis = direction the first dimension (width) runs along
    width_axis = vec_to_axis(along)
    # Facing = direction the front points (perpendicular into room)
    facing = vec_to_cardinal(perp)
    
    return along, perp, width_axis, facing

def compute_bbox(pos, dims, along, perp):
    """Compute bounding box corners from position, dimensions, and directions.
    
    Position is the corner of object nearest to reference walls.
    Object extends in 'along' direction by width, in 'perp' direction by depth.
    """
    if not dims:
        return None
    
    width = dims.get('width', dims.get('length', 100))
    depth = dims.get('depth', dims.get('length', 50))
    
    # Four corners of bounding box
    corners = [
        pos,  # origin corner
        (pos[0] + along[0] * width, pos[1] + along[1] * width),
        (pos[0] + along[0] * width + perp[0] * depth, pos[1] + along[1] * width + perp[1] * depth),
        (pos[0] + perp[0] * depth, pos[1] + perp[1] * depth),
    ]
    return corners

def rotate_bbox(bbox, center, angle_deg):
    """Rotate bbox corners around center by angle (degrees, clockwise).
    
    Returns None if bbox is None or angle is 0/None.
    """
    if not bbox or not angle_deg:
        return bbox
    rad = math.radians(-angle_deg)  # negative for clockwise
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    result = []
    for p in bbox:
        dx, dy = p[0] - center[0], p[1] - center[1]
        result.append((
            center[0] + dx * cos_a - dy * sin_a,
            center[1] + dx * sin_a + dy * cos_a
        ))
    return result

def closest_point_on_bbox(bbox, point):
    """Find closest point on bounding box to a given point."""
    if not bbox:
        return None
    
    # Simple approach: check distance to each edge and find minimum
    min_dist = float('inf')
    closest = None
    
    for i in range(4):
        p1 = bbox[i]
        p2 = bbox[(i + 1) % 4]
        
        # Project point onto line segment
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        length_sq = dx*dx + dy*dy
        if length_sq == 0:
            closest_on_seg = p1
        else:
            t = max(0, min(1, ((point[0] - p1[0]) * dx + (point[1] - p1[1]) * dy) / length_sq))
            closest_on_seg = (p1[0] + t * dx, p1[1] + t * dy)
        
        dist = math.sqrt((point[0] - closest_on_seg[0])**2 + (point[1] - closest_on_seg[1])**2)
        if dist < min_dist:
            min_dist = dist
            closest = closest_on_seg
    
    return closest, min_dist

def segment_to_segment_distance(p1, p2, p3, p4):
    """Minimum distance between two line segments (p1-p2) and (p3-p4)."""
    def point_to_segment_dist(px, py, ax, ay, bx, by):
        dx, dy = bx - ax, by - ay
        length_sq = dx*dx + dy*dy
        if length_sq == 0:
            return math.sqrt((px - ax)**2 + (py - ay)**2)
        t = max(0, min(1, ((px - ax)*dx + (py - ay)*dy) / length_sq))
        proj_x, proj_y = ax + t*dx, ay + t*dy
        return math.sqrt((px - proj_x)**2 + (py - proj_y)**2)
    
    # Check all endpoints against the other segment
    d1 = point_to_segment_dist(p1[0], p1[1], p3[0], p3[1], p4[0], p4[1])
    d2 = point_to_segment_dist(p2[0], p2[1], p3[0], p3[1], p4[0], p4[1])
    d3 = point_to_segment_dist(p3[0], p3[1], p1[0], p1[1], p2[0], p2[1])
    d4 = point_to_segment_dist(p4[0], p4[1], p1[0], p1[1], p2[0], p2[1])
    return min(d1, d2, d3, d4)

def bbox_to_bbox_distance(bbox1, bbox2):
    """Minimum edge-to-edge distance between two bounding boxes."""
    if not bbox1 or not bbox2:
        return None
    
    min_dist = float('inf')
    for i in range(4):
        for j in range(4):
            d = segment_to_segment_distance(
                bbox1[i], bbox1[(i+1) % 4],
                bbox2[j], bbox2[(j+1) % 4]
            )
            min_dist = min(min_dist, d)
    return min_dist

def point_in_polygon(point, polygon, tolerance=5):
    """Check if point is inside polygon (with tolerance for boundary points).
    
    Uses ray casting but also checks if point is within tolerance of any edge.
    """
    x, y = point
    n = len(polygon)
    
    # First check if on or near any edge (within tolerance)
    for i in range(n):
        p1 = polygon[i]
        p2 = polygon[(i + 1) % n]
        
        # Distance from point to line segment
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        length_sq = dx*dx + dy*dy
        if length_sq == 0:
            # Degenerate segment
            dist = math.sqrt((x - p1[0])**2 + (y - p1[1])**2)
        else:
            t = max(0, min(1, ((x - p1[0])*dx + (y - p1[1])*dy) / length_sq))
            proj_x = p1[0] + t * dx
            proj_y = p1[1] + t * dy
            dist = math.sqrt((x - proj_x)**2 + (y - proj_y)**2)
        
        if dist <= tolerance:
            return True  # On or near boundary - counts as inside
    
    # Standard ray casting for points clearly inside
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    
    return inside

def bbox_overlaps(bbox1, bbox2):
    """Check if two oriented bounding boxes overlap using Separating Axis Theorem.
    
    Works correctly for rotated rectangles - no false positives from AABB approximation.
    """
    if not bbox1 or not bbox2:
        return False
    
    def get_edges(bbox):
        """Get edge vectors for the polygon."""
        edges = []
        for i in range(len(bbox)):
            p1, p2 = bbox[i], bbox[(i + 1) % len(bbox)]
            edges.append((p2[0] - p1[0], p2[1] - p1[1]))
        return edges
    
    def get_normals(edges):
        """Get perpendicular normals to edges (potential separating axes)."""
        normals = []
        for edge in edges:
            # Perpendicular: rotate 90°
            normals.append((-edge[1], edge[0]))
        return normals
    
    def project(bbox, axis):
        """Project all points onto axis, return (min, max)."""
        dots = [p[0] * axis[0] + p[1] * axis[1] for p in bbox]
        return min(dots), max(dots)
    
    def overlaps_on_axis(bbox1, bbox2, axis):
        """Check if projections overlap on given axis."""
        min1, max1 = project(bbox1, axis)
        min2, max2 = project(bbox2, axis)
        return max1 > min2 and max2 > min1
    
    # Get all potential separating axes (edge normals from both boxes)
    axes = get_normals(get_edges(bbox1)) + get_normals(get_edges(bbox2))
    
    # If we find ANY axis where projections don't overlap, boxes don't overlap
    for axis in axes:
        if not overlaps_on_axis(bbox1, bbox2, axis):
            return False
    
    # No separating axis found - boxes overlap
    return True

def validate_objects(objects, corners, room):
    """Check for objects outside room or overlapping. Returns list of warnings."""
    warnings = []
    
    # Build room polygon from corners in wall order (traced correctly)
    room_polygon = []
    walls = room.get('walls', [])
    if walls:
        # Get corner order from wall IDs
        for wall in walls:
            start = wall['id'].split('-')[0]
            if start in corners:
                room_polygon.append(corners[start])
    
    if len(room_polygon) < 3:
        # Fallback - can't validate
        return warnings
    
    # Check each object with bbox
    for obj in objects:
        if not obj.get('bbox'):
            continue
        
        bbox = obj['bbox']
        obj_id = obj['id']
        
        # Wall-mounted items are allowed to extend slightly outside room boundary
        # (they're on the wall, not on the floor)
        if obj.get('mount') == 'wall':
            continue  # Skip boundary check for wall-mounted items
        
        # Items on surfaces don't need floor boundary checks
        if obj.get('on'):
            continue  # Skip boundary check for on-surface items
        
        # Check if any corner of bbox is outside room
        for i, corner in enumerate(bbox):
            if not point_in_polygon(corner, room_polygon):
                warnings.append(f"# WARNING: {obj_id} extends outside room (corner {i+1} at {corner[0]:.0f},{corner[1]:.0f})")
                break  # One warning per object
    
    # Check for overlaps between objects
    # Skip overlap checks for items at different heights:
    # - wall-mounted vs floor-standing
    # - on-surface items vs floor items
    # - on-surface item vs its base object
    objects_with_bbox = [o for o in objects if o.get('bbox')]
    for i, obj1 in enumerate(objects_with_bbox):
        for obj2 in objects_with_bbox[i+1:]:
            # Skip if one is wall-mounted and the other is floor-standing
            obj1_wall = obj1.get('mount') == 'wall'
            obj2_wall = obj2.get('mount') == 'wall'
            if obj1_wall != obj2_wall:
                continue  # Different mount types - no collision possible
            
            # Skip if either is on a surface (different height layer)
            obj1_on = obj1.get('on')
            obj2_on = obj2.get('on')
            if obj1_on or obj2_on:
                # Skip collision between surface item and floor items
                # Also skip if surface item is on the other object
                if obj1_on == obj2['id'] or obj2_on == obj1['id']:
                    continue  # Item is ON the other object
                if obj1_on and not obj2_on:
                    continue  # obj1 is on surface, obj2 is on floor
                if obj2_on and not obj1_on:
                    continue  # obj2 is on surface, obj1 is on floor
            
            if bbox_overlaps(obj1['bbox'], obj2['bbox']):
                # Show actual bounds for debugging
                def bounds(bbox):
                    xs = [p[0] for p in bbox]
                    ys = [p[1] for p in bbox]
                    return f"x:{min(xs):.0f}-{max(xs):.0f}, y:{min(ys):.0f}-{max(ys):.0f}"
                warnings.append(f"# WARNING: {obj1['id']} [{bounds(obj1['bbox'])}] overlaps with {obj2['id']} [{bounds(obj2['bbox'])}]")
    
    return warnings

def get_objects(room, corners, room_path=None):
    """Extract all positioned objects with absolute coordinates and bounding boxes."""
    objects = []
    
    # Built-ins
    for item in room.get('built_ins', []):
        if 'position' in item and isinstance(item['position'], dict):
            pos = resolve_position(item['position'], corners, item.get('id'))
            dims = item.get('dimensions', {})
            mass = item.get('mass')  # kg
            bbox = None
            width_axis = None
            facing = None
            
            # STRICT: Require explicit orientation or facing (no wall-derived fallback)
            if item.get('orientation'):
                width_axis = item['orientation'].upper()  # N-S or E-W
                if width_axis not in ('N-S', 'E-W'):
                    print(f"# ERROR: {item['id']} has invalid orientation '{width_axis}' - must be N-S or E-W", file=sys.stderr)
                    continue
            if item.get('facing'):
                facing = item['facing'].lower()  # north/south/east/west
                if facing not in ('north', 'south', 'east', 'west'):
                    print(f"# ERROR: {item['id']} has invalid facing '{facing}' - must be north/south/east/west", file=sys.stderr)
                    continue
            
            # Compute bbox only if orientation is explicitly specified
            if pos and dims:
                if not width_axis and not facing:
                    print(f"# WARNING: {item['id']} has dimensions but no orientation/facing - bbox skipped", file=sys.stderr)
                elif facing:
                    perp_map = {'north': (0, 1), 'south': (0, -1), 'east': (1, 0), 'west': (-1, 0)}
                    face_dir = perp_map[facing]
                    along = (-face_dir[1], face_dir[0])
                    perp = face_dir
                    bbox = compute_bbox(pos, dims, along, perp)
                elif width_axis:
                    if width_axis == 'N-S':
                        along = (0, 1)
                        perp = (1, 0)
                    else:  # E-W
                        along = (1, 0)
                        perp = (0, 1)
                    bbox = compute_bbox(pos, dims, along, perp)
            
            if pos:
                objects.append({
                    'type': 'built_in',
                    'id': item['id'],
                    'pos': pos,
                    'dims': dims,
                    'bbox': bbox,
                    'width_axis': width_axis,
                    'facing': facing,
                    'mass': mass,  # kg (None if unknown)
                    'mount': item.get('mount'),  # 'wall' for wall-mounted items
                })
        elif 'wall' in item and 'position' in item:
            # Wall-mounted built-in
            wall_id = item['wall']
            start, end = wall_id.split('-')
            start_pos = corners[start]
            end_pos = corners[end]
            dx = end_pos[0] - start_pos[0]
            dy = end_pos[1] - start_pos[1]
            length_val = math.sqrt(dx**2 + dy**2)
            unit = (dx/length_val, dy/length_val)
            # Perpendicular into room (rotate 90° counterclockwise)
            perp = (-unit[1], unit[0])
            
            offset = item['position']
            x = start_pos[0] + unit[0] * offset
            y = start_pos[1] + unit[1] * offset
            
            # Compute bbox if length and depth are specified
            bbox = None
            item_length = item.get('length')
            item_depth = item.get('depth')
            if item_length and item_depth:
                # Rectangle along wall, extending into room
                p1 = (x, y)  # start corner on wall
                p2 = (x + unit[0] * item_length, y + unit[1] * item_length)  # end along wall
                p3 = (p2[0] + perp[0] * item_depth, p2[1] + perp[1] * item_depth)  # into room
                p4 = (p1[0] + perp[0] * item_depth, p1[1] + perp[1] * item_depth)  # into room
                bbox = [p1, p2, p3, p4]
            
            objects.append({
                'type': 'built_in',
                'id': item['id'],
                'pos': (round(x), round(y)),
                'length': item_length,
                'depth': item_depth,
                'bbox': bbox,
                'mass': item.get('mass'),  # kg (None if unknown)
            })
    
    # Lighting (ceiling fixtures - point objects, no bbox)
    for item in room.get('lighting', []):
        pos = resolve_position(item.get('position'), corners, item.get('id'))
        if pos:
            objects.append({
                'type': 'light',
                'id': item['id'],
                'pos': pos,
                'ceiling': item.get('ceiling'),
                'bbox': None,
            })
    
    # Furniture (with registry lookup for dimensions and mass)
    for item in room.get('furniture', []):
        pos = resolve_position(item.get('position'), corners, item.get('id'))
        if pos:
            # Get dimensions and mass from registry or inline
            dims = item.get('dimensions', {})
            mass = item.get('mass')  # kg
            reg = None
            if room_path and item.get('registry'):
                reg = load_registry(room_path, item['registry'])
                if reg:
                    if not dims:
                        dims = reg.get('dimensions', {})
                    if mass is None:
                        mass = reg.get('mass')  # kg
            
            bbox = None
            width_axis = None
            facing = None
            
            # STRICT: Require explicit orientation or facing (no wall-derived fallback)
            if item.get('orientation'):
                width_axis = item['orientation'].upper()  # N-S or E-W
                if width_axis not in ('N-S', 'E-W'):
                    print(f"# ERROR: {item['id']} has invalid orientation '{width_axis}' - must be N-S or E-W", file=sys.stderr)
                    continue
            if item.get('facing'):
                facing = item['facing'].lower()  # north/south/east/west
                if facing not in ('north', 'south', 'east', 'west'):
                    print(f"# ERROR: {item['id']} has invalid facing '{facing}' - must be north/south/east/west", file=sys.stderr)
                    continue
            
            # Compute bbox only if orientation is explicitly specified
            rotation = item.get('rotation', 0)
            if dims:
                if not width_axis and not facing:
                    print(f"# WARNING: {item['id']} has dimensions but no orientation/facing - bbox skipped", file=sys.stderr)
                elif facing:
                    # Position is corner nearest to reference walls (consistent with orientation items)
                    # For facing items: width runs perpendicular to facing, depth projects in facing direction
                    perp_map = {'north': (0, 1), 'south': (0, -1), 'east': (1, 0), 'west': (-1, 0)}
                    face_dir = perp_map[facing]
                    # along = perpendicular to facing (width runs along this axis)
                    along = (-face_dir[1], face_dir[0])
                    perp = face_dir
                    bbox = compute_bbox(pos, dims, along, perp)
                elif width_axis:
                    if width_axis == 'N-S':
                        along = (0, 1)
                        perp = (1, 0)
                    else:  # E-W
                        along = (1, 0)
                        perp = (0, 1)
                    bbox = compute_bbox(pos, dims, along, perp)
                
                # Apply rotation if specified
                if bbox and rotation:
                    # Rotate around bbox center
                    cx = sum(p[0] for p in bbox) / 4
                    cy = sum(p[1] for p in bbox) / 4
                    bbox = rotate_bbox(bbox, (cx, cy), rotation)
            
            objects.append({
                'type': 'furniture',
                'id': item['id'],
                'pos': pos,
                'dims': dims,
                'bbox': bbox,
                'width_axis': width_axis,
                'facing': facing,
                'rotation': rotation,
                'registry': item.get('registry'),
                'mass': mass,  # kg (None if unknown)
                'mount': item.get('mount'),  # 'wall' for wall-mounted items
                'on': item.get('on'),  # base object ID for surface items
                'height': item.get('height'),  # cm AFFL for wall-mounted items
            })
    
    # Windows
    for item in room.get('windows', []):
        if 'wall' not in item or 'position' not in item:
            # Skip incomplete windows (notes-only entries)
            continue
        wall_id = item['wall']
        start, end = wall_id.split('-')
        start_pos = corners[start]
        end_pos = corners[end]
        dx = end_pos[0] - start_pos[0]
        dy = end_pos[1] - start_pos[1]
        length = math.sqrt(dx**2 + dy**2)
        unit = (dx/length, dy/length)
        
        offset = item['position']
        x = start_pos[0] + unit[0] * offset
        y = start_pos[1] + unit[1] * offset
        objects.append({
            'type': 'window',
            'id': item['id'],
            'pos': (round(x), round(y)),
            'width': item.get('width'),
            'wall': wall_id,
            'wall_unit': unit,
        })
    
    # Outlets
    for item in room.get('outlets', []):
        if 'wall' not in item or 'position' not in item:
            # Skip incomplete outlets
            continue
        wall_id = item['wall']
        start, end = wall_id.split('-')
        start_pos = corners[start]
        end_pos = corners[end]
        dx = end_pos[0] - start_pos[0]
        dy = end_pos[1] - start_pos[1]
        length = math.sqrt(dx**2 + dy**2)
        unit = (dx/length, dy/length)
        
        offset = item['position']
        x = start_pos[0] + unit[0] * offset
        y = start_pos[1] + unit[1] * offset
        objects.append({
            'type': 'outlet',
            'id': item['id'],
            'pos': (round(x), round(y)),
            'height': item.get('height'),
            'outlet_type': item.get('type'),
        })
    
    # Openings (passages between rooms)
    for item in room.get('openings', []):
        if 'wall' not in item or 'position' not in item:
            # Skip incomplete openings (notes-only entries)
            continue
        wall_id = item['wall']
        start, end = wall_id.split('-')
        start_pos = corners[start]
        end_pos = corners[end]
        dx = end_pos[0] - start_pos[0]
        dy = end_pos[1] - start_pos[1]
        length = math.sqrt(dx**2 + dy**2)
        unit = (dx/length, dy/length)
        
        offset = item['position']
        x = start_pos[0] + unit[0] * offset
        y = start_pos[1] + unit[1] * offset
        objects.append({
            'type': 'opening',
            'id': item['id'],
            'pos': (round(x), round(y)),
            'width': item.get('width'),
            'to': item.get('to'),
            'has_door': item.get('has_door', False),
            'wall': wall_id,
            'wall_unit': unit,
        })
    
    # Heating
    for item in room.get('heating') or []:
        if 'wall' in item and 'position' in item:
            wall_id = item['wall']
            start, end = wall_id.split('-')
            start_pos = corners[start]
            end_pos = corners[end]
            dx = end_pos[0] - start_pos[0]
            dy = end_pos[1] - start_pos[1]
            length = math.sqrt(dx**2 + dy**2)
            unit = (dx/length, dy/length)
            
            offset = item['position']
            x = start_pos[0] + unit[0] * offset
            y = start_pos[1] + unit[1] * offset
            objects.append({
                'type': 'heating',
                'id': item['id'],
                'pos': (round(x), round(y)),
                'length': item.get('length'),
            })
    
    # Plumbing
    for item in room.get('plumbing', []):
        if 'wall' in item and 'position' in item:
            wall_id = item['wall']
            start, end = wall_id.split('-')
            start_pos = corners[start]
            end_pos = corners[end]
            dx = end_pos[0] - start_pos[0]
            dy = end_pos[1] - start_pos[1]
            length = math.sqrt(dx**2 + dy**2)
            unit = (dx/length, dy/length)
            
            offset = item['position']
            x = start_pos[0] + unit[0] * offset
            y = start_pos[1] + unit[1] * offset
            objects.append({
                'type': 'plumbing',
                'id': item['id'],
                'pos': (round(x), round(y)),
            })
    
    return objects

def distance(p1, p2):
    """Euclidean distance between two points."""
    return math.sqrt((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2)

FACING_ANGLES = {
    'north': 90,
    'south': -90,
    'east': 0,
    'west': 180,
}

def normalize_angle(a):
    """Normalize angle to -180 to 180."""
    while a > 180: a -= 360
    while a < -180: a += 360
    return a

def view_from(objects, corners, viewer_pos, facing=None):
    """List objects visible from a position, sorted by distance to closest edge.
    
    If facing is specified (north/south/east/west), only show objects
    within 90° cone of that direction.
    
    Distance is to the closest point on the object's bounding box (if available),
    otherwise to the position point.
    """
    facing_angle = FACING_ANGLES.get(facing) if facing else None
    
    result = []
    for obj in objects:
        # Use closest edge if bbox available, otherwise position point
        if obj.get('bbox'):
            closest, d = closest_point_on_bbox(obj['bbox'], viewer_pos)
            # Angle to closest point
            angle = math.degrees(math.atan2(
                closest[1] - viewer_pos[1],
                closest[0] - viewer_pos[0]
            ))
        else:
            d = distance(viewer_pos, obj['pos'])
            angle = math.degrees(math.atan2(
                obj['pos'][1] - viewer_pos[1],
                obj['pos'][0] - viewer_pos[0]
            ))
        
        # Filter by facing direction if specified
        if facing_angle is not None:
            diff = abs(normalize_angle(angle - facing_angle))
            if diff > 45:  # outside 90° cone
                continue
        
        result.append({**obj, 'distance': round(d), 'angle': round(angle)})
    
    result.sort(key=lambda x: x['distance'])
    return result

def main():
    if len(sys.argv) < 2 or '-h' in sys.argv or '--help' in sys.argv:
        print(__doc__)
        sys.exit(0 if '--help' in sys.argv or '-h' in sys.argv else 1)
    
    room_path = sys.argv[1]
    room = load_room(room_path)
    corners = trace_corners(room['walls'])
    objects = get_objects(room, corners, room_path)
    
    print(f"# {room.get('name', room_path)}")
    print(f"# Origin (0,0) at corner A (SW)")
    print(f"# X = East, Y = North, units = cm\n")
    
    # Print corners
    print("## Corners")
    for name, pos in sorted(corners.items()):
        print(f"  {name}: ({pos[0]}, {pos[1]})")
    
    # Items with a clear "front" that face a direction
    DIRECTIONAL_KEYWORDS = ('sofa', 'chair', 'armchair', 'tv', 'desk', 'bed')
    
    # Print objects
    print("\n## Objects (absolute positions)")
    for obj in objects:
        pos = obj['pos']
        width_axis = obj.get('width_axis')
        facing = obj.get('facing')
        dims = obj.get('dims', {})
        obj_id = obj['id'].lower()
        
        if dims and (width_axis or facing):
            w = dims.get('width', dims.get('length', '?'))
            d = dims.get('depth', dims.get('length', '?'))
            
            # Use facing if explicitly set OR if directional item
            is_directional = any(kw in obj_id for kw in DIRECTIONAL_KEYWORDS)
            if facing and is_directional:
                print(f"  {obj['type']:10} {obj['id']:25} at ({pos[0]:4}, {pos[1]:4})  {w}×{d}cm facing {facing}")
            elif width_axis:
                print(f"  {obj['type']:10} {obj['id']:25} at ({pos[0]:4}, {pos[1]:4})  {w}×{d}cm ({width_axis})")
            else:
                print(f"  {obj['type']:10} {obj['id']:25} at ({pos[0]:4}, {pos[1]:4})  {w}×{d}cm")
        else:
            print(f"  {obj['type']:10} {obj['id']:25} at ({pos[0]:4}, {pos[1]:4})")
    
    # Validate objects (overlaps, out of bounds)
    validation_warnings = validate_objects(objects, corners, room)
    if validation_warnings:
        print("\n## Validation Warnings")
        for warning in validation_warnings:
            print(warning)
    
    # Footprint summary (m²)
    items_with_dims = []
    for o in objects:
        if o['type'] in ('furniture', 'built_in') and o.get('dims'):
            dims = o['dims']
            w = dims.get('width', 0)
            d = dims.get('depth', 0)
            if w > 0 and d > 0:
                area_m2 = (w * d) / 10000  # cm² to m²
                items_with_dims.append((o['id'], area_m2))
    
    items_without_dims = [o['id'] for o in objects if o['type'] in ('furniture', 'built_in') and not (o.get('dims', {}).get('width') and o.get('dims', {}).get('depth'))]
    
    if items_with_dims or items_without_dims:
        print("\n## Footprint (m²)")
        total_area = 0
        for item_id, area in sorted(items_with_dims, key=lambda x: -x[1]):  # largest first
            print(f"  {area:5.2f}m² : {item_id}")
            total_area += area
        if items_with_dims:
            print(f"  ─────────")
            print(f"  {total_area:5.2f}m²   TOTAL ({len(items_with_dims)} items)")
        if items_without_dims:
            print(f"  (unknown): {', '.join(items_without_dims)}")

    # View from position
    viewer = None
    view_facing = None
    if '--view' in sys.argv:
        idx = sys.argv.index('--view')
        coords = sys.argv[idx + 1].split(',')
        viewer = (int(coords[0]), int(coords[1]))
        
        # Check for facing direction
        if '--facing' in sys.argv:
            facing_idx = sys.argv.index('--facing')
            view_facing = sys.argv[facing_idx + 1].lower()
            if view_facing not in FACING_ANGLES:
                print(f"Error: --facing must be north/south/east/west")
                sys.exit(1)
        
        if view_facing:
            print(f"\n## View from ({viewer[0]}, {viewer[1]}) facing {view_facing}")
        else:
            print(f"\n## View from ({viewer[0]}, {viewer[1]})")
        
        visible = view_from(objects, corners, viewer, view_facing)
        for obj in visible:
            print(f"  {obj['distance']:4}cm @ {obj['angle']:+4}° : {obj['id']}")
    
    # Edge-to-edge distance between two items
    if '--gap' in sys.argv:
        idx = sys.argv.index('--gap')
        if idx + 2 >= len(sys.argv):
            print("Error: --gap requires two item IDs", file=sys.stderr)
            sys.exit(1)
        id1, id2 = sys.argv[idx + 1], sys.argv[idx + 2]
        
        obj1 = next((o for o in objects if o['id'] == id1), None)
        obj2 = next((o for o in objects if o['id'] == id2), None)
        
        if not obj1:
            print(f"Error: '{id1}' not found", file=sys.stderr)
            sys.exit(1)
        if not obj2:
            print(f"Error: '{id2}' not found", file=sys.stderr)
            sys.exit(1)
        
        if not obj1.get('bbox') or not obj2.get('bbox'):
            print(f"Error: both items need bounding boxes (dimensions)", file=sys.stderr)
            sys.exit(1)
        
        gap = bbox_to_bbox_distance(obj1['bbox'], obj2['bbox'])
        print(f"\n## Edge-to-edge gap")
        print(f"  {id1} ↔ {id2}: {round(gap)}cm")
    
    # Distance matrix
    if '--matrix' in sys.argv:
        # Only items with bounding boxes (furniture, built-ins)
        items = [o for o in objects if o.get('bbox') and o['type'] in ('furniture', 'built_in')]
        
        if len(items) < 2:
            print("\n## Distance matrix: need at least 2 items with dimensions")
        else:
            print(f"\n## Edge-to-edge distances (cm)")
            
            # Object-to-object distances
            distances = []
            for i, obj1 in enumerate(items):
                for obj2 in items[i+1:]:
                    d = round(bbox_to_bbox_distance(obj1['bbox'], obj2['bbox']))
                    distances.append((d, obj1['id'], obj2['id']))
            
            # Object-to-wall distances
            walls = room.get('walls', [])
            for obj in items:
                for wall in walls:
                    wall_id = wall['id']
                    start, end = wall_id.split('-')
                    wall_start = corners[start]
                    wall_end = corners[end]
                    # Create wall as 2-point "bbox" and use segment distance
                    min_dist = float('inf')
                    for i in range(4):
                        p1, p2 = obj['bbox'][i], obj['bbox'][(i+1) % 4]
                        d = segment_to_segment_distance(p1, p2, wall_start, wall_end)
                        min_dist = min(min_dist, d)
                    distances.append((round(min_dist), obj['id'], f"wall:{wall_id}"))
            
            # Sort by distance and print
            distances.sort(key=lambda x: x[0])
            for d, id1, id2 in distances:
                print(f"  {d:4}cm : {id1} ↔ {id2}")
    
    # Plot floor plan
    if '--plot' in sys.argv:
        # Pass viewer info if specified
        viewer_info = None
        if viewer:
            visible = view_from(objects, corners, viewer, view_facing) if viewer else []
            viewer_info = {'pos': viewer, 'facing': view_facing, 'visible': visible}
        plot_room(room, corners, objects, room_path, viewer_info)

def plot_room(room, corners, objects, room_path, viewer_info=None):
    """Generate a floor plan image."""
    import math
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
    from matplotlib.patches import FancyArrow
    
    fig, ax = plt.subplots(1, 1, figsize=(12, 10))
    
    # Colors
    COLORS = {
        'wall': '#2d3436',
        'furniture': '#74b9ff',
        'built_in': '#a29bfe',
        'light': '#fdcb6e',
        'window': '#00b894',
        'opening': '#e17055',
        'outlet': '#ff7675',
        'heating': '#d63031',
        'plumbing': '#0984e3',
    }
    
    # Draw room outline (walls)
    corner_list = []
    for wall in room['walls']:
        start = wall['id'].split('-')[0]
        corner_list.append(corners[start])
    corner_list.append(corner_list[0])  # close the polygon
    
    xs = [c[0] for c in corner_list]
    ys = [c[1] for c in corner_list]
    ax.plot(xs, ys, color=COLORS['wall'], linewidth=3, zorder=10)
    ax.fill(xs, ys, color='#f5f5f5', alpha=0.5, zorder=1)
    
    # Label corners
    for name, pos in corners.items():
        ax.annotate(name, (pos[0], pos[1]), fontsize=10, fontweight='bold',
                   ha='center', va='center', zorder=15,
                   bbox=dict(boxstyle='circle', facecolor='white', edgecolor='black'))
    
    # Draw objects
    for obj in objects:
        pos = obj['pos']
        obj_type = obj['type']
        color = COLORS.get(obj_type, '#636e72')
        
        if obj.get('bbox'):
            # Draw bounding box
            bbox = obj['bbox']
            xs = [p[0] for p in bbox] + [bbox[0][0]]
            ys = [p[1] for p in bbox] + [bbox[0][1]]
            ax.fill(xs, ys, color=color, alpha=0.6, zorder=5)
            ax.plot(xs, ys, color=color, linewidth=1.5, zorder=6)
            
            # Label at center
            cx = sum(p[0] for p in bbox) / 4
            cy = sum(p[1] for p in bbox) / 4
            label = obj['id'].replace('-', '\n')
            ax.annotate(label, (cx, cy), fontsize=7, ha='center', va='center', zorder=7)
            
            # Draw facing arrow for directional items
            DIRECTIONAL = ('sofa', 'chair', 'armchair', 'tv', 'desk', 'bed')
            if obj.get('facing') and any(kw in obj['id'].lower() for kw in DIRECTIONAL):
                facing = obj['facing']
                arrow_len = 40
                dx, dy = {'north': (0, arrow_len), 'south': (0, -arrow_len),
                          'east': (arrow_len, 0), 'west': (-arrow_len, 0)}.get(facing, (0, 0))
                # Apply rotation if present
                rotation = obj.get('rotation', 0)
                if rotation:
                    rad = math.radians(-rotation)  # clockwise
                    dx_rot = dx * math.cos(rad) - dy * math.sin(rad)
                    dy_rot = dx * math.sin(rad) + dy * math.cos(rad)
                    dx, dy = dx_rot, dy_rot
                ax.annotate('', xy=(cx + dx, cy + dy), xytext=(cx, cy),
                           arrowprops=dict(arrowstyle='->', color='red', lw=2), zorder=8)
        else:
            # Skip types that are drawn separately below
            if obj_type in ('window', 'opening', 'outlet', 'heating', 'plumbing'):
                continue
            # Draw as point (lights and unlabeled built-ins)
            marker = 'o' if obj_type == 'light' else 's'
            ax.scatter([pos[0]], [pos[1]], c=color, s=80, marker=marker, zorder=5, edgecolors='black')
            ax.annotate(obj['id'], (pos[0], pos[1] + 20), fontsize=6, ha='center', zorder=6)
    
    # Draw windows and openings on walls
    for obj in objects:
        if obj['type'] == 'window':
            pos = obj['pos']
            width = obj.get('width', 100)
            unit = obj.get('wall_unit', (0, 1))
            # Draw along wall direction
            end_x = pos[0] + unit[0] * width
            end_y = pos[1] + unit[1] * width
            ax.plot([pos[0], end_x], [pos[1], end_y], 
                   color=COLORS['window'], linewidth=8, zorder=4, solid_capstyle='butt')
            # Label
            mid_x, mid_y = (pos[0] + end_x) / 2, (pos[1] + end_y) / 2
            ax.annotate(obj['id'], (mid_x, mid_y), fontsize=5, ha='center', va='bottom',
                       color=COLORS['window'], fontweight='bold', zorder=5)
        
        elif obj['type'] == 'opening':
            pos = obj['pos']
            width = obj.get('width', 100)
            unit = obj.get('wall_unit', (0, 1))
            end_x = pos[0] + unit[0] * width
            end_y = pos[1] + unit[1] * width
            # Draw as dashed line (gap in wall)
            linestyle = '-' if obj.get('has_door') else '--'
            ax.plot([pos[0], end_x], [pos[1], end_y], 
                   color=COLORS['opening'], linewidth=6, linestyle=linestyle, zorder=4)
            # Label with destination
            mid_x, mid_y = (pos[0] + end_x) / 2, (pos[1] + end_y) / 2
            label = f"→{obj.get('to', '')}" if obj.get('to') else obj['id']
            ax.annotate(label, (mid_x, mid_y), fontsize=5, ha='center', va='bottom',
                       color=COLORS['opening'], fontweight='bold', zorder=5)
        
        elif obj['type'] == 'outlet':
            pos = obj['pos']
            # Draw as small square
            ax.scatter([pos[0]], [pos[1]], c=COLORS['outlet'], s=60, marker='s', 
                      zorder=6, edgecolors='black', linewidths=0.5)
            ax.annotate(obj['id'], (pos[0], pos[1] + 15), fontsize=5, ha='center', 
                       color=COLORS['outlet'], zorder=7)
        
        elif obj['type'] == 'heating':
            pos = obj['pos']
            length = obj.get('length', 50)
            # Draw as thick red line
            ax.plot([pos[0], pos[0] + length], [pos[1], pos[1]], 
                   color=COLORS['heating'], linewidth=4, zorder=4)
            ax.annotate(obj['id'], (pos[0] + length/2, pos[1] + 15), fontsize=5, 
                       ha='center', color=COLORS['heating'], zorder=5)
        
        elif obj['type'] == 'plumbing':
            pos = obj['pos']
            # Draw as blue diamond
            ax.scatter([pos[0]], [pos[1]], c=COLORS['plumbing'], s=60, marker='D', 
                      zorder=6, edgecolors='black', linewidths=0.5)
            ax.annotate(obj['id'], (pos[0], pos[1] + 15), fontsize=5, ha='center', 
                       color=COLORS['plumbing'], zorder=7)
    
    # Draw viewer position and sight lines if specified
    if viewer_info:
        vpos = viewer_info['pos']
        facing_dir = viewer_info.get('facing')
        visible = viewer_info.get('visible', [])
        
        # Draw viewer marker (star)
        ax.scatter([vpos[0]], [vpos[1]], c='red', s=200, marker='*', zorder=20, edgecolors='black', linewidths=1)
        ax.annotate('VIEW', (vpos[0], vpos[1] - 40), fontsize=8, ha='center', 
                   fontweight='bold', color='red', zorder=21)
        
        # Draw facing cone if specified
        if facing_dir:
            cone_len = 150
            dir_map = {'north': (0, 1), 'south': (0, -1), 'east': (1, 0), 'west': (-1, 0)}
            if facing_dir in dir_map:
                dx, dy = dir_map[facing_dir]
                # Draw cone edges (45° each side)
                import math
                for angle_offset in [-45, 45]:
                    rad = math.radians(angle_offset)
                    rx = dx * math.cos(rad) - dy * math.sin(rad)
                    ry = dx * math.sin(rad) + dy * math.cos(rad)
                    ax.plot([vpos[0], vpos[0] + rx * cone_len], 
                           [vpos[1], vpos[1] + ry * cone_len],
                           color='red', linestyle='--', alpha=0.5, linewidth=1, zorder=15)
        
        # Draw distance lines to visible objects
        for obj in visible:
            obj_pos = obj['pos']
            dist = obj['distance']
            # Draw line
            ax.plot([vpos[0], obj_pos[0]], [vpos[1], obj_pos[1]], 
                   color='red', linestyle=':', alpha=0.4, linewidth=1, zorder=3)
            # Label with distance at midpoint
            mid_x = (vpos[0] + obj_pos[0]) / 2
            mid_y = (vpos[1] + obj_pos[1]) / 2
            ax.annotate(f'{dist}cm', (mid_x, mid_y), fontsize=6, ha='center', 
                       color='red', alpha=0.8, zorder=4,
                       bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.7, edgecolor='none'))
    
    ax.set_aspect('equal')
    ax.set_xlabel('X (East) - cm')
    ax.set_ylabel('Y (North) - cm')
    ax.set_title(room.get('name', 'Room Layout'))
    ax.grid(True, alpha=0.3)
    
    # Add legend
    legend_elements = [
        patches.Patch(facecolor=COLORS['furniture'], label='Furniture'),
        patches.Patch(facecolor=COLORS['built_in'], label='Built-in'),
        patches.Patch(facecolor=COLORS['window'], label='Window'),
        patches.Patch(facecolor=COLORS['opening'], label='Opening'),
        plt.Line2D([0], [0], marker='o', color='w', markerfacecolor=COLORS['light'], 
                   markersize=10, label='Light'),
        plt.Line2D([0], [0], marker='s', color='w', markerfacecolor=COLORS['outlet'], 
                   markersize=8, label='Outlet'),
    ]
    if viewer_info:
        legend_elements.append(plt.Line2D([0], [0], marker='*', color='w', markerfacecolor='red',
                                          markersize=12, label='Viewpoint'))
    ax.legend(handles=legend_elements, loc='upper left', fontsize=8)
    
    # Determine output path
    idx = sys.argv.index('--plot')
    if idx + 1 < len(sys.argv) and not sys.argv[idx + 1].startswith('-'):
        output_path = sys.argv[idx + 1]
    else:
        output_path = str(Path(room_path).with_suffix('.png'))
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"\n## Floor plan saved to: {output_path}")

if __name__ == '__main__':
    main()

