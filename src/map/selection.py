"""Multi-select, group relationships, and bundle ops — editor only."""

from dataclasses import replace
import math
import uuid
import re
from .alignment import bounds,snap_transform
from .scene import CAMPUS,scope_key
from .scene_renderer import path_shape,project


def owner_for(item,items):
    from navigation.collision import wall_edges,opening_axis
    if item.kind in {"door","double_door","opening","window"}:
        a,b,_=opening_axis(item)
        center=((a[0]+b[0])/2,(a[1]+b[1])/2)
        candidates=[]
        for wall in items:
            for start,end,radius in wall_edges(wall):
                dx,dy=end[0]-start[0],end[1]-start[1]
                length2=dx*dx+dy*dy
                t=((center[0]-start[0])*dx+(center[1]-start[1])*dy)/length2 if length2 else -1
                distance=math.hypot(center[0]-start[0]-t*dx,center[1]-start[1]-t*dy)
                if 0<=t<=1 and distance<=radius+8: candidates.append((distance,wall.id))
        if candidates: return min(candidates)[1]
    if item.kind not in {"room","building","entry_zone"}:
        center=item.local_to_world(item.width/2,item.height/2)
        rooms=[room for room in items if room.kind=="room" and room.contains(*center,tolerance=0)]
        if rooms: return min(rooms,key=lambda room:room.width*room.height).id
    return None


def related_owner_chain(items,owner):
    parents={i.id:i.parent_id for i in items}
    result=set()
    while owner and owner not in result:
        result.add(owner)
        owner=parents.get(owner)
    return result


def aggregate(items):
    from drafting.models import DraftItem
    boxes=[bounds(i) for i in items]
    x,y=min(b[0][0] for b in boxes),min(b[1][0] for b in boxes)
    return DraftItem("rectangle",x,y,max(1,max(b[0][1] for b in boxes)-x),
                     max(1,max(b[1][1] for b in boxes)-y),id="selection-bounds")


def related(items,ids,ancestors=False,*,structures=False):
    """Manual groups always expand; attachments/proximity only on explicit request."""
    ids=set(ids)
    changed=True
    while changed:
        previous=set(ids)
        selected=[i for i in items if i.id in ids]
        if structures and ancestors:
            valid={i.id for i in items}
            ids.update(i.parent_id for i in selected if i.parent_id in valid)
        groups={i.group_id for i in selected if i.group_id}
        rooms=[i for i in selected if i.kind=="room"] if structures else []
        for item in items:
            if (structures and item.parent_id in ids) or (item.group_id and item.group_id in groups):
                ids.add(item.id)
            if item.id in ids or item.kind in {"building","entry_zone"}: continue
            # A room selection includes its furniture, stairs, and railings.
            for room in rooms:
                points=[item.local_to_world(*p) for p in
                        ((0,0),(item.width,0),(item.width,item.height),(0,item.height))]
                if all(room.contains(*p,tolerance=1e-6) for p in points):
                    ids.add(item.id)
                    break
        changed=ids!=previous
    return ids


def clone_bundle(roots,floors):
    all_items=[*roots,*[c for children in floors.values() for c in children]]
    ids={i.id:uuid.uuid4().hex for i in all_items}
    groups={i.group_id:uuid.uuid4().hex for i in all_items if i.group_id}
    def clone(item):
        return replace(item,id=ids[item.id],parent_id=ids.get(item.parent_id),
            group_id=groups.get(item.group_id),
            activator_stair=ids.get(item.activator_stair,item.activator_stair),
            opens=f"scene:{ids[item.id]}" if item.kind=="building" and (not item.opens or item.opens.startswith("scene:")) else item.opens)
    new_roots=[clone(i) for i in roots]
    new_floors={f"{ids[key.split(':',1)[0]]}:{key.split(':',1)[1]}":[clone(i) for i in children]
                for key,children in floors.items()}
    return new_roots,new_floors


