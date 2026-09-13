"""Shared-scene, integrated-editor and real movement-controller regressions."""

import asyncio
from dataclasses import replace
import json
import math
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import flet as ft
from drafting.models import DraftDocument,DraftItem,primitives
from map.campus import PlacedBuilding
from map_fixtures import EXAMPLE_PLACEMENTS as BUILDINGS_ON_MAP
from map.scene import CAMPUS,MapScene,scope_key,to_placement
from map.scene_store import load_scene,save_scene
from map.scene_renderer import render_scene,world_handles,item_shapes
from map.workspace_editor import MapWorkspaceEditor
from navigation.app import EvacuationApp
from navigation.collision import barriers_for,move_with_collisions,find_free_position
from navigation.data import MARKER_SIZE,DEFAULT_PLAYER_SIZE
from player_fixtures import isolate_player_settings


def pointer(x,y):
    return SimpleNamespace(local_position=SimpleNamespace(x=x,y=y))


def keyboard(key):
    return SimpleNamespace(key=key,ctrl=True,meta=False,shift=False,alt=False)


def page_stub():
    return SimpleNamespace(width=1400,height=900,update=Mock(),add=Mock(),clean=Mock(),
        run_task=Mock(),show_dialog=Mock(),pop_dialog=Mock(),overlay=[],on_keyboard_event=None)


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        isolate_player_settings(self)
        patcher=patch.object(ft.Control,"update")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.page=page_stub()

    def editor(self,scene=None):
        editor=MapWorkspaceEditor(self.page,MapScene() if scene is None else scene)
        editor.mount()
        return editor

    def parent(self):
        return DraftItem("building",200,100,320,200,text="School",fill="#FFDDAA",floor_count=4,opens="school")

    def scene_with_parent(self):
        scene=MapScene()
        parent=self.parent()
        scene.floors[CAMPUS].append(parent)
        return scene,parent

    def test_existing_asset_placements_keep_positions_and_assets_on_load(self):
        scene=MapScene(BUILDINGS_ON_MAP)
        self.assertEqual([to_placement(i) for i in scene.buildings()],BUILDINGS_ON_MAP)
        self.assertEqual(MapScene.from_json(scene.to_json()).snapshot(),scene.snapshot())

    def test_building_local_projection_roundtrips_rotation_resize_and_mirror(self):
        scene,parent=self.scene_with_parent()
        scope=scope_key(parent,"Floor 2")
        for angle in (0,30,90,270):
            for mirror in (False,True):
                scene.floors[CAMPUS]=[replace(parent,rotation=angle,mirrored=mirror,width=450,height=130)]
                world=scene.project(scope,600,300)
                local=scene.unproject(scope,*world)
                self.assertAlmostEqual(local[0],600)
                self.assertAlmostEqual(local[1],300)

    def test_many_building_floor_layers_save_without_old_draft_limit(self):
        scene=MapScene(BUILDINGS_ON_MAP)
        for parent in scene.buildings():
            for layer in scene.layers(parent): scene.floors[scope_key(parent,layer)]=[]
        self.assertGreater(len(scene.floors),20)
        self.assertEqual(MapScene.from_json(scene.to_json()).snapshot(),scene.snapshot())

    def test_scene_rejects_unsafe_assets_unknown_layers_and_invalid_collision_flags(self):
        scene,parent=self.scene_with_parent()
        raw=json.loads(scene.to_json())
        for source in ("../secret.png","C:/secret.png","/secret.png"):
            changed=json.loads(scene.to_json())
            changed["floors"][CAMPUS][0]["image_src"]=source
            with self.assertRaises(ValueError): MapScene.from_json(json.dumps(changed))
        raw["floors"]["unknown:Floor 1"]=[]
        with self.assertRaises(ValueError): MapScene.from_json(json.dumps(raw))
        raw=json.loads(scene.to_json())
        raw["floors"][CAMPUS][0]["blocking"]="true"
        with self.assertRaises(ValueError): MapScene.from_json(json.dumps(raw))

    def test_explicit_save_load_and_failed_save_preserve_last_good_scene(self):
        scene,parent=self.scene_with_parent()
        scene.floors[scope_key(parent,"Floor 1")]=[DraftItem("railing",100,200,300,0,stroke=10)]
        with tempfile.TemporaryDirectory(prefix="bpnhs-scene-test-") as directory:
            path=Path(directory)/"map.json"
            save_scene(scene,path)
            data=path.read_bytes()
            self.assertEqual(load_scene(path).snapshot(),scene.snapshot())
            scene.floors["invalid:Floor 1"]=[]
            with self.assertRaises(ValueError): save_scene(scene,path)
            self.assertEqual(path.read_bytes(),data)

    def test_unified_editor_mounts_without_drafting_window_or_add_to_map(self):
        editor=self.editor()
        self.assertEqual(self.page.overlay,[])
        self.assertEqual(editor.floor,CAMPUS)
        self.assertIn("building",editor.tool_buttons)
        self.assertIn("railing",editor.tool_buttons)
        labels=[str(c.content) for row in editor.control.controls if isinstance(row,ft.Row)
                for c in row.controls if isinstance(c,ft.Button)]
        self.assertNotIn("Add to map",labels)
        self.assertNotIn("Draft building",labels)
        self.assertIn("Save map",labels)

    def test_railing_can_draw_move_resize_rotate_duplicate_delete_and_undo(self):
        editor=self.editor()
        editor.choose_tool("railing")
        editor.pointer_down(pointer(100,150))
        editor.pointer_move(pointer(400,150))
        editor.pointer_up()
        railing=editor.items()[0]
        self.assertEqual((railing.kind,railing.width,railing.height),("railing",300,0))
        self.assertTrue(railing.blocking)
        self.assertEqual(editor.tool,"select")
        rotate=world_handles(railing)["rotate"]
        self.assertAlmostEqual(math.hypot(rotate[0]-250,rotate[1]-150),36)
        editor.pointer_down(pointer(150,150))
        editor.pointer_move(pointer(180,180))
        editor.pointer_up()
        moved=editor.items()[0]
        self.assertEqual((moved.x,moved.y),(130,180))
        editor.pointer_down(pointer(430,180))
        editor.pointer_move(pointer(530,180))
        editor.pointer_up()
        self.assertEqual(editor.items()[0].width,400)
        editor.rotate()
        self.assertEqual(editor.items()[0].rotation,90)
        self.page.on_keyboard_event(keyboard("d"))
        self.assertEqual(len(editor.items()),2)
        editor.delete()
        self.assertEqual(len(editor.items()),1)
        self.page.on_keyboard_event(keyboard("z"))
        self.assertEqual(len(editor.items()),2)
        self.page.on_keyboard_event(keyboard("y"))
        self.assertEqual(len(editor.items()),1)

    def test_railing_length_and_blocking_properties_are_editable(self):
        editor=self.editor()
        editor.choose_tool("railing")
        editor.tap(pointer(100,150))
        editor.length.value="350"
        editor.blocks.value=False
        editor.apply_properties()
        rail=editor.items()[0]
        self.assertAlmostEqual(math.hypot(rail.width,rail.height),350)
        self.assertFalse(rail.blocking)
        self.assertEqual(barriers_for(editor.items()),[])

    def test_floor_drawing_uses_map_pointer_and_attaches_to_parent(self):
        scene,parent=self.scene_with_parent()
        editor=self.editor(scene)
        scope=scope_key(parent,"Floor 2")
        editor.change_scope(scope)
        editor.choose_tool("railing")
        start=scene.project(scope,100,100)
        end=scene.project(scope,500,100)
        editor.pointer_down(pointer(*start))
        editor.pointer_move(pointer(*end))
        editor.pointer_up()
        child=editor.items()[0]
        self.assertAlmostEqual(child.x,100)
        self.assertAlmostEqual(child.width,400)
        world_before=scene.project(scope,child.x,child.y)
        scene.floors[CAMPUS]=[replace(parent,x=500,y=300,rotation=90,width=600)]
        editor.refresh(properties=True)
        self.assertNotEqual(scene.project(scope,child.x,child.y),world_before)
        self.assertEqual(editor.items()[0],child)

    def test_building_duplication_and_deletion_include_its_floor_objects(self):
        scene,parent=self.scene_with_parent()
        scope=scope_key(parent,"Floor 1")
        child=DraftItem("railing",100,100,300,0,stroke=10)
        scene.floors[scope]=[child]
        editor=self.editor(scene)
        editor.selected=parent.id
        editor.refresh(properties=True)
        editor.duplicate()
        clone=editor.selected_item()
        clone_scope=scope_key(clone,"Floor 1")
        self.assertEqual(scene.floors[clone_scope][0].width,300)
        self.assertNotEqual(scene.floors[clone_scope][0].id,child.id)
        editor.delete()
        self.assertNotIn(clone_scope,scene.floors)
        editor.history(False)
        self.assertIn(clone_scope,scene.floors)
        editor.history(False)
        self.assertNotIn(clone_scope,scene.floors)
        self.assertIn(scope,scene.floors)

    def test_import_draft_stays_editable_and_undo_removes_whole_import(self):
        editor=self.editor()
        draft=DraftDocument()
        draft.floors["Floor 1"]=[DraftItem("room",100,100,300,200,fill="#FFFFFF"),
                                  DraftItem("railing",100,350,300,0,stroke=10)]
        draft.floors["Roof"]=[DraftItem("roof",100,100,300,200,fill="#C66A41")]
        editor.import_document(draft)
        self.assertEqual(len(editor.document.buildings()),1)
        parent=editor.document.buildings()[0]
        self.assertEqual(parent.floor_count,4)
        self.assertEqual([i.kind for i in editor.items()],["room","railing"])
        self.assertEqual(editor.document.floors[scope_key(parent,"Roof")][0].kind,"roof")
        editor.history(False)
        self.assertEqual(editor.document.buildings(),[])
        self.assertEqual(editor.floor,CAMPUS)

    def test_renderer_reuses_unchanged_building_controls_and_shows_collision_bounds(self):
        scene,parent=self.scene_with_parent()
        rail=DraftItem("railing",100,200,300,0,stroke=10)
        scene.floors[CAMPUS].append(rail)
        images,vectors={},{}
        render_scene(scene,image_cache=images,vector_cache=vectors,collisions=True)
        control=images[parent.id][1]
        render_scene(scene,image_cache=images,vector_cache=vectors,collisions=True)
        self.assertIs(images[parent.id][1],control)
        self.assertGreater(len(item_shapes(rail,collisions=True)),len(item_shapes(rail)))

    def test_test_walk_blocks_player_and_disables_editing_until_finished(self):
        scene=MapScene()
        scene.floors[CAMPUS]=[DraftItem("railing",300,0,0,800,stroke=10)]
        editor=self.editor(scene)
        editor.player=(200,200)
        self.assertFalse(editor.joystick_control.visible)
        editor.toggle_walk()
        self.assertTrue(editor.move_mode)
        self.assertTrue(editor.joystick_control.visible)
        self.assertTrue(editor.floor_picker.disabled)
        editor.move_player(300,0)
        self.assertLess(editor.player[0],300)
        editor.toggle_walk()
        self.assertFalse(editor.joystick_control.visible)
        self.assertFalse(editor.floor_picker.disabled)
        self.assertFalse(editor.move_mode)

    def test_floor_test_walk_dot_keeps_size_and_tracks_projected_player_center(self):
        scene,parent=self.scene_with_parent()
        parent=replace(parent,rotation=30)
        scene.floors[CAMPUS]=[parent]
        editor=self.editor(scene)
        editor.change_scope(scope_key(parent,"Floor 1"))
        editor.toggle_walk()
        marker=editor.scene_stack.controls[-1]
        self.assertAlmostEqual(marker.width,DEFAULT_PLAYER_SIZE)
        self.assertAlmostEqual(marker.height,DEFAULT_PLAYER_SIZE)
        center=scene.project(editor.floor,*editor.player)
        self.assertAlmostEqual(marker.left+marker.width/2,center[0])
        self.assertAlmostEqual(marker.top+marker.height/2,center[1])
        self.assertIsNone(marker.rotate)

    def test_pan_tool_keeps_drawing_gestures_disabled_after_test_walk(self):
        editor=self.editor()
        editor.choose_tool("pan")
        editor.toggle_walk()
        editor.toggle_walk()
        self.assertTrue(editor.viewer.pan_enabled)
        self.assertIsNone(editor.gesture.on_pan_down)
        self.assertIsNone(editor.gesture.on_tap_up)

    def test_no_selection_clears_and_disables_properties(self):
        editor=self.editor()
        rail=DraftItem("railing",100,100,200,0)
        editor.items().append(rail)
        editor.selected=rail.id
        editor.refresh(properties=True)
        self.assertFalse(editor.properties["width"].disabled)
        editor.selected=None
        editor.refresh(properties=True)
        self.assertTrue(editor.properties["width"].disabled)
        self.assertEqual(editor.properties["width"].value,"")

    def test_navigation_demo_uses_unsaved_campus_collisions(self):
        scene=MapScene()
        scene.floors[CAMPUS]=[DraftItem("railing",300,0,0,800,stroke=10)]
        app=EvacuationApp(self.page,scene=scene)
        app.state.marker_x=200-MARKER_SIZE/2
        app.state.marker_y=200-MARKER_SIZE/2
        app.state.move_mode=True
        app.move_user(600,0)
        self.assertLess(app._marker_center()[0],300)

    def test_navigation_demo_uses_floor_specific_barriers_not_other_floors(self):
        scene,parent=self.scene_with_parent()
        scene.floors[scope_key(parent,"Floor 1")]=[DraftItem("railing",300,0,0,751,stroke=10)]
        app=EvacuationApp(self.page,scene=scene)
        app.enter_building("school")
        app.state.move_mode=True
        app.state.marker_x=200-MARKER_SIZE/2
        app.state.marker_y=200-MARKER_SIZE/2
        app.move_user(500,0)
        self.assertLess(app._marker_center()[0],300)
        app.state.floor=2
        app.move_user(100,0)
        self.assertGreater(app._marker_center()[0],300)

    def test_navigation_spawn_is_not_trapped_by_new_campus_or_floor_barriers(self):
        scene,parent=self.scene_with_parent()
        campus_rail=DraftItem("railing",1536,0,0,800,stroke=10)
        floor_rail=DraftItem("railing",0,685,1436,0,stroke=10)
        scene.floors[CAMPUS].append(campus_rail)
        scene.floors[scope_key(parent,"Floor 1")]=[floor_rail]
        app=EvacuationApp(self.page,scene=scene)
        self.assertFalse(barriers_for([campus_rail])[0].blocks(*app._marker_center(),26))
        app.enter_building("school")
        self.assertFalse(barriers_for([floor_rail])[0].blocks(*app._marker_center(),26))

    def test_rotated_building_entry_is_not_an_unrotated_rectangle(self):
        scene,parent=self.scene_with_parent()
        parent=replace(parent,rotation=90)
        scene.floors[CAMPUS]=[parent]
        app=EvacuationApp(self.page,scene=scene)
        app.state.move_mode=True
        app.state.marker_x=150-MARKER_SIZE/2
        app.state.marker_y=200-MARKER_SIZE/2
        self.assertTrue(app.move_user(0,0))
        self.assertEqual(app.state.building_name,"school")


