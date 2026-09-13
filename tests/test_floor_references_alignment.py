"""Editor references, smart guides, geometry and zoom behavior."""

import asyncio
from dataclasses import replace
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import flet as ft
import flet.canvas as cv
from drafting.models import DraftItem
from drafting.handles import handles, transform
from map.alignment import bounds, snap_transform, snap_point
from map.reference_layers import ReferenceView, reference_controls
from map.scene import CAMPUS, MapScene, scope_key
from map.scene_renderer import render_scene, world_handles
from map.workspace_editor import MapWorkspaceEditor
from navigation.collision import barriers_for
from test_map_workspace import page_stub, pointer


class AlignmentGeometryTests(unittest.TestCase):
    def moved(self, item, others, **settings):
        return snap_transform((item.x, item.y), lambda p: replace(item, x=p[0], y=p[1]),
                              others, (3000, 1200), equal=False, **settings)

    def test_all_edges_and_centers_on_both_axes(self):
        target = DraftItem("room", 100, 100, 100, 100)
        for axis in (0, 1):
            for target_feature, value in enumerate((100, 150, 200)):
                for feature, offset in enumerate((0, 10, 20)):
                    item = DraftItem("rectangle", 500, 500, 20, 20)
                    item = replace(item, **{("x", "y")[axis]: value - offset + 2})
                    moved, guides = self.moved(item, [target])
                    anchors = (bounds(moved)[axis][0], sum(bounds(moved)[axis]) / 2, bounds(moved)[axis][1])
                    self.assertAlmostEqual(anchors[feature], value)
                    self.assertTrue(any(g.axis == axis and g.position == value for g in guides))

    def test_distance_limit_and_zoom_are_screen_based(self):
        target = DraftItem("wall", 100, 300, 0, 200)
        item = DraftItem("wall", 105, 0, 0, 50)
        moved, _ = self.moved(item, [target], pixels=6, scale=(1, 1))
        self.assertAlmostEqual(moved.x, 100)
        moved, guides = self.moved(item, [target], pixels=6, scale=(2, 2))
        self.assertAlmostEqual(moved.x, 105)
        self.assertFalse(guides)
        moved, _ = self.moved(replace(item, x=110), [target], pixels=6, scale=(.5, .5))
        self.assertAlmostEqual(moved.x, 100)

    def test_grid_and_smart_choose_closest_and_can_be_disabled(self):
        target = DraftItem("wall", 103, 300, 0, 100)
        item = DraftItem("wall", 104, 0, 0, 50)
        moved, guides = self.moved(item, [target], grid=20)
        self.assertAlmostEqual(moved.x, 103)
        self.assertTrue(guides)
        moved, _ = self.moved(replace(item, x=101), [target], grid=20)
        self.assertAlmostEqual(moved.x, 100)
        moved, guides = self.moved(item, [target], smart=False, grid=20)
        self.assertAlmostEqual(moved.x, 100)
        self.assertFalse(guides)
        moved, guides = self.moved(item, [target], smart=False)
        self.assertEqual(moved, item)
        self.assertFalse(guides)

    def test_layer_center_and_no_self_snapping(self):
        item = DraftItem("room", 1452, 850, 100, 100)
        moved, guides = self.moved(item, [item])
        self.assertAlmostEqual(moved.x, 1450)
        self.assertTrue(any(g.label == "Layer center" for g in guides))
        item = replace(item, x=350, y=350)
        moved, _ = self.moved(item, [item], smart=False)
        self.assertEqual(moved, item)

    def test_equal_gaps_before_after_and_between_in_both_axes(self):
        for axis in (0, 1):
            a = DraftItem("rectangle", 100, 100, 40, 40)
            b = replace(a, id="second", **{("x", "y")[axis]: 160})
            for near, expected in ((222, 220), (42, 40)):
                c = replace(a, id="third", **{("x", "y")[axis]: near})
                moved, guides = snap_transform((c.x, c.y), lambda p: replace(c, x=p[0], y=p[1]),
                    [a, b], (3000, 1200), smart=False, equal=True)
                self.assertAlmostEqual((moved.x, moved.y)[axis], expected)
                self.assertTrue(any(g.label.startswith("Equal gap") and len(g.gaps) == 2 for g in guides))
            b = replace(b, **{("x", "y")[axis]: 260})
            c = replace(a, id="third", **{("x", "y")[axis]: 182})
            moved, guides = snap_transform((c.x, c.y), lambda p: replace(c, x=p[0], y=p[1]),
                [a, b], (3000, 1200), smart=False, equal=True)
            self.assertAlmostEqual((moved.x, moved.y)[axis], 180)
            self.assertTrue(guides)

    def test_resize_snaps_moving_edge_not_fixed_anchor(self):
        item = DraftItem("room", 100, 100, 100, 100)
        target = DraftItem("room", 250, 350, 80, 80)
        start = handles(item)["e"]
        moved, guides = snap_transform((248, 150), lambda p: transform(item, "e", start, p),
            [target], (3000, 1200), equal=False, resizing=True)
        self.assertAlmostEqual(moved.width, 150)
        self.assertEqual((moved.x, moved.y, moved.height), (100, 100, 100))
        self.assertEqual(len(guides), 1)
        self.assertEqual(guides[0].axis, 0)

    def test_rotated_and_mirrored_resize_preserves_opposite_corner(self):
        for angle in (30, 90, 210):
            for mirrored in (False, True):
                item = DraftItem("stairs", 100, 100, 100, 160, rotation=angle, mirrored=mirrored)
                start = handles(item)["se"]
                target = DraftItem("wall", start[0] + 5, 300, 0, 200)
                moved, _ = snap_transform((start[0] + 4, start[1] + 3),
                    lambda p: transform(item, "se", start, p), [target], (3000, 1200),
                    equal=False, resizing=True)
                before, after = handles(item)["nw"], handles(moved)["nw"]
                self.assertAlmostEqual(before[0], after[0])
                self.assertAlmostEqual(before[1], after[1])
                self.assertEqual(moved.rotation, angle)
                self.assertEqual(moved.mirrored, mirrored)

    def test_line_endpoint_resize_keeps_other_endpoint(self):
        item = DraftItem("railing", 100, 100, 150, -50, rotation=20, stroke=10)
        start = handles(item)["end"]
        target = DraftItem("wall", start[0] + 5, 300, 0, 200)
        moved, guides = snap_transform((start[0] + 4, start[1]),
            lambda p: transform(item, "end", start, p), [target], (3000, 1200),
            equal=False, resizing=True)
        self.assertEqual(handles(item)["start"], handles(moved)["start"])
        self.assertTrue(guides)

    def test_point_snapping_for_new_walls_and_symbols(self):
        target = DraftItem("room", 100, 100, 200, 200)
        point, guides = snap_point((303, 201), [target], (3000, 1200), equal=False)
        self.assertAlmostEqual(point[0], 300)
        self.assertAlmostEqual(point[1], 200)
        self.assertEqual(len(guides), 2)

    def test_cached_targets_update_when_a_peer_moves(self):
        target = DraftItem("wall", 100, 300, 0, 200)
        item = DraftItem("wall", 105, 0, 0, 50)
        moved, _ = self.moved(item, [target])
        self.assertAlmostEqual(moved.x, 100)
        moved, guides = self.moved(item, [replace(target, x=300)])
        self.assertEqual(moved, item)
        self.assertFalse(guides)


class ReferenceEditorTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(ft.Control, "update")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.scene = MapScene()
        self.parent = DraftItem("building", 100, 100, 1000, 500, floor_count=6, opens="demo", text="School")
        self.scene.floors[CAMPUS].append(self.parent)
        self.lower = DraftItem("room", 100, 100, 200, 200, fill="#FFFFFF", stroke=6)
        self.scene.floors[scope_key(self.parent, "Floor 1")] = [self.lower]
        self.page = page_stub()
        self.editor = MapWorkspaceEditor(self.page, self.scene)
        self.editor.mount()

    def scope(self, n):
        key = scope_key(self.parent, f"Floor {n}")
        self.editor.change_scope(key)
        return key

    def test_defaults_and_arbitrary_floor_visibility(self):
        view = ReferenceView()
        self.assertEqual(view.layers(self.scene, self.scope(1)), [])
        self.assertEqual(view.layers(self.scene, self.scope(2)), [(scope_key(self.parent, "Floor 1"), .22)])
        self.assertEqual(view.layers(self.scene, self.scope(6)), [(scope_key(self.parent, "Floor 5"), .22)])
        view.multiple = True
        layers = view.layers(self.scene, self.editor.floor)
        self.assertEqual(len(layers), 5)
        self.assertLess(layers[0][1], layers[-1][1])
        view.focus = True
        self.assertFalse(view.layers(self.scene, self.editor.floor))
        view.focus, view.previous = False, False
        self.assertFalse(view.layers(self.scene, self.editor.floor))

    def test_ghosts_are_gray_noninteractive_under_current_floor(self):
        scope = self.scope(2)
        current = replace(self.lower, id="current", x=400)
        self.editor.items().append(current)
        self.editor.refresh()
        ghost = self.editor.reference_cache["controls"][0]
        self.assertTrue(ghost.ignore_interactions)
        self.assertEqual(ghost.opacity, .22)
        self.assertTrue(ghost.content.controls[-1].shapes)
        controls = self.editor.scene_stack.controls
        self.assertLess(controls.index(self.editor.image_cache[self.parent.id][1]), controls.index(ghost))
        self.assertLess(controls.index(ghost), controls.index(self.editor.vector_cache[current.id][1]))
        self.assertEqual(self.scene.floors[scope_key(self.parent, "Floor 1")][0], self.lower)
        self.assertEqual(self.editor.vector_cache[current.id][0][0], current)
        # Lower-floor room fill must not paint over current-floor objects.
        paths = ghost.content.controls[-1].shapes
        self.assertTrue(all(s.paint.color == "#64748B" for s in paths if isinstance(s, cv.Path)))

    def test_existing_asset_floor_images_are_referenced_without_asset_changes(self):
        from map_fixtures import EXAMPLE_PLACEMENTS
        from map.layers import BUILDING_LAYER_STYLES
        scene = MapScene(EXAMPLE_PLACEMENTS)
        parent = scene.buildings()[0]
        scope = scope_key(parent, "Floor 3")
        view = ReferenceView()
        ghosts = reference_controls(scene, scope, view)
        self.assertEqual(len(ghosts), 1)
        image = ghosts[0].content.controls[0]
        visible = [layer for layer in image.controls if layer.visible]
        self.assertEqual(len(visible), 1)
        self.assertEqual(visible[0].content.controls[0].src, BUILDING_LAYER_STYLES[parent.layer_style].layers[1][1])
        editor = MapWorkspaceEditor(self.page, scene)
        editor.change_scope(scope)
        current = editor.image_cache[parent.id][1]
        visible = [layer for layer in current.controls if layer.visible]
        self.assertEqual(len(visible), 1)
        self.assertEqual(visible[0].content.controls[0].src, BUILDING_LAYER_STYLES[parent.layer_style].layers[2][1])
        self.assertEqual(current.opacity, 1.)

    def test_lower_floor_cannot_be_hit_selected_moved_or_collide(self):
        scope = self.scope(2)
        world = self.scene.project(scope, 150, 150)
        self.assertIsNone(self.editor.hit_item(pointer(*world)))
        self.editor.pointer_down(pointer(*world))
        self.editor.pointer_move(pointer(world[0] + 40, world[1]))
        self.editor.pointer_up()
        self.assertIsNone(self.editor.selected)
        self.assertFalse(barriers_for(self.editor.items()))
        self.assertEqual(self.scene.floors[scope_key(self.parent, "Floor 1")], [self.lower])
        self.scope(1)
        self.assertEqual(self.editor.hit_item(pointer(*world)).id, self.lower.id)

    def test_view_settings_are_not_saved_or_runtime_rendered(self):
        scope = self.scope(2)
        saved = self.scene.to_json()
        self.editor.references.multiple = True
        self.editor.references.opacity = .1
        self.editor.references.focus = True
        self.editor.refresh()
        self.assertEqual(self.scene.to_json(), saved)
        self.assertFalse(self.scene.dirty)
        runtime_controls = render_scene(self.scene, scope)
        self.assertFalse(any(getattr(c, "ignore_interactions", False) for c in runtime_controls))

    def test_reference_cache_updates_after_lower_floor_changes_and_parent_resize(self):
        scope = self.scope(2)
        cache = {}
        first = reference_controls(self.scene, scope, self.editor.references, cache)
        self.assertIs(first, reference_controls(self.scene, scope, self.editor.references, cache))
        self.scene.floors[scope_key(self.parent, "Floor 1")].append(DraftItem("door", 120, 240, 60, 60))
        second = reference_controls(self.scene, scope, self.editor.references, cache)
        self.assertIsNot(first, second)
        self.scene.floors[CAMPUS] = [replace(self.parent, width=1200, rotation=30, mirrored=True)]
        third = reference_controls(self.scene, scope, self.editor.references, cache)
        self.assertIsNot(second, third)

    def test_visibility_dialog_applies_live_without_editing_map(self):
        self.scope(2)
        saved = self.scene.to_json()
        self.editor.reference_settings()
        dialog = self.page.show_dialog.call_args.args[0]
        previous, multiple, focus, _, opacity = dialog.content.controls[:5]
        opacity.value = .4
        opacity.on_change(None)
        self.assertEqual(self.editor.references.opacity, .4)
        self.assertEqual(self.editor.reference_cache["controls"][0].opacity, .4)
        focus.value = True
        focus.on_change(None)
        self.assertFalse(self.editor.reference_cache["controls"])
        self.assertTrue(opacity.disabled)
        dialog.actions[0].on_click(None)
        self.assertFalse(self.editor.dialog_open)
        self.assertEqual(self.scene.to_json(), saved)

    def test_drag_guides_snap_and_clear_on_release_cancel_and_scope_change(self):
        item = DraftItem("room", 100, 100, 100, 100)
        target = DraftItem("room", 350, 300, 100, 100)
        self.editor.items().extend([item, target])
        self.editor.selected = item.id
        self.editor.refresh()
        self.editor.pointer_down(pointer(150, 150))
        self.editor.pointer_move(pointer(303, 150))
        self.assertAlmostEqual(self.editor.selected_item().x, 250)
        self.assertTrue(self.editor.alignment_guides)
        self.assertTrue(self.editor.guide_shapes())
        self.editor.pointer_up()
        self.assertFalse(self.editor.alignment_guides)
        self.editor.history(False)
        self.assertEqual(self.editor.selected_item(), item)
        self.editor.pointer_down(pointer(150, 150))
        self.editor.pointer_move(pointer(303, 150))
        self.editor.cancel_gesture()
        self.assertEqual(self.editor.selected_item(), item)
        self.assertFalse(self.editor.alignment_guides)
        self.editor.pointer_down(pointer(150, 150))
        self.editor.pointer_move(pointer(303, 150))
        self.scope(2)
        self.assertFalse(self.editor.alignment_guides)

    def test_resize_gesture_and_floor_scaled_snap_distance(self):
        scope = self.scope(2)
        item = DraftItem("room", 100, 100, 100, 100)
        target = DraftItem("room", 250, 350, 80, 80)
        self.editor.items().extend([item, target])
        self.editor.selected = item.id
        self.editor.refresh()
        self.editor.pointer_down(pointer(*world_handles(item, self.parent)["e"]))
        self.editor.pointer_move(pointer(*self.scene.project(scope, 248, 150)))
        self.assertAlmostEqual(self.editor.selected_item().width, 150)
        self.assertEqual(self.editor.selected_item().x, 100)
        self.assertTrue(self.editor.alignment_guides)
        self.editor.pointer_up()
        self.editor.view_scale = 2
        self.assertAlmostEqual(self.editor.snap_settings()["scale"][0], 2 * self.parent.width / 1436)

    def test_interaction_and_programmatic_zoom_tracking(self):
        self.editor.view_interaction_start(None)
        self.editor.view_interaction_update(SimpleNamespace(scale=2))
        self.assertEqual(self.editor.view_scale, 2)
        self.editor.view_interaction_update(SimpleNamespace(scale=2.5))
        self.assertEqual(self.editor.view_scale, 2.5)
        self.editor.view_interaction_start(None)
        self.editor.view_interaction_update(SimpleNamespace(scale=.5))
        self.assertEqual(self.editor.view_scale, 1.25)
        with patch.object(ft.InteractiveViewer, "zoom", new_callable=AsyncMock), patch.object(
                ft.InteractiveViewer, "reset", new_callable=AsyncMock):
            asyncio.run(self.editor.zoom_in())
            self.assertEqual(self.editor.view_scale, 1.5625)
            asyncio.run(self.editor.zoom_out())
            self.assertEqual(self.editor.view_scale, 1.25)
            asyncio.run(self.editor.reset_view())
            self.assertEqual(self.editor.view_scale, 1)


if __name__ == "__main__":
    unittest.main()
