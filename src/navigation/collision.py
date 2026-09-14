"""Wall/room collision with automatic doorway cuts."""

from dataclasses import dataclass,replace,field
from functools import lru_cache
import math
from spatial import BoundsIndex
from drafting.models import railing_profile,GATE_KINDS
from drafting.circular import ellipse_points,solid_arcs

OPENING_KINDS = {"door", "double_door", "opening"}
WALL_KINDS = {"wall", "room", "circle_wall"}
COLLISION_KINDS = WALL_KINDS | {"railing","stairs"} | GATE_KINDS


def collision_thickness(item):
    """Collision width — legacy objects use their stroke as-is."""
    if item.collision_thickness is not None:return item.collision_thickness
    if item.kind=="railing":return 2*railing_profile(item.stroke)[3]
    return max(1,item.stroke)


@dataclass(frozen=True)
class Barrier:
    start: tuple[float,float]
    end: tuple[float,float]
    radius: float
    flat: bool = False

    def blocks(self, x, y, player_radius):
        ax,ay = self.start
        dx,dy = self.end[0]-ax,self.end[1]-ay
        length2 = dx*dx+dy*dy
        if self.flat and length2:
            length = math.sqrt(length2)
            along = ((x-ax)*dx+(y-ay)*dy)/length
            across = abs((x-ax)*dy-(y-ay)*dx)/length
            if player_radius == 0:
                return 0 < along < length and across < self.radius
            # Test the circle against the actual rectangle, not a spanning box.
            return math.hypot(max(0,-along,along-length),max(0,across-self.radius)) < player_radius-1e-7
        t = max(0,min(1,((x-ax)*dx+(y-ay)*dy)/length2)) if length2 else 0
        return math.hypot(x-ax-t*dx,y-ay-t*dy) < self.radius+player_radius-1e-7


@dataclass(frozen=True)
class PolygonBarrier:
    """Transformed thick wall for circle-vs-polygon collision."""
    points: tuple
    bounds: tuple = field(init=False)

    def __post_init__(self):
        object.__setattr__(self,"bounds",tuple((min(p[a] for p in self.points),max(p[a] for p in self.points)) for a in (0,1)))

    def blocks(self,x,y,player_radius):
        if any(p<self.bounds[a][0]-player_radius or p>self.bounds[a][1]+player_radius for a,p in enumerate((x,y))):return False
        inside=False
        previous=self.points[-1]
        for current in self.points:
            ax,ay=previous;bx,by=current
            if (ay>y)!=(by>y) and x<(bx-ax)*(y-ay)/(by-ay)+ax:inside=not inside
            dx,dy=bx-ax,by-ay;length2=dx*dx+dy*dy
            t=max(0,min(1,((x-ax)*dx+(y-ay)*dy)/length2)) if length2 else 0
            if (x-ax-t*dx)**2+(y-ay-t*dy)**2<(player_radius-1e-7)**2:return True
            previous=current
        return inside


def project_barriers(barriers,project,scales):
    """Precompute collision geometry once, not every frame.

    Uniform scale keeps exact capsules. Non-uniform walls become polygons.
    """
    sx,sy=scales
    result=[]
    for barrier in barriers:
        if abs(sx-sy)<1e-9:
            result.append(Barrier(project(*barrier.start),project(*barrier.end),
                barrier.radius*abs(sx),barrier.flat));continue
        ax,ay=barrier.start;bx,by=barrier.end
        angle=math.atan2(by-ay,bx-ax);r=barrier.radius
        if barrier.flat:
            nx,ny=-math.sin(angle)*r,math.cos(angle)*r
            points=((ax+nx,ay+ny),(bx+nx,by+ny),(bx-nx,by-ny),(ax-nx,ay-ny))
        else:
            points=tuple((px+r*math.cos(a),py+r*math.sin(a))
                for px,py,start in ((ax,ay,angle+math.pi/2),(bx,by,angle-math.pi/2))
                for a in (start+n*math.pi/96 for n in range(97)))
        result.append(PolygonBarrier(tuple(project(*p) for p in points)))
    return tuple(result)


