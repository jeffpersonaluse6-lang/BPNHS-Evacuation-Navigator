"""Automatic invisible stair flights replace separately drawn activation zones."""

from dataclasses import asdict,replace
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import flet as ft
from drafting.models import DraftItem,validate_item,KINDS
from map.scene import MapScene,CAMPUS,scope_key
from map.workspace_editor import MapWorkspaceEditor,MAP_TOOLS
from map.world_renderer import WorldMapView
from navigation.models import NavigationState
from navigation.stairs import transitions,section_progress
from navigation.world import WorldNavigator,TransitionPhase
from test_map_workspace import page_stub,pointer
from player_fixtures import isolate_player_settings


def simple_scene(count=4):
    scene=MapScene();parent=DraftItem("building",100,100,1436,751,floor_count=count)
    scene.floors={CAMPUS:[parent],**{scope_key(parent,f"Floor {n}"):[] for n in range(1,count+1)}}
    stair=DraftItem("stairs",200,100,120,240,stair_from=1,stair_to=2)
    scene.floors[scope_key(parent,"Floor 1")]=[stair]
    scene.floors[scope_key(parent,"Floor 2")]=[replace(stair,id="return-stair",stair_from=2,stair_to=1,stair_direction="down")]
    return scene,parent,stair


class AutomaticStairRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.scene,self.parent,self.stair=simple_scene()
        self.nav=WorldNavigator(self.scene,NavigationState(collision_radius=1));self.nav.enter(self.parent)

    def visit(self,*points):
        for point in points:self.nav.update(self.scene.project(scope_key(self.parent,"Floor 1"),*point))

    def test_every_stair_has_automatic_connection_without_a_stored_zone(self):
        self.assertEqual(len(self.nav.candidates()),1)
        self.visit((260,345),(260,340),(260,220))
        self.assertEqual((self.nav.travel.source,self.nav.travel.target),(1,2))
        self.assertAlmostEqual(self.nav.travel.progress,.5)
        self.visit((260,100));self.assertEqual(self.nav.state.floor,2)
        self.assertEqual(len(self.scene.floors[scope_key(self.parent,"Floor 1")]),1)

    def test_midway_turnaround_reverses_opacity_without_committing_target(self):
        self.visit((260,345),(260,340))
        for p in (0,.1,.333,.5,.8,.4,.2):
            self.visit((260,340-240*p))
            self.assertAlmostEqual(self.nav.travel.progress,p)
            self.assertAlmostEqual(self.nav.active_floor_opacities()[2],p)
            self.assertEqual(self.nav.state.floor,1)
        self.visit((260,345));self.assertIsNone(self.nav.travel)
        self.assertEqual(self.nav.state.floor,1)

    def test_invalid_disabled_wrong_floor_or_outside_building_connections_never_trigger(self):
        for changed in (replace(self.stair,stair_enabled=False),replace(self.stair,stair_from=2),
                replace(self.stair,stair_to=99),replace(self.stair,stair_direction="down",stair_to=2)):
            self.scene.floors[scope_key(self.parent,"Floor 1")]=[changed]
            self.nav=WorldNavigator(self.scene,NavigationState());self.nav.enter(self.parent)
            self.visit((260,345),(260,340),(260,100))
            self.assertEqual(self.nav.state.floor,1);self.assertIsNone(self.nav.travel)

    def test_spawning_or_entering_from_side_in_middle_is_not_stair_entry(self):
        self.visit((260,220),(260,330),(330,300),(260,300),(260,330))
        self.assertIsNone(self.nav.travel)
        self.visit((260,345),(260,340),(260,220));self.assertIsNotNone(self.nav.travel)

    def test_double_stair_flights_have_independent_floor_connections(self):
        stair=replace(self.stair,kind="double_stairs",width=240,stair_to=2,
            stair_right_direction="up",stair_right_to=4)
        self.scene.floors[scope_key(self.parent,"Floor 1")]=[stair]
        for x,target in ((250,2),(380,4)):
            nav=WorldNavigator(self.scene,NavigationState());nav.enter(self.parent)
            for y in (345,340,220,124):nav.update(self.scene.project(scope_key(self.parent,"Floor 1"),x,y))
            self.assertEqual(nav.state.floor,target)
        sections=transitions(stair,1,4)
        self.assertFalse(section_progress(sections[0],stair.local_to_world(120,200))[1])
        self.assertFalse(section_progress(sections[1],stair.local_to_world(120,200))[1])

    def test_stair_rotation_mirror_resize_and_parent_scale_define_activation_geometry(self):
        for rotation,mirrored,width,height in ((0,False,120,240),(90,True,200,400),(37,False,80,200)):
            stair=replace(self.stair,x=700,y=300,rotation=rotation,mirrored=mirrored,width=width,height=height)
            self.parent=replace(self.parent,width=718,height=563.25,rotation=19,mirrored=True)
            self.scene.floors[CAMPUS]=[self.parent];self.scene.floors[scope_key(self.parent,"Floor 1")]=[stair]
            nav=WorldNavigator(self.scene,NavigationState(collision_radius=1));nav.enter(self.parent)
            for p in (-.02,0,.5,1):
                point=stair.local_to_world(width/2,height*(1-p))
                nav.update(self.scene.project(scope_key(self.parent,"Floor 1"),*point))
                if p==.5:self.assertAlmostEqual(nav.travel.progress,.5)
            self.assertEqual(nav.state.floor,2)

    def test_source_and_destination_collision_use_same_partial_transition(self):
        self.scene.floors[scope_key(self.parent,"Floor 1")].append(DraftItem("wall",200,180,120,0,stroke=6))
        self.scene.floors[scope_key(self.parent,"Floor 2")].append(DraftItem("wall",200,240,120,0,stroke=6))
        self.nav=WorldNavigator(self.scene,NavigationState(collision_radius=1));self.nav.enter(self.parent)
        position=lambda x,y:self.scene.project(scope_key(self.parent,"Floor 1"),x,y)
        self.assertTrue(self.nav.allowed(position(260,240)))
        self.visit((260,345),(260,340),(260,300))
        self.assertFalse(self.nav.allowed(position(260,180)));self.assertFalse(self.nav.allowed(position(260,240)))
        self.visit((260,100));self.assertEqual(self.nav.state.floor,2)
        self.assertTrue(self.nav.allowed(position(260,180)))

    def test_destination_obstruction_stops_player_before_target_wall(self):
        self.scene.floors[scope_key(self.parent,"Floor 2")].append(DraftItem("wall",200,300,120,0,stroke=6))
        self.nav=WorldNavigator(self.scene,NavigationState(collision_radius=1));self.nav.enter(self.parent)
        point=self.scene.project(scope_key(self.parent,"Floor 1"),260,345)
        point=self.nav.move(point,0,-245)
        self.assertGreater(self.scene.unproject(scope_key(self.parent,"Floor 1"),*point)[1],300)
        self.assertEqual(self.nav.state.floor,1)

    def test_per_stair_speed_override_does_not_change_geometry(self):
        stair=replace(self.stair,stair_speed_multiplier=.4)
        self.scene.floors[scope_key(self.parent,"Floor 1")]=[stair]
        self.nav=WorldNavigator(self.scene,NavigationState(collision_radius=1,player_speed=100));self.nav.enter(self.parent)
        start=self.scene.project(scope_key(self.parent,"Floor 1"),260,330)
        end=self.nav.walk(start,0,-1,.25)
        self.assertAlmostEqual(start[1]-end[1],10)
        self.assertEqual(self.scene.floors[scope_key(self.parent,"Floor 1")],[stair])

    def test_runtime_renders_stairs_but_never_derived_activation_rectangles(self):
        import map.world_renderer as renderer
        seen=[];original=renderer.item_shapes
        def draw(item,*args,**kwargs):seen.append(item.kind);return original(item,*args,**kwargs)
        with patch.object(renderer,"item_shapes",side_effect=draw):view=WorldMapView(self.scene)
        self.assertIn("stairs",seen);self.assertNotIn("floor_activator",seen)
        self.visit((260,345),(260,340),(260,220));view.update(self.nav,self.scene.project(scope_key(self.parent,"Floor 1"),260,220))
        self.assertEqual(view.layers[self.parent.id,2][0].opacity,.5)


