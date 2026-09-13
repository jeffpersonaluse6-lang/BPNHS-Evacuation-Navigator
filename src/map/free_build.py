"""Free-building bounds and read-only alignment targets in the editor."""

from dataclasses import replace
from drafting.models import DraftItem,railing_profile
from navigation.data import floor_scale
from .scene import CAMPUS,scope_key


def item_corners(item,padded=True):
    padding=item.stroke/2 if padded else 0
    if padded and item.kind=="railing":padding=railing_profile(item.stroke)[3]
    if item.kind in {"line","wall","railing"}:
        return [item.local_to_world(x+dx,y+dy)
            for x,y in ((0,0),(item.width,item.height))
            for dx,dy in ((-padding,-padding),(padding,-padding),(padding,padding),(-padding,padding))]
    return [item.local_to_world(*p) for p in ((-padding,-padding),
        (item.width+padding,-padding),(item.width+padding,item.height+padding),(-padding,item.height+padding))]


def fit_building(parent,floors):
    """Fit the logical container without changing any child's native coordinates.

    Rebasing its floor origin preserves the previous affine transform, including
    rotation, mirroring, thickness and nonuniformly resized older buildings.
    Existing floor-image footprints remain unchanged to preserve their assets.
    """
    if parent.layer_style or parent.image_src: return parent
    points=[p for items in floors.values() for item in items if item.kind!="floor_activator" for p in item_corners(item)]
    if not points: raise ValueError("Place at least one building object before adding the building to the map.")
    left,top=min(p[0] for p in points),min(p[1] for p in points)
    width=max(1,max(p[0] for p in points)-left)
    height=max(1,max(p[1] for p in points)-top)
    sx,sy=floor_scale(parent)
    new_width,new_height=width*sx,height*sy
    x,y=parent.local_to_world((left-parent.floor_origin_x)*sx+(new_width if parent.mirrored else 0),
                             (top-parent.floor_origin_y)*sy)
    return replace(parent,x=x,y=y,width=new_width,height=new_height,
        floor_width=width,floor_height=height,floor_origin_x=left,floor_origin_y=top,free_build=True)


def map_alignment_targets(scene,current,scope):
    """Reference coordinates are proxies, never the actual editable map objects."""
    from .scene_renderer import project
    targets=[]
    destination=scene.parent_for_scope(scope)
    sx,sy=floor_scale(destination)
    def unproject(x,y):
        if destination is None:return x,y
        x,y=destination.world_to_local(x,y)
        return x/sx+destination.floor_origin_x,y/sy+destination.floor_origin_y
    layers=[(CAMPUS,[i for i in scene.floors[CAMPUS] if i.id!=current.id])]
    for parent in scene.buildings():
        if parent.id!=current.id:
            for layer in ("Floor 1","Roof"):
                key=scope_key(parent,layer)
                layers.append((key,scene.floors.get(key,[])))
    for source,items in layers:
        source_parent=scene.parent_for_scope(source)
        for item in items:
            if item.kind=="floor_activator":continue
            points=[unproject(*project(source_parent,*point)) for point in item_corners(item,padded=False)]
            left,top=min(p[0] for p in points),min(p[1] for p in points)
            targets.append(DraftItem("rectangle",left,top,max(1e-6,max(p[0] for p in points)-left),
                max(1e-6,max(p[1] for p in points)-top),id=f"reference:{item.id}",blocking=False))
    return targets
