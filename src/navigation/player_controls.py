"""Shared selected-player inspector and centered, non-interactive collision guide."""

import flet as ft
from .player_settings import PlayerSettings,load_player_settings,save_player_settings,PLAYER_SETTINGS_FILE


def player_collision_preview(center,radius,selected=False):
    return ft.Container(left=center[0]-radius,top=center[1]-radius,
        width=2*radius,height=2*radius,border_radius=radius,
        border=ft.Border.all(1.5,"#06B6D4"),bgcolor="#1606B6D4",
        ignore_interactions=True,visible=selected)


def update_collision_preview(control,center,radius,selected):
    control.left,control.top=center[0]-radius,center[1]-radius
    control.width=control.height=2*radius;control.border_radius=radius
    control.visible=selected


class PlayerControls:
    def __init__(self,get_settings,apply_settings,on_deselect,path=PLAYER_SETTINGS_FILE):
        self.get_settings,self.apply_settings=get_settings,apply_settings
        self.path=path
        self.radius=ft.Slider(min=1,max=100,divisions=99,value=get_settings().collision_radius,
            label="{value}",width=180,on_change=self.resize_radius)
        self.radius_field=ft.TextField(label="Collision radius (map units)",width=210,dense=True,
            value=str(get_settings().collision_radius),on_submit=self.resize_radius_field)
        self.message=ft.Text(size=12)
        self.control=ft.Container(visible=False,padding=8,bgcolor="#ECFEFF",
            content=ft.Column(spacing=4,controls=[
                ft.Row(wrap=True,controls=[ft.Text("Selected player"),self.radius_field,self.radius,
                    ft.Button("Save player settings",on_click=self.save),
                    ft.Button("Load player settings",on_click=self.load),
                    ft.IconButton(icon=ft.Icons.CLOSE,tooltip="Deselect player",on_click=on_deselect)]),
                self.message]))

    def sync(self):
        value=self.get_settings().collision_radius
        self.radius.value=value;self.radius_field.value=f"{value:g}"

    def resize_radius(self,event):self.resize(event.control.value)

    def resize_radius_field(self,event):self.resize(event.control.value)

    def resize(self,value):
        try:
            current=self.get_settings()
            settings=PlayerSettings(current.visual_size,float(value))
            self.apply_settings(settings)
        except (ValueError,TypeError) as error:
            self.message.value=f"Could not resize collision: {error}"
            self.control.update();return
        self.sync();self.message.value="Collision updated. Save player settings to keep it."
        self.control.update()

    def save(self,event=None):
        try:save_player_settings(self.get_settings(),self.path)
        except (OSError,ValueError) as error:self.message.value=f"Could not save: {error}"
        else:self.message.value="Player appearance and collision saved."
        self.control.update()

    def load(self,event=None):
        try:
            settings=load_player_settings(self.path)
            self.apply_settings(settings)
        except (OSError,ValueError) as error:self.message.value=f"Could not load: {error}"
        else:
            self.sync();self.message.value="Player settings loaded."
        self.control.update()
