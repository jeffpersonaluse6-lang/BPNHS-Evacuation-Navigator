"""Shared circular structure outlines and tangent doorway arc cuts."""

import math
from dataclasses import dataclass,field
import uuid

CIRCLE_KINDS={"circle_wall","gazebo_roof"}
TAU=2*math.pi


@dataclass(frozen=True)
class CircleOpening:
    angle: float = 0
    width: float = 80
    id: str = field(default_factory=lambda:uuid.uuid4().hex)


def validate_openings(openings):
    if not isinstance(openings,tuple) or len(openings)>128:raise ValueError("Invalid circle openings")
    ids=set()
    for opening in openings:
        if not isinstance(opening,CircleOpening):raise ValueError("Invalid circle opening")
        if (type(opening.angle) not in (int,float) or not math.isfinite(opening.angle) or not 0<=opening.angle<360 or
                type(opening.width) not in (int,float) or not math.isfinite(opening.width) or not 0<opening.width<=100000):
            raise ValueError("Opening angle must be 0–359 degrees; width must be positive")
        if not isinstance(opening.id,str) or not opening.id or len(opening.id)>80 or opening.id in ids:
            raise ValueError("Invalid circle opening ID")
        ids.add(opening.id)


def load_openings(raw):
    if not isinstance(raw,(list,tuple)):raise ValueError("Invalid circle openings")
    if len(raw)>128:raise ValueError("Too many circle openings")
    if any(not isinstance(value,dict) for value in raw):raise ValueError("Invalid circle opening")
    result=tuple(CircleOpening(**value) for value in raw)
    validate_openings(result)
    return result


def ellipse_points(width,height,start=0,end=TAU,error=.025):
    radius=max(width,height)/2
    count=max(1,min(4096,math.ceil((end-start)/max(.001,2*math.acos(max(-1,1-error/radius))))))
    return tuple((width/2+width/2*math.cos(start+(end-start)*n/count),
        height/2+height/2*math.sin(start+(end-start)*n/count)) for n in range(count+1))


def solid_arcs(item,openings=()):
    """Cut walkable angular openings from the wall, not the enclosing square.

    Openings must be tangent and near the visible rim. Increasing collision
    thickness never widens which unrelated doors count as openings.
    """
    rx,ry=item.width/2,item.height/2;cuts=[]
    def cut(angle,half):
        center=angle%TAU
        for shift in (-TAU,0,TAU):
            lo,hi=max(0,center-half+shift),min(TAU,center+half+shift)
            if hi>lo:cuts.append((lo,hi))
    for opening in item.circle_openings:
        angle=math.radians(opening.angle)
        tangent=math.hypot(rx*math.sin(angle),ry*math.cos(angle))
        cut(angle,math.asin(min(1,opening.width/(2*tangent))))
    for opening in openings:
        if opening.parent_id is not None and opening.parent_id!=item.id:continue
        y=opening.height/2 if opening.kind=="opening" else opening.height
        a,b=(item.world_to_local(*opening.local_to_world(x,y)) for x in (0,opening.width))
        cx,cy=(a[0]+b[0])/2-rx,(a[1]+b[1])/2-ry
        angle=math.atan2(cy/ry,cx/rx)
        rim=(rx*math.cos(angle),ry*math.sin(angle))
        reach=opening.height/2 if opening.kind=="opening" else max(8,opening.stroke+6)/2
        if math.hypot(cx-rim[0],cy-rim[1])>max(.5,item.stroke/2)+reach+1e-7:continue
        dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
        tx,ty=-rx*math.sin(angle),ry*math.cos(angle);tangent=math.hypot(tx,ty)
        if not length or abs(dx*ty-dy*tx)/(length*tangent)>.2:continue
        half=math.asin(min(1,length/(2*tangent)))
        cut(angle,half)
    cursor=0;arcs=[]
    for lo,hi in sorted(cuts):
        if lo>cursor+1e-9:arcs.append((cursor,lo))
        cursor=max(cursor,hi)
    if cursor<TAU-1e-9:arcs.append((cursor,TAU))
    return tuple(arcs)


def diameter_values(item,values):
    """Circle properties keep a shared diameter; either size field can edit it."""
    if item.kind in CIRCLE_KINDS:
        diameter=values["width"] if values["width"]!=item.width else values["height"]
        values.update(width=diameter,height=diameter)
    return values


def wall_polygons(item,openings=(),radius=None):
    """Retained annular strips: few draw calls, including real doorway gaps."""
    radius=item.stroke/2 if radius is None else radius
    polygons=[]
    for start,end in solid_arcs(item,openings):
        outer=[item.local_to_world(x-radius,y-radius) for x,y in
            ellipse_points(item.width+2*radius,item.height+2*radius,start,end)]
        iw,ih=max(.001,item.width-2*radius),max(.001,item.height-2*radius)
        inner=[item.local_to_world(x+(item.width-iw)/2,y+(item.height-ih)/2) for x,y in ellipse_points(iw,ih,start,end)]
        polygons.append(tuple([*outer,*reversed(inner)]))
    return tuple(polygons)
