"""Map measurements and building data for the BPNHS prototype."""

from .models import Building, Rect
from map.layers import ACADEMIC_LAYERS, JHS_LAYERS, JHS_B_LAYERS, TVL_A_LAYERS


FLOOR_WIDTH = 1436
FLOOR_HEIGHT = 751
MARKER_SIZE = 52
# Legacy position encoding only; collision now uses NavigationState.collision_radius.
# The visible blue dot has its own configurable diameter.
DEFAULT_PLAYER_SIZE = 20


def floor_frame(parent):
    """Image buildings keep the legacy frame; free builds use their saved frame."""
    return (parent.floor_width or FLOOR_WIDTH,parent.floor_height or FLOOR_HEIGHT)


def floor_scale(parent):
    if parent is None: return 1.,1.
    width,height=floor_frame(parent)
    return parent.width/width,parent.height/height


# These values belong to the temporary campus layout. Replace them with values
# measured from the final campus map once the routes have been verified.
BUILDINGS = {
    "TVL Building B": Building(
        name="TVL Building B",
        stair_area=Rect(left=1120, top=FLOOR_HEIGHT - 255 - 365, width=235, height=365),
        floor_assets={floor: source for floor, (_, source) in enumerate(ACADEMIC_LAYERS, 1)},
        flip_vertical=True,
    ),
    "TVL Building A": Building(
        name="TVL Building A",
        stair_area=Rect(left=1175, top=210, width=220, height=310),
        floor_assets={floor: source for floor, (_, source) in enumerate(TVL_A_LAYERS, 1)},
    ),
    "Academic Building": Building(
        name="Academic Building",
        stair_area=Rect(left=1120, top=255, width=235, height=365),
        floor_assets={floor: source for floor, (_, source) in enumerate(ACADEMIC_LAYERS, 1)},
    ),
    "JHS Building": Building(
        name="JHS Building",
        stair_area=Rect(left=75, top=255, width=235, height=365),
        floor_assets={floor: source for floor, (_, source) in enumerate(JHS_LAYERS, 1)},
    ),
    "JHS Building B": Building(
        name="JHS Building B",
        stair_area=Rect(left=1255, top=240, width=170, height=245),
        floor_assets={floor: source for floor, (_, source) in enumerate(JHS_B_LAYERS, 1)},
    ),
}


def building_for(name: str | None) -> Building | None:
    """Return the selected building, if one is open."""
    return BUILDINGS.get(name) if name else None
