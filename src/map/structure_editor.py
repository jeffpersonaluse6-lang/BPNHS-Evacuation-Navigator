"""Circular sizing and roof opacity controls shared by both map workspaces."""

from dataclasses import replace
import math
import flet as ft
from drafting.circular import CIRCLE_KINDS
from drafting.roof import ROOF_KINDS
from drafting.models import validate_item
from .circle_opening_editor import CircleOpeningEditor


class StructureEditor:
    def __init__(self,editor):
        self.editor=editor
        self.radius=ft.TextField(label="Radius (drawing units)",dense=True)
        self.diameter=ft.TextField(label="Diameter (drawing units)",dense=True)
        self.circle_control=ft.Column(controls=[self.radius,self.diameter,
            ft.Row(wrap=True,controls=[ft.Button("Apply radius",on_click=lambda e:self.resize(True)),
                ft.Button("Apply diameter",on_click=lambda e:self.resize(False))])])
        self.opacity=ft.TextField(label="Roof opacity (0–1)",dense=True,on_change=self.change_opacity)
        self.openings=CircleOpeningEditor(editor)
        self.control=ft.Column(visible=False,controls=[self.circle_control,self.openings.control,self.opacity])

    def sync(self,item,multiple):
        self.openings.sync(item,multiple)
        self.control.visible=bool(item and item.kind in CIRCLE_KINDS|ROOF_KINDS)
        self.control.disabled=multiple or self.editor.selection.locked()
        if not self.control.visible:return
        self.circle_control.visible=item.kind in CIRCLE_KINDS
        self.opacity.visible=item.kind in ROOF_KINDS
        self.radius.value=f"{item.width/2:g}";self.diameter.value=f"{item.width:g}"
        self.opacity.value=f"{item.opacity:g}"
        for field in (self.radius,self.diameter,self.opacity):field.error_text=None

    def modify(self,item):
        editor=self.editor
        validate_item(item)
        editor.modify(lambda:editor.document.floors.__setitem__(editor.floor,
            [item if i.id==item.id else i for i in editor.items()]))

    def resize(self,radius=True):
        editor=self.editor;item=editor.selected_item()
        if editor.selection.locked() or len(editor.selection.items())!=1 or not item or item.kind not in CIRCLE_KINDS:return
        field=self.radius if radius else self.diameter
        try:
            diameter=float(field.value)*(2 if radius else 1)
            if not math.isfinite(diameter) or not 4<=diameter<=100000:raise ValueError()
            cx,cy=item.local_to_world(item.width/2,item.height/2)
            changed=replace(item,width=diameter,height=diameter)
            nx,ny=changed.local_to_world(diameter/2,diameter/2)
            self.modify(replace(changed,x=changed.x+cx-nx,y=changed.y+cy-ny))
        except (ValueError,TypeError):
            field.error_text="Use a diameter from 4 to 100000."
            editor.page.update(field)

    def change_opacity(self,event):
        editor=self.editor;item=editor.selected_item()
        if editor.selection.locked() or len(editor.selection.items())!=1 or not item or item.kind not in ROOF_KINDS:return
        try:self.modify(replace(item,opacity=float(event.control.value)))
        except (ValueError,TypeError):
            self.opacity.error_text="Use a value from 0 to 1."
            editor.page.update(self.opacity)
