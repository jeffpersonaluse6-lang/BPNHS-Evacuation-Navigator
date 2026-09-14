"""Frame independence, spatial caches, thin-zone sweeps and strict arrival locks."""

from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import flet as ft
from drafting.models import DraftItem
from map.scene import MapScene,CAMPUS,scope_key
from map.workspace_editor import MapWorkspaceEditor
from navigation.app import EvacuationApp
from navigation.models import NavigationState
from navigation.motion import MotionClock
from navigation.player_settings import PlayerSettings,load_player_settings,save_player_settings
from navigation.world import WorldNavigator,TransitionPhase
from navigation.runtime_cache import FloorTransform
from benchmark_navigation import stress_scene
from test_map_workspace import page_stub
import test_floor_reentry as reentry


class GameplayTimingTests(unittest.TestCase):
    def setUp(self):
        updater=patch.object(ft.Control,"update");updater.start();self.addCleanup(updater.stop)

    def app(self,speed=120):
        app=EvacuationApp(page_stub(),MapScene(),PlayerSettings(20,1,speed))
        app.state.move_mode=True;app.set_joystick_direction(1,0)
        return app

    def test_default_walk_is_slower_and_elapsed_time_independent_at_different_fps(self):
        positions=[]
        for ticks in (10,30,60,120):
            app=self.app();start=app._marker_center()
            for _ in range(ticks):app.movement_tick(1/ticks)
            distance=app._marker_center()[0]-start[0]
            self.assertAlmostEqual(distance,120,places=6);positions.append(distance)
        self.assertEqual(PlayerSettings().player_speed,120)

    def test_ordinary_delayed_frames_preserve_time_and_camera_remains_visible(self):
        app=self.app();start=app._marker_center()
        for dt in (.4,.01,.09,.3,.2):
            app.movement_tick(dt)
            self.assertTrue(app.viewer.camera.visible(app._marker_center()))
        self.assertAlmostEqual(app._marker_center()[0]-start[0],120,places=6)

    def test_suspension_is_not_replayed_as_teleport(self):
        app=self.app();start=app._marker_center();app.movement_tick(5)
        self.assertEqual(app._marker_center(),start)
        app.movement_tick(.1);self.assertAlmostEqual(app._marker_center()[0]-start[0],12)

    def test_diagonal_direction_does_not_accelerate_player(self):
        app=self.app();app.set_joystick_direction(1,1);start=app._marker_center()
        app.movement_tick(.1);end=app._marker_center()
        import math
        self.assertAlmostEqual(math.dist(start,end),12)

    def test_camera_transform_and_transport_are_batched_once_per_frame(self):
        app=self.app();app.page.update.reset_mock()
        with patch.object(app.viewer,"apply",wraps=app.viewer.apply) as apply:
            app.movement_tick(.1)
        self.assertEqual(apply.call_count,1);self.assertEqual(app.page.update.call_count,1)
        targets=app.page.update.call_args.args
        self.assertIn(app.viewer.scene,targets);self.assertNotIn(app.marker,targets)

    def test_static_geometry_is_not_rebuilt_and_far_buildings_are_not_scanned(self):
        app=EvacuationApp(page_stub(),stress_scene(80,20),PlayerSettings(20,1))
        app.state.move_mode=True;app.set_joystick_direction(1,0)
        with patch.object(app.scene,"buildings",side_effect=AssertionError("whole map scan")),\
             patch("navigation.world.barriers_for",side_effect=AssertionError("collision rebuild")),\
             patch("map.world_renderer.item_shapes",side_effect=AssertionError("geometry rebuild")),\
             patch.object(app.navigator,"floor_opacities",side_effect=AssertionError("all floors scan")),\
             patch.object(app.navigator,"inside",wraps=app.navigator.inside) as inside:
            app.movement_tick(.1)
        self.assertEqual(inside.call_count,0)

    def test_zero_input_camera_settling_never_runs_physics_or_map_updates(self):
        app=self.app();app.movement_tick(.1);app.set_joystick_direction(0,0)
        with patch.object(app.navigator,"walk",wraps=app.navigator.walk) as walk,\
             patch.object(app.world_view,"update",wraps=app.world_view.update) as update:
            app.movement_tick(.1)
        self.assertEqual(update.call_count,0);self.assertEqual(walk.call_count,0)

    def test_scheduler_includes_update_cost_instead_of_sleeping_an_extra_frame(self):
        clock=MotionClock(10)
        self.assertAlmostEqual(clock.delay(10.01,1/60),1/60-.01)
        self.assertAlmostEqual(clock.advance(10.02),.02)
        self.assertEqual(clock.delay(10.05,1/60),0)
        self.assertAlmostEqual(clock.advance(10.05),.03)
        self.assertEqual(clock.advance(20),0)

    def test_speed_controls_preserve_sizes_and_save_load_speed(self):
        app=self.app();app.select_player()
        app.player_controls.change_speed(SimpleNamespace(control=SimpleNamespace(value=75)))
        app.player_controls.change_stair_speed(SimpleNamespace(control=SimpleNamespace(value=.7)))
        app.player_controls.resize(9)
        self.assertEqual(app.player_settings(),PlayerSettings(20,9,75,.7))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"settings.json";app.player_controls.path=path
            app.player_controls.save()
            self.assertEqual(load_player_settings(path),app.player_settings())

    def test_old_settings_load_new_defaults_without_overwriting_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"settings.json"
            save_player_settings(PlayerSettings(20,1),path);before=path.read_bytes()
            raw=json.loads(before);raw.pop("player_speed");raw.pop("stair_speed_multiplier")
            with patch.object(Path,"read_text",return_value=json.dumps(raw)):
                self.assertEqual(load_player_settings(path),PlayerSettings(20,1,120,.65))
            self.assertEqual(path.read_bytes(),before)

    def test_reject_invalid_speed_and_stair_multiplier(self):
        for value in (0,601,float("nan"),float("inf"),True):
            with self.assertRaises(ValueError):PlayerSettings(player_speed=value)
        for value in (0,1.1,float("nan"),True):
            with self.assertRaises(ValueError):PlayerSettings(stair_speed_multiplier=value)

    def test_editor_test_walk_moves_retained_dot_without_refreshing_static_map(self):
        with patch("map.workspace_editor.load_player_settings",return_value=PlayerSettings(20,1)):
            editor=MapWorkspaceEditor(page_stub(),MapScene());editor.mount();editor.toggle_walk()
        nodes=tuple(editor.scene_stack.controls);marker=editor.walk_marker
        with patch.object(editor,"refresh",side_effect=AssertionError("full refresh")),\
             patch.object(editor,"player_barriers",side_effect=AssertionError("barrier recalc")):
            editor.move_player(12,0);editor.update_walk_player()
        self.assertEqual(tuple(editor.scene_stack.controls),nodes)
        self.assertIs(editor.walk_marker,marker)
        self.assertAlmostEqual(marker.left+marker.width/2,editor.player[0])

    def test_cached_transform_matches_scene_with_rotation_mirror_and_offset(self):
        scene=MapScene()
        parent=DraftItem("building",500,400,718,563.25,rotation=37,mirrored=True,
            floor_origin_x=100,floor_origin_y=50)
        scene.floors[CAMPUS]=[parent];transform=FloorTransform.build(parent)
        for point in ((0,0),(100,50),(222,340),(1000,700)):
            expected=scene.project(scope_key(parent,"Floor 1"),*point)
            actual=transform.project(*point)
            for a,b in zip(expected,actual):self.assertAlmostEqual(a,b)
            for a,b in zip(transform.unproject(*actual),point):self.assertAlmostEqual(a,b)


