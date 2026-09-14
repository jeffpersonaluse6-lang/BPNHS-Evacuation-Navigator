"""Cached roof-object footprints and opacity-only runtime updates."""

import flet as ft
import flet.canvas as cv
from drafting.circular import ellipse_points
from navigation.collision import PolygonBarrier
from navigation.runtime_cache import RuntimeIndex,polygon_distance
from .scene_renderer import project,item_shapes


class RoofFading:
    def __init__(self,scene):
        self.scene=scene;self.records={};self.faded=set();self.index=None

    def add(self,item,parent=None):
        points=(ellipse_points(item.width,item.height) if item.kind=="gazebo_roof" else
            ((0,0),(item.width,0),(item.width,item.height),(0,item.height)))
        area=PolygonBarrier(tuple(project(parent,*item.local_to_world(*p)) for p in points))
        control=ft.Container(width=self.scene.width,height=self.scene.height,opacity=item.opacity,
            animate_opacity=ft.Animation(140,ft.AnimationCurve.EASE_OUT),
            content=cv.Canvas(width=self.scene.width,height=self.scene.height,shapes=list(item_shapes(item,parent))))
        self.records[item.id]=(item,area,control)
        return control

    def finish(self):
        ids=tuple(self.records)
        boxes=[tuple((lo-self.records[key][0].approach_distance,hi+self.records[key][0].approach_distance)
            for lo,hi in self.records[key][1].bounds) for key in ids]
        self.index=RuntimeIndex(ids,boxes)

    def update(self,point):
        dirty=[];nearby=set(self.index.query(point));faded=set()
        for key in nearby|self.faded:
            item,area,control=self.records[key];factor=1.
            if item.fade_when_obstructing and key in nearby:
                distance=polygon_distance(area,point)
                factor=min(1,distance/item.approach_distance) if item.approach_distance else float(distance>0)
            value=item.opacity*factor
            if control.opacity!=value:control.opacity=value;dirty.append(control)
            if value<item.opacity:faded.add(key)
        self.faded=faded
        return dirty
