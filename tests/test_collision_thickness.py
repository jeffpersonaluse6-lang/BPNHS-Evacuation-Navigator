"""Independent physical widths, doorway clearance, live previews and persistence."""

from dataclasses import replace
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import flet as ft
from drafting.models import DraftItem,primitives,validate_item
from map.scene import MapScene,CAMPUS,scope_key
from map.scene_renderer import item_shapes
from map.workspace_editor import MapWorkspaceEditor
from navigation.collision import barriers_for,barriers_for_item,wall_sections,move_with_collisions
from navigation.world import WorldNavigator
from navigation.models import NavigationState
from test_map_workspace import page_stub


def event(value):return SimpleNamespace(control=SimpleNamespace(value=value))


class PhysicalThicknessTests(unittest.TestCase):
    def test_collision_width_never_changes_visible_wall_geometry(self):
        thin=DraftItem("wall",100,200,400,0,stroke=4)
        thick=replace(thin,collision_thickness=12)
        self.assertEqual(primitives(thin),primitives(thick))
        self.assertEqual(wall_sections(thin),wall_sections(thick))
        self.assertEqual(barriers_for_item(thick)[0].radius,6)
        self.assertFalse(barriers_for_item(thin)[0].blocks(300,205,0))
        self.assertTrue(barriers_for_item(thick)[0].blocks(300,205,0))
        self.assertFalse(barriers_for_item(replace(thick,blocking=False)))

    def test_thick_collision_keeps_doorway_walkable_and_ignores_parallel_doors(self):
        wall=DraftItem("wall",100,200,400,0,stroke=4,collision_thickness=100)
        doorway=DraftItem("door",250,140,100,60)
        barriers=barriers_for([wall,doorway])
        self.assertEqual([b.radius for b in barriers],[50,50])
        self.assertEqual(move_with_collisions(300,100,0,200,26,barriers,1000,1000),(300,300))
        self.assertTrue(any(b.blocks(150,230,0) for b in barriers))
        unrelated=replace(doorway,y=160)
        self.assertEqual(len(barriers_for([wall,unrelated])),1)
        self.assertTrue(barriers_for([wall,unrelated])[0].blocks(300,200,0))

    def test_rotated_mirrored_room_blocks_perimeter_but_not_interior_or_opening(self):
        for angle in (0,35,90):
            room=DraftItem("room",400,300,300,200,stroke=4,collision_thickness=20,rotation=angle,mirrored=True)
            door=DraftItem("door",0,0,100,60,rotation=angle,mirrored=True)
            baseline=room.local_to_world(100,0)
            offset=door.local_to_world(0,60)
            door=replace(door,x=baseline[0]-offset[0],y=baseline[1]-offset[1])
            barriers=barriers_for([room,door])
            self.assertFalse(any(b.blocks(*room.local_to_world(150,100),0) for b in barriers))
            self.assertFalse(any(b.blocks(*room.local_to_world(150,0),0) for b in barriers))
            self.assertTrue(any(b.blocks(*room.local_to_world(30,8),0) for b in barriers))
            self.assertEqual(wall_sections(room,(door,)),wall_sections(replace(room,collision_thickness=2),(door,)))

    def test_stair_side_barriers_leave_treads_and_ends_walkable(self):
        for kind in ("stairs","double_stairs"):
            stair=DraftItem(kind,100,100,240,240,stroke=4)
            self.assertFalse(barriers_for_item(stair))
            barriers=barriers_for_item(replace(stair,collision_thickness=12))
            self.assertEqual(len(barriers),2 if kind=="stairs" else 3)
            self.assertTrue(any(b.blocks(100,220,0) for b in barriers))
            self.assertFalse(any(b.blocks(160,220,26) for b in barriers))
            self.assertFalse(any(b.blocks(160,100,26) for b in barriers))
            self.assertFalse(any(b.blocks(160,340,26) for b in barriers))

    def test_saved_width_changes_runtime_collision_and_legacy_json_keeps_defaults(self):
        scene=MapScene();wall=DraftItem("wall",100,300,400,0,stroke=4,collision_thickness=60)
        scene.floors[CAMPUS]=[wall]
        restored=MapScene.from_json(scene.to_json())
        self.assertFalse(WorldNavigator(restored,NavigationState()).allowed((250,350)))
        raw=json.loads(scene.to_json());raw["floors"][CAMPUS][0].pop("collision_thickness")
        legacy=MapScene.from_json(json.dumps(raw))
        self.assertIsNone(legacy.floors[CAMPUS][0].collision_thickness)
        self.assertTrue(WorldNavigator(legacy,NavigationState()).allowed((250,350)))
        for value in (0,-1,201,True,float("inf"),float("nan"),"12"):
            with self.subTest(value=value),self.assertRaises(ValueError):validate_item(replace(wall,collision_thickness=value))


