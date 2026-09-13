"""Free-build floor editor — fit bounds on save only."""

from dataclasses import replace
import math
import flet as ft
from .workspace_editor import MapWorkspaceEditor
from .scene import MapScene,CAMPUS,scope_key
from .scene_store import save_scene
from .free_build import fit_building,map_alignment_targets


class BuildingEditor(MapWorkspaceEditor):
    def __init__(self,owner,parent=None):
        self.owner_editor=owner
        self.editing_existing=parent is not None
        self.building_session=True
        self.closed=False
        self.map_reference=None
        self.floor_panel=None
        self.floor_panel_signature=None
        self.alignment_reference_cache={}
        working=MapScene.from_json(owner.document.to_json())
        if parent is None:
            # Internal metadata only — not a visible/selectable box.
            parent=owner.create_item("building",0,0,working.width,working.height)
            parent=replace(parent,floor_count=1,fill="none",free_build=True,
                floor_width=working.width,floor_height=working.height)
            working.floors[CAMPUS].append(parent)
        self.building_id=parent.id
        self.hidden_buildings=(parent.id,) if not parent.image_src and not parent.layer_style else ()
        for n in range(1,parent.floor_count+1): working.floors.setdefault(scope_key(parent,f"Floor {n}"),[])
        working.floors.setdefault(scope_key(parent,"Floor 1"),[])
        super().__init__(owner.page,working)
        self.references.multiple=True
        self.references.all_other=False
        self.selection.clipboard=owner.selection.clipboard
        self.name.label="Building name"
        self.name.value=parent.text
        self.name.on_change=self.rename_building
        self.floor_panel=ft.Row(scroll=ft.ScrollMode.AUTO,spacing=4)
        self.done_button=ft.Button("Floor 1 Done",on_click=self.floor_done)
        self.commit_button=ft.Button("Save Building Changes" if self.editing_existing else "Add Building to Map",
            icon=ft.Icons.SAVE,on_click=self.commit)
        self.control.controls[0]=ft.Row(scroll=ft.ScrollMode.AUTO,controls=[
            ft.Text("BPNHS Building Editor",size=21,weight=ft.FontWeight.BOLD),self.name,
            self.done_button,
            ft.Button("Remove current floor",on_click=self.remove_floor),
            self.commit_button,ft.Button("Cancel",on_click=self.cancel)])
        self.control.controls.insert(2,self.floor_panel)
        # No nested building sessions or old SVG workflow here.
        self.control.controls[1].controls=[c for c in self.control.controls[1].controls
            if c is not self.building_actions and getattr(c,"content",None) not in ("Edit Building","Edit selected draft")]
        self.tool_buttons["building"].content="Free build"
        self.change_scope(scope_key(parent,"Floor 1"))
        self.initial_snapshot=self.document.snapshot()

    def building(self):
        return next(b for b in self.document.buildings() if b.id==self.building_id)

    def mount(self):
        super().mount()
        self.page.title="BPNHS Building Editor"

    def editable_items(self):
        return super().editable_items()

    def items(self):
        if not getattr(self,"ready",False): return super().items()
        if not self.floor.startswith(f"{self.building_id}:"): return []
        return self.document.floors.get(self.floor,[])

    def selected_item(self):
        if getattr(self,"interaction",None) is not None: return self.interaction.current.get(self.selected)
        return next((i for i in self.items() if i.id==self.selected),None)

    def point(self,event,snap=True):
        if not getattr(self,"ready",False): return super().point(event,snap)
        # Clamp to the map bounds, not the legacy building rectangle.
        x=max(0,min(self.document.width,event.local_position.x))
        y=max(0,min(self.document.height,event.local_position.y))
        x,y=self.unproject_point(x,y)
        if snap and self.snap.value:
            step=int(self.spacing.value)
            x,y=math.floor(x/step+.5+1e-9)*step,math.floor(y/step+.5+1e-9)*step
        return x,y

    def alignment_items(self):
        signature=(self.floor,self.building(),tuple((key,tuple(items)) for key,items in self.document.floors.items()
            if not key.startswith(f"{self.building_id}:")))
        if self.alignment_reference_cache.get("signature")!=signature:
            self.alignment_reference_cache={"signature":signature,
                "items":map_alignment_targets(self.document,self.building(),self.floor)}
        return [*super().alignment_items(),*self.alignment_reference_cache["items"]]

    def hit_item(self,event):
        point=self.point(event,snap=False)
        return next((i for i in reversed(self.editable_items()) if i.contains(*point)),None)

    def select_object(self,event):
        if event.control.value in {i.id for i in self.editable_items()}: super().select_object(event)

    def choose_tool(self,kind):
        if kind=="building": kind="select"
        super().choose_tool(kind)

    def change_scope(self,scope):
        if not scope.startswith(f"{self.building_id}:") or scope not in self.document.floors:
            if scope==scope_key(self.building(),"Roof"): self.document.floors.setdefault(scope,[])
            else: return
        super().change_scope(scope)
        self.status.value=f"Free build on {scope.split(':',1)[1]} anywhere over the map. Map objects and other floors are locked references."
        self.page.update()

    def refresh(self,update=True,properties=False,*,selection_only=False,changed_only=False):
        if (getattr(self,"interaction",None) is not None and not properties) or selection_only or changed_only:
            super().refresh(update,properties,selection_only=selection_only,changed_only=changed_only)
            return
        if getattr(self,"ready",False) and (not self.floor.startswith(f"{self.building_id}:") or self.floor not in self.document.floors):
            self.floor=scope_key(self.building(),"Floor 1")
        super().refresh(False,properties)
        if not self.ready: return
        parent=self.building()
        if properties:
            options=[(scope_key(parent,layer),layer+(" ✓" if layer.startswith("Floor ") and int(layer.split()[-1]) in parent.completed_floors else ""))
                for layer in self.document.layers(parent)]
            self.dropdown_options(self.floor_picker,options)
            self.dropdown_options(self.object_picker,[(i.id,f"{i.kind}: {i.text}") for i in self.editable_items()])
        if self.floor_panel is not None:
            signature=(parent.floor_count,parent.completed_floors,self.floor)
            if signature!=self.floor_panel_signature:
                self.floor_panel_signature=signature
                self.floor_panel.controls=[ft.Button(layer+(" - Editing" if self.floor==scope_key(parent,layer) else
                    " ✓" if layer.startswith("Floor ") and int(layer.split()[-1]) in parent.completed_floors else ""),
                    bgcolor="#DBEAFE" if self.floor==scope_key(parent,layer) else None,
                    on_click=lambda e,l=layer:self.change_scope(scope_key(self.building(),l))) for layer in self.document.layers(parent)]
            layer=self.floor.split(":",1)[-1]
            self.done_button.content=f"{layer} Done → next"
            self.done_button.disabled=not layer.startswith("Floor ")
        if update: self.page.update()

    def arrange_scene(self,controls):
        parent=self.building()
        background=[]
        foreground=[]
        own_ids={parent.id}|{i.id for key,children in self.document.floors.items() if key.startswith(f"{parent.id}:") for i in children}
        other_ids={i.id for items in self.document.floors.values() for i in items if i.id not in own_ids}
        references={id(v[1]) for key,v in self.image_cache.items() if key!=parent.id}
        references.update(id(v[1]) for key,v in self.vector_cache.items() if key in other_ids)
        for control in controls:
            (background if id(control) in references else foreground).append(control)
        if self.map_reference is None:
            self.map_reference=ft.Container(opacity=.22,ignore_interactions=True,
                content=ft.Stack(width=self.document.width,height=self.document.height))
        previous=self.map_reference.content.controls
        if len(previous)!=len(background) or any(a is not b for a,b in zip(previous,background)):
            self.map_reference.content.controls=background
        # Draw background/grid, then reference map, then current building.
        split=2 if self.grid.value else 1
        return [*foreground[:split],self.map_reference,*foreground[split:]]

    def rename_building(self,event):
        parent=self.building()
        text=event.control.value[:200]
        self.modify(lambda:self.update_parent(replace(parent,text=text)))

    def update_parent(self,parent):
        if parent.id!=self.building_id: raise ValueError("Only the current building can be changed")
        self.document.floors[CAMPUS]=[parent if i.id==parent.id else i for i in self.document.floors[CAMPUS]]

    def floor_done(self,event=None):
        if not self.active or self.move_mode or self.exporting or self.dialog_open: return
        if self.floor==CAMPUS or self.floor.endswith(":Roof"): return
        parent=self.building()
        number=int(self.floor.split()[-1])
        count=parent.floor_count
        next_layer=f"Floor {number+1}"
        if number==count:
            if parent.layer_style: next_layer="Roof"
            else: count+=1
        def done():
            self.update_parent(replace(parent,floor_count=count,
                completed_floors=tuple(sorted(set(parent.completed_floors)|{number}))))
            self.document.floors.setdefault(scope_key(parent,next_layer),[])
        self.modify(done)
        self.change_scope(scope_key(parent,next_layer))

    def remove_floor(self,event=None):
        if not self.active or self.move_mode or self.exporting or self.dialog_open: return
        parent=self.building()
        if not self.floor.startswith(f"{parent.id}:Floor ") or parent.floor_count<=1 or parent.layer_style:
            self.status.value="Keep Floor 1; image-based buildings keep their original floor count."; self.refresh(); return
        number=int(self.floor.split()[-1])
        def remove():
            before=self.document.snapshot()
            old={n:self.document.floors.pop(scope_key(parent,f"Floor {n}"),[]) for n in range(1,parent.floor_count+1)}
            for n,items in old.items():
                if n==number: continue
                dest=n-1 if n>number else n
                children=[]
                for item in items:
                    if item.kind=="floor_activator":
                        if item.activator_to==number:continue
                        item=replace(item,activator_from=dest,activator_to=item.activator_to-1 if item.activator_to>number else item.activator_to)
                    targets={}
                    for key in ("stair_to","stair_right_to"):
                        target=getattr(item,key)
                        targets[key]=None if target==number else target-1 if target and target>number else target
                    children.append(replace(item,**targets))
                self.document.floors[scope_key(parent,f"Floor {dest}")]=children
            self.update_parent(replace(parent,floor_count=parent.floor_count-1,
                completed_floors=tuple(n-1 if n>number else n for n in parent.completed_floors if n!=number)))
            self.document.remember(before)
            self.change_scope(scope_key(parent,f"Floor {min(number,parent.floor_count-1)}"))
        self.confirm("Delete this floor and activators leading to it, then renumber higher floors? Undo can restore them.",remove)

    def duplicate(self,event=None):
        if self.floor!=CAMPUS: super().duplicate(event)

    def delete(self,event=None):
        if self.floor!=CAMPUS: super().delete(event)

    def select_all(self):
        self.selection.select({i.id for i in self.editable_items()})
        self.refresh(properties=True)

    def commit(self,event=None):
        if not self.active or self.move_mode or self.exporting or self.dialog_open: return
        self.cancel_gesture(update=False)
        owner=self.owner_editor
        parent=self.building()
        floors={k:v for k,v in self.document.floors.items() if k.startswith(f"{parent.id}:")}
        try: parent=fit_building(parent,floors)
        except ValueError as error:
            self.status.value=f"Building not saved: {error}"; self.refresh(); return
        staged=MapScene.from_json(owner.document.to_json())
        existed=any(i.id==parent.id for i in staged.floors[CAMPUS])
        if self.editing_existing and not existed:
            self.status.value="Building not saved: the original building is no longer on the map.";self.refresh();return
        if parent.free_build:parent=replace(parent,completed_floors=tuple(range(1,parent.floor_count+1)))
        staged.floors[CAMPUS]=[parent if i.id==parent.id else i for i in staged.floors[CAMPUS]]
        if not existed: staged.floors[CAMPUS].append(parent)
        for key in list(staged.floors):
            if key.startswith(f"{parent.id}:"): staged.floors.pop(key)
        staged.floors.update(floors)
        try:
            MapScene.from_json(staged.to_json())
            save_scene(staged)
        except (ValueError,TypeError,OSError) as error:
            self.status.value=f"Building not saved: {error}"; self.refresh(); return
        before=owner.document.snapshot()
        owner.document.name,owner.document.width,owner.document.height,owner.document.floors=staged.snapshot()
        owner.document.remember(before)
        owner.document.dirty=False
        owner.floor=CAMPUS
        owner.selection.select({parent.id},False)
        self.close()
        owner.status.value="Building changes saved." if self.editing_existing else "Building added. Select it and Edit This Building to revise its floors."
        owner.refresh(properties=True)

    def save_map(self,event=None):
        self.status.value=f"Use {self.commit_button.content} to save this building."; self.refresh()

    def copy_floor(self,event=None):
        # The generic drafter's layer could be Campus — never copy it.
        if not self.floor.startswith(f"{self.building_id}:Floor ") or int(self.floor.split()[-1])<=1: return
        if self.selection.locked(): return
        from .selection import clone_bundle
        number=int(self.floor.split()[-1])
        originals=self.document.floors.get(scope_key(self.building(),f"Floor {number-1}"),[])
        copies,_=clone_bundle(originals,{})
        adjusted=[]
        for original,item in zip(originals,copies):
            if item.kind=="floor_activator":
                target=item.activator_to+1
                if target>self.building().floor_count:
                    self.status.value="Copy would lead to a missing floor. Add another floor before copying activators.";self.refresh();return
                item=replace(item,activator_from=number,activator_to=target)
            targets={key:(getattr(item,key)+1 if getattr(item,key) is not None and
                          getattr(item,key)<self.building().floor_count else None)
                     for key in ("stair_to","stair_right_to")}
            adjusted.append(replace(item,**targets,parent_id=self.building_id if original.parent_id==self.building_id else item.parent_id))
        def copy(): self.modify(lambda:self.document.floors.__setitem__(self.floor,adjusted))
        if self.items(): self.confirm("Replace this floor with a copy of this building's previous floor?",copy)
        else: copy()

    async def load_map(self,event=None): return

    async def pick_map(self): return

    async def import_draft(self,event=None): return

    def import_document(self,draft,parent=None): return

    def edit_saved_draft(self,event=None): return

    def open_building_editor(self,parent=None): return

    def edit_building(self,event=None): return

    def attach_selected(self,event):
        allowed={i.id for i in self.items()}|{self.building_id}
        if event.control.value and event.control.value not in allowed: return
        super().attach_selected(event)

    def cancel(self,event=None):
        if not self.active or self.move_mode or self.exporting or self.dialog_open:return
        self.cancel_gesture(update=False)
        if self.document.snapshot()==self.initial_snapshot:
            self.close();return
        self.dialog_open=True
        def keep(event):
            self.page.pop_dialog();self.dialog_open=False
        def discard(event):
            self.page.pop_dialog();self.dialog_open=False;self.close()
        self.page.show_dialog(ft.AlertDialog(modal=True,title=ft.Text("Discard changes to this building?"),
            actions=[ft.TextButton("Keep Editing",on_click=keep),ft.Button("Discard Changes",on_click=discard)]))

    def close(self):
        if self.closed:return
        self.closed=True
        self.active=False
        self.shortcuts.remove()
        self.owner_editor.selection.clipboard=self.selection.clipboard
        self.owner_editor.mount()
        self.owner_editor.refresh(properties=True)

    def history(self,redo):
        layer=self.floor.split(":",1)[-1]
        super().history(redo)
        if layer.startswith("Floor "):
            number=min(int(layer.split()[-1]),self.building().floor_count)
            self.change_scope(scope_key(self.building(),f"Floor {number}"))
        self.name.value=self.building().text
        self.refresh()
