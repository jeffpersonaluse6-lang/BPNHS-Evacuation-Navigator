"""Raster building layers and editable vectors in one coordinate system."""

from dataclasses import replace
from functools import lru_cache
import math
import flet as ft
import flet.canvas as cv
from drafting.canvas import grid_shapes
from drafting.handles import handles,frame
from drafting.models import primitives
from drafting.circular import wall_polygons
from drafting.roof import ROOF_KINDS
from navigation.collision import barriers_for_item,wall_sections,openings_for,WALL_KINDS,OpeningIndex
from navigation.data import floor_scale
from .scene import CAMPUS,to_placement,scope_key


def project(parent,x,y):
    if parent is None: return x,y
    sx,sy=floor_scale(parent)
    return parent.local_to_world((x-parent.floor_origin_x)*sx,(y-parent.floor_origin_y)*sy)


def path_shape(points,color,width=1,fill=False,closed=False):
    elements=[cv.Path.MoveTo(*points[0])]+[cv.Path.LineTo(*p) for p in points[1:]]
    if closed: elements.append(cv.Path.Close())
    return cv.Path(elements,paint=ft.Paint(color=color,stroke_width=width,
        style=ft.PaintingStyle.FILL if fill else ft.PaintingStyle.STROKE))


def wall_polygon(barrier):
    angle=math.atan2(barrier.end[1]-barrier.start[1],barrier.end[0]-barrier.start[0])
    nx,ny=-math.sin(angle)*barrier.radius,math.cos(angle)*barrier.radius
    ax,ay=barrier.start
    bx,by=barrier.end
    return [(ax+nx,ay+ny),(bx+nx,by+ny),(bx-nx,by-ny),(ax-nx,ay-ny)]


@lru_cache(maxsize=2048)
def item_shapes(item,parent=None,collisions=False,openings=()):
    shapes=[]
    scale=min(floor_scale(parent))
    if item.kind=="circle_wall":
        if item.stroke:
            for polygon in wall_polygons(item,openings):
                shapes.append(path_shape([project(parent,*p) for p in polygon],item.color,fill=True,closed=True))
        if collisions and item.blocking:
            from navigation.collision import collision_thickness
            for polygon in wall_polygons(item,openings,collision_thickness(item)/2):
                points=[project(parent,*p) for p in polygon]
                shapes.append(path_shape(points,"#00A6A6,0.12",fill=True,closed=True))
                shapes.append(path_shape(points,"#00A6A6",1.5,closed=True))
        return tuple(shapes)
    for primitive in primitives(item):
        if "text" in primitive:
            x,y=project(parent,*item.local_to_world(*primitive["position"]))
            shapes.append(cv.Text(x,y,primitive["text"],style=ft.TextStyle(
                size=primitive["size"]*scale,color=primitive["color"]),
                rotate=math.radians(item.rotation+(parent.rotation if parent else 0))))
        else:
            points=[project(parent,*item.local_to_world(*p)) for p in primitive["points"]]
            if primitive["fill"]!="none":
                shapes.append(path_shape(points,primitive["fill"],fill=True,closed=primitive["closed"]))
            if primitive["stroke"] and item.kind not in WALL_KINDS:
                shapes.append(path_shape(points,primitive["color"],primitive["stroke"]*scale,closed=primitive["closed"]))
    if item.kind in WALL_KINDS and item.stroke:
        for section in wall_sections(item,openings):
            # Project full wall thickness including non-uniform building scale.
            shapes.append(path_shape([project(parent,*p) for p in wall_polygon(section)],item.color,fill=True,closed=True))
    if collisions:
        for barrier in barriers_for_item(item,openings):
            ax,ay=barrier.start
            bx,by=barrier.end
            angle=math.atan2(by-ay,bx-ax)
            if barrier.flat:
                points=wall_polygon(barrier)
            else:
                points=[(ax+barrier.radius*math.cos(angle+math.pi/2+i*math.pi/16),
                         ay+barrier.radius*math.sin(angle+math.pi/2+i*math.pi/16)) for i in range(17)]
                points += [(bx+barrier.radius*math.cos(angle-math.pi/2+i*math.pi/16),
                            by+barrier.radius*math.sin(angle-math.pi/2+i*math.pi/16)) for i in range(17)]
            points=[project(parent,*p) for p in points]
            shapes.append(path_shape(points,ft.Colors.with_opacity(.12,"#00A6A6"),fill=True,closed=True))
            shapes.append(path_shape(points,"#008D8D",1.5,closed=True))
    return tuple(shapes)


def world_handles(item,parent=None):
    result={key:project(parent,*p) for key,p in handles(item).items()}
    center=project(parent,*frame(item).local_to_world(item.width/2,item.height/2))
    top=project(parent,*frame(item).local_to_world(item.width/2,min(0,item.height)))
    dx,dy=top[0]-center[0],top[1]-center[1]
    if math.hypot(dx,dy)<1e-9:
        dx,dy=result["rotate"][0]-center[0],result["rotate"][1]-center[1]
    distance=math.hypot(dx,dy) or 1
    result["rotate"]=(top[0]+36*dx/distance,top[1]+36*dy/distance)
    return result