class CollisionInspectorTests(unittest.TestCase):
    def setUp(self):
        update=patch.object(ft.Control,"update");update.start();self.addCleanup(update.stop)
        self.scene=MapScene();self.editor=MapWorkspaceEditor(page_stub(),self.scene)
        self.rail=self.editor.create_item("railing",100,100,300,0)
        self.other=DraftItem("room",600,100,300,200)
        self.editor.items().extend([self.rail,self.other]);self.editor.selection.select({self.rail.id},False)
        self.editor.refresh(properties=True);self.control=self.editor.collision_editor

    def test_slider_live_collision_preview_is_local_and_one_undo_entry(self):
        canvas=self.editor.vector_cache[self.rail.id][1]
        other=self.editor.vector_cache[self.other.id][1];other_shapes=other.shapes
        self.control.start()
        with patch("map.workspace_editor.render_scene",side_effect=AssertionError("Full scene while changing width")):
            self.control.change(event(40));self.control.change(event(12))
        changed=self.editor.selected_item()
        self.assertEqual(changed.stroke,self.rail.stroke);self.assertEqual(primitives(changed),primitives(self.rail))
        self.assertEqual(barriers_for_item(changed)[0].radius,6)
        # Last cyan outline is the newly sized physical boundary, not visual rails.
        self.assertAlmostEqual(canvas.shapes[-1].elements[0].y,106)
        self.assertIs(other.shapes,other_shapes);self.assertFalse(self.scene.undo_stack)
        self.control.end();self.assertEqual(len(self.scene.undo_stack),1)
        self.editor.history(False);self.assertEqual(self.editor.items()[0],self.rail)
        self.editor.history(True);self.assertEqual(self.editor.items()[0].collision_thickness,12)

    def test_typed_value_is_immediate_and_visual_edit_keeps_physical_width(self):
        self.control.type_value(event("12.5"))
        self.assertEqual(barriers_for_item(self.editor.items()[0])[0].radius,6.25)
        self.assertEqual(self.editor.items()[0].stroke,10)
        self.editor.railings.start();self.editor.railings.change(event(30));self.editor.railings.end()
        self.assertEqual(self.editor.items()[0].collision_thickness,12.5)
        before=self.scene.snapshot();self.control.type_value(event("-2"))
        self.assertEqual(self.scene.snapshot(),before);self.assertIsNotNone(self.control.field.error_text)

    def test_save_duplicate_and_building_floors_preserve_physical_width(self):
        self.control.type_value(event("12"));self.editor.duplicate()
        self.assertEqual(self.editor.selected_item().collision_thickness,12)
        saved=MapScene.from_json(self.scene.to_json());self.assertEqual(saved.snapshot(),self.scene.snapshot())
        self.editor.choose_tool("building");builder=self.editor.builder
        wall=builder.create_item("wall",100,100,300,0)
        builder.items().append(wall);builder.selection.select({wall.id},False);builder.refresh(properties=True)
        builder.collision_editor.type_value(event("20"));builder.floor_done();builder.copy_floor()
        self.assertEqual(builder.items()[0].collision_thickness,20)
        MapScene.from_json(builder.document.to_json())

    def test_cancel_width_gesture_and_locked_selection_do_not_change_collision(self):
        self.control.start();self.control.change(event(100));self.editor.cancel_gesture()
        self.assertFalse(self.control.active);self.assertEqual(self.editor.items()[0],self.rail)
        self.assertFalse(self.scene.undo_stack)
        self.editor.selection.select({self.rail.id,self.other.id},False);self.editor.refresh(properties=True)
        before=self.scene.snapshot();self.control.change(event(100));self.control.type_value(event("100"))
        self.assertEqual(self.scene.snapshot(),before);self.assertTrue(self.control.control.disabled)

    def test_explicit_stair_collision_checkbox_enables_sides_without_blocking_ends(self):
        stair=self.editor.create_item("stairs",100,400,240,240)
        self.editor.items().append(stair);self.editor.selection.select({stair.id},False);self.editor.refresh(properties=True)
        self.assertFalse(self.editor.blocks.value);self.assertFalse(barriers_for_item(stair))
        self.editor.blocks.value=True;self.editor.apply_properties()
        barriers=barriers_for_item(self.editor.selected_item())
        self.assertEqual(len(barriers),2)
        self.assertFalse(any(b.blocks(220,400,26) for b in barriers))


if __name__=="__main__":unittest.main()
