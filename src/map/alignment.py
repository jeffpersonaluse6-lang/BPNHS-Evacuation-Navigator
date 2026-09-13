"""Editor snap guides — screen-distance alignment against floor axes."""

from dataclasses import dataclass, replace
from functools import lru_cache
from bisect import bisect_left,bisect_right
import math
from spatial import BoundsIndex


class AlignmentIndex:
    """Prepared once per gesture; mouse moves query a local spatial neighborhood."""
    def __init__(self,items,excluded=()):
        excluded=set(excluded)
        self.items=tuple(i for i in items if i.id not in excluded)
        self.boxes=tuple(bounds(i) for i in self.items)
        self.spatial=BoundsIndex(self.boxes)
        self.axes=[]
        for axis in (0,1):
            entries=[(value,feature,box,number) for number,box in enumerate(self.boxes)
                for feature,value in enumerate(anchors(box,axis))]
            entries.sort(key=lambda entry:entry[0])
            self.axes.append((tuple(e[0] for e in entries),tuple(entries)))
        self.last_candidate_count=0

    def nearby(self,box,scale):
        padding=tuple(max(512/max(scale[a],1e-9),2*(box[a][1]-box[a][0])) for a in (0,1))
        numbers=self.spatial.query(box,padding)
        self.last_candidate_count=len(numbers)
        return set(numbers),[self.boxes[n] for n in numbers]


@dataclass(frozen=True)
class Guide:
    axis: int
    position: float
    start: float
    end: float
    label: str
    gaps: tuple = ()


@lru_cache(maxsize=4096)
def bounds(item):
    corners = ((0, 0), (item.width, item.height)) if item.kind in {
        "wall", "line", "railing"} else (
        (0, 0), (item.width, 0), (item.width, item.height), (0, item.height))
    points = [item.local_to_world(*p) for p in corners]
    return tuple((min(p[a] for p in points), max(p[a] for p in points)) for a in (0, 1))


def anchors(box, axis):
    lo, hi = box[axis]
    return lo, (lo + hi) / 2, hi


@lru_cache(maxsize=32)
def target_index(items, axis):
    entries = [(value, feature, bounds(item)) for item in items
               for feature, value in enumerate(anchors(bounds(item), axis))]
    entries.sort(key=lambda entry: entry[0])
    return tuple(entry[0] for entry in entries), tuple(entries)


def spacing_targets(box, targets, axis):
    """Match an existing gap or evenly fit between two non-overlapping peers."""
    cross = 1 - axis
    peers = [b for b in targets if min(b[cross][1], box[cross][1]) >=
             max(b[cross][0], box[cross][0]) - 1e-7]
    peers.sort(key=lambda b: b[axis][0])
    width = box[axis][1] - box[axis][0]
    for left, right in zip(peers, peers[1:]):
        gap = right[axis][0] - left[axis][1]
        if gap < 0:
            continue
        # Equal gaps before/after, or in between the pair.
        yield right[axis][1] + gap, gap, left, right, "after"
        yield left[axis][0] - gap - width, gap, left, right, "before"
        if gap >= width:
            yield left[axis][1] + (gap - width) / 2, (gap - width) / 2, left, right, "between"


