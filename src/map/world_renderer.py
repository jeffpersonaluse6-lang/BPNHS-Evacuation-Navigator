"""Runtime layers — floor/stair opacity updates without scene rebuilds."""

import flet as ft
import flet.canvas as cv
from .scene import CAMPUS,scope_key
from .scene_renderer import building_image,item_shapes,project,path_shape
from navigation.collision import openings_for,OpeningIndex
from navigation.data import floor_frame
from drafting.roof import ROOF_KINDS
from .roof_fading import RoofFading


class WorldMapView:
    def __init__(self,scene):
        self.scene=scene
        self.layers={}
        self.parents={p.id:p for p in scene.buildings()}
        self.previous_parent=None
        self.floor_values={}
        self.faded_roofs=set()
        self.object_roofs=RoofFading(scene)
        controls=[ft.Container(width=scene.width,height=scene.height,bgcolor="#EDF8FA")]
        context=OpeningIndex(openings_for(scene.floors[CAMPUS]))
        for item in scene.floors[CAMPUS]:
            if item.kind!="building":
                if item.kind in ROOF_KINDS:
                    controls.append(self.object_roofs.add(item));continue
                if item.kind!="entry_zone":
                    controls.append(cv.Canvas(width=scene.width,height=scene.height,
                        shapes=list(item_shapes(item,openings=context.for_wall(item)))))
                continue
            for n in range(1,item.floor_count+1):
                children=scene.floors.get(scope_key(item,f"Floor {n}"),[])
                if item.layer_style:
                    from .layers import building_layer_names
                    base=building_image(item,building_layer_names(item.layer_style)[n-1])
                elif item.image_src: base=building_image(item)
                elif item.free_build: base=cv.Canvas(width=scene.width,height=scene.height)
                else:
                    fw,fh=floor_frame(item)
                    points=[project(item,*p) for p in ((0,0),(fw,0),(fw,fh),(0,fh))]
                    base=cv.Canvas(width=scene.width,height=scene.height,
                        shapes=[path_shape(points,"#FFFFFF",fill=True,closed=True)])
                controls.extend(self.add_layer(item,n,base,children))
            roof=scene.floors.get(scope_key(item,"Roof"),[])
            roof_base=(cv.Canvas(width=scene.width,height=scene.height) if (item.free_build or any(c.kind in ROOF_KINDS for c in roof)) and not item.layer_style and not item.image_src
                       else building_image(item))
            controls.extend(self.add_layer(item,"Roof",roof_base,roof,roof=True))
        self.object_roofs.finish()
        self.control=ft.Stack(width=scene.width,height=scene.height,controls=controls)

    def add_layer(self,parent,key,base,items,roof=False):
        context=OpeningIndex(openings_for(items))
        fade_shapes=[]
        solid_shapes=[]
        fade_roofs=[];solid_roofs=[]
        for item in items:
            if item.kind=="entry_zone": continue
            if item.kind in ROOF_KINDS:
                (fade_roofs if item.fade_when_obstructing else solid_roofs).append(self.object_roofs.add(item,parent));continue
            target=fade_shapes if item.fade_when_obstructing else solid_shapes
            target.extend(item_shapes(item,parent,openings=context.for_wall(item)))
        visible=key in {1,"Roof"}
        fade=ft.Container(opacity=1 if visible else 0,visible=visible,
            animate_opacity=ft.Animation(140,ft.AnimationCurve.EASE_OUT) if roof else None,
            content=ft.Stack(width=self.scene.width,height=self.scene.height,controls=[base,
                cv.Canvas(width=self.scene.width,height=self.scene.height,shapes=fade_shapes),*fade_roofs]))
        solid=ft.Container(opacity=1 if visible else 0,visible=visible,
            content=cv.Canvas(width=self.scene.width,height=self.scene.height,shapes=solid_shapes))
        if solid_roofs:solid.content=ft.Stack(width=self.scene.width,height=self.scene.height,controls=[solid.content,*solid_roofs])
        self.layers[parent.id,key]=(fade,solid)
        return [fade,solid]

    def update(self,navigator,point):
        dirty=[]
        def set_opacity(control,value):
            if control.opacity==value:return
            was_visible=control.visible
            should_show=value>0
            if should_show and not was_visible:control.visible=True
            control.opacity=value
            dirty.append(control)
            if not should_show and was_visible:control.visible=False
        current=navigator.parent.id if navigator.parent else None
        for pid in {self.previous_parent,current}-{None}:
            values=navigator.active_floor_opacities() if pid==current else {1:1.}
            previous=self.floor_values.get(pid,{1:1.})
            for floor in previous.keys()|values.keys():
                alpha=values.get(floor,0.)
                if alpha==previous.get(floor,0.):continue
                fade,solid=self.layers[pid,floor]
                set_opacity(fade,alpha)
                set_opacity(solid,alpha)
            self.floor_values[pid]=values
        self.previous_parent=current
        nearby={p.id for p in navigator.roof_index.query(point)}
        fading=set()
        for pid in nearby|self.faded_roofs|({current} if current else set()):
            parent=self.parents[pid]
            fade,solid=self.layers[parent.id,"Roof"]
            value=navigator.roof_opacity(parent,point) if pid in nearby or pid==current else 1.
            set_opacity(fade,value)
            if value<1:fading.add(pid)
        self.faded_roofs=fading
        dirty.extend(self.object_roofs.update(point))
        return dirty
