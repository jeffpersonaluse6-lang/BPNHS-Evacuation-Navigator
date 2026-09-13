"""Floor-plan drafting editor — standalone or opened from the campus editor."""

from dataclasses import replace
import math
from pathlib import Path
import uuid
import flet as ft
import flet.canvas as cv
from .canvas import drawing_shapes
from .models import DraftDocument, DraftItem, validate_item
from .handles import hit_handle, transform, rotate_about_center
from editor_shortcuts import EditorShortcuts

TOOLS = [("select","Select"),("room","Room"),("rectangle","Rectangle"),
         ("ellipse","Ellipse"),("wall","Wall"),("line","Line"),("text","Text"),
         ("door","Door"),("double_door","Double door"),("opening","Opening"),
         ("window","Window"),("stairs","Stairs"),("double_stairs","Double stairs"),
         ("roof","Roof"),("dimension","Dimension"),("pan","Pan")]
STAMP_SIZES = {"door":(60,60),"double_door":(120,60),"opening":(60,12),
               "window":(80,10),"stairs":(80,160),"double_stairs":(120,180),
               "text":(180,30),"dimension":(160,30),"roof":(320,200)}


class BuildingDraftEditor:
    def __init__(self,page,on_add_to_map=None):
        self.page=page
        self.on_add_to_map=on_add_to_map
        self.document=DraftDocument()
        self.floor=next(iter(self.document.floors))
        self.tool="select"
        self.add_kind="room"
        self.active_handle=None
        self.selected=None
        self.origin=None
        self.preview=None
        self.before_gesture=None
        self.drag_item=None
        self.is_dragging=False
        self.exporting=False
        self.dialog_open=False
        self.shortcuts=EditorShortcuts(page,lambda:self.history(False),lambda:self.history(True),
            blocked=lambda:self.exporting or self.dialog_open)
        self.picker=ft.FilePicker()
        self.status=ft.Text("Start with Room to draw an opaque building interior. Drag to draw; click to place symbols.",size=12)
        self.name=ft.TextField(label="Building name",value=self.document.name,width=230,on_change=self.rename)
        self.floor_picker=ft.Dropdown(label="Floor",value=self.floor,width=130,
                                      options=[ft.DropdownOption(f) for f in self.document.floors],on_select=self.change_floor)
        self.snap=ft.Checkbox(label="Snap to grid",value=False)
        self.grid=ft.Checkbox(label="Show grid",value=True,on_change=lambda event:self.refresh())
        self.ortho=ft.Checkbox(label="Straight walls",value=True)
        self.spacing=ft.Dropdown(label="Grid units",value="20",width=100,
                                 options=[ft.DropdownOption(str(n)) for n in (5,10,20,50)],on_select=lambda event:self.refresh())
        self.undo_button=ft.Button("Undo",on_click=lambda event:self.history(False),tooltip="Ctrl+Z")
        self.redo_button=ft.Button("Redo",on_click=lambda event:self.history(True),tooltip="Ctrl+Y / Ctrl+Shift+Z")
        self.tool_buttons={kind:ft.Button(label,height=34,
            style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=10,vertical=4)),
            on_click=lambda event,k=kind:self.choose_tool(k)) for kind,label in TOOLS}
        self.add_choice=ft.Dropdown(label="Object to add",value="room",width=170,
            options=[ft.DropdownOption(kind,label) for kind,label in TOOLS if kind not in {"select","pan"}],
            on_select=lambda event:setattr(self,'add_kind',event.control.value))
        self.add_button=ft.Button("Add to map",icon=ft.Icons.ADD_LOCATION_ALT,
            on_click=self.add_to_map,bgcolor="#155EEF",color="#FFFFFF",
            disabled=on_add_to_map is None,
            tooltip="Place the current floor draft on the campus map. Open from map_preview.py to use this.")
        self.properties={key:ft.TextField(label=label,value=default,dense=True)
                         for key,label,default in (("x","X / hinge X","0"),("y","Y / hinge Y","0"),
                         ("width","Width / line dx","120"),("height","Height / line dy","80"),
                         ("rotation","Rotation (degrees)","0"),("stroke","Line thickness","2"),
                         ("text","Text / label","Room"),("font_size","Text size","18"),
                         ("steps","Stair treads","12"),("color","Line color (#RRGGBB)","#111111"),
                         ("fill","Fill (#RRGGBB or none)","none"))}
        self.mirror=ft.Checkbox(label="Mirror horizontally",value=False)
        for field in [self.name,*self.properties.values()]:
            self.shortcuts.watch_text(field)
        self.selected_label=ft.Text("No object selected",weight=ft.FontWeight.BOLD)
        self.canvas=cv.Canvas(width=self.document.width,height=self.document.height)
        self.gesture=ft.GestureDetector(width=self.document.width,height=self.document.height,content=self.canvas,
            drag_interval=16,on_pan_down=self.pointer_down,on_pan_start=self.pan_start,
            on_pan_update=self.pointer_move,on_pan_end=self.pointer_up,on_pan_cancel=self.cancel_gesture,
            on_tap_up=self.tap)
        self.viewer=ft.InteractiveViewer(content=self.gesture,constrained=False,pan_enabled=False,
                                        min_scale=.3,max_scale=4,boundary_margin=ft.Margin.all(500))
        self.sidebar=ft.Container(visible=False,width=225,padding=10,bgcolor="#F8FAFC",content=ft.Column(
            scroll=ft.ScrollMode.AUTO,controls=[self.selected_label]+list(self.properties.values())+[
                self.mirror,ft.Button("Apply properties",on_click=self.apply_properties),
                ft.Row(wrap=True,controls=[ft.Button("Rotate 90°",on_click=lambda event:self.rotate()),
                    ft.Button("Duplicate",on_click=self.duplicate),ft.Button("Delete",on_click=self.delete)]),
                ft.Row(wrap=True,controls=[ft.Button("Bring front",on_click=lambda event:self.reorder(True)),
                    ft.Button("Send back",on_click=lambda event:self.reorder(False))]),
                ft.Text("Drag square handles to resize. Drag the blue ↻ handle to rotate, or click it for 90°. Snap also locks rotation to 15° steps.",size=12),
            ]))
        self.properties_button=ft.Button("Properties",icon=ft.Icons.TUNE,on_click=self.toggle_properties,
            tooltip="Show / hide object properties to give the canvas more space")
        self.control=ft.Column(expand=True,spacing=3,controls=[
            ft.Row(scroll=ft.ScrollMode.AUTO,spacing=6,controls=[self.name,self.floor_picker,ft.Button("Copy previous floor",on_click=self.copy_floor),
                self.undo_button,self.redo_button,ft.Button("Save draft",on_click=self.save_draft),
                ft.Button("Load draft",on_click=self.load_draft),ft.Button("Export PNG",on_click=self.export_png),
                ft.Button("Export SVG",on_click=self.export_svg)]),
            ft.Row(scroll=ft.ScrollMode.AUTO,spacing=4,controls=list(self.tool_buttons.values())),
            ft.Row(scroll=ft.ScrollMode.AUTO,spacing=6,controls=[self.add_button,self.properties_button,self.snap,self.grid,self.spacing,self.ortho,
                ft.IconButton(icon=ft.Icons.ZOOM_IN,on_click=self.zoom_in,tooltip="Zoom in"),
                ft.IconButton(icon=ft.Icons.ZOOM_OUT,on_click=self.zoom_out,tooltip="Zoom out"),
                ft.Button("Reset view",on_click=self.reset_view)]),
            ft.Row(expand=True,spacing=0,controls=[
                ft.Container(expand=True,bgcolor="#FFFFFF",clip_behavior=ft.ClipBehavior.HARD_EDGE,
                             border=ft.Border.all(1,"#CBD5E1"),content=self.viewer),self.sidebar]),
            self.status,
        ])
        self.refresh(update=False)

    def toggle_properties(self,event=None):
        self.sidebar.visible=not self.sidebar.visible
        self.properties_button.bgcolor="#DBEAFE" if self.sidebar.visible else None
        self.refresh(properties=True)

    def items(self):
        return self.document.floors[self.floor]

    def selected_item(self):
        return next((item for item in self.items() if item.id==self.selected),None)

    def point(self,event,snap=True):
        p=event.local_position
        x=max(0,min(self.document.width,p.x))
        y=max(0,min(self.document.height,p.y))
        if snap and self.snap.value:
            step=int(self.spacing.value)
            # Half-up rounding for stable grid snapping with rotated points.
            x,y=(math.floor(x/step+.5+1e-9)*step,
                 math.floor(y/step+.5+1e-9)*step)
            x=max(0,min(self.document.width,x))
            y=max(0,min(self.document.height,y))
        return x,y

    def refresh(self,update=True,properties=False):
        if self.floor not in self.document.floors:
            self.floor=next(iter(self.document.floors))
        self.canvas.shapes=drawing_shapes(self.document,self.floor,self.grid.value,int(self.spacing.value),self.selected,self.preview)
        self.canvas.width=self.gesture.width=self.document.width
        self.canvas.height=self.gesture.height=self.document.height
        self.undo_button.disabled=not self.document.undo_stack
        self.redo_button.disabled=not self.document.redo_stack
        for kind,button in self.tool_buttons.items():
            button.bgcolor="#DBEAFE" if kind==self.tool else None
        if properties:
            item=self.selected_item()
            self.selected_label.value=f"Selected: {item.kind.replace('_',' ')}" if item else "No object selected"
            if item:
                for key,control in self.properties.items():
                    control.value=str(getattr(item,key))
                self.mirror.value=item.mirrored
        if update:
            self.page.update()

    def choose_tool(self,kind):
        self.cancel_gesture(update=False)
        self.tool=kind
        if kind not in {"select","pan"}:
            self.add_kind=kind
            self.add_choice.value=kind
        self.viewer.pan_enabled=(kind=="pan")
        for name,handler in (("on_pan_down",self.pointer_down),("on_pan_start",self.pan_start),
                             ("on_pan_update",self.pointer_move),("on_pan_end",self.pointer_up),
                             ("on_pan_cancel",self.cancel_gesture),("on_tap_up",self.tap)):
            setattr(self.gesture,name,None if kind=="pan" else handler)
        self.status.value=f"Tool: {dict(TOOLS)[kind]}. " + ("Drag to pan; scroll or use +/- to zoom." if kind=="pan" else
            "Click to place a symbol." if kind in STAMP_SIZES else "Drag to move; square handles resize; ↻ rotates." if kind=="select" else "Drag from start to end.")
        self.refresh()

    async def add_object(self,event=None):
        if self.exporting:
            return
        self.cancel_gesture(update=False)
        kind=self.add_kind
        w,h=STAMP_SIZES.get(kind,{'room':(320,240),'rectangle':(180,120),
            'ellipse':(140,100),'wall':(240,0),'line':(180,0)}.get(kind,(120,80)))
        # Reset view so new objects appear on screen immediately.
        offset=(len(self.items())%6)*20
        item=self.create_item(kind,120+offset,120+offset,w,h)
        before=self.document.snapshot()
        self.items().append(item)
        self.selected=item.id
        self.document.remember(before)
        self.choose_tool('select')
        self.status.value=f"Added {dict(TOOLS)[kind]}. Drag its square handles to resize or ↻ to rotate."
        self.refresh(properties=True)
        await self.viewer.reset()

    async def add_to_map(self,event=None):
        if self.exporting or self.on_add_to_map is None:
            return
        self.cancel_gesture(update=False)
        if not self.items():
            self.status.value="Draw a building on this floor before adding it to the map."
            self.refresh()
            return
        self.exporting=True
        self.add_button.disabled=True
        try:
            await self.on_add_to_map(self.document,self.floor)
            self.document.dirty=False
            self.status.value="Added to campus map. The editable draft was saved with its image."
        except Exception as error:
            self.status.value=f"Could not add draft to map: {error}"
        finally:
            self.exporting=False
            self.add_button.disabled=False
            self.refresh()

    def pointer_down(self,event):
        if self.exporting or self.tool=="pan":
            return
        self.origin=self.point(event,snap=False)
        self.before_gesture=self.document.snapshot()
        self.is_dragging=False
        self.drag_item=None
        self.active_handle=None
        if self.tool=="select":
            item=self.selected_item()
            self.active_handle=hit_handle(item,*self.origin) if item else None
            if not self.active_handle:
                item=self.document.hit_test(self.floor,event.local_position.x,event.local_position.y)
            self.selected=item.id if item else None
            self.drag_item=item
            self.refresh(properties=True)
        else:
            self.origin=self.point(event)

    def pan_start(self,event):
        if self.origin is None:
            self.pointer_down(event)
        self.is_dragging=True

    def create_item(self,kind,x,y,w,h):
        return DraftItem(kind,x,y,w,h,stroke=6 if kind=="wall" else 2,
                         color="#783B23" if kind=="roof" else "#111111",
                         fill="#C66A41" if kind=="roof" else "#FFFFFF" if kind=="room" else "none",
                         text=self.properties["text"].value or "Room")

    def pointer_move(self,event):
        if self.origin is None or self.exporting:
            return
        self.is_dragging=True
        x,y=self.point(event,snap=self.tool!='select')
        ox,oy=self.origin
        if self.tool=="select" and self.drag_item:
            original=self.drag_item
            if self.active_handle:
                moved=transform(original,self.active_handle,self.origin,(x,y),int(self.spacing.value) if self.snap.value else 0)
            else:
                dx,dy=x-ox,y-oy
                if self.snap.value:
                    step=int(self.spacing.value)
                    dx,dy=round(dx/step)*step,round(dy/step)*step
                moved=replace(original,x=original.x+dx,y=original.y+dy)
            self.document.floors[self.floor]=[moved if item.id==moved.id else item for item in self.items()]
            self.status.value=f"{moved.kind.replace('_',' ').title()} | {moved.width:.1f} × {moved.height:.1f} | {moved.rotation%360:.1f}°"
        elif self.tool in {"line","wall"}:
            dx,dy=x-ox,y-oy
            if self.tool=="wall" and self.ortho.value:
                if abs(dx)>=abs(dy): dy=0
                else: dx=0
            self.preview=self.create_item(self.tool,ox,oy,dx,dy)
        elif self.tool not in {"select","pan"}:
            self.preview=self.create_item(self.tool,min(x,ox),min(y,oy),max(1,abs(x-ox)),max(1,abs(y-oy)))
        # Only redraw shapes and status during drag; keep text fields stable.
        self.canvas.shapes=drawing_shapes(self.document,self.floor,self.grid.value,int(self.spacing.value),self.selected,self.preview)
        self.page.update()

    def finish(self):
        self.origin=None
        self.preview=None
        self.before_gesture=None
        self.drag_item=None
        self.active_handle=None
        self.is_dragging=False

    def pointer_up(self,event=None):
        if self.exporting:
            return
        created=False
        if self.preview and self.origin:
            item=self.preview
            if ((item.kind in {"wall","line"} and math.hypot(item.width,item.height)>=3)
                or (item.kind not in {"wall","line"} and item.width>=3 and item.height>=3)):
                self.items().append(item)
                self.selected=item.id
                created=True
        if self.before_gesture is not None:
            self.document.remember(self.before_gesture)
        self.finish()
        if created:
            self.choose_tool('select')
        self.refresh(properties=True)

    def cancel_gesture(self,event=None,update=True):
        if self.before_gesture is not None and self.drag_item:
            self.document.name,self.document.width,self.document.height,self.document.floors=self.before_gesture
        self.finish()
        if update:
            self.refresh(properties=True)

    def tap(self,event):
        if self.exporting:
            return
        current=self.selected_item()
        if self.tool=='select' and current and hit_handle(current,event.local_position.x,event.local_position.y):
            handle=hit_handle(current,event.local_position.x,event.local_position.y)
            self.finish()
            if handle=='rotate': self.rotate()
            return
        if self.tool in STAMP_SIZES:
            x,y=self.point(event)
            w,h=STAMP_SIZES[self.tool]
            before=self.document.snapshot()
            item=self.create_item(self.tool,x,y,w,h)
            self.items().append(item)
            self.selected=item.id
            self.document.remember(before)
            self.finish()
            self.choose_tool('select')
        elif self.tool=="select":
            item=self.document.hit_test(self.floor,event.local_position.x,event.local_position.y)
            self.selected=item.id if item else None
        self.finish()
        self.refresh(properties=True)

    def modify(self,callback):
        self.cancel_gesture(update=False)
        before=self.document.snapshot()
        callback()
        self.document.remember(before)
        self.refresh(properties=True)

    def apply_properties(self,event=None):
        item=self.selected_item()
        if not item:
            self.status.value="Select an object first."
            self.refresh()
            return
        try:
            values={key:(control.value if key in {"text","color","fill"} else
                         int(control.value) if key=="steps" else float(control.value))
                    for key,control in self.properties.items()}
            changed=replace(item,**values,mirrored=self.mirror.value)
            validate_item(changed)
            self.modify(lambda:self.document.floors.__setitem__(self.floor,[changed if obj.id==item.id else obj for obj in self.items()]))
        except (ValueError,TypeError) as error:
            self.status.value=f"Properties not applied: {error}"
            self.page.update()

    def rotate(self):
        item=self.selected_item()
        if item:
            self.modify(lambda:self.document.floors.__setitem__(self.floor,[rotate_about_center(obj,obj.rotation+90) if obj.id==item.id else obj for obj in self.items()]))

    def duplicate(self,event=None):
        item=self.selected_item()
        if item:
            copy=replace(item,id=uuid.uuid4().hex,x=item.x+20,y=item.y+20)
            def add():
                self.items().append(copy)
                self.selected=copy.id
            self.modify(add)

    def delete(self,event=None):
        item=self.selected_item()
        if item:
            self.modify(lambda:self.document.floors.__setitem__(self.floor,[obj for obj in self.items() if obj.id!=item.id]))
            self.selected=None
            self.refresh(properties=True)

    def reorder(self,front):
        item=self.selected_item()
        if item:
            remaining=[obj for obj in self.items() if obj.id!=item.id]
            self.modify(lambda:self.document.floors.__setitem__(self.floor,remaining+[item] if front else [item]+remaining))

    def history(self,redo):
        self.cancel_gesture(update=False)
        self.document.redo() if redo else self.document.undo()
        self.selected=None
        self.name.value=self.document.name
        self.refresh(properties=True)

    def rename(self,event):
        before=self.document.snapshot()
        self.document.name=event.control.value[:200]
        self.document.remember(before)
        self.refresh()

    def change_floor(self,event):
        self.cancel_gesture(update=False)
        self.floor=event.control.value
        self.selected=None
        self.refresh(properties=True)

    def confirm(self,title,action):
        self.dialog_open=True
        def accept(event):
            self.page.pop_dialog()
            self.dialog_open=False
            action()
        def cancel(event):
            self.page.pop_dialog()
            self.dialog_open=False
        self.page.show_dialog(ft.AlertDialog(modal=True,title=ft.Text(title),
            actions=[ft.TextButton("Cancel",on_click=cancel),
                     ft.Button("Continue",on_click=accept)]))

    def copy_floor(self,event=None):
        names=list(self.document.floors)
        index=names.index(self.floor)
        if index==0:
            self.status.value="Select Floor 2 or higher to copy the floor before it."
            self.refresh()
            return
        def copy():
            self.modify(lambda:self.document.floors.__setitem__(self.floor,[replace(item,id=uuid.uuid4().hex) for item in self.document.floors[names[index-1]]]))
            self.selected=None
            self.refresh(properties=True)
        if self.items():
            self.confirm(f"Replace {self.floor} with a copy of {names[index-1]}?",copy)
        else: copy()

    async def zoom_in(self,event):
        await self.viewer.zoom(1.25)

    async def zoom_out(self,event):
        await self.viewer.zoom(.8)

    async def reset_view(self,event):
        await self.viewer.reset()

    def file_name(self,extension):
        name="".join(c if c.isalnum() or c in "-_" else "_" for c in self.document.name).strip("_") or "building"
        return f"{name}-{self.floor.replace(' ','_')}.{extension}"

    async def save_draft(self,event=None):
        self.cancel_gesture(update=False)
        try:
            saved=self.document.to_json()
            path=await self.picker.save_file(dialog_title="Save editable building draft",file_name=self.file_name("json"),
                file_type=ft.FilePickerFileType.CUSTOM,allowed_extensions=["json"],src_bytes=saved.encode("utf-8"))
            if path:
                # Don't mark as saved if the user edited while the picker was open.
                if self.document.to_json()==saved: self.document.dirty=False
                self.status.value=f"Draft saved: {path}"
            self.refresh()
        except Exception as error:
            self.status.value=f"Could not save draft: {error}"
            self.refresh()

    async def load_draft(self,event=None):
        if self.document.dirty:
            self.dialog_open=True
            def cancel(event):
                self.page.pop_dialog()
                self.dialog_open=False
            self.page.show_dialog(ft.AlertDialog(modal=True,title=ft.Text("Load another draft? Unsaved edits will be replaced."),
                actions=[ft.TextButton("Cancel",on_click=cancel),
                         ft.Button("Load another draft",on_click=self.load_confirmed)]))
        else:
            await self.load_confirmed()

    async def load_confirmed(self,event=None):
        if event is not None:
            self.page.pop_dialog()
            self.dialog_open=False
        self.cancel_gesture(update=False)
        try:
            files=await self.picker.pick_files(dialog_title="Load BPNHS draft JSON",file_type=ft.FilePickerFileType.CUSTOM,
                                              allowed_extensions=["json"],with_data=True)
            if not files: return
            contents=files[0].bytes
            if contents is None:
                self.status.value="Could not read selected file."
                self.refresh()
                return
            loaded=DraftDocument.from_json(contents.decode("utf-8-sig"))
            self.document=loaded
            self.floor=next(iter(loaded.floors))
            self.floor_picker.options=[ft.DropdownOption(name) for name in loaded.floors]
            self.floor_picker.value=self.floor
            self.name.value=loaded.name
            self.selected=None
            self.status.value=f"Loaded: {files[0].name}"
            self.refresh(properties=True)
        except Exception as error:
            self.status.value=f"Could not load draft; current drawing preserved: {error}"
            self.refresh()

    async def export_svg(self,event=None):
        self.cancel_gesture(update=False)
        try:
            svg=self.document.svg(self.floor)
            path=await self.picker.save_file(dialog_title="Export current floor without background",file_name=self.file_name("svg"),
                file_type=ft.FilePickerFileType.CUSTOM,allowed_extensions=["svg"],src_bytes=svg.encode("utf-8"))
            if path: self.status.value=f"SVG exported: {path}"
        except Exception as error:
            self.status.value=f"Could not export SVG: {error}"
        self.refresh()

    async def export_png(self,event=None):
        if self.exporting: return
        self.cancel_gesture(update=False)
        self.exporting=True
        self.control.disabled=True
        try:
            # Capture shapes only — no grid, selection, or canvas background.
            await self.canvas.clear_capture()
            self.canvas.shapes=drawing_shapes(self.document,self.floor,grid=False)
            self.page.update()
            await self.canvas.capture(pixel_ratio=1)
            data=await self.canvas.get_capture()
            if not isinstance(data,bytes) or not data:
                raise ValueError("Canvas returned no PNG data")
            path=await self.picker.save_file(dialog_title="Export current floor PNG",file_name=self.file_name("png"),
                file_type=ft.FilePickerFileType.CUSTOM,allowed_extensions=["png"],src_bytes=data)
            if path: self.status.value=f"PNG exported: {path}"
        except Exception as error:
            self.status.value=f"Could not export PNG: {error}. SVG export is also available."
        finally:
            try: await self.canvas.clear_capture()
            finally:
                self.exporting=False
                self.control.disabled=False
                self.refresh()


def open_drafting_dialog(page,on_add_to_map=None):
    from .window import DraftingWindow
    window=DraftingWindow(page,lambda callback:BuildingDraftEditor(page,callback),on_add_to_map)
    window.show()
    return window


def main(page):
    page.title="BPNHS Building Drafting Editor"
    page.padding=4
    page.theme_mode=ft.ThemeMode.LIGHT
    editor=BuildingDraftEditor(page)
    editor.shortcuts.install()
    page.add(editor.control)


if __name__=="__main__":
    ft.run(main,assets_dir=str(Path(__file__).resolve().parent.parent/"assets"))

