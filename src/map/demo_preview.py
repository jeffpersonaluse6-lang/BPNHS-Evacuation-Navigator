"""Editor-only evacuation preview — not imported by the main app."""

import flet as ft
import flet.canvas as cv
from .scene import scope_key
from .scene_renderer import path_shape,project

from navigation.app import EvacuationApp


class EditorDemoPreview(EvacuationApp):
    """Reuse the runtime player while keeping development UI on the editor side."""

    def __init__(self, page, scene, on_edit, player_settings=None):
        self.on_edit = on_edit
        self.zone_canvas=None
        super().__init__(page, scene=scene,player_settings=player_settings)

    def _header(self):
        header = super()._header()
        header.content.controls.insert(0, ft.Button(
            "Edit map", icon=ft.Icons.EDIT, on_click=self.return_to_editor
        ))
        return header

    def _action_bar(self, subtitle, is_campus):
        bar = super()._action_bar(subtitle, is_campus)
        self.demo_zones_button=ft.OutlinedButton(
            "Hide demo zones" if self.state.show_demo_zones else "Show demo zones",
            icon=ft.Icons.VISIBILITY, on_click=self.toggle_demo_zones,
            visible=not is_campus,
        )
        bar.content.controls.insert(1,self.demo_zones_button)
        return bar

    def _update_world(self):
        if hasattr(self,"demo_zones_button"):
            self.demo_zones_button.visible=self.navigator.parent is not None
            self.demo_zones_button.content="Hide demo zones" if self.state.show_demo_zones else "Show demo zones"
        if self.zone_canvas is None:
            self.zone_canvas=cv.Canvas(width=self.scene.width,height=self.scene.height,visible=False)
            self.world_view.control.controls.insert(len(self.world_view.control.controls)-1,self.zone_canvas)
        shapes=[]
        parent=self.navigator.parent
        if parent:
            for item in self.scene.floors.get(scope_key(parent,f"Floor {self.state.floor}"),[]):
                if item.kind in {"stairs","entry_zone"}:
                    points=[project(parent,*item.local_to_world(*p)) for p in ((0,0),(item.width,0),(item.width,item.height),(0,item.height))]
                    shapes.append(path_shape(points,ft.Colors.with_opacity(.25,"#FBBF24"),fill=True,closed=True))
        self.zone_canvas.shapes=shapes
        self.zone_canvas.visible=self.state.show_demo_zones
        super()._update_world()

    def toggle_demo_zones(self, event):
        self.state.show_demo_zones = not self.state.show_demo_zones
        self.render()

    def return_to_editor(self, event=None):
        self._stop_joystick()
        self.active = False
        self.on_edit()
