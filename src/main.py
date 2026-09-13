"""Normal user entry point — navigation only, no editor tools."""

from pathlib import Path

import flet as ft

from navigation.app import main


if __name__ == "__main__":
    ft.run(main, assets_dir=str(Path(__file__).resolve().parent / "assets"))
