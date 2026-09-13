"""Unified campus and floor-object editor. No drafting dialog or flattened drafts."""

from dataclasses import replace
import asyncio
import math
import flet as ft
import flet.canvas as cv
from drafting.editor import BuildingDraftEditor,TOOLS,STAMP_SIZES
from drafting.models import DraftDocument,validate_item
from drafting.handles import transform
from editor_shortcuts import EditorShortcuts
from navigation.collision import barriers_for,move_with_collisions,find_free_position,openings_for,snap_opening_to_wall,OPENING_KINDS,COLLISION_KINDS,collision_thickness,project_barriers
from navigation.components import VirtualJoystick,user_marker
from navigation.data import MARKER_SIZE,floor_scale
from navigation.player_settings import PlayerSettings,load_player_settings
from navigation.player_controls import PlayerControls,player_collision_preview
from .scene import CAMPUS,MapScene,scope_key,to_placement
from .export import placement_code
from .scene_store import ASSETS_DIR,load_scene,save_scene
from .scene_renderer import render_scene,selection_shapes,item_shapes,world_handles
from .alignment import snap_transform,snap_point
from .reference_layers import ReferenceView,reference_controls,active_floor_outline
from .selection import SelectionController,owner_for,related_owner_chain
from .canvas_size import checked_map_size,MIN_MAP_SIZE,MAX_MAP_SIZE
from .interaction import Interaction
from .railing_editor import RailingEditor
from .activator_editor import ActivatorEditor
from .collision_editor import CollisionEditor
from navigation.stairs import STAIR_KINDS,indicators

MAP_TOOLS=[("select","Select"),("pan","Pan"),("building","Building"),("room","Room"),
    ("wall","Wall"),("railing","Railing / barrier"),("floor","Floor section"),("entry_zone","Entry / approach area"),("floor_activator","Floor Activator")]+[(k,v) for k,v in TOOLS if k not in {"select","pan","room","wall"}]
MAP_STAMPS={**STAMP_SIZES,"building":(300,180),"railing":(200,0),"floor":(300,180),"entry_zone":(180,120),"floor_activator":(100,200)}
LINE_KINDS={"line","wall","railing"}


