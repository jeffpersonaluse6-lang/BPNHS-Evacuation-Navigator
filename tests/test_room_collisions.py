"""Room boundaries, walkable doorway cuts, edit invalidation, and empty map reset."""

from dataclasses import replace
from pathlib import Path
import math
import sys
import tempfile
import unittest
from unittest.mock import patch
import flet as ft

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from drafting.models import DraftItem
from map.placements import BUILDINGS_ON_MAP
from map.scene import CAMPUS,MapScene,scope_key
from map.scene_store import load_scene,save_scene
from map.scene_renderer import render_scene,item_shapes
from map.workspace_editor import MapWorkspaceEditor
from navigation.app import EvacuationApp
from navigation.collision import barriers_for,barriers_for_item,openings_for,snap_opening_to_wall,move_with_collisions
from test_map_workspace import page_stub,pointer


class RoomCollisionTests(unittest.TestCase):
    def room(self):
        return DraftItem("room",100,100,400,300,stroke=6,fill="#FFFFFF")

    def door(self,kind="door"):
        return DraftItem(kind,250,40 if kind!="opening" else 94,100,60 if kind!="opening" else 12)

    def move(self,items,start,delta):
        return move_with_collisions(*start,*delta,26,barriers_for(items),2000,1000)

    def test_room_interior_is_free_and_all_four_thin_walls_block_movement(self):
        room=self.room()
        barriers=barriers_for([room])
        self.assertEqual(len(barriers),4)
        self.assertTrue(all(b.flat and b.radius==3 for b in barriers))
        self.assertFalse(any(b.blocks(300,250,26) for b in barriers))
        for delta,axis,minimum,maximum in (
            ((-600,0),0,129,300),((600,0),0,300,471),
            ((0,-600),1,129,250),((0,600),1,250,371),
        ):
            moved=self.move([room],(300,250),delta)
            self.assertGreaterEqual(moved[axis],minimum-1e-7)
            self.assertLessEqual(moved[axis],maximum+1e-7)

    def test_each_opening_kind_allows_entry_and_exit_without_disabling_solid_walls(self):
        for kind in ("door","double_door","opening"):
            with self.subTest(kind=kind):
                items=[self.room(),self.door(kind)]
                self.assertEqual(self.move(items,(300,40),(0,180)),(300,220))
                self.assertEqual(self.move(items,(300,220),(0,-180)),(300,40))
                self.assertLess(self.move(items,(180,40),(0,180))[1],100)
                self.assertGreater(len(barriers_for(items)),4)

    def test_doorway_is_exactly_its_width_not_its_swing_box(self):
        room=self.room()
        door=self.door()
        barriers=barriers_for([room,door])
        self.assertFalse(any(b.blocks(250.1,100,0) for b in barriers))
        self.assertFalse(any(b.blocks(349.9,100,0) for b in barriers))
        self.assertTrue(any(b.blocks(249.9,100,0) for b in barriers))
        self.assertTrue(any(b.blocks(350.1,100,0) for b in barriers))
        # Being near a jamb is naturally blocked by the player's body radius.
        self.assertLess(self.move([room,door],(260,40),(0,180))[1],100)

    def test_a_door_cuts_a_standalone_wall_into_two_solid_sections(self):
        wall=DraftItem("wall",100,100,500,0,stroke=12)
        door=self.door()
        barriers=barriers_for([wall,door])
        self.assertEqual(len(barriers),2)
        self.assertEqual(barriers[0].end,(250,100))
        self.assertEqual(barriers[1].start,(350,100))
        self.assertEqual(self.move([wall,door],(300,40),(0,180)),(300,220))
        self.assertLess(self.move([wall,door],(180,40),(0,180))[1],100)

    def test_rotated_and_mirrored_rooms_keep_walls_and_doors_aligned(self):
        for angle in (0,30,90,135,270):
            for mirrored in (False,True):
                with self.subTest(angle=angle,mirrored=mirrored):
                    room=DraftItem("room",700,350,300,300,rotation=angle,mirrored=mirrored,stroke=6)
                    point=room.local_to_world(150,0)
                    door=snap_opening_to_wall(DraftItem("door",0,0,100,60),[room],point)
                    before=room.local_to_world(150,-80)
                    after=room.local_to_world(150,80)
                    moved=self.move([room,door],before,(after[0]-before[0],after[1]-before[1]))
                    self.assertAlmostEqual(moved[0],after[0])
                    self.assertAlmostEqual(moved[1],after[1])
                    solid_before=room.local_to_world(40,-80)
                    solid_after=room.local_to_world(40,80)
                    moved=self.move([room,door],solid_before,(solid_after[0]-solid_before[0],solid_after[1]-solid_before[1]))
                    self.assertGreater(math.hypot(moved[0]-solid_after[0],moved[1]-solid_after[1]),50)

    def test_rotated_and_vertical_standalone_walls_have_walkable_openings(self):
        for angle in (35,90,180):
            wall=DraftItem("wall",700,300,400,0,rotation=angle,stroke=6)
            door=snap_opening_to_wall(DraftItem("double_door",0,0,120,60),[wall],wall.local_to_world(200,0))
            before=wall.local_to_world(200,-80)
            after=wall.local_to_world(200,80)
            moved=self.move([wall,door],before,(after[0]-before[0],after[1]-before[1]))
            self.assertAlmostEqual(moved[0],after[0])
            self.assertAlmostEqual(moved[1],after[1])

    def test_overlapping_and_multiple_openings_merge_without_ghost_sections(self):
        wall=DraftItem("wall",100,100,700,0,stroke=6)
        doors=[self.door(),replace(self.door(),x=300),replace(self.door(),x=550)]
        barriers=barriers_for([wall,*doors])
        self.assertEqual([(b.start[0],b.end[0]) for b in barriers],[(100,250),(400,550),(650,800)])
        self.assertEqual(barriers_for([wall,replace(self.door(),x=50,width=850)]),[])

    def test_unrelated_doors_windows_and_swing_arcs_never_remove_walls(self):
        wall=DraftItem("wall",100,100,500,0,stroke=6)
        for symbol in (replace(self.door(),y=80),replace(self.door(),rotation=90),
                       replace(self.door(),kind="window"),replace(self.door(),kind="stairs")):
            self.assertEqual(barriers_for([wall,symbol]),barriers_for([wall]))

    def test_railings_are_not_automatically_cut_by_door_symbols(self):
        rail=DraftItem("railing",100,100,500,0,stroke=10)
        self.assertEqual(barriers_for([rail,self.door()]),barriers_for([rail]))

    def test_moving_resizing_rotating_or_deleting_geometry_immediately_updates_collision(self):
        wall=DraftItem("wall",100,100,500,0,stroke=6)
        door=self.door()
        self.assertEqual(self.move([wall,door],(300,40),(0,180)),(300,220))
        moved=replace(door,x=400)
        self.assertLess(self.move([wall,moved],(300,40),(0,180))[1],100)
        self.assertEqual(self.move([wall,moved],(450,40),(0,180)),(450,220))
        narrow=replace(door,width=30)
        self.assertLess(self.move([wall,narrow],(265,40),(0,180))[1],100)
        self.assertEqual(self.move([wall,replace(narrow,width=120)],(310,40),(0,180)),(310,220))
        self.assertLess(self.move([wall],(300,40),(0,180))[1],100)
        self.assertEqual(self.move([door],(180,40),(0,180)),(180,220))
        self.assertEqual(self.move([replace(wall,x=800),door],(180,40),(0,180)),(180,220))
        self.assertEqual(self.move([replace(wall,width=40),door],(180,40),(0,180)),(180,220))
        self.assertEqual(self.move([replace(wall,rotation=90),door],(300,40),(0,180)),(300,220))

    def test_nonblocking_room_is_decorative_and_rectangle_is_not_a_room_wall(self):
        self.assertEqual(barriers_for([replace(self.room(),blocking=False)]),[])
        self.assertEqual(barriers_for([replace(self.room(),kind="rectangle")]),[])


