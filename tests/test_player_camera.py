"""Blue-dot sizing, stable building geometry, and bounded interpolated following."""

import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import flet as ft
from drafting.models import DraftItem
from map.scene import MapScene,CAMPUS,scope_key
from navigation.app import EvacuationApp
from navigation.camera import SmoothCamera
from test_map_workspace import page_stub


class SmoothCameraTests(unittest.TestCase):
    def test_start_recenter_interpolates_without_changing_zoom_or_rotation(self):
        camera=SmoothCamera(width=1000,height=700)
        camera.follow((800,350),1/30,moving=True)
        self.assertGreater(camera.x,-300);self.assertLess(camera.x,0)
        self.assertEqual((camera.scale,camera.rotation),(1,0))

    def test_movement_trails_and_stopping_settles_without_overshoot(self):
        camera=SmoothCamera(width=1000,height=700);point=(500,350)
        for _ in range(60):
            point=(point[0]+10,350);camera.follow(point,1/30,moving=True)
            self.assertTrue(camera.visible(point))
        gap=camera.screen(point)[0]-500
        self.assertGreater(gap,20);self.assertLess(gap,80)
        for _ in range(90):
            camera.follow(point,1/30)
            next_gap=camera.screen(point)[0]-500
            self.assertGreaterEqual(next_gap,-1e-6);self.assertLessEqual(next_gap,gap+1e-6);gap=next_gap
        self.assertLess(gap,.05)

    def test_interpolation_is_frame_independent_for_stationary_focus(self):
        results=[]
        for ticks in (30,60,120):
            camera=SmoothCamera(width=1000,height=700)
            for _ in range(ticks):camera.follow((700,350),1/ticks)
            results.append(camera.x)
        self.assertAlmostEqual(results[0],results[1]);self.assertAlmostEqual(results[1],results[2])

    def test_visibility_guard_handles_fast_movement_small_viewport_zoom_and_rotation(self):
        for rotation in (0,math.pi/2,math.pi):
            camera=SmoothCamera(width=300,height=400,scale=3,rotation=rotation)
            camera.center((500,500));camera.follow((900,100),1/30,moving=True,diameter=52,guard=True)
            self.assertTrue(camera.visible((900,100),52))
            self.assertEqual((camera.scale,camera.rotation),(3,rotation))

    def test_offscreen_manual_view_returns_gradually(self):
        camera=SmoothCamera(width=1000,height=700,x=-4000)
        camera.follow((500,350),1/30,guard=False)
        self.assertLess(camera.x,-1000)
        for _ in range(120):camera.follow((500,350),1/30)
        self.assertAlmostEqual(camera.screen((500,350))[0],500,places=2)


