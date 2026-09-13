"""Canvas sizing preserves authored geometry and stays editor-only."""

import asyncio
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import flet as ft
from drafting.models import DraftItem
from map.canvas_size import checked_map_size,content_extent
from map.scene import MapScene,CAMPUS,scope_key
from map.scene_store import load_scene,save_scene
from map.workspace_editor import MapWorkspaceEditor
from navigation.app import EvacuationApp
from navigation.data import MARKER_SIZE
from test_entry_points import ui_labels
from test_map_workspace import page_stub,pointer


class MapResizingTests(unittest.TestCase):
    def setUp(self):
        from player_fixtures import isolate_player_settings
        isolate_player_settings(self)
        update=patch.object(ft.Control,"update");update.start();self.addCleanup(update.stop)
        self.scene=MapScene()
        self.scene.width,self.scene.height=800,600
        self.room=DraftItem("room",100,100,200,180,stroke=2)
        self.scene.floors[CAMPUS]=[self.room]
        self.page=page_stub()
        self.editor=MapWorkspaceEditor(self.page,self.scene)
        self.editor.mount()

    def test_growing_keeps_all_objects_and_does_not_automatically_save(self):
        parent=DraftItem("building",400,100,200,100,floor_count=3)
        self.scene.floors[CAMPUS].append(parent)
        scope=scope_key(parent,"Floor 2")
        self.scene.floors[scope]=[DraftItem("stairs",100,100,80,160),
                                  DraftItem("railing",300,50,250,0)]
        floors=self.scene.snapshot()[3]
        with patch("map.workspace_editor.save_scene") as save:
            self.assertTrue(self.editor.resize_map("1600","900"))
            save.assert_not_called()
        self.assertEqual(self.scene.floors,floors)
        self.assertEqual((self.scene.width,self.scene.height),(1600,900))
        self.assertTrue(self.scene.dirty)
        self.assertEqual(len(self.scene.undo_stack),1)

    def test_cached_canvases_grid_and_input_bounds_resize_and_undo_redo(self):
        canvas=self.editor.vector_cache[self.room.id][1]
        original_shapes=canvas.shapes
        self.assertTrue(self.editor.resize_map(1200,750))
        self.assertIs(self.editor.vector_cache[self.room.id][1],canvas)
        self.assertIs(canvas.shapes,original_shapes)
        for control in (canvas,self.editor.canvas,self.editor.scene_stack,self.editor.gesture,
                        *self.editor.scene_stack.controls[:2]):
            self.assertEqual((control.width,control.height),(1200,750))
        self.assertEqual(self.editor.point(pointer(2000,2000),snap=False),(1200,750))
        self.editor.history(False)
        self.assertEqual((canvas.width,canvas.height),(800,600))
        self.assertEqual((self.editor.map_width.value,self.editor.map_height.value),("800","600"))
        self.editor.history(True)
        self.assertEqual((canvas.width,canvas.height),(1200,750))
        self.assertEqual((self.editor.map_width.value,self.editor.map_height.value),("1200","750"))

    def test_shrinking_empty_space_preserves_geometry(self):
        self.assertTrue(self.editor.resize_map(350,320))
        self.assertEqual(self.scene.floors[CAMPUS],[self.room])
        self.assertEqual((self.scene.width,self.scene.height),(350,320))

    def test_shrinking_across_wall_thickness_is_rejected_without_changes(self):
        before=self.scene.snapshot()
        self.assertFalse(self.editor.resize_map(300,280))
        self.assertIn("width at least 301",self.editor.status.value)
        self.assertIn("height at least 281",self.editor.status.value)
        self.assertEqual(self.scene.snapshot(),before)
        self.assertFalse(self.scene.undo_stack)

    def test_hidden_floor_objects_outside_the_parent_are_protected(self):
        parent=DraftItem("building",100,100,400,200,floor_count=3)
        self.scene.floors[CAMPUS]=[parent]
        scope=scope_key(parent,"Floor 3")
        child=DraftItem("room",1200,100,900,400)
        self.scene.floors[scope]=[child]
        right,bottom=content_extent(self.scene)
        self.assertGreater(right,680)
        self.assertFalse(self.editor.resize_map(600,600))
        self.assertEqual(self.scene.floors[scope],[child])
        self.assertTrue(self.editor.resize_map(750,600))

    def test_rotated_mirrored_and_negative_length_lines_have_real_extents(self):
        railing=DraftItem("railing",500,300,-200,0,rotation=90,mirrored=True,stroke=10)
        self.scene.floors[CAMPUS]=[railing]
        right,bottom=content_extent(self.scene)
        from drafting.models import railing_profile
        radius=railing_profile(railing.stroke)[3]
        self.assertAlmostEqual(right,500+radius)
        self.assertAlmostEqual(bottom,300+radius)
        self.assertFalse(self.editor.resize_map(506,306))
        self.assertTrue(self.editor.resize_map(510,510))

    def test_enlarging_does_not_reject_content_already_outside_the_old_canvas(self):
        self.scene.floors[CAMPUS]=[replace(self.room,y=800)]
        self.assertTrue(self.editor.resize_map(1000,600))
        self.assertEqual(self.scene.floors[CAMPUS][0].y,800)

    def test_invalid_dimensions_never_mutate_or_create_history(self):
        before=self.scene.snapshot()
        for value in ("",None,True,"abc","nan","inf","-inf",99,-100,5001):
            with self.subTest(value=value):
                self.assertFalse(self.editor.resize_map(value,600))
                self.assertFalse(self.editor.resize_map(800,value))
                self.assertEqual(self.scene.snapshot(),before)
        self.assertFalse(self.scene.undo_stack)

    def test_same_size_is_a_history_no_op_and_fractional_sizes_roundtrip(self):
        self.assertTrue(self.editor.resize_map("800","600"))
        self.assertFalse(self.scene.undo_stack)
        self.assertFalse(self.scene.dirty)
        self.assertTrue(self.editor.resize_map("850.5","625.25"))
        loaded=MapScene.from_json(self.scene.to_json())
        self.assertEqual((loaded.width,loaded.height),(850.5,625.25))

    def test_empty_map_supports_minimum_and_maximum_sizes(self):
        self.scene.floors[CAMPUS]=[]
        self.assertEqual(checked_map_size(self.scene,100,100),(100,100))
        self.assertTrue(self.editor.resize_map(5000,5000))
        self.assertTrue(self.editor.resize_map(100,100))

    def test_dialog_applies_valid_size_but_keeps_invalid_input_open(self):
        self.assertIn("Map size",ui_labels(self.editor.control))
        self.editor.map_size_settings()
        dialog=self.page.show_dialog.call_args.args[0]
        self.assertTrue(self.editor.dialog_open)
        self.editor.map_width.value="too small"
        dialog.actions[1].on_click(None)
        self.assertTrue(self.editor.dialog_open)
        self.assertTrue(dialog.content.controls[-1].visible)
        self.assertEqual(self.editor.map_width.value,"too small")
        self.editor.map_width.value="1000";self.editor.map_height.value="700"
        dialog.actions[1].on_click(None)
        self.assertFalse(self.editor.dialog_open)
        self.page.pop_dialog.assert_called_once()
        self.assertEqual((self.scene.width,self.scene.height),(1000,700))

    def test_dialog_cancel_and_dismiss_are_non_mutating(self):
        before=self.scene.snapshot()
        self.editor.map_size_settings()
        dialog=self.page.show_dialog.call_args.args[0]
        self.editor.map_width.value="2000"
        dialog.actions[0].on_click(None)
        self.assertFalse(self.editor.dialog_open)
        self.assertEqual(self.scene.snapshot(),before)
        self.editor.map_size_settings()
        self.assertEqual(self.editor.map_width.value,"800")
        self.page.show_dialog.call_args.args[0].on_dismiss(None)
        self.assertFalse(self.editor.dialog_open)

    def test_walk_inactive_and_building_sessions_cannot_resize_campus(self):
        before=self.scene.snapshot()
        self.editor.toggle_walk()
        self.assertTrue(self.editor.map_size_button.disabled)
        self.assertFalse(self.editor.resize_map(1000,700))
        self.editor.toggle_walk()
        self.editor.choose_tool("building")
        builder=self.editor.builder
        self.assertNotIn("Map size",ui_labels(builder.control))
        self.assertFalse(builder.resize_map(1000,700))
        self.assertFalse(self.editor.resize_map(1000,700))
        self.assertEqual(self.scene.snapshot(),before)

    def test_saved_dimensions_load_in_main_app_without_editor_controls(self):
        self.assertTrue(self.editor.resize_map(1600,900))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"map.json"
            save_scene(self.scene,path)
            scene=load_scene(path)
        app=EvacuationApp(page_stub(),scene=scene)
        self.assertEqual((app.world_view.control.width,app.world_view.control.height),(1600,900))
        self.assertNotIn("Map size",ui_labels(app.page.add.call_args.args[0]))
        x,y=app.navigator.move((1400,700),1000,1000)
        self.assertLessEqual(x,1600-MARKER_SIZE/2)
        self.assertLessEqual(y,900-MARKER_SIZE/2)

    def test_loading_another_size_updates_controls_and_editor_bounds(self):
        loaded=MapScene()
        loaded.width,loaded.height=2400,1400
        file=SimpleNamespace(bytes=loaded.to_json().encode("utf-8"))
        with patch.object(self.editor.picker,"pick_files",return_value=[file]):
            asyncio.run(self.editor.pick_map())
        self.assertEqual((self.editor.map_width.value,self.editor.map_height.value),("2400","1400"))
        self.assertEqual((self.editor.gesture.width,self.editor.gesture.height),(2400,1400))


if __name__=="__main__": unittest.main()
