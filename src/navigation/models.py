"""Data models used by the navigation prototype."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    """A rectangular area in a map's coordinate system."""

    left: float
    top: float
    width: float
    height: float

    def contains(self, x: float, y: float) -> bool:
        return (
            self.left <= x <= self.left + self.width
            and self.top <= y <= self.top + self.height
        )


@dataclass(frozen=True)
class Building:
    """Indoor floor images and the stair trigger area for one building."""

    name: str
    stair_area: Rect
    floor_assets: dict[int, str]
    flip_vertical: bool = False


@dataclass
class NavigationState:
    """Small, UI-independent state for the manual demo."""

    view: str = "campus"
    building_name: str | None = None
    floor: int = 1
    move_mode: bool = False
    show_demo_zones: bool = False
    marker_x: float = 1510.0
    marker_y: float = 620.0
    stair_armed: bool = True
    status: str = "Move the user over a building to enter its Ground Floor."
    joystick_x: float = 0.0
    joystick_y: float = 0.0
    player_size: float = 20.0
    collision_radius: float = 26.0
