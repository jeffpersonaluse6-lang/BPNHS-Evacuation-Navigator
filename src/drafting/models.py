"""Floor-plan data model with undo, JSON save/load, and SVG export."""

from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
from html import escape
import json
import math
import uuid
from .roof import roof_seams,structure_roof_primitives,ROOF_KINDS
from .circular import ellipse_points,solid_arcs,CircleOpening,validate_openings,load_openings

GATE_KINDS = {"main_gate", "secondary_gate"}
KINDS = {"room", "rectangle", "floor", "ellipse", "wall", "line", "door", "double_door",
         "opening", "window", "stairs", "text", "dimension", "roof", "railing", "building", "entry_zone",
         "circle_wall","gazebo_roof","court_roof"} | GATE_KINDS


@dataclass(frozen=True)
class DraftItem:
    kind: str
    x: float
    y: float
    width: float
    height: float
    rotation: float = 0
    stroke: float = 2
    color: str = "#111111"
    fill: str = "none"
    text: str = "Room"
    font_size: float = 18
    steps: int = 12
    mirrored: bool = False
    blocking: bool = True
    image_src: str | None = None
    layer_style: str | None = None
    opens: str | None = None
    subtitle: str = ""
    floor_count: int = 1
    group_id: str | None = None
    parent_id: str | None = None
    stair_direction: str = "up"
    stair_to: int | None = None
    completed_floors: tuple = ()
    approach_distance: float = 80
    fade_when_obstructing: bool = True
    # Custom floor frame — free builds keep their original X/Y.
    floor_width: float | None = None
    floor_height: float | None = None
    floor_origin_x: float = 0
    floor_origin_y: float = 0
    free_build: bool = False
    stair_from: int | None = None
    stair_enabled: bool = True
    stair_speed_multiplier: float | None = None
    # Physical collision width; None uses legacy defaults.
    collision_thickness: float | None = None
    opacity: float = 1
    circle_openings: tuple[CircleOpening,...] = ()
    gate_open: bool = False
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def local_to_world(self, x, y):
        if self.mirrored:
            x = self.width - x
        angle = math.radians(self.rotation)
        return (self.x + x * math.cos(angle) - y * math.sin(angle),
                self.y + x * math.sin(angle) + y * math.cos(angle))

    def world_to_local(self, x, y):
        angle = math.radians(-self.rotation)
        dx, dy = x - self.x, y - self.y
        lx = dx * math.cos(angle) - dy * math.sin(angle)
        ly = dx * math.sin(angle) + dy * math.cos(angle)
        return (self.width - lx if self.mirrored else lx, ly)

    def contains(self, x, y, tolerance=8):
        x, y = self.world_to_local(x, y)
        if self.kind in {"circle_wall","gazebo_roof"}:
            rx,ry=self.width/2,self.height/2
            normalized=math.hypot((x-rx)/rx,(y-ry)/ry)
            reach=max(tolerance,self.stroke/2)/min(rx,ry)
            return abs(normalized-1)<=reach if self.kind=="circle_wall" else normalized<=1+reach
        if self.kind in {"wall", "line", "railing"}:
            length2 = self.width ** 2 + self.height ** 2
            t = max(0, min(1, (x * self.width + y * self.height) / length2)) if length2 else 0
            radius=railing_profile(self.stroke)[3] if self.kind=="railing" else self.stroke/2
            return math.hypot(x - t * self.width, y - t * self.height) <= max(tolerance,radius)
        return -tolerance <= x <= self.width + tolerance and -tolerance <= y <= self.height + tolerance


def railing_profile(stroke):
    """Rail spacing, strokes, and collision envelope."""
    gap=max(2,min(8,stroke/2))
    rails=max(2,stroke*.4)
    posts=max(2.5,stroke*.5)
    radius=max(1,stroke/2+2,gap+rails/2,gap+1+posts/2)
    return gap,rails,posts,radius


