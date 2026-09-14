"""One complete stair interaction must produce only one floor change."""

from dataclasses import replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from drafting.models import DraftItem
from map.scene import CAMPUS,MapScene,scope_key
from navigation.models import NavigationState
from navigation.world import WorldNavigator
from navigation.stairs import transitions


class FloorReentryTests(unittest.TestCase):
    def setup_stairs(self,source=1,target=2,radius=26,parent=None):
        self.scene=MapScene()
        self.parent=parent or DraftItem("building",100,100,1436,751,floor_count=max(source,target))
        direction="up" if target>source else "down"
        self.stair=DraftItem("stairs",200,50,120,350,stair_from=source,
            stair_to=target,stair_direction=direction)
        self.other=replace(self.stair,id="destination-stair",stair_from=target,
            stair_direction="down" if direction=="up" else "up",stair_to=source)
        self.flight=transitions(self.stair,source,self.parent.floor_count)[0]
        self.reverse=transitions(self.other,target,self.parent.floor_count)[0]
        self.scene.floors={CAMPUS:[self.parent],**{
            scope_key(self.parent,f"Floor {n}"):[] for n in range(1,self.parent.floor_count+1)}}
        self.scene.floors[scope_key(self.parent,f"Floor {source}")]=[self.stair]
        self.scene.floors[scope_key(self.parent,f"Floor {target}")]=[self.other]
        self.nav=WorldNavigator(self.scene,NavigationState(collision_radius=radius))
        self.nav.enter(self.parent);self.nav.state.floor=source

    def visit(self,*points):
        for point in points:self.nav.update(self.scene.project(scope_key(self.parent,"Floor 1"),*point))

    def complete(self):
        points=((222,405),(222,400),(222,225),(222,50)) if self.flight.direction=="up" else (
            (222,45),(222,50),(222,225),(222,400))
        self.visit(*points)
        self.assertEqual(self.nav.state.floor,self.flight.target);self.assertIsNone(self.nav.transition)

    def test_overlapping_return_stair_cannot_reverse_on_same_landing(self):
        self.setup_stairs();self.complete()
        for _ in range(20):
            self.visit((222,45),(292,45),(292,50),(292,225),(292,400))
            self.assertEqual(self.nav.state.floor,2);self.assertIsNone(self.nav.transition)
            self.assertFalse(self.nav.stair_armed(self.reverse))

    def test_full_exit_then_intentional_reentry_allows_exactly_one_descent(self):
        self.setup_stairs();self.complete();self.visit((292,20))
        self.assertTrue(self.nav.stair_armed(self.reverse))
        self.visit((292,50),(292,225),(292,400))
        self.assertEqual(self.nav.state.floor,1);self.assertIsNone(self.nav.transition)
        self.visit((222,405),(222,400),(222,50))
        self.assertEqual(self.nav.state.floor,1);self.assertIsNone(self.nav.transition)

    def test_center_outside_stair_is_not_exit_while_player_body_overlaps(self):
        self.setup_stairs();self.complete();self.visit((292,40),(292,22))
        self.assertFalse(self.nav.stair_armed(self.reverse))
        self.visit((292,20));self.assertTrue(self.nav.stair_armed(self.reverse))

    def test_active_transition_exclusively_owns_current_floor_flight(self):
        self.setup_stairs();self.visit((222,405),(222,400),(222,225))
        self.assertEqual(self.nav.state.floor,1);self.assertEqual(self.nav.candidates(),(self.flight,))
        self.assertIsNone(self.nav.detect_stair_entry((292,50)))
        self.assertFalse(self.nav.stair_armed(self.reverse));self.assertFalse(self.nav.stair_armed(self.flight))

    def test_high_floor_pair_uses_same_exit_reentry_logic(self):
        self.setup_stairs(source=17,target=18);self.complete();self.visit((292,45),(292,50),(292,400))
        self.assertEqual(self.nav.state.floor,18);self.assertIsNone(self.nav.transition)
        self.visit((292,20),(292,50),(292,400));self.assertEqual(self.nav.state.floor,17)

    def test_descending_transition_disarms_upward_return_until_exit(self):
        self.setup_stairs(source=4,target=3);self.complete();self.visit((292,405),(292,400),(292,50))
        self.assertEqual(self.nav.state.floor,3);self.assertIsNone(self.nav.transition)
        self.visit((292,440),(292,405),(292,400),(292,50));self.assertEqual(self.nav.state.floor,4)

    def test_rotated_mirrored_nonuniform_building_exit_is_in_world_units(self):
        parent=DraftItem("building",1500,900,718,563.25,rotation=90,mirrored=True,floor_count=2)
        self.setup_stairs(parent=parent);self.complete();self.visit((292,30))
        self.assertFalse(self.nav.stair_armed(self.reverse))
        self.visit((292,-100));self.assertTrue(self.nav.stair_armed(self.reverse))
        self.visit((292,45),(292,50),(292,400));self.assertEqual(self.nav.state.floor,1)

    def test_live_collision_radius_change_is_used_by_exit_detection(self):
        self.setup_stairs();self.complete();self.visit((292,40))
        self.assertFalse(self.nav.stair_armed(self.reverse));cached=dict(self.nav.area_cache)
        self.nav.state.collision_radius=1;self.visit((292,40))
        self.assertTrue(self.nav.stair_armed(self.reverse));self.assertEqual(self.nav.area_cache,cached)


if __name__=="__main__":unittest.main()
