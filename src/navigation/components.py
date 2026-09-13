"""Reusable Flet controls for maps, buildings, the user, and the joystick."""

from collections.abc import Callable
from math import hypot

import flet as ft

from .data import (
    FLOOR_HEIGHT,
    FLOOR_WIDTH,
    DEFAULT_PLAYER_SIZE,
)
from .models import Building


def user_marker(left: float, top: float, size: float = DEFAULT_PLAYER_SIZE) -> ft.Container:
    """The visible person marker. It is moved only by the virtual joystick."""
    return ft.Container(
        left=left,
        top=top,
        width=size,
        height=size,
        tooltip="Demo user",
        bgcolor="#155EEF",
        border_radius=size/2,
    )


def floor_canvas(
    building: Building,
    floor: int,
    marker: ft.Container,
    show_demo_zone: bool,
    overlay_shapes=None,
    floorplan_control=None,
) -> ft.Stack:
    """Display a floor-plan image, the user marker, and optional stair guidance."""
    controls: list[ft.Control] = [
        ft.Image(
            src=building.floor_assets[floor],
            width=FLOOR_WIDTH,
            height=FLOOR_HEIGHT,
            fit=ft.BoxFit.FILL,
            scale=(
                ft.Scale(scale_x=1, scale_y=-1, alignment=ft.Alignment.CENTER)
                if building.flip_vertical else None
            ),
        )
    ] if building.floor_assets.get(floor) else [ft.Container(width=FLOOR_WIDTH,height=FLOOR_HEIGHT,bgcolor="#EDF8FA")]
    if floorplan_control is not None: controls=[floorplan_control]
    if show_demo_zone and floor + 1 in building.floor_assets:
        area = building.stair_area
        controls.append(
            ft.Container(
                left=area.left,
                top=area.top,
                width=area.width,
                height=area.height,
                bgcolor=ft.Colors.with_opacity(0.19, "#155EEF"),
                border=ft.Border.all(3, "#155EEF"),
                border_radius=6,
                alignment=ft.Alignment.CENTER,
                content=ft.Text(
                    "STAIR\nNEXT FLOOR",
                    size=16,
                    weight=ft.FontWeight.BOLD,
                    color="#0B3E91",
                    text_align=ft.TextAlign.CENTER,
                ),
            )
        )
    if overlay_shapes:
        import flet.canvas as cv
        controls.append(cv.Canvas(width=FLOOR_WIDTH,height=FLOOR_HEIGHT,shapes=overlay_shapes))
    controls.append(marker)
    return ft.Stack(width=FLOOR_WIDTH, height=FLOOR_HEIGHT, controls=controls)


class VirtualJoystick:
    """A touch/mouse joystick that continuously reports a direction vector."""

    BASE_SIZE = 148
    KNOB_SIZE = 56

    def __init__(self, on_direction: Callable[[float, float], None], enabled: bool):
        self.on_direction = on_direction
        self.enabled = enabled
        center = (self.BASE_SIZE - self.KNOB_SIZE) / 2

        self.knob = ft.Container(
            left=center,
            top=center,
            width=self.KNOB_SIZE,
            height=self.KNOB_SIZE,
            border_radius=self.KNOB_SIZE / 2,
            bgcolor="#155EEF" if enabled else "#9AAFC2",
            alignment=ft.Alignment.CENTER,
            content=ft.Icon(ft.Icons.OPEN_WITH, color="#FFFFFF", size=26),
        )
        self.label = ft.Text(
            "MOVE" if enabled else "LOCKED",
            color="#12345A",
            size=12,
            weight=ft.FontWeight.BOLD,
            text_align=ft.TextAlign.CENTER,
        )
        self.base = ft.Container(
            width=self.BASE_SIZE,
            height=self.BASE_SIZE,
            border_radius=self.BASE_SIZE / 2,
            bgcolor="#FFFFFFE8",
            border=ft.Border.all(3, "#155EEF" if enabled else "#9AAFC2"),
            alignment=ft.Alignment.CENTER,
            content=ft.GestureDetector(
                drag_interval=16,
                on_pan_start=self._on_pan_start,
                on_pan_update=self._on_pan_update,
                on_pan_end=self._on_pan_end,
                content=ft.Stack(
                    width=self.BASE_SIZE,
                    height=self.BASE_SIZE,
                    controls=[
                        ft.Container(
                            alignment=ft.Alignment.CENTER,
                            content=self.label,
                        ),
                        self.knob,
                    ],
                ),
            ),
        )

    @property
    def control(self) -> ft.Container:
        """The panel placed above the map, so it does not pan with the map."""
        return ft.Container(
            width=180,
            padding=10,
            border_radius=18,
            bgcolor="#FFFFFFE8",
            border=ft.Border.all(1, "#C7D4E2"),
            content=ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=4,
                controls=[
                    self.base,
                    ft.Text("Joystick", size=13, weight=ft.FontWeight.BOLD),
                    ft.Text("Hold and drag", size=11, color="#476582"),
                ],
            ),
        )

    def set_enabled(self, enabled: bool):
        self.enabled = enabled
        self._send_direction(0, 0)
        self.label.value = "MOVE" if enabled else "LOCKED"
        self.knob.bgcolor = "#155EEF" if enabled else "#9AAFC2"
        self.base.border = ft.Border.all(3, "#155EEF" if enabled else "#9AAFC2")
        self._center_knob()
        self.label.update()
        self.base.update()

    def deactivate(self):
        """Stop safely before this control is removed during a map transition."""
        self.enabled = False
        self._send_direction(0, 0)

    def _on_pan_start(self, event):
        if not self.enabled:
            return
        self._set_direction(event.local_position.x, event.local_position.y)
        self._place_knob(event.local_position.x, event.local_position.y)

    def _on_pan_update(self, event):
        if not self.enabled:
            return
        current_x = event.local_position.x
        current_y = event.local_position.y
        self._set_direction(current_x, current_y)
        self._place_knob(current_x, current_y)

    def _on_pan_end(self, event):
        self._send_direction(0, 0)
        self._center_knob()

    def _set_direction(self, x: float, y: float):
        center = self.BASE_SIZE / 2
        delta_x = x - center
        delta_y = y - center
        distance = hypot(delta_x, delta_y)
        if distance < 8:
            self._send_direction(0, 0)
            return
        radius = self.BASE_SIZE / 2
        if distance > radius:
            delta_x = delta_x / distance * radius
            delta_y = delta_y / distance * radius
        self._send_direction(delta_x / radius, delta_y / radius)

    def _send_direction(self, x: float, y: float):
        self.on_direction(x, y)

    def _place_knob(self, x: float, y: float):
        maximum = self.BASE_SIZE - self.KNOB_SIZE
        self.knob.left = max(0, min(x - self.KNOB_SIZE / 2, maximum))
        self.knob.top = max(0, min(y - self.KNOB_SIZE / 2, maximum))
        self.knob.update()

    def _center_knob(self):
        center = (self.BASE_SIZE - self.KNOB_SIZE) / 2
        self.knob.left = center
        self.knob.top = center
        self.knob.update()