def primitives(item):
    """Local-space drawing shapes for canvas and SVG."""
    w, h = item.width, item.height
    result = []

    def line(points, color=None, stroke=None, fill="none", closed=False):
        result.append({"points": points, "color": color or item.color,
                       "stroke": item.stroke if stroke is None else stroke,
                       "fill": fill, "closed": closed})

    def box(x, y, bw, bh, fill="none", color=None, stroke=None):
        line([(x,y),(x+bw,y),(x+bw,y+bh),(x,y+bh)], color, stroke, fill, True)

    def text(x, y, value, size=None):
        result.append({"text": value, "position": (x,y), "size": size or item.font_size,
                       "color": item.color})

    def single_door(hinge, radius, mirror=False):
        sign = -1 if mirror else 1
        line([(hinge,h),(hinge+sign*radius,h)], "#FFFFFF", max(8,item.stroke+6))
        line([(hinge,h),(hinge,0)])
        arc = [(hinge + sign * radius * math.cos(t * math.pi / 128),
                h - h * math.sin(t * math.pi / 128)) for t in range(65)]
        line(arc)

    if item.kind in {"room", "rectangle", "floor", "entry_zone"}:
        box(0,0,w,h,item.fill)
    elif item.kind == "roof":
        box(0,0,w,h,item.fill)
        for seam in roof_seams(w,h):
            line(seam)
    elif item.kind in {"gazebo_roof","court_roof"}:
        result.extend(structure_roof_primitives(item))
    elif item.kind == "circle_wall":
        for start,end in solid_arcs(item):
            line(ellipse_points(w,h,start,end),closed=end-start>=2*math.pi-1e-9)
    elif item.kind == "ellipse":
        line([(w/2+w/2*math.cos(i*math.pi/32),h/2+h/2*math.sin(i*math.pi/32))
              for i in range(64)], fill=item.fill, closed=True)
    elif item.kind in {"wall", "line"}:
        line([(0,0),(w,h)])
    elif item.kind == "railing":
        length = math.hypot(w,h)
        nx,ny = (-h/length,w/length) if length else (0,1)
        gap,rail_width,post_width,_=railing_profile(item.stroke)
        for sign in (-1,1):
            line([(sign*nx*gap,sign*ny*gap),(w+sign*nx*gap,h+sign*ny*gap)],stroke=rail_width)
        count = max(1,min(300,int(length/24)))
        for i in range(count+1):
            x,y = w*i/count,h*i/count
            line([(x-nx*(gap+1),y-ny*(gap+1)),(x+nx*(gap+1),y+ny*(gap+1))],stroke=post_width)
    elif item.kind == "opening":
        box(0,0,w,h,"#FFFFFF","#FFFFFF",0)
    elif item.kind == "door":
        single_door(0,w)
    elif item.kind == "double_door":
        single_door(0,w/2)
        single_door(w,w/2,True)
    elif item.kind == "window":
        box(0,0,w,h,"#FFFFFF")
        line([(0,h/2),(w,h/2)])
    elif item.kind in GATE_KINDS:
        post=max(6,min(18,w*.07))
        box(0,0,post,h,item.color,item.color,0)
        box(w-post,0,post,h,item.color,item.color,0)
        y=h/2
        if item.kind=="main_gate":
            if item.gate_open:
                line([(post,y),(post+w*.28,max(0,y-h*.42))],stroke=max(3,item.stroke*.65))
                line([(w-post,y),(w-post-w*.28,max(0,y-h*.42))],stroke=max(3,item.stroke*.65))
            else:
                line([(post,y),(w/2,y)],stroke=max(3,item.stroke*.65))
                line([(w/2,y),(w-post,y)],stroke=max(3,item.stroke*.65))
        else:
            if item.gate_open:
                line([(post,y),(post+w*.55,max(0,y-h*.42))],stroke=max(3,item.stroke*.65))
            else:
                line([(post,y),(w-post,y)],stroke=max(3,item.stroke*.65))
    elif item.kind == "stairs":
        box(0,0,w,h,"#FFFFFF")
        for i in range(item.steps):
            depth = (1-i/max(1,item.steps-1)) if item.stair_direction=="up" else i/max(1,item.steps-1)
            shade = round(248-62*depth)
            color = f"#{shade:02x}{shade:02x}{shade:02x}"
            box(0,h*i/item.steps,w,h/item.steps,color,color,0)
        for i in range(1,item.steps):
            y = h*i/item.steps
            line([(0,y),(w,y)])
    elif item.kind == "text":
        text(0,0,item.text)
    elif item.kind == "dimension":
        y = h/2
        line([(0,y),(w,y)])
        line([(0,0),(0,h)])
        line([(w,0),(w,h)])
        line([(7,y-4),(0,y),(7,y+4)])
        line([(w-7,y-4),(w,y),(w-7,y+4)])
        text(max(0,w/2-35),0,f"{w:g} units",12)
    return result


