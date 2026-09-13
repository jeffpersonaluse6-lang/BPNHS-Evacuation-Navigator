"""Development-only map editor launcher, beside the shared assets folder."""

from pathlib import Path

import flet as ft

from map.campus import main


if __name__ == "__main__":
    ft.run(main, assets_dir=str(Path(__file__).resolve().parent / "assets"))
