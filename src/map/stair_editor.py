"""Editor-only connections stored on stairs, with derived flight previews."""

from dataclasses import replace
import flet as ft
from drafting.models import validate_item
from navigation.stairs import STAIR_KINDS,transitions
from .scene import scope_key


class StairEditor:
    def __init__(self,editor):
        self.editor=editor
        self.source=ft.Dropdown(label="From Floor",on_select=self.change_source)
        self.direction=ft.Dropdown(label="Direction: Up / Down",options=self.directions(),on_select=self.change_direction)
        self.target=ft.Dropdown(label="To Floor")
        self.enabled=ft.Checkbox(label="Enable Stair Activator",value=True,on_change=self.toggle_enabled)
        self.speed=ft.TextField(label="Stair speed multiplier (blank = player setting)",dense=True)
        self.connection_controls=ft.Column(controls=[self.source,self.direction,self.target,self.speed,
            ft.Button("Apply stair settings",on_click=self.apply)])
        self.control=ft.Column(visible=False,controls=[ft.Text("Stair floor transition",weight=ft.FontWeight.BOLD),
            self.enabled,self.connection_controls,
            ft.Text("Invisible walking areas follow this stair. Enter at the arrow tail. After arrival, leave the entire staircase before another transition. No separate zone is needed.",size=11)])

    def toggle_enabled(self,event=None):
        editor=self.editor;item=editor.selected_item()
        if editor.selection.locked() or not item or item.kind!="stairs" or len(editor.selection.items())!=1:return
        enabled=self.enabled.value
        if event is not None:enabled=event.control.value
        if type(enabled) is not bool:return
        changed=replace(item,stair_enabled=enabled)
        editor.modify(lambda:editor.document.floors.__setitem__(editor.floor,
            [changed if i.id==item.id else i for i in editor.items()]))
        editor.status.value="Stair Activator enabled" if enabled else "Stair Activator disabled — visual and collision settings unchanged"
        editor.page.update(editor.status)

    @staticmethod
    def directions():return [ft.DropdownOption(k,k.title()) for k in ("up","down")]

    def target_options(self):
        parent=self.editor.parent()
        if not parent:return
        source=int(self.source.value or 1)
        for field,direction in ((self.target,self.direction.value),):
            options=[("","Adjacent floor (automatic)")]+[(str(n),f"Floor {n}") for n in range(1,parent.floor_count+1)
                if n!=source and (direction=="up")== (n>source)]
            self.editor.dropdown_options(field,options)
            if field.value not in {value for value,_ in options}:field.value=""

    def change_source(self,event=None):
        self.target_options();self.editor.page.update(self.target)

    def change_direction(self,event=None):self.change_source()

    def sync(self,item,multiple):
        parent=self.editor.parent()
        numbered=parent is not None and ":Floor " in self.editor.floor
        self.control.visible=bool(item and item.kind in STAIR_KINDS)
        self.control.disabled=multiple or self.editor.move_mode
        if not self.control.visible:return
        self.enabled.value=item.stair_enabled
        self.connection_controls.visible=numbered
        if not numbered:return
        self.editor.dropdown_options(self.source,[(str(n),f"Floor {n}") for n in range(1,parent.floor_count+1)])
        self.source.value=str(item.stair_from or int(self.editor.floor.split()[-1]))
        self.direction.value=item.stair_direction
        self.target.value=str(item.stair_to) if item.stair_to is not None else ""
        self.speed.value="" if item.stair_speed_multiplier is None else f"{item.stair_speed_multiplier:g}"
        self.target_options()

    def apply(self,event=None):
        editor=self.editor;item=editor.selected_item();parent=editor.parent()
        if editor.selection.locked() or not parent or not item or item.kind not in STAIR_KINDS or len(editor.selection.items())!=1:return
        try:
            source=int(self.source.value)
            if not 1<=source<=parent.floor_count:raise ValueError("Choose an existing From Floor")
            changed=replace(item,stair_from=source,stair_to=int(self.target.value) if self.target.value else None,
                stair_direction=self.direction.value,stair_enabled=self.enabled.value,
                stair_speed_multiplier=float(self.speed.value) if self.speed.value.strip() else None)
            validate_item(changed)
            pairs=[(changed.stair_direction,changed.stair_to)]
            for direction,target in pairs:
                if target is not None and (not 1<=target<=parent.floor_count or target==source or (direction=="up")!=(target>source)):
                    raise ValueError("To Floor must exist and agree with Up / Down")
            destination=scope_key(parent,f"Floor {source}")
            if destination!=editor.floor:
                changed=replace(changed,parent_id=parent.id if item.parent_id==parent.id else None,group_id=None)
            def apply():
                editor.document.floors[editor.floor]=[i for i in editor.items() if i.id!=item.id]
                editor.document.floors.setdefault(destination,[]).append(changed)
                editor.floor=destination;editor.selection.select({item.id},False)
            editor.modify(apply)
            sections=transitions(changed,source,parent.floor_count)
            editor.status.value="Stair: "+(", ".join(f"F{s.source} → F{s.target} ({s.direction})" for s in sections) or "no available floor connection")
        except (ValueError,TypeError) as error:editor.status.value=f"Stair settings not applied: {error}"
        editor.page.update(editor.status)


def transition_shapes(item,parent,floor,scale=1):
    """Selection-only guides; runtime doesn't draw activation areas."""
    from .scene_renderer import project,path_shape
    import flet.canvas as cv
    shapes=[]
    for section in transitions(item,floor,parent.floor_count):
        points=[project(parent,*section.local_to_world(x,y)) for x,y in
            ((0,0),(section.width,0),(section.width,section.height),(0,section.height))]
        shapes.append(path_shape(points,"#7C3AED,0.12",fill=True,closed=True))
        shapes.append(path_shape(points,"#7C3AED",1.5/max(.1,scale),closed=True))
        center=project(parent,*section.local_to_world(section.width/2,section.height/2))
        shapes.append(cv.Text(*center,f"F{section.source} → F{section.target}",
            style=ft.TextStyle(size=12/max(.1,scale),color="#5B21B6",bgcolor="#FFFFFF"),alignment=ft.Alignment.CENTER))
    return shapes
