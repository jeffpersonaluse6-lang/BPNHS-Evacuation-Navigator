"""Save a complete editable draft and a tightly framed current-floor SVG."""
from pathlib import Path
import uuid
import xml.etree.ElementTree as ET
from .models import primitives


def map_svg(document,floor):
    points=[]
    padding=4
    for item in document.floors[floor]:
        padding=max(padding,item.stroke/2+2)
        for primitive in primitives(item):
            if 'points' in primitive:
                points.extend(item.local_to_world(*p) for p in primitive['points'])
            else:
                x,y=primitive['position']
                w=max(item.width,len(primitive['text'])*primitive['size']*.7)
                h=max(item.height,primitive['size']*1.4)
                points.extend(item.local_to_world(px,py) for px,py in ((x,y),(x+w,y),(x+w,y+h),(x,y+h)))
    if not points:
        raise ValueError('This floor has no drawing objects.')
    left=min(p[0] for p in points)-padding
    top=min(p[1] for p in points)-padding
    width=max(p[0] for p in points)-left+padding
    height=max(p[1] for p in points)-top+padding
    ET.register_namespace('', 'http://www.w3.org/2000/svg')
    root=ET.fromstring(document.svg(floor))
    root.set('viewBox',f'{left:g} {top:g} {width:g} {height:g}')
    root.set('width',f'{width:g}')
    root.set('height',f'{height:g}')
    return ET.tostring(root,encoding='utf-8'),width,height


def save_map_draft(document,floor,assets_root):
    svg,width,height=map_svg(document,floor)
    folder=Path(assets_root)/'DRAFT BUILDINGS'
    folder.mkdir(parents=True,exist_ok=True)
    name=''.join(c if c.isalnum() or c in '-_' else '_' for c in document.name)[:60] or 'building'
    stem=f'{name}-{uuid.uuid4().hex[:12]}'
    # Unique sibling files preserve all earlier exports and editable floor data.
    (folder/f'{stem}.json').write_text(document.to_json(),encoding='utf-8')
    (folder/f'{stem}.svg').write_bytes(svg)
    return f'DRAFT BUILDINGS/{stem}.svg',width,height


