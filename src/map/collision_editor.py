"""Live physical thickness controls, independent from visible object strokes."""

from dataclasses import replace
import flet as ft
from drafting.models import validate_item
from navigation.collision import COLLISION_KINDS,collision_thickness


class CollisionEditor:
    def __init__(self,editor):
        self.editor=editor
        self.active=False
        self.field=ft.TextField(label="Collision Thickness",dense=True,on_change=self.type_value,
            tooltip="Full physical width in drawing units; visual thickness is separate")
        self.slider=ft.Slider(min=1,max=200,divisions=199,value=2,label="{value}",
            on_change_start=self.start,on_change=self.change,on_change_end=self.end)
        self.control=ft.Column(visible=False,spacing=0,controls=[self.field,self.slider,
            ft.Text("Use Blocks player to enable collision. Setting stair thickness adds side/divider barriers; both ends stay open.",size=11)])

    def sync(self,item,multiple):
        self.control.visible=bool(item and item.kind in COLLISION_KINDS)
        self.control.disabled=multiple or self.editor.move_mode
        if self.control.visible:
            value=collision_thickness(item)
            self.field.error_text=None
            self.field.value=f"{value:g}"
            self.slider.value=max(1,min(200,value))

    def start(self,event=None):
        editor=self.editor
        if editor.selection.locked() or len(editor.selection.items())!=1:return
        item=editor.selected_item()
        if not item or item.kind not in COLLISION_KINDS:return
        editor.cancel_gesture(update=False)
        if not editor.collisions.value:
            editor.collisions.value=True;editor.refresh()
        editor.drag_item=item
        editor.before_gesture=editor.document.snapshot()
        editor.begin_interaction()
        editor.interaction.live_collisions=True
        self.active=True

    def change(self,event):
        if not self.active:self.start()
        editor=self.editor
        if not self.active or editor.interaction is None:return
        item=editor.selected_item()
        try:
            changed=replace(item,collision_thickness=float(event.control.value))
            validate_item(changed)
        except (ValueError,TypeError):return
        editor.interaction.put({item.id:changed})
        self.field.error_text=None
        self.field.value=f"{changed.collision_thickness:g}"
        editor.refresh()
        editor.page.update(self.field)

    def end(self,event=None):
        editor=self.editor
        if not self.active or editor.interaction is None:return
        if event is not None:self.change(event)
        editor.document.remember(editor.before_gesture)
        editor.finish()
        editor.refresh(properties=True,changed_only=True)

    def type_value(self,event):
        editor=self.editor;item=editor.selected_item()
        if editor.selection.locked() or len(editor.selection.items())!=1 or not item or item.kind not in COLLISION_KINDS:return
        try:
            changed=replace(item,collision_thickness=float(event.control.value))
            validate_item(changed)
        except (ValueError,TypeError):
            self.field.error_text="Enter a width greater than 0 and at most 200."
            editor.page.update(self.field);return
        self.field.error_text=None
        if changed==item:editor.page.update(self.field);return
        editor.collisions.value=True
        editor.modify(lambda:editor.document.floors.__setitem__(editor.floor,
            [changed if i.id==item.id else i for i in editor.items()]))
