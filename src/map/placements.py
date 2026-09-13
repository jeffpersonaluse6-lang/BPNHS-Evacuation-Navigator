"""Building placement models — no editor UI."""

from dataclasses import dataclass
import math
from navigation.models import Rect

CAMPUS_WIDTH = 3000
CAMPUS_HEIGHT = 1200

# Paths relative to src/assets — don't prefix with "assets/" again.
ACADEMIC_FLOORPLAN_ASSET = (
    "BPNHS MAP/ACADEMIC-BUILDING SHS/FixGroundFloor.png"
)


@dataclass(frozen=True)
class PlacedBuilding:
    """A building placement — either a floor-plan image or a solid block."""

    label: str
    left: float
    top: float
    width: float
    height: float
    color: str
    subtitle: str = ""
    opens: str | None = None
    text_color: str = "#FFFFFF"
    image_src: str | None = None
    layer_style: str | None = None
    rotation: float = 0
    mirrored: bool = False

    @property
    def area(self) -> Rect:
        return Rect(self.left, self.top, self.width, self.height)

    def contains(self,x,y):
        angle=math.radians(-self.rotation)
        dx,dy=x-self.left,y-self.top
        lx,ly=dx*math.cos(angle)-dy*math.sin(angle),dx*math.sin(angle)+dy*math.cos(angle)
        return 0<=lx<=self.width and 0<=ly<=self.height


# ---------------------------------------------------------------------------
# EDIT BUILDING POSITIONS AND SIZES HERE
# ---------------------------------------------------------------------------
# Intentionally empty: build the layout in the separate Map Editor and Save map.
BUILDINGS_ON_MAP = []


def navigable_building_at(x: float, y: float, placements=None) -> str | None:
    """Return the indoor-map key at a campus point, if one is placed there."""
    for building in reversed(BUILDINGS_ON_MAP if placements is None else placements):
        if building.opens and building.contains(x, y):
            return building.opens
    return None
