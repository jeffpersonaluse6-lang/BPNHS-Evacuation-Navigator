"""Arbitrary floor counts and stair-owned landing connections."""

from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import flet as ft
from drafting.models import DraftItem
from map.scene import MapScene,CAMPUS,scope_key
from map.workspace_editor import MapWorkspaceEditor
from navigation.models import NavigationState
from navigation.world import WorldNavigator
from test_map_workspace import page_stub
from player_fixtures import isolate_player_settings


def stacked_sections(count):
    scene=MapScene();scene.height=5000
    parent=DraftItem("building",0,0,2000,5000,free_build=True,
        floor_width=2000,floor_height=5000,floor_count=count)
    scene.floors={CAMPUS:[parent]}
    for floor in range(1,count+1):
        items=[]
        if floor<count:items.append(DraftItem("stairs",200,2000-floor*80,120,80,stair_from=floor,stair_to=floor+1))
        if floor>1:items.append(DraftItem("stairs",200,2000-(floor-1)*80,120,80,
            stair_from=floor,stair_to=floor-1,stair_direction="down"))
        scene.floors[scope_key(parent,f"Floor {floor}")]=items
    return scene,parent


class MultilevelStairTests(unittest.TestCase):
    def test_twenty_floors_ascend_after_separate_stair_exit_and_reentry(self):
        scene,parent=stacked_sections(20)
        scene=MapScene.from_json(scene.to_json());parent=scene.buildings()[0]
        nav=WorldNavigator(scene,NavigationState());nav.enter(parent);nav.update((260,2005))
        for source in range(1,20):
            tail=2000-(source-1)*80
            if source>1:nav.update((400,tail));nav.update((260,tail))
            nav.update((260,tail));nav.update((260,tail-20))
            self.assertEqual((nav.travel.source,nav.travel.target),(source,source+1))
            self.assertAlmostEqual(nav.travel.progress,.25)
            self.assertEqual(set(nav.active_floor_opacities()),{source,source+1})
            nav.update((260,tail-80));self.assertEqual(nav.state.floor,source+1);self.assertIsNone(nav.travel)
        self.assertEqual(nav.state.floor,20);self.assertEqual(nav.candidates()[0].target,19)

    def test_four_floor_descent_requires_each_stair_interaction_to_finish(self):
        scene,parent=stacked_sections(4);nav=WorldNavigator(scene,NavigationState());nav.enter(parent)
        nav.state.floor=4;nav.update((260,1760))
        for source in (4,3,2):
            tail=2000-(source-1)*80
            if source<4:nav.update((400,tail));nav.update((260,tail))
            nav.update((260,tail+20));self.assertEqual((nav.travel.source,nav.travel.target),(source,source-1))
            nav.update((260,tail+80));self.assertEqual(nav.state.floor,source-1);self.assertIsNone(nav.travel)

    def test_one_continuous_move_cannot_chain_overlapping_stair_sections(self):
        scene,parent=stacked_sections(4);nav=WorldNavigator(scene,NavigationState())
        nav.move((260,2005),0,-245)
        self.assertEqual(nav.state.floor,2);self.assertIsNone(nav.travel)

    def test_identical_overlapping_higher_flights_do_not_cascade(self):
        scene,parent=stacked_sections(6)
        for floor in range(1,6):scene.floors[scope_key(parent,f"Floor {floor}")]=[
            DraftItem("stairs",200,100,120,240,stair_from=floor,stair_to=floor+1)]
        nav=WorldNavigator(scene,NavigationState())
        for y in (345,340,220,100,100,99.8,100.2,99,120,200,300):nav.update((260,y))
        self.assertEqual(nav.state.floor,2);self.assertIsNone(nav.travel)
        nav.update((400,345));nav.update((260,345));nav.update((260,340));nav.update((260,220))
        self.assertEqual((nav.travel.source,nav.travel.target),(2,3))

    def test_only_current_floor_connections_are_candidates_above_floor_two(self):
        scene,parent=stacked_sections(20);nav=WorldNavigator(scene,NavigationState());nav.enter(parent);nav.state.floor=17
        self.assertEqual({s.source for s in nav.candidates()},{17})
        tail=2000-16*80;nav.update((260,tail));nav.update((260,tail-40))
        self.assertEqual((nav.travel.source,nav.travel.target),(17,18))

    def test_number_of_floors_is_not_bounded_by_old_dropdown_limits(self):
        scene,parent=stacked_sections(520)
        # Keep JSON under the file-size guard; layer count itself is unbounded.
        scene.floors={k:[] if k!=CAMPUS else v for k,v in scene.floors.items()}
        loaded=MapScene.from_json(scene.to_json());self.assertEqual(loaded.buildings()[0].floor_count,520)


class MultilevelStairEditorTests(unittest.TestCase):
    def setUp(self):
        isolate_player_settings(self)
        updater=patch.object(ft.Control,"update");updater.start();self.addCleanup(updater.stop)
        self.owner=MapWorkspaceEditor(page_stub(),MapScene());self.owner.choose_tool("building")
        self.editor=self.owner.builder

    def test_add_floor_and_inspector_can_connect_floor_seventeen_to_nineteen(self):
        editor=self.editor
        for _ in range(19):editor.add_floor()
        self.assertEqual(editor.building().floor_count,20)
        editor.change_scope(scope_key(editor.building(),"Floor 17"))
        stair=editor.create_item("stairs",200,100,120,240);editor.items().append(stair)
        editor.selection.select({stair.id},False);editor.refresh(properties=True)
        inspector=editor.stair_editor
        self.assertEqual(len(inspector.source.options),20)
        inspector.source.value="17";inspector.target.value="19";inspector.apply()
        self.assertEqual((editor.selected_item().stair_from,editor.selected_item().stair_to),(17,19))
        MapScene.from_json(editor.document.to_json())

    def test_generic_building_floor_count_keeps_layers_and_rejects_dangling_stairs(self):
        owner=self.owner;self.editor.close()
        parent=DraftItem("building",300,100,500,300,floor_count=1)
        owner.document.floors[CAMPUS]=[parent];owner.selection.select({parent.id},False);owner.refresh(properties=True)
        owner.floor_count.value="20";owner.apply_properties();parent=owner.selected_item()
        self.assertTrue(all(scope_key(parent,f"Floor {n}") in owner.document.floors for n in range(1,21)))
        owner.document.floors[scope_key(parent,"Floor 1")]=[DraftItem("stairs",200,100,100,200,stair_to=20,stair_from=1)]
        before=owner.document.snapshot();owner.floor_count.value="19";owner.apply_properties()
        self.assertEqual(owner.document.snapshot(),before);self.assertIn("stairs",owner.status.value)


if __name__=="__main__":unittest.main()