class StairStatePerformanceTests(unittest.TestCase):
    def fixture(self):
        fixture=reentry.FloorReentryTests();fixture.setup_stairs(radius=1)
        return fixture

    def test_explicit_phase_and_authoritative_floor_stay_synchronized(self):
        f=self.fixture();n=f.nav
        self.assertEqual(n.phase,TransitionPhase.ON_FLOOR)
        f.visit((222,405),(222,400))
        self.assertEqual(n.phase,TransitionPhase.ENTERING_STAIRS);self.assertEqual(n.state.floor,1)
        f.visit((222,237));self.assertEqual(n.phase,TransitionPhase.TRANSITIONING)
        self.assertEqual(n.active_floor_opacities(),{1:.5,2:.5})
        f.visit((222,74));self.assertEqual(n.phase,TransitionPhase.ARRIVED)
        self.assertEqual(n.state.floor,2);self.assertEqual(n.active_floor_opacities(),{2:1.})
        f.visit((292,69));self.assertEqual(n.phase,TransitionPhase.WAIT_FOR_EXIT)
        f.visit((292,20));self.assertEqual(n.phase,TransitionPhase.ON_FLOOR)

    def test_exit_frame_cannot_retroactively_trigger_previously_disarmed_zone(self):
        f=self.fixture();f.complete()
        # This segment crosses the down zone while leaving, but it was locked
        # when the segment started. The crossing must not be replayed.
        f.visit((550,400))
        self.assertEqual(f.nav.state.floor,2);self.assertIsNone(f.nav.transition)

    def test_normal_and_stair_speed_are_frame_independent(self):
        for ticks in (10,30,60):
            f=self.fixture();point=f.scene.project(scope_key(f.parent,"Floor 1"),222,390)
            f.nav.update(point)
            start=point
            for _ in range(ticks):point=f.nav.walk(point,0,-1,1/ticks)
            self.assertAlmostEqual(start[1]-point[1],120*.65,places=6)

    def test_thinner_than_collision_substep_zone_is_detected_on_swept_path(self):
        f=self.fixture()
        thin=DraftItem("stairs",200,100,120,.08,stair_from=1,stair_to=2)
        f.scene.floors[scope_key(f.parent,"Floor 1")]=[thin]
        n=WorldNavigator(f.scene,NavigationState(collision_radius=1,player_speed=600))
        n.enter(f.parent)
        point=f.scene.project(scope_key(f.parent,"Floor 1"),222,105)
        n.move(point,0,-10)
        self.assertEqual(n.state.floor,2);self.assertIsNone(n.transition)

    def test_distant_same_floor_stairs_do_not_run_progress_checks(self):
        f=self.fixture();items=f.scene.floors[scope_key(f.parent,"Floor 1")]
        items.extend(replace(f.stair,id=f"far-{n}",x=5000+n*200) for n in range(1000))
        n=WorldNavigator(f.scene,NavigationState(collision_radius=1));n.enter(f.parent)
        with patch("navigation.world.progress",wraps=__import__("navigation.stairs",fromlist=["section_progress"]).section_progress) as progress:
            n.move(f.scene.project(scope_key(f.parent,"Floor 1"),222,405),0,-6)
        self.assertLess(progress.call_count,100)

    def test_distant_barriers_do_not_run_narrow_phase_collision_checks(self):
        f=self.fixture();items=f.scene.floors[scope_key(f.parent,"Floor 1")]
        items.extend(DraftItem("wall",5000+i*200,100,100,0) for i in range(1000))
        n=WorldNavigator(f.scene,NavigationState(collision_radius=1));n.enter(f.parent)
        from navigation.collision import Barrier
        calls=[];original=Barrier.blocks
        def blocks(barrier,*args):calls.append(barrier);return original(barrier,*args)
        with patch.object(Barrier,"blocks",blocks):
            n.move(f.scene.project(scope_key(f.parent,"Floor 1"),222,405),0,-6)
        self.assertLess(len(calls),100)


if __name__=="__main__":unittest.main()
