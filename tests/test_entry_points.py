"""Startup separation and finished-map interoperability without desktop automation."""

from dataclasses import replace
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

SOURCE_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE_DIR))

import flet as ft
from drafting.models import DraftItem
from map_fixtures import EXAMPLE_PLACEMENTS as BUILDINGS_ON_MAP
from map.scene import CAMPUS, MapScene, scope_key
from map.scene_store import load_scene, save_scene
from navigation import app as runtime
from navigation.data import MARKER_SIZE


def page_stub():
    return SimpleNamespace(width=1400, height=900, update=Mock(), add=Mock(),
        clean=Mock(), run_task=Mock(), show_dialog=Mock(), pop_dialog=Mock(),
        overlay=[], on_keyboard_event=None)


def ui_labels(control):
    """Include hidden controls too: hiding an editor button is not separation."""
    labels = []
    pending = [control]
    seen = set()
    while pending:
        node = pending.pop()
        if not isinstance(node, ft.Control) or id(node) in seen:
            continue
        seen.add(id(node))
        for field in ("value", "content", "label", "tooltip"):
            value = getattr(node, field, None)
            if isinstance(value, str):
                labels.append(value)
        for field in ("content", "controls", "actions", "title", "subtitle", "leading", "trailing"):
            value = getattr(node, field, None)
            pending.extend(value if isinstance(value, (list, tuple)) else [value])
    return labels