def snap_transform(point, make_item, others, dimensions, *, pixels=6,
                   scale=(1, 1), smart=True, equal=True, grid=0, grid_origin=(0, 0),
                   resizing=False):
    """Snap translation or anchor-preserving resize, without changing rotation.

    ``make_item(pointer)`` is the existing unsnapped geometry operation. A small
    numerical derivative measures which bounds actually move with that handle;
    fixed opposite edges cannot produce false resize snaps. Distances are measured
    in screen pixels, including building scale and viewer zoom.
    """
    raw = tuple(point)
    current = make_item(raw)
    prepared=others if isinstance(others,AlignmentIndex) else None
    if prepared:
        nearby,peers=prepared.nearby(bounds(current),scale)
    else:
        others = tuple(i for i in others if i.id != current.id)
        peers = [bounds(i) for i in others]
    guides = []
    for axis in (0, 1):
        box = bounds(current)
        values = anchors(box, axis)
        # How each bound moves when the pointer shifts along either axis.
        derivatives = []
        denominators = []
        for feature in range(3):
            gradient = []
            for direction in (0, 1):
                offset = list(raw)
                offset[direction] += .01
                gradient.append((anchors(bounds(make_item(offset)), axis)[feature] - values[feature]) / .01)
            derivatives.append(gradient)
            denominators.append(sum((gradient[a] / max(scale[a], 1e-9)) ** 2 for a in (0, 1)))
        best = None

        def candidate(feature, target, label, target_box=None, gaps=()):
            nonlocal best
            gradient = derivatives[feature]
            # Smallest screen-distance correction: gradient dot delta = error.
            denom = denominators[feature]
            if denom < 1e-10:
                return
            error = target - values[feature]
            distance = abs(error) / math.sqrt(denom)
            if distance > pixels + 1e-7 or (best is not None and distance >= best[0] - 1e-9):
                return
            delta = tuple(error * gradient[a] / max(scale[a], 1e-9) ** 2 / denom for a in (0, 1))
            cross = 1 - axis
            span = box[cross] if target_box is None else (
                min(box[cross][0], target_box[cross][0]), max(box[cross][1], target_box[cross][1]))
            guide = Guide(axis, target, span[0], span[1], label, gaps)
            best = (distance, delta, guide)

        if smart:
            coordinates, entries = prepared.axes[axis] if prepared else target_index(others, axis)
            labels = ("Left", "Vertical center", "Right") if axis == 0 else ("Top", "Horizontal center", "Bottom")
            for feature in range(3):
                radius = pixels * math.sqrt(denominators[feature]) + 1e-7
                lo = bisect_left(coordinates, values[feature] - radius)
                hi = bisect_right(coordinates, values[feature] + radius)
                for entry in entries[lo:hi]:
                    if prepared and entry[3] not in nearby: continue
                    target,target_feature,peer=entry[:3]
                    candidate(feature, target, labels[target_feature], peer)
            for feature in range(3):
                candidate(feature, dimensions[axis] / 2, "Layer center")
        if equal and not resizing and (best is None or best[0] > 1e-9):
            for target, gap, left, right, placement in spacing_targets(box, peers, axis):
                width = box[axis][1] - box[axis][0]
                if placement == "after":
                    gaps = ((left[axis][1], right[axis][0]), (right[axis][1], target))
                elif placement == "before":
                    gaps = ((target + width, left[axis][0]), (left[axis][1], right[axis][0]))
                else:
                    gaps = ((left[axis][1], target), (target + width, right[axis][0]))
                candidate(0, target, f"Equal gap {gap:g}", left, gaps)
        if grid:
            target = grid_origin[axis] + round((raw[axis] - grid_origin[axis]) / grid) * grid
            delta = [0., 0.]
            delta[axis] = target - raw[axis]
            distance = abs(delta[axis]) * scale[axis]
            if best is None or distance < best[0] - 1e-9:
                best = (distance, tuple(delta), None)
        if best is not None:
            # Smart guides win over grid — no grid after this.
            _, delta, guide = best
            raw = tuple(raw[a] + delta[a] for a in (0, 1))
            current = make_item(raw)
            if guide:
                guides.append(guide)
    # Rotated resize can change one axis while snapping the other.
    final_box = bounds(current)
    guides = [g for g in guides if min(abs(v - g.position) for v in anchors(final_box, g.axis)) < 1e-4]
    return current, guides


def snap_point(point, others, dimensions, **settings):
    from drafting.models import DraftItem
    marker = DraftItem("line", *point, 0, 0)
    item, guides = snap_transform(point, lambda p: replace(marker, x=p[0], y=p[1]), others, dimensions, **settings)
    return (item.x, item.y), guides