class SelectionController:
    def __init__(self,editor):
        self.editor=editor
        self.ids=set()
        self.anchor=None
        self.drag=()
        self.box=None
        self.box_end=None
        self.clipboard=None

    def locked(self):
        editor=self.editor
        return editor.move_mode or editor.exporting or editor.dialog_open or not editor.active

    def sync(self):
        editor=self.editor
        valid=set(editor.interaction.current) if getattr(editor,"interaction",None) is not None else {i.id for i in editor.items()}
        if editor.selected!=self.anchor:
            self.ids={editor.selected} if editor.selected in valid else set()
            self.anchor=editor.selected
        self.ids &= valid

    def items(self):
        self.sync()
        if getattr(self.editor,"interaction",None) is not None: return self.editor.interaction.items()
        return [i for i in self.editor.items() if i.id in self.ids]

    def select(self,ids,expand=True,*,structure=False):
        editor=self.editor
        allowed=editor.editable_items()
        self.ids=related(allowed,ids,structure,structures=structure) if expand else set(ids)
        self.ids &= {i.id for i in allowed}
        self.anchor=next((i.id for i in allowed if i.id in self.ids),None)
        editor.selected=self.anchor

    def select_structure(self):
        editor=self.editor
        if self.locked() or not editor.smart_structure.value:return
        editor.cancel_gesture(update=False)
        self.select(self.ids,structure=True)
        editor.status.value="Related structure selected temporarily. Only Group creates a manual group."
        editor.refresh(properties=True,selection_only=True)

    def down(self,event):
        editor=self.editor
        self.sync()
        point=editor.point(event,snap=False)
        hit=editor.hit_item(event)
        if not hit and len(self.ids)>1:
            area=aggregate(self.items())
            if area.contains(*point,tolerance=0): hit=self.items()[0]
        current=editor.selected_item()
        if len(self.ids)<=1 and current and editor.hit_handle(current,event.local_position.x,event.local_position.y):
            return False
        if hit:
            ids=self.ids if hit.id in self.ids else related(editor.editable_items(),{hit.id})
            self.select(ids)
            if len(self.ids)<=1: return False
            self.drag=tuple(self.items())
            editor.drag_item=self.drag[0]
            editor.origin=point
            editor.before_gesture=editor.document.snapshot()
        else:
            self.select((),False)
            self.box=self.box_end=point
            editor.origin=point
            editor.before_gesture=editor.document.snapshot()
        editor.refresh(properties=True,selection_only=True)
        return True

    def move(self,event):
        editor=self.editor
        if self.box is None and not self.drag: return False
        point=editor.point(event,snap=False)
        if self.box is not None:
            self.box_end=point
            editor.is_dragging=True
            editor.refresh()
            return True
        if not self.drag: return False
        editor.is_dragging=True
        original=editor.interaction.group_bounds
        ox,oy=editor.origin
        others=editor.interaction_targets()
        moved,editor.alignment_guides=snap_transform(point,
            lambda p:replace(original,x=original.x+p[0]-ox,y=original.y+p[1]-oy),others,
            editor.editing_dimensions(),grid_origin=editor.origin,**editor.snap_settings())
        dx,dy=moved.x-original.x,moved.y-original.y
        updates={i.id:replace(i,x=i.x+dx,y=i.y+dy) for i in self.drag}
        editor.interaction.group_current=moved
        editor.interaction.put(updates)
        editor.refresh()
        return True

    def up(self):
        editor=self.editor
        transformed=bool(self.drag)
        if self.box is not None:
            ax,bx=sorted((self.box[0],self.box_end[0]))
            ay,by=sorted((self.box[1],self.box_end[1]))
            self.select({i.id for i in editor.editable_items() if
                bounds(i)[0][0]>=ax and bounds(i)[0][1]<=bx and bounds(i)[1][0]>=ay and bounds(i)[1][1]<=by})
        elif self.drag:
            editor.document.remember(editor.before_gesture)
        else: return False
        editor.finish()
        editor.refresh(properties=True,selection_only=not transformed,changed_only=transformed)
        return True

    def finish(self):
        self.drag=()
        self.box=self.box_end=None

    def visuals(self):
        editor=self.editor
        items=self.items()
        shapes=[]
        def outline(box,color,width):
            x0,x1=box[0]; y0,y1=box[1]
            shapes.append(path_shape([project(editor.parent(),*p) for p in ((x0,y0),(x1,y0),(x1,y1),(x0,y1))],
                color,width/editor.view_scale,closed=True))
        if len(items)>1:
            interaction=getattr(editor,"interaction",None)
            if interaction is not None and interaction.group_bounds is not None:
                dx=interaction.group_current.x-interaction.group_bounds.x
                dy=interaction.group_current.y-interaction.group_bounds.y
                for box in interaction.group_boxes:
                    outline(((box[0][0]+dx,box[0][1]+dx),(box[1][0]+dy,box[1][1]+dy)),"#93C5FD",1)
                area=interaction.group_current
            else:
                for item in items: outline(bounds(item),"#93C5FD",1)
                area=aggregate(items)
            outline(bounds(area),"#155EEF",2)
        if self.box is not None:
            ax,bx=sorted((self.box[0],self.box_end[0])); ay,by=sorted((self.box[1],self.box_end[1]))
            outline(((ax,bx),(ay,by)),"#155EEF",1.5)
        return shapes

    def group(self,ungroup=False):
        if self.locked(): return
        editor=self.editor
        if editor.interaction is not None:editor.pointer_up()
        items=self.items()
        if not items or (not ungroup and len(items)<2): return
        ids=related(editor.items(),{i.id for i in items})
        anchor=editor.selected
        token=None if ungroup else uuid.uuid4().hex
        def apply():
            editor.document.floors[editor.floor]=[replace(i,group_id=token) if i.id in ids else i for i in editor.items()]
            self.select({anchor} if ungroup and anchor else ids,False)
        editor.status.value="Manual group removed; attachments preserved. Objects are individually selectable." if ungroup else "Manual group created."
        editor.modify(apply)

    def copy(self):
        editor=self.editor
        roots=self.items()
        if not roots: return
        building_ids={i.id for i in roots if i.kind=="building"}
        floors={k:tuple(v) for k,v in editor.document.floors.items() if k.split(":",1)[0] in building_ids}
        self.clipboard=(tuple(roots),floors,editor.parent() is not None)
        editor.status.value=f"Copied {len(roots)} selected objects and their building layers."
        editor.refresh()

    def paste(self,duplicate=False):
        if self.locked(): return
        editor=self.editor
        if not self.clipboard: return
        if getattr(editor,"building_session",False) and editor.floor==CAMPUS: return
        roots,floors,on_floor=self.clipboard
        if (editor.parent() is not None)!=on_floor:
            editor.status.value="Paste floor components onto a building floor, or buildings onto Campus."
            editor.refresh(); return
        roots,floors=clone_bundle(roots,floors)
        if on_floor:
            source=int(editor.floor.split()[-1]) if ":Floor " in editor.floor else None
            if any(i.kind=="floor_activator" for i in roots) and source is None:
                editor.status.value="Paste Floor Activators onto a numbered building floor.";editor.refresh();return
            valid_stairs={i.id for i in [*editor.items(),*roots] if i.kind in {"stairs","double_stairs"}}
            adjusted=[]
            for item in roots:
                if item.kind=="floor_activator":
                    target=source+item.activator_to-item.activator_from
                    if not 1<=target<=editor.parent().floor_count:
                        editor.status.value="Pasted activator would lead to a missing floor. Add that floor first.";editor.refresh();return
                    linked=item.activator_stair is None or item.activator_stair in valid_stairs
                    item=replace(item,activator_from=source,activator_to=target,
                        activator_stair=item.activator_stair if linked else None,activator_enabled=item.activator_enabled and linked)
                adjusted.append(item)
            roots=adjusted
        copied=[]
        used={b.text for b in editor.document.buildings()}
        for item in roots:
            label=item.text
            if item.kind=="building":
                base=re.sub(r" \(copy(?: \d+)?\)$","",label)
                n=1; label=f"{base} (copy)"
                while label in used:
                    n+=1; label=f"{base} (copy {n})"
                used.add(label)
            copied.append(replace(item,x=item.x+24,y=item.y+24,text=label))
        roots=copied
        def add():
            editor.items().extend(roots)
            editor.document.floors.update(floors)
            self.select({i.id for i in roots},False)
        editor.modify(add)

    def duplicate(self):
        self.copy()
        self.paste(True)

    def delete(self):
        if self.locked(): return
        editor=self.editor
        ids={i.id for i in self.items()}
        if not ids: return
        def remove():
            kept=[]
            for item in editor.items():
                if item.id in ids:continue
                changes={}
                if item.parent_id in ids:changes["parent_id"]=None
                if item.activator_stair in ids:changes.update(activator_stair=None,activator_enabled=False)
                kept.append(replace(item,**changes) if changes else item)
            editor.document.floors[editor.floor]=kept
            for key in list(editor.document.floors):
                if key.split(":",1)[0] in ids: editor.document.floors.pop(key)
            self.select((),False)
        editor.modify(remove)

    def translate(self,dx,dy):
        if self.locked(): return
        editor=self.editor
        updates={i.id:replace(i,x=i.x+dx,y=i.y+dy) for i in self.items()}
        from drafting.models import validate_item
        for item in updates.values(): validate_item(item)
        editor.modify(lambda:editor.document.floors.__setitem__(editor.floor,
            [updates.get(i.id,i) for i in editor.items()]))