class StairEditorTests(unittest.TestCase):
    def setUp(self):
        isolate_player_settings(self)
        updater=patch.object(ft.Control,"update");updater.start();self.addCleanup(updater.stop)
        self.owner=MapWorkspaceEditor(page_stub(),MapScene());self.owner.choose_tool("building")
        self.editor=self.owner.builder
        self.stair=self.editor.create_item("double_stairs",200,100,240,240)
        self.editor.items().append(self.stair);self.editor.floor_done()
        self.editor.change_scope(scope_key(self.editor.building(),"Floor 1"))
        self.editor.selection.select({self.stair.id},False);self.editor.refresh(properties=True)

    def test_old_tool_fields_and_inspector_are_completely_removed(self):
        self.assertNotIn("floor_activator",KINDS)
        self.assertNotIn("floor_activator",dict(MAP_TOOLS))
        self.assertFalse(hasattr(self.editor,"activator_editor"));self.assertFalse(hasattr(self.editor,"show_activators"))
        self.assertFalse(any(k.startswith("activator_") for k in asdict(self.stair)))
        self.assertTrue(self.editor.stair_editor.control.visible)

    def test_configure_both_flights_speed_and_roundtrip(self):
        inspector=self.editor.stair_editor
        inspector.target.value="2";inspector.right_direction.value="up";inspector.right_target.value="2"
        inspector.speed.value="0.5";inspector.apply()
        changed=self.editor.selected_item()
        self.assertEqual((changed.stair_from,changed.stair_to,changed.stair_right_to),(1,2,2))
        self.assertEqual(changed.stair_speed_multiplier,.5)
        saved=MapScene.from_json(self.editor.document.to_json())
        self.assertEqual(saved.snapshot(),self.editor.document.snapshot())
        self.assertNotIn("activator_",saved.to_json())

    def test_change_from_floor_moves_stair_without_moving_rotating_or_resizing_it(self):
        inspector=self.editor.stair_editor;inspector.source.value="2";inspector.direction.value="down"
        inspector.target.value="1";inspector.right_enabled.value=False;inspector.apply()
        changed=self.editor.selected_item()
        self.assertEqual((changed.x,changed.y,changed.width,changed.height,changed.rotation),
            (self.stair.x,self.stair.y,self.stair.width,self.stair.height,self.stair.rotation))
        self.assertEqual(changed.stair_from,2);self.assertTrue(self.editor.floor.endswith("Floor 2"))
        MapScene.from_json(self.editor.document.to_json())

    def test_nudge_resize_rotate_duplicate_delete_and_undo_keep_connections_on_stair(self):
        inspector=self.editor.stair_editor;inspector.target.value="2";inspector.apply()
        self.editor.nudge(10,0);self.editor.properties["width"].value="280";self.editor.apply_properties();self.editor.rotate()
        self.assertEqual(self.editor.selected_item().stair_to,2)
        self.editor.duplicate();copy=self.editor.selected_item()
        self.assertNotEqual(copy.id,self.stair.id);self.assertEqual(copy.stair_to,2)
        self.assertEqual(len(self.editor.items()),2)
        self.editor.delete();self.editor.history(False)
        self.assertIn(copy.id,{i.id for i in self.editor.items()})

    def test_drag_creates_no_attached_zone_and_does_not_full_render(self):
        self.editor.snap.value=False;self.editor.smart_snap.value=False
        self.editor.pointer_down(pointer(250,200));self.editor.pointer_move(pointer(270,220))
        with patch("map.workspace_editor.render_scene",side_effect=AssertionError("full render")):
            self.editor.pointer_move(pointer(290,240))
        self.assertEqual(len(self.editor.items()),1)
        self.assertFalse(hasattr(self.editor.interaction,"attached_zones"))
        self.editor.pointer_up();self.editor.history(False)
        self.assertEqual(self.editor.items(),[self.stair])

    def test_invalid_floors_direction_and_speed_do_not_mutate_map(self):
        inspector=self.editor.stair_editor;before=self.editor.document.snapshot()
        for field,value in ((inspector.source,"99"),(inspector.target,"99"),(inspector.target,"1"),(inspector.speed,"nan")):
            inspector.sync(self.editor.selected_item(),False);field.value=value;inspector.apply()
            self.assertEqual(self.editor.document.snapshot(),before)

    def test_copy_previous_floor_updates_stair_source_target_and_creates_no_zone(self):
        self.editor.stair_editor.target.value="2";self.editor.stair_editor.apply()
        self.editor.change_scope(scope_key(self.editor.building(),"Floor 2"));self.editor.floor_done()
        self.editor.change_scope(scope_key(self.editor.building(),"Floor 2"));self.editor.copy_floor()
        copy=self.editor.items()[0]
        self.assertEqual((copy.stair_from,copy.stair_to),(2,3));self.assertNotEqual(copy.id,self.stair.id)
        self.assertEqual(len(self.editor.items()),1);MapScene.from_json(self.editor.document.to_json())

    def test_remove_floor_disables_deleted_destination_without_redirecting_stair(self):
        self.editor.stair_editor.target.value="2";self.editor.stair_editor.apply()
        self.editor.change_scope(scope_key(self.editor.building(),"Floor 2"));self.editor.floor_done()
        self.editor.change_scope(scope_key(self.editor.building(),"Floor 2"))
        with patch.object(self.editor,"confirm",side_effect=lambda message,action:action()):self.editor.remove_floor()
        stair=self.editor.document.floors[scope_key(self.editor.building(),"Floor 1")][0]
        self.assertFalse(stair.stair_enabled);self.assertIsNone(stair.stair_to)
        MapScene.from_json(self.editor.document.to_json())
        self.editor.history(False);self.assertEqual(self.editor.building().floor_count,3)

    def test_paste_on_other_floor_updates_floor_connection(self):
        self.editor.stair_editor.target.value="2";self.editor.stair_editor.apply();self.editor.selection.copy()
        self.editor.change_scope(scope_key(self.editor.building(),"Floor 2"));self.editor.floor_done()
        self.editor.change_scope(scope_key(self.editor.building(),"Floor 2"));self.editor.selection.paste()
        stair=self.editor.selected_item()
        self.assertEqual((stair.stair_from,stair.stair_to),(2,3))


