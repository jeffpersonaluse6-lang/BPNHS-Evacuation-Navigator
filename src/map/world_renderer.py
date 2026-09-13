"""Retained runtime layers: entering/stairs update opacity, never rebuild a scene."""

import flet as ft
import flet.canvas as cv
from .scene import CAMPUS,scope_key
from .scene_renderer import building_image,item_shapes,project,path_shape
from navigation.collision import openings_for,OpeningIndex
from navigation.data import floor_frame


class WorldMapView:
    def __init__(self,scene):
        self.scene=scene
        self.layers={}
        controls=[ft.Container(width=scene.width,height=scene.height,bgcolor="#EDF8FA")]
        context=OpeningIndex(openings_for(scene.floors[CAMPUS]))
        for item in scene.floors[CAMPUS]:
            if item.kind!="building":
                if item.kind not in {"entry_zone","floor_activator"}:
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
            roof_base=(cv.Canvas(width=scene.width,height=scene.height) if (item.free_build or any(c.kind=="roof" for c in roof)) and not item.layer_style and not item.image_src
                       else building_image(item))
            controls.extend(self.add_layer(item,"Roof",roof_base,roof,roof=True))
        self.control=ft.Stack(width=scene.width,height=scene.height,controls=controls)

    def add_layer(self,parent,key,base,items,roof=False):
        context=OpeningIndex(openings_for(items))
        fade_shapes=[]
        solid_shapes=[]
        for item in items:
            if item.kind in {"entry_zone","floor_activator"}: continue
            target=fade_shapes if item.fade_when_obstructing else solid_shapes
            target.extend(item_shapes(item,parent,openings=context.for_wall(item)))
        fade=ft.Container(opacity=1 if key in {1,"Roof"} else 0,
            animate_opacity=ft.Animation(140,ft.AnimationCurve.EASE_OUT) if roof else None,
            content=ft.Stack(width=self.scene.width,height=self.scene.height,controls=[base,
                cv.Canvas(width=self.scene.width,height=self.scene.height,shapes=fade_shapes)]))
        solid=ft.Container(opacity=0,content=cv.Canvas(width=self.scene.width,height=self.scene.height,shapes=solid_shapes))
        self.layers[parent.id,key]=(fade,solid)
        return [fade,solid]

    def update(self,navigator,point):
        dirty=[]
        def opacity(control,value):
            if control.opacity!=value:control.opacity=value;dirty.append(control)
        for parent in self.scene.buildings():
            for floor,alpha in navigator.floor_opacities(parent).items():
                fade,solid=self.layers[parent.id,floor]
                opacity(fade,alpha)
                opacity(solid,alpha)
            fade,solid=self.layers[parent.id,"Roof"]
            opacity(fade,navigator.roof_opacity(parent,point))
            opacity(solid,1)  # Explicitly non-fading roof objects remain visible.
        return dirty