class CollisionTests(unittest.TestCase):
    def test_horizontal_vertical_and_rotated_railings_cannot_be_crossed(self):
        for rail,start,delta in (
            (DraftItem("railing",0,300,1000,0,stroke=10),(500,100),(0,600)),
            (DraftItem("railing",300,0,0,1000,stroke=10),(100,500),(600,0)),
            (DraftItem("railing",500,100,800,0,rotation=90,stroke=10),(100,500),(800,0)),
        ):
            with self.subTest(rail=rail):
                barriers=barriers_for([rail])
                moved=move_with_collisions(*start,*delta,26,barriers,1000,1000)
                self.assertFalse(barriers[0].blocks(*moved,26))
                self.assertLess(moved[1],300) if rail.height==0 and rail.rotation==0 else self.assertLess(moved[0],rail.x)

    def test_wall_uses_same_collision_solver_and_nonblocking_rail_does_not_block(self):
        wall=DraftItem("wall",300,0,0,800,stroke=8)
        self.assertLess(move_with_collisions(200,200,600,0,26,barriers_for([wall]),1000,1000)[0],300)
        rail=replace(wall,kind="railing",blocking=False)
        self.assertEqual(move_with_collisions(200,200,600,0,26,barriers_for([rail]),1000,1000),(800,200))

    def test_parallel_movement_slides_along_barrier(self):
        rail=DraftItem("railing",300,0,0,1000,stroke=10)
        x,y=move_with_collisions(250,200,100,200,26,barriers_for([rail]),1000,1000)
        self.assertLess(x,300)
        self.assertGreater(y,350)

    def test_collision_is_local_to_segment_and_player_can_walk_around_ends(self):
        rail=DraftItem("railing",300,300,0,100,stroke=10)
        x,y=move_with_collisions(200,200,500,0,26,barriers_for([rail]),1000,1000)
        self.assertEqual((x,y),(700,200))

    def test_spawn_moves_out_of_new_barrier(self):
        rail=DraftItem("railing",300,0,0,1000,stroke=10)
        barriers=barriers_for([rail])
        spawn=find_free_position(300,300,26,barriers,1000,1000)
        self.assertIsNotNone(spawn)
        self.assertFalse(barriers[0].blocks(*spawn,26))


if __name__=="__main__": unittest.main()
