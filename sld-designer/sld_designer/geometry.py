"""Small geometry helpers. The JavaScript editor (static/core.js) implements the
same maths; tests/test_parity.py checks both produce identical drawings."""

import math


def r4(v):
    """Round to 4 decimals and normalise -0.0 -> 0.0 (needed for stable parity checks)."""
    return round(float(v), 4) + 0.0


def transform_vec(px, py, rot, mirror):
    """Mirror about the local Y axis, then rotate clockwise (screen, y down)."""
    if mirror:
        px = -px
    r = int(rot) % 360
    if r == 0:
        return px, py
    if r == 90:
        return -py, px
    if r == 180:
        return -px, -py
    if r == 270:
        return py, -px
    a = math.radians(r)
    return px * math.cos(a) - py * math.sin(a), px * math.sin(a) + py * math.cos(a)


def transform_point(px, py, rot, mirror, ox, oy):
    x, y = transform_vec(px, py, rot, mirror)
    return x + ox, y + oy


def arc_points(cx, cy, r, a0, a1, step):
    """Polyline approximation of an arc. Angles in degrees; the point at angle t is
    (cx + r cos t, cy + r sin t) in the y-down coordinate system."""
    n = max(2, int(math.ceil(abs(a1 - a0) / step)))
    pts = []
    for i in range(n + 1):
        t = math.radians(a0 + (a1 - a0) * i / n)
        pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
    return pts


def seg_hit(p, a, b):
    """True if point p lies on segment a-b (axis-aligned or not), tolerance 1e-6 mm."""
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return abs(px - ax) < 1e-6 and abs(py - ay) < 1e-6
    t = ((px - ax) * dx + (py - ay) * dy) / L2
    if t < -1e-9 or t > 1 + 1e-9:
        return False
    qx, qy = ax + t * dx, ay + t * dy
    return (px - qx) ** 2 + (py - qy) ** 2 < 1e-10
