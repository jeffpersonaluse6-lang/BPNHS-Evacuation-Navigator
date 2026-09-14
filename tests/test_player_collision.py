"""Selected-player collision resizing, world-unit clearance and separate persistence."""

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
from navigation.world import WorldNavigator
from navigation.player_settings import PlayerSettings,load_player_settings,save_player_settings
from test_map_workspace import page_stub


def event(value):return SimpleNamespace(control=SimpleNamespace(value=value))


class PlayerSettingsTests(unittest.TestCase):
    def test_missing_defaults_and_round_trip_both_independent_sizes(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"preferences.json"
            self.assertEqual(load_player_settings(path),PlayerSettings())
            self.assertFalse(path.exists())
            settings=PlayerSettings(34,7.5)
            save_player_settings(settings,path)
            self.assertEqual(load_player_settings(path),settings)
            self.assertEqual(list(Path(directory).glob("*.tmp")),[])

    def test_reject_invalid_radius_and_visual_sizes(self):
        for value in (0,-1,101,float("inf"),float("nan"),True,"12",None):
            with self.subTest(value=value),self.assertRaises(ValueError):PlayerSettings(20,value)
        for value in (7,53,float("nan"),True):
            with self.assertRaises(ValueError):PlayerSettings(value,26)

    def test_bad_file_does_not_modify_last_saved_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"preferences.json"
            save_player_settings(PlayerSettings(40,9),path);original=path.read_bytes()
            with patch("navigation.player_settings.os.replace",side_effect=OSError("disk error")):
                with self.assertRaises(OSError):save_player_settings(PlayerSettings(20,30),path)
            self.assertEqual(path.read_bytes(),original)
            self.assertEqual(len(list(Path(directory).iterdir())),1)

    def test_invalid_file_schema_and_values_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"preferences.json"
            for data in ([],{"schema":"wrong","version":1},
                         {"schema":"bpnhs-player","version":1,"collision_radius":False},
                         {"schema":"bpnhs-player","version":2}):
                with patch.object(Path,"read_text",return_value=json.dumps(data)),patch.object(Path,"exists",return_value=True):
                    with self.assertRaises(ValueError):load_player_settings(path)


class PlayerCollisionUITests(unittest.TestCase):
    def setUp(self):
        update=patch.object(ft.Control,"update");update.start();self.addCleanup(update.stop)
        settings=patch("navigation.app.load_player_settings",return_value=PlayerSettings())
        settings.start();self.addCleanup(settings.stop)
        editor=patch("map.workspace_editor.load_player_settings",return_value=PlayerSettings())
        editor.start();self.addCleanup(editor.stop)
        self.scene=MapScene();self.app=EvacuationApp(page_stub(),self.scene)

    def assert_centered(self,preview,center,radius):
        self.assertAlmostEqual(preview.left+preview.width/2,center[0])
        self.assertAlmostEqual(preview.top+preview.height/2,center[1])
        self.assertEqual((preview.width,preview.height),(2*radius,2*radius))

    def test_select_resize_move_deselect_preview_and_dot_are_independent(self):
        app=self.app;original=self.scene.snapshot();position=app._marker_center()
        self.assertFalse(app.collision_preview.visible);self.assertFalse(app.player_controls.control.visible)
        app.marker.on_click(None)
        self.assertTrue(app.collision_preview.visible);self.assertTrue(app.player_controls.control.visible)
        app.player_controls.resize_radius(event(8))
        self.assertEqual(app.state.collision_radius,8);self.assertEqual(app.marker.width,20)
        self.assertEqual(app._marker_center(),position)
        self.assert_centered(app.collision_preview,position,8)
        app.resize_player(event(44))
        self.assertEqual(app.state.collision_radius,8);self.assertEqual(app.marker.width,44)
        app.state.move_mode=True;app.move_user(30,15)
        self.assert_centered(app.collision_preview,app._marker_center(),8)
        self.assertEqual(self.scene.snapshot(),original)
        app.deselect_player();self.assertFalse(app.collision_preview.visible)
        self.assertFalse(app.player_controls.control.visible)

    def test_radius_text_accepts_fractional_and_rejects_invalid_without_mutating(self):
        app=self.app;app.select_player()
        app.player_controls.resize_radius_field(event("6.25"))
        self.assertEqual(app.state.collision_radius,6.25)
        for value in ("abc","nan","0","101"):
            app.player_controls.resize_radius_field(event(value))
            self.assertEqual(app.state.collision_radius,6.25)
        self.assert_centered(app.collision_preview,app._marker_center(),6.25)

    def test_save_load_and_new_app_startup_use_same_preferences_without_map_writes(self):
        app=self.app;before=self.scene.snapshot()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"player.json";app.player_controls.path=path
            app.select_player();app.resize_player(event(36));app.player_controls.resize_radius(event(12))
            self.assertFalse(path.exists())
            app.player_controls.save()
            app.resize_player(event(20));app.player_controls.resize_radius(event(26))
            app.player_controls.load()
            self.assertEqual(app.player_settings(),PlayerSettings(36,12))
            self.assert_centered(app.collision_preview,app._marker_center(),12)
            with patch("navigation.app.load_player_settings",side_effect=lambda:load_player_settings(path)):
                restored=EvacuationApp(page_stub(),self.scene)
            self.assertEqual(restored.player_settings(),PlayerSettings(36,12))
            self.assertEqual(restored.marker.width,36)
        self.assertEqual(self.scene.snapshot(),before)

    def test_invalid_load_preserves_live_settings_and_startup_preserves_bad_file(self):
        app=self.app;app.select_player();app.player_controls.resize_radius(event(9))
        with patch("navigation.player_controls.load_player_settings",side_effect=ValueError("bad settings")):
            app.player_controls.load()
        self.assertEqual(app.state.collision_radius,9)
        self.assertIn("Could not load",app.player_controls.message.value)
        with patch("navigation.app.load_player_settings",side_effect=ValueError("bad settings")):
            restored=EvacuationApp(page_stub(),self.scene)
        self.assertEqual(restored.player_settings(),PlayerSettings())
        self.assertIn("could not load",restored.player_controls.message.value)

    def test_editor_test_walk_uses_and_saves_same_radius_with_locked_editing(self):
        editor=MapWorkspaceEditor(page_stub(),self.scene);editor.mount();editor.toggle_walk()
        editor.select_player()
        position=editor.player
        editor.player_controls.resize_radius(event(11))
        preview=editor.scene_stack.controls[-2];marker=editor.scene_stack.controls[-1]
        self.assert_centered(preview,position,11)
        self.assertEqual(marker.width,20);self.assertTrue(editor.sidebar.disabled)
        editor.move_player(25,15);editor.refresh()
        self.assert_centered(editor.scene_stack.controls[-2],editor.player,11)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"player.json";editor.player_controls.path=path
            editor.player_controls.save();self.assertEqual(load_player_settings(path).collision_radius,11)
        editor.toggle_walk();self.assertFalse(editor.player_controls.control.visible)
        self.assertFalse(editor.select_player_button.visible)

    def test_editor_projected_barriers_are_cached_and_rebuilt_only_for_geometry_change(self):
        editor=MapWorkspaceEditor(page_stub(),self.scene)
        rail=DraftItem("railing",300,0,0,800)
        editor.items().append(rail)
        first=editor.player_barriers()
        editor.apply_player_preferences(PlayerSettings(20,8))
        self.assertIs(editor.player_barriers(),first)
        editor.items()[0]=replace(rail,x=400)
        self.assertIsNot(editor.player_barriers(),first)

    def test_demo_handoff_preserves_unsaved_player_preferences_both_directions(self):
        from map.demo_preview import EditorDemoPreview
        editor=MapWorkspaceEditor(page_stub(),self.scene);editor.mount()
        editor.apply_player_preferences(PlayerSettings(28,6))
        previews=[]
        def create(*args,**kwargs):
            result=EditorDemoPreview(*args,**kwargs);previews.append(result);return result
        with patch("map.demo_preview.EditorDemoPreview",side_effect=create):editor.run_demo()
        preview=previews[0]
        self.assertEqual(preview.player_settings(),PlayerSettings(28,6))
        preview.apply_player_settings(PlayerSettings(40,15));preview.return_to_editor()
        self.assertEqual(editor.player_preferences,PlayerSettings(40,15))
        self.assertTrue(editor.active)

    def test_real_protocol_serializes_selected_preview_and_live_resize(self):
        import msgpack
        from flet.controls.object_patch import ObjectPatch
        from flet.messaging.protocol import configure_encode_object_for_msgpack
        app=self.app;root=app.page.add.call_args.args[0]
        encode=configure_encode_object_for_msgpack(ft.Control)
        def serialize(control,previous=None):
            delta=ObjectPatch.from_diff(previous,control,control_cls=ft.Control)[0]
            return msgpack.packb(delta.to_message(),default=encode)
        self.assertTrue(serialize(root))
        app.select_player();app.player_controls.resize_radius(event(35))
        self.assertTrue(serialize(app.collision_preview,app.collision_preview))
        self.assertTrue(serialize(app.player_controls.control,app.player_controls.control))


class WorldRadiusTests(unittest.TestCase):
    def test_small_and_large_radius_change_wall_clearance_immediately_and_map_bounds(self):
        scene=MapScene();scene.floors[CAMPUS]=[DraftItem("wall",100,0,0,500,stroke=4)]
        state=NavigationState(collision_radius=8);nav=WorldNavigator(scene,state)
        self.assertTrue(nav.allowed((85,200)))
        state.collision_radius=20;self.assertFalse(nav.allowed((85,200)))
        self.assertEqual(nav.move((60,200),-100,0)[0],20)

    def test_door_clearance_world_radius_is_constant_across_scaled_and_rotated_buildings(self):
        for rotation in (0,35,90):
            parent=DraftItem("building",300,300,718,375.5,floor_count=2,rotation=rotation)
            scene=MapScene();scope=scope_key(parent,"Floor 1")
            scene.floors[CAMPUS]=[parent]
            scene.floors[scope]=[DraftItem("wall",100,200,400,0,stroke=4),
                DraftItem("opening",260,190,80,20)]
            point=scene.project(scope,300,200)
            state=NavigationState(collision_radius=10);nav=WorldNavigator(scene,state)
            nav.enter(parent);self.assertTrue(nav.allowed(point))
            state.collision_radius=26;self.assertFalse(nav.allowed(point))
            self.assertTrue(nav.allowed(scene.project(scope,300,100)))

    def test_nonuniform_wall_projection_uses_actual_world_clearance(self):
        parent=DraftItem("building",200,200,718,751)
        scene=MapScene();scope=scope_key(parent,"Floor 1")
        scene.floors[CAMPUS]=[parent];scene.floors[scope]=[DraftItem("wall",100,200,400,0,stroke=4)]
        state=NavigationState(collision_radius=8);nav=WorldNavigator(scene,state);nav.enter(parent)
        x,y=scene.project(scope,300,200)
        self.assertTrue(nav.allowed((x,y-11)));self.assertFalse(nav.allowed((x,y-9)))
        state.collision_radius=12;self.assertFalse(nav.allowed((x,y-11)))

    def test_minimum_radius_does_not_tunnel_through_thin_walls(self):
        scene=MapScene();scene.floors[CAMPUS]=[DraftItem("wall",100,0,0,500,stroke=1)]
        nav=WorldNavigator(scene,NavigationState(collision_radius=1))
        self.assertLess(nav.move((50,200),400,0)[0],100)

    def test_nonuniform_mirrored_railing_projection_retains_collision_at_caps_and_sides(self):
        parent=DraftItem("building",300,300,718,751,rotation=35,mirrored=True)
        scene=MapScene();scope=scope_key(parent,"Floor 1")
        scene.floors[CAMPUS]=[parent];scene.floors[scope]=[DraftItem("railing",200,200,300,0,collision_thickness=12)]
        state=NavigationState(collision_radius=4);nav=WorldNavigator(scene,state);nav.enter(parent)
        self.assertFalse(nav.allowed(scene.project(scope,350,200)))
        self.assertFalse(nav.allowed(scene.project(scope,200,200)))
        self.assertTrue(nav.allowed(scene.project(scope,350,220)))

    def test_radius_change_updates_collision_on_both_floors_mid_transition(self):
        from navigation.world import FloorTravel
        parent=DraftItem("building",0,0,1436,751,floor_count=2)
        stair=DraftItem("stairs",150,100,100,200)
        scene=MapScene();scene.floors[CAMPUS]=[parent]
        scene.floors[scope_key(parent,"Floor 1")]=[stair]
        scene.floors[scope_key(parent,"Floor 2")]=[DraftItem("wall",220,100,0,200,stroke=4)]
        state=NavigationState(collision_radius=8);nav=WorldNavigator(scene,state);nav.enter(parent)
        nav.travel=FloorTravel(nav.candidates()[0],1,2,.5)
        self.assertTrue(nav.allowed((200,200)))
        state.collision_radius=20;self.assertFalse(nav.allowed((200,200)))


if __name__=="__main__":unittest.main()
