"""Hip-roof seam lines for canvas and SVG."""

from .circular import ellipse_points
import math

ROOF_KINDS={"roof","gazebo_roof","court_roof"}


def structure_roof_primitives(item):
    """Purpose-built radial gazebo and ribbed gable court roofs."""
    w,h=item.width,item.height;result=[]
    def line(points,fill="none",closed=False,stroke=None):
        result.append({"points":points,"color":item.color,"stroke":item.stroke if stroke is None else stroke,
            "fill":fill,"closed":closed})
    if item.kind=="gazebo_roof":
        for n in range(8):
            points=[(w/2,h/2),*ellipse_points(w,h,n*math.pi/4,(n+1)*math.pi/4)]
            line(points,item.fill,True,0)
        line(ellipse_points(w,h),closed=True)
        for n in range(8):
            a=n*math.pi/4;line([(w/2,h/2),(w/2+w/2*math.cos(a),h/2+h/2*math.sin(a))])
        line([(w/2+x-w*.46,h/2+y-h*.46) for x,y in ellipse_points(w*.92,h*.92)],closed=True)
        line([(w/2+x-w*.04,h/2+y-h*.04) for x,y in ellipse_points(w*.08,h*.08)],item.fill,True)
    elif item.kind=="court_roof":
        line([(0,0),(w,0),(w,h),(0,h)],item.fill,True)
        horizontal=w>=h
        count=max(4,min(80,math.ceil((w if horizontal else h)/48)))
        for n in range(1,count):
            p=n/count
            line([(w*p,0),(w*p,h)] if horizontal else [(0,h*p),(w,h*p)],stroke=max(.5,item.stroke*.5))
        line([(0,h/2),(w,h/2)] if horizontal else [(w/2,0),(w/2,h)])
        for p in (.06,.94):
            line([(0,h*p),(w,h*p)] if horizontal else [(w*p,0),(w*p,h)],stroke=max(.5,item.stroke*.6))
    return result


def roof_seams(width, height):
    inset = min(width, height) / 2
    if width >= height:
        first, last = (inset, height / 2), (width - inset, height / 2)
        corners = [((0, 0), first), ((0, height), first),
                   ((width, 0), last), ((width, height), last)]
    else:
        first, last = (width / 2, inset), (width / 2, height - inset)
        corners = [((0, 0), first), ((width, 0), first),
                   ((0, height), last), ((width, height), last)]
    return [list(pair) for pair in corners] + ([[first, last]] if first != last else [])
