"""Floor Activator inspector and editor-only zone graphics."""

from dataclasses import replace
import math
import flet as ft
import flet.canvas as cv
from drafting.models import validate_item
from navigation.activators import KIND,endpoints
from navigation.stairs import STAIR_KINDS
from .scene import scope_key


def zone_shapes(item,parent):
    from .scene_renderer import project,path_shape
    points=[project(parent,*item.local_to_world(*p)) for p in ((0,0),(item.width,0),(item.width,item.height),(0,item.height))]
    shapes=[path_shape(points,"#7C3AED,0.16",fill=True,closed=True),path_shape(points,"#7C3AED",2,closed=True)]
    a,b=[project(parent,*item.local_to_world(*p)) for p in endpoints(item)]
    angle=math.atan2(b[1]-a[1],b[0]-a[0])
    shapes.append(cv.Line(*a,*b,paint=ft.Paint(color="#7C3AED",stroke_width=3)))
    for sign in (-1,1):
        end=(b[0]-12*math.cos(angle)+sign*6*math.sin(angle),b[1]-12*math.sin(angle)-sign*6*math.cos(angle))
        shapes.append(cv.Line(*b,*end,paint=ft.Paint(color="#7C3AED",stroke_width=3)))
    center=project(parent,*item.local_to_world(item.width/2,item.height/2))
    shapes.append(cv.Text(*center,f"F{item.activator_from} → F{item.activator_to}"+(" (disabled)" if not item.activator_enabled else ""),
        style=ft.TextStyle(size=14,color="#5B21B6",bgcolor="#FFFFFF"),alignment=ft.Alignment.CENTER))
    return tuple(shapes)


class ActivatorEditor:
    def __init__(self,editor):
        self.editor=editor
        self.source=ft.Dropdown(label="From Floor",on_select=self.change_source)
        self.target=ft.Dropdown(label="To Floor")
        self.direction=ft.Dropdown(label="Direction",options=[ft.DropdownOption(k,k.title()) for k in ("up","down")])
        self.stair=ft.Dropdown(label="Connected staircase")
        self.enabled=ft.Checkbox(label="Activator enabled",value=True)
        self.axis=ft.Dropdown(label="Travel orientation (before rotation)",options=[ft.DropdownOption(k,label) for k,label in
            (("auto","Auto: Up = bottom to top; Down = top to bottom"),("up","Bottom → top"),("down","Top → bottom"),("left","Right → left"),("right","Left → right"))])
        self.control=ft.Column(visible=False,controls=[ft.Text("Floor Activator",weight=ft.FontWeight.BOLD),
            self.source,self.target,self.direction,self.stair,self.axis,self.enabled,
            ft.Button("Apply activator",on_click=self.apply),ft.Text("Size, position and rotation use the regular object properties. Place one zone per stair flight.",size=11)])

    def stairs(self):
        parent=self.editor.parent()
        if parent is None:return []
        return [i for i in self.editor.document.floors.get(scope_key(parent,f"Floor {self.source.value}"),[]) if i.kind in STAIR_KINDS]

    def change_source(self,event=None):
        self.editor.dropdown_options(self.stair,[("","Unlinked zone")]+[(i.id,f"{i.text} · {i.id[:6]}") for i in self.stairs()])
        if self.stair.value not in {i.id for i in self.stairs()}:self.stair.value=""
        self.editor.page.update(self.stair)

    def sync(self,item,multiple):
        self.control.visible=bool(item and item.kind==KIND)
        self.control.disabled=multiple or self.editor.move_mode
        if not self.control.visible:return
        parent=self.editor.parent()
        options=[(str(n),f"Floor {n}") for n in range(1,parent.floor_count+1)] if parent else []
        for field in (self.source,self.target):self.editor.dropdown_options(field,options)
        self.source.value=str(item.activator_from);self.target.value=str(item.activator_to)
        self.direction.value=item.stair_direction;self.axis.value=item.activator_axis
        self.enabled.value=item.activator_enabled
        self.editor.dropdown_options(self.stair,[("","Unlinked zone")]+[(i.id,f"{i.text} · {i.id[:6]}") for i in self.stairs()])
        self.stair.value=item.activator_stair or ""

    def apply(self,event=None):
        editor=self.editor;item=editor.selected_item();parent=editor.parent()
        if editor.selection.locked() or not parent or not item or item.kind!=KIND or len(editor.selection.items())!=1:return
        try:
            source,target=int(self.source.value),int(self.target.value)
            changed=replace(item,activator_from=source,activator_to=target,stair_direction=self.direction.value,
                activator_axis=self.axis.value,activator_stair=self.stair.value or None,activator_enabled=self.enabled.value)
            validate_item(changed)
            if not 1<=source<=parent.floor_count or not 1<=target<=parent.floor_count:raise ValueError("Choose existing floors")
            if changed.activator_stair and changed.activator_stair not in {i.id for i in self.stairs()}:raise ValueError("Staircase must belong to From Floor")
            destination=scope_key(parent,f"Floor {source}")
            if destination!=editor.floor:changed=replace(changed,parent_id=None,group_id=None)
            def apply():
                editor.document.floors[editor.floor]=[i for i in editor.items() if i.id!=item.id]
                editor.document.floors.setdefault(destination,[]).append(changed)
                editor.floor=destination;editor.selection.select({item.id},False)
            editor.modify(apply)
            editor.status.value=f"Activator: Floor {source} → Floor {target}. Enter at the tail of its arrow."
            editor.page.update(editor.status)
        except (ValueError,TypeError) as error:
            editor.status.value=f"Activator not applied: {error}";editor.page.update(editor.status)
