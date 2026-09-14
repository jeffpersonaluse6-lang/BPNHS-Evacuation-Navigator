"""Continuous world coordinates, retained layers and elevation-aware barriers."""

from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import flet as ft
from drafting.models import DraftItem
from map.scene import MapScene,CAMPUS,scope_key
from navigation.app import EvacuationApp
from navigation.models import NavigationState
from navigation.world import WorldNavigator
from test_map_workspace import page_stub


class SeamlessWorldTests(unittest.TestCase):
    def setUp(self):
        from player_fixtures import isolate_player_settings
        isolate_player_settings(self)
        patcher=patch.object(ft.Control,"update");patcher.start();self.addCleanup(patcher.stop)
        self.scene=MapScene()
        self.parent=DraftItem("building",300,100,1436,751,floor_count=4,opens="school",text="Academic",approach_distance=80)
        self.scene.floors[CAMPUS]=[self.parent]
        self.up=DraftItem("stairs",200,100,100,200)
        self.down=replace(self.up,id="down",stair_direction="down")
        self.scene.floors[scope_key(self.parent,"Floor 1")]=[self.up]
        self.scene.floors[scope_key(self.parent,"Floor 2")]=[self.down,replace(self.up,id="up23",x=500)]
        self.scene.floors[scope_key(self.parent,"Floor 3")]=[replace(self.down,id="down32",x=500),replace(self.up,id="up34",x=800)]
        self.scene.floors[scope_key(self.parent,"Floor 4")]=[replace(self.down,id="down43",x=800)]

    def navigator(self):
        state=NavigationState()
        nav=WorldNavigator(self.scene,state)
        nav.enter(self.parent)
        return nav

    def position(self,x,y):
        return self.scene.project(scope_key(self.parent,"Floor 1"),x,y)

    def test_stair_visibility_uses_continuous_progress_not_fixed_stages(self):
        nav=self.navigator()
        nav.update(self.position(250,300))
        for value in (0,.1,.25,.333,.5,.75,.913):
            nav.update(self.position(250,300-200*value))
            self.assertAlmostEqual(nav.transition.progress,value)
            alpha=nav.floor_opacities(self.parent)
            self.assertAlmostEqual(alpha[1],1-value)
            self.assertAlmostEqual(alpha[2],value)
            self.assertEqual(alpha[3],0)
            self.assertEqual(alpha[4],0)
        nav.update(self.position(250,100))
        self.assertEqual(nav.state.floor,2)
        self.assertIsNone(nav.transition)

    def test_descending_and_reversing_midway(self):
        nav=self.navigator();nav.state.floor=2
        nav.update(self.position(250,100))
        nav.update(self.position(250,150))
        self.assertAlmostEqual(nav.floor_opacities(self.parent)[1],.25)
        self.assertAlmostEqual(nav.floor_opacities(self.parent)[2],.75)
        nav.update(self.position(250,125))
        self.assertAlmostEqual(nav.transition.progress,.125)
        nav.update(self.position(250,300))
        self.assertEqual(nav.state.floor,1)

    def test_multiple_connections_do_not_hardcode_first_second_floors(self):
        nav=self.navigator()
        for source,x in ((1,250),(2,550),(3,850)):
            nav.state.floor=source;nav.state.stair_armed=True
            nav.update(self.position(x,310))
            nav.update(self.position(x,300))
            nav.update(self.position(x,200))
            self.assertEqual(nav.transition.target,source+1)
            nav.update(self.position(x,100))
            self.assertEqual(nav.state.floor,source+1)

    def test_entry_exit_preserves_position_viewer_joystick_and_control_identity(self):
        app=EvacuationApp(page_stub(),self.scene)
        viewer=app.viewer;control=app.world_view.control
        layer_ids={key:tuple(id(c) for c in controls) for key,controls in app.world_view.layers.items()}
        app.state.move_mode=True
        app.set_joystick_direction(.4,.7)
        app.state.marker_x,app.state.marker_y=280-26,500-26
        app.move_user(40,0)
        self.assertEqual(app.active_parent.id,self.parent.id)
        self.assertAlmostEqual(app._marker_center()[0],320)
        self.assertAlmostEqual(app._marker_center()[1],500)
        app.move_user(-50,0)
        self.assertIsNone(app.active_parent)
        self.assertAlmostEqual(app._marker_center()[0],270)
        self.assertIs(app.viewer,viewer)
        self.assertIs(app.world_view.control,control)
        self.assertEqual(layer_ids,{key:tuple(id(c) for c in controls) for key,controls in app.world_view.layers.items()})
        self.assertEqual((app.state.joystick_x,app.state.joystick_y),(.4,.7))

    def test_roof_approach_is_distance_based_and_reversible(self):
        state=NavigationState();nav=WorldNavigator(self.scene,state)
        self.assertEqual(nav.roof_opacity(self.parent,(200,500)),1)
        self.assertAlmostEqual(nav.roof_opacity(self.parent,(260,500)),.5)
        self.assertAlmostEqual(nav.roof_opacity(self.parent,(280,500)),.25)
        self.assertEqual(nav.roof_opacity(self.parent,(320,500)),0)
        nav.update((320,500));nav.update((260,500))
        self.assertAlmostEqual(nav.roof_opacity(self.parent,(260,500)),.5)

    def test_hidden_walls_still_block_and_door_gaps_stay_open_in_world(self):
        room=DraftItem("room",100,100,400,300,stroke=6)
        door=DraftItem("door",250,40,100,60)
        self.scene.floors[scope_key(self.parent,"Floor 1")]=[room,door]
        nav=WorldNavigator(self.scene,NavigationState())
        start=self.position(300,40)
        end=nav.move(start,0,180)
        self.assertAlmostEqual(end[0],self.position(300,220)[0])
        self.assertAlmostEqual(end[1],self.position(300,220)[1])
        end=nav.move(self.position(180,40),0,180)
        self.assertLess(self.scene.unproject(scope_key(self.parent,"Floor 1"),*end)[1],100)
        app=EvacuationApp(page_stub(),self.scene)
        app.world_view.layers[self.parent.id,1][0].opacity=0
        self.assertFalse(app.navigator.allowed(self.position(180,100)))

    def test_upper_floor_barriers_do_not_block_player_at_ground_elevation(self):
        rail=DraftItem("railing",400,0,0,751,stroke=10)
        self.scene.floors[scope_key(self.parent,"Floor 3")]=[rail]
        nav=self.navigator()
        self.assertTrue(nav.allowed(self.position(400,400)))
        nav.state.floor=3
        self.assertFalse(nav.allowed(self.position(400,400)))

    def test_transformed_building_stair_progress_and_collision_use_its_local_axes(self):
        for angle in (90,180,270):
            parent=replace(self.parent,rotation=angle,x=1800,y=900,width=718,height=375.5,mirrored=True)
            self.scene.floors[CAMPUS]=[parent]
            nav=WorldNavigator(self.scene,NavigationState());nav.enter(parent)
            scope=scope_key(parent,"Floor 1")
            nav.update(self.scene.project(scope,250,300))
            nav.update(self.scene.project(scope,250,200))
            self.assertAlmostEqual(nav.transition.progress,.5)

    def test_stairs_cannot_be_triggered_by_stepping_directly_into_middle(self):
        nav=self.navigator()
        nav.update(self.position(250,200))
        self.assertIsNone(nav.transition)
        self.assertEqual(nav.state.floor,1)

    def test_floor_transition_does_not_render_again_or_stop_held_input(self):
        app=EvacuationApp(page_stub(),self.scene)
        app.enter_building("school")
        app.state.move_mode=True
        app.set_joystick_direction(0,-1)
        start=self.position(250,300)
        app.state.marker_x,app.state.marker_y=start[0]-26,start[1]-26
        with patch.object(app,"render") as render,patch.object(app,"_stop_joystick") as stop:
            app.move_user(0,-200)
            self.assertEqual(app.state.floor,2)
            render.assert_not_called();stop.assert_not_called()
        self.assertEqual((app.state.joystick_x,app.state.joystick_y),(0,-1))
        self.assertAlmostEqual(app._marker_center()[1],self.position(250,100)[1])

    def test_campus_clearance_uses_configured_radius_not_building_scale(self):
        parent=replace(self.parent,width=718,height=375.5)
        rail=DraftItem("railing",800,200,0,200,stroke=10)
        self.scene.floors[CAMPUS]=[parent,rail]
        nav=WorldNavigator(self.scene,NavigationState());nav.enter(parent)
        self.assertFalse(nav.allowed((778,350)))
        nav.state.collision_radius=13
        self.assertTrue(nav.allowed((778,350)))
        self.assertFalse(nav.allowed((785,350)))


if __name__=="__main__": unittest.main()
