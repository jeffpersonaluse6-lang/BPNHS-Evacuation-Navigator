"""Wall-owned circle gaps: editing UI only, with retained angle-drag previews."""

from dataclasses import replace
import math
import flet as ft
from drafting.circular import CircleOpening
from drafting.models import validate_item


class CircleOpeningEditor:
    def __init__(self,editor):
        self.editor=editor;self.wall_id=None;self.selected_id=None;self.active=False
        self.picker=ft.Dropdown(label="Opening / Door Gap",on_select=self.select)
        self.angle=ft.TextField(label="Opening position (degrees)",dense=True)
        self.width=ft.TextField(label="Opening width (drawing units)",dense=True)
        self.slider=ft.Slider(min=0,max=360,divisions=360,value=0,label="{value}°",
            on_change_start=self.start,on_change=self.change,on_change_end=self.end)
        self.add_button=ft.Button("Add Opening",on_click=self.add)
        self.apply_button=ft.Button("Apply opening",on_click=self.apply)
        self.delete_button=ft.Button("Delete opening",on_click=self.delete)
        self.control=ft.Column(visible=False,controls=[ft.Text("Circle Wall entrances",weight=ft.FontWeight.BOLD),
            self.picker,self.angle,self.width,self.slider,self.add_button,
            ft.Row(wrap=True,controls=[self.apply_button,self.delete_button]),
            ft.Text("0° right · 90° bottom · 180° left · 270° top, before wall rotation/flip. Drag the slider to move a gap. Width is capped by the diameter if the wall shrinks.",size=11)])

    def item(self):
        editor=self.editor;item=editor.selected_item()
        if editor.selection.locked() or len(editor.selection.items())!=1 or not item or item.kind!="circle_wall":return None
        return item

    def gap(self,item):return next((g for g in item.circle_openings if g.id==self.selected_id),None)

    def sync(self,item,multiple):
        self.control.visible=bool(item and item.kind=="circle_wall")
        self.control.disabled=multiple or self.editor.selection.locked()
        if not self.control.visible:return
        if item.id!=self.wall_id:self.wall_id=item.id;self.selected_id=None
        if not self.gap(item):self.selected_id=item.circle_openings[0].id if item.circle_openings else None
        entries=[(gap.id,f"Gap {n+1}: {gap.angle:g}° · width {gap.width:g}") for n,gap in enumerate(item.circle_openings)]
        self.editor.dropdown_options(self.picker,entries)
        self.picker.value=self.selected_id;self.picker.disabled=not entries
        gap=self.gap(item)
        self.angle.value=f"{gap.angle:g}" if gap else "0"
        self.width.value=f"{gap.width:g}" if gap else f"{min(80,item.width/4):g}"
        self.slider.value=gap.angle if gap else 0
        self.slider.disabled=self.apply_button.disabled=self.delete_button.disabled=gap is None
        for field in (self.angle,self.width):field.error_text=None

    def select(self,event):
        item=self.item()
        if not item or event.control.value not in {g.id for g in item.circle_openings}:return
        self.selected_id=event.control.value;self.sync(item,False)
        self.editor.page.update(self.control)

    def settings(self,item):
        angle=float(self.angle.value);width=float(self.width.value)
        if not math.isfinite(angle):raise ValueError("Opening position must be finite")
        if not math.isfinite(width) or not 0<width<=100000:raise ValueError("Opening width must be positive and at most 100000")
        return angle%360,width

    def modify(self,item,message):
        validate_item(item)
        editor=self.editor
        editor.modify(lambda:editor.document.floors.__setitem__(editor.floor,
            [item if i.id==item.id else i for i in editor.items()]))
        editor.status.value=message;editor.page.update(editor.status)

    def error(self,error):
        self.editor.status.value=f"Opening not changed: {error}"
        self.editor.page.update(self.editor.status)

    def add(self,event=None):
        item=self.item()
        if not item:return
        try:
            angle,width=self.settings(item)
            current=self.gap(item)
            if current and math.isclose(angle,current.angle,abs_tol=1e-7):angle=(angle+45)%360
            gap=CircleOpening(angle,width);changed=replace(item,circle_openings=(*item.circle_openings,gap))
            validate_item(changed);self.selected_id=gap.id
            self.modify(changed,"Circle Wall opening added — visible gap and collision updated.")
        except (ValueError,TypeError) as error:self.error(error)

    def apply(self,event=None):
        item=self.item()
        if not item or not self.gap(item):return
        try:
            angle,width=self.settings(item)
            gaps=tuple(replace(g,angle=angle,width=width) if g.id==self.selected_id else g for g in item.circle_openings)
            self.modify(replace(item,circle_openings=gaps),"Opening position/width updated.")
        except (ValueError,TypeError) as error:self.error(error)

    def delete(self,event=None):
        item=self.item()
        if not item or not self.gap(item):return
        self.modify(replace(item,circle_openings=tuple(g for g in item.circle_openings if g.id!=self.selected_id)),
            "Opening removed; that arc is closed again.")

    def start(self,event=None):
        item=self.item()
        if not item or not self.gap(item):return
        editor=self.editor;editor.cancel_gesture(update=False)
        editor.drag_item=item;editor.before_gesture=editor.document.snapshot()
        editor.begin_interaction();editor.interaction.live_collisions=True;self.active=True

    def change(self,event):
        if not self.active:self.start()
        editor=self.editor
        if not self.active or editor.interaction is None:return
        item=editor.selected_item()
        try:
            angle=float(event.control.value)%360
            gaps=tuple(replace(g,angle=angle) if g.id==self.selected_id else g for g in item.circle_openings)
            changed=replace(item,circle_openings=gaps);validate_item(changed)
        except (ValueError,TypeError):return
        editor.interaction.put({item.id:changed})
        self.angle.value=f"{angle:g}";self.slider.value=angle
        editor.refresh();editor.page.update(self.angle)

    def end(self,event=None):
        editor=self.editor
        if not self.active or editor.interaction is None:self.active=False;return
        if event is not None:self.change(event)
        editor.document.remember(editor.before_gesture)
        editor.finish();self.active=False
        editor.refresh(properties=True,changed_only=True)
