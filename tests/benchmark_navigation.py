"""Repeatable headless gameplay profile, including real Flet object diffs.

Run: python tests/benchmark_navigation.py --buildings 200 --floors 20 --ticks 60
This measures Python/patch work, not native GPU rendering or display latency.
"""

import argparse
import cProfile
from pathlib import Path
import pstats
import sys
import time
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import flet as ft
from flet.controls.object_patch import ObjectPatch
from drafting.models import DraftItem
from map.scene import MapScene,CAMPUS,scope_key
from navigation.app import EvacuationApp
from navigation.player_settings import PlayerSettings
from test_map_workspace import page_stub


def stress_scene(count,floors):
    scene=MapScene();scene.width=max(100000,count*2000+5000);scene.height=20000
    scene.floors={CAMPUS:[]}
    for n in range(count):
        parent=DraftItem("building",4000+n*2000,2000,1436,751,floor_count=floors)
        scene.floors[CAMPUS].append(parent)
        for floor in range(1,floors+1):scene.floors[scope_key(parent,f"Floor {floor}")]=[]
    return scene


def run(count,floors,ticks,speed=120):
    with patch.object(ft.Control,"update"):
        app=EvacuationApp(page_stub(),stress_scene(count,floors),PlayerSettings(20,1,speed))
        app.state.move_mode=True;app.set_joystick_direction(.5,0)
        ObjectPatch.from_diff(None,app.world_view.control,control_cls=ft.Control)
        def send(*controls):
            for control in controls:ObjectPatch.from_diff(control,control,control_cls=ft.Control)
        app.page.update.side_effect=send
        with patch.object(app.viewer.scene,"update",side_effect=lambda:send(app.viewer.scene)):
            profiler=cProfile.Profile();start=time.perf_counter();profiler.enable()
            for _ in range(ticks):app.movement_tick(1/30)
            profiler.disable();elapsed=time.perf_counter()-start
    print(f"{count} buildings, {floors} floors each, {ticks} ticks: {elapsed*1000/ticks:.3f} ms/tick (profiled)")
    pstats.Stats(profiler).strip_dirs().sort_stats("cumtime").print_stats(15)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--buildings",type=int,default=200)
    parser.add_argument("--floors",type=int,default=20)
    parser.add_argument("--ticks",type=int,default=60)
    parser.add_argument("--speed",type=float,default=120)
    args=parser.parse_args();run(args.buildings,args.floors,args.ticks,args.speed)
