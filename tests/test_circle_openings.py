"""Wall-owned entrances remain visible, walkable and attached through edits."""

from dataclasses import replace
import json
import math
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import flet as ft
from drafting.circular import CircleOpening,solid_arcs,wall_polygons
from drafting.models import DraftItem,DraftDocument,primitives,validate_item
from map.scene import MapScene,CAMPUS,scope_key
from map.scene_store import save_scene,load_scene
from map.workspace_editor import MapWorkspaceEditor
from map.scene_renderer import item_shapes
from map.flips import flip_items
from navigation.collision import barriers_for,move_with_collisions,PolygonBarrier,snap_opening_to_wall
from navigation.models import NavigationState
from navigation.world import WorldNavigator
from test_map_workspace import page_stub,pointer
from player_fixtures import isolate_player_settings


def event(value):return SimpleNamespace(control=SimpleNamespace(value=value))


class OwnedGapGeometryTests(unittest.TestCase):
    def wall(self,angle=0):
        return DraftItem("circle_wall",600,400,400,400,stroke=8,collision_thickness=20,
            circle_openings=(CircleOpening(angle,100),))

    def assert_passage(self,wall,angle):
        a=math.radians(angle);rx,ry=wall.width/2,wall.height/2
        start=wall.local_to_world(rx+rx*.7*math.cos(a),ry+ry*.7*math.sin(a))
        end=wall.local_to_world(rx+rx*1.4*math.cos(a),ry+ry*1.4*math.sin(a))
        moved=move_with_collisions(*start,end[0]-start[0],end[1]-start[1],10,barriers_for([wall]),3000,2000)
        for actual,expected in zip(moved,end):self.assertAlmostEqual(actual,expected,places=6)

    def test_closed_by_default_and_explicit_gaps_split_collision_into_arcs(self):
        closed=replace(self.wall(),circle_openings=())
        self.assertEqual(solid_arcs(closed),((0,2*math.pi),))
        self.assertTrue(any(b.blocks(1000,600,10) for b in barriers_for([closed])))
        wall=self.wall();self.assertNotEqual(solid_arcs(wall),solid_arcs(closed))
        self.assert_passage(wall,0)
        self.assertTrue(any(b.blocks(800,800,10) for b in barriers_for([wall])))
        self.assertFalse(any(b.blocks(800,600,10) for b in barriers_for([wall])))
        for polygon in wall_polygons(wall):self.assertFalse(PolygonBarrier(polygon).blocks(1000,600,5))

    def test_gaps_remain_attached_when_moved_resized_rotated_and_flipped(self):
        for angle in (0,45,90,180,270,359):
            for rotation in (0,37,90):
                for diameter in (300,600):
                    wall=replace(self.wall(angle),x=900,y=650,rotation=rotation,width=diameter,height=diameter)
                    for mirrored in (False,True):self.assert_passage(replace(wall,mirrored=mirrored),angle)
            original=self.wall(angle);flipped=flip_items([original])[original.id]
            self.assert_passage(flipped,angle)

    def test_multiple_overlap_and_wraparound_gaps_merge_without_phantom_wall_sections(self):
        wall=replace(self.wall(),circle_openings=(CircleOpening(359,100),CircleOpening(1,100),CircleOpening(180,100)))
        arcs=solid_arcs(wall)
        self.assertEqual(len(arcs),2);self.assertTrue(all(start<end for start,end in arcs))
        for angle in (0,180):self.assert_passage(wall,angle)
        self.assertTrue(any(b.blocks(800,800,10) for b in barriers_for([wall])))

    def test_collision_thickness_changes_never_restore_gap(self):
        wall=self.wall()
        for thickness in (4,12,40):
            changed=replace(wall,collision_thickness=thickness)
            self.assertEqual(solid_arcs(wall),solid_arcs(changed));self.assert_passage(changed,0)

    def test_owned_gaps_and_existing_tangent_door_objects_can_coexist(self):
        wall=self.wall();door=snap_opening_to_wall(DraftItem("door",0,0,100,60),[wall],(600,600))
        door=replace(door,parent_id=wall.id);barriers=barriers_for([wall,door])
        self.assertFalse(any(b.blocks(1000,600,5) for b in barriers))
        self.assertFalse(any(b.blocks(600,600,5) for b in barriers))
        self.assertTrue(any(b.blocks(800,800,5) for b in barriers))

    def test_model_validation_json_and_svg_preserve_gaps(self):
        doc=DraftDocument();scope=next(iter(doc.floors));wall=self.wall()
        doc.floors[scope]=[wall]
        self.assertEqual(DraftDocument.from_json(doc.to_json()).snapshot(),doc.snapshot())
        root=ET.fromstring(doc.svg(scope));self.assertGreater(len(root),0)
        self.assertTrue(all(p["closed"] is False for p in primitives(wall)))
        for gap in (CircleOpening(float("nan"),100),CircleOpening(360,100),CircleOpening(0,0),CircleOpening(True,100)):
            with self.assertRaises(ValueError):validate_item(replace(wall,circle_openings=(gap,)))
        with self.assertRaises(ValueError):validate_item(replace(wall,circle_openings=(wall.circle_openings[0],)*2))
        with self.assertRaises(ValueError):validate_item(replace(wall,kind="roof"))
        raw=json.loads(doc.to_json());raw["floors"][scope][0]["circle_openings"]=["invalid"]
        with self.assertRaises(ValueError):DraftDocument.from_json(json.dumps(raw))

    def test_runtime_player_walks_through_owned_gap_without_floor_change(self):
        scene=MapScene();wall=self.wall();scene.floors[CAMPUS]=[wall]
        nav=WorldNavigator(scene,NavigationState(collision_radius=10))
        result=nav.move((940,600),120,0)
        self.assertAlmostEqual(result[0],1060)
        self.assertEqual(nav.state.floor,1);self.assertIsNone(nav.transition)