class MapWorkspaceEditor(BuildingDraftEditor):
    def __init__(self,page,scene=None):
        self.ready=False
        self.load_error=None
        super().__init__(page)
        if scene is None:
            try: scene=load_scene()
            except (ValueError,OSError,TypeError) as error:
                self.load_error=str(error)
                from .placements import BUILDINGS_ON_MAP
                scene=MapScene(BUILDINGS_ON_MAP)
        self.document=scene
        self.floor=CAMPUS
        self.scope_parent=None
        self.image_cache,self.vector_cache={},{}
        self.background_cache={}
        self.references=ReferenceView()
        self.selection=SelectionController(self)
        self.interaction=None
        self.new_stair_direction="up"
        self.reference_cache={}
        self.alignment_guides=[]
        self.view_scale=self.gesture_scale=1.
        self.move_mode=False
        self.active=True
        self.player=(1510+MARKER_SIZE/2,620+MARKER_SIZE/2)
        try:self.player_preferences=load_player_settings()
        except (ValueError,OSError):self.player_preferences=PlayerSettings()
        if self.player_preferences.collision_radius>min(scene.width,scene.height)/2:
            self.player_preferences=PlayerSettings(self.player_preferences.visual_size)
        self.player_selected=False
        self.player_barrier_cache=None
        self.player_controls=PlayerControls(lambda:self.player_preferences,self.apply_player_preferences,self.deselect_player)
        self.direction=(0,0)
        self.name.label="Map name"
        self.name.value=scene.name
        self.map_width=ft.TextField(label="Map width",value=f"{scene.width:g}",width=180,dense=True)
        self.map_height=ft.TextField(label="Map height",value=f"{scene.height:g}",width=180,dense=True)
        self.map_size_button=ft.Button("Map size",icon=ft.Icons.ASPECT_RATIO,on_click=self.map_size_settings)
        self.floor_picker.label="Editing layer"
        self.floor_picker.width=275
        self.object_picker=ft.Dropdown(label="Selected object",width=240,on_select=self.select_object)
        self.collisions=ft.Checkbox(label="Show collisions",value=True,on_change=lambda e:self.refresh())
        self.smart_structure=ft.Checkbox(label="Smart structure select",value=True,
            tooltip="Enable Select structure to temporarily select related parts. Ordinary clicks select only manual groups.")
        self.smart_snap=ft.Checkbox(label="Smart alignment",value=True,on_change=self.snap_settings_changed)
        self.equal_spacing=ft.Checkbox(label="Equal spacing",value=True,on_change=self.snap_settings_changed)
        self.snap_distance=ft.Dropdown(label="Snap distance (px)",width=150,value="6",
            options=[ft.DropdownOption(str(n)) for n in (2,4,6,8,12)],on_select=self.snap_settings_changed)
        self.reference_label=ft.Text(size=12,color="#2563EB")
        self.blocks=ft.Checkbox(label="Blocks player",value=True)
        self.fade=ft.Checkbox(label="Fade when view is obstructed",value=True)
        self.stair_direction=ft.Dropdown(label="Direction / left flight",value="up",dense=True,
            options=[ft.DropdownOption("up","Up"),ft.DropdownOption("down","Down")],on_select=self.apply_stair_settings)
        self.stair_right=ft.Dropdown(label="Right flight direction",value="down",dense=True,
            options=[ft.DropdownOption("up","Up"),ft.DropdownOption("down","Down")],on_select=self.apply_stair_settings)
        self.stair_to=ft.TextField(label="Destination floor (blank = adjacent)",dense=True)
        self.stair_right_to=ft.TextField(label="Right flight destination (optional)",dense=True)
        self.approach=ft.TextField(label="Roof reveal distance (map units)",dense=True)
        self.owner=ft.Dropdown(label="Attached to (same floor)",dense=True,on_select=self.attach_selected)
        self.length=ft.TextField(label="Length (walls / railings)",dense=True,visible=False)
        self.railings=RailingEditor(self)
        self.collision_editor=CollisionEditor(self)
        self.activator_editor=ActivatorEditor(self)
        self.show_activators=ft.Checkbox(label="Show Floor Activators",value=True,on_change=self.activators_visibility)
        self.floor_count=ft.TextField(label="Building floors",dense=True,visible=False)
        self.shortcuts=EditorShortcuts(page,lambda:self.history(False),lambda:self.history(True),
            blocked=lambda:self.exporting or self.dialog_open or self.move_mode or not self.active,
            duplicate=self.duplicate,nudge=self.nudge)
        self.shortcuts.actions={"c":self.selection.copy,"v":self.selection.paste,"g":self.selection.group,
            "shift+g":lambda:self.selection.group(True),"a":self.select_all,
            "plain:delete":self.delete,"plain:escape":self.deselect}
        for field in [self.name,self.map_width,self.map_height,self.length,self.floor_count,self.stair_to,self.stair_right_to,self.approach,*self.properties.values()]: self.shortcuts.watch_text(field)
        self.shortcuts.watch_text(self.railings.slider)
        self.shortcuts.watch_text(self.collision_editor.slider)
        self.shortcuts.watch_text(self.collision_editor.field)
        self.shortcut_installed=False
        self.tool_buttons={kind:ft.Button(label,height=34,
            style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=10,vertical=4)),
            on_click=lambda e,k=kind:self.choose_tool(k)) for kind,label in MAP_TOOLS}
        self.selected_label.value="No object selected"
        self.selected_building_name=ft.Text()
        self.edit_building_button=ft.Button("Edit This Building",icon=ft.Icons.EDIT,on_click=self.edit_this_building)
        self.building_actions=ft.Row(visible=False,spacing=8,
            controls=[self.selected_building_name,self.edit_building_button])
        inspector=self.sidebar.content
        inspector.controls[-1].value += "\nArrow keys move the selected object: 1 unit; Shift+arrow: 10 units; Ctrl+arrow: 0.1 unit. Grid snapping does not limit keyboard nudges."
        inspector.controls.insert(1,self.blocks)
        inspector.controls.insert(2,self.length)
        inspector.controls.insert(3,self.railings.control)
        inspector.controls.insert(3,self.activator_editor.control)
        inspector.controls.insert(3,self.collision_editor.control)
        inspector.controls.insert(3,self.floor_count)
        inspector.controls[4:4]=[self.fade,self.owner,self.approach,self.stair_direction,self.stair_right,self.stair_to,self.stair_right_to]
        self.sidebar.width=250
        self.sidebar.visible=True
        self.scene_stack=ft.Stack(width=scene.width,height=scene.height)
        self.canvas=cv.Canvas(width=scene.width,height=scene.height)
        self.gesture.content=self.scene_stack
        self.gesture.width,self.gesture.height=scene.width,scene.height
        self.viewer.content=self.gesture
        self.viewer.min_scale=.25
        self.viewer.max_scale=8
        # Don't override the tracked zoom with a viewport-fit minimum.
        self.viewer.boundary_margin=ft.Margin.all(math.inf)
        self.viewer.on_interaction_start=self.view_interaction_start
        self.viewer.on_interaction_update=self.view_interaction_update
        self.viewer.interaction_update_interval=16
        self.walk_button=ft.Button("Test walk",icon=ft.Icons.DIRECTIONS_WALK,on_click=self.toggle_walk)
        self.select_player_button=ft.Button("Select player",visible=False,on_click=self.select_player)
        self.joystick=VirtualJoystick(self.set_direction,False)
        self.joystick_control=self.joystick.control
        self.joystick_control.visible=False
        self.duplicate_button=ft.Button("Duplicate",icon=ft.Icons.CONTENT_COPY,on_click=self.duplicate,tooltip="Ctrl+D")
        self.delete_button=ft.Button("Delete",icon=ft.Icons.DELETE_OUTLINE,on_click=self.delete)
        self.control=ft.Column(expand=True,spacing=3,controls=[
            ft.Row(scroll=ft.ScrollMode.AUTO,spacing=6,controls=[
                ft.Text("BPNHS Map Workspace",size=21,weight=ft.FontWeight.BOLD),self.name,
                ft.Button("Save map",icon=ft.Icons.SAVE,on_click=self.save_map),
                self.map_size_button,
                ft.Button("Load map",on_click=self.load_map),ft.Button("Import editable draft",on_click=self.import_draft),
                ft.Button("Export placements",on_click=self.export_placements),
                ft.Button("Run evacuation demo",on_click=self.run_demo)]),
            ft.Row(scroll=ft.ScrollMode.AUTO,spacing=6,controls=[self.floor_picker,self.object_picker,
                self.undo_button,self.redo_button,self.duplicate_button,self.delete_button,
                ft.Button("Group",on_click=lambda e:self.selection.group(),tooltip="Ctrl+G"),
                ft.Button("Ungroup",on_click=lambda e:self.selection.group(True),tooltip="Ctrl+Shift+G"),
                ft.Button("Select structure",on_click=lambda e:self.selection.select_structure(),tooltip="Temporary smart selection; does not group objects"),
                ft.Button("Copy",on_click=lambda e:self.selection.copy(),tooltip="Ctrl+C"),
                ft.Button("Paste",on_click=lambda e:self.selection.paste(),tooltip="Ctrl+V"),
                self.properties_button,ft.Button("Floor references",on_click=self.reference_settings),
                self.building_actions,
                self.reference_label,ft.Button("Edit selected draft",on_click=self.edit_saved_draft)]),
            ft.Row(scroll=ft.ScrollMode.AUTO,spacing=4,controls=[*self.tool_buttons.values(),
                ft.Button("Stair Up",on_click=lambda e:self.choose_stair("up")),
                ft.Button("Stair Down",on_click=lambda e:self.choose_stair("down"))]),
            ft.Row(scroll=ft.ScrollMode.AUTO,spacing=6,controls=[self.snap,self.grid,self.spacing,self.ortho,
                self.smart_structure,
                self.smart_snap,self.equal_spacing,self.snap_distance,
                self.collisions,self.show_activators,self.walk_button,self.select_player_button,
                ft.IconButton(icon=ft.Icons.ZOOM_IN,on_click=self.zoom_in),
                ft.IconButton(icon=ft.Icons.ZOOM_OUT,on_click=self.zoom_out),
                ft.Button("Reset view",on_click=self.reset_view),
                ft.Button("Export vectors SVG",on_click=self.export_svg),
                ft.Button("Export vectors PNG",on_click=self.export_png)]),
            self.player_controls.control,
            ft.Row(expand=True,spacing=0,controls=[
                ft.Container(expand=True,clip_behavior=ft.ClipBehavior.HARD_EDGE,
                    border=ft.Border.all(1,"#CBD5E1"),content=ft.Stack(expand=True,controls=[
                        ft.Container(expand=True,content=self.viewer),
                        ft.Container(right=20,bottom=20,content=self.joystick_control)])),self.sidebar]),
            self.status])
        self.ready=True
        self.status.value=(f"Saved map could not load: {self.load_error}. Empty canvas shown; saved file kept."
            if self.load_error else "One map, one editor. Choose a tool and draw directly here; select a building floor to edit its interior.")
        self.refresh(update=False,properties=True)

    def mount(self):
        self.active=True
        self.shortcuts.install()
        self.page.padding=4
        self.page.title="BPNHS Map Workspace"
        self.page.clean()
        self.page.add(self.control)
        if not self.shortcut_installed:
            self.page.run_task(self.movement_loop)
            self.shortcut_installed=True

    def parent(self):
        if self.interaction is not None: return self.interaction.parent
        return self.document.parent_for_scope(self.floor)

    def selected_item(self):
        if getattr(self,"interaction",None) is not None: return self.interaction.current.get(self.selected)
        return super().selected_item()

    def begin_interaction(self):
        self.interaction=Interaction(self)

    def interaction_targets(self):
        return self.interaction.alignment if self.interaction is not None else self.alignment_items()

    def editing_dimensions(self):
        return self.interaction.dimensions if self.interaction is not None else self.document.dimensions(self.floor)

    def unproject_point(self,x,y):
        parent=self.parent()
        if parent is None: return x,y
        x,y=parent.world_to_local(x,y)
        sx,sy=floor_scale(parent)
        return x/sx+parent.floor_origin_x,y/sy+parent.floor_origin_y

    def dropdown_options(self,control,entries):
        # Keep option IDs on geometry changes — recreating them sends huge
        # unrelated lists to Flet for comparison.
        entries=tuple(entries)
        current=control.options
        if tuple((o.key,o.text) for o in current)==entries:return
        available={(o.key,o.text):o for o in current}
        control.options=[available.get((key,label)) or ft.DropdownOption(key,label) for key,label in entries]

    def ui_state(self):
        controls=[self.selected_label,self.object_picker,self.floor_picker,self.owner,self.status,self.reference_label,
            self.building_actions,self.selected_building_name,self.edit_building_button,
            self.undo_button,self.redo_button,self.duplicate_button,self.delete_button,self.map_size_button,
            self.map_width,self.map_height,self.mirror,self.blocks,self.length,self.floor_count,self.fade,self.approach,
            self.stair_direction,self.stair_right,self.stair_to,self.stair_right_to,self.railings.control,self.railings.slider,
            self.collision_editor.control,self.collision_editor.field,self.collision_editor.slider,
            self.activator_editor.control,self.activator_editor.source,self.activator_editor.target,self.activator_editor.direction,
            self.activator_editor.stair,self.activator_editor.axis,self.activator_editor.enabled,*self.properties.values(),*self.tool_buttons.values()]
        result={}
        for control in controls:
            state=tuple(getattr(control,key,None) for key in ("value","visible","disabled","bgcolor","content"))
            if isinstance(control,ft.Dropdown):state+=(tuple(id(o) for o in control.options),)
            result[id(control)]=(control,state)
        return result

    def arrange_scene(self,controls):
        return controls

    def point(self,event,snap=True):
        if not self.ready: return super().point(event,snap)
        x,y=self.unproject_point(event.local_position.x,event.local_position.y)
        width,height=self.editing_dimensions()
        x,y=max(0,min(width,x)),max(0,min(height,y))
        if snap and self.snap.value:
            step=int(self.spacing.value)
            x,y=math.floor(x/step+.5+1e-9)*step,math.floor(y/step+.5+1e-9)*step
        return x,y

    def refresh(self,update=True,properties=False,*,selection_only=False,changed_only=False):
        if not self.ready: return super().refresh(update,properties)
        if self.interaction is not None and not properties:
            self.interaction.render(update)
            return
        if self.floor not in self.document.floors or (self.floor!=CAMPUS and self.parent() is None): self.floor=CAMPUS
        parent=self.parent()
        targeted=selection_only or changed_only
        before_ui=self.ui_state() if targeted else {}
        previous_nodes=tuple(self.scene_stack.controls) if changed_only else ()
        before_graphics={id(c):id(c.shapes) for _,c in self.vector_cache.values()} if changed_only else {}
        before_images={id(c):(c.left,c.top,c.width,c.height) for _,c in self.image_cache.values()} if changed_only else {}
        if not selection_only:
            controls=render_scene(self.document,self.floor,self.collisions.value,self.grid.value,
                int(self.spacing.value),self.image_cache,self.vector_cache,show_coordinates=True,preview_item=self.preview,
                floor_underlay=reference_controls(self.document,self.floor,self.references,self.reference_cache) if not self.move_mode else (),
                hidden_buildings=getattr(self,"hidden_buildings",()),background_cache=self.background_cache,
                show_activators=self.show_activators.value and not self.move_mode)
        overlay=[]
        if not self.move_mode:
            if not getattr(self,"building_session",False): overlay.extend(active_floor_outline(self.document,self.floor,self.view_scale))
            overlay.extend(self.guide_shapes())
        if self.preview: overlay.extend(item_shapes(self.preview,parent,self.collisions.value,openings_for(self.items())))
        item=self.selected_item()
        selected_items=self.selection.items()
        if not self.move_mode:
            overlay.extend(self.selection.visuals())
            if item and len(selected_items)<=1: overlay.extend(selection_shapes(item,parent))
            for selected in selected_items:
                if selected.kind in STAIR_KINDS: overlay.extend(self.stair_indicator_shapes(selected))
        self.canvas.shapes=overlay
        self.canvas.width,self.canvas.height=self.document.width,self.document.height
        if not selection_only:controls.append(self.canvas)
        if self.move_mode:
            x,y=self.document.project(self.floor,*self.player)
            size=self.player_preferences.visual_size
            controls.append(player_collision_preview((x,y),self.player_preferences.collision_radius,self.player_selected))
            marker=user_marker(x-size/2,y-size/2,size)
            marker.on_click=self.select_player
            controls.append(marker)
        if not selection_only:self.scene_stack.controls=self.arrange_scene(controls)
        self.scene_stack.width=self.gesture.width=self.document.width
        self.scene_stack.height=self.gesture.height=self.document.height
        self.undo_button.disabled=not self.document.undo_stack
        self.redo_button.disabled=not self.document.redo_stack
        self.map_size_button.disabled=self.move_mode or bool(getattr(self,"building_session",False))
        self.duplicate_button.disabled=self.delete_button.disabled=item is None or self.move_mode
        self.building_actions.visible=bool(not getattr(self,"building_session",False) and self.floor==CAMPUS
            and item and item.kind=="building" and item.free_build and len(selected_items)==1)
        self.edit_building_button.disabled=self.move_mode or self.exporting or self.dialog_open
        self.selected_building_name.value=f"Building Name: {item.text}" if self.building_actions.visible else ""
        for kind,button in self.tool_buttons.items():
            button.bgcolor="#DBEAFE" if kind==self.tool else None
            button.disabled=self.move_mode
            if kind=="floor_activator":button.disabled=self.move_mode or not parent or self.floor.endswith(":Roof") or parent.floor_count<2
        if not item: self.selected=None
        references=self.references.layers(self.document,self.floor)
        self.reference_label.value=("Current floor only" if parent and not references else
            "Reference: " + ", ".join(key.split(":",1)[1] for key,_ in references) if references else "")
        if properties:
            self.map_width.value=f"{self.document.width:g}"
            self.map_height.value=f"{self.document.height:g}"
            if getattr(self,"building_session",False) and parent:
                options=[(scope_key(parent,layer),layer+(" ✓" if layer.startswith("Floor ") and int(layer.split()[-1]) in parent.completed_floors else ""))
                    for layer in self.document.layers(parent)]
            else:
                options=[(CAMPUS,"Campus / environment")]
                for building in self.document.buildings():
                    for layer in self.document.layers(building):options.append((scope_key(building,layer),f"{building.text} · {layer}"))
            self.dropdown_options(self.floor_picker,options)
            self.floor_picker.value=self.floor
            self.dropdown_options(self.object_picker,[(i.id,f"{i.kind}: {i.text}" if getattr(self,"building_session",False) else
                f"{i.kind.title()} · {i.text or i.id[:6]}") for i in self.editable_items()])
            self.object_picker.value=self.selected if item else None
            self.selected_label.value=f"Selected: {item.kind.replace('_',' ')}" if item else "No object selected"
            if len(selected_items)>1: self.selected_label.value=f"{len(selected_items)} objects selected (move together)"
            for field in [*self.properties.values(),self.mirror,self.blocks,self.length,self.floor_count]:
                field.disabled=item is None or self.move_mode or len(selected_items)>1
            self.length.visible=bool(item and item.kind in LINE_KINDS)
            self.railings.sync(item,len(selected_items)>1)
            self.collision_editor.sync(item,len(selected_items)>1)
            self.activator_editor.sync(item,len(selected_items)>1)
            self.blocks.visible=bool(item and item.kind in COLLISION_KINDS)
            self.floor_count.visible=bool(item and item.kind=="building")
            self.approach.visible=self.floor_count.visible
            owner_options=[("","No attachment")]+[(i.id,f"{i.kind}: {i.text}") for i in self.editable_items() if item and i.id!=item.id]
            if parent: owner_options.append((parent.id,"Building root"))
            self.dropdown_options(self.owner,owner_options)
            self.owner.value=item.parent_id or "" if item else ""
            self.owner.disabled=self.fade.disabled=not item or self.move_mode or len(selected_items)>1
            for control in (self.stair_direction,self.stair_to): control.visible=bool(item and item.kind in STAIR_KINDS)
            for control in (self.stair_right,self.stair_right_to): control.visible=bool(item and item.kind=="double_stairs")
            for control in (self.stair_direction,self.stair_right,self.stair_to,self.stair_right_to,self.approach):
                control.disabled=not item or self.move_mode or len(selected_items)>1
            if item:
                for key,field in self.properties.items(): field.value=str(getattr(item,key))
                self.mirror.value=item.mirrored
                self.blocks.value=item.blocking
                if item.kind in STAIR_KINDS:self.blocks.value=item.blocking and item.collision_thickness is not None
                self.length.value=f"{math.hypot(item.width,item.height):g}"
                self.floor_count.value=str(item.floor_count)
                self.fade.value=item.fade_when_obstructing
                self.approach.value=str(item.approach_distance)
                self.stair_direction.value=item.stair_direction
                self.stair_right.value=item.stair_right_direction
                self.stair_to.value=str(item.stair_to or "")
                self.stair_right_to.value=str(item.stair_right_to or "")
            else:
                for field in self.properties.values(): field.value=""
        if update:
            if targeted:
                after_ui=self.ui_state()
                dirty=[control for key,(control,state) in after_ui.items() if before_ui[key][1]!=state]
                if changed_only:
                    if tuple(id(c) for c in previous_nodes)!=tuple(id(c) for c in self.scene_stack.controls):dirty.append(self.scene_stack)
                    else:
                        dirty.extend(c for _,c in self.vector_cache.values() if before_graphics.get(id(c))!=id(c.shapes))
                        dirty.extend(c for _,c in self.image_cache.values() if before_images.get(id(c))!=(c.left,c.top,c.width,c.height))
                if not any(c is self.scene_stack for c in dirty):dirty.append(self.canvas)
                self.page.update(*dirty)
            else:self.page.update()

    def choose_tool(self,kind):
        if self.move_mode: return
        if kind=="floor_activator":
            parent=self.parent()
            if not parent or self.floor.endswith(":Roof") or parent.floor_count<2:
                self.status.value="Open a building floor with at least two floors to place an activator.";self.page.update(self.status);return
            self.show_activators.value=True
        if kind=="building" and not getattr(self,"building_session",False):
            self.open_building_editor()
            return
        if kind=="building" and self.floor!=CAMPUS:
            self.change_scope(CAMPUS)
        self.cancel_gesture(update=False)
        self.tool=kind
        self.viewer.pan_enabled=kind=="pan"
        for name,handler in (("on_pan_down",self.pointer_down),("on_pan_start",self.pan_start),
                ("on_pan_update",self.pointer_move),("on_pan_end",self.pointer_up),
                ("on_pan_cancel",self.cancel_gesture),("on_tap_up",self.tap)):
            setattr(self.gesture,name,None if kind=="pan" else handler)
        self.status.value=f"{dict(MAP_TOOLS)[kind]}: " + ("drag an endpoint to change length; cyan outline is the collision boundary."
            if kind=="railing" else "click a wall to align a walkable doorway; Width sets the opening size."
            if kind in OPENING_KINDS else "click to place or drag to draw. Square handles resize; ↻ rotates.")
        self.refresh(properties=True)

    def create_item(self,kind,x,y,w,h):
        item=super().create_item(kind,x,y,w,h)
        if kind in {"wall","room"}:return replace(item,collision_thickness=collision_thickness(item))
        if kind=="stairs": return replace(item,stair_direction=self.new_stair_direction)
        if kind=="floor": return replace(item,stroke=0,fill="#FFFFFF",blocking=False,text="Floor section")
        if kind=="railing":
            item=replace(item,stroke=10,color="#475569",text="Railing")
            return replace(item,collision_thickness=collision_thickness(item))
        if kind=="building": return replace(item,fill="#F5DF85",color="#263238",text="New building",opens=f"scene:{item.id}")
        if kind=="entry_zone": return replace(item,fill="none",color="#059669",text="Entry area",blocking=False)
        if kind=="floor_activator":
            source=int(self.floor.split()[-1]);target=source+1 if source<self.parent().floor_count else source-1
            return replace(item,text="Floor Activator",blocking=False,color="#7C3AED",fill="none",
                activator_from=source,activator_to=target,stair_direction="up" if target>source else "down")
        return item

    def hit_handle(self,item,x,y):
        return next((key for key,p in reversed(list(world_handles(item,self.parent()).items()))
            if math.hypot(x-p[0],y-p[1])<=14),None)

    def hit_item(self,event):
        x,y=self.point(event,snap=False)
        parent=self.parent()
        sx,sy=floor_scale(parent)
        tolerance=8/min(sx,sy)
        return next((i for i in reversed(self.editable_items()) if i.contains(x,y,tolerance)),None)

    def pointer_down(self,event):
        if self.move_mode or self.exporting or self.tool=="pan": return
        if self.interaction is not None: self.cancel_gesture(update=False)
        if self.tool=="select" and self.selection.down(event):
            self.begin_interaction()
            return
        self.origin=self.point(event,snap=False)
        self.before_gesture=self.document.snapshot()
        self.is_dragging=False
        self.drag_item=None
        self.active_handle=None
        if self.tool=="select":
            item=self.selected_item()
            self.active_handle=self.hit_handle(item,event.local_position.x,event.local_position.y) if item else None
            if not self.active_handle: item=self.hit_item(event)
            self.selected=item.id if item else None
            self.drag_item=item
            self.refresh(properties=True,selection_only=True)
        else:
            self.origin,_=snap_point(self.point(event,snap=False),self.alignment_items(),
                self.document.dimensions(self.floor),**self.snap_settings())
        self.begin_interaction()

    def pointer_move(self,event):
        if self.origin is None or self.move_mode or self.exporting: return
        if self.tool=="select" and self.selection.move(event): return
        self.is_dragging=True
        x,y=self.point(event,snap=False)
        ox,oy=self.origin
        if self.tool=="select" and self.drag_item:
            original=self.drag_item
            if self.active_handle:
                if self.active_handle=="rotate":
                    moved=transform(original,self.active_handle,self.origin,(x,y),int(self.spacing.value) if self.snap.value else 0)
                    self.alignment_guides=[]
                else:
                    moved,self.alignment_guides=snap_transform((x,y),
                        lambda p:transform(original,self.active_handle,self.origin,p),self.interaction_targets(),
                        self.editing_dimensions(),grid_origin=self.origin,resizing=True,**self.snap_settings())
            else:
                moved,self.alignment_guides=snap_transform((x,y),
                    lambda p:replace(original,x=original.x+p[0]-ox,y=original.y+p[1]-oy),self.interaction_targets(),
                    self.editing_dimensions(),grid_origin=self.origin,**self.snap_settings())
            self.interaction.put({moved.id:moved})
        elif self.tool in LINE_KINDS:
            (x,y),self.alignment_guides=snap_point((x,y),self.interaction_targets(),self.editing_dimensions(),**self.snap_settings())
            dx,dy=x-ox,y-oy
            if self.tool=="wall" and self.ortho.value:
                if abs(dx)>=abs(dy): dy=0
                else: dx=0
            self.preview=self.create_item(self.tool,ox,oy,dx,dy)
            if self.tool=="wall" and self.ortho.value:
                # Don't show a guide the straight-wall constraint discarded.
                endpoint=(ox+dx,oy+dy)
                self.alignment_guides=[g for g in self.alignment_guides if abs(endpoint[g.axis]-g.position)<1e-4]
        elif self.tool not in {"select","pan"}:
            (x,y),self.alignment_guides=snap_point((x,y),self.interaction_targets(),self.editing_dimensions(),**self.snap_settings())
            self.preview=self.create_item(self.tool,min(x,ox),min(y,oy),max(1,abs(x-ox)),max(1,abs(y-oy)))
        self.refresh()

    def pointer_up(self,event=None):
        if self.exporting: return
        # The throttled final move may arrive before the actual release.
        if self.is_dragging and self.origin is not None and getattr(event,"local_position",None) is not None:
            self.pointer_move(event)
        if self.selection.up(): return
        created=False
        transformed=bool(self.interaction and self.interaction.originals)
        if self.preview and self.origin:
            item=replace(self.preview,parent_id=owner_for(self.preview,self.items()))
            if (math.hypot(item.width,item.height)>=3 if item.kind in LINE_KINDS else item.width>=3 and item.height>=3):
                self.items().append(item)
                self.selected=item.id
                created=True
        if self.before_gesture is not None: self.document.remember(self.before_gesture)
        self.finish()
        if created: self.choose_tool("select")
        self.refresh(properties=True,changed_only=transformed)

    def tap(self,event):
        if self.move_mode or self.exporting: return
        current=self.selected_item()
        handle=self.hit_handle(current,event.local_position.x,event.local_position.y) if self.tool=="select" and current else None
        if handle:
            self.finish()
            if handle=="rotate": self.rotate()
            return
        if self.tool in MAP_STAMPS:
            x,y=self.point(event,snap=False)
            w,h=MAP_STAMPS[self.tool]
            before=self.document.snapshot()
            item=self.create_item(self.tool,x,y,w,h)
            item,_=snap_transform((x,y),lambda p:replace(item,x=p[0],y=p[1]),
                self.alignment_items(),self.document.dimensions(self.floor),**self.snap_settings())
            if self.tool in OPENING_KINDS:
                item=snap_opening_to_wall(item,self.items(),(x,y))
            item=replace(item,parent_id=owner_for(item,self.items()))
            self.items().append(item)
            self.selected=item.id
            self.document.remember(before)
            self.finish()
            self.choose_tool("select")
        elif self.tool=="select":
            item=self.hit_item(event)
            self.selection.select({item.id} if item else set())
        self.finish()
        self.refresh(properties=True)

    def finish(self):
        if getattr(self,"interaction",None) is not None:
            self.interaction.close()
            self.interaction=None
        super().finish()
        if hasattr(self,"railings"):self.railings.active=False
        if hasattr(self,"collision_editor"):self.collision_editor.active=False
        self.alignment_guides=[]
        if hasattr(self,"selection"): self.selection.finish()

    def editable_items(self):
        return [i for i in self.items() if self.show_activators.value or i.kind!="floor_activator"]

    def activators_visibility(self,event=None):
        self.cancel_gesture(update=False)
        self.selection.select(self.selection.ids & {i.id for i in self.editable_items()},False)
        if self.tool=="floor_activator" and not self.show_activators.value:self.tool="select"
        self.refresh(properties=True)

    def alignment_items(self):
        items=list(self.editable_items())
        if getattr(self,"building_session",False):
            items.extend(i for key,_ in self.references.layers(self.document,self.floor) for i in self.document.floors.get(key,[]) if i.kind!="floor_activator")
        return items

    def select_all(self):
        self.cancel_gesture(update=False)
        self.selection.select({i.id for i in self.editable_items()})
        self.refresh(properties=True)

    def deselect(self):
        self.cancel_gesture(update=False)
        self.selection.select(set(),False)
        self.refresh(properties=True)

    def stair_indicator_shapes(self,item):
        from .scene_renderer import project
        shapes=[]
        for start,end,label in indicators(item):
            a,b=[project(self.parent(),*item.local_to_world(*p)) for p in (start,end)]
            dx,dy=b[0]-a[0],b[1]-a[1]
            distance=math.hypot(dx,dy) or 1
            ux,uy=dx/distance,dy/distance
            paint=ft.Paint(color="#2563EB",stroke_width=2/self.view_scale)
            shapes.append(cv.Line(*a,*b,paint=paint))
            for sign in (-1,1):
                shapes.append(cv.Line(*b,b[0]-10*ux/self.view_scale+sign*5*uy/self.view_scale,
                    b[1]-10*uy/self.view_scale-sign*5*ux/self.view_scale,paint=paint))
            shapes.append(cv.Text(a[0],a[1],label,rotate=math.atan2(dy,dx)+math.pi/2,
                style=ft.TextStyle(size=11/self.view_scale,color="#2563EB",bgcolor="#FFFFFF")))
        return shapes

    def apply_stair_settings(self,event=None):
        item=self.selected_item()
        if item and item.kind in STAIR_KINDS and len(self.selection.items())==1 and not self.move_mode:
            changed=replace(item,stair_direction=self.stair_direction.value,stair_right_direction=self.stair_right.value,
                stair_to=None,stair_right_to=None)
            self.modify(lambda:self.document.floors.__setitem__(self.floor,[changed if i.id==item.id else i for i in self.items()]))

    def choose_stair(self,direction):
        self.new_stair_direction=direction
        self.choose_tool("stairs")
        self.status.value=f"Stair {direction.title()}: click to place or drag to draw; shading follows its own rotated travel axis."
        self.refresh()

    def attach_selected(self,event):
        item=self.selected_item()
        if item is None or self.move_mode or len(self.selection.items())>1: return
        owner=event.control.value or None
        if owner and item.id in related_owner_chain(self.items(),owner):
            self.status.value="An attachment cannot create a parent cycle."; self.refresh(); return
        changed=replace(item,parent_id=owner)
        self.modify(lambda:self.document.floors.__setitem__(self.floor,[changed if i.id==item.id else i for i in self.items()]))

    def open_building_editor(self,parent=None):
        if self.selection.locked():return
        if parent is not None:
            parent=next((b for b in self.document.buildings() if b.id==parent.id),None)
            if parent is None:
                self.status.value="That building is no longer on the map.";self.page.update(self.status);return
        self.cancel_gesture(update=False)
        self.active=False
        self.shortcuts.remove()
        from .building_editor import BuildingEditor
        self.builder=BuildingEditor(self,parent)
        self.builder.mount()

    def edit_this_building(self,event=None):
        parent=self.selected_item()
        if self.selection.locked() or self.floor!=CAMPUS or len(self.selection.items())!=1:return
        if parent and parent.kind=="building" and parent.free_build:self.open_building_editor(parent)

    def edit_building(self,event=None):
        parent=self.selected_item()
        if parent is None or parent.kind!="building": parent=self.parent()
        if parent is None:
            self.status.value="Select a building, then Edit This Building, or choose its floor in Editing layer."; self.refresh(); return
        self.open_building_editor(parent)

    def snap_settings(self):
        parent=self.parent()
        sx,sy=floor_scale(parent)
        return dict(pixels=float(self.snap_distance.value),smart=self.smart_snap.value,
            equal=self.equal_spacing.value,grid=int(self.spacing.value) if self.snap.value else 0,
            scale=(sx*self.view_scale,sy*self.view_scale))

    def snap_settings_changed(self,event=None):
        self.alignment_guides=[]
        self.refresh()

    def guide_shapes(self):
        shapes=[]
        color="#D946EF"
        from .scene_renderer import project
        parent=self.parent()
        for guide in self.alignment_guides:
            def point(along,cross):
                return project(parent,*((along,cross) if guide.axis==0 else (cross,along)))
            scale=self.snap_settings()["scale"][1-guide.axis]
            margin=12/max(scale,1e-9)
            a,b=point(guide.position,guide.start-margin),point(guide.position,guide.end+margin)
            shapes.append(cv.Line(*a,*b,paint=ft.Paint(color=color,stroke_width=1/self.view_scale)))
            shapes.append(cv.Text(a[0]+4/self.view_scale,a[1]-14/self.view_scale,guide.label,
                style=ft.TextStyle(size=11/self.view_scale,color=color,bgcolor="#FFFFFF")))
            for start,end in guide.gaps:
                a,b=point(start,guide.end),point(end,guide.end)
                shapes.append(cv.Line(*a,*b,paint=ft.Paint(color=color,stroke_width=2/self.view_scale)))
                for x,y in (a,b):
                    shapes.append(cv.Circle(x,y,3/self.view_scale,paint=ft.Paint(color=color)))
        return shapes

    def resize_map(self,width,height):
        if not self.active or self.move_mode or self.exporting or getattr(self,"building_session",False):
            self.status.value="Return to the Map Editor and stop Test walk before resizing the map."
            self.page.update()
            return False
        try:
            width,height=checked_map_size(self.document,width,height)
        except ValueError as error:
            self.status.value=f"Map not resized: {error}"
            self.page.update()
            return False
        if (width,height)!=(self.document.width,self.document.height):
            def apply(): self.document.width,self.document.height=width,height
            self.modify(apply)
        self.status.value=f"Map resized to {width:g} × {height:g}. Objects kept in place. Use Save map to keep this size."
        self.page.update()
        return True

    def map_size_settings(self,event=None):
        if not self.active or self.move_mode or self.exporting or self.dialog_open or getattr(self,"building_session",False): return
        self.cancel_gesture(update=False)
        self.map_width.value=f"{self.document.width:g}"
        self.map_height.value=f"{self.document.height:g}"
        self.dialog_open=True
        error=ft.Text(color="#DC2626",size=12,visible=False)
        def dismissed(e): self.dialog_open=False
        def close(e=None):
            self.page.pop_dialog()
            self.dialog_open=False
        def apply(e):
            if self.resize_map(self.map_width.value,self.map_height.value): close()
            else:
                error.value=self.status.value
                error.visible=True
                self.page.update()
        self.page.show_dialog(ft.AlertDialog(modal=True,title=ft.Text("Resize map canvas"),
            on_dismiss=dismissed,
            content=ft.Column(width=420,tight=True,controls=[ft.Row(controls=[self.map_width,self.map_height]),
                ft.Text(f"Each dimension: {MIN_MAP_SIZE}–{MAX_MAP_SIZE} map units. "
                    "Buildings and floor objects keep their positions and sizes. "
                    "Shrinking cannot cut off placed objects. Ctrl+Z / Ctrl+Y can undo / redo a resize.",size=12),error]),
            actions=[ft.TextButton("Cancel",on_click=close),ft.Button("Resize map",on_click=apply)]))

    def reference_settings(self,event=None):
        self.cancel_gesture(update=False)
        self.dialog_open=True
        previous=ft.Checkbox(label="Show previous floor",value=self.references.previous)
        multiple=ft.Checkbox(label="Show all lower floors (older floors fade further)",value=self.references.multiple)
        focus=ft.Checkbox(label="Focus only on current floor",value=self.references.focus)
        opacity=ft.Slider(min=0,max=.6,divisions=30,value=self.references.opacity,label="{value}")
        percentage=ft.Text()
        other=ft.Checkbox(label="Show other floors too (including higher floors)",value=self.references.all_other)
        def changed(e=None):
            self.references.previous=bool(previous.value)
            self.references.multiple=bool(multiple.value)
            self.references.focus=bool(focus.value)
            self.references.all_other=bool(other.value)
            self.references.opacity=float(opacity.value)
            percentage.value=f"Reference opacity: {round(opacity.value*100)}%"
            multiple.disabled=opacity.disabled=other.disabled=not previous.value or focus.value
            self.refresh()
        def close(e):
            self.page.pop_dialog()
            self.dialog_open=False
        for control in (previous,multiple,focus,opacity,other): control.on_change=changed
        changed()
        self.page.show_dialog(ft.AlertDialog(modal=True,title=ft.Text("Floor reference view"),
            content=ft.Column(width=450,tight=True,controls=[previous,multiple,focus,percentage,opacity,other,
                ft.Text("Gray reference floors cannot be selected, moved, or used as player collisions. "
                    "Switch Editing layer to edit them. These settings do not change saved maps or the main app.",size=12)]),
            actions=[ft.TextButton("Done",on_click=close)]))

    def view_interaction_start(self,event):
        self.gesture_scale=self.view_scale

    def view_interaction_update(self,event):
        scale=max(self.viewer.min_scale,min(self.viewer.max_scale,self.gesture_scale*event.scale))
        if abs(scale-self.view_scale)>1e-9:
            self.view_scale=scale
            self.refresh()

    async def zoom_in(self,event=None):
        await self.viewer.zoom(1.25)
        self.view_scale=min(self.viewer.max_scale,self.view_scale*1.25)
        self.refresh()

    async def zoom_out(self,event=None):
        await self.viewer.zoom(.8)
        self.view_scale=max(self.viewer.min_scale,self.view_scale*.8)
        self.refresh()

    async def reset_view(self,event=None):
        await self.viewer.reset()
        self.view_scale=self.gesture_scale=1.
        self.refresh()

    def select_object(self,event):
        if event.control.value not in {i.id for i in self.editable_items()}:return
        self.cancel_gesture(update=False)
        self.selection.select({event.control.value})
        self.refresh(properties=True)

    def change_scope(self,scope):
        self.cancel_gesture(update=False)
        self.document.floors.setdefault(scope,[])
        self.floor=scope
        self.selected=None
        self.direction=(0,0)
        self.player=(self.document.dimensions(scope)[0]/2,50)
        self.status.value="Campus editing." if scope==CAMPUS else "Editing this floor directly on the map. PNG wall lines are references; draw Walls / Railings to add collision."
        self.refresh(properties=True)

    def change_floor(self,event):
        scope=event.control.value
        if not getattr(self,"building_session",False) and scope!=CAMPUS:
            parent=self.document.parent_for_scope(scope)
            if parent:
                self.open_building_editor(parent)
                self.builder.change_scope(scope)
                return
        self.change_scope(scope)

    def history(self,redo):
        self.cancel_gesture(update=False)
        self.document.redo() if redo else self.document.undo()
        # Keep the same object selected after undo if it still exists.
        self.name.value=self.document.name
        self.refresh(properties=True)

    def nudge(self,dx,dy):
        """Translate selection in map-axis directions, keeping all its geometry."""
        if (not self.active or self.move_mode or self.exporting or self.dialog_open
                or self.origin is not None or self.preview is not None or self.interaction is not None):
            return
        item=self.selected_item()
        if item is None or not (dx or dy): return
        if self.parent():
            # A rotated/mirrored building shouldn't flip arrow directions.
            world=self.document.project(self.floor,item.x,item.y)
            local=self.document.unproject(self.floor,world[0]+dx,world[1]+dy)
            lx,ly=local[0]-item.x,local[1]-item.y
            length=math.hypot(lx,ly)
            if not length: return
            step=math.hypot(dx,dy)
            dx,dy=lx*step/length,ly*step/length
        changed=replace(item,x=item.x+dx,y=item.y+dy)
        try: validate_item(changed)
        except ValueError as error:
            self.status.value=f"Object not moved: {error}"
            self.page.update()
            return
        self.status.value="Arrow nudge: 1 unit · Shift+arrow: 10 units · Ctrl+arrow: 0.1 unit · Ctrl+Z to undo."
        if len(self.selection.items())>1:
            try: self.selection.translate(dx,dy)
            except ValueError as error: self.status.value=f"Object not moved: {error}"; self.refresh()
            return
        self.modify(lambda:self.document.floors.__setitem__(self.floor,
            [changed if i.id==item.id else i for i in self.items()]))

    def apply_properties(self,event=None):
        item=self.selected_item()
        if item is None or len(self.selection.items())>1: return
        try:
            values={key:(field.value if key in {"text","color","fill"} else int(field.value) if key=="steps" else float(field.value))
                for key,field in self.properties.items()}
            if item.kind in LINE_KINDS:
                length=float(self.length.value)
                # Width/height wins unless the separate Length field changed.
                if not math.isclose(length,math.hypot(item.width,item.height),rel_tol=1e-8):
                    if not math.isfinite(length) or length<=0: raise ValueError("Length must be positive")
                    current=math.hypot(values["width"],values["height"]) or 1
                    values["width"]*=length/current
                    values["height"]*=length/current
            count=int(self.floor_count.value) if item.kind=="building" else item.floor_count
            if item.free_build and count!=item.floor_count:
                raise ValueError("Use Building Editor: Floor Done / Remove current floor to change the floor count")
            if item.layer_style and count!=item.floor_count: raise ValueError("Existing floor images determine this building's floor count")
            if count<item.floor_count and any(self.document.floors.get(scope_key(item,f"Floor {n}")) for n in range(count+1,item.floor_count+1)):
                raise ValueError("Delete objects on the higher floors before reducing floor count")
            changed=replace(item,**values,mirrored=self.mirror.value,blocking=self.blocks.value if item.kind in COLLISION_KINDS else item.blocking,floor_count=count,
                collision_thickness=collision_thickness(item) if item.kind in {"wall","room","railing"} or
                    (item.kind in STAIR_KINDS and self.blocks.value) else item.collision_thickness,
                completed_floors=tuple(n for n in item.completed_floors if n<=count),fade_when_obstructing=self.fade.value,
                approach_distance=float(self.approach.value) if item.kind=="building" else item.approach_distance,
                stair_to=int(self.stair_to.value) if item.kind in STAIR_KINDS and self.stair_to.value.strip() else None,
                stair_right_to=int(self.stair_right_to.value) if item.kind=="double_stairs" and self.stair_right_to.value.strip() else None)
            validate_item(changed)
            def apply():
                self.document.floors[self.floor]=[changed if i.id==item.id else i for i in self.items()]
                for n in range(count+1,item.floor_count+1): self.document.floors.pop(scope_key(item,f"Floor {n}"),None)
            self.modify(apply)
        except (ValueError,TypeError) as error:
            self.status.value=f"Properties not applied: {error}"
            self.page.update()

    def duplicate(self,event=None):
        item=self.selected_item()
        if item is None or self.move_mode: return
        self.selection.duplicate()

    def delete(self,event=None):
        item=self.selected_item()
        if item is None or self.move_mode: return
        self.selection.delete()

    def save_map(self,event=None):
        self.cancel_gesture(update=False)
        def save():
            try:
                save_scene(self.document)
                self.load_error=None
                self.status.value="Map saved. Buildings, editable objects and collisions will reload together."
            except (OSError,ValueError,TypeError) as error: self.status.value=f"Map not saved: {error}"
            self.refresh()
        if self.load_error: self.confirm("The previous saved map could not load. Replace that saved workspace?",save)
        else: save()

    def export_placements(self,event=None):
        self.cancel_gesture(update=False)
        code=placement_code([to_placement(b) for b in self.document.buildings()])
        status=ft.Text("Building placements only. Use Save map to keep floor objects, walls and railings too.")
        self.dialog_open=True
        def close(e):
            self.page.pop_dialog()
            self.dialog_open=False
        async def copy(e):
            try:
                await ft.Clipboard().set(code)
                status.value="Copied building placements. Paste over BUILDINGS_ON_MAP in src/map/placements.py."
            except Exception: status.value="Clipboard unavailable; select and copy the text manually."
            status.update()
        self.page.show_dialog(ft.AlertDialog(modal=True,title=ft.Text("Export building placements"),
            content=ft.Column(width=650,tight=True,controls=[status,
                ft.TextField(value=code,read_only=True,multiline=True,min_lines=10,max_lines=15,text_size=12)]),
            actions=[ft.Button("Copy placements",on_click=copy),ft.TextButton("Close",on_click=close)]))

    async def load_map(self,event=None):
        if self.document.dirty:
            self.dialog_open=True
            def cancel(e):
                self.page.pop_dialog()
                self.dialog_open=False
            async def load(e):
                self.page.pop_dialog()
                self.dialog_open=False
                await self.pick_map()
            self.page.show_dialog(ft.AlertDialog(modal=True,title=ft.Text("Load another map? Unsaved edits will be replaced."),
                actions=[ft.TextButton("Cancel",on_click=cancel),ft.Button("Load",on_click=load)]))
        else: await self.pick_map()

    async def pick_map(self):
        try:
            files=await self.picker.pick_files(allowed_extensions=["json"],file_type=ft.FilePickerFileType.CUSTOM,with_data=True)
            if not files: return
            loaded=MapScene.from_json(files[0].bytes.decode("utf-8-sig"))
            self.document=loaded
            self.name.value=loaded.name
            self.floor=CAMPUS
            self.selected=None
            self.image_cache.clear()
            self.vector_cache.clear()
            self.status.value="Map loaded; use Save map to make this the demo's startup scene."
            self.refresh(properties=True)
        except (ValueError,TypeError,AttributeError,OSError) as error:
            self.status.value=f"Map not loaded; current edits kept: {error}"
            self.refresh()

    def import_document(self,draft,parent=None):
        before=self.document.snapshot()
        floor_names=[name for name in draft.floors if name.lower()!="roof"]
        if parent is None:
            parent=self.create_item("building",100,100,320,200)
            parent=replace(parent,text=draft.name,floor_count=max(1,len(floor_names)))
            self.document.floors[CAMPUS].append(parent)
        from .selection import clone_bundle
        originals=[i for children in draft.floors.values() for i in children if i.kind!="building"]
        clones,_=clone_bundle(originals,{})
        cloned={old.id:new for old,new in zip(originals,clones)}
        number=0
        for name,items in draft.floors.items():
            if name.lower()!="roof": number+=1
            layer="Roof" if name.lower()=="roof" else f"Floor {number}"
            if layer!="Roof" and number>parent.floor_count: break
            # Bake source coords into the shared floor canvas, keeping objects editable.
            scale=min(1436/draft.width,751/draft.height)
            ox,oy=(1436-draft.width*scale)/2,(751-draft.height*scale)/2
            children=[replace(cloned[i.id],x=i.x*scale+ox,y=i.y*scale+oy,
                width=i.width*scale,height=i.height*scale,stroke=i.stroke*scale,font_size=i.font_size*scale)
                for i in items if i.kind!="building"]
            self.document.floors[scope_key(parent,layer)]=children
        self.document.remember(before)
        self.floor=scope_key(parent,"Floor 1")
        self.document.floors.setdefault(self.floor,[])
        self.selected=None
        self.status.value="Editable draft imported into this building's floor layers on the map."
        self.refresh(properties=True)

    async def import_draft(self,event=None):
        try:
            files=await self.picker.pick_files(allowed_extensions=["json"],file_type=ft.FilePickerFileType.CUSTOM,with_data=True)
            if files: self.import_document(DraftDocument.from_json(files[0].bytes.decode("utf-8-sig")))
        except (ValueError,TypeError,AttributeError,OSError) as error:
            self.status.value=f"Draft not imported: {error}"
            self.refresh()

    def edit_saved_draft(self,event=None):
        parent=self.selected_item()
        if not parent or parent.kind!="building":
            self.status.value="Select an image-based draft building first, or use Editing layer for any building's floor."
            self.refresh()
            return
        if not parent.image_src or not parent.image_src.endswith(".svg"):
            self.change_scope(scope_key(parent,"Floor 1"))
            return
        try:
            path=(ASSETS_DIR/parent.image_src).with_suffix(".json")
            if not path.resolve().is_relative_to(ASSETS_DIR.resolve()): raise ValueError("Draft path is outside assets")
            draft=DraftDocument.from_json(path.read_text(encoding="utf-8-sig"))
            def convert():
                before=self.document.snapshot()
                editable=replace(parent,image_src=None,floor_count=max(1,len([f for f in draft.floors if f.lower()!="roof"])))
                for key in list(self.document.floors):
                    if key.startswith(f"{parent.id}:"): self.document.floors.pop(key)
                self.document.floors[CAMPUS]=[editable if i.id==parent.id else i for i in self.document.floors[CAMPUS]]
                self.import_document(draft,editable)
                # One undo restores both the image placement and all its objects.
                self.document.undo_stack.pop()
                self.document.remember(before)
            if any(self.document.floors.get(scope_key(parent,layer)) for layer in self.document.layers(parent)):
                self.confirm("Replace this building's edited floor objects with its saved draft?",convert)
            else: convert()
        except (ValueError,OSError,TypeError) as error:
            self.status.value=f"Editable draft unavailable; the original image is kept: {error}"
            self.refresh()

    def set_direction(self,x,y): self.direction=(x,y)

    def select_player(self,event=None):
        if not self.move_mode:return
        self.player_selected=True;self.player_controls.control.visible=True
        self.player_controls.sync();self.refresh();self.player_controls.control.update()

    def deselect_player(self,event=None):
        self.player_selected=False;self.player_controls.control.visible=False
        self.refresh();self.player_controls.control.update()

    def apply_player_preferences(self,settings):
        if settings.collision_radius>min(self.document.width,self.document.height)/2:
            raise ValueError("Collision radius must fit inside the map.")
        self.player_preferences=settings;self.refresh()

    def player_barriers(self):
        key=(self.floor,self.parent(),tuple(self.items()))
        if self.player_barrier_cache is None or self.player_barrier_cache[0]!=key:
            compiled=project_barriers(barriers_for(key[2]),
                lambda x,y:self.document.project(self.floor,x,y),floor_scale(self.parent()))
            self.player_barrier_cache=(key,compiled)
        return self.player_barrier_cache[1]

    def toggle_walk(self,event=None):
        self.cancel_gesture(update=False)
        if not self.move_mode:
            width,height=self.document.width,self.document.height
            spawn=find_free_position(*self.document.project(self.floor,*self.player),
                self.player_preferences.collision_radius,self.player_barriers(),width,height)
            if spawn is None:
                self.status.value="No free space for the demo player on this layer. Move or disable a barrier first."
                self.refresh()
                return
            self.player=self.document.unproject(self.floor,*spawn)
        self.move_mode=not self.move_mode
        self.direction=(0,0)
        self.joystick_control.visible=self.move_mode
        self.select_player_button.visible=self.move_mode
        self.player_selected=False;self.player_controls.control.visible=False
        self.joystick.set_enabled(self.move_mode)
        self.walk_button.content="Finish test walk" if self.move_mode else "Test walk"
        self.floor_picker.disabled=self.object_picker.disabled=self.move_mode
        self.sidebar.disabled=self.move_mode
        self.viewer.pan_enabled=not self.move_mode and self.tool=="pan"
        for name,handler in (("on_pan_down",self.pointer_down),("on_pan_start",self.pan_start),
                ("on_pan_update",self.pointer_move),("on_pan_end",self.pointer_up),
                ("on_pan_cancel",self.cancel_gesture),("on_tap_up",self.tap)):
            setattr(self.gesture,name,None if self.move_mode or self.tool=="pan" else handler)
        self.status.value="Joystick test: walls and railings block movement. Cyan boundaries are physical barrier thickness, not routing guidance." if self.move_mode else "Editing resumed."
        self.refresh(properties=True)

    def move_player(self,dx,dy):
        width,height=self.document.width,self.document.height
        before=self.player
        start=self.document.project(self.floor,*self.player)
        target=self.document.project(self.floor,self.player[0]+dx,self.player[1]+dy)
        moved=move_with_collisions(*start,target[0]-start[0],target[1]-start[1],self.player_preferences.collision_radius,
            self.player_barriers(),width,height)
        self.player=self.document.unproject(self.floor,*moved)
        return self.player[0]-before[0],self.player[1]-before[1]

    async def movement_loop(self):
        while not getattr(self,"closed",False):
            await asyncio.sleep(1/30)
            if not self.active or not self.move_mode or self.direction==(0,0): continue
            dx,dy=self.move_player(self.direction[0]*10,self.direction[1]*10)
            if dx or dy:
                self.refresh()
                before=self.document.project(self.floor,self.player[0]-dx,self.player[1]-dy)
                after=self.document.project(self.floor,*self.player)
                await self.viewer.pan(before[0]-after[0],before[1]-after[1])

    def run_demo(self,event=None):
        self.cancel_gesture(update=False)
        self.active=False
        self.shortcuts.remove()
        from .demo_preview import EditorDemoPreview
        def resume():
            self.player_preferences=preview.player_settings()
            self.mount()
        preview=EditorDemoPreview(self.page,scene=self.document,on_edit=resume,
            player_settings=self.player_preferences)
