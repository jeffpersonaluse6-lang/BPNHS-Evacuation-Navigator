"""Live railing thickness editing, with one undo entry per slider gesture."""

from dataclasses import replace
import flet as ft
from drafting.models import validate_item
from navigation.collision import collision_thickness


class RailingEditor:
    def __init__(self,editor):
        self.editor=editor
        self.active=False
        self.slider=ft.Slider(min=0,max=50,divisions=50,value=10,label="{value}",
            on_change_start=self.start,on_change=self.change,on_change_end=self.end,
            tooltip="Railing visual thickness; physical width uses Collision Thickness")
        self.control=ft.Column(visible=False,spacing=0,controls=[ft.Text("Railing thickness"),self.slider])

    def sync(self,item,multiple):
        self.control.visible=bool(item and item.kind=="railing")
        self.slider.disabled=not self.control.visible or multiple or self.editor.move_mode
        if self.control.visible:self.slider.value=item.stroke

    def start(self,event=None):
        editor=self.editor
        if editor.selection.locked() or len(editor.selection.items())!=1:return
        item=editor.selected_item()
        if item is None or item.kind!="railing":return
        editor.cancel_gesture(update=False)
        editor.drag_item=item
        editor.before_gesture=editor.document.snapshot()
        editor.begin_interaction()
        self.active=True

    def change(self,event):
        if not self.active:self.start()
        editor=self.editor
        if not self.active or editor.interaction is None:return
        item=editor.selected_item()
        try:
            changed=replace(item,stroke=float(event.control.value),collision_thickness=collision_thickness(item))
            validate_item(changed)
        except (ValueError,TypeError):return
        editor.interaction.put({item.id:changed})
        editor.refresh()

    def end(self,event=None):
        editor=self.editor
        if not self.active or editor.interaction is None:return
        if event is not None:self.change(event)
        editor.document.remember(editor.before_gesture)
        editor.finish()
        editor.refresh(properties=True,changed_only=True)