class RoomEditorTests(unittest.TestCase):
    def setUp(self):
        from player_fixtures import isolate_player_settings
        isolate_player_settings(self)
        patcher=patch.object(ft.Control,"update")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.page=page_stub()
        self.editor=MapWorkspaceEditor(self.page,MapScene())
        self.editor.mount()

    def room_and_door(self):
        editor=self.editor
        editor.choose_tool("room")
        editor.pointer_down(pointer(100,100))
        editor.pointer_move(pointer(500,400))
        editor.pointer_up()
        room=editor.items()[0]
        editor.choose_tool("door")
        editor.tap(pointer(300,100))
        return room,editor.selected_item()

    def test_default_room_has_collision_and_clicked_door_aligns_its_baseline(self):
        room,door=self.room_and_door()
        self.assertTrue(room.blocking)
        self.assertEqual(door.local_to_world(door.width/2,door.height),(300,100))
        self.editor.player=(300,40)
        self.editor.move_player(0,180)
        self.assertEqual(self.editor.player,(300,220))
        self.editor.player=(180,40)
        self.editor.move_player(0,180)
        self.assertLess(self.editor.player[1],100)

    def test_door_drag_resize_delete_and_undo_update_gaps(self):
        room,door=self.room_and_door()
        editor=self.editor
        editor.smart_structure.value=False  # Intentionally edit one attached doorway.
        # Move the door horizontally with its interior, away from selection handles.
        editor.pointer_down(pointer(300,70))
        editor.pointer_move(pointer(400,70))
        editor.pointer_up()
        moved=editor.selected_item()
        self.assertAlmostEqual(moved.x,door.x+100)
        self.assertTrue(any(b.blocks(300,100,0) for b in barriers_for(editor.items())))
        self.assertFalse(any(b.blocks(400,100,0) for b in barriers_for(editor.items())))
        editor.properties["width"].value="100"
        editor.apply_properties()
        self.assertFalse(any(b.blocks(moved.x+80,100,0) for b in barriers_for(editor.items())))
        editor.delete()
        self.assertTrue(any(b.blocks(400,100,0) for b in barriers_for(editor.items())))
        editor.history(False)
        self.assertFalse(any(b.blocks(400,100,0) for b in barriers_for(editor.items())))

    def test_room_resize_move_and_delete_remove_old_collision_without_affecting_tools(self):
        room,door=self.room_and_door()
        editor=self.editor
        editor.selected=room.id
        editor.refresh(properties=True)
        self.assertTrue(editor.blocks.visible)
        editor.properties["x"].value="600"
        editor.properties["width"].value="500"
        editor.apply_properties()
        barriers=barriers_for(editor.items())
        self.assertFalse(any(b.blocks(100,250,0) for b in barriers))
        self.assertTrue(any(b.blocks(600,250,0) for b in barriers))
        editor.delete()
        self.assertEqual(barriers_for(editor.items()),[])
        self.assertIn("stairs",editor.tool_buttons)
        self.assertIn("railing",editor.tool_buttons)
        editor.history(False)
        self.assertTrue(any(b.blocks(600,250,0) for b in barriers_for(editor.items())))

    def test_collision_guides_match_cut_sections_and_rebuild_when_door_moves(self):
        room,door=self.room_and_door()
        editor=self.editor
        cuts=openings_for(editor.items())
        physical=barriers_for_item(room,cuts)
        self.assertEqual(len(item_shapes(room,collisions=True,openings=cuts))-len(item_shapes(room,openings=cuts)),2*len(physical))
        cache=editor.vector_cache[room.id]
        shapes=tuple(cache[1].shapes)
        editor.document.floors[CAMPUS][1]=replace(door,x=door.x+100)
        editor.refresh()
        self.assertNotEqual(editor.vector_cache[room.id][0],cache[0])
        self.assertNotEqual(tuple(editor.vector_cache[room.id][1].shapes),shapes)
        # Runtime does not request either guide color or guides, even on floor overlays.
        controls=render_scene(editor.document,collisions=False,grid=False)
        colors=[getattr(getattr(shape,"paint",None),"color",None) for control in controls
                for shape in getattr(control,"shapes",[])]
        self.assertNotIn("#008D8D",colors)

    def test_floor_openings_only_cut_walls_on_their_own_floor(self):
        parent=DraftItem("building",500,300,500,300,opens="test",floor_count=2)
        scene=MapScene()
        scene.floors[CAMPUS]=[parent]
        floor_room=DraftItem("room",100,100,400,300,stroke=6)
        door=DraftItem("door",250,40,100,60)
        scene.floors[scope_key(parent,"Floor 1")]=[floor_room,door]
        scene.floors[scope_key(parent,"Floor 2")]=[replace(floor_room,id="floor2-room")]
        app=EvacuationApp(self.page,scene=scene)
        app.enter_building("test")
        app.state.move_mode=True
        # This scaled doorway is ~35 map units wide. Use a world-space body
        # small enough to pass; building scale no longer resizes the player.
        app.state.collision_radius=10
        scope=scope_key(parent,"Floor 1")
        start=scene.project(scope,300,40)
        app.state.marker_x,app.state.marker_y=start[0]-26,start[1]-26
        app.move_user(0,180*parent.height/751)
        local=scene.unproject(scope,*app._marker_center())
        self.assertAlmostEqual(local[0],300)
        self.assertAlmostEqual(local[1],220)
        app.state.floor=2
        app.state.marker_x,app.state.marker_y=start[0]-26,start[1]-26
        app.move_user(0,180*parent.height/751)
        self.assertLess(scene.unproject(scope,*app._marker_center())[1],100)

    def test_drawing_preview_cuts_guides_without_committing_an_opening_to_map_data(self):
        scene=MapScene()
        room=DraftItem("room",100,100,400,300,stroke=6)
        scene.floors[CAMPUS]=[room]
        preview=DraftItem("door",250,40,100,60)
        vectors={}
        render_scene(scene,collisions=True,vector_cache=vectors,preview_item=preview)
        self.assertEqual(tuple(vectors[room.id][1].shapes),item_shapes(room,collisions=True,openings=(preview,)))
        self.assertEqual(scene.floors[CAMPUS],[room])
        render_scene(scene,collisions=True,vector_cache=vectors)
        self.assertEqual(tuple(vectors[room.id][1].shapes),item_shapes(room,collisions=True))

    def test_projected_wall_thickness_matches_collision_when_building_is_stretched(self):
        parent=DraftItem("building",500,300,600,100,rotation=35,mirrored=True)
        room=DraftItem("room",100,100,400,300,stroke=6,fill="#FFFFFF")
        visual=item_shapes(room,parent)
        debug=item_shapes(room,parent,collisions=True)
        self.assertEqual(len(visual),5)
        for index in range(4):
            self.assertEqual(visual[index+1].elements,debug[len(visual)+2*index].elements)

    def test_saved_room_openings_reconstruct_identical_collision_without_stored_boxes(self):
        room,door=self.room_and_door()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"map.json"
            save_scene(self.editor.document,path)
            restored=load_scene(path)
            self.assertEqual(barriers_for(restored.floors[CAMPUS]),barriers_for(self.editor.items()))
            self.assertEqual([i.kind for i in restored.floors[CAMPUS]],["room","door"])


class EmptyMapResetTests(unittest.TestCase):
    def test_empty_workspace_persists_and_missing_file_does_not_repopulate_old_layout(self):
        self.assertEqual(BUILDINGS_ON_MAP,[])
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(load_scene(Path(directory)/"missing.json").floors,{CAMPUS:[]})
            path=Path(directory)/"workspace.json"
            scene=MapScene()
            save_scene(scene,path)
            self.assertEqual(load_scene(path).floors,{CAMPUS:[]})
            self.assertEqual((load_scene(path).width,load_scene(path).height),(3000,1200))
            # A newly rebuilt saved map must load, not be reset again on startup.
            scene.floors[CAMPUS]=[DraftItem("room",100,100,400,300)]
            save_scene(scene,path)
            self.assertEqual(load_scene(path).snapshot(),scene.snapshot())

    def test_previous_layout_is_recoverable_without_being_used_as_active_map(self):
        backup=Path(__file__).resolve().parents[1]/"backups"/"map-before-reset-20260913.json"
        original=load_scene(backup)
        self.assertEqual(len(original.floors[CAMPUS]),21)
        self.assertEqual(BUILDINGS_ON_MAP,[])


if __name__=="__main__":
    unittest.main()
