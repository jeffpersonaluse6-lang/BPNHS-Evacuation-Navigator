"""Exact floor-coordinate reflection using the shared rotation/mirror transform."""

from dataclasses import replace
from .alignment import bounds


def flip_items(items,vertical=True):
    """Reflect the entire selection about its horizontal/vertical center line.

    Rotation plus horizontal mirroring represents either reflection exactly, so
    drawing, collision, door cuts and stair progress all use the same transform.
    Up/Down remains a floor connection, not a screen-space compass direction.
    """
    items=tuple(items)
    if not items:return {}
    boxes=[bounds(item) for item in items]
    center=tuple((min(b[a][0] for b in boxes)+max(b[a][1] for b in boxes))/2 for a in (0,1))
    result={}
    for item in items:
        cx,cy=item.local_to_world(item.width/2,item.height/2)
        destination=(cx,2*center[1]-cy) if vertical else (2*center[0]-cx,cy)
        changed=replace(item,rotation=((180 if vertical else 0)-item.rotation)%360,mirrored=not item.mirrored)
        nx,ny=changed.local_to_world(item.width/2,item.height/2)
        result[item.id]=replace(changed,x=changed.x+destination[0]-nx,y=changed.y+destination[1]-ny)
    return result