def barrier_bounds(barriers):
    if not barriers:return None
    boxes=[b.bounds
        if isinstance(b,PolygonBarrier) else
        tuple((min(b.start[a],b.end[a])-b.radius,max(b.start[a],b.end[a])+b.radius) for a in (0,1))
        for b in barriers]
    return tuple((min(box[a][0] for box in boxes),max(box[a][1] for box in boxes)) for a in (0,1))


def openings_for(items):
    """Doors and openings cut walls; windows and stairs don't."""
    return tuple(item for item in items if item.kind in OPENING_KINDS)


def wall_edges(item,*,collision=False):
    """Wall boundary segments — a room's interior is never solid."""
    if item.kind not in WALL_KINDS:
        return ()
    radius = collision_thickness(item)/2 if collision else max(.5,item.stroke/2)
    if item.kind=="circle_wall":
        points=[item.local_to_world(*p) for p in ellipse_points(item.width,item.height)]
        return tuple((a,b,radius) for a,b in zip(points,points[1:]))
    if item.kind == "wall":
        local = [((0,0),(item.width,item.height))]
    else:
        w,h = item.width,item.height
        # Miter corners extend by half the stroke, not a bounding box.
        local = [((-radius,0),(w+radius,0)),((w,-radius),(w,h+radius)),
                 ((w+radius,h),(-radius,h)),((0,h+radius),(0,-radius))]
    return tuple((item.local_to_world(*a),item.local_to_world(*b),radius) for a,b in local)


def opening_axis(item):
    """The door's baseline — not its leaf or swing arc."""
    y = item.height/2 if item.kind == "opening" else item.height
    reach = item.height/2 if item.kind == "opening" else max(8,item.stroke+6)/2
    return item.local_to_world(0,y),item.local_to_world(item.width,y),reach


class OpeningIndex:
    """Index of nearby door baselines for efficient wall-cut lookups."""
    def __init__(self,openings):
        self.openings=tuple(openings)
        boxes=[]
        for opening in self.openings:
            start,end,reach=opening_axis(opening)
            boxes.append(tuple((min(start[a],end[a])-reach,max(start[a],end[a])+reach) for a in (0,1)))
        self.index=BoundsIndex(boxes)

    def for_wall(self,item):
        if item.kind not in WALL_KINDS or not self.openings: return ()
        if item.kind=="circle_wall":
            points=[item.local_to_world(*p) for p in ellipse_points(item.width,item.height)]
            radius=max(.5,item.stroke/2)
            box=tuple((min(p[a] for p in points)-radius,max(p[a] for p in points)+radius) for a in (0,1))
            return tuple(self.openings[n] for n in self.index.query(box))
        candidates=set()
        for start,end,radius in wall_edges(item):
            box=tuple((min(start[a],end[a])-radius-1e-7,max(start[a],end[a])+radius+1e-7) for a in (0,1))
            candidates.update(self.index.query(box))
        return tuple(self.openings[n] for n in sorted(candidates))


def solid_sections(start,end,radius,openings):
    dx,dy = end[0]-start[0],end[1]-start[1]
    length = math.hypot(dx,dy)
    if length < 1e-9:
        return ()
    ux,uy = dx/length,dy/length
    cuts = []
    for opening in openings:
        a,b,reach = opening_axis(opening)
        ox,oy = b[0]-a[0],b[1]-a[1]
        opening_length = math.hypot(ox,oy)
        if not opening_length or abs(ux*oy-uy*ox)/opening_length > 1e-5:
            continue
        distances = [abs((p[0]-start[0])*uy-(p[1]-start[1])*ux) for p in (a,b)]
        if max(distances) > radius+reach+1e-7:
            continue
        positions = [(p[0]-start[0])*ux+(p[1]-start[1])*uy for p in (a,b)]
        lo,hi = max(0,min(positions)),min(length,max(positions))
        if hi-lo > 1e-7:
            cuts.append((lo,hi))
    cursor = 0
    sections = []
    for lo,hi in sorted(cuts):
        if lo > cursor+1e-7:
            sections.append((cursor,lo))
        cursor = max(cursor,hi)
    if cursor < length-1e-7:
        sections.append((cursor,length))
    return tuple(Barrier((start[0]+a*ux,start[1]+a*uy),
                         (start[0]+b*ux,start[1]+b*uy),radius,flat=True) for a,b in sections)