class EntryPointTests(unittest.TestCase):
    def setUp(self):
        from player_fixtures import isolate_player_settings
        isolate_player_settings(self)
        control_update = patch.object(ft.Control, "update")
        control_update.start()
        self.addCleanup(control_update.stop)

    def test_each_launcher_starts_only_its_intended_screen(self):
        for entry, module, title in (
            ("main.py", "navigation.app", "BPNHS Evacuation Navigator"),
            ("map_editor.py", "map.campus", "BPNHS Map Workspace"),
            ("map_preview.py", "map.campus", "BPNHS Map Workspace"),
        ):
            with self.subTest(entry=entry), patch.object(ft, "run") as launch:
                runpy.run_path(str(SOURCE_DIR / entry), run_name="__main__")
                launch.assert_called_once()
                target = launch.call_args.args[0]
                self.assertEqual(target.__module__, module)
                self.assertEqual(Path(launch.call_args.kwargs["assets_dir"]), SOURCE_DIR / "assets")
                page = page_stub()
                target(page)
                self.assertEqual(page.title, title)
                labels = ui_labels(page.add.call_args.args[0])
                if entry == "main.py":
                    self.assertIn("BPNHS Evacuation Navigator", labels)
                    self.assertNotIn("BPNHS Map Workspace", labels)
                else:
                    self.assertIn("Save map", labels)
                    self.assertIn("Railing / barrier", labels)

    def test_main_startup_never_imports_editor_modules_in_fresh_process(self):
        script = r'''
import importlib.abc
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch
sys.path.insert(0, sys.argv[1])
blocked = {
    'map.campus', 'map.workspace_editor', 'map.editor', 'map.demo_preview',
    'drafting.editor', 'drafting.window', 'drafting.assets', 'editor_shortcuts',
    'map.history', 'map.geometry', 'map.export', 'map.alignment', 'map.reference_layers',
    'map.selection', 'map.building_editor', 'map.canvas_size', 'map.free_build', 'map.interaction', 'map.railing_editor', 'map.stair_editor', 'map.collision_editor',
}
class NoEditorImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in blocked:
            raise AssertionError('Runtime imported editor module: ' + fullname)
sys.meta_path.insert(0, NoEditorImports())
import flet as ft
from map.scene_store import load_scene
from map.scene import MapScene, CAMPUS, scope_key
from drafting.models import DraftItem
scene = load_scene(Path(sys.argv[1]) / 'missing-startup-test-map.json')
building = DraftItem('building', 100, 100, 500, 300, floor_count=2)
stair = DraftItem('stairs', 200, 100, 120, 240, fade_when_obstructing=False)
scene.floors = {CAMPUS: [building], scope_key(building, 'Floor 1'): [stair], scope_key(building, 'Floor 2'): []}
scene = MapScene.from_json(scene.to_json())
page = SimpleNamespace(update=Mock(), add=Mock(), clean=Mock(), run_task=Mock())
with patch('navigation.app.load_scene', return_value=scene), patch.object(ft, 'run') as launch:
    runpy.run_path(str(Path(sys.argv[1]) / 'main.py'), run_name='__main__')
    launch.assert_called_once()
    launch.call_args.args[0](page)
assert page.title == 'BPNHS Evacuation Navigator'
assert not blocked.intersection(sys.modules), blocked.intersection(sys.modules)
print('Runtime-only startup verified')
'''
        result = subprocess.run([sys.executable, "-B", "-c", script, str(SOURCE_DIR)],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Runtime-only startup verified", result.stdout)

    def test_runtime_contains_no_editor_or_development_controls_on_campus_or_floor(self):
        page = page_stub()
        app = runtime.EvacuationApp(page, scene=MapScene(BUILDINGS_ON_MAP))
        forbidden = {"Edit map", "Save map", "Load map", "Undo", "Redo", "Delete",
            "Edit This Building", "Save Building Changes", "Collision Thickness",
            "Duplicate", "Properties", "Show demo zones", "Hide demo zones",
            "Railing / barrier", "Test walk", "Editing layer", "Export placements", "Map size", "Resize map"}
        for view in ("campus", "floor"):
            if view == "floor":
                app.enter_building("Academic Building")
            labels = ui_labels(page.add.call_args.args[0])
            self.assertFalse(forbidden.intersection(labels), forbidden.intersection(labels))
            self.assertFalse(any("x=" in text and "y=" in text for text in labels))
            self.assertFalse(app.state.show_demo_zones)
        self.assertFalse(hasattr(app, "on_edit"))
        self.assertFalse(hasattr(app, "edit_map"))

    def test_runtime_reads_saved_buildings_floors_roofs_and_railings_without_writing(self):
        scene = MapScene(BUILDINGS_ON_MAP)
        parent = replace(scene.buildings()[0], x=123, y=77, width=400, rotation=25)
        scene.floors[CAMPUS][0] = parent
        campus_rail = DraftItem("railing", 300, 0, 0, scene.height, stroke=10)
        floor_rail = DraftItem("railing", 300, 0, 0, 751, stroke=10)
        roof = DraftItem("roof", 100, 100, 300, 200, fill="#C66A41")
        scene.floors[CAMPUS].append(campus_rail)
        scene.floors[scope_key(parent, "Floor 1")] = [floor_rail]
        scene.floors[scope_key(parent, "Roof")] = [roof]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "finished-map.json"
            save_scene(scene, path)
            original = path.read_bytes()
            with patch.object(runtime, "load_scene", side_effect=lambda: load_scene(path)), \
                    patch("map.scene_store.save_scene") as write:
                app = runtime.EvacuationApp(page_stub())
                self.assertEqual(app.scene.snapshot(), scene.snapshot())
                app.state.move_mode = True
                app.state.marker_x = 200 - MARKER_SIZE / 2
                app.state.marker_y = 700 - MARKER_SIZE / 2
                app.move_user(500, 0)
                self.assertLess(app._marker_center()[0], 300)
                app.enter_building(parent.opens)
                app.state.marker_x = 200 - MARKER_SIZE / 2
                app.state.marker_y = 500 - MARKER_SIZE / 2
                app.move_user(500, 0)
                self.assertLess(app._marker_center()[0], 300)
                write.assert_not_called()
            self.assertEqual(path.read_bytes(), original)

    def test_preview_return_controls_exist_only_in_editor_preview(self):
        from map.demo_preview import EditorDemoPreview
        page = page_stub()
        return_callback = Mock()
        preview = EditorDemoPreview(page, MapScene(BUILDINGS_ON_MAP), return_callback)
        self.assertIn("Edit map", ui_labels(page.add.call_args.args[0]))
        preview.enter_building("Academic Building")
        self.assertIn("Show demo zones", ui_labels(page.add.call_args.args[0]))
        preview.return_to_editor()
        return_callback.assert_called_once()
        self.assertFalse(preview.active)


if __name__ == "__main__":
    unittest.main()
