"""Stair direction and travel geometry (local axes, not screen)."""

STAIR_KINDS={"stairs","double_stairs"}


def stair_sections(item):
    if item.kind=="stairs":
        return ((0,item.width,item.stair_direction,item.stair_to),)
    return ((0,item.width/2-3,item.stair_direction,item.stair_to),
            (item.width/2+3,item.width,item.stair_right_direction,item.stair_right_to))


def connection(item,section,floor,count):
    _,_,direction,explicit=stair_sections(item)[section]
    target=explicit if explicit is not None else floor+(1 if direction=="up" else -1)
    return target if 1<=target<=count and target!=floor else None


def progress(item,section,point):
    x,y=item.world_to_local(*point)
    lo,hi,direction,_=stair_sections(item)[section]
    landing=min(24,item.height/5) if item.kind=="double_stairs" else 0
    p=(item.height-y)/(item.height-landing) if direction=="up" else (y-landing)/(item.height-landing)
    return max(0,min(1,p)),lo-1e-7<=x<=hi+1e-7 and landing-1e-7<=y<=item.height+1e-7,p


def indicators(item):
    """Arrow endpoints and labels for each flight."""
    landing=min(24,item.height/5) if item.kind=="double_stairs" else 0
    result=[]
    for lo,hi,direction,_ in stair_sections(item):
        x=(lo+hi)/2
        start,end=(item.height*.8,landing+(item.height-landing)*.2)
        if direction=="down": start,end=end,start
        result.append(((x,start),(x,end),direction.upper()))
    return result
