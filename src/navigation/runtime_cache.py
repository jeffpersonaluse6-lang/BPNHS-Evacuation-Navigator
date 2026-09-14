"""Immutable geometry and broad-phase lookups compiled once per loaded map."""

from dataclasses import dataclass
import math
from spatial import BoundsIndex


def point_box(point,other=None):
    other=point if other is None else other
    return tuple((min(a,b),max(a,b)) for a,b in zip(point,other))


class RuntimeIndex:
    def __init__(self,items,boxes,cell_size=256):
        self.items=tuple(items)
        self.index=BoundsIndex(boxes,cell_size)

    def query(self,point,other=None,padding=0):
        return tuple(self.items[n] for n in self.index.query(point_box(point,other),(padding,padding)))


@dataclass(frozen=True)
class FloorTransform:
    """Avoid finding the scene's parent and rebuilding trig per physics substep."""
    parent: object
    sx: float
    sy: float
    cosine: float
    sine: float

    @classmethod
    def build(cls,parent):
        from .data import floor_scale
        sx,sy=floor_scale(parent);angle=math.radians(parent.rotation)
        return cls(parent,sx,sy,math.cos(angle),math.sin(angle))

    def project(self,x,y):
        p=self.parent
        x=(x-p.floor_origin_x)*self.sx;y=(y-p.floor_origin_y)*self.sy
        if p.mirrored:x=p.width-x
        return p.x+x*self.cosine-y*self.sine,p.y+x*self.sine+y*self.cosine

    def unproject(self,x,y):
        p=self.parent;dx,dy=x-p.x,y-p.y
        x=dx*self.cosine+dy*self.sine;y=-dx*self.sine+dy*self.cosine
        if p.mirrored:x=p.width-x
        return x/self.sx+p.floor_origin_x,y/self.sy+p.floor_origin_y


def polygon_distance(area,point):
    if area.blocks(*point,0):return 0.
    previous=area.points[-1];best=float("inf")
    for current in area.points:
        dx,dy=current[0]-previous[0],current[1]-previous[1]
        length2=dx*dx+dy*dy
        t=max(0,min(1,((point[0]-previous[0])*dx+(point[1]-previous[1])*dy)/length2)) if length2 else 0
        best=min(best,math.hypot(point[0]-previous[0]-t*dx,point[1]-previous[1]-t*dy))
        previous=current
    return best
