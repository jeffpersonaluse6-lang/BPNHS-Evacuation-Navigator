"""Precision positioning through the real map workspace keyboard handler."""

from dataclasses import replace
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import flet as ft
from drafting.models import DraftItem
from editor_shortcuts import EditorShortcuts,nudge_shortcut
from map.scene import CAMPUS,MapScene,scope_key
from map.workspace_editor import MapWorkspaceEditor
from navigation.collision import barriers_for
from test_map_workspace import page_stub,pointer


def key(label,ctrl=False,shift=False,alt=False,meta=False):
    return SimpleNamespace(key=label,ctrl=ctrl,shift=shift,alt=alt,meta=meta)


class KeyboardNudgeTests(unittest.TestCase):
    def setUp(self):
        patcher=patch.object(ft.Control,"update")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.page=page_stub()
        self.editor=MapWorkspaceEditor(self.page,MapScene())
        self.editor.mount()

    def select(self,item):
        self.editor.items().append(item)
        self.editor.selected=item.id
        self.editor.refresh(properties=True)

    def press(self,label,**modifiers):
        self.page.on_keyboard_event(key(label,**modifiers))

    def test_arrow_labels_and_modifier_mapping(self):
        for label in ("Arrow Left","ArrowLeft","Left","left arrow"):
            self.assertEqual(nudge_shortcut(key(label)),(-1,0))
        self.assertEqual(nudge_shortcut(key("Arrow Up",shift=True)),(0,-10))
        self.assertEqual(nudge_shortcut(key("ArrowRight",ctrl=True)),(.1,0))
        self.assertEqual(nudge_shortcut(key("Down",ctrl=True,shift=True)),(0,.1))
        self.assertIsNone(nudge_shortcut(key("Arrow Left",alt=True)))
        self.assertIsNone(nudge_shortcut(key("Arrow Left",meta=True)))
        self.assertIsNone(nudge_shortcut(key("a")))

    def test_four_arrow_directions_move_only_the_selected_object(self):
        room=DraftItem("room",100,150,200,100,rotation=35)
        other=DraftItem("roof",400,300,300,100)
        self.editor.items().append(other)
        self.select(room)
        for label,expected in (("Arrow Right",(101,150)),("Arrow Down",(101,151)),
                               ("Arrow Left",(100,151)),("Arrow Up",(100,150))):
            self.press(label)
            moved=self.editor.selected_item()
            self.assertEqual((moved.x,moved.y),expected)
            self.assertEqual(moved,replace(room,x=expected[0],y=expected[1]))
            self.assertEqual(self.editor.items()[0],other)
        self.assertEqual(len(self.editor.document.undo_stack),4)

    def test_shift_fast_ctrl_fine_and_grid_snapping_does_not_override_precision(self):
        self.select(DraftItem("room",100,100,200,100))
        self.editor.snap.value=True
        self.editor.spacing.value="50"
        self.press("Right")
        self.press("Down",shift=True)
        self.press("Left",ctrl=True)
        moved=self.editor.selected_item()
        self.assertAlmostEqual(moved.x,100.9)
        self.assertAlmostEqual(moved.y,110)
        self.assertAlmostEqual(float(self.editor.properties["x"].value),100.9)
        self.assertTrue(self.editor.document.dirty)

    def test_rooms_walls_railings_stairs_roofs_and_doors_can_all_be_nudged(self):
        for kind in ("room","wall","railing","stairs","roof","door","opening","text"):
            with self.subTest(kind=kind):
                item=DraftItem(kind,100,100,120,-30 if kind in {"wall","railing"} else 80,rotation=25)
                self.select(item)
                self.press("Up",shift=True)
                self.assertEqual(self.editor.selected_item(),replace(item,y=90))

    def test_whole_building_movement_carries_its_floor_and_roof_objects(self):
        parent=DraftItem("building",300,200,400,200,opens="test",floor_count=2,rotation=30)
        self.select(parent)
        child=DraftItem("room",100,100,300,200)
        scope=scope_key(parent,"Floor 1")
        roof_scope=scope_key(parent,"Roof")
        roof=DraftItem("roof",100,100,300,200)
        self.editor.document.floors[scope]=[child]
        self.editor.document.floors[roof_scope]=[roof]
        before=self.editor.document.project(scope,child.x,child.y)
        self.press("Right",shift=True)
        after=self.editor.document.project(scope,child.x,child.y)
        self.assertAlmostEqual(after[0]-before[0],10)
        self.assertAlmostEqual(after[1]-before[1],0)
        self.assertEqual(self.editor.document.floors[scope],[child])
        self.assertEqual(self.editor.document.floors[roof_scope],[roof])

    def test_floor_arrows_follow_map_axes_under_parent_rotation_mirroring_and_stretch(self):
        for angle in (0,30,90,270):
            for mirrored in (False,True):
                parent=DraftItem("building",500,300,600,120,rotation=angle,mirrored=mirrored)
                self.editor.document.floors[CAMPUS]=[parent]
                scope=scope_key(parent,"Floor 1")
                child=DraftItem("room",100,120,300,200,rotation=15)
                self.editor.document.floors[scope]=[child]
                self.editor.change_scope(scope)
                self.editor.selected=child.id
                for label,axis,sign in (("Right",0,1),("Left",0,-1),("Up",1,-1),("Down",1,1)):
                    before_item=self.editor.selected_item()
                    before=self.editor.document.project(scope,before_item.x,before_item.y)
                    self.press(label)
                    after_item=self.editor.selected_item()
                    after=self.editor.document.project(scope,after_item.x,after_item.y)
                    self.assertGreater((after[axis]-before[axis])*sign,0)
                    self.assertAlmostEqual(after[1-axis]-before[1-axis],0)
                    self.assertAlmostEqual(math.hypot(after_item.x-before_item.x,after_item.y-before_item.y),1)
                    self.assertEqual(after_item.rotation,child.rotation)

    def test_nudges_support_undo_redo_and_new_move_clears_redo(self):
        item=DraftItem("room",100,100,200,100)
        self.select(item)
        self.press("Right")
        self.press("z",ctrl=True)
        self.assertEqual(self.editor.selected_item(),item)
        self.press("y",ctrl=True)
        self.assertEqual(self.editor.selected_item(),replace(item,x=101))
        self.press("z",ctrl=True)
        self.press("Down")
        self.assertEqual(self.editor.selected_item(),replace(item,y=101))
        self.assertFalse(self.editor.document.redo_stack)
        self.assertEqual(MapScene.from_json(self.editor.document.to_json()).snapshot(),self.editor.document.snapshot())

    def test_property_text_focus_keeps_arrows_for_caret_navigation(self):
        item=DraftItem("room",100,100,200,100)
        self.select(item)
        for field in (self.editor.name,self.editor.properties["x"],self.editor.length,self.editor.floor_count):
            field.on_focus(None)
            for modifiers in ({},{"ctrl":True},{"shift":True}):
                self.press("Right",**modifiers)
            self.assertEqual(self.editor.selected_item(),item)
            field.on_blur(None)
        self.press("Right")
        self.assertEqual(self.editor.selected_item(),replace(item,x=101))

    def test_no_selection_dialog_export_inactive_preview_or_test_walk_does_not_move_objects(self):
        self.press("Right")
        self.assertFalse(self.editor.document.undo_stack)
        item=DraftItem("room",100,100,200,100)
        self.select(item)
        for flag in ("dialog_open","exporting","move_mode"):
            setattr(self.editor,flag,True)
            self.press("Right")
            self.assertEqual(self.editor.selected_item(),item)
            setattr(self.editor,flag,False)
        self.editor.active=False
        self.press("Right")
        self.assertEqual(self.editor.selected_item(),item)
        self.editor.active=True
        self.editor.toggle_walk()
        self.press("Right")
        self.assertEqual(self.editor.selected_item(),item)
        self.editor.toggle_walk()
        self.press("Right")
        self.assertEqual(self.editor.selected_item(),replace(item,x=101))

    def test_arrows_do_not_interrupt_an_active_mouse_gesture(self):
        item=DraftItem("room",100,100,200,100)
        self.select(item)
        self.editor.pointer_down(pointer(200,150))
        self.press("Right")
        self.assertEqual(self.editor.selected_item(),item)
        self.assertFalse(self.editor.document.undo_stack)
        self.editor.pointer_up()
        self.press("Right")
        self.assertEqual(self.editor.selected_item(),replace(item,x=101))

    def test_door_nudge_updates_room_collision_and_its_cached_guides(self):
        room=DraftItem("room",100,100,400,300,stroke=6)
        door=DraftItem("door",250,40,80,60)
        self.editor.items().append(room)
        self.select(door)
        before=self.editor.vector_cache[room.id][0]
        self.assertFalse(any(b.blocks(255,100,0) for b in barriers_for(self.editor.items())))
        self.assertTrue(any(b.blocks(335,100,0) for b in barriers_for(self.editor.items())))
        self.press("Right",shift=True)
        self.assertTrue(any(b.blocks(255,100,0) for b in barriers_for(self.editor.items())))
        self.assertFalse(any(b.blocks(335,100,0) for b in barriers_for(self.editor.items())))
        self.assertNotEqual(self.editor.vector_cache[room.id][0],before)
        self.press("z",ctrl=True)
        self.assertFalse(any(b.blocks(255,100,0) for b in barriers_for(self.editor.items())))

    def test_coordinate_limits_fail_safely_without_corrupting_history(self):
        item=DraftItem("room",100000,100,200,100)
        self.select(item)
        self.press("Right")
        self.assertEqual(self.editor.selected_item(),item)
        self.assertFalse(self.editor.document.undo_stack)
        self.assertIn("Object not moved",self.editor.status.value)

    def test_other_shortcut_owners_do_not_receive_nudging_unless_opted_in(self):
        page=page_stub()
        undo,redo=Mock(),Mock()
        shortcuts=EditorShortcuts(page,undo,redo)
        shortcuts.install()
        page.on_keyboard_event(key("Arrow Right"))
        undo.assert_not_called()
        redo.assert_not_called()


if __name__=="__main__": unittest.main()
