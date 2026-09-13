"""Selection handles and resize/rotation math."""
from dataclasses import replace
import math

def frame(item):
    return replace(item, mirrored=False)

def handles(item):
    f=frame(item)
    if item.kind in {'wall','line','railing'}:
        points={'start':(0,0),'end':(item.width,item.height)}
    else:
        w,h=item.width,item.height
        points={'nw':(0,0),'n':(w/2,0),'ne':(w,0),'e':(w,h/2),
                'se':(w,h),'s':(w/2,h),'sw':(0,h),'w':(0,h/2)}
    points['rotate']=(item.width/2,min(0,item.height)-36)
    return {key:f.local_to_world(*point) for key,point in points.items()}

def hit_handle(item,x,y):
    return next((key for key,(hx,hy) in reversed(list(handles(item).items()))
                 if math.hypot(x-hx,y-hy)<=14),None)

def rotate_about_center(item,degrees):
    cx,cy=frame(item).local_to_world(item.width/2,item.height/2)
    rotated=replace(item,rotation=degrees%360)
    rx,ry=frame(rotated).local_to_world(item.width/2,item.height/2)
    return replace(rotated,x=rotated.x+cx-rx,y=rotated.y+cy-ry)

def transform(item,handle,start,point,snap=0):
    f=frame(item)
    if handle=='rotate':
        cx,cy=f.local_to_world(item.width/2,item.height/2)
        a=math.atan2(start[1]-cy,start[0]-cx)
        b=math.atan2(point[1]-cy,point[0]-cx)
        angle=item.rotation+math.degrees(b-a)
        if snap: angle=round(angle/15)*15
        return rotate_about_center(item,angle)
    sx,sy=f.world_to_local(*start)
    px,py=f.world_to_local(*point)
    dx,dy=px-sx,py-sy
    if snap:
        dx,dy=round(dx/snap)*snap,round(dy/snap)*snap
    if handle=='end':
        return replace(item,width=item.width+dx,height=item.height+dy)
    if handle=='start':
        x,y=f.local_to_world(dx,dy)
        return replace(item,x=x,y=y,width=item.width-dx,height=item.height-dy)
    left=top=0
    right,bottom=item.width,item.height
    if 'w' in handle: left=min(dx,right-4)
    if 'e' in handle: right=max(4,right+dx)
    if 'n' in handle: top=min(dy,bottom-4)
    if 's' in handle: bottom=max(4,bottom+dy)
    x,y=f.local_to_world(left,top)
    return replace(item,x=x,y=y,width=right-left,height=bottom-top)

