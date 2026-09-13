"""Geometry and UI callback regressions without opening native windows."""

import asyncio
from dataclasses import replace
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

import flet as ft

SOURCE_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE_DIR))

from drafting.editor import BuildingDraftEditor
from drafting.assets import map_svg
from drafting.models import DraftDocument, DraftItem, primitives, validate_item
from drafting.window import DraftingWindow
from editor_shortcuts import history_shortcut
from map.campus import PlacedBuilding, _building_control, build_campus_map
from map.editor import CampusPlacementEditor
from map.geometry import resize_building, resize_handles


def page_stub():
    return SimpleNamespace(width=1400, height=900, overlay=[], update=Mock(),
        on_keyboard_event=None, on_resize=None, show_dialog=Mock(), pop_dialog=Mock())


def pointer(x, y):
    return SimpleNamespace(local_position=SimpleNamespace(x=x, y=y),
        global_position=SimpleNamespace(x=x, y=y))


def key(letter, ctrl=True, shift=False, alt=False):
    return SimpleNamespace(key=letter, ctrl=ctrl, shift=shift, alt=alt, meta=False)


class EditorTests(unittest.TestCase):
    def setUp(self):
        self.control_updates = patch.object(ft.Control, "update")
        self.control_updates.start()
        self.addCleanup(self.control_updates.stop)
        self.page = page_stub()
        self.original = PlacedBuilding("Test", 100, 100, 320, 200, "#FFFFFF", layer_style="academic")

    def map_editor(self, building=None):
        editor = CampusPlacementEditor(self.page, [building or self.original],
            build_campus_map, 3000, 1200, building_builder=_building_control)
        editor.viewer = ft.InteractiveViewer(content=editor.build_content())
        return editor

    def test_all_resize_handles_keep_opposite_edges_fixed(self):
        for handle, start in resize_handles(self.original).items():
            with self.subTest(handle=handle):
                b = resize_building(self.original, handle, start,
                    (start[0] + 30, start[1] + 20), 3000, 1200)
                self.assertEqual(b.left, 130 if "w" in handle else 100)
                self.assertEqual(b.top, 120 if "n" in handle else 100)
                self.assertEqual(b.left + b.width, 450 if "e" in handle else 420)
                self.assertEqual(b.top + b.height, 320 if "s" in handle else 300)

    def test_resize_clamps_to_map_and_minimum_size(self):
        small = resize_building(self.original, "nw", (100, 100), (10000, 10000), 3000, 1200)
        self.assertEqual((small.width, small.height), (24, 24))
        large = resize_building(self.original, "se", (420, 300), (10000, 10000), 3000, 1200)
        self.assertEqual((large.left + large.width, large.top + large.height), (3000, 1200))
        edge = resize_building(self.original, "nw", (100, 100), (-10000, -10000), 3000, 1200)
        self.assertEqual((edge.left, edge.top), (0, 0))

    def test_map_resize_updates_floor_and_roof_and_undo_redo(self):
        editor = self.map_editor()
        editor.select(0)
        # Grab a corner slightly outside the image: no selection loss or jump.
        editor.select_at_pointer(pointer(424, 304))
        self.assertEqual(editor.selected, 0)
        editor.start_drag(pointer(424, 304))
        editor.drag(pointer(504, 344))
        editor.end_drag()
        changed = editor.placements[0]
        self.assertEqual((changed.width, changed.height), (400, 240))
        self.assertEqual(len(editor.history), 1)
        stack = editor.building_controls[0]
        self.assertEqual((stack.width, stack.height), (400, 240))
        self.assertAlmostEqual(stack.controls[-1].width, 400 * .8815)
        self.page.on_keyboard_event(key("z"))
        self.assertEqual(editor.placements[0], self.original)
        self.page.on_keyboard_event(key("Y"))
        self.assertEqual(editor.placements[0], changed)
        self.assertEqual(editor.building_controls[0].width, 400)
        self.assertIn("width=400", editor.export_text())
        editor.undo()
        editor.size_fields["width"].value = "360"
        editor.size_fields["height"].value = "220"
        editor.apply_size()
        self.assertFalse(editor.redo_history)

    def test_exact_size_scales_draft_images_and_rejects_invalid_values(self):
        b = replace(self.original, layer_style=None, image_src="DRAFT BUILDINGS/test.svg")
        editor = self.map_editor(b)
        editor.select(0)
        editor.size_fields["width"].value = "500"
        editor.size_fields["height"].value = "120"
        editor.apply_size()
        self.assertEqual((editor.building_controls[0].width, editor.building_controls[0].height), (500, 120))
        self.assertEqual(editor.building_controls[0].fit, ft.BoxFit.FILL)
        changed = editor.placements[0]
        for value in ("nan", "inf", "0", "-30", "3001", "oops"):
            editor.size_fields["width"].value = value
            editor.apply_size()
            self.assertEqual(editor.placements[0], changed)
        self.assertEqual(len(editor.history), 1)

    def test_move_uses_map_coordinates_and_noop_does_not_add_history(self):
        editor = self.map_editor()
        editor.start_drag(pointer(200, 200))
        editor.drag(pointer(260, 230))
        editor.end_drag()
        self.assertEqual((editor.placements[0].left, editor.placements[0].top), (160, 130))
        editor.start_drag(pointer(250, 230))
        editor.end_drag()
        self.assertEqual(len(editor.history), 1)

    def test_roof_tool_draws_exports_and_roundtrips_with_undo(self):
        editor = BuildingDraftEditor(self.page)
        editor.shortcuts.install()
        editor.choose_tool("roof")
        editor.pointer_down(pointer(100, 100))
        editor.pointer_move(pointer(500, 300))
        editor.pointer_up()
        roof = editor.items()[0]
        self.assertEqual((roof.kind, roof.width, roof.height, roof.fill), ("roof", 400, 200, "#C66A41"))
        self.assertEqual(editor.tool, "select")
        validate_item(roof)
        self.assertEqual(len(primitives(roof)), 6)
        root = ET.fromstring(editor.document.svg(editor.floor))
        self.assertEqual(len(root), 6)
        self.assertEqual(root[0].attrib["fill"], "#C66A41")
        exported, width, height = map_svg(editor.document, editor.floor)
        self.assertEqual((width, height), (408, 208))
        self.assertEqual(ET.fromstring(exported)[0].attrib["fill"], "#C66A41")
        loaded = DraftDocument.from_json(editor.document.to_json())
        self.assertEqual(loaded.floors[editor.floor][0], roof)
        self.page.on_keyboard_event(key("z"))
        self.assertFalse(editor.items())
        self.page.on_keyboard_event(key("y"))
        self.assertEqual(editor.items()[0], roof)

    def test_roof_stamp_and_tall_and_square_geometry(self):
        editor = BuildingDraftEditor(self.page)
        editor.choose_tool("roof")
        editor.tap(pointer(100, 100))
        self.assertEqual(editor.items()[0].kind, "roof")
        for width, height in ((300, 500), (200, 200), (400, 200)):
            roof = DraftItem("roof", 10, 20, width, height, rotation=90, fill="#C66A41")
            validate_item(roof)
            self.assertTrue(primitives(roof))

    def test_shortcuts_leave_text_editing_and_exports_alone(self):
        editor = self.map_editor()
        editor.select(0)
        editor.size_fields["width"].value = "500"
        editor.size_fields["height"].value = "300"
        editor.apply_size()
        editor.size_fields["width"].on_focus(None)
        self.page.on_keyboard_event(key("z"))
        self.assertEqual(editor.placements[0].width, 500)
        editor.size_fields["width"].on_blur(None)
        self.page.on_keyboard_event(key("z"))
        self.assertEqual(editor.placements[0], self.original)
        draft = BuildingDraftEditor(self.page)
        draft.shortcuts.install()
        draft.choose_tool("roof")
        draft.tap(pointer(100, 100))
        draft.exporting = True
        self.page.on_keyboard_event(key("z"))
        self.assertEqual(len(draft.items()), 1)

    def test_maximized_window_and_scoped_keyboard_handlers(self):
        editor = self.map_editor()
        editor.select(0)
        editor.size_fields["width"].value = "500"
        editor.size_fields["height"].value = "300"
        editor.apply_size()
        map_handler = self.page.on_keyboard_event
        previous_resize = Mock()
        self.page.on_resize = previous_resize
        window = DraftingWindow(self.page, lambda callback: BuildingDraftEditor(self.page, callback), None)
        window.show()
        self.assertTrue(window.maximized)
        self.assertEqual((window.panel.left, window.panel.top, window.panel.width, window.panel.height), (0, 0, 1400, 900))
        self.assertFalse(window.editor.sidebar.visible)
        window.editor.toggle_properties()
        self.assertTrue(window.editor.sidebar.visible)
        window.editor.choose_tool("roof")
        window.editor.tap(pointer(100, 100))
        self.page.on_keyboard_event(key("z"))
        self.assertFalse(window.editor.items())
        self.assertEqual(editor.placements[0].width, 500)
        self.page.width, self.page.height = 1000, 700
        asyncio.run(self.page.on_resize(None))
        previous_resize.assert_called_once()
        self.assertEqual((window.panel.width, window.panel.height), (1000, 700))
        window.maximize()
        self.assertFalse(window.maximized)
        self.assertTrue(window.resize_grip.visible)
        window.start_move(pointer(10, 10))
        window.move(pointer(40, 40))
        self.assertEqual((window.panel.left, window.panel.top), (46, 42))
        window.remove()
        self.assertEqual(self.page.on_keyboard_event, map_handler)
        self.assertEqual(self.page.on_resize, previous_resize)
        self.page.on_keyboard_event(key("z"))
        self.assertEqual(editor.placements[0], self.original)

    def test_shortcut_key_mapping(self):
        self.assertEqual(history_shortcut(key("Z")), "undo")
        self.assertEqual(history_shortcut(key("z", shift=True)), "redo")
        self.assertEqual(history_shortcut(key("y")), "redo")
        self.assertIsNone(history_shortcut(key("z", ctrl=False)))
        self.assertIsNone(history_shortcut(key("z", alt=True)))

    def test_add_to_map_undo_redo_and_resize_history(self):
        editor = self.map_editor()
        added = replace(self.original, label="New draft", left=600, layer_style=None,
                        image_src="DRAFT BUILDINGS/new.svg")
        editor.add_building(added)
        self.assertEqual(editor.selected, 1)
        editor.size_fields["width"].value = "450"
        editor.size_fields["height"].value = "250"
        editor.apply_size()
        editor.undo()
        self.assertEqual(editor.placements[1], added)
        editor.undo()
        self.assertEqual(editor.placements, [self.original])
        editor.redo()
        self.assertEqual(editor.placements[1], added)
        editor.redo()
        self.assertEqual(editor.placements[1].width, 450)
        self.assertEqual(len(editor.selection.options), 2)

    def test_add_to_empty_map_can_be_undone_and_restored(self):
        editor = CampusPlacementEditor(self.page, [], build_campus_map, 3000, 1200,
                                       building_builder=_building_control)
        editor.viewer = ft.InteractiveViewer(content=editor.build_content())
        editor.add_building(self.original)
        editor.undo()
        self.assertEqual(editor.placements, [])
        self.assertIsNone(editor.selected)
        self.assertTrue(editor.size_button.disabled)
        editor.redo()
        self.assertEqual(editor.placements, [self.original])
        self.assertEqual(editor.selected, 0)

    def test_delete_building_is_disabled_without_a_selection(self):
        editor = self.map_editor()
        self.assertTrue(editor.delete_button.disabled)
        editor.delete_building()
        self.assertEqual(editor.placements, [self.original])
        self.assertFalse(editor.history)
        editor.select(0)
        self.assertFalse(editor.delete_button.disabled)
        editor.select(None)
        self.assertTrue(editor.delete_button.disabled)

    def test_delete_last_building_clears_controls_and_supports_shortcuts(self):
        editor = self.map_editor()
        editor.select(0)
        # Test the real toolbar callback, not just its helper.
        editor.delete_button.on_click(None)
        self.assertEqual(editor.placements, [])
        self.assertEqual(editor.building_controls, [])
        self.assertIsNone(editor.selected)
        self.assertFalse(editor.outline.visible)
        self.assertTrue(editor.delete_button.disabled)
        self.assertTrue(editor.size_button.disabled)
        self.assertFalse(editor.selection.options)
        self.assertEqual(editor.export_text(), "BUILDINGS_ON_MAP = [\n]")
        self.page.on_keyboard_event(key("z"))
        self.assertEqual(editor.placements, [self.original])
        self.assertEqual(editor.selected, 0)
        self.assertFalse(editor.delete_button.disabled)
        self.page.on_keyboard_event(key("y"))
        self.assertEqual(editor.placements, [])

    def test_middle_deletion_restores_order_and_survives_mixed_edit_history(self):
        editor = self.map_editor()
        middle = replace(self.original, label="Middle", left=600)
        last = replace(self.original, label="Last", left=1000)
        editor.add_building(middle)
        editor.add_building(last)
        editor.select(1)
        editor.delete_building()
        self.assertEqual(editor.placements, [self.original, last])
        self.assertEqual(editor.selected, 1)
        self.assertEqual(len(editor.selection.options), 2)
        self.assertNotIn("label='Middle'", editor.export_text())
        editor.size_fields["width"].value = "420"
        editor.size_fields["height"].value = "240"
        editor.apply_size()
        resized = editor.placements[1]
        expected = [
            [self.original, last], [self.original, middle, last],
            [self.original, middle], [self.original],
        ]
        for state in expected:
            editor.undo()
            self.assertEqual(editor.placements, state)
        for state in ([self.original, middle], [self.original, middle, last],
                      [self.original, last], [self.original, resized]):
            editor.redo()
            self.assertEqual(editor.placements, state)
        editor.undo()
        editor.undo()
        editor.select(0)
        editor.delete_building()
        self.assertFalse(editor.redo_history)

    def test_duplicate_button_copies_layers_and_supports_undo_redo(self):
        editor = self.map_editor()
        self.assertTrue(editor.duplicate_button.disabled)
        editor.select(0)
        self.assertFalse(editor.duplicate_button.disabled)
        editor.duplicate_button.on_click(None)
        copy = editor.placements[1]
        self.assertEqual(copy, replace(self.original, label="Test (copy)", left=124, top=124))
        self.assertEqual(editor.placements[0], self.original)
        self.assertEqual(editor.selected, 1)
        self.assertEqual(len(editor.building_controls), 2)
        self.assertEqual(editor.building_controls[1].width, self.original.width)
        self.assertTrue(editor.outline.visible)
        self.assertEqual(editor.outline.left, 124)
        self.assertIn("label='Test (copy)'", editor.export_text())
        self.page.on_keyboard_event(key("z"))
        self.assertEqual(editor.placements, [self.original])
        self.page.on_keyboard_event(key("y"))
        self.assertEqual(editor.placements, [self.original, copy])
        self.assertEqual(editor.selected, 1)

    def test_duplicate_shortcut_creates_unique_labels_and_independent_size(self):
        editor = self.map_editor()
        editor.select(0)
        self.page.on_keyboard_event(key("d"))
        self.page.on_keyboard_event(key("D"))
        self.assertEqual([b.label for b in editor.placements], ["Test", "Test (copy)", "Test (copy 2)"])
        self.assertEqual(editor.selected, 2)
        editor.size_fields["width"].value = "400"
        editor.size_fields["height"].value = "240"
        editor.apply_size()
        self.assertEqual(editor.placements[0], self.original)
        self.assertEqual(editor.placements[1].width, self.original.width)
        self.assertEqual(editor.placements[2].width, 400)
        editor.undo()
        editor.undo()
        self.assertEqual(len(editor.placements), 2)
        editor.redo()
        editor.redo()
        self.assertEqual(editor.placements[2].width, 400)

    def test_duplicate_keeps_draft_source_and_building_metadata(self):
        source = replace(self.original, label="Custom draft", layer_style=None,
            image_src="DRAFT BUILDINGS/custom.svg", opens="Academic Building",
            subtitle="My rooms", text_color="#123456")
        editor = self.map_editor(source)
        editor.select(0)
        editor.duplicate_building()
        copy = editor.placements[1]
        self.assertEqual(copy, replace(source, label="Custom draft (copy)", left=124, top=124))
        self.assertEqual(editor.building_controls[1].src, source.image_src)

    def test_duplicate_at_map_edges_offsets_inward(self):
        source = replace(self.original, left=2680, top=1000)
        editor = self.map_editor(source)
        editor.select(0)
        editor.duplicate_building()
        copy = editor.placements[1]
        self.assertEqual((copy.left, copy.top), (2656, 976))
        self.assertLessEqual(copy.left + copy.width, editor.width)
        self.assertLessEqual(copy.top + copy.height, editor.height)
        self.assertEqual(editor.placements[0], source)

    def test_duplicate_shortcut_ignores_empty_selection_and_text_focus(self):
        editor = self.map_editor()
        self.page.on_keyboard_event(key("d"))
        self.assertEqual(editor.placements, [self.original])
        self.assertFalse(editor.history)
        editor.select(0)
        editor.size_fields["width"].on_focus(None)
        self.page.on_keyboard_event(key("d"))
        self.assertEqual(editor.placements, [self.original])
        editor.size_fields["width"].on_blur(None)
        for event in (key("d", ctrl=False), key("d", shift=True), key("d", alt=True)):
            self.page.on_keyboard_event(event)
            self.assertEqual(editor.placements, [self.original])
        self.page.on_keyboard_event(key("d"))
        self.assertEqual(len(editor.placements), 2)

    def test_duplicate_shortcut_does_not_change_map_from_drafting_window(self):
        editor = self.map_editor()
        editor.select(0)
        window = DraftingWindow(self.page, lambda callback: BuildingDraftEditor(self.page, callback), None)
        window.show()
        self.page.on_keyboard_event(key("d"))
        self.assertEqual(editor.placements, [self.original])
        window.remove()
        self.page.on_keyboard_event(key("d"))
        self.assertEqual(len(editor.placements), 2)


if __name__ == "__main__":
    unittest.main()
