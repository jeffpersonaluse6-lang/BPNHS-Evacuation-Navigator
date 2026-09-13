"""Canvas drawing that matches the SVG export geometry."""

import math
from functools import lru_cache
import flet as ft
import flet.canvas as cv
from .models import primitives
from .handles import handles, frame


@lru_cache(maxsize=2048)
def draw_item(item):
    shapes=[]
    for primitive in primitives(item):
        if "text" in primitive:
            x,y=item.local_to_world(*primitive["position"])
            shapes.append(cv.Text(x,y,primitive["text"],
                                  style=ft.TextStyle(size=primitive["size"],color=primitive["color"]),
                                  rotate=math.radians(item.rotation)))
        else:
            points=[item.local_to_world(*point) for point in primitive["points"]]
            elements=[cv.Path.MoveTo(*points[0])]+[cv.Path.LineTo(*point) for point in points[1:]]
            if primitive["closed"]:
                elements.append(cv.Path.Close())
            if primitive["fill"]!="none":
                shapes.append(cv.Path(elements,paint=ft.Paint(color=primitive["fill"],style=ft.PaintingStyle.FILL)))
            if primitive["stroke"]>0:
                shapes.append(cv.Path(elements,paint=ft.Paint(color=primitive["color"],
                                          stroke_width=primitive["stroke"],style=ft.PaintingStyle.STROKE)))
    return shapes


@lru_cache(maxsize=12)
def grid_shapes(width,height,spacing):
    shapes=[]
    for axis,limit in (("x",int(width)),("y",int(height))):
        for n in range(0,limit+1,spacing):
            paint=ft.Paint(color="#CCD6E0" if n%(spacing*5)==0 else "#E8EDF2",stroke_width=1)
            shapes.append(cv.Line(n,0,n,height,paint=paint) if axis=="x"
                          else cv.Line(0,n,width,n,paint=paint))
    return tuple(shapes)


def drawing_shapes(document,floor,grid=True,spacing=20,selected=None,preview=None):
    shapes=list(grid_shapes(document.width,document.height,spacing)) if grid else []
    for item in document.floors[floor]:
        shapes.extend(draw_item(item))
    if preview:
        shapes.extend(draw_item(preview))
    item=next((item for item in document.floors[floor] if item.id==selected),None)
    if item:
        points=[item.local_to_world(x,y) for x,y in ((0,0),(item.width,0),(item.width,item.height),(0,item.height))]
        elements=[cv.Path.MoveTo(*points[0])]+[cv.Path.LineTo(*point) for point in points[1:]]+[cv.Path.Close()]
        shapes.append(cv.Path(elements,paint=ft.Paint(color="#155EEF",stroke_width=1,style=ft.PaintingStyle.STROKE)))
        positions=handles(item)
        rx,ry=positions['rotate']
        tx,ty=frame(item).local_to_world(item.width/2,min(0,item.height))
        shapes.append(cv.Line(tx,ty,rx,ry,paint=ft.Paint(color="#155EEF",stroke_width=1)))
        for key,(x,y) in positions.items():
            if key=='rotate':
                shapes.append(cv.Circle(x,y,12,paint=ft.Paint(color="#155EEF")))
                shapes.append(cv.Text(x,y,"↻",style=ft.TextStyle(size=21,color="#FFFFFF"),alignment=ft.Alignment.CENTER))
            else:
                shapes.append(cv.Rect(x-5,y-5,10,10,paint=ft.Paint(color="#FFFFFF")))
                shapes.append(cv.Rect(x-5,y-5,10,10,paint=ft.Paint(color="#155EEF",stroke_width=2,style=ft.PaintingStyle.STROKE)))
    return shapes