def validate_item(item):
    if item.kind not in KINDS:
        raise ValueError("Unknown drawing object")
    validate_openings(item.circle_openings)
    if item.circle_openings and item.kind!="circle_wall":raise ValueError("Openings belong to Circle Walls")
    if type(item.opacity) not in (int,float) or not math.isfinite(item.opacity) or not 0<=item.opacity<=1:
        raise ValueError("Opacity must be between 0 and 1")
    for name in ("x","y","width","height","rotation","stroke","font_size"):
        value = getattr(item,name)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or abs(value)>100000:
            raise ValueError(f"Invalid {name}")
    if item.kind not in {"wall","line","railing"} and (item.width<=0 or item.height<=0):
        raise ValueError("Width and height must be positive")
    if not 0 <= item.stroke <= 50 or not 1 <= item.font_size <= 200:
        raise ValueError("Invalid stroke or text size")
    if type(item.steps) is not int or not 2 <= item.steps <= 60:
        raise ValueError("Stair count must be from 2 to 60")
    for color in (item.color,item.fill):
        if color != "none" and (not isinstance(color,str) or len(color)!=7 or color[0]!="#"
                                or any(c not in "0123456789abcdefABCDEF" for c in color[1:])):
            raise ValueError("Use a color like #111111 or none")
    if not isinstance(item.text,str) or len(item.text)>2000 or not isinstance(item.id,str):
        raise ValueError("Invalid text or object ID")
    if type(item.mirrored) is not bool:
        raise ValueError("Invalid mirror flag")
    if type(item.gate_open) is not bool:
        raise ValueError("Gate open state must be a boolean")
    if type(item.blocking) is not bool or type(item.floor_count) is not int or item.floor_count < 1:
        raise ValueError("Invalid collision flag or floor count")
    if item.collision_thickness is not None and (isinstance(item.collision_thickness,bool) or
            not isinstance(item.collision_thickness,(int,float)) or not math.isfinite(item.collision_thickness) or
            not 0<item.collision_thickness<=200):
        raise ValueError("Collision thickness must be greater than 0 and at most 200")
    for value in (item.image_src,item.layer_style,item.opens):
        if value is not None and (not isinstance(value,str) or len(value)>500):
            raise ValueError("Invalid building metadata")
    for value in (item.group_id,item.parent_id):
        if value is not None and (not isinstance(value,str) or not value or len(value)>80):
            raise ValueError("Invalid structure relationship")
    if item.stair_from is not None and (type(item.stair_from) is not int or item.stair_from<1):
        raise ValueError("Stair From Floor must be a positive floor number")
    if type(item.stair_enabled) is not bool:
        raise ValueError("Stair transition enabled must be a boolean")
    if item.stair_speed_multiplier is not None and (type(item.stair_speed_multiplier) not in (int,float)
            or not math.isfinite(item.stair_speed_multiplier) or not .25<=item.stair_speed_multiplier<=1):
        raise ValueError("Stair speed multiplier must be between 0.25 and 1")
    if item.stair_direction not in {"up","down"}:
        raise ValueError("Stair direction must be up or down")
    for target in (item.stair_to,):
        if target is not None and (type(target) is not int or target<1):
            raise ValueError("Stair destination must be a positive floor number")
    if (not isinstance(item.completed_floors,(tuple,list)) or
            any(type(n) is not int or not 1<=n<=item.floor_count for n in item.completed_floors)):
        raise ValueError("Invalid completed floor list")
    if (type(item.approach_distance) not in (int,float) or not math.isfinite(item.approach_distance)
            or not 0<=item.approach_distance<=1000 or type(item.fade_when_obstructing) is not bool):
        raise ValueError("Invalid building visibility settings")
    if not isinstance(item.subtitle,str) or len(item.subtitle)>2000:
        raise ValueError("Invalid building subtitle")
    if type(item.free_build) is not bool:
        raise ValueError("Invalid free-build flag")
    if (item.floor_width is None)!=(item.floor_height is None):
        raise ValueError("Both floor frame dimensions are required")
    for value in (item.floor_width,item.floor_height):
        if value is not None and (type(value) not in (int,float) or not math.isfinite(value) or not 0<value<=100000):
            raise ValueError("Invalid floor frame size")
    for value in (item.floor_origin_x,item.floor_origin_y):
        if type(value) not in (int,float) or not math.isfinite(value) or abs(value)>100000:
            raise ValueError("Invalid floor frame origin")
    if item.free_build and item.floor_width is None:
        raise ValueError("Free builds require a floor coordinate frame")


