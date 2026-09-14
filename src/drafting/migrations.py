"""One-way import of old map files. No legacy objects survive deserialization."""

from copy import deepcopy
import math
import uuid


def corners(item):
    angle=math.radians(item.get("rotation",0));c,s=math.cos(angle),math.sin(angle)
    return tuple((item["x"]+x*c-y*s,item["y"]+x*s+y*c)
        for x,y in ((0,0),(item["width"],0),(item["width"],item["height"]),(0,item["height"])))


def overlap(a,b):
    a,b=corners(a),corners(b)
    for polygon in (a,b):
        previous=polygon[-1]
        for current in polygon:
            axis=previous[1]-current[1],current[0]-previous[0]
            pa=[x*axis[0]+y*axis[1] for x,y in a];pb=[x*axis[0]+y*axis[1] for x,y in b]
            if max(pa)<min(pb)-1e-7 or max(pb)<min(pa)-1e-7:return False
            previous=current
    return True


def local_x(stair,point):
    angle=math.radians(stair.get("rotation",0));dx,dy=point[0]-stair["x"],point[1]-stair["y"]
    x=dx*math.cos(angle)+dy*math.sin(angle)
    return stair["width"]-x if stair.get("mirrored",False) else x


def migrate_stair_data(raw):
    floors=raw.get("floors")
    if not isinstance(floors,dict):return raw,()
    if not any(isinstance(i,dict) and (i.get("kind")=="floor_activator" or
            any(k.startswith("activator_") for k in i)) for items in floors.values()
            if isinstance(items,list) for i in items):return normal_stairs_only(raw),()
    raw=deepcopy(raw);notes=[]
    for scope,items in raw["floors"].items():
        if not isinstance(items,list):continue
        stairs=[i for i in items if isinstance(i,dict) and i.get("kind") in {"stairs","double_stairs"}]
        number=int(scope.split()[-1]) if scope.split()[-1].isdigit() and "Floor " in scope else None
        assignments={}
        removed={i.get("id") for i in items if isinstance(i,dict) and i.get("kind")=="floor_activator"}
        for zone in items:
            if not isinstance(zone,dict) or zone.get("kind")!="floor_activator":continue
            source,target=zone.get("activator_from",1),zone.get("activator_to",2)
            direction=zone.get("stair_direction","up")
            if (type(source) is not int or type(target) is not int or source!=number or target<1
                    or source==target or direction not in {"up","down"} or (direction=="up")!=(target>source)):
                raise ValueError("Legacy stair connection has invalid floor/direction data")
            linked=zone.get("activator_stair")
            candidates=[s for s in stairs if s.get("id")==linked] if linked else [s for s in stairs if overlap(s,zone)]
            center=tuple(sum(p[a] for p in corners(zone))/4 for a in (0,1))
            if not candidates:
                notes.append(f"{scope}: discarded an old zone without an overlapping staircase; configure its stair connection.")
                continue
            stair=min(candidates,key=lambda s:math.dist(center,tuple(sum(p[a] for p in corners(s))/4 for a in (0,1))))
            section=int(local_x(stair,center)>stair["width"]/2) if stair["kind"]=="double_stairs" else 0
            key=stair["id"],section
            setting=(source,target,direction,zone.get("activator_enabled",True))
            if key in assignments and assignments[key]!=setting:
                raise ValueError(f"Conflicting legacy connections on {scope}, stair {stair['id']}, flight {section+1}; cannot migrate safely")
            assignments[key]=setting
            prefix="stair_" if section==0 else "stair_right_"
            stair.update({"stair_from":source,prefix+"to":target,prefix+"direction":direction,prefix+"enabled":setting[3]})
        kept=[]
        for item in items:
            if not isinstance(item,dict):kept.append(item);continue
            if item.get("kind")=="floor_activator":continue
            item={k:v for k,v in item.items() if not k.startswith("activator_")}
            if item.get("parent_id") in removed and item.get("parent_id") is not None:item["parent_id"]=None
            if item.get("kind") in {"stairs","double_stairs"} and number is not None:
                item.setdefault("stair_from",number)
            kept.append(item)
        raw["floors"][scope]=kept
    return normal_stairs_only(raw),tuple(notes)


def normal_stairs_only(raw):
    """One-way legacy conversion. The live model only stores normal stairs.

    Preserve each old flight as an independent Stair, plus ordinary landing and
    divider shapes. This is import compatibility, not a creation/runtime tool.
    """
    floors=raw.get("floors",{})
    if not any(isinstance(i,dict) and (i.get("kind")=="double_stairs" or
            any(k.startswith("stair_right_") for k in i)) for items in floors.values()
            if isinstance(items,list) for i in items):return raw
    raw=deepcopy(raw)
    for scope,items in raw["floors"].items():
        if not isinstance(items,list):continue
        converted=[]
        for original in items:
            if not isinstance(original,dict):converted.append(original);continue
            item={k:v for k,v in original.items() if not k.startswith("stair_right_")}
            if original.get("kind")!="double_stairs":converted.append(item);continue
            w,h=original["width"],original["height"]
            if not (type(w) in (int,float) and type(h) in (int,float) and math.isfinite(w) and math.isfinite(h) and w>0 and h>0):
                raise ValueError("Invalid legacy stair dimensions")
            landing=min(24,h/5);gap=min(3,w/8)
            def fragment(label,kind,lo,y,width,height,**settings):
                angle=math.radians(original.get("rotation",0))
                x=w-lo-width if original.get("mirrored",False) else lo
                identity=original["id"] if label=="left" else uuid.uuid5(uuid.NAMESPACE_URL,f"bpnhs-stair:{original['id']}:{label}").hex
                return {**item,"kind":kind,"id":identity,"x":original["x"]+x*math.cos(angle)-y*math.sin(angle),
                    "y":original["y"]+x*math.sin(angle)+y*math.cos(angle),"width":width,"height":height,**settings}
            physical=original.get("blocking",True) and original.get("collision_thickness") is not None
            converted.append(fragment("left","stairs",0,landing,w/2-gap,h-landing,blocking=False if physical else original.get("blocking",True)))
            converted.append(fragment("right","stairs",w/2+gap,landing,w/2-gap,h-landing,
                stair_direction=original.get("stair_right_direction","down"),stair_to=original.get("stair_right_to"),
                stair_enabled=original.get("stair_right_enabled",True),blocking=False if physical else original.get("blocking",True)))
            converted.append(fragment("landing","rectangle",0,0,w,landing,blocking=False,fill="#FFFFFF",collision_thickness=None))
            converted.append(fragment("divider","rectangle",w/2-gap,landing,2*gap,h-landing,blocking=False,fill="#FFFFFF",collision_thickness=None))
            if physical:
                for label,x,y,height in (("side-left",0,0,h),("side-right",w,0,h),("center",w/2,landing,h-landing)):
                    # A line has no local width, so mirroring its vector changes
                    # nothing. The transformed start preserves the old barrier.
                    converted.append(fragment(label,"wall",x,y,0,height,fill="none",blocking=True,stair_enabled=False))
        raw["floors"][scope]=converted
    return raw
