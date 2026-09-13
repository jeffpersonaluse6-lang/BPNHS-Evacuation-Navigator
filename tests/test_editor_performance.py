"""Work-count regressions for real gestures, not machine-dependent FPS asserts."""

from dataclasses import replace
from pathlib import Path
import random
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import flet as ft
from drafting.models import DraftItem
from map.alignment import AlignmentIndex,snap_transform
from map.scene import CAMPUS,MapScene,scope_key
from map.scene_renderer import render_scene
from map.workspace_editor import MapWorkspaceEditor
from navigation.collision import OpeningIndex,wall_sections,openings_for,barriers_for
from spatial import BoundsIndex
from test_map_workspace import page_stub,pointer


class InteractionPerformanceTests(unittest.TestCase):
    def setUp(self):
        update=patch.object(ft.Control,"update");update.start();self.addCleanup(update.stop)
        self.scene=MapScene();self.scene.width=self.scene.height=5000
        self.scene.floors[CAMPUS]=[DraftItem("room",100+(n%25)*160,100+(n//25)*160,100,100)
            for n in range(200)]
        self.page=page_stub()
        self.editor=MapWorkspaceEditor(self.page,self.scene)
        self.editor.smart_structure.value=False
        self.editor.snap.value=self.editor.smart_snap.value=self.editor.equal_spacing.value=False

    def start(self,item=None,handle=None):
        item=item or self.editor.items()[0]
        self.editor.selection.select({item.id},False);self.editor.refresh(properties=True)
        from map.scene_renderer import world_handles
        point=world_handles(item)[handle] if handle else (item.x+40,item.y+40)
        self.editor.pointer_down(pointer(*point));self.page.update.reset_mock()
        return item,point

    def test_single_drag_skips_full_scene_reference_alignment_and_collision_rebuilds(self):
        item,point=self.start()
        graphics=self.editor.vector_cache[item.id][1]
        baseline=graphics.shapes
        controls=self.editor.scene_stack.controls
        with patch("map.workspace_editor.render_scene",side_effect=AssertionError("Full scene on mouse move")), \
             patch.object(self.editor,"alignment_items",side_effect=AssertionError("Peer list on mouse move")), \
             patch("map.interaction.item_shapes",side_effect=AssertionError("Translated geometry regenerated")):
            for n in range(10):self.editor.pointer_move(pointer(point[0]+n,point[1]+n))
        self.assertIs(self.editor.scene_stack.controls,controls)
        self.assertIs(graphics.shapes,baseline)
        self.assertEqual((graphics.left,graphics.top),(9,9))
        for call in self.page.update.call_args_list:
            self.assertEqual({id(c) for c in call.args},{id(graphics),id(self.editor.canvas)})

    def test_click_release_retain_grid_options_and_patch_only_changed_controls(self):
        background=tuple(self.editor.scene_stack.controls[:2])
        options=tuple(self.editor.object_picker.options)
        item,point=self.start()
        graphics=self.editor.vector_cache[item.id][1]
        unrelated=self.editor.vector_cache[self.editor.items()[100].id][1]
        self.assertTrue(all(a is b for a,b in zip(background,self.editor.scene_stack.controls)))
        self.assertTrue(all(a is b for a,b in zip(options,self.editor.object_picker.options)))
        self.editor.pointer_move(pointer(point[0]+17,point[1]+21))
        self.page.update.reset_mock()
        with patch.object(self.scene,"snapshot",side_effect=AssertionError("History copied all unchanged items on release")):
            self.editor.pointer_up()
        updates=self.page.update.call_args.args
        self.assertIn(id(graphics),[id(c) for c in updates])
        self.assertNotIn(id(unrelated),[id(c) for c in updates])
        self.assertNotIn(id(self.editor.scene_stack),[id(c) for c in updates])
        self.assertNotIn(id(self.editor.object_picker),[id(c) for c in updates])
        self.assertTrue(all(a is b for a,b in zip(background,self.editor.scene_stack.controls)))
        self.assertTrue(all(a is b for a,b in zip(options,self.editor.object_picker.options)))

    def test_identical_snapped_geometry_skips_duplicate_protocol_updates(self):
        item,point=self.start()
        self.editor.pointer_move(pointer(point[0]+10,point[1]+10))
        self.page.update.reset_mock()
        self.editor.pointer_move(pointer(point[0]+10,point[1]+10))
        self.page.update.assert_not_called()

    def test_real_flet_protocol_moves_canvas_coordinates_without_resending_shapes(self):
        import msgpack
        from flet.controls.object_patch import ObjectPatch
        from flet.messaging.protocol import configure_encode_object_for_msgpack
        encode=configure_encode_object_for_msgpack(ft.Control)
        def serialize(delta):msgpack.packb(delta.to_message(),default=encode)
        serialize(ObjectPatch.from_diff(None,self.editor.control,control_cls=ft.Control)[0])
        messages=[]
        def update(*controls):
            for control in controls or (self.editor.control,):
                delta=ObjectPatch.from_diff(control,control,control_cls=ft.Control)[0]
                messages.append((control,delta.patch));serialize(delta)
        self.page.update.side_effect=update
        item,point=self.start();messages.clear()
        graphics=self.editor.vector_cache[item.id][1]
        self.editor.pointer_move(pointer(point[0]+17,point[1]+21))
        operations=next(ops for control,ops in messages if control is graphics)
        self.assertEqual({tuple(op["path"]) for op in operations},{("left",),("top",)})
        messages.clear();self.editor.pointer_up()
        operations=next(ops for control,ops in messages if control is graphics)
        self.assertTrue(any(op["path"][0]=="shapes" for op in operations))
        self.assertTrue(all(control is not self.editor.control for control,ops in messages))

    def test_group_drag_preserves_slots_offsets_and_only_updates_group_controls(self):
        selected=self.editor.items()[:10]
        self.editor.selection.select({i.id for i in selected},False);self.editor.refresh(properties=True)
        item=selected[0];self.editor.pointer_down(pointer(item.x+40,item.y+40))
        floor_items=self.editor.items();aggregate=self.editor.interaction.group_bounds
        self.page.update.reset_mock()
        with patch("map.workspace_editor.render_scene",side_effect=AssertionError("Group full refresh")), \
             patch("map.selection.aggregate",side_effect=AssertionError("Aggregate recalculated")):
            self.editor.pointer_move(pointer(item.x+80,item.y+65))
        self.assertIs(self.editor.items(),floor_items)
        self.assertIs(self.editor.interaction.group_bounds,aggregate)
        for old,new in zip(selected,self.editor.items()[:10]):
            self.assertEqual((new.x-old.x,new.y-old.y),(40,25))
        self.assertEqual(len(self.page.update.call_args.args),11)
        self.editor.pointer_up()
        self.assertEqual(len(self.scene.undo_stack),1)
        self.editor.history(False)
        self.assertEqual(self.editor.items()[:10],selected)

    def test_resize_redraws_only_selected_geometry_without_collision_guides(self):
        item,start=self.start(handle="se")
        with patch("map.interaction.item_shapes",wraps=__import__("map.scene_renderer",fromlist=["item_shapes"]).item_shapes) as draw, \
             patch("map.workspace_editor.render_scene",side_effect=AssertionError("Resize full refresh")), \
             patch("map.interaction.OpeningIndex",side_effect=AssertionError("Opening index rebuilt")):
            self.editor.pointer_move(pointer(start[0]+25,start[1]+15))
        self.assertEqual(draw.call_count,1)
        self.assertFalse(draw.call_args.args[2])
        self.assertEqual((self.editor.selected_item().width,self.editor.selected_item().height),(125,115))
        self.editor.pointer_up()
        self.assertTrue(barriers_for([self.editor.selected_item()]))

    def test_cancel_after_resize_restores_model_and_cached_original_shapes(self):
        item,start=self.start(handle="se")
        canvas=self.editor.vector_cache[item.id][1];baseline=canvas.shapes
        self.editor.pointer_move(pointer(start[0]+30,start[1]+40))
        self.assertIsNot(canvas.shapes,baseline)
        self.editor.cancel_gesture()
        self.assertIsNone(self.editor.interaction)
        self.assertEqual(self.editor.items()[0],item)
        self.assertIs(canvas.shapes,baseline)
        self.assertIsNone(canvas.left)
        self.assertFalse(self.scene.undo_stack)

    def test_release_restores_graphics_positions_and_commits_exact_release_point(self):
        item,start=self.start()
        canvas=self.editor.vector_cache[item.id][1]
        self.editor.pointer_move(pointer(start[0]+20,start[1]+20))
        self.editor.pointer_up(pointer(start[0]+23.5,start[1]+24.5))
        moved=self.editor.items()[0]
        self.assertEqual((moved.x,moved.y),(item.x+23.5,item.y+24.5))
        self.assertIsNone(canvas.left);self.assertIsNone(canvas.top)
        self.assertIsNone(self.editor.interaction)
        self.assertEqual(len(self.scene.undo_stack),1)

    def test_static_references_and_lower_floors_keep_same_control_trees_while_dragging(self):
        self.editor.choose_tool("building");builder=self.editor.builder
        room=DraftItem("room",2000,2000,300,300);builder.items().append(room);builder.floor_done()
        upper=DraftItem("stairs",2100,2100,80,160);builder.items().append(upper)
        builder.selection.select({upper.id},False);builder.refresh(properties=True)
        reference=builder.map_reference.content.controls;ghosts=builder.reference_cache["controls"]
        builder.pointer_down(pointer(2140,2170))
        with patch("map.workspace_editor.reference_controls",side_effect=AssertionError("Ghost rebuilt")), \
             patch.object(builder,"alignment_items",side_effect=AssertionError("Map reference rescan")), \
             patch("map.building_editor.map_alignment_targets",side_effect=AssertionError("Map alignment proxies rebuilt")):
            builder.pointer_move(pointer(2150,2180))
        self.assertIs(builder.map_reference.content.controls,reference)
        self.assertIs(builder.reference_cache["controls"],ghosts)
        self.assertEqual(builder.document.floors[scope_key(builder.building(),"Floor 1")],[room])

    def test_door_move_invalidates_only_nearby_wall_cache_on_release(self):
        room=self.editor.items()[0]
        door=DraftItem("door",130,40,60,60)
        self.editor.items().append(door);self.editor.refresh(properties=True)
        unrelated=self.editor.vector_cache[self.editor.items()[100].id][1]
        unrelated_shapes=unrelated.shapes
        self.start(door)
        self.editor.pointer_move(pointer(door.x+40+20,door.y+40))
        self.editor.pointer_up()
        self.assertIs(unrelated.shapes,unrelated_shapes)
        expected=replace(door,x=door.x+20)
        self.assertEqual(wall_sections(room,OpeningIndex(openings_for(self.editor.items())).for_wall(room)),wall_sections(room,(expected,)))

    def test_drawing_preview_skips_full_refresh_and_collision_rebuilds(self):
        self.editor.choose_tool("wall");self.editor.pointer_down(pointer(4300,4300))
        with patch("map.workspace_editor.render_scene",side_effect=AssertionError("Draw full refresh")):
            self.editor.pointer_move(pointer(4500,4300))
        self.assertEqual(self.editor.preview.width,200)
        self.editor.pointer_up();self.assertEqual(self.editor.items()[-1].width,200)

    def test_box_selection_updates_only_overlay_until_release(self):
        self.editor.pointer_down(pointer(80,80));self.page.update.reset_mock()
        with patch("map.workspace_editor.render_scene",side_effect=AssertionError("Box full refresh")):
            self.editor.pointer_move(pointer(220,220))
        self.assertEqual(self.page.update.call_args.args,(self.editor.canvas,))
        self.editor.pointer_up();self.assertEqual(len(self.editor.selection.items()),1)

    def test_building_resize_does_not_update_cached_hidden_floor_controls(self):
        parent=DraftItem("building",4000,3000,500,300,floor_count=2)
        child=DraftItem("room",100,100,500,300)
        hidden=DraftItem("room",100,100,300,200)
        self.editor.items().append(parent)
        self.scene.floors[scope_key(parent,"Roof")]=[child]
        self.scene.floors[scope_key(parent,"Floor 2")]=[hidden]
        render_scene(self.scene,scope_key(parent,"Floor 2"),image_cache=self.editor.image_cache,vector_cache=self.editor.vector_cache)
        self.editor.refresh(properties=True)
        item,start=self.start(parent,"se")
        hidden_canvas=self.editor.vector_cache[hidden.id][1]
        self.assertNotIn(hidden.id,{record[0] for record in self.editor.interaction.records})
        self.editor.pointer_move(pointer(start[0]+40,start[1]+25))
        self.assertNotIn(hidden_canvas,self.page.update.call_args.args)
        self.editor.pointer_up();self.assertEqual(self.scene.floors[scope_key(parent,"Floor 2")],[hidden])

    def test_asset_building_translation_retains_image_tree_and_patches_it_on_release(self):
        parent=DraftItem("building",4000,3000,500,300,floor_count=4,layer_style="academic")
        self.editor.items().append(parent);self.editor.refresh(properties=True)
        image=self.editor.image_cache[parent.id][1]
        self.start(parent)
        self.assertIsNone(self.editor.interaction.image_records[0][-1])
        self.editor.pointer_move(pointer(parent.x+65,parent.y+60))
        self.page.update.reset_mock();self.editor.pointer_up()
        self.assertIs(self.editor.image_cache[parent.id][1],image)
        self.assertEqual((image.left,image.top),(parent.x+25,parent.y+20))
        self.assertIn(id(image),[id(c) for c in self.page.update.call_args.args])
        self.assertNotIn(id(self.editor.scene_stack),[id(c) for c in self.page.update.call_args.args])


class GeometryIndexTests(unittest.TestCase):
    def test_background_cache_invalidates_only_for_grid_or_canvas_changes(self):
        scene=MapScene();cache={}
        first=render_scene(scene,background_cache=cache)
        second=render_scene(scene,background_cache=cache)
        self.assertTrue(all(a is b for a,b in zip(first,second)))
        resized=MapScene();resized.width+=100
        third=render_scene(resized,background_cache=cache)
        self.assertIsNot(first[0],third[0])
        self.assertEqual(third[0].width,resized.width)
        fourth=render_scene(resized,grid=False,background_cache=cache)
        self.assertEqual(len(fourth),1)

    def test_map_alignment_proxies_use_cached_transforms_not_per_corner_scene_scans(self):
        from map.free_build import map_alignment_targets,item_corners
        scene=MapScene()
        parent=DraftItem("building",500,600,400,300,rotation=30,mirrored=True,floor_count=2)
        room=DraftItem("room",100,100,250,150,rotation=20)
        scene.floors[CAMPUS]=[room,parent]
        scope=scope_key(parent,"Floor 2")
        points=[scene.unproject(scope,*point) for point in item_corners(room,padded=False)]
        with patch.object(scene,"project",side_effect=AssertionError("Source scanned for each corner")), \
             patch.object(scene,"unproject",side_effect=AssertionError("Destination scanned for each corner")):
            targets=map_alignment_targets(scene,parent,scope)
        target=targets[0]
        self.assertAlmostEqual(target.x,min(p[0] for p in points))
        self.assertAlmostEqual(target.y,min(p[1] for p in points))
        self.assertAlmostEqual(target.width,max(p[0] for p in points)-target.x)
        self.assertAlmostEqual(target.height,max(p[1] for p in points)-target.y)

    def test_large_and_negative_boxes_query_deterministically(self):
        index=BoundsIndex((((-10000,10000),(-10000,10000)),((-200,-100),(100,200)),((500,600),(500,600))))
        self.assertEqual(index.query(((-150,-120),(120,150))),(0,1))
        self.assertEqual(index.query(((0,0),(0,0))),(0,))

    def test_local_alignment_index_excludes_distant_objects_and_matches_near_snaps(self):
        near=DraftItem("room",100,100,100,100)
        distant=[DraftItem("rectangle",2000+n*100,2000,20,20) for n in range(1000)]
        index=AlignmentIndex([near,*distant])
        current=DraftItem("room",103,250,100,100)
        function=lambda p:replace(current,x=p[0],y=p[1])
        fast,guides=snap_transform((103,250),function,index,(5000,5000),equal=False)
        slow,expected=snap_transform((103,250),function,[near],(5000,5000),equal=False)
        self.assertEqual(fast,slow);self.assertEqual(guides,expected)
        self.assertEqual(index.last_candidate_count,1)

    def test_equal_spacing_grid_and_rotated_resize_still_work_with_prepared_targets(self):
        from drafting.handles import handles,transform
        near=[DraftItem("rectangle",100,100,40,40),DraftItem("rectangle",160,100,40,40)]
        current=DraftItem("rectangle",222,100,40,40)
        moved,guides=snap_transform((222,100),lambda p:replace(current,x=p[0],y=p[1]),AlignmentIndex(near),
            (5000,5000),smart=False,equal=True)
        self.assertAlmostEqual(moved.x,220);self.assertTrue(guides)
        item=DraftItem("stairs",300,300,100,160,rotation=30,mirrored=True)
        start=handles(item)["se"];target=DraftItem("wall",start[0]+5,300,0,200)
        fast,_=snap_transform((start[0]+4,start[1]+3),lambda p:transform(item,"se",start,p),AlignmentIndex([target]),
            (5000,5000),equal=False,resizing=True,grid=20)
        for a,b in zip(handles(item)["nw"],handles(fast)["nw"]):self.assertAlmostEqual(a,b)

    def test_spatial_opening_filter_matches_full_geometry_on_rotated_mirrored_rooms(self):
        rng=random.Random(42)
        for angle in (0,35,90,180):
            for mirrored in (False,True):
                room=DraftItem("room",800,800,400,300,rotation=angle,mirrored=mirrored,stroke=8)
                local_door=DraftItem("door",150,-60,100,60)
                x,y=room.local_to_world(local_door.x,local_door.y)
                aligned=replace(local_door,x=x,y=y,rotation=angle,mirrored=mirrored)
                far=[DraftItem("door",rng.uniform(-5000,5000),rng.uniform(-5000,5000),100,60,
                    rotation=rng.choice((0,35,90,180)),mirrored=rng.choice((True,False))) for _ in range(100)]
                openings=(aligned,*far)
                self.assertEqual(wall_sections(room,OpeningIndex(openings).for_wall(room)),wall_sections(room,openings))


if __name__=="__main__":unittest.main()