class PlayerCameraIntegrationTests(unittest.TestCase):
    def setUp(self):
        from player_fixtures import isolate_player_settings
        isolate_player_settings(self)
        update=patch.object(ft.Control,"update");update.start();self.addCleanup(update.stop)
        self.scene=MapScene();self.app=EvacuationApp(page_stub(),self.scene)

    def test_blue_dot_resizes_about_its_center_without_resizing_world(self):
        app=self.app;center=app._marker_center();before=self.scene.snapshot()
        self.assertEqual(app.marker.bgcolor,"#155EEF");self.assertIsNone(app.marker.content)
        self.assertIsNone(app.marker.border);self.assertEqual(app.marker.width,20)
        app.resize_player(SimpleNamespace(control=SimpleNamespace(value=36)))
        self.assertEqual((app.marker.width,app.marker.height,app.marker.border_radius),(36,36,18))
        self.assertEqual((app.marker.left+18,app.marker.top+18),center)
        self.assertEqual(self.scene.snapshot(),before)

    def test_approach_entry_floor_blend_and_exit_keep_all_building_geometry_constant(self):
        parent=DraftItem("building",100,100,718,375.5,floor_count=4,layer_style="academic",opens="school")
        stair=DraftItem("stairs",200,100,120,240)
        self.scene.floors={CAMPUS:[parent],scope_key(parent,"Floor 1"):[stair]}
        app=EvacuationApp(page_stub(),self.scene);before=self.scene.snapshot()
        def geometry():
            seen=set();result={};pending=[app.world_view.control]
            while pending:
                node=pending.pop()
                if not isinstance(node,ft.Control) or id(node) in seen:continue
                seen.add(id(node))
                if node is not app.marker and node is not app.collision_preview:
                    result[id(node)]=tuple(getattr(node,k,None) for k in ("left","top","width","height","scale","rotate"))
                for field in ("controls","content"):
                    child=getattr(node,field,None);pending.extend(child if isinstance(child,list) else [child])
            return result
        original=geometry();scale=app.viewer.camera.scale
        points=[(60,300),(90,300),self.scene.project(scope_key(parent,"Floor 1"),260,345),
            *[self.scene.project(scope_key(parent,"Floor 1"),260,y) for y in (340,280,220,160,100)]]
        for point in points:
            app.state.marker_x,app.state.marker_y=point[0]-26,point[1]-26
            app._check_building_entry()
            self.assertEqual(geometry(),original);self.assertEqual(app.marker.width,20)
            self.assertEqual(app.viewer.camera.scale,scale)
        self.assertEqual(app.state.floor,2)
        app.return_to_campus(None)
        self.assertEqual(geometry(),original);self.assertEqual(self.scene.snapshot(),before)

    def test_movement_loop_trails_then_continues_settling_with_zero_input(self):
        app=self.app;app.state.move_mode=True;app.set_joystick_direction(.6,.2)
        viewer=app.viewer;canvas=app.world_view.control
        for _ in range(30):
            app.movement_tick(1/30);self.assertTrue(viewer.camera.visible(app._marker_center(),app.state.player_size))
        x,y=viewer.camera.screen(app._marker_center())
        self.assertGreater(x,viewer.camera.width/2)
        app.set_joystick_direction(0,0);position=app._marker_center()
        for _ in range(90):app.movement_tick(1/30)
        self.assertEqual(app._marker_center(),position)
        x,y=viewer.camera.screen(position)
        self.assertAlmostEqual(x,viewer.camera.width/2,places=2);self.assertAlmostEqual(y,viewer.camera.height/2,places=2)
        self.assertIs(app.viewer,viewer);self.assertIs(app.world_view.control,canvas)

    def test_manual_zoom_rotation_and_pan_share_transform_with_follow(self):
        viewer=self.app.viewer;camera=viewer.camera
        focal=SimpleNamespace(x=300,y=200)
        anchor=camera.world((300,200))
        viewer.start(SimpleNamespace(local_focal_point=focal))
        viewer.gesture_update(SimpleNamespace(local_focal_point=SimpleNamespace(x=330,y=240),scale=1.5,rotation=.4))
        for actual,expected in zip(camera.screen(anchor),(330,240)):self.assertAlmostEqual(actual,expected)
        self.app.state.move_mode=True;viewer.pan_enabled=viewer.scale_enabled=False
        transform=(camera.scale,camera.rotation)
        for _ in range(60):self.app.movement_tick(1/30)
        self.assertEqual((camera.scale,camera.rotation),transform)
        center=camera.world((camera.width/2,camera.height/2))
        viewer.resize(SimpleNamespace(width=800,height=500))
        for actual,expected in zip(camera.world((400,250)),center):self.assertAlmostEqual(actual,expected)

    def test_unseen_player_waits_for_smooth_recenter_before_walking(self):
        app=self.app;app.state.move_mode=True;app.set_joystick_direction(1,0)
        app.viewer.camera.x-=4000;before=app._marker_center();offset=app.viewer.camera.x
        app.movement_tick(1/30)
        self.assertEqual(app._marker_center(),before)
        self.assertGreater(app.viewer.camera.x,offset)
        self.assertFalse(app.viewer.camera.visible(before))
        for _ in range(120):app.movement_tick(1/30)
        self.assertGreater(app._marker_center()[0],before[0])
        self.assertTrue(app.viewer.camera.visible(app._marker_center(),app.state.player_size))

    def test_finish_moving_settles_and_manual_gesture_cancels_follow(self):
        app=self.app;app.toggle_move_mode(None);app.set_joystick_direction(1,0)
        for _ in range(30):app.movement_tick(1/30)
        app.toggle_move_mode(None);self.assertTrue(app.follow_active)
        center=app._marker_center()
        for _ in range(90):app.movement_tick(1/30)
        self.assertEqual(app._marker_center(),center);self.assertFalse(app.follow_active)
        app.follow_active=True
        app.viewer.start(SimpleNamespace(local_focal_point=SimpleNamespace(x=300,y=200)))
        self.assertFalse(app.follow_active)

    def test_real_flet_protocol_serializes_viewport_and_transform_updates(self):
        import msgpack
        from flet.controls.object_patch import ObjectPatch
        from flet.messaging.protocol import configure_encode_object_for_msgpack
        encode=configure_encode_object_for_msgpack(ft.Control)
        def serialize(control,previous=None):
            delta=ObjectPatch.from_diff(previous,control,control_cls=ft.Control)[0]
            return msgpack.packb(delta.to_message(),default=encode)
        root=self.app.page.add.call_args.args[0]
        self.assertTrue(serialize(root))
        self.app.toggle_move_mode(None);self.app.set_joystick_direction(1,0)
        self.app.movement_tick(1/30)
        canvas=self.app.world_view.control
        self.assertTrue(serialize(canvas,canvas))
        self.app.resize_player(SimpleNamespace(control=SimpleNamespace(value=40)))
        self.assertTrue(serialize(self.app.marker,self.app.marker))
        self.assertEqual(len(canvas.transform.matrix.ops),3)


if __name__=="__main__":unittest.main()
