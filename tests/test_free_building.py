"""Whole-map tracing, reference isolation, exact coordinates and dynamic floors."""

import asyncio
from dataclasses import replace
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import flet as ft
import msgpack
from flet.messaging.protocol import configure_encode_object_for_msgpack
from drafting.models import DraftItem,primitives
from map.scene import MapScene,CAMPUS,scope_key
from map.workspace_editor import MapWorkspaceEditor
from map.free_build import fit_building,map_alignment_targets
from map.scene_renderer import render_scene,project,item_shapes
from map.alignment import snap_transform
from navigation.app import EvacuationApp
from navigation.collision import barriers_for
from navigation.models import NavigationState
from navigation.world import WorldNavigator
from test_entry_points import ui_labels
from test_map_workspace import page_stub,pointer


def event(value): return SimpleNamespace(control=SimpleNamespace(value=value))


def world_points(scene,scope,item):
    return [scene.project(scope,*item.local_to_world(*point))
        for primitive in primitives(item) for point in primitive.get("points",[])]


class FreeBuildingTests(unittest.TestCase):
    def setUp(self):
        from player_fixtures import isolate_player_settings
        isolate_player_settings(self)
        update=patch.object(ft.Control,"update");update.start();self.addCleanup(update.stop)
        self.scene=MapScene()
        self.path=DraftItem("rectangle",2100,700,500,80,fill="#CCCCCC",text="Pathway")
        self.other=DraftItem("building",100,100,400,300,floor_count=2,text="Other school building")
        self.other_room=DraftItem("room",200,200,300,200)
        self.scene.floors[CAMPUS]=[self.path,self.other]
        self.scene.floors[scope_key(self.other,"Floor 1")]=[self.other_room]
        self.owner=MapWorkspaceEditor(page_stub(),self.scene)
        self.owner.mount()
        self.original=self.scene.snapshot()
        self.owner.choose_tool("building")
        self.builder=self.owner.builder
        self.builder.snap.value=False

    def commit(self):
        with patch("map.building_editor.save_scene") as save: self.builder.commit()
        save.assert_called_once()
        return next(p for p in self.scene.buildings() if p.id==self.builder.building_id)

    def test_no_starting_box_outline_or_footprint_controls(self):
        b=self.builder
        labels=ui_labels(b.control)
        self.assertNotIn("Position / resize footprint",labels)
        self.assertNotIn("Building footprint",labels)
        self.assertNotIn(b.building_id,b.image_cache)
        self.assertFalse(b.canvas.shapes)
        self.assertEqual(b.document.dimensions(b.floor),(3000,1200))
        self.assertEqual((b.gesture.width,b.gesture.height),(3000,1200))
        self.assertEqual(b.editable_items(),[])
        self.assertEqual(self.scene.snapshot(),self.original)
        self.assertIsNone(b.hit_item(pointer(1500,600)))

    def test_draw_far_from_old_box_preserves_exact_map_coordinates_on_save(self):
        b=self.builder
        b.choose_tool("room")
        b.pointer_down(pointer(2400,850));b.pointer_move(pointer(2750,1070));b.pointer_up()
        room=b.items()[0]
        self.assertEqual((room.x,room.y,room.width,room.height),(2400,850,350,220))
        before=world_points(b.document,b.floor,room)
        parent=self.commit()
        scope=scope_key(parent,"Floor 1")
        self.assertEqual(self.scene.floors[scope],[room])
        self.assertEqual(world_points(self.scene,scope,room),before)
        self.assertEqual(project(parent,room.x,room.y),(2400,850))
        self.assertEqual((parent.x,parent.y,parent.width,parent.height),(2399,849,352,222))

    def test_real_map_stays_visible_faded_and_current_floor_is_not_faded(self):
        b=self.builder
        room=DraftItem("room",2100,800,300,200)
        b.items().append(room);b.refresh()
        self.assertEqual(b.map_reference.opacity,.22)
        self.assertTrue(b.map_reference.ignore_interactions)
        self.assertIn(b.vector_cache[self.path.id][1],b.map_reference.content.controls)
        self.assertIn(b.image_cache[self.other.id][1],b.map_reference.content.controls)
        self.assertIn(b.vector_cache[room.id][1],b.scene_stack.controls)
        self.assertNotIn(b.vector_cache[room.id][1],b.map_reference.content.controls)

    def test_reference_click_drag_handles_and_all_edit_actions_are_blocked(self):
        b=self.builder
        for target in (self.path,self.other,self.other_room):
            b.selection.select({target.id});self.assertFalse(b.selection.ids)
            b.selected=target.id
            b.apply_properties();b.rotate();b.nudge(10,0);b.delete();b.duplicate()
            b.selection.group();b.selection.copy();b.selection.paste()
            self.assertIsNone(b.selected_item())
        b.tap(pointer(2200,740))
        b.pointer_down(pointer(2100,700));b.pointer_move(pointer(2250,850));b.pointer_up()
        self.assertEqual(b.document.floors[CAMPUS][:2],[self.path,self.other])
        self.assertEqual(b.document.floors[scope_key(self.other,"Floor 1")],[self.other_room])
        self.assertEqual(self.scene.snapshot(),self.original)

    def test_scope_dropdown_and_direct_selection_cannot_unlock_map_objects(self):
        b=self.builder
        old=b.floor
        b.change_scope(CAMPUS);b.change_scope(scope_key(self.other,"Floor 1"))
        self.assertEqual(b.floor,old)
        b.select_object(event(self.path.id));self.assertIsNone(b.selected_item())
        b.floor=CAMPUS;b.selected=self.path.id
        self.assertEqual(b.selection.items(),[])
        b.apply_properties();b.delete();b.refresh()
        self.assertEqual(b.floor,old)
        with self.assertRaises(ValueError): b.update_parent(replace(self.other,x=2000))
        self.assertEqual(self.scene.snapshot(),self.original)

    def test_foreign_attachment_and_global_loading_importing_are_blocked(self):
        b=self.builder
        wall=DraftItem("wall",2100,800,300,0)
        b.items().append(wall);b.selection.select({wall.id})
        b.attach_selected(event(self.path.id))
        self.assertIsNone(b.items()[0].parent_id)
        asyncio.run(b.load_map());asyncio.run(b.pick_map());asyncio.run(b.import_draft())
        b.import_document(self.scene,self.other);b.edit_saved_draft();b.edit_building()
        with patch("map.workspace_editor.save_scene") as save: b.save_map()
        save.assert_not_called()
        self.assertEqual(self.scene.snapshot(),self.original)

    def test_box_select_group_duplicate_and_delete_affect_only_active_floor(self):
        b=self.builder
        lower=DraftItem("room",2100,800,300,200)
        b.items().append(lower);b.floor_done()
        wall=DraftItem("wall",2100,800,200,0)
        stairs=DraftItem("stairs",2350,800,80,160)
        b.items().extend([wall,stairs])
        b.pointer_down(pointer(0,0));b.pointer_move(pointer(3000,1200));b.pointer_up()
        self.assertEqual(b.selection.ids,{wall.id,stairs.id})
        b.selection.group();b.duplicate();b.selection.copy();b.selection.paste();b.delete()
        self.assertEqual(len(b.items()),4)
        self.assertEqual(b.document.floors[scope_key(b.building(),"Floor 1")],[lower])
        self.assertEqual(b.document.floors[CAMPUS][:2],[self.path,self.other])

    def test_previous_floor_copy_never_copies_the_campus(self):
        b=self.builder
        b.copy_floor();self.assertEqual(b.items(),[])
        room=DraftItem("room",2100,800,300,200,parent_id=b.building_id)
        door=DraftItem("door",2200,740,100,60,parent_id=room.id)
        b.items().extend([room,door]);b.floor_done();b.copy_floor()
        self.assertEqual(len(b.items()),2)
        self.assertNotEqual(b.items()[0].id,room.id)
        self.assertEqual(b.items()[1].parent_id,b.items()[0].id)
        self.assertEqual(b.items()[0].parent_id,b.building_id)

    def test_lower_floors_are_ghosted_and_locked_but_supply_alignment(self):
        b=self.builder
        lower=DraftItem("room",2100,800,300,200)
        b.items().append(lower);b.floor_done();b.floor_done()
        layers=b.references.layers(b.document,b.floor)
        self.assertEqual(len(layers),2)
        self.assertLess(layers[0][1],layers[1][1])
        self.assertIn(lower,b.alignment_items())
        self.assertIsNone(b.hit_item(pointer(2200,850)))
        b.selection.select({lower.id});self.assertFalse(b.selection.ids)
        current=DraftItem("rectangle",2103,950,300,40)
        snapped,guides=snap_transform((current.x,current.y),lambda p:replace(current,x=p[0],y=p[1]),
            b.alignment_items(),b.document.dimensions(b.floor),grid=0,equal=False)
        self.assertAlmostEqual(snapped.x,2100)
        self.assertTrue(guides)

    def test_underlying_pathway_alignment_uses_locked_proxies(self):
        b=self.builder
        targets=map_alignment_targets(b.document,b.building(),b.floor)
        self.assertTrue(any(t.id==f"reference:{self.path.id}" for t in targets))
        current=DraftItem("rectangle",2103,800,100,40)
        snapped,guides=snap_transform((2103,800),lambda p:replace(current,x=p[0],y=p[1]),
            targets,(3000,1200),grid=0,equal=False)
        self.assertAlmostEqual(snapped.x,2100)
        b.selection.select({t.id for t in targets});self.assertFalse(b.selection.ids)

    def test_bounds_include_all_floors_roof_and_railing_without_shifting(self):
        b=self.builder
        room=DraftItem("room",1600,400,400,300,stroke=6)
        door=DraftItem("door",1750,340,100,60,parent_id=room.id)
        b.items().extend([room,door]);b.floor_done()
        railing=DraftItem("railing",1500,800,700,0,stroke=10)
        b.items().append(railing)
        b.change_scope(scope_key(b.building(),"Roof"))
        roof=DraftItem("roof",1550,350,700,550,fill="#C66A41")
        b.items().append(roof)
        floor_data={key:list(items) for key,items in b.document.floors.items() if key.startswith(b.building_id+":")}
        parent=self.commit()
        self.assertTrue(parent.free_build)
        self.assertLessEqual(parent.x,1500)
        self.assertGreaterEqual(parent.x+parent.width,2250)
        for key,items in floor_data.items():
            self.assertEqual(self.scene.floors[key],items)
            for item in items:
                for point in item_corners_for_test(item):
                    self.assertEqual(self.scene.project(key,*point),point)

    def test_empty_build_cannot_commit_and_failed_save_is_atomic(self):
        b=self.builder
        with patch("map.building_editor.save_scene") as save: b.commit()
        save.assert_not_called();self.assertFalse(b.closed)
        self.assertIn("at least one",b.status.value)
        b.items().append(DraftItem("room",2100,800,300,200))
        with patch("map.building_editor.save_scene",side_effect=OSError("Unavailable")): b.commit()
        self.assertFalse(b.closed)
        self.assertEqual(self.scene.snapshot(),self.original)

    def test_add_then_reopen_expands_bounds_without_duplicates_or_position_drift(self):
        b=self.builder
        room=DraftItem("room",2100,800,300,200)
        b.items().append(room);parent=self.commit()
        before=world_points(self.scene,scope_key(parent,"Floor 1"),room)
        self.owner.open_building_editor(parent);b=self.owner.builder
        b.choose_tool("wall");b.snap.value=False;b.smart_snap.value=False
        b.pointer_down(pointer(900,600));b.pointer_move(pointer(1800,600));b.pointer_up()
        with patch("map.building_editor.save_scene"): b.commit()
        updated=next(p for p in self.scene.buildings() if p.id==parent.id)
        self.assertEqual(len(self.scene.buildings()),2)
        self.assertLess(updated.x,1000)
        self.assertEqual(world_points(self.scene,scope_key(updated,"Floor 1"),room),before)
        self.owner.history(False)
        restored=next(p for p in self.scene.buildings() if p.id==parent.id)
        self.assertEqual(restored,parent)

    def test_fitting_preserves_rotation_mirror_and_nonuniform_scale_for_legacy_builds(self):
        items=[DraftItem("room",900,200,400,300,rotation=30,stroke=6),
               DraftItem("railing",750,650,500,0,rotation=15)]
        for angle in (0,35,90,270):
            for mirrored in (False,True):
                with self.subTest(angle=angle,mirrored=mirrored):
                    parent=DraftItem("building",1200,400,600,150,rotation=angle,mirrored=mirrored)
                    scope=scope_key(parent,"Floor 1")
                    before=MapScene();before.floors[CAMPUS]=[parent];before.floors[scope]=items
                    fitted=fit_building(parent,{scope:items})
                    after=MapScene();after.floors[CAMPUS]=[fitted];after.floors[scope]=items
                    for item in items:
                        for a,c in zip(world_points(before,scope,item),world_points(after,scope,item)):
                            self.assertAlmostEqual(a[0],c[0]);self.assertAlmostEqual(a[1],c[1])

    def test_floor_count_goes_past_twelve_and_old_five_hundred_scope_cap(self):
        b=self.builder
        b.items().append(DraftItem("floor",2100,800,300,200,stroke=0,fill="#FFFFFF"))
        for _ in range(15): b.floor_done()
        self.assertEqual(b.building().floor_count,16)
        self.assertTrue(b.floor.endswith(":Floor 16"))
        b.items().append(DraftItem("stairs",2100,800,80,160,stair_direction="down",stair_to=15))
        parent=self.commit()
        loaded=MapScene.from_json(self.scene.to_json())
        self.assertEqual(loaded.buildings()[-1].floor_count,16)
        large=MapScene();large_parent=replace(parent,floor_count=520,completed_floors=())
        large.floors[CAMPUS]=[large_parent]
        for n in range(1,521): large.floors[scope_key(large_parent,f"Floor {n}")]=[]
        self.assertEqual(MapScene.from_json(large.to_json()).buildings()[0].floor_count,520)
        self.assertIsNotNone(WorldNavigator(large,NavigationState()))

    def test_malformed_huge_floor_counts_bad_frames_and_missing_layers_are_rejected(self):
        b=self.builder
        for changed in (replace(b.building(),floor_count=10**12),
                        replace(b.building(),floor_width=0),replace(b.building(),floor_origin_x=float("nan"))):
            raw=json.loads(b.document.to_json())
            from dataclasses import asdict
            raw["floors"][CAMPUS][-1]=asdict(changed)
            with self.assertRaises(ValueError): MapScene.from_json(json.dumps(raw))

    def test_actual_authored_objects_not_a_placeholder_display_on_campus_and_runtime(self):
        b=self.builder
        room=DraftItem("room",2100,800,300,200)
        b.items().append(room);parent=self.commit()
        images={};vectors={}
        render_scene(self.scene,image_cache=images,vector_cache=vectors)
        self.assertNotIn(parent.id,images)
        self.assertIn(room.id,vectors)
        app=EvacuationApp(page_stub(),scene=self.scene)
        self.assertNotIn("New building",ui_labels(app.world_view.control))
        self.assertFalse(app.world_view.layers[parent.id,1][0].content.controls[0].shapes)
        self.assertFalse(app.world_view.layers[parent.id,"Roof"][0].content.controls[0].shapes)

    def test_world_collisions_keep_doorways_walkable_after_bounds_are_fitted(self):
        b=self.builder
        room=DraftItem("room",1600,400,400,300,stroke=6)
        door=DraftItem("door",1750,340,100,60,parent_id=room.id)
        b.items().extend([room,door]);parent=self.commit()
        nav=WorldNavigator(self.scene,NavigationState())
        x,y=nav.move((1800,300),0,250)
        self.assertAlmostEqual(y,550)
        self.assertEqual(nav.parent.id,parent.id)
        x,y=nav.move((1700,500),600,0)
        self.assertLess(x,2000)
        self.assertEqual(barriers_for(self.scene.floors[scope_key(parent,"Floor 1")]),barriers_for([room,door]))

    def test_stair_floor_blending_stays_at_exact_world_position_after_save(self):
        b=self.builder
        up=DraftItem("stairs",2100,800,80,160)
        b.items().append(up);b.floor_done()
        b.items().append(replace(up,id="return-stairs",stair_direction="down"))
        parent=self.commit();nav=WorldNavigator(self.scene,NavigationState())
        nav.update((2140,961));nav.update((2140,959))
        self.assertIsNotNone(nav.transition)
        nav.update((2140,880));self.assertAlmostEqual(nav.transition.progress,.5)
        nav.update((2140,800));self.assertEqual(nav.state.floor,2)
        self.assertEqual(self.scene.project(scope_key(parent,"Floor 2"),2140,800),(2140,800))

    def test_legacy_image_buildings_keep_assets_positions_and_allow_outside_drawing(self):
        b=self.builder;b.close()
        parent=DraftItem("building",400,200,500,300,layer_style="academic",floor_count=4)
        self.scene.floors[CAMPUS].append(parent)
        self.owner.open_building_editor(parent);b=self.owner.builder
        point=b.point(pointer(2400,900),snap=False)
        self.assertGreater(point[0],1436)
        self.assertEqual(b.document.project(b.floor,*point),(2400,900))
        b.items().append(DraftItem("wall",*point,100,0))
        with patch("map.building_editor.save_scene"): b.commit()
        self.assertEqual(next(p for p in self.scene.buildings() if p.id==parent.id),parent)

    def test_free_build_control_tree_serializes_for_flet(self):
        b=self.builder
        b.choose_tool("floor");b.tap(pointer(2100,800));b.floor_done()
        encoded=msgpack.packb(b.control,default=configure_encode_object_for_msgpack(ft.Control))
        self.assertGreater(len(encoded),1000)
        self.assertIn("Floor section",ui_labels(b.control))


def item_corners_for_test(item):
    return [item.local_to_world(*point) for point in ((0,0),(item.width,0),(item.width,item.height),(0,item.height))]


if __name__=="__main__": unittest.main()
