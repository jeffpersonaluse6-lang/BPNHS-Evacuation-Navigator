"""One world position with elevation-aware collision and continuous stair progress."""

from dataclasses import dataclass
import math
from map.scene import CAMPUS,scope_key
from .collision import barriers_for,project_barriers,barrier_bounds
from .data import floor_scale
from .activators import valid,progress


@dataclass
class FloorTravel:
    zone: object
    source: int
    target: int
    progress: float = 0


class WorldNavigator:
    def __init__(self,scene,state):
        self.scene,self.state=scene,state
        self.parents=tuple(scene.buildings())
        self.parent=None
        self.travel=None
        self.previous_point=None
        self.locked_zones=set()
        self.activators={}
        self.building_activators={}
        self.colliders={}
        for parent in self.parents:
            for floor in range(1,parent.floor_count+1):
                items=scene.floors.get(scope_key(parent,f"Floor {floor}"),[])
                self.activators[parent.id,floor]=tuple(i for i in items if valid(i,floor,parent.floor_count,items))
                scope=scope_key(parent,"Floor 1")
                barriers=project_barriers(barriers_for(items),
                    lambda x,y:self.scene.project(scope,x,y),floor_scale(parent))
                box=barrier_bounds(barriers)
                self.colliders[parent.id,floor]=(barriers,box)
            self.building_activators[parent.id]=tuple(z for (pid,_),zones in self.activators.items() if pid==parent.id for z in zones)
        self.campus_barriers=tuple(barriers_for(scene.floors[CAMPUS]))

    def zones(self,parent):
        campus=[(i,CAMPUS) for i in self.scene.floors[CAMPUS] if i.kind=="entry_zone" and i.parent_id==parent.id]
        floor=scope_key(parent,"Floor 1")
        return campus+[(i,floor) for i in self.scene.floors.get(floor,[]) if i.kind=="entry_zone"]

    def inside(self,parent,point):
        if parent.contains(*point,tolerance=0): return True
        return any(zone.contains(*self.scene.unproject(scope,*point),tolerance=0) for zone,scope in self.zones(parent))

    def distance(self,parent,point):
        if self.inside(parent,point): return 0
        zones=self.zones(parent)
        if not zones: zones=[(parent,CAMPUS)]
        distances=[]
        for zone,scope in zones:
            local=zone.world_to_local(*self.scene.unproject(scope,*point))
            closest=zone.local_to_world(max(0,min(zone.width,local[0])),max(0,min(zone.height,local[1])))
            closest=self.scene.project(scope,*closest)
            distances.append(math.hypot(point[0]-closest[0],point[1]-closest[1]))
        return min(distances)

    def roof_opacity(self,parent,point):
        if not parent.fade_when_obstructing: return 1
        if self.parent and self.parent.id==parent.id: return 0
        distance=self.distance(parent,point)
        return min(1,distance/parent.approach_distance) if parent.approach_distance else float(distance>0)

    def enter(self,parent):
        self.parent=parent
        self.travel=None
        self.previous_point=None
        self.locked_zones.clear()
        self.state.view="floor"  # Context label only; the map/viewer never changes.
        self.state.building_name=parent.opens or parent.id
        self.state.floor=1
        self.state.stair_armed=True

    def exit(self):
        self.parent=None
        self.travel=None
        self.previous_point=None
        self.locked_zones.clear()
        self.state.view="campus"
        self.state.building_name=None
        self.state.floor=1
        self.state.stair_armed=True

    def candidates(self):
        return self.activators.get((self.parent.id,self.state.floor),()) if self.parent else ()

    def starting_zone(self,local):
        for zone in self.candidates():
            if zone.id in self.locked_zones:continue
            p,lateral,raw=progress(zone,local)
            if not lateral or not -1e-7<=raw<=1:continue
            previous=progress(zone,self.previous_point)[2] if self.previous_point is not None else None
            # Entry from the source end only; spawning/side-entry halfway never changes floors.
            if previous is None and raw<=1e-7:return zone
            if previous is not None and previous<=1e-7 and raw>previous+1e-9:
                # Check where the movement segment crossed the source edge, including
                # small zones that a movement substep crosses by more than 15%.
                fraction=max(0,min(1,-previous/(raw-previous)))
                crossing=tuple(a+(b-a)*fraction for a,b in zip(self.previous_point,local))
                if progress(zone,crossing)[1]:return zone
        return None

    def lock_overlapping(self,local):
        self.locked_zones.update(z.id for z in self.building_activators[self.parent.id] if z.contains(*local,tolerance=3))

    def update(self,point):
        before=(self.state.building_name,self.state.floor)
        if self.parent is None:
            parent=next((p for p in reversed(self.parents) if self.inside(p,point)),None)
            if parent: self.enter(parent)
        if self.parent is None: return before!=(self.state.building_name,self.state.floor)
        local=self.scene.unproject(scope_key(self.parent,"Floor 1"),*point)
        all_zones=self.building_activators[self.parent.id]
        self.locked_zones.intersection_update(z.id for z in all_zones if z.contains(*local,tolerance=3))
        if self.travel:
            travel=self.travel
            p,lateral,raw=progress(travel.zone,local)
            if lateral:travel.progress=p
            if lateral and raw>=1-1e-7:
                self.state.floor=travel.target
                self.travel=None
                self.state.stair_armed=False
                self.lock_overlapping(local)
            elif raw<0 and lateral:
                self.state.floor=travel.source
                self.travel=None
                self.lock_overlapping(local)
        else:
            for candidate in self.candidates():
                p,lateral,raw=progress(candidate,local)
                if not lateral or not 1e-7<raw<1-1e-7:continue
                previous=progress(candidate,self.previous_point) if self.previous_point is not None else None
                if previous is None or (not previous[1] and previous[2]>0):
                    self.locked_zones.add(candidate.id)
            zone=self.starting_zone(local)
            if zone:self.travel=FloorTravel(zone,self.state.floor,zone.activator_to,progress(zone,local)[0])
        self.previous_point=local
        if self.state.floor==1 and self.travel is None and not self.inside(self.parent,point): self.exit()
        return before!=(self.state.building_name,self.state.floor)

    def floor_opacities(self,parent):
        result={n:0. for n in range(1,parent.floor_count+1)}
        if self.parent is None or self.parent.id!=parent.id:
            result[1]=1.
        elif self.travel:
            result[self.travel.source]=1-self.travel.progress
            result[self.travel.target]=self.travel.progress
        else: result[self.state.floor]=1.
        return result

    def allowed(self,point):
        floors={self.state.floor if self.parent else 1}
        if self.parent:
            local=self.scene.unproject(scope_key(self.parent,"Floor 1"),*point)
            if self.travel:
                p,lateral,raw=progress(self.travel.zone,local)
                # Remain in the authored stair corridor until one end is reached.
                if not lateral:return False
                floors=({self.travel.source} if raw<=0 else {self.travel.target} if raw>=1 else
                    {self.travel.source,self.travel.target})
            else:
                zone=self.starting_zone(local)
                if zone and progress(zone,local)[0]>0:floors.add(zone.activator_to)
        radius=self.state.collision_radius
        if 1 in floors and any(b.blocks(*point,radius) for b in self.campus_barriers): return False
        for floor in floors:
            parents=self.parents if floor==1 else [self.parent]
            for parent in parents:
                barriers,box=self.colliders.get((parent.id,floor if self.parent and parent.id==self.parent.id else 1),((),None))
                if not box: continue
                if any(point[a]<box[a][0]-radius or point[a]>box[a][1]+radius for a in (0,1)): continue
                if any(b.blocks(*point,radius) for b in barriers): return False
        return True

    def move(self,point,dx,dy):
        scales=[min(floor_scale(p)) for p in self.parents]
        step=max(.01,min(4,self.state.collision_radius/2,4*min(scales,default=1)))
        count=max(1,math.ceil(math.hypot(dx,dy)/step))
        x,y=point
        self.update(point)
        radius=self.state.collision_radius
        for _ in range(count):
            nx=max(radius,min(self.scene.width-radius,x+dx/count))
            ny=max(radius,min(self.scene.height-radius,y+dy/count))
            if self.allowed((nx,ny)): x,y=nx,ny
            else:
                if self.allowed((nx,y)): x=nx
                if self.allowed((x,ny)): y=ny
            self.update((x,y))
        return x,y
