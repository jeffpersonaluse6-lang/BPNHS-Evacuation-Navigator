"""Single world position with collision and stair progress tracking."""

from dataclasses import dataclass
from enum import Enum
import math
from map.scene import CAMPUS,scope_key
from .collision import barriers_for,project_barriers,barrier_bounds,PolygonBarrier
from .data import floor_scale
from .stairs import STAIR_KINDS,transitions,section_progress as progress
from .runtime_cache import RuntimeIndex,FloorTransform,polygon_distance


class TransitionPhase(str,Enum):
    ON_FLOOR="ON_FLOOR"
    ENTERING_STAIRS="ENTERING_STAIRS"
    TRANSITIONING="TRANSITIONING"
    ARRIVED="ARRIVED"
    WAIT_FOR_EXIT="WAIT_FOR_EXIT"


@dataclass
class FloorTravel:
    section: object
    source: int
    target: int
    progress: float = 0


def footprints_overlap(first,second):
    """Exact overlap of rotated stair/zone rectangles, including shared edges."""
    if any(first.bounds[a][1]<second.bounds[a][0] or second.bounds[a][1]<first.bounds[a][0] for a in (0,1)):return False
    for polygon in (first,second):
        previous=polygon.points[-1]
        for current in polygon.points:
            axis=(previous[1]-current[1],current[0]-previous[0])
            a=[p[0]*axis[0]+p[1]*axis[1] for p in first.points]
            b=[p[0]*axis[0]+p[1]*axis[1] for p in second.points]
            if max(a)<min(b)-1e-7 or max(b)<min(a)-1e-7:return False
            previous=current
    return True


