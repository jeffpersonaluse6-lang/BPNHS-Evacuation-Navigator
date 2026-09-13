"""Map-space resize handles; independent of camera zoom and image layering."""

from dataclasses import replace
from math import hypot


MIN_BUILDING_SIZE = 24


def resize_handles(building):
    left, top = building.left, building.top
    right, bottom = left + building.width, top + building.height
    return {
        "nw": (left, top), "n": ((left + right) / 2, top),
        "ne": (right, top), "e": (right, (top + bottom) / 2),
        "se": (right, bottom), "s": ((left + right) / 2, bottom),
        "sw": (left, bottom), "w": (left, (top + bottom) / 2),
    }


def hit_resize_handle(building, x, y):
    return next((key for key, (hx, hy) in resize_handles(building).items()
                 if hypot(x - hx, y - hy) <= 12), None)


def resize_building(original, handle, start, point, map_width, map_height):
    """Keep opposite edges fixed and clamp the changing edges to the campus."""
    dx, dy = point[0] - start[0], point[1] - start[1]
    left, top = original.left, original.top
    right, bottom = left + original.width, top + original.height
    if "w" in handle:
        left = max(0, min(right - MIN_BUILDING_SIZE, left + dx))
    if "e" in handle:
        right = min(map_width, max(left + MIN_BUILDING_SIZE, right + dx))
    if "n" in handle:
        top = max(0, min(bottom - MIN_BUILDING_SIZE, top + dy))
    if "s" in handle:
        bottom = min(map_height, max(top + MIN_BUILDING_SIZE, bottom + dy))
    return replace(original, left=round(left, 1), top=round(top, 1),
                   width=round(right - left, 1), height=round(bottom - top, 1))
