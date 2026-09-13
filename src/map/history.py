"""Placement undo/redo for insert, move, and delete."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PlacementChange:
    index: int
    before: object | None
    after: object | None

    def apply(self, placements, reverse=False):
        source, target = (self.after, self.before) if reverse else (self.before, self.after)
        if source is None:
            placements.insert(self.index, target)
        elif target is None:
            placements.pop(self.index)
        else:
            placements[self.index] = target