class WorldNavigator:
    def __init__(self,scene,state):
        self.scene,self.state=scene,state
        self.parents=tuple(scene.buildings())
        self.parent=None
        self.travel=None
        self.previous_point=None
        self.previous_world_point=None
        self.phase=TransitionPhase.ON_FLOOR
        self.exit_areas=()
        self.wait_floor=None
        self.locked_sections=set()
        self.area_cache={}
        self.stair_objects={}
        self.stair_indices={}
        self.connections={}
        self.colliders={}
        self.collision_indices={}
        self.section_indices={}
        self.sections_by_id={}
        self.transforms={p.id:FloorTransform.build(p) for p in self.parents}
        self.entry_zones={}
        self.entry_areas={}
        self.roof_areas={}
        parent_boxes=[];roof_boxes=[];ground_barriers=[]
        for parent in self.parents:
            transform=self.transforms[parent.id]
            scope=scope_key(parent,"Floor 1")
            zones=[(i,CAMPUS) for i in scene.floors[CAMPUS] if i.kind=="entry_zone" and i.parent_id==parent.id]
            zones += [(i,scope) for i in scene.floors.get(scope,[]) if i.kind=="entry_zone"]
            self.entry_zones[parent.id]=tuple(zones)
            footprint=PolygonBarrier(tuple(parent.local_to_world(x,y) for x,y in
                ((0,0),(parent.width,0),(parent.width,parent.height),(0,parent.height))))
            areas=tuple(PolygonBarrier(tuple((transform.project(*i.local_to_world(x,y)) if layer!=CAMPUS
                else i.local_to_world(x,y)) for x,y in ((0,0),(i.width,0),(i.width,i.height),(0,i.height)))) for i,layer in zones)
            self.entry_areas[parent.id]=(footprint,*areas)
            self.roof_areas[parent.id]=areas or (footprint,)
            bounds=barrier_bounds(self.entry_areas[parent.id]);parent_boxes.append(bounds)
            roof_boxes.append(tuple((a-parent.approach_distance,b+parent.approach_distance) for a,b in bounds))
            for floor in range(1,parent.floor_count+1):
                items=scene.floors.get(scope_key(parent,f"Floor {floor}"),[])
                self.stair_objects[parent.id,floor]=tuple(i for i in items if i.kind in STAIR_KINDS)
                stairs=self.stair_objects[parent.id,floor]
                self.stair_indices[parent.id,floor]=RuntimeIndex(stairs,[self.area(s,floor,parent).bounds for s in stairs])
                self.connections[parent.id,floor]=tuple(s for stair in stairs for s in transitions(stair,floor,parent.floor_count))
                zones=self.connections[parent.id,floor]
                self.sections_by_id.update({z.id:z for z in zones})
                self.section_indices[parent.id,floor]=RuntimeIndex(zones,
                    [self.area(z,floor,parent).bounds for z in zones])
                barriers=project_barriers(barriers_for(items),
                    transform.project,floor_scale(parent))
                box=barrier_bounds(barriers)
                self.colliders[parent.id,floor]=(barriers,box)
                self.collision_indices[parent.id,floor]=RuntimeIndex(barriers,[barrier_bounds((b,)) for b in barriers])
                if floor==1:ground_barriers.extend(barriers)
        self.campus_barriers=tuple(barriers_for(scene.floors[CAMPUS]))
        ground_barriers.extend(self.campus_barriers)
        self.ground_index=RuntimeIndex(ground_barriers,[barrier_bounds((b,)) for b in ground_barriers])
        self.parent_index=RuntimeIndex(self.parents,parent_boxes)
        self.roof_index=RuntimeIndex(self.parents,roof_boxes)
        self.physics_step=min(4,4*min((min(floor_scale(p)) for p in self.parents),default=1))

    def zones(self,parent):
        return self.entry_zones[parent.id]

    def inside(self,parent,point):
        return any(area.blocks(*point,1e-6) for area in self.entry_areas[parent.id])

    def distance(self,parent,point):
        if self.inside(parent,point): return 0
        return min(polygon_distance(area,point) for area in self.roof_areas[parent.id])

    def roof_opacity(self,parent,point):
        if not parent.fade_when_obstructing: return 1
        if self.parent and self.parent.id==parent.id: return 0
        distance=self.distance(parent,point)
        return min(1,distance/parent.approach_distance) if parent.approach_distance else float(distance>0)

    def enter(self,parent):
        self.parent=parent
        self.travel=None
        self.previous_point=None
        self.previous_world_point=None
        self.phase=TransitionPhase.ON_FLOOR
        self.exit_areas=();self.wait_floor=None
        self.locked_sections.clear()
        self.state.view="floor"  # Just a label — the map doesn't actually change.
        self.state.building_name=parent.opens or parent.id
        self.state.floor=1
        self.state.stair_armed=True

    def exit(self):
        self.parent=None
        self.travel=None
        self.previous_point=None
        self.previous_world_point=None
        self.phase=TransitionPhase.ON_FLOOR
        self.exit_areas=();self.wait_floor=None
        self.locked_sections.clear()
        self.state.view="campus"
        self.state.building_name=None
        self.state.floor=1
        self.state.stair_armed=True

    def candidates(self):
        if self.travel is not None:
            return (self.travel.section,) if self.travel.source==self.state.floor else ()
        return self.connections.get((self.parent.id,self.state.floor),()) if self.parent else ()

    def stair_armed(self,zone):
        return (self.parent is not None and self.travel is None
            and zone.source==self.state.floor and zone.id not in self.locked_sections
            and not self.exit_areas)

    def nearby_candidates(self,point,previous=None):
        if self.travel:return (self.travel.section,)
        index=self.section_indices.get((self.parent.id,self.state.floor)) if self.parent else None
        return index.query(point,previous,padding=1e-7) if index else ()

    def area(self,item,floor,parent=None):
        parent=parent or self.parent
        key=parent.id,floor,item.id
        if key not in self.area_cache:
            project=self.transforms[parent.id].project
            points=tuple(project(*item.local_to_world(x,y))
                for x,y in ((0,0),(item.width,0),(item.width,item.height),(0,item.height)))
            self.area_cache[key]=PolygonBarrier(points)
        return self.area_cache[key]

    def stair_areas(self,zone):
        return (self.area(zone.stair,zone.source),)

    def wait_for_stair_exit(self,completed):
        """Arrival locks stair transitions until one complete physical exit."""
        source_areas=self.stair_areas(completed.section)
        self.exit_areas=tuple(source_areas);self.wait_floor=self.state.floor
        self.phase=TransitionPhase.ARRIVED

    def rearm_after_exit(self,point):
        # Exit is spatial, not timed. The entire physical player circle must
        # clear the stair footprint plus a small anti-jitter margin.
        radius=self.state.collision_radius+3
        if not self.exit_areas:return False
        if self.wait_floor!=self.state.floor or not any(area.blocks(*point,radius) for area in self.exit_areas):
            self.exit_areas=();self.wait_floor=None
            self.phase=TransitionPhase.ON_FLOOR
            return True
        self.phase=TransitionPhase.WAIT_FOR_EXIT
        return False

    def starting_section(self,local):
        if self.travel is not None or self.exit_areas:return None
        point=self.transforms[self.parent.id].project(*local) if self.parent else local
        ENTRY_BAND=0.08
        for zone in self.nearby_candidates(point,self.previous_world_point):
            if not self.stair_armed(zone):continue
            p,lateral,raw=progress(zone,local)
            if raw < -ENTRY_BAND:continue
            if raw<1 and not lateral:continue
            previous=progress(zone,self.previous_point)[2] if self.previous_point is not None else None
            if previous is None and lateral and raw<=ENTRY_BAND:return zone
            if previous is not None and previous<=ENTRY_BAND and raw>previous+1e-9:
                fraction=max(0,min(1,-previous/(raw-previous)))
                crossing=tuple(a+(b-a)*fraction for a,b in zip(self.previous_point,local))
                if not progress(zone,crossing)[1]:continue
                if raw>1:
                    end_fraction=max(0,min(1,(1-previous)/(raw-previous)))
                    end=tuple(a+(b-a)*end_fraction for a,b in zip(self.previous_point,local))
                    if not progress(zone,end)[1]:continue
                return zone
        return None

    def lock_overlapping(self,local):
        point=self.transforms[self.parent.id].project(*local)
        for zone in self.nearby_candidates(point):
            if zone.contains(*local,tolerance=3):
                self.locked_sections.add(zone.id)
                break

    def update(self,point):
        before=(self.state.building_name,self.state.floor)
        if self.parent is None:
            parent=next((p for p in reversed(self.parent_index.query(point)) if self.inside(p,point)),None)
            if parent: self.enter(parent)
        if self.parent is None:
            self.previous_world_point=point
            return before!=(self.state.building_name,self.state.floor)
        local=self.transforms[self.parent.id].unproject(*point)
        if self.rearm_after_exit(point):
            # A zone crossed BEFORE clearing the stairs was still disarmed.
            # Never retroactively trigger it from this frame's swept segment.
            self.previous_point=local;self.previous_world_point=point
            self.lock_overlapping(local)
        self.locked_sections.intersection_update(key for key in tuple(self.locked_sections)
            if self.sections_by_id[key].contains(*local,tolerance=8))
        if self.travel:
            travel=self.travel
            p,lateral,raw=progress(travel.section,local)
            if lateral:travel.progress=p
            self.phase=TransitionPhase.TRANSITIONING
            if lateral and raw>=1-1e-7:
                self.finish_transition(travel,local)
            elif raw<0 and lateral:
                self.state.floor=travel.source
                self.travel=None
                self.lock_overlapping(local)
                self.phase=TransitionPhase.ON_FLOOR
        else:
            for candidate in (() if self.exit_areas else self.nearby_candidates(point,self.previous_world_point)):
                p,lateral,raw=progress(candidate,local)
                if not lateral or not 1e-7<raw<1-1e-7:continue
                previous=progress(candidate,self.previous_point) if self.previous_point is not None else None
                if previous is None or (not previous[1] and previous[2]>0):
                    self.locked_sections.add(candidate.id)
            zone=self.starting_section(local)
            if zone:
                self.travel=FloorTravel(zone,self.state.floor,zone.target,progress(zone,local)[0])
                self.phase=TransitionPhase.ENTERING_STAIRS
                # A swept path can cross both ends of a very thin zone in one
                # substep. Commit once, never silently miss that transition.
                if progress(zone,local)[2]>=1-1e-7:self.finish_transition(self.travel,local)
        self.previous_point=local
        self.previous_world_point=point
        self.state.stair_armed=self.travel is None and not self.exit_areas
        if self.state.floor==1 and self.travel is None and not self.inside(self.parent,point): self.exit()
        return before!=(self.state.building_name,self.state.floor)

    def finish_transition(self,travel,local):
        self.state.floor=travel.target;self.travel=None
        self.lock_overlapping(local)
        self.wait_for_stair_exit(travel)

    def active_floor_opacities(self):
        """Only changed floors; the renderer remembers and clears old layers."""
        if self.parent is None:return {}
        if self.travel:return {self.travel.source:1-self.travel.progress,self.travel.target:self.travel.progress}
        return {self.state.floor:1.}

    def visual_state(self):
        return (self.parent.id if self.parent else None,self.state.floor,
            (self.travel.section.id,self.travel.progress) if self.travel else None)

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
            local=self.transforms[self.parent.id].unproject(*point)
            if self.travel:
                p,lateral,raw=progress(self.travel.section,local)
                # Stay in the stair corridor until we reach the end.
                if not lateral:return False
                floors=({self.travel.source} if raw<=0 else {self.travel.target} if raw>=1 else
                    {self.travel.source,self.travel.target})
            else:
                zone=self.starting_section(local)
                if zone and progress(zone,local)[0]>0:floors.add(zone.target)
        radius=self.state.collision_radius
        if 1 in floors and any(b.blocks(*point,radius) for b in self.ground_index.query(point,padding=radius)):return False
        for floor in floors:
            if floor==1:continue
            parents=[self.parent]
            for parent in parents:
                barriers,box=self.colliders.get((parent.id,floor if self.parent and parent.id==self.parent.id else 1),((),None))
                if not box: continue
                if any(point[a]<box[a][0]-radius or point[a]>box[a][1]+radius for a in (0,1)): continue
                if any(b.blocks(*point,radius) for b in self.collision_indices[parent.id,floor].query(point,padding=radius)): return False
        return True

    def move(self,point,dx,dy):
        step=max(.01,min(self.state.collision_radius/2,self.physics_step))
        count=max(1,math.ceil(math.hypot(dx,dy)/step))
        x,y=point
        if self.previous_world_point!=point:self.update(point)
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

    def walking_speed(self,point):
        speed=self.state.player_speed
        if self.travel:
            multiplier=self.travel.section.stair.stair_speed_multiplier
            return speed*(self.state.stair_speed_multiplier if multiplier is None else multiplier)
        if self.parent:
            index=self.stair_indices.get((self.parent.id,self.state.floor))
            if index:
                stair=next((s for s in index.query(point) if self.area(s,self.state.floor).blocks(*point,1e-7)),None)
                if stair:
                    multiplier=stair.stair_speed_multiplier
                    return speed*(self.state.stair_speed_multiplier if multiplier is None else multiplier)
        return speed

    def walk(self,point,x,y,dt):
        """Consume time, not pixels, so stair speed also applies mid-frame."""
        if dt<=0 or not (x or y):return point
        length=math.hypot(x,y)
        if length>1:x/=length;y/=length
        if self.previous_world_point!=point:self.update(point)
        remaining=dt
        distance_step=max(.01,min(self.physics_step,self.state.collision_radius/2))
        while remaining>1e-9:
            speed=self.walking_speed(point)
            elapsed=min(remaining,distance_step/speed)
            point=self.move(point,x*speed*elapsed,y*speed*elapsed)
            remaining-=elapsed
        return point
