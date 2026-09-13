"""Manual grouping must not be inferred from proximity or attachment."""

from dataclasses import replace
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import flet as ft
from drafting.models import DraftItem,primitives,railing_profile
from map.scene import CAMPUS,MapScene,scope_key
from map.workspace_editor import MapWorkspaceEditor
from navigation.collision import barriers_for,barriers_for_item
from test_map_workspace import page_stub,pointer


class ManualGroupingTests(unittest.TestCase):
    def setUp(self):
        update=patch.object(ft.Control,"update");update.start();self.addCleanup(update.stop)
        self.scene=MapScene();self.editor=MapWorkspaceEditor(page_stub(),self.scene)
        self.room=DraftItem("room",100,100,400,300,stroke=6)
        self.door=DraftItem("door",180,40,100,60,parent_id=self.room.id)
        self.rail=DraftItem("railing",150,220,200,0,parent_id=self.room.id,rotation=10,stroke=10)
        self.editor.items().extend((self.room,self.door,self.rail));self.editor.refresh(properties=True)

    def test_ordinary_click_does_not_select_attached_structure_even_with_smart_enabled(self):
        self.editor.tap(pointer(230,70))
        self.assertEqual(self.editor.selection.ids,{self.door.id})
        self.assertTrue(all(i.group_id is None for i in self.editor.items()))

    def test_nearby_placed_symbols_keep_independent_group_data(self):
        for kind in ("wall","railing","door","stairs"):
            self.editor.choose_tool(kind)
            if kind=="wall":
                self.editor.pointer_down(pointer(150,150));self.editor.pointer_move(pointer(200,150));self.editor.pointer_up()
            else:self.editor.tap(pointer(200,180))
            placed=self.editor.items()[-1]
            self.assertIsNone(placed.group_id)
        self.assertTrue(all(i.group_id is None for i in self.editor.items()))

    def test_smart_selection_is_explicit_temporary_and_does_not_modify_data(self):
        before=self.scene.snapshot()
        self.editor.selection.select({self.door.id});self.editor.selection.select_structure()
        self.assertEqual(self.editor.selection.ids,{self.room.id,self.door.id,self.rail.id})
        self.assertEqual(self.scene.snapshot(),before)
        self.assertFalse(self.scene.undo_stack)

    def test_manual_group_does_not_include_unselected_attached_parts(self):
        self.editor.selection.select({self.room.id,self.door.id},False);self.editor.selection.group()
        self.editor.tap(pointer(230,70))
        self.assertEqual(self.editor.selection.ids,{self.room.id,self.door.id})
        self.assertIsNone(self.editor.items()[2].group_id)

    def test_partial_ungroup_removes_all_members_preserving_geometry_attachments_collision(self):
        self.editor.selection.select({self.room.id,self.door.id,self.rail.id},False);self.editor.selection.group()
        before=list(self.editor.items());collision=barriers_for(before)
        self.editor.selection.select({self.door.id},False);self.editor.selection.group(True)
        self.assertEqual(self.editor.items(),[replace(i,group_id=None) for i in before])
        self.assertEqual(barriers_for(self.editor.items()),collision)
        self.assertEqual(self.editor.selection.ids,{self.door.id})
        self.editor.tap(pointer(230,70));self.assertEqual(self.editor.selection.ids,{self.door.id})

    def test_ungroup_without_manual_group_preserves_attachment(self):
        before=list(self.editor.items())
        self.editor.selection.select({self.door.id});self.editor.selection.group(True)
        self.assertEqual(self.editor.items(),before)
        self.assertEqual(self.editor.items()[1].parent_id,self.room.id)
        self.assertFalse(self.scene.undo_stack)

    def test_group_ungroup_undo_redo(self):
        self.editor.selection.select({self.room.id,self.door.id},False);self.editor.selection.group()
        grouped=list(self.editor.items())
        self.editor.selection.group(True);ungrouped=list(self.editor.items())
        self.editor.history(False);self.assertEqual(self.editor.items(),grouped)
        self.editor.history(True);self.assertEqual(self.editor.items(),ungrouped)

    def test_ungroup_during_drag_commits_current_positions_instead_of_reverting_them(self):
        self.editor.selection.select({self.room.id,self.door.id,self.rail.id},False);self.editor.selection.group()
        self.editor.pointer_down(pointer(230,70));self.editor.pointer_move(pointer(300,150))
        current=list(self.editor.items());self.editor.selection.group(True)
        self.assertEqual(self.editor.items(),[replace(i,group_id=None) for i in current])
        self.assertIsNone(self.editor.interaction)

    def test_ungroup_stays_on_current_floor_and_leaves_other_floor_unchanged(self):
        self.editor.choose_tool("building");builder=self.editor.builder
        lower=replace(self.rail,group_id="floor-group")
        builder.items().append(lower);builder.floor_done()
        upper=[replace(self.room,group_id="floor-group"),replace(self.door,group_id="floor-group")]
        builder.items().extend(upper);builder.refresh(properties=True)
        scope=builder.floor;builder.selection.select({self.door.id},False);builder.selection.group(True)
        self.assertEqual(builder.floor,scope)
        self.assertEqual(builder.items(),[replace(i,group_id=None) for i in upper])
        self.assertEqual(builder.document.floors[scope_key(builder.building(),"Floor 1")],[lower])


