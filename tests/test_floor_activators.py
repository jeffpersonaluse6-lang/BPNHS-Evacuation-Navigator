"""Explicit transitions, synchronized collision, stable edges and editor persistence."""

from dataclasses import replace
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import flet as ft
from drafting.models import DraftItem
from map.scene import MapScene,CAMPUS,scope_key
from map.workspace_editor import MapWorkspaceEditor
from map.world_renderer import WorldMapView
from navigation.models import NavigationState
from navigation.world import WorldNavigator
from navigation.activators import progress
from test_map_workspace import page_stub,pointer


class ActivatorRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.scene=MapScene()
        self.parent=DraftItem("building",100,100,1436,751,floor_count=3)
        self.stair=DraftItem("stairs",200,100,120,240)
        self.zone=DraftItem("floor_activator",200,100,120,240,activator_stair=self.stair.id,blocking=False)
        self.down=replace(self.zone,id="down-zone",activator_stair="down-stair",activator_from=2,activator_to=1,stair_direction="down")
        self.scene.floors={CAMPUS:[self.parent],scope_key(self.parent,"Floor 1"):[self.stair,self.zone],
            scope_key(self.parent,"Floor 2"):[replace(self.stair,id="down-stair",stair_direction="down"),self.down],
            scope_key(self.parent,"Floor 3"):[]}

    def position(self,x,y):return self.scene.project(scope_key(self.parent,"Floor 1"),x,y)
    def nav(self):return WorldNavigator(self.scene,NavigationState())
    def start(self,nav):
        nav.update(self.position(260,345));nav.update(self.position(260,340))

    def test_proximity_footprint_and_bare_stairs_never_activate_upper_floors(self):
        self.scene.floors[scope_key(self.parent,"Floor 1")]=[self.stair]
        nav=self.nav()
        for point in ((90,400),(110,400),self.position(260,340),self.position(260,220),self.position(260,100)):
            nav.update(point)
            self.assertEqual(nav.state.floor,1);self.assertIsNone(nav.travel)
            self.assertEqual(nav.floor_opacities(self.parent)[2],0)

    def test_zone_progress_blends_both_directions_and_reverses_without_jumping(self):
        nav=self.nav();self.start(nav)
        for value in (0,.25,.5,.75,.4,.2,0,.5,1):
            nav.update(self.position(260,340-value*240))
            alpha=nav.floor_opacities(self.parent)
            self.assertAlmostEqual(alpha[1],1-value);self.assertAlmostEqual(alpha[2],value)
        self.assertEqual(nav.state.floor,2)
        # Exit the terminal area to re-arm, then approach the down-zone arrow tail.
        nav.update(self.position(260,95));nav.update(self.position(260,100))
        nav.update(self.position(260,220));self.assertAlmostEqual(nav.travel.progress,.5)
        nav.update(self.position(260,340));self.assertEqual(nav.state.floor,1)

    def test_terminal_edge_jitter_does_not_retrigger_overlapping_return_zone(self):
        nav=self.nav();self.start(nav);nav.update(self.position(260,100))
        for y in (100,100.2,99.7,100.5,100)*5:
            nav.update(self.position(260,y));self.assertEqual(nav.state.floor,2);self.assertIsNone(nav.travel)

    def test_short_zone_activates_when_a_substep_crosses_source_edge(self):
        zone=replace(self.zone,height=10)
        self.scene.floors[scope_key(self.parent,"Floor 1")]=[self.stair,zone]
        nav=self.nav();nav.update(self.position(260,111));nav.update(self.position(260,107))
        self.assertIsNotNone(nav.travel);self.assertAlmostEqual(nav.travel.progress,.3)

    def test_spawning_or_side_entry_in_middle_stays_on_source_until_leaving(self):
        nav=self.nav()
        for x,y in ((260,220),(260,330),(260,325),(330,300),(260,300),(260,330),(260,325)):
            nav.update(self.position(x,y));self.assertIsNone(nav.travel)
        self.start(nav);nav.update(self.position(260,300));self.assertIsNotNone(nav.travel)

    def test_wrong_floor_disabled_or_broken_stair_link_does_not_trigger(self):
        for changed in (replace(self.zone,activator_from=2,activator_to=3),replace(self.zone,activator_enabled=False),
                        replace(self.zone,activator_stair="missing")):
            self.scene.floors[scope_key(self.parent,"Floor 1")]=[self.stair,changed]
            nav=self.nav();self.start(nav);nav.update(self.position(260,220))
            self.assertIsNone(nav.travel);self.assertEqual(nav.state.floor,1)

    def test_source_and_destination_collision_are_active_during_partial_visibility(self):
        source=DraftItem("wall",200,180,120,0,stroke=6)
        destination=DraftItem("wall",200,240,120,0,stroke=6)
        self.scene.floors[scope_key(self.parent,"Floor 1")].append(source)
        self.scene.floors[scope_key(self.parent,"Floor 2")].append(destination)
        nav=self.nav();nav.enter(self.parent)
        self.assertTrue(nav.allowed(self.position(260,240)))
        self.start(nav)
        nav.update(self.position(260,300))
        self.assertGreater(nav.floor_opacities(self.parent)[2],0)
        self.assertFalse(nav.allowed(self.position(260,240)))
        self.assertFalse(nav.allowed(self.position(260,180)))
        nav.update(self.position(260,100))
        self.assertEqual(nav.state.floor,2)
        self.assertTrue(nav.allowed(self.position(260,180)))

    def test_destination_obstruction_blocks_movement_before_entering_wall(self):
        wall=DraftItem("wall",200,300,120,0,stroke=6)
        self.scene.floors[scope_key(self.parent,"Floor 2")].append(wall)
        nav=self.nav();start=self.position(260,345)
        point=nav.move(start,0,-245)
        self.assertGreater(self.scene.unproject(scope_key(self.parent,"Floor 1"),*point)[1],300)
        self.assertEqual(nav.state.floor,1)

    def test_cannot_leave_side_of_stair_corridor_mid_transition(self):
        nav=self.nav();self.start(nav);nav.update(self.position(260,220))
        self.assertFalse(nav.allowed(self.position(350,220)))
        nav.update(self.position(260,345));self.assertIsNone(nav.travel)
        self.assertTrue(nav.allowed(self.position(350,345)))

    def test_double_stair_independent_zones_only_activate_correct_flight(self):
        stair=replace(self.stair,kind="double_stairs",width=240)
        up=replace(self.zone,width=110,activator_stair=stair.id)
        right=replace(up,id="right-zone",x=330,activator_to=3)
        self.scene.floors[scope_key(self.parent,"Floor 1")]=[stair,up,right]
        for x,target in ((250,2),(380,3)):
            nav=self.nav();nav.update(self.position(x,345));nav.update(self.position(x,340));nav.update(self.position(x,100))
            self.assertEqual(nav.state.floor,target)

    def test_rotated_mirrored_scaled_building_and_horizontal_zone_use_local_axes(self):
        zone=replace(self.zone,rotation=90,mirrored=True,activator_axis="right")
        self.parent=replace(self.parent,x=1500,y=900,rotation=180,mirrored=True,width=718,height=375.5)
        self.scene.floors[CAMPUS]=[self.parent]
        self.scene.floors[scope_key(self.parent,"Floor 1")]=[self.stair,zone]
        nav=self.nav()
        for x in (-5,0,30,60,120):
            point=self.position(*zone.local_to_world(x,zone.height/2));nav.update(point)
            if 0<x<120:self.assertAlmostEqual(nav.travel.progress,x/120)
        self.assertEqual(nav.state.floor,2)

    def test_runtime_never_renders_activators_even_if_nonfading(self):
        self.scene.floors[scope_key(self.parent,"Floor 1")][1]=replace(self.zone,fade_when_obstructing=False)
        import map.world_renderer as renderer
        original=renderer.item_shapes;seen=[]
        def draw(item,*args,**kwargs):seen.append(item.kind);return original(item,*args,**kwargs)
        with patch.object(renderer,"item_shapes",side_effect=draw):view=WorldMapView(self.scene)
        self.assertNotIn("floor_activator",seen)
        nav=self.nav();self.start(nav);nav.update(self.position(260,280));view.update(nav,self.position(260,280))
        self.assertAlmostEqual(view.layers[self.parent.id,2][0].opacity,.25)
        self.assertAlmostEqual(view.layers[self.parent.id,2][1].opacity,.25)


