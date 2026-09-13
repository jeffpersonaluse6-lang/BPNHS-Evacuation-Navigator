"""Hip-roof seam lines for canvas and SVG."""


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