@lru_cache(maxsize=4096)
def wall_sections(item,openings=()):
    """Visible wall sections with doorway gaps cut out."""
    if item.kind=="circle_wall":return circular_wall_sections(item,openings,max(.5,item.stroke/2))
    return tuple(section for a,b,r in wall_edges(item) for section in solid_sections(a,b,r,openings))


@lru_cache(maxsize=4096)
def collision_wall_sections(item,openings=()):
    # Match doors to the visible wall so widening collision doesn't
    # accidentally cut a doorway on a parallel wall nearby.
    visual_radius=max(.5,item.stroke/2)
    radius=collision_thickness(item)/2
    if item.kind=="circle_wall":return circular_wall_sections(item,openings,radius)
    return tuple(replace(section,radius=radius) for a,b,_ in wall_edges(item,collision=True)
        for section in solid_sections(a,b,visual_radius,openings))


def circular_wall_sections(item,openings,radius):
    sections=[]
    for start,end in solid_arcs(item,openings):
        points=[item.local_to_world(*p) for p in ellipse_points(item.width,item.height,start,end)]
        sections.extend(Barrier(a,b,radius,flat=True) for a,b in zip(points,points[1:]))
    return tuple(sections)


@lru_cache(maxsize=4096)
def barriers_for_item(item,openings=()):
    if item.kind in GATE_KINDS:
        radius=collision_thickness(item)/2
        barriers=[
            Barrier(item.local_to_world(0,0),item.local_to_world(0,item.height),radius,flat=True),
            Barrier(item.local_to_world(item.width,0),item.local_to_world(item.width,item.height),radius,flat=True),
        ]
        if not item.gate_open:
            barriers.append(Barrier(item.local_to_world(0,item.height/2),
                                    item.local_to_world(item.width,item.height/2),
                                    radius,flat=True))
        return tuple(barriers)
    if not item.blocking:
        return ()
    if item.kind in WALL_KINDS:
        return collision_wall_sections(item,openings)
    if item.kind == "railing":
        return (Barrier(item.local_to_world(0,0),item.local_to_world(item.width,item.height),
                        collision_thickness(item)/2),)
    if item.kind == "stairs" and item.collision_thickness is not None:
        # Stairs stay walkable on the treads. Optional side barriers keep
        # the player in the corridor without blocking the ends.
        lines=[((0,0),(0,item.height)),((item.width,0),(item.width,item.height))]
        return tuple(Barrier(item.local_to_world(*a),item.local_to_world(*b),collision_thickness(item)/2,flat=True)
            for a,b in lines)
    return ()


@lru_cache(maxsize=64)
def _compiled_barriers(items):
    openings = OpeningIndex(openings_for(items))
    return tuple(b for item in items for b in barriers_for_item(item,openings.for_wall(item)))


def barriers_for(items):
    # Cached by item tuple — invalidates after move/resize/delete/undo.
    return list(_compiled_barriers(tuple(items)))


