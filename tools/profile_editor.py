"""Headless gesture benchmark. Never loads or saves the user's map/assets.

Run with the project environment: python -B tools/profile_editor.py --patches
Measures Python handlers and optionally Flet diff/serialization, NOT native FPS.
"""

import argparse
import cProfile
from pathlib import Path
import pstats
import statistics
import sys
import time
from types import SimpleNamespace
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import flet as ft
from drafting.models import DraftItem
from map.scene import CAMPUS,MapScene
from map.scene_renderer import world_handles
from map.workspace_editor import MapWorkspaceEditor


def pointer(x,y):
    return SimpleNamespace(local_position=SimpleNamespace(x=x,y=y))


class HeadlessPage:
    def __init__(self,patches):
        self.width,self.height=1400,900
        self.overlay=[]
        self.on_keyboard_event=None
        self.root=None
        self.patches=patches
        self.bytes=0
        for name in ("add","clean","run_task","show_dialog","pop_dialog"):
            setattr(self,name,Mock())
        if patches:
            import msgpack
            from flet.messaging.protocol import configure_encode_object_for_msgpack
            from flet.controls.object_patch import ObjectPatch
            self.pack=lambda value:msgpack.packb(value,default=configure_encode_object_for_msgpack(ft.Control))
            self.diff=lambda c:ObjectPatch.from_diff(c,c,control_cls=ft.Control)[0].to_message()
            self.initial=lambda c:ObjectPatch.from_diff(None,c,control_cls=ft.Control)[0].to_message()

    def arm(self,root):
        self.root=root
        if self.patches:self.pack(self.initial(root))  # Configure tracking and snapshot like Flet's initial add.

    def update(self,*controls):
        if self.root is None or not self.patches:return
        for control in controls or (self.root,):
            self.bytes+=len(self.pack(self.diff(control)))


def fixture(count):
    scene=MapScene();scene.width=scene.height=5000
    kinds=("room","wall","railing","stairs","door")
    scene.floors[CAMPUS]=[DraftItem(kinds[n%5],80+(n%50)*80,80+(n//50)*80,
        60,0 if kinds[n%5] in {"wall","railing"} else 60) for n in range(count)]
    return scene


def benchmark(name,count,frames,patches,profile):
    page=HeadlessPage(patches)
    editor=MapWorkspaceEditor(page,fixture(count))
    if name=="building / 200 ghost objects":
        editor.choose_tool("building");editor=editor.builder
        page.arm(editor.control)
        editor.items().extend(DraftItem("room",200+(n%20)*80,200+(n//20)*80,60,60) for n in range(200))
        editor.floor_done()
        editor.items().append(DraftItem("room",600,600,100,100))
    editor.smart_structure.value=False
    editor.smart_snap.value=editor.equal_spacing.value=True
    editor.snap.value=False
    selected=editor.items()[:10] if name=="group / 10 objects" else editor.items()[:1]
    editor.selection.select({i.id for i in selected},False)
    editor.refresh(update=False,properties=True)
    page.arm(editor.control)
    start=world_handles(selected[0],editor.parent())["se"] if name=="resize" else (
        selected[0].x+25,selected[0].y+25)
    began=time.perf_counter();editor.pointer_down(pointer(*start))
    setup=(time.perf_counter()-began)*1000
    page.bytes=0
    profiler=cProfile.Profile() if profile else None
    if profiler:profiler.enable()
    durations=[]
    for frame in range(frames):
        event=pointer(start[0]+frame*.8,start[1]+frame*.5)
        began=time.perf_counter();editor.pointer_move(event)
        durations.append((time.perf_counter()-began)*1000)
    if profiler:profiler.disable()
    candidates=editor.interaction.alignment.last_candidate_count
    byte_count=page.bytes
    began=time.perf_counter();editor.pointer_up(event)
    release=(time.perf_counter()-began)*1000
    p95=sorted(durations)[int((len(durations)-1)*.95)]
    print(f"{name:30} mean {statistics.mean(durations):7.2f} ms  p95 {p95:7.2f} ms  "
          f"begin {setup:7.2f} ms  release {release:7.2f} ms  nearby {candidates}")
    if patches:print(f"  Serialized update payload: {byte_count/frames:,.0f} bytes/event")
    if profiler:pstats.Stats(profiler).strip_dirs().sort_stats("cumulative").print_stats(18)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--objects",type=int,default=1000)
    parser.add_argument("--frames",type=int,default=40)
    parser.add_argument("--patches",action="store_true",help="Include installed Flet diff/serialization CPU work")
    parser.add_argument("--profile",action="store_true",help="Print cProfile hot paths; profiling affects timings")
    args=parser.parse_args()
    if not 10<=args.objects<=3000 or not 1<=args.frames<=300:
        parser.error("Use 10–3000 objects and 1–300 frames")
    print(f"Synthetic 5000×5000 map, {args.objects} mixed objects, {args.frames} moves/gesture; "
          f"Flet patches {'included' if args.patches else 'excluded'}. No native client or map writes.")
    with patch.object(ft.Control,"update"):
        for name in ("drag","group / 10 objects","resize","building / 200 ghost objects"):
            benchmark(name,args.objects,args.frames,args.patches,args.profile)


if __name__=="__main__":main()
