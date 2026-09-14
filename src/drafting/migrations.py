"""One-way import of old map files. No legacy objects survive deserialization."""

from copy import deepcopy
import math


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
            if isinstance(items,list) for i in items):return raw,()
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
    return raw,tuple(notes)
