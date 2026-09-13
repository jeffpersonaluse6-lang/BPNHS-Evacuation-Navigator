"""Export placements as Python code."""

from dataclasses import fields


def placement_code(placements):
    lines=["BUILDINGS_ON_MAP = ["]
    for building in placements:
        lines.append("    PlacedBuilding(")
        for field in fields(building):
            lines.append(f"        {field.name}={getattr(building,field.name)!r},")
        lines.append("    ),")
    lines.append("]")
    return "\n".join(lines)
