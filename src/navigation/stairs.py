"""Stair direction and travel geometry (local axes, not screen)."""

from dataclasses import dataclass

STAIR_KINDS={"stairs"}


def connection(item,section,floor,count):
    if item.stair_from is not None and item.stair_from!=floor:return None
    if item.kind != "stairs" or section!=0 or not item.stair_enabled:return None
    direction,explicit=item.stair_direction,item.stair_to
    target=explicit if explicit is not None else floor+(1 if direction=="up" else -1)
    if explicit is None and (target<1 or target>count):return None
    return target if 1<=target<=count and target!=floor and (direction=="up")== (target>floor) else None


@dataclass(frozen=True)
class StairSection:
    """Derived runtime flight, never a separately stored or editable object."""
    stair: object
    source: int
    target: int

    @property
    def id(self):return f"{self.stair.id}:stair"

    @property
    def direction(self):return self.stair.stair_direction

    @property
    def width(self):
        return self.stair.width

    @property
    def height(self):return self.stair.height

    def local_to_world(self,x,y):
        return self.stair.local_to_world(x,y)

    def world_to_local(self,x,y):
        return self.stair.world_to_local(x,y)

    def contains(self,x,y,tolerance=0):
        x,y=self.world_to_local(x,y)
        return -tolerance<=x<=self.width+tolerance and -tolerance<=y<=self.height+tolerance


def transitions(item,floor,count):
    if item.kind not in STAIR_KINDS:return ()
    target=connection(item,0,floor,count)
    return (StairSection(item,floor,target),) if target is not None else ()


def section_progress(section,point):
    x,y=section.world_to_local(*point)
    raw=(section.height-y)/section.height if section.direction=="up" else y/section.height
    return max(0,min(1,raw)),-1e-7<=x<=section.width+1e-7,raw


def indicators(item):
    """Arrow endpoints for the normal stair's walking direction."""
    x=item.width/2;start,end=item.height*.8,item.height*.2
    if item.stair_direction=="down":start,end=end,start
    return [((x,start),(x,end),item.stair_direction.upper())]