class DraftDocument:
    def __init__(self):
        self.name = "Untitled building"
        self.width, self.height = 1600, 1000
        self.floors = {f"Floor {i}":[] for i in range(1,5)}
        self.undo_stack, self.redo_stack = [], []
        self.dirty = False

    def snapshot(self):
        return deepcopy((self.name,self.width,self.height,self.floors))

    def remember(self, previous):
        # Don't re-copy unchanged objects — it's slow and the snapshot is already isolated.
        if previous != (self.name,self.width,self.height,self.floors):
            self.undo_stack.append(previous)
            self.undo_stack = self.undo_stack[-100:]
            self.redo_stack.clear()
            self.dirty = True

    def restore(self, snapshot):
        self.name,self.width,self.height,self.floors = deepcopy(snapshot)
        self.dirty = True

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append(self.snapshot())
            self.restore(self.undo_stack.pop())

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(self.snapshot())
            self.restore(self.redo_stack.pop())

    def hit_test(self,floor,x,y):
        return next((item for item in reversed(self.floors[floor]) if item.contains(x,y)),None)

    def to_json(self):
        return json.dumps({"format":"bpnhs-draft","version":1,"name":self.name,
                           "width":self.width,"height":self.height,
                           "floors":{k:[asdict(item) for item in v] for k,v in self.floors.items()}},indent=2)

    @classmethod
    def from_json(cls,data,max_floors=20):
        if len(data)>10_000_000:
            raise ValueError("Draft file is too large")
        raw=json.loads(data)
        if not isinstance(raw,dict) or raw.get("format")!="bpnhs-draft" or raw.get("version")!=1:
            raise ValueError("Not a supported BPNHS draft file")
        from .migrations import migrate_stair_data
        raw,notes=migrate_stair_data(raw)
        doc=cls()
        doc.migration_notes=notes
        for dimension in ("width","height"):
            value=raw.get(dimension)
            if type(value) not in (int,float) or not math.isfinite(value) or not 100<=value<=5000:
                raise ValueError("Invalid canvas size")
            setattr(doc,dimension,value)
        if not isinstance(raw.get("name"),str) or len(raw["name"])>200:
            raise ValueError("Invalid building name")
        doc.name=raw["name"]
        floors=raw.get("floors")
        if not isinstance(floors,dict) or not floors or (max_floors is not None and len(floors)>max_floors):
            raise ValueError("Invalid floor list")
        doc.floors={}
        ids=set()
        for name,items in floors.items():
            if not isinstance(name,str) or not name or len(name)>80 or not isinstance(items,list) or len(items)>3000:
                raise ValueError("Invalid floor contents")
            doc.floors[name]=[]
            for item in items:
                if not isinstance(item,dict):
                    raise ValueError("Invalid drawing object")
                completed=item.get("completed_floors",())
                if not isinstance(completed,(list,tuple)): raise ValueError("Invalid completed floor list")
                obj=DraftItem(**{**item,"completed_floors":tuple(completed),
                    "circle_openings":load_openings(item.get("circle_openings",()))})
                validate_item(obj)
                if obj.id in ids:
                    raise ValueError("Duplicate object IDs")
                ids.add(obj.id)
                doc.floors[name].append(obj)
        return doc

    def svg(self,floor):
        """SVG without grid or background; room fills kept."""
        result=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width:g}" height="{self.height:g}" viewBox="0 0 {self.width:g} {self.height:g}">']
        for item in self.floors[floor]:
            if item.kind in ROOF_KINDS and item.opacity!=1:result.append(f'<g opacity="{item.opacity:g}">')
            for primitive in primitives(item):
                if "text" in primitive:
                    x,y=item.local_to_world(*primitive["position"])
                    result.append(f'<text x="{x:g}" y="{y:g}" font-size="{primitive["size"]:g}" font-family="Arial" dominant-baseline="hanging" fill="{primitive["color"]}" transform="rotate({item.rotation:g} {x:g} {y:g})">{escape(primitive["text"])}</text>')
                else:
                    points=" ".join(f"{x:g},{y:g}" for x,y in (item.local_to_world(*point) for point in primitive["points"]))
                    tag="polygon" if primitive["closed"] else "polyline"
                    result.append(f'<{tag} points="{points}" stroke="{primitive["color"]}" stroke-width="{primitive["stroke"]:g}" fill="{primitive["fill"]}" stroke-linecap="butt" stroke-linejoin="miter"/>')
            if item.kind in ROOF_KINDS and item.opacity!=1:result.append('</g>')
        result.append("</svg>")
        return "\n".join(result)
