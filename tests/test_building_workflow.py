"""Dedicated building sessions, selection bundles and direction-preserving stairs."""

import json
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import flet as ft
from drafting.models import DraftItem,primitives,validate_item
from map.scene import MapScene,CAMPUS,scope_key
from map.scene_store import save_scene,load_scene
from map.workspace_editor import MapWorkspaceEditor
from map.selection import clone_bundle
from navigation.collision import barriers_for
from navigation.stairs import indicators,section_progress,transitions,connection
from test_map_workspace import page_stub,pointer,keyboard


class BuildingWorkflowTests(unittest.TestCase):
    def setUp(self):
        patcher=patch.object(ft.Control,"update");patcher.start();self.addCleanup(patcher.stop)
        self.scene=MapScene()
        self.landmark=DraftItem("room",1800,100,200,200)
        self.scene.floors[CAMPUS]=[self.landmark]
        self.editor=MapWorkspaceEditor(page_stub(),self.scene)
        self.editor.mount()

    def builder(self):
        self.editor.choose_tool("building")
        return self.editor.builder

    def test_building_button_opens_floor_one_with_locked_map_reference(self):
        saved=self.scene.to_json()
        builder=self.builder()
        self.assertEqual(builder.page.title,"BPNHS Building Editor")
        self.assertTrue(builder.floor.endswith(":Floor 1"))
        self.assertTrue(builder.map_reference.ignore_interactions)
        self.assertEqual(builder.map_reference.opacity,.22)
        self.assertFalse(self.editor.active)
        self.assertEqual(self.scene.to_json(),saved)
        self.assertEqual(builder.document.dimensions(builder.floor),(self.scene.width,self.scene.height))
        builder.selection.select({self.landmark.id})
        self.assertFalse(builder.selection.ids)
        self.assertIsNone(builder.hit_item(pointer(1900,150)))
        builder.delete()
        self.assertIn(self.landmark,builder.document.floors[CAMPUS])

    def test_floor_done_advances_and_locks_completed_floors(self):
        builder=self.builder()
        first=DraftItem("wall",100,100,300,0)
        builder.items().append(first)
        builder.floor_done()
        self.assertTrue(builder.floor.endswith(":Floor 2"))
        self.assertEqual(builder.building().floor_count,2)
        self.assertEqual(builder.building().completed_floors,(1,))
        world=builder.document.project(builder.floor,200,100)
        self.assertIsNone(builder.hit_item(pointer(*world)))
        self.assertIn(first,builder.alignment_items())
        builder.floor_done()
        self.assertTrue(builder.floor.endswith(":Floor 3"))
        builder.change_scope(scope_key(builder.building(),"Floor 1"))
        self.assertIn(first,builder.editable_items())
        self.assertEqual(builder.floor_picker.value,builder.floor)

    def test_undo_floor_done_returns_to_valid_floor_not_footprint_mode(self):
        builder=self.builder()
        builder.floor_done()
        builder.history(False)
        self.assertTrue(builder.floor.endswith(":Floor 1"))
        self.assertEqual(builder.building().floor_count,1)

    def test_removing_floor_renumbers_connections_and_undo_restores_contents(self):
        builder=self.builder();builder.floor_done();builder.floor_done()
        parent=builder.building()
        stair=DraftItem("stairs",100,100,80,160,stair_direction="down",stair_to=1)
        builder.items().append(stair)
        builder.change_scope(scope_key(parent,"Floor 2"))
        before=builder.document.snapshot()
        with patch.object(builder,"confirm",side_effect=lambda text,action:action()): builder.remove_floor()
        self.assertEqual(builder.building().floor_count,2)
        self.assertEqual(builder.document.floors[scope_key(parent,"Floor 2")][0].stair_to,1)
        builder.history(False)
        self.assertEqual(builder.document.snapshot(),before)

    def test_bulk_edit_buttons_and_shortcuts_do_not_modify_during_test_walk(self):
        self.scene.floors[CAMPUS]=[]
        a=DraftItem("rectangle",100,100,80,80)
        b=DraftItem("stairs",220,100,80,160)
        self.editor.items().extend([a,b]);self.editor.selection.select({a.id,b.id})
        self.editor.selection.copy()
        saved=self.scene.snapshot()
        self.editor.toggle_walk()
        self.editor.selection.group();self.editor.selection.paste();self.editor.selection.delete()
        self.assertEqual(self.scene.snapshot(),saved)

    def test_floor_picker_opens_dedicated_workspace_for_existing_building(self):
        parent=DraftItem("building",500,100,500,300,floor_count=2)
        self.scene.floors[CAMPUS].append(parent)
        from types import SimpleNamespace
        scope=scope_key(parent,"Floor 2")
        self.editor.change_floor(SimpleNamespace(control=SimpleNamespace(value=scope)))
        self.assertTrue(self.editor.builder.building_session)
        self.assertEqual(self.editor.builder.floor,scope)

    def test_commit_saves_complete_building_and_can_undo_as_one_operation(self):
        builder=self.builder()
        parent=builder.building()
        room=DraftItem("room",100,100,500,300)
        builder.items().append(room)
        builder.floor_done()
        stair=DraftItem("stairs",600,100,100,200,stair_direction="down",stair_to=1)
        builder.items().append(stair)
        before=self.scene.snapshot()
        with patch("map.building_editor.save_scene") as save:
            builder.commit()
        save.assert_called_once()
        self.assertTrue(builder.closed)
        self.assertTrue(self.editor.active)
        self.assertEqual(self.scene.floors[scope_key(parent,"Floor 1")],[room])
        self.assertEqual(self.scene.floors[scope_key(parent,"Floor 2")],[stair])
        self.assertEqual(len(self.scene.buildings()),1)
        self.assertEqual(self.scene.floors[CAMPUS][0],self.landmark)
        self.editor.history(False)
        self.assertEqual(self.scene.snapshot(),before)

    def test_edit_existing_building_updates_identity_without_duplicate(self):
        builder=self.builder()
        self.assertEqual(builder.commit_button.content,"Add Building to Map")
        room=DraftItem("room",100,100,300,200)
        builder.items().append(room)
        with patch("map.building_editor.save_scene"): builder.commit()
        parent=self.scene.buildings()[0]
        self.editor.open_building_editor(parent)
        builder=self.editor.builder
        self.assertEqual(builder.commit_button.content,"Save Building Changes")
        builder.items().append(DraftItem("stairs",100,100,100,200))
        with patch("map.building_editor.save_scene"): builder.commit()
        self.assertEqual(len(self.scene.buildings()),1)
        self.assertEqual(self.scene.buildings()[0].id,parent.id)
        self.assertEqual(len(self.scene.floors[scope_key(parent,"Floor 1")]),2)

    def test_edit_this_building_appears_for_one_completed_free_building_only(self):
        builder=self.builder();builder.items().append(DraftItem("room",100,100,300,200))
        with patch("map.building_editor.save_scene"):builder.commit()
        parent=self.scene.buildings()[0]
        self.editor.deselect();self.assertFalse(self.editor.building_actions.visible)
        self.editor.tap(pointer(250,180))
        self.assertEqual(self.editor.selected_item().id,parent.id)
        self.assertTrue(self.editor.building_actions.visible)
        self.assertEqual(self.editor.selected_building_name.value,f"Building Name: {parent.text}")
        self.editor.selection.select({parent.id,self.landmark.id},False);self.editor.refresh(properties=True)
        self.assertFalse(self.editor.building_actions.visible)
        self.editor.selection.select({self.landmark.id},False);self.editor.refresh(properties=True)
        self.assertFalse(self.editor.building_actions.visible)
        image=DraftItem("building",600,100,500,300,layer_style="academic",floor_count=4)
        self.editor.items().append(image);self.editor.selection.select({image.id},False);self.editor.refresh(properties=True)
        self.assertFalse(self.editor.building_actions.visible)
        self.editor.selection.select({parent.id},False);self.editor.refresh(properties=True)
        self.editor.edit_building_button.on_click(None)
        self.assertEqual(self.editor.builder.building_id,parent.id)
        self.assertFalse(self.editor.builder.building_actions.visible)

    def test_saved_building_reopens_all_layers_and_updates_only_original_after_reload(self):
        parent=DraftItem("building",500,350,700,500,floor_width=700,floor_height=500,
            free_build=True,floor_count=2,completed_floors=(1,2),rotation=35,mirrored=True,text="Main Building")
        room=DraftItem("room",100,100,300,200,group_id="room-group")
        door=DraftItem("door",200,40,100,60,parent_id=room.id,group_id="room-group")
        stair=DraftItem("double_stairs",500,100,120,220,stair_to=2)
        down=DraftItem("stairs",500,100,120,220,stair_direction="down",stair_to=1)
        rail=DraftItem("railing",100,400,400,0,stroke=14)
        lower=[room,door,stair,DraftItem("window",350,100,80,40),rail]
        upper=[DraftItem("wall",100,100,300,0),down,DraftItem("opening",200,80,100,40)]
        roof=[DraftItem("roof",100,100,500,300)]
        self.scene.floors.update({CAMPUS:[self.landmark,parent],scope_key(parent,"Floor 1"):lower,
            scope_key(parent,"Floor 2"):upper,scope_key(parent,"Roof"):roof})
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"map.json";save_scene(self.scene,path)
            owner=MapWorkspaceEditor(page_stub(),load_scene(path));owner.mount()
            before=owner.document.snapshot()
            owner.tap(pointer(*parent.local_to_world(350,250)));owner.edit_building_button.on_click(None)
            editor=owner.builder
            self.assertTrue(editor.editing_existing)
            self.assertEqual(editor.commit_button.content,"Save Building Changes")
            self.assertEqual(editor.document.snapshot(),before)
            self.assertEqual(editor.building().completed_floors,(1,2))
            self.assertIn(editor.vector_cache[rail.id][1],editor.scene_stack.controls)
            self.assertIn(editor.vector_cache[self.landmark.id][1],editor.map_reference.content.controls)
            editor.selection.select({self.landmark.id});self.assertFalse(editor.selection.ids)
            editor.change_scope(scope_key(parent,"Floor 2"));self.assertEqual(editor.items(),upper)
            editor.selection.select({upper[0].id},False);editor.nudge(20,0)
            changed=editor.items()[0]
            expected_point=editor.document.project(editor.floor,changed.x,changed.y)
            with patch("map.building_editor.save_scene",side_effect=lambda scene:save_scene(scene,path)):editor.commit()
            saved=load_scene(path)
            self.assertEqual(len(saved.buildings()),1);updated=saved.buildings()[0]
            self.assertEqual(updated.id,parent.id);self.assertEqual(updated.text,parent.text)
            self.assertEqual((updated.rotation,updated.mirrored),(parent.rotation,parent.mirrored))
            self.assertEqual(saved.floors[CAMPUS][0],self.landmark)
            self.assertEqual(saved.floors[scope_key(updated,"Floor 1")],lower)
            self.assertEqual(saved.floors[scope_key(updated,"Roof")],roof)
            for actual,expected in zip(saved.project(scope_key(updated,"Floor 2"),changed.x,changed.y),expected_point):
                self.assertAlmostEqual(actual,expected)
            self.assertEqual(barriers_for(saved.floors[scope_key(updated,"Floor 1")]),barriers_for(lower))
            self.assertTrue(owner.active);self.assertTrue(owner.building_actions.visible)

    def test_cancel_existing_edit_keep_or_discard_preserves_original(self):
        builder=self.builder();room=DraftItem("room",100,100,300,200);builder.items().append(room)
        with patch("map.building_editor.save_scene"):builder.commit()
        before=self.scene.snapshot();self.editor.edit_this_building();builder=self.editor.builder
        builder.selection.select({room.id},False);builder.nudge(10,0)
        with patch("map.building_editor.save_scene") as save:
            builder.cancel();dialog=builder.page.show_dialog.call_args.args[0]
            self.assertEqual(dialog.title.value,"Discard changes to this building?")
            self.assertEqual([c.content for c in dialog.actions],["Keep Editing","Discard Changes"])
            dialog.actions[0].on_click(None);self.assertTrue(builder.active);self.assertFalse(builder.dialog_open)
            builder.cancel();dialog=builder.page.show_dialog.call_args.args[0];dialog.actions[1].on_click(None)
            self.assertTrue(builder.closed);self.assertTrue(self.editor.active);save.assert_not_called()
        self.assertEqual(self.scene.snapshot(),before)

    def test_cancel_after_undoing_all_edits_needs_no_discard_prompt(self):
        builder=self.builder();room=DraftItem("room",100,100,300,200);builder.items().append(room)
        with patch("map.building_editor.save_scene"):builder.commit()
        self.editor.edit_this_building();builder=self.editor.builder
        builder.selection.select({room.id},False);builder.nudge(10,0);builder.history(False)
        builder.page.show_dialog.reset_mock();builder.cancel()
        builder.page.show_dialog.assert_not_called();self.assertTrue(builder.closed)

    def test_cancel_discards_session_without_touching_original_map(self):
        before=self.scene.snapshot()
        builder=self.builder()
        builder.items().append(DraftItem("wall",100,100,400,0))
        builder.close()
        self.assertEqual(self.scene.snapshot(),before)
        self.assertTrue(self.editor.active)

    def test_failed_save_keeps_session_and_owner_map_intact(self):
        before=self.scene.snapshot()
        builder=self.builder()
        builder.items().append(DraftItem("room",100,100,300,200))
        with patch("map.building_editor.save_scene",side_effect=OSError("Unavailable")): builder.commit()
        self.assertFalse(builder.closed)
        self.assertEqual(self.scene.snapshot(),before)
        self.assertIn("not saved",builder.status.value)

    def test_group_room_click_moves_attached_door_and_collision_together(self):
        self.scene.floors[CAMPUS]=[]
        room=DraftItem("room",100,100,400,300,stroke=6)
        door=DraftItem("door",250,40,100,60,parent_id=room.id)
        railing=DraftItem("railing",120,150,200,0,parent_id=room.id)
        self.editor.items().extend([room,door,railing])
        self.editor.selection.select({door.id});self.editor.selection.select_structure()
        self.editor.pointer_down(pointer(300,70))
        self.editor.pointer_move(pointer(400,170))
        self.editor.pointer_up()
        self.assertEqual(len(self.editor.selection.items()),3)
        moved={i.id:i for i in self.editor.items()}
        self.assertEqual((moved[door.id].x,moved[door.id].y),(350,140))
        self.assertEqual((moved[room.id].x,moved[room.id].y),(200,200))
        self.assertFalse(any(b.blocks(400,200,0) for b in barriers_for(self.editor.items())))
        self.assertEqual(len(self.scene.undo_stack),1)
        self.editor.history(False)
        self.assertEqual(self.editor.items(),[room,door,railing])

    def test_box_selection_group_duplicate_copy_paste_delete_and_undo(self):
        self.scene.floors[CAMPUS]=[]
        a=DraftItem("rectangle",100,100,80,60)
        b=DraftItem("stairs",220,100,80,160)
        self.editor.items().extend([a,b])
        self.editor.pointer_down(pointer(80,80))
        self.editor.pointer_move(pointer(320,280))
        self.editor.pointer_up()
        self.assertEqual(self.editor.selection.ids,{a.id,b.id})
        self.editor.selection.group()
        self.assertEqual(len({i.group_id for i in self.editor.items()}),1)
        self.editor.deselect()
        self.editor.tap(pointer(140,130))
        self.assertEqual(len(self.editor.selection.items()),2)
        self.editor.duplicate()
        copies=self.editor.selection.items()
        self.assertEqual(len(copies),2)
        self.assertEqual(copies[1].x-copies[0].x,b.x-a.x)
        self.assertNotEqual(copies[0].group_id,self.editor.items()[0].group_id)
        self.editor.selection.copy()
        self.editor.selection.paste()
        self.assertEqual(len(self.editor.items()),6)
        self.editor.delete()
        self.assertEqual(len(self.editor.items()),4)
        self.editor.history(False)
        self.assertEqual(len(self.editor.items()),6)
        self.editor.selection.group(True)
        self.assertTrue(all(i.group_id is None for i in self.editor.selection.items()))

    def test_ghost_floor_never_enters_box_selection(self):
        builder=self.builder()
        lower=DraftItem("room",100,100,300,200)
        builder.items().append(lower)
        builder.floor_done()
        start=builder.document.project(builder.floor,50,50)
        end=builder.document.project(builder.floor,500,400)
        builder.pointer_down(pointer(*start));builder.pointer_move(pointer(*end));builder.pointer_up()
        self.assertFalse(builder.selection.items())

    def test_bundle_cloning_remaps_all_parent_group_and_building_layer_ids(self):
        parent=DraftItem("building",100,100,500,300,floor_count=2,opens="scene:original")
        room=DraftItem("room",100,100,400,300,group_id="classroom",parent_id=parent.id)
        door=DraftItem("door",200,40,80,60,parent_id=room.id,group_id="classroom")
        roots,floors=clone_bundle([parent],{scope_key(parent,"Floor 1"):[room,door]})
        clone=roots[0]
        room2,door2=floors[scope_key(clone,"Floor 1")]
        self.assertEqual(room2.parent_id,clone.id)
        self.assertEqual(door2.parent_id,room2.id)
        self.assertEqual(room2.group_id,door2.group_id)
        self.assertNotEqual(room2.group_id,room.group_id)

    def test_stair_shadow_direction_and_rotated_progress(self):
        up=DraftItem("stairs",100,100,80,160)
        down=replace(up,stair_direction="down")
        up_fills=[p["fill"] for p in primitives(up) if p.get("fill") not in (None,"none","#FFFFFF")]
        down_fills=[p["fill"] for p in primitives(down) if p.get("fill") not in (None,"none","#FFFFFF")]
        self.assertEqual(up_fills,list(reversed(down_fills)))
        self.assertEqual(barriers_for([up]),barriers_for([down]))
        for angle in (0,90,180,270):
            item=replace(up,rotation=angle)
            p,inside,_=section_progress(transitions(item,1,4)[0],item.local_to_world(40,80))
            self.assertAlmostEqual(p,.5)
            self.assertTrue(inside)
        double=replace(up,kind="double_stairs",width=120)
        self.assertEqual([arrow[2] for arrow in indicators(double)],["UP","DOWN"])
        self.assertEqual(connection(up,0,1,4),2)
        self.assertEqual(connection(down,0,3,4),2)
        self.assertIsNone(connection(down,0,1,4))

    def test_new_metadata_roundtrips_and_invalid_relationships_are_rejected(self):
        parent=DraftItem("building",100,100,500,300,floor_count=2,completed_floors=(1,))
        room=DraftItem("room",100,100,400,300)
        stair=DraftItem("stairs",100,100,80,160,parent_id=room.id,stair_to=2,group_id="room-parts")
        self.scene.floors[CAMPUS].append(parent)
        self.scene.floors[scope_key(parent,"Floor 1")]=[room,stair]
        self.assertEqual(MapScene.from_json(self.scene.to_json()).snapshot(),self.scene.snapshot())
        self.scene.floors[scope_key(parent,"Floor 1")][1]=replace(stair,parent_id="missing")
        with self.assertRaises(ValueError): MapScene.from_json(self.scene.to_json())
        self.scene.floors[scope_key(parent,"Floor 1")][1]=replace(stair,stair_to=3)
        with self.assertRaises(ValueError): MapScene.from_json(self.scene.to_json())


if __name__=="__main__": unittest.main()
