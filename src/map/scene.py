"""One editable scene: campus objects and building-local floor objects."""

from dataclasses import replace
import json
from pathlib import PurePosixPath

from drafting.models import DraftDocument, DraftItem
from navigation.data import FLOOR_WIDTH,FLOOR_HEIGHT,building_for,floor_scale
from navigation.models import Building,Rect
from .layers import BUILDING_LAYER_STYLES

CAMPUS = "Campus"


def scope_key(parent,layer):
    return f"{parent.id}:{layer}"


def from_placement(b):
    count = len(BUILDING_LAYER_STYLES[b.layer_style].layers) if b.layer_style else 1
    return DraftItem("building",b.left,b.top,b.width,b.height,rotation=b.rotation,
        text=b.label,fill=b.color,color=b.text_color,image_src=b.image_src,
        layer_style=b.layer_style,opens=b.opens,subtitle=b.subtitle,floor_count=count,mirrored=b.mirrored)


def to_placement(item):
    from .placements import PlacedBuilding
    return PlacedBuilding(label=item.text,left=item.x,top=item.y,width=item.width,height=item.height,
        color=item.fill if item.fill!="none" else "#FFFFFF",text_color=item.color,
        subtitle=item.subtitle,opens=item.opens,image_src=item.image_src,
        layer_style=item.layer_style,rotation=item.rotation,mirrored=item.mirrored)


class MapScene(DraftDocument):
    def __init__(self,placements=()):
        super().__init__()
        self.name="BPNHS campus"
        self.width,self.height=3000,1200
        self.floors={CAMPUS:[from_placement(b) for b in placements]}

    def buildings(self):
        return [item for item in self.floors[CAMPUS] if item.kind=="building"]

    def parent_for_scope(self,scope):
        if scope==CAMPUS: return None
        return next((b for b in self.buildings() if scope.startswith(f"{b.id}:")),None)

    def parent_for_key(self,key):
        return next((b for b in self.buildings() if b.opens==key),None)

    def layers(self,parent):
        return [f"Floor {n}" for n in range(1,parent.floor_count+1)]+["Roof"]

    def dimensions(self,scope):
        parent=self.parent_for_scope(scope)
        return (self.width,self.height) if scope==CAMPUS or (parent and parent.free_build) else (FLOOR_WIDTH,FLOOR_HEIGHT)

    def project(self,scope,x,y):
        parent=self.parent_for_scope(scope)
        if parent is None: return x,y
        sx,sy=floor_scale(parent)
        return parent.local_to_world((x-parent.floor_origin_x)*sx,(y-parent.floor_origin_y)*sy)

    def unproject(self,scope,x,y):
        parent=self.parent_for_scope(scope)
        if parent is None: return x,y
        lx,ly=parent.world_to_local(x,y)
        sx,sy=floor_scale(parent)
        return lx/sx+parent.floor_origin_x,ly/sy+parent.floor_origin_y

    def navigation_building(self,key,parent=None):
        parent=parent or self.parent_for_key(key)
        if parent is None: return building_for(key)
        original=building_for(key)
        assets = ({i:source for i,(_,source) in enumerate(BUILDING_LAYER_STYLES[parent.layer_style].layers,1)}
                  if parent.layer_style else {i:parent.image_src or "" for i in range(1,parent.floor_count+1)})
        items=self.floors.get(scope_key(parent,"Floor 1"),[])
        stair=next((i for i in items if i.kind in {"stairs","double_stairs"}),None)
        area=Rect(stair.x,stair.y,stair.width,stair.height) if stair else (original.stair_area if original else Rect(0,0,0,0))
        flip=BUILDING_LAYER_STYLES[parent.layer_style].flip_vertical if parent.layer_style else False
        return Building(parent.text,area,assets,flip)

    def to_json(self):
        raw=json.loads(super().to_json())
        raw["format"]="bpnhs-map"
        return json.dumps(raw,indent=2)

    @classmethod
    def from_json(cls,data):
        if len(data)>10_000_000: raise ValueError("Map workspace is too large")
        raw=json.loads(data)
        if not isinstance(raw,dict) or raw.get("format")!="bpnhs-map":
            raise ValueError("Not a BPNHS map workspace")
        raw["format"]="bpnhs-draft"
        loaded=DraftDocument.from_json(json.dumps(raw),max_floors=None)
        if CAMPUS not in loaded.floors: raise ValueError("Missing campus layer")
        scene=cls()
        scene.name,scene.width,scene.height,scene.floors=loaded.snapshot()
        # No arbitrary floor-count limit: stored layers bound work to actual file data.
        # Legacy maps may omit empty layers for up to their old 12-floor limit.
        for building in scene.buildings():
            numbers={int(key.split()[-1]) for key in scene.floors
                if key.startswith(f"{building.id}:Floor ") and key.split()[-1].isdigit()}
            if building.free_build or building.floor_count>12:
                if (len(numbers)!=building.floor_count or not numbers or
                        min(numbers)!=1 or max(numbers)!=building.floor_count):
                    raise ValueError("Building floor count must match its stored floor layers")
        for scope,items in scene.floors.items():
            parent=scene.parent_for_scope(scope) if scope!=CAMPUS else None
            valid_ids={i.id for i in items}|({parent.id} if parent else set())
            parents={i.id:i.parent_id for i in items}
            if scope!=CAMPUS:
                parent=scene.parent_for_scope(scope)
                layer=scope.split(":",1)[-1]
                valid_floor=(layer.startswith("Floor ") and layer[6:].isdigit() and
                    layer==f"Floor {int(layer[6:])}" and parent and 1<=int(layer[6:])<=parent.floor_count)
                if parent is None or not (layer=="Roof" or valid_floor):
                    raise ValueError("Unknown building floor layer")
            for item in items:
                if item.kind=="floor_activator":
                    from navigation.activators import valid
                    if parent is None or not scope.split(":",1)[-1].startswith("Floor ") or not valid(item,int(scope.split()[-1]),parent.floor_count,items,configuration=True):
                        raise ValueError("Floor Activator must belong to its From Floor and connect valid floors/stairs in that building")
                if item.parent_id and item.parent_id not in valid_ids:
                    raise ValueError("Attachment parent must belong to the same floor / building")
                seen={item.id}; ancestor=item.parent_id
                while ancestor and ancestor in parents:
                    if ancestor in seen: raise ValueError("Attachment parent cycle")
                    seen.add(ancestor); ancestor=parents[ancestor]
                if parent and scope.split(":",1)[1].startswith("Floor ") and item.kind in {"stairs","double_stairs"}:
                    source=int(scope.split()[-1])
                    for direction,target in ((item.stair_direction,item.stair_to),(item.stair_right_direction,item.stair_right_to)):
                        if target is not None and (target>parent.floor_count or target==source or
                                (direction=="up")!=(target>source)):
                            raise ValueError("Stair destination must exist and agree with its up/down direction")
                if item.kind=="building" and scope!=CAMPUS: raise ValueError("Buildings belong on the campus layer")
                if item.layer_style is not None and item.layer_style not in BUILDING_LAYER_STYLES:
                    raise ValueError("Unknown floor-plan asset set")
                if item.layer_style and item.floor_count!=len(BUILDING_LAYER_STYLES[item.layer_style].layers):
                    raise ValueError("Floor count must match the existing image set")
                if item.image_src:
                    asset=PurePosixPath(item.image_src.replace("\\","/"))
                    if asset.is_absolute() or ".." in asset.parts or ":" in item.image_src:
                        raise ValueError("Image must be relative to the shared assets folder")
        return scene