def snap_opening_to_wall(item,items,point,tolerance=20):
    """Snap a new opening to the nearest wall when clicking."""
    candidates = [];circular=[]
    for wall in items:
        if wall.kind=="circle_wall":
            lx,ly=wall.world_to_local(*point);rx,ry=wall.width/2,wall.height/2
            angle=math.atan2((ly-ry)/ry,(lx-rx)/rx)
            rim=wall.local_to_world(rx+rx*math.cos(angle),ry+ry*math.sin(angle))
            next_point=wall.local_to_world(rx+rx*math.cos(angle+.0001),ry+ry*math.sin(angle+.0001))
            distance=math.dist(rim,point)
            if distance<=tolerance+wall.stroke/2:
                width=min(item.width,min(wall.width,wall.height)*.8)
                aligned=replace(item,width=width,rotation=math.degrees(math.atan2(next_point[1]-rim[1],next_point[0]-rim[0])),x=0,y=0)
                baseline=aligned.local_to_world(width/2,item.height/2 if item.kind=="opening" else item.height)
                circular.append((distance,replace(aligned,x=rim[0]-baseline[0],y=rim[1]-baseline[1])))
            continue
        for a,b,radius in wall_edges(wall):
            dx,dy = b[0]-a[0],b[1]-a[1]
            length = math.hypot(dx,dy)
            if length < 4:
                continue
            ux,uy = dx/length,dy/length
            along = max(0,min(length,(point[0]-a[0])*ux+(point[1]-a[1])*uy))
            px,py = a[0]+along*ux,a[1]+along*uy
            distance = math.hypot(point[0]-px,point[1]-py)
            if distance <= tolerance+radius:
                candidates.append((distance,a,ux,uy,length,along))
    if circular and (not candidates or min(circular,key=lambda c:c[0])[0]<min(candidates,key=lambda c:c[0])[0]):
        return min(circular,key=lambda c:c[0])[1]
    if not candidates:
        return item
    _,a,ux,uy,length,along = min(candidates,key=lambda c:c[0])
    width = min(item.width,length)
    along = max(width/2,min(length-width/2,along))
    aligned = replace(item,width=width,rotation=math.degrees(math.atan2(uy,ux)),x=0,y=0)
    baseline = aligned.local_to_world(width/2,item.height/2 if item.kind == "opening" else item.height)
    return replace(aligned,x=a[0]+along*ux-baseline[0],y=a[1]+along*uy-baseline[1])


def move_with_collisions(x,y,dx,dy,radius,barriers,width,height):
    """Move in substeps to avoid tunnelling; slide along blocked diagonals."""
    steps = max(1,math.ceil(math.hypot(dx,dy)/max(1,min(4,radius/2))))
    sx,sy = dx/steps,dy/steps

    def allowed(px,py):
        nearby=barriers.query((px,py),padding=radius) if hasattr(barriers,"query") else barriers
        return not any(barrier.blocks(px,py,radius) for barrier in nearby)

    def clamp(value,limit):
        return max(radius,min(limit-radius,value))

    for _ in range(steps):
        nx,ny = clamp(x+sx,width),clamp(y+sy,height)
        if allowed(nx,ny):
            x,y = nx,ny
        else:
            if allowed(nx,y): x = nx
            if allowed(x,ny): y = ny
    return x,y


def find_free_position(x,y,radius,barriers,width,height):
    """Find a free spawn point nearby, or None if everything is blocked."""
    x,y=max(radius,min(width-radius,x)),max(radius,min(height-radius,y))
    if not any(b.blocks(x,y,radius) for b in barriers): return x,y
    step=max(8,radius)
    for ring in range(1,math.ceil(max(width,height)/step)+2):
        candidates=[]
        for n in range(-ring,ring+1):
            candidates.extend([(x+n*step,y-ring*step),(x+n*step,y+ring*step),
                               (x-ring*step,y+n*step),(x+ring*step,y+n*step)])
        for px,py in sorted(candidates,key=lambda p:(p[0]-x)**2+(p[1]-y)**2):
            if radius<=px<=width-radius and radius<=py<=height-radius and not any(b.blocks(px,py,radius) for b in barriers):
                return px,py
    return None