class RailingThicknessTests(unittest.TestCase):
    def setUp(self):
        update=patch.object(ft.Control,"update");update.start();self.addCleanup(update.stop)
        self.scene=MapScene();self.editor=MapWorkspaceEditor(page_stub(),self.scene)
        self.rail=self.editor.create_item("railing",100,100,250,0)
        self.editor.items().append(self.rail);self.editor.selection.select({self.rail.id})
        self.editor.refresh(properties=True)

    def event(self,value):return SimpleNamespace(control=SimpleNamespace(value=value))

    def test_default_strokes_are_noticeably_thicker_and_within_collision_envelope(self):
        gap,rails,posts,radius=railing_profile(self.rail.stroke)
        shapes=primitives(self.rail)
        self.assertEqual(self.rail.stroke,10)
        self.assertGreaterEqual(shapes[0]["stroke"],4)
        self.assertGreaterEqual(shapes[2]["stroke"],5)
        self.assertGreaterEqual(radius,gap+1+posts/2)
        self.assertEqual(barriers_for_item(self.rail)[0].radius,radius)

    def test_slider_updates_only_selected_geometry_and_creates_one_undo_entry(self):
        canvas=self.editor.vector_cache[self.rail.id][1];original=canvas.shapes
        self.editor.railings.start()
        with patch("map.workspace_editor.render_scene",side_effect=AssertionError("Whole scene refreshed for thickness")):
            self.editor.railings.change(self.event(16));self.editor.railings.change(self.event(22))
        self.assertEqual(self.editor.selected_item().stroke,22)
        self.assertIsNot(canvas.shapes,original)
        self.assertFalse(self.scene.undo_stack)
        self.editor.railings.end(self.event(22))
        self.assertEqual(len(self.scene.undo_stack),1)
        # Visual strokes now change independently from the saved physical width.
        self.assertEqual(barriers_for_item(self.editor.items()[0])[0].radius,barriers_for_item(self.rail)[0].radius)
        self.editor.history(False);self.assertEqual(self.editor.items()[0],self.rail)
        self.editor.history(True);self.assertEqual(self.editor.items()[0].stroke,22)

    def test_thickness_cancel_restores_original_geometry_and_no_history(self):
        self.editor.railings.start();self.editor.railings.change(self.event(26));self.editor.cancel_gesture()
        self.assertFalse(self.editor.railings.active)
        self.assertEqual(self.editor.items()[0],self.rail)
        self.assertFalse(self.scene.undo_stack)

    def test_thickness_save_load_preserves_width_and_collision(self):
        self.editor.railings.start();self.editor.railings.change(self.event(30));self.editor.railings.end()
        restored=MapScene.from_json(self.scene.to_json())
        self.assertEqual(restored.snapshot(),self.scene.snapshot())
        self.assertEqual(barriers_for(restored.floors[CAMPUS]),barriers_for(self.editor.items()))

    def test_slider_ignores_multi_selection_and_focus_prevents_keyboard_nudge(self):
        other=DraftItem("wall",300,200,250,0);self.editor.items().append(other)
        self.editor.selection.select({self.rail.id,other.id},False);self.editor.refresh(properties=True)
        before=self.scene.snapshot();self.editor.railings.change(self.event(30))
        self.assertEqual(self.scene.snapshot(),before)
        self.assertTrue(self.editor.railings.slider.disabled)
        self.editor.railings.slider.on_focus(None);self.assertTrue(self.editor.shortcuts.text_focused)
        self.editor.railings.slider.on_blur(None);self.assertFalse(self.editor.shortcuts.text_focused)


if __name__=="__main__":unittest.main()