class ActivatorEditorTests(unittest.TestCase):
    def setUp(self):
        patcher=patch.object(ft.Control,"update");patcher.start();self.addCleanup(patcher.stop)
        self.owner=MapWorkspaceEditor(page_stub(),MapScene());self.owner.choose_tool("building")
        self.editor=self.owner.builder
        self.stair=DraftItem("double_stairs",200,100,240,240)
        self.editor.items().append(self.stair);self.editor.floor_done()
        self.editor.change_scope(scope_key(self.editor.building(),"Floor 1"))

    def place(self):
        self.editor.choose_tool("floor_activator")
        self.editor.pointer_down(pointer(200,100));self.editor.pointer_move(pointer(310,340));self.editor.pointer_up()
        return self.editor.selected_item()

    def test_place_configure_move_resize_duplicate_delete_undo_and_roundtrip(self):
        zone=self.place();self.assertEqual(zone.kind,"floor_activator")
        inspector=self.editor.activator_editor
        inspector.stair.value=self.stair.id;inspector.axis.value="right";inspector.apply()
        zone=self.editor.selected_item();self.assertEqual(zone.activator_stair,self.stair.id)
        self.editor.nudge(10,0);self.editor.properties["width"].value="160";self.editor.apply_properties()
        self.editor.rotate();self.editor.duplicate()
        duplicate=self.editor.selected_item();self.assertNotEqual(duplicate.id,zone.id)
        self.assertEqual(duplicate.activator_stair,self.stair.id)
        saved=MapScene.from_json(self.editor.document.to_json());self.assertEqual(saved.snapshot(),self.editor.document.snapshot())
        self.editor.delete();self.editor.history(False)
        self.assertIn(duplicate.id,{i.id for i in self.editor.items()})

    def test_show_toggle_hides_graphics_and_selection_without_disabling_runtime_zone(self):
        zone=self.place();self.editor.show_activators.value=False;self.editor.activators_visibility()
        self.assertNotIn(zone.id,{i.id for i in self.editor.editable_items()})
        self.assertNotIn(id(self.editor.vector_cache[zone.id][1]),{id(c) for c in self.editor.scene_stack.controls})
        self.editor.select_all();self.assertNotIn(zone.id,self.editor.selection.ids)
        self.assertTrue(next(i for i in self.editor.items() if i.id==zone.id).activator_enabled)
        self.editor.show_activators.value=True;self.editor.activators_visibility()
        self.assertIn(zone.id,{i.id for i in self.editor.editable_items()})

    def test_change_source_moves_zone_to_that_floor_with_world_geometry_preserved(self):
        zone=self.place();inspector=self.editor.activator_editor
        inspector.source.value="2";inspector.target.value="1";inspector.direction.value="down";inspector.apply()
        changed=self.editor.selected_item()
        self.assertTrue(self.editor.floor.endswith("Floor 2"))
        self.assertEqual((changed.x,changed.y,changed.width,changed.height),(zone.x,zone.y,zone.width,zone.height))
        MapScene.from_json(self.editor.document.to_json())

    def test_stair_delete_disables_linked_zone_undo_restores_connection(self):
        zone=self.place();self.editor.activator_editor.stair.value=self.stair.id;self.editor.activator_editor.apply()
        self.editor.selection.select({self.stair.id},False);self.editor.delete()
        changed=next(i for i in self.editor.items() if i.id==zone.id)
        self.assertFalse(changed.activator_enabled);self.assertIsNone(changed.activator_stair)
        MapScene.from_json(self.editor.document.to_json())
        self.editor.history(False)
        self.assertEqual(next(i for i in self.editor.items() if i.id==zone.id).activator_stair,self.stair.id)

    def test_duplicate_stair_and_zone_remaps_link_within_bundle(self):
        zone=self.place();self.editor.activator_editor.stair.value=self.stair.id;self.editor.activator_editor.apply()
        self.editor.selection.select({zone.id,self.stair.id},False);self.editor.duplicate()
        copies=self.editor.selection.items();stair=next(i for i in copies if i.kind=="double_stairs")
        self.assertEqual(next(i for i in copies if i.kind=="floor_activator").activator_stair,stair.id)

    def test_invalid_floor_or_link_configuration_is_rejected_without_mutating(self):
        self.place();before=self.editor.document.snapshot();inspector=self.editor.activator_editor
        for field,value in ((inspector.target,"1"),(inspector.target,"99"),(inspector.stair,"missing")):
            inspector.sync(self.editor.selected_item(),False);field.value=value;inspector.apply()
            self.assertEqual(self.editor.document.snapshot(),before)

    def test_copy_previous_floor_updates_destinations_and_stair_links(self):
        self.place();self.editor.activator_editor.stair.value=self.stair.id;self.editor.activator_editor.apply()
        self.editor.change_scope(scope_key(self.editor.building(),"Floor 2"));self.editor.floor_done()
        self.editor.change_scope(scope_key(self.editor.building(),"Floor 2"));self.editor.copy_floor()
        zone=next(i for i in self.editor.items() if i.kind=="floor_activator")
        stair=next(i for i in self.editor.items() if i.kind=="double_stairs")
        self.assertEqual((zone.activator_from,zone.activator_to),(2,3))
        self.assertEqual(zone.activator_stair,stair.id);self.assertNotEqual(stair.id,self.stair.id)
        MapScene.from_json(self.editor.document.to_json())

    def test_paste_zone_on_another_floor_disables_missing_original_stair_link(self):
        self.place();self.editor.activator_editor.stair.value=self.stair.id;self.editor.activator_editor.apply()
        self.editor.selection.copy()
        self.editor.change_scope(scope_key(self.editor.building(),"Floor 2"));self.editor.floor_done()
        self.editor.change_scope(scope_key(self.editor.building(),"Floor 2"));self.editor.selection.paste()
        zone=self.editor.selected_item()
        self.assertEqual((zone.activator_from,zone.activator_to),(2,3))
        self.assertIsNone(zone.activator_stair);self.assertFalse(zone.activator_enabled)
        MapScene.from_json(self.editor.document.to_json())

    def test_remove_floor_removes_incoming_zones_and_renumbers_surviving_links(self):
        zone=self.place()
        self.editor.change_scope(scope_key(self.editor.building(),"Floor 2"));self.editor.floor_done()
        down=replace(zone,id="third-down",activator_from=3,activator_to=1,stair_direction="down")
        self.editor.items().append(down)
        self.editor.change_scope(scope_key(self.editor.building(),"Floor 2"))
        with patch.object(self.editor,"confirm",side_effect=lambda message,action:action()):self.editor.remove_floor()
        remaining=[i for items in self.editor.document.floors.values() for i in items]
        self.assertNotIn(zone.id,{i.id for i in remaining})
        changed=next(i for i in remaining if i.id==down.id)
        self.assertEqual((changed.activator_from,changed.activator_to),(2,1))
        self.assertEqual((changed.x,changed.y,changed.width,changed.height),(down.x,down.y,down.width,down.height))
        MapScene.from_json(self.editor.document.to_json())
        self.editor.history(False);self.assertEqual(self.editor.building().floor_count,3)


if __name__=="__main__":unittest.main()