class LegacyStairMigrationTests(unittest.TestCase):
    def data(self,double=False):
        scene,parent,stair=simple_scene()
        if double:stair=replace(stair,kind="double_stairs",width=240)
        raw=json.loads(scene.to_json());scope=scope_key(parent,"Floor 1")
        raw["floors"][scope]=[asdict(stair)]
        raw["floors"][scope].append({"kind":"floor_activator","x":200,"y":100,"width":100,"height":240,
            "activator_from":1,"activator_to":2,"activator_stair":None,"stair_direction":"up","id":"old-zone"})
        return raw,parent,stair

    def test_unlinked_old_zone_is_imported_into_stair_then_removed(self):
        raw,parent,stair=self.data();loaded=MapScene.from_json(json.dumps(raw))
        items=loaded.floors[scope_key(parent,"Floor 1")]
        self.assertEqual(len(items),1);self.assertEqual(items[0].stair_to,2)
        self.assertNotIn("activator_",loaded.to_json());self.assertNotIn("floor_activator",loaded.to_json())
        self.assertEqual(MapScene.from_json(loaded.to_json()).snapshot(),loaded.snapshot())

    def test_two_old_zones_migrate_to_independent_double_stair_flights(self):
        raw,parent,stair=self.data(double=True);scope=scope_key(parent,"Floor 1")
        raw["floors"][scope].append({**raw["floors"][scope][-1],"id":"old-right","x":330,"activator_to":4})
        loaded=MapScene.from_json(json.dumps(raw));item=loaded.floors[scope][0]
        self.assertEqual((item.stair_to,item.stair_right_to),(2,4));self.assertEqual(item.stair_right_direction,"up")

    def test_conflicting_connections_fail_instead_of_silently_losing_data(self):
        raw,parent,stair=self.data();scope=scope_key(parent,"Floor 1")
        raw["floors"][scope].append({**raw["floors"][scope][-1],"id":"conflict","activator_to":3})
        with self.assertRaisesRegex(ValueError,"Conflicting"):MapScene.from_json(json.dumps(raw))

    def test_old_unattached_zone_is_removed_with_diagnostic_not_new_runtime_object(self):
        raw,parent,stair=self.data();raw["floors"][scope_key(parent,"Floor 1")][-1]["x"]=5000
        loaded=MapScene.from_json(json.dumps(raw));self.assertTrue(loaded.migration_notes)
        self.assertNotIn("floor_activator",loaded.to_json())

    def test_model_rejects_separate_activator_and_invalid_stair_speed(self):
        with self.assertRaises(ValueError):validate_item(DraftItem("floor_activator",0,0,100,100))
        for value in (0,1.1,float("nan"),True):
            with self.assertRaises(ValueError):validate_item(DraftItem("stairs",0,0,100,100,stair_speed_multiplier=value))


if __name__=="__main__":unittest.main()