def selection_shapes(item,parent=None):
    points=[project(parent,*frame(item).local_to_world(*p)) for p in
            ((0,0),(item.width,0),(item.width,item.height),(0,item.height))]
    shapes=[path_shape(points,"#155EEF",1.5,closed=True)]
    positions=world_handles(item,parent)
    rx,ry=positions["rotate"]
    top=project(parent,*frame(item).local_to_world(item.width/2,min(0,item.height)))
    shapes.append(cv.Line(*top,rx,ry,paint=ft.Paint(color="#155EEF")))
    for key,(x,y) in positions.items():
        if key=="rotate":
            shapes.extend([cv.Circle(x,y,12,paint=ft.Paint(color="#155EEF")),
                cv.Text(x,y,"↻",style=ft.TextStyle(size=21,color="#FFFFFF"),alignment=ft.Alignment.CENTER)])
        else:
            shapes.extend([cv.Rect(x-5,y-5,10,10,paint=ft.Paint(color="#FFFFFF")),
                cv.Rect(x-5,y-5,10,10,paint=ft.Paint(color="#155EEF",stroke_width=2,style=ft.PaintingStyle.STROKE))])
    return shapes


def building_image(item,layer="Roof",show_coordinates=False):
    from .building_renderer import building_control
    options={f"{item.layer_style}_layer":layer} if item.layer_style else {}
    if item.layer_style=="academic": options={"academic_layer":layer}
    if item.layer_style=="jhs": options={"jhs_layer":layer}
    return building_control(to_placement(item),show_coordinates=show_coordinates,**options)


def render_scene(scene,scope=CAMPUS,collisions=False,grid=True,spacing=20,
                 image_cache=None,vector_cache=None,show_coordinates=False,preview_item=None,
                 floor_underlay=(),hidden_buildings=(),background_cache=None):
    image_cache={} if image_cache is None else image_cache
    vector_cache={} if vector_cache is None else vector_cache
    background_signature=(scene.width,scene.height,grid,spacing)
    if background_cache is not None and background_cache.get("signature")==background_signature:
        controls=list(background_cache["controls"])
    else:
        controls=[ft.Container(width=scene.width,height=scene.height,bgcolor="#EDF8FA",
            border=ft.Border.all(2,"#94A3B8"))]
        if grid:
            controls.append(cv.Canvas(width=scene.width,height=scene.height,
                shapes=list(grid_shapes(scene.width,scene.height,spacing))))
        if background_cache is not None:background_cache.update(signature=background_signature,controls=tuple(controls))
    parent=scene.parent_for_scope(scope)
    contexts={}

    def context(layer):
        if layer in contexts: return contexts[layer]
        items=scene.floors.get(layer,[])
        if layer==scope and preview_item is not None: items=[*items,preview_item]
        contexts[layer]=OpeningIndex(openings_for(items))
        return contexts[layer]

    def vector(item,owner=None,openings=()):
        openings=openings.for_wall(item) if item.kind in WALL_KINDS else ()
        signature=(item,owner,collisions,openings)
        cached=vector_cache.get(item.id)
        if cached is None:
            canvas=cv.Canvas(width=scene.width,height=scene.height)
        else: canvas=cached[1]
        # Canvas size changed but the geometry is still valid.
        canvas.width,canvas.height=scene.width,scene.height
        canvas.opacity=item.opacity if item.kind in ROOF_KINDS else 1
        if cached is None or cached[0]!=signature:
            canvas.shapes=list(item_shapes(item,owner,collisions,openings))
        vector_cache[item.id]=(signature,canvas)
        controls.append(canvas)

    campus_openings=context(CAMPUS)
    for item in scene.floors[CAMPUS]:
        if item.kind!="building":
            vector(item,openings=campus_openings)
            continue
        layer=scope.split(":",1)[1] if parent and item.id==parent.id else "Roof"
        if item.layer_style and layer.startswith("Floor "):
            from .layers import building_layer_names
            number=int(layer.split()[-1])
            layer=building_layer_names(item.layer_style)[number-1]
        if item.id not in hidden_buildings and not (item.free_build and not item.layer_style and not item.image_src):
            signature=(item,layer,show_coordinates)
            cached=image_cache.get(item.id)
            if cached is None or cached[0]!=signature:
                previous=cached[0][0] if cached else None
                if (cached and (item.image_src or item.layer_style) and cached[0][1:]==signature[1:] and
                        replace(previous,x=item.x,y=item.y)==item):
                    control=cached[1]
                    control.left=(control.left or 0)+item.x-previous.x
                    control.top=(control.top or 0)+item.y-previous.y
                    cached=(signature,control)
                else:cached=(signature,building_image(item,layer,show_coordinates))
                image_cache[item.id]=cached
            controls.append(cached[1])
        # Optional overlays from the caller; the runtime never supplies editor refs.
        if parent and item.id==parent.id: controls.extend(floor_underlay)
        # Show edited roofs on campus; active floor objects replace them.
        visible_scopes=([scope] if parent and parent.id==item.id else
            [scope_key(item,"Floor 1"),scope_key(item,"Roof")] if item.free_build else [scope_key(item,"Roof")])
        for visible_scope in visible_scopes:
            layer_openings=context(visible_scope)
            for child in scene.floors.get(visible_scope,[]): vector(child,item,layer_openings)
    valid_ids={item.id for items in scene.floors.values() for item in items}
    for cache in (image_cache,vector_cache):
        for key in list(cache):
            if key not in valid_ids: cache.pop(key)
    return controls