class CircleOpeningEditorTests(unittest.TestCase):
    def setUp(self):
        isolate_player_settings(self)
        updater=patch.object(ft.Control,"update");updater.start();self.addCleanup(updater.stop)
        self.editor=MapWorkspaceEditor(page_stub(),MapScene())
        self.wall=self.editor.create_item("circle_wall",200,200,400,400)
        self.editor.items().append(self.wall);self.editor.selection.select({self.wall.id},False)
        self.editor.refresh(properties=True);self.controls=self.editor.structures.openings

    def test_add_edit_multiple_select_delete_and_undo(self):
        controls=self.controls;editor=self.editor
        self.assertTrue(controls.control.visible);self.assertEqual(editor.selected_item().circle_openings,())
        controls.width.value="100";controls.add()
        first=editor.selected_item().circle_openings[0]
        self.assertEqual((first.angle,first.width),(0,100))
        controls.angle.value="90";controls.width.value="120";controls.add()
        second=editor.selected_item().circle_openings[1]
        self.assertNotEqual(first.id,second.id)
        controls.select(event(first.id));controls.angle.value="270";controls.width.value="80";controls.apply()
        self.assertEqual(editor.selected_item().circle_openings[0],replace(first,angle=270,width=80))
        before=editor.document.snapshot();controls.delete()
        self.assertEqual(editor.selected_item().circle_openings,(second,))
        editor.history(False);self.assertEqual(editor.document.snapshot(),before)
        editor.history(True);self.assertEqual(editor.selected_item().circle_openings,(second,))

    def test_slider_preview_is_retained_updates_collision_guides_and_undoes_once(self):
        controls=self.controls;editor=self.editor;controls.add()
        before=editor.document.snapshot();undo_count=len(editor.document.undo_stack)
        controls.start()
        with patch("map.workspace_editor.render_scene",side_effect=AssertionError("full redraw")):
            for angle in (10,30,60,90):controls.change(event(angle))
        self.assertEqual(editor.selected_item().circle_openings[0].angle,90)
        self.assertEqual(len(editor.document.undo_stack),undo_count)
        controls.end(event(90));self.assertEqual(len(editor.document.undo_stack),undo_count+1)
        self.assertFalse(controls.active)
        self.assertFalse(any(b.blocks(400,600,5) for b in barriers_for(editor.items())))
        editor.history(False);self.assertEqual(editor.document.snapshot(),before)

    def test_cancel_angle_drag_restores_gap_and_does_not_break_next_drag(self):
        controls=self.controls;editor=self.editor;controls.add();before=editor.document.snapshot()
        controls.start();controls.change(event(90));editor.cancel_gesture()
        self.assertFalse(controls.active);self.assertEqual(editor.document.snapshot(),before)
        controls.start();controls.change(event(180));controls.end()
        self.assertEqual(editor.selected_item().circle_openings[0].angle,180)

    def test_resize_copy_cross_floor_paste_group_flip_save_load_and_delete_wall(self):
        self.editor.choose_tool("building");editor=self.editor.builder
        wall=editor.create_item("circle_wall",400,300,400,400)
        editor.items().append(wall);editor.selection.select({wall.id},False);editor.refresh(properties=True)
        controls=editor.structures.openings;controls.add();controls.angle.value="180";controls.add()
        editor.structures.radius.value="250";editor.structures.resize(True)
        original=editor.selected_item();editor.selection.copy();editor.floor_done();editor.selection.paste()
        copy=editor.selected_item()
        self.assertNotEqual(copy.id,original.id)
        self.assertEqual([(g.angle,g.width) for g in copy.circle_openings],[(g.angle,g.width) for g in original.circle_openings])
        self.assertTrue({g.id for g in copy.circle_openings}.isdisjoint(g.id for g in original.circle_openings))
        self.assertEqual((copy.x,copy.y),(original.x,original.y))
        extra=editor.create_item("railing",100,100,100,0);editor.items().append(extra)
        editor.selection.select({copy.id,extra.id});editor.selection.group();editor.selection.flip()
        before=editor.document.snapshot()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"gaps.json";save_scene(editor.document,path)
            self.assertEqual(load_scene(path).snapshot(),before)
        editor.selection.delete();self.assertEqual(editor.items(),[])
        editor.history(False);self.assertEqual(editor.document.snapshot(),before)

    def test_invalid_settings_do_not_change_wall_and_other_types_hide_controls(self):
        controls=self.controls;before=self.editor.document.snapshot()
        for width in ("0","-1","nan","inf"):
            controls.width.value=width;controls.add();self.assertEqual(self.editor.document.snapshot(),before)
        controls.width.value="80";controls.angle.value="nan";controls.add()
        self.assertEqual(self.editor.document.snapshot(),before)
        other=self.editor.create_item("gazebo_roof",100,100,300,300)
        self.editor.items().append(other);self.editor.selection.select({other.id},False);self.editor.refresh(properties=True)
        self.assertFalse(controls.control.visible)

    def test_deleting_all_gaps_closes_the_wall_again_and_controls_encode(self):
        controls=self.controls;controls.add();controls.delete()
        self.assertEqual(self.editor.selected_item().circle_openings,())
        self.assertTrue(any(b.blocks(600,400,5) for b in barriers_for(self.editor.items())))
        controls.add()
        import msgpack
        from flet.messaging.protocol import configure_encode_object_for_msgpack
        self.assertTrue(msgpack.packb(self.editor.control,default=configure_encode_object_for_msgpack(ft.Control)))


if __name__=="__main__":unittest.main()
