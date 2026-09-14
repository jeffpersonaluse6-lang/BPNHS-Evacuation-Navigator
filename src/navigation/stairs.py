"""Stair direction and travel geometry (local axes, not screen)."""

from dataclasses import dataclass

STAIR_KINDS={"stairs","double_stairs"}


def stair_sections(item):
    if item.kind=="stairs":
        return ((0,item.width,item.stair_direction,item.stair_to),)
    gap=min(3,item.width/8)
    return ((0,item.width/2-gap,item.stair_direction,item.stair_to),
            (item.width/2+gap,item.width,item.stair_right_direction,item.stair_right_to))


def connection(item,section,floor,count):
    if item.stair_from is not None and item.stair_from!=floor:return None
    if not (item.stair_enabled if section==0 else item.stair_right_enabled):return None
    _,_,direction,explicit=stair_sections(item)[section]
    target=explicit if explicit is not None else floor+(1 if direction=="up" else -1)
    if explicit is None and (target<1 or target>count):return None
    return target if 1<=target<=count and target!=floor and (direction=="up")== (target>floor) else None


@dataclass(frozen=True)
class StairSection:
    """Derived runtime flight, never a separately stored or editable object."""
    stair: object
    number: int
    source: int
    target: int

    @property
    def id(self):return f"{self.stair.id}:flight:{self.number}"

    @property
    def direction(self):return stair_sections(self.stair)[self.number][2]

    @property
    def landing(self):return min(24,self.stair.height/5) if self.stair.kind=="double_stairs" else 0

    @property
    def width(self):
        lo,hi,_,_=stair_sections(self.stair)[self.number]
        return hi-lo

    @property
    def height(self):return self.stair.height-self.landing

    def local_to_world(self,x,y):
        lo=stair_sections(self.stair)[self.number][0]
        return self.stair.local_to_world(x+lo,y+self.landing)

    def world_to_local(self,x,y):
        x,y=self.stair.world_to_local(x,y)
        lo=stair_sections(self.stair)[self.number][0]
        return x-lo,y-self.landing

    def contains(self,x,y,tolerance=0):
        x,y=self.world_to_local(x,y)
        return -tolerance<=x<=self.width+tolerance and -tolerance<=y<=self.height+tolerance


def transitions(item,floor,count):
    if item.kind not in STAIR_KINDS:return ()
    return tuple(StairSection(item,n,floor,target) for n in range(len(stair_sections(item)))
        if (target:=connection(item,n,floor,count)) is not None)


def section_progress(section,point):
    x,y=section.world_to_local(*point)
    raw=(section.height-y)/section.height if section.direction=="up" else y/section.height
    return max(0,min(1,raw)),-1e-7<=x<=section.width+1e-7,raw


def indicators(item):
    """Arrow endpoints and labels for each flight."""
    landing=min(24,item.height/5) if item.kind=="double_stairs" else 0
    result=[]
    for lo,hi,direction,_ in stair_sections(item):
        x=(lo+hi)/2
        start,end=(item.height*.8,landing+(item.height-landing)*.2)
        if direction=="down": start,end=end,start
        result.append(((x,start),(x,end),direction.upper()))
    return result
