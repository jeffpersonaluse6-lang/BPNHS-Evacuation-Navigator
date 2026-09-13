"""Asset regressions that can run without opening a desktop window."""

import importlib
import os
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import patch

import flet as ft


SOURCE_DIR = Path(__file__).resolve().parents[1] / "src"
ASSETS_DIR = SOURCE_DIR / "assets"


class MapAssetsTests(unittest.TestCase):
    def test_launchers_register_shared_assets(self):
        # Run as __main__ to exercise each real startup branch, without a UI.
        with patch.object(sys, "path", [str(SOURCE_DIR), *sys.path]):
            for entry in ("main.py", "map_editor.py", "map_preview.py", "map/campus.py"):
                with self.subTest(entry=entry), patch.object(ft, "run") as launch:
                    runpy.run_path(str(SOURCE_DIR / entry), run_name="__main__")
                    self.assertEqual(
                        Path(launch.call_args.kwargs["assets_dir"]), ASSETS_DIR
                    )

    def test_flet_cli_default_for_preview_finds_shared_assets(self):
        # Flet's CLI overrides ft.run(assets_dir=...) with entry.parent/assets.
        # The thin preview launcher must stay next to the actual assets folder.
        cli_default = (SOURCE_DIR / "map_preview.py").parent / "assets"
        flet_app = importlib.import_module("flet.app")
        with patch.dict(os.environ, {"FLET_ASSETS_DIR": str(cli_default)}):
            actual = getattr(flet_app, "__get_assets_dir_path")(str(ASSETS_DIR))
        self.assertEqual(Path(actual), ASSETS_DIR)
        self.assertTrue(Path(actual).is_dir())

    def test_all_placed_images_and_floor_roofs_exist(self):
        with patch.object(sys, "path", [str(SOURCE_DIR), *sys.path]):
            from map.campus import BUILDINGS_ON_MAP
            from map.layers import BUILDING_LAYER_STYLES

        sources = {b.image_src for b in BUILDINGS_ON_MAP if b.image_src}
        for style in BUILDING_LAYER_STYLES.values():
            sources.update(source for _, source in style.layers)
            sources.add(style.roof_source)
        self.assertTrue(sources)
        for source in sorted(sources):
            with self.subTest(source=source):
                image = ASSETS_DIR / source
                self.assertTrue(image.is_file(), f"Missing image: {image}")
                self.assertGreater(image.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
