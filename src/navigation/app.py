"""Main app controller for the evacuation navigator."""

import asyncio
import math
import time

import flet as ft

from .components import VirtualJoystick, user_marker
from .data import (
    MARKER_SIZE,
)
from .models import NavigationState
from .collision import barriers_for,find_free_position
from map.scene import CAMPUS,scope_key
from map.scene_store import load_scene
from .world import WorldNavigator
from .camera import CameraViewport
from .player_settings import PlayerSettings,load_player_settings
from .player_controls import PlayerControls,player_collision_preview,update_collision_preview
from .motion import MotionClock
from map.world_renderer import WorldMapView


MOVEMENT_TICK_SECONDS = 1 / 60
MOVEMENT_SPEED = 120  # Compatibility constant; live speed comes from player settings.


class EvacuationApp:
    """Ties together the map, movement, building entry, and floor switching."""

    def __init__(self, page: ft.Page, scene=None, player_settings=None):
        self.page = page
        self.scene=scene if scene is not None else load_scene()
        self.active=True
        self.follow_active=False
        self.active_parent=None
        self.state = NavigationState()
        self.player_selected=False
        self.settings_error=None
        try:settings=player_settings if player_settings is not None else load_player_settings()
        except (OSError,ValueError) as error:
            settings=PlayerSettings();self.settings_error=str(error)
        if settings.collision_radius>min(self.scene.width,self.scene.height)/2:
            self.settings_error="Saved collision radius does not fit this map; using the default radius."
            from dataclasses import replace
            settings=replace(settings,collision_radius=26)
        self.state.player_size=settings.visual_size
        self.state.collision_radius=settings.collision_radius
        self.state.player_speed=settings.player_speed
        self.state.stair_speed_multiplier=settings.stair_speed_multiplier
        self.navigator=WorldNavigator(self.scene,self.state)
        self.world_view=WorldMapView(self.scene)
        self.viewer: CameraViewport | None = None
        self.marker: ft.Container | None = None
        self.joystick: VirtualJoystick | None = None
        self.mode_button: ft.Button | None = None
        self.mode_text: ft.Text | None = None
        self.status_text: ft.Text | None = None

        self._configure_page()
        self.render()
        self.page.run_task(self._movement_loop)

    def _configure_page(self):
        self.page.title = "BPNHS Evacuation Navigator"
        self.page.padding = 0
        self.page.spacing = 0
        self.page.bgcolor = "#F5F7FB"
        self.page.theme_mode = ft.ThemeMode.LIGHT

    def render(self):
        """Build the world canvas once; floors update without a full rebuild."""
        if self.viewer is not None:
            self._update_world()
            return
        self._ensure_free_spawn()
        center=self._marker_center()
        self.marker = user_marker(center[0]-self.state.player_size/2,center[1]-self.state.player_size/2,self.state.player_size)
        self.marker.on_click=self.select_player
        self.collision_preview=player_collision_preview(center,self.state.collision_radius)
        self.player_controls=PlayerControls(self.player_settings,self.apply_player_settings,self.deselect_player)
        if self.settings_error:self.player_controls.message.value=f"Saved player settings could not load: {self.settings_error}"
        map_content=self.world_view.control
        map_content.controls.append(self.collision_preview)
        map_content.controls.append(self.marker)
        self.viewer = CameraViewport(map_content,center,
            width=(getattr(self.page,"width",None) or 1400)-32,
            height=max(200,(getattr(self.page,"height",None) or 900)-190))
        self.viewer.pan_enabled=self.viewer.scale_enabled=not self.state.move_mode
        self.viewer.on_manual=self.stop_camera_follow
        self.player_size_label=ft.Text("Player size",size=12)
        self.player_size_slider=ft.Slider(min=8,max=52,divisions=44,value=self.state.player_size,
            width=140,label="{value}",on_change=self.resize_player,tooltip="Blue-dot diameter in map units")
        self.joystick = VirtualJoystick(self.set_joystick_direction, self.state.move_mode)
        self.mode_text = ft.Text(
            self._mode_message(),
            color="#DCE8F7",
            size=13,
        )
        self.status_text = ft.Text(self.state.status, color="#31475E", size=14)
        self.mode_button = ft.Button(
            content="Finish moving" if self.state.move_mode else "Move user",
            icon=ft.Icons.CHECK if self.state.move_mode else ft.Icons.OPEN_WITH,
            on_click=self.toggle_move_mode,
            bgcolor="#D9E8FF" if self.state.move_mode else "#FFFFFF",
            color="#12345A",
        )

        self.page.clean()
        self.page.add(
            ft.Column(
                expand=True,
                spacing=0,
                controls=[
                    self._header(),
                    self._action_bar("Campus overview", True),
                    self.player_controls.control,
                    self._map_area(),
                ],
            )
        )
        self._update_world()

    def _header(self) -> ft.Container:
        return ft.Container(
            bgcolor="#12345A",
            padding=ft.Padding.symmetric(horizontal=20, vertical=14),
            content=ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.ROUTE, color="#FFFFFF", size=28),
                    ft.Column(
                        spacing=0,
                        expand=True,
                        controls=[
                            ft.Text(
                                "BPNHS Evacuation Navigator",
                                color="#FFFFFF",
                                size=22,
                                weight=ft.FontWeight.BOLD,
                            ),
                            self.mode_text,
                        ],
                    ),
                    ft.IconButton(
                        icon=ft.Icons.REFRESH,
                        tooltip="Reset pan, zoom, and rotation",
                        icon_color="#FFFFFF",
                        on_click=self.reset_map,
                    ),
                ],
            ),
        )

    def _action_bar(self, subtitle: str, is_campus: bool) -> ft.Container:
        self.subtitle_text=ft.Text(subtitle,size=18,weight=ft.FontWeight.BOLD,color="#183B56")
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=20, vertical=10),
            bgcolor="#FFFFFF",
            content=ft.Row(
                controls=[
                    ft.Column(
                        expand=True,
                        spacing=0,
                        controls=[
                            self.subtitle_text,
                            self.status_text,
                        ],
                    ),
                    ft.Column(spacing=0,controls=[self.player_size_label,self.player_size_slider]),
                    ft.Button("Select player",on_click=self.select_player),self.mode_button,
                ],
            ),
        )

    def _map_area(self) -> ft.Container:
        return ft.Container(
            expand=True,
            padding=16,
            content=ft.Stack(
                expand=True,
                fit=ft.StackFit.EXPAND,
                controls=[
                    ft.Container(
                        expand=True,
                        bgcolor="#D5DEE8",
                        border_radius=12,
                        clip_behavior=ft.ClipBehavior.HARD_EDGE,
                        content=self.viewer,
                    ),
                    ft.Container(
                        right=30,
                        bottom=30,
                        content=self.joystick.control,
                    ),
                ],
            ),
        )

    def _mode_message(self) -> str:
        if self.state.move_mode:
            return "MOVE USER MODE - use the joystick. Map gestures are locked."
        return "MAP MODE - drag to pan; pinch and twist to zoom and rotate."

    def _set_status(self, message: str):
        self.state.status = message
        if self.status_text is not None:
            self.status_text.value = message
            self.status_text.update()

    def _map_dimensions(self) -> tuple[float, float]:
        return self.scene.width,self.scene.height

    @staticmethod
    def _clamp(value: float, lower: float, upper: float) -> float:
        return max(lower, min(value, upper))

    async def reset_map(self, event):
        if self.viewer is not None:
            await self.viewer.reset()
            self.viewer.camera.center(self._marker_center());self.viewer.apply()

    def resize_player(self,event):
        value=float(event.control.value)
        if not math.isfinite(value):return
        self.state.player_size=max(8,min(52,value))
        self._update_world()

    def player_settings(self):return PlayerSettings(self.state.player_size,self.state.collision_radius,
        self.state.player_speed,self.state.stair_speed_multiplier)

    def apply_player_settings(self,settings):
        if settings.collision_radius>min(self.scene.width,self.scene.height)/2:
            raise ValueError("Collision radius must fit inside the map.")
        self.state.player_size=settings.visual_size
        self.state.collision_radius=settings.collision_radius
        self.state.player_speed=settings.player_speed
        self.state.stair_speed_multiplier=settings.stair_speed_multiplier
        self.player_size_slider.value=settings.visual_size
        # Don't teleport on resize — even if the bigger circle overlaps a wall,
        # the next move will use the accurate new collision.
        self._update_world();self.player_size_slider.update()

    def select_player(self,event=None):
        self.player_selected=True;self.player_controls.control.visible=True
        self.player_controls.sync();self._update_world();self.player_controls.control.update()

    def deselect_player(self,event=None):
        self.player_selected=False;self.player_controls.control.visible=False
        self._update_world();self.player_controls.control.update()

    def stop_camera_follow(self):self.follow_active=False

    def toggle_move_mode(self, event):
        """Toggle between map gestures and joystick movement."""
        self.state.move_mode = not self.state.move_mode
        self.follow_active=True
        if self.viewer is not None:
            self.viewer.pan_enabled = not self.state.move_mode
            self.viewer.scale_enabled = not self.state.move_mode
        if self.joystick is not None:
            self.joystick.set_enabled(self.state.move_mode)
        if self.mode_button is not None:
            self.mode_button.content = (
                "Finish moving" if self.state.move_mode else "Move user"
            )
            self.mode_button.icon = (
                ft.Icons.CHECK if self.state.move_mode else ft.Icons.OPEN_WITH
            )
            self.mode_button.bgcolor = (
                "#D9E8FF" if self.state.move_mode else "#FFFFFF"
            )
        if self.mode_text is not None:
            self.mode_text.value = self._mode_message()
        self._set_status(
            "Use the joystick to move the blue dot."
            if self.state.move_mode
            else "Use map gestures to look around."
        )
        self.page.update()

    def set_joystick_direction(self, x: float, y: float):
        """Update from the joystick's current direction (-1 to 1)."""
        self.state.joystick_x = x
        self.state.joystick_y = y

    async def _movement_loop(self):
        """Tick the movement loop while the joystick is held down."""
        clock=MotionClock(time.perf_counter())
        while self.active:
            await asyncio.sleep(clock.delay(time.perf_counter(),MOVEMENT_TICK_SECONDS))
            dt=clock.advance(time.perf_counter())
            if not self.state.move_mode and not self.follow_active:
                continue
            self.movement_tick(dt)

    def movement_tick(self,dt):
        if (not self.active or not self.viewer or not math.isfinite(dt) or dt<=0 or dt>.5
                or (not self.state.move_mode and not self.follow_active)):return
        # Integrate long frames in bounded simulation steps, but submit ONE UI
        # patch per frame. Regular lag retains elapsed time; a suspended app
        # deliberately discards its pause rather than teleporting on resume.
        remaining=dt
        visual_before=self.navigator.visual_state()
        moved=False;camera_changed=False
        while remaining>1e-9:
            step=min(1/120,remaining);remaining-=step
            before=self._marker_center()
            visible=self.viewer.camera.visible(before,self.state.player_size)
            if visible and self.state.move_mode and (self.state.joystick_x or self.state.joystick_y):
                x,y=self.navigator.walk(before,self.state.joystick_x,self.state.joystick_y,step)
                self.state.marker_x,self.state.marker_y=x-MARKER_SIZE/2,y-MARKER_SIZE/2
            after=self._marker_center();moving=after!=before;moved=moved or moving
            camera_changed=self.viewer.camera.follow(after,step,moving=moving,
                diameter=self.state.player_size,guard=visible) or camera_changed
        if camera_changed:self.viewer.apply(False)
        if moved or self.navigator.visual_state()!=visual_before:
            self._update_world([self.viewer.scene] if camera_changed else [])
        elif camera_changed:self.page.update(self.viewer.scene)
        after=self._marker_center()
        if not self.state.move_mode:
            screen=self.viewer.camera.screen(after)
            if math.hypot(screen[0]-self.viewer.camera.width/2,screen[1]-self.viewer.camera.height/2)<.05:
                self.follow_active=False

    def move_user(self, delta_x: float, delta_y: float) -> bool:
        """Move the player one step and check for building/floor triggers."""
        if not self.state.move_mode:
            return False

        before=(self.state.building_name,self.state.floor)
        x,y=self.navigator.move(self._marker_center(),delta_x,delta_y)
        self.state.marker_x,self.state.marker_y=x-MARKER_SIZE/2,y-MARKER_SIZE/2
        self._update_world()
        return before!=(self.state.building_name,self.state.floor)

    def _update_world(self,extra_dirty=()):
        self.active_parent=self.navigator.parent
        center=self._marker_center()
        dirty=list(extra_dirty)+self.world_view.update(self.navigator,center)
        camera_dirty=self.viewer is not None and self.viewer.scene in extra_dirty
        if camera_dirty:dirty=list(extra_dirty)  # Root patch already includes changed map children.
        if self.marker:
            size=self.state.player_size
            self.marker.left,self.marker.top=center[0]-size/2,center[1]-size/2
            self.marker.width=self.marker.height=size
            self.marker.border_radius=size/2
            if not camera_dirty:dirty.append(self.marker)
        if hasattr(self,"collision_preview") and (self.player_selected or self.collision_preview.visible):
            update_collision_preview(self.collision_preview,center,self.state.collision_radius,self.player_selected)
            if not camera_dirty:dirty.append(self.collision_preview)
        message="Walking on campus. Walk through a building doorway to enter."
        if self.active_parent:
            message=f"{self.active_parent.text} · Floor {self.state.floor}"
            if self.navigator.transition:
                t=self.navigator.transition
                message=f"{self.active_parent.text} · Floor {t.source} → {t.target} · stairs {t.progress:.0%}"
        self.state.status=message
        if self.status_text and self.status_text.value!=message:
            self.status_text.value=message;dirty.append(self.status_text)
        if hasattr(self,"subtitle_text"):
            subtitle=f"{self.active_parent.text} - Floor {self.state.floor}" if self.active_parent else "Campus overview"
            if self.subtitle_text.value!=subtitle:
                self.subtitle_text.value=subtitle;dirty.append(self.subtitle_text)
        if dirty:self.page.update(*dirty)

    def _marker_center(self) -> tuple[float, float]:
        return (
            self.state.marker_x + MARKER_SIZE / 2,
            self.state.marker_y + MARKER_SIZE / 2,
        )

    def _ensure_free_spawn(self):
        """Make sure the spawn point isn't stuck inside a wall."""
        width,height=self._map_dimensions()
        radius=self.state.collision_radius
        spawn=find_free_position(*self._marker_center(),radius,
            barriers_for(self._scene_items()),width,height)
        if spawn is not None and not self.navigator.allowed(spawn):
            original=spawn
            spawn=None
            # Only search for a free spot at startup, not on floor transitions.
            for ring in range(1,101):
                offsets=[(n*8,edge*ring*8) for n in range(-ring,ring+1) for edge in (-1,1)]
                offsets += [(edge*ring*8,n*8) for n in range(-ring,ring+1) for edge in (-1,1)]
                for dx,dy in sorted(offsets,key=lambda p:p[0]**2+p[1]**2):
                    candidate=original[0]+dx,original[1]+dy
                    if radius<=candidate[0]<=width-radius and radius<=candidate[1]<=height-radius and self.navigator.allowed(candidate):
                        spawn=candidate; break
                if spawn is not None: break
        if spawn is None:
            self.state.move_mode=False
            self.state.status="This layer has no free space for the player. Contact the map administrator."
        else:
            self.state.marker_x,self.state.marker_y=spawn[0]-MARKER_SIZE/2,spawn[1]-MARKER_SIZE/2
            self.navigator.update(spawn)

    def _check_building_entry(self) -> bool:
        changed=self.navigator.update(self._marker_center())
        self._update_world()
        return changed

    def enter_building(self, name: str):
        parent=self.scene.parent_for_key(name)
        if parent:
            self.navigator.enter(parent)
            self._update_world()

    def _check_staircase(self) -> bool:
        return self._check_building_entry()

    def _stop_joystick(self):
        """Stop movement before tearing down a view that owns the joystick."""
        self.state.joystick_x = 0
        self.state.joystick_y = 0
        if self.joystick is not None:
            self.joystick.deactivate()

    def return_to_campus(self, event):
        self.navigator.exit()
        self._update_world()

    def _building(self):
        return self.scene.navigation_building(self.state.building_name,parent=self.active_parent)

    def _scene_items(self):
        if self.state.view=="campus": return self.scene.floors[CAMPUS]
        parent=self.active_parent or self.scene.parent_for_key(self.state.building_name)
        return self.scene.floors.get(scope_key(parent,f"Floor {self.state.floor}"),[]) if parent else []

def main(page: ft.Page):
    """Flet entry point — called from main.py."""
    EvacuationApp(page)
