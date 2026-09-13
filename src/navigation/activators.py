"""Explicit floor transition zones shared by runtime and editor."""

from .stairs import STAIR_KINDS

KIND="floor_activator"


def orientation(zone):
    return zone.stair_direction if zone.activator_axis=="auto" else zone.activator_axis


def progress(zone,point):
    """Return clamped progress, lateral corridor membership, and raw progress."""
    x,y=zone.world_to_local(*point)
    axis=orientation(zone)
    if axis in {"up","down"}:
        raw=(zone.height-y)/zone.height if axis=="up" else y/zone.height
        lateral=-1e-7<=x<=zone.width+1e-7
    else:
        raw=(zone.width-x)/zone.width if axis=="left" else x/zone.width
        lateral=-1e-7<=y<=zone.height+1e-7
    return max(0,min(1,raw)),lateral,raw


def endpoints(zone):
    axis=orientation(zone)
    if axis in {"up","down"}:
        pair=((zone.width/2,zone.height*.85),(zone.width/2,zone.height*.15))
        return pair if axis=="up" else pair[::-1]
    pair=((zone.width*.15,zone.height/2),(zone.width*.85,zone.height/2))
    return pair if axis=="right" else pair[::-1]


def valid(zone,source,count,items,*,configuration=False):
    if zone.kind!=KIND or zone.activator_from!=source:return False
    if not configuration and not zone.activator_enabled:return False
    if not 1<=zone.activator_to<=count or zone.activator_to==source:return False
    if (zone.stair_direction=="up")!=(zone.activator_to>source):return False
    return zone.activator_stair is None or any(i.id==zone.activator_stair and i.kind in STAIR_KINDS for i in items)
