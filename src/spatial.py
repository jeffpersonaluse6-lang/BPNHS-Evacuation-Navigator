"""Small deterministic bounding-box index shared by geometry and editor tools."""

import math


class BoundsIndex:
    def __init__(self,boxes,cell_size=128):
        self.boxes=tuple(boxes)
        self.cell_size=cell_size
        self.cells={}
        self.large=[]
        for number,box in enumerate(self.boxes):
            x0,x1,y0,y1=self.cell_range(box)
            if (x1-x0+1)*(y1-y0+1)>64:
                self.large.append(number)
                continue
            for x in range(x0,x1+1):
                for y in range(y0,y1+1): self.cells.setdefault((x,y),[]).append(number)

    def cell_range(self,box):
        return tuple(math.floor(value/self.cell_size) for value in (*box[0],*box[1]))

    def query(self,box,padding=(0,0)):
        expanded=tuple((box[a][0]-padding[a],box[a][1]+padding[a]) for a in (0,1))
        x0,x1,y0,y1=self.cell_range(expanded)
        # Bound huge queries by occupied cells rather than iterating empty space.
        candidates=set(self.large)
        if (x1-x0+1)*(y1-y0+1)>max(64,len(self.cells)*2):
            for (x,y),numbers in self.cells.items():
                if x0<=x<=x1 and y0<=y<=y1: candidates.update(numbers)
        else:
            for x in range(x0,x1+1):
                for y in range(y0,y1+1): candidates.update(self.cells.get((x,y),()))
        return tuple(n for n in sorted(candidates) if all(
            self.boxes[n][a][1]>=expanded[a][0] and self.boxes[n][a][0]<=expanded[a][1] for a in (0,1)))
