"""Retained gesture updates for drag/resize/draw — editor only."""

import flet as ft
from dataclasses import replace
from navigation.collision import OpeningIndex,openings_for
from .alignment import AlignmentIndex,bounds
from .scene_renderer import item_shapes,selection_shapes,project,building_image
from .selection import aggregate
from .reference_layers import active_floor_outline


class Interaction:
    def __init__(self,editor):
        self.editor=editor
        self.parent=editor.document.parent_for_scope(editor.floor)
        self.dimensions=editor.document.dimensions(editor.floor)
        selected=tuple(editor.selection.drag or ([editor.drag_item] if editor.drag_item else []))
        self.originals={i.id:i for i in selected}
        self.current=dict(self.originals)
        self.slots={i.id:n for n,i in enumerate(editor.items()) if i.id in self.originals}
        self.floor_items=editor.items()
        self.alignment=AlignmentIndex(editor.alignment_items(),self.originals)
        self.openings=OpeningIndex(openings_for(self.floor_items))
        self.group_bounds=aggregate(selected) if len(selected)>1 else None
        self.group_current=self.group_bounds
        self.group_boxes=tuple(bounds(i) for i in selected) if self.group_bounds else ()
        self.static_overlay=active_floor_outline(editor.document,editor.floor,editor.view_scale) if not getattr(editor,"building_session",False) else ()
        self.last_state=None
        self.last_updated=False
        self.live_collisions=False
        self.records=[]
        self.image_records=[]
        self.child_contexts={}
        owners={i.id for i in selected if i.kind=="building"}
        visible={id(node) for node in editor.scene_stack.controls}
        reference=getattr(editor,"map_reference",None)
        if reference is not None: visible.update(id(node) for node in reference.content.controls)
        self.child_scopes={item.id:scope for scope,items in editor.document.floors.items()
            if scope.split(":",1)[0] in owners for item in items}
        for key,(signature,control) in editor.vector_cache.items():
            if id(control) not in visible: continue
            owner=signature[1]
            if key not in self.originals and (owner is None or owner.id not in owners): continue
            self.records.append((key,control,control.left,control.top,control.shapes,signature))
        for key,cached in editor.image_cache.items():
            if key not in owners or id(cached[1]) not in visible: continue
            control=cached[1]
            wrapper=None
            if editor.active_handle:
                wrapper=ft.Stack(width=editor.document.width,height=editor.document.height,controls=[control])
                # Only resize/rotation needs a wrapper; translations keep the tree.
                for number,node in enumerate(editor.scene_stack.controls):
                    if node is control: editor.scene_stack.controls[number]=wrapper;break
            self.image_records.append((key,control,control.left,control.top,cached,wrapper))
        if any(record[-1] is not None for record in self.image_records):editor.page.update(editor.scene_stack)

    def items(self):
        return [self.current[key] for key in self.originals if key in self.editor.selection.ids or key==self.editor.selected]

    def put(self,updates):
        for key,item in updates.items():
            self.floor_items[self.slots[key]]=item
            self.current[key]=item

    def render(self,update=True):
        editor=self.editor
        state=(tuple(self.current.values()),editor.preview,tuple(editor.alignment_guides),
            editor.selection.box,editor.selection.box_end,editor.view_scale)
        if state==self.last_state and (not update or self.last_updated):return
        self.last_state=state
        self.last_updated=update
        dirty=[]
        for key,control,left,top,shapes,signature in self.records:
            original=signature[0]
            old_parent=signature[1]
            current=self.current.get(key,original)
            new_parent=self.current.get(old_parent.id,old_parent) if old_parent else None
            moved_parent=old_parent is not None and old_parent.id in self.current
            before=self.originals[old_parent.id] if moved_parent else self.originals[key]
            after=new_parent if moved_parent else current
            translation=replace(before,x=after.x,y=after.y)==after
            if translation:
                if moved_parent: dx,dy=after.x-before.x,after.y-before.y
                else:
                    a,b=project(self.parent,before.x,before.y),project(self.parent,after.x,after.y)
                    dx,dy=b[0]-a[0],b[1]-a[1]
                control.left=(left or 0)+dx;control.top=(top or 0)+dy
                # Reuse geometry and guides — no collision work during translation.
            else:
                control.left,control.top=left,top
                if moved_parent:
                    # Child floor data stays put; only the parent's visible pieces change.
                    scope=self.child_scopes[key]
                    context=self.child_contexts.get(scope)
                    if context is None:
                        context=self.child_contexts[scope]=OpeningIndex(openings_for(editor.document.floors.get(scope,[])))
                else: context=self.openings
                control.shapes=list(item_shapes(current,new_parent,self.live_collisions and editor.collisions.value,context.for_wall(current)))
            dirty.append(control)
        for key,control,left,top,cached,wrapper in self.image_records:
            original,after=self.originals[key],self.current[key]
            if (original.width,original.height,original.rotation,original.mirrored)==(
                    after.width,after.height,after.rotation,after.mirrored):
                control.left=(left or 0)+after.x-original.x;control.top=(top or 0)+after.y-original.y
                dirty.append(control)
            else:
                wrapper.controls=[building_image(after,cached[0][1],True)]
                dirty.append(wrapper)
        overlay=list(self.static_overlay)
        if editor.preview:
            overlay.extend(item_shapes(editor.preview,self.parent,False,self.openings.for_wall(editor.preview)))
        overlay.extend(editor.guide_shapes())
        overlay.extend(editor.selection.visuals())
        selected=editor.selected_item()
        if selected and len(self.current)<=1: overlay.extend(selection_shapes(selected,self.parent))
        for item in self.items():
            if item.kind in {"stairs","double_stairs"}: overlay.extend(editor.stair_indicator_shapes(item))
        editor.canvas.shapes=overlay
        dirty.append(editor.canvas)
        if update: editor.page.update(*dirty)

    def close(self):
        # Restore the retained baseline before the final render, including on cancel.
        # Cache signatures still match this baseline, not the temporary preview.
        for key,control,left,top,shapes,signature in self.records:
            control.left,control.top,control.shapes=left,top,shapes
        for key,control,left,top,cached,wrapper in self.image_records:
            control.left,control.top=left,top
