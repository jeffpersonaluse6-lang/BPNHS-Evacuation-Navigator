"""Editor canvas sizing without moving, scaling, or removing map content."""

import math
from .free_build import item_corners

MIN_MAP_SIZE = 100
MAX_MAP_SIZE = 5000


def content_extent(scene):
    """Right/bottom bounds, including rotated objects and projected floor pieces."""
    right = bottom = 0.
    for scope, items in scene.floors.items():
        parent = scene.parent_for_scope(scope)
        for item in items:
            for x,y in item_corners(item):
                if parent is not None:
                    x, y = scene.project(scope, x, y)
                right, bottom = max(right, x), max(bottom, y)
    return right, bottom


def checked_map_size(scene, width, height):
    """Validate a size; refuse a shrink that would newly clip placed objects."""
    values = []
    for label, value in (("Width", width), ("Height", height)):
        try:
            if isinstance(value, bool): raise ValueError
            number = float(value)
        except (ValueError, TypeError, OverflowError):
            raise ValueError(f"{label} must be a number.") from None
        if not math.isfinite(number) or not MIN_MAP_SIZE <= number <= MAX_MAP_SIZE:
            raise ValueError(f"{label} must be between {MIN_MAP_SIZE} and {MAX_MAP_SIZE} map units.")
        values.append(number)
    width, height = values
    right, bottom = content_extent(scene)
    required = []
    if width < scene.width and right > width + 1e-7:
        required.append(f"width at least {math.ceil(right)}")
    if height < scene.height and bottom > height + 1e-7:
        required.append(f"height at least {math.ceil(bottom)}")
    if required:
        raise ValueError("That size would clip placed objects. Keep " +
                         " and ".join(required) + ", or move the objects inward first.")
    return width, height
