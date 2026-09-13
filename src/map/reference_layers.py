"""Ghost floors and their visibility settings belong to the editor only."""

from dataclasses import dataclass, replace
import flet as ft
import flet.canvas as cv
from navigation.collision import openings_for,OpeningIndex
from .scene import scope_key
from .scene_renderer import building_image, item_shapes, project, path_shape


@dataclass
class ReferenceView:
    previous: bool = True
    multiple: bool = False
    opacity: float = .22
    focus: bool = False
    all_other: bool = False

    def layers(self, scene, scope):
        parent = scene.parent_for_scope(scope)
        if not parent or not self.previous or self.focus:
            return []
        layer = scope.split(":", 1)[1]
        number = parent.floor_count + 1 if layer == "Roof" else int(layer.split()[-1])
        if self.all_other:
            return [(scope_key(parent,f"Floor {n}"),self.opacity/abs(number-n))
                    for n in range(1,parent.floor_count+1) if n!=number]
        numbers = range(1, number) if self.multiple else range(max(1, number - 1), number)
        return [(scope_key(parent, f"Floor {n}"), self.opacity / (number - n)) for n in numbers]


def reference_controls(scene, scope, view, cache=None):
    parent = scene.parent_for_scope(scope)
    references = view.layers(scene, scope)
    signature = (scene.width, scene.height, parent,
                 tuple((key, opacity, tuple(scene.floors.get(key, []))) for key, opacity in references))
    if cache is not None and cache.get("signature") == signature:
        return cache["controls"]
    controls = []
    for key, opacity in references:
        children = scene.floors.get(key, [])
        shapes = []
        openings = OpeningIndex(openings_for(children))
        for item in children:
            if item.kind=="floor_activator":continue
            # Outlines, not opaque room interiors, make useful blueprint references.
            ghost = replace(item, fill="none", color="#64748B")
            shapes.extend(item_shapes(ghost, parent, False, openings.for_wall(ghost)))
        layers = []
        if parent.layer_style:
            from .layers import building_layer_names
            number = int(key.split()[-1])
            layers.append(building_image(parent, building_layer_names(parent.layer_style)[number - 1]))
        layers.append(cv.Canvas(width=scene.width, height=scene.height, shapes=shapes))
        controls.append(ft.Container(opacity=max(0, min(1, opacity)),ignore_interactions=True,
            content=ft.Stack(width=scene.width, height=scene.height, controls=layers)))
    if cache is not None:
        cache.update(signature=signature, controls=controls)
    return controls


def active_floor_outline(scene, scope, zoom=1):
    parent = scene.parent_for_scope(scope)
    if parent is None:
        return []
    from navigation.data import floor_frame
    width,height=floor_frame(parent)
    x,y=parent.floor_origin_x,parent.floor_origin_y
    return [path_shape([project(parent, *p) for p in ((x,y),(x+width,y),(x+width,y+height),(x,y+height))],
                       "#2563EB", 1.5 / zoom, closed=True)]
