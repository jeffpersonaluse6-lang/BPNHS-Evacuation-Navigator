"""Older editor launcher — map_editor.py is the main one now."""

from pathlib import Path

import flet as ft

from map.campus import main


if __name__ == "__main__":
    ft.run(main, assets_dir=str(Path(__file__).resolve().parent / "assets"))
