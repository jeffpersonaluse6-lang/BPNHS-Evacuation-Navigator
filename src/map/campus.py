"""Development-only map editor launcher and legacy placement-editor compatibility.

Run src/map_editor.py (or the older src/map_preview.py) to edit the map.
Normal users launch src/main.py; it never imports this module.
Original placement constants now live in map/placements.py.
"""

from pathlib import Path
import sys
import flet as ft

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from map.layers import LAYER_NAMES, building_layer_names
from map.placements import (CAMPUS_WIDTH, CAMPUS_HEIGHT, ACADEMIC_FLOORPLAN_ASSET,
    BUILDINGS_ON_MAP, PlacedBuilding, navigable_building_at)
from map.building_renderer import building_control

SHOW_EDITOR_GRID = True

def _grid_controls() -> list[ft.Control]:
    if not SHOW_EDITOR_GRID:
        return []

    controls: list[ft.Control] = []
    for x in range(100, CAMPUS_WIDTH, 100):
        controls.append(
            ft.Container(
                left=x,
                top=0,
                width=1,
                height=CAMPUS_HEIGHT,
                bgcolor=ft.Colors.with_opacity(0.18, "#66809A"),
            )
        )
    for y in range(100, CAMPUS_HEIGHT, 100):
        controls.append(
            ft.Container(
                left=0,
                top=y,
                width=CAMPUS_WIDTH,
                height=1,
                bgcolor=ft.Colors.with_opacity(0.18, "#66809A"),
            )
        )
    return controls


def _building_control(building: PlacedBuilding, **layers) -> ft.Control:
    """Legacy editor wrapper; coordinate labels never leak into the main app."""
    return building_control(building, show_coordinates=SHOW_EDITOR_GRID, **layers)


def build_campus_map(
    marker: ft.Container | None = None, academic_layer: str = "Roof",
    jhs_layer: str = "Roof",
    jhs_b_layer: str = "Roof",
    tvl_a_layer: str = "Roof",
    tvl_b_layer: str = "Roof",
    jhs_c_layer: str = "Roof",
    placements: list[PlacedBuilding] | None = None,
) -> ft.Stack:
    """Build the building-only campus map. No trees or roads are drawn."""
    controls: list[ft.Control] = [
        ft.Container(
            width=CAMPUS_WIDTH,
            height=CAMPUS_HEIGHT,
            bgcolor="#EDF8FA",
            border=ft.Border.all(4, "#7D8C98"),
        )
    ]
    controls.extend(_grid_controls())
    controls.extend(
        _building_control(building, academic_layer=academic_layer,jhs_layer=jhs_layer,
            jhs_b_layer=jhs_b_layer,tvl_a_layer=tvl_a_layer,tvl_b_layer=tvl_b_layer,jhs_c_layer=jhs_c_layer)
        for building in (BUILDINGS_ON_MAP if placements is None else placements)
    )
    if marker is not None:
        controls.append(marker)
    return ft.Stack(width=CAMPUS_WIDTH, height=CAMPUS_HEIGHT, controls=controls)


def legacy_preview_main(page: ft.Page):
    """Open a live campus-placement preview."""
    page.title = "BPNHS Campus Map Editor"
    page.padding = 0
    page.spacing = 0
    page.bgcolor = "#F5F7FB"
    page.theme_mode = ft.ThemeMode.LIGHT

    if __package__:
        from .editor import CampusPlacementEditor
    else:
        from map.editor import CampusPlacementEditor

    editor = CampusPlacementEditor(
        page, BUILDINGS_ON_MAP, build_campus_map, CAMPUS_WIDTH, CAMPUS_HEIGHT,
        building_builder=_building_control,
    )

    viewer = ft.InteractiveViewer(
        content=editor.build_content(),
        pan_enabled=False,
        constrained=False,
        min_scale=0.5,
        max_scale=4.0,
        boundary_margin=ft.Margin.all(300),
    )
    editor.viewer = viewer

    async def reset_view(event):
        await viewer.reset()

    drafting_window = None

    async def add_draft_to_map(document, floor):
        from drafting.assets import save_map_draft

        source, width, height = save_map_draft(document, floor, Path(__file__).resolve().parent.parent / "assets")
        factor = min(1, 340 / max(width, height))
        building = PlacedBuilding(
            label=document.name, left=100, top=100,
            width=round(width * factor, 2), height=round(height * factor, 2),
            color="#FFFFFF", subtitle=f"Draft - {floor}", image_src=source,
        )
        editor.add_building(building)
        await viewer.reset()

    def open_building_drafter(event):
        nonlocal drafting_window
        from drafting.editor import open_drafting_dialog

        if drafting_window is not None and drafting_window.overlay in page.overlay:
            return
        drafting_window = open_drafting_dialog(page, add_draft_to_map)

    def select_layer(event):
        editor.layer_options = dict(
            academic_layer=academic_selector.value, jhs_layer=jhs_selector.value,
            jhs_b_layer=jhs_b_selector.value,
            tvl_a_layer=tvl_a_selector.value,
            tvl_b_layer=tvl_b_selector.value,
            jhs_c_layer=jhs_c_selector.value,
        )
        editor.refresh()

    academic_selector = ft.Dropdown(
        label="Academic Building top layer", width=260, value="Roof",
        options=[ft.DropdownOption(name) for name in LAYER_NAMES], on_select=select_layer,
    )
    jhs_selector = ft.Dropdown(
        label="JHS Building A top layer", width=260, value="Roof",
        options=[ft.DropdownOption(name) for name in LAYER_NAMES], on_select=select_layer,
    )
    jhs_b_selector = ft.Dropdown(
        label="JHS Building B top layer", width=260, value="Roof",
        options=[ft.DropdownOption(name) for name in building_layer_names("jhs_b")],
        on_select=select_layer,
    )
    tvl_a_selector = ft.Dropdown(
        label="TVL Building A top layer", width=260, value="Roof",
        options=[ft.DropdownOption(name) for name in building_layer_names("tvl_a")],
        on_select=select_layer,
    )
    tvl_b_selector = ft.Dropdown(
        label="TVL Building B top layer", width=260, value="Roof",
        options=[ft.DropdownOption(name) for name in building_layer_names("tvl_b")],
        on_select=select_layer,
    )
    jhs_c_selector = ft.Dropdown(
        label="JHS Building C top layer", width=260, value="Roof",
        options=[ft.DropdownOption(name) for name in building_layer_names("jhs_c")],
        on_select=select_layer,
    )

    page.add(
        ft.Column(
            expand=True,
            spacing=0,
            controls=[
                ft.Container(
                    bgcolor="#12345A",
                    padding=ft.Padding.symmetric(horizontal=16, vertical=8),
                    content=ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.EDIT_LOCATION, color="#FFFFFF", size=28),
                            ft.Column(
                                expand=True,
                                spacing=0,
                                controls=[
                                    ft.Text(
                                        "BPNHS Campus Map Editor",
                                        color="#FFFFFF",
                                        size=22,
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                    ft.Text(
                                        "Move or resize buildings, then export placements to src/map/placements.py.",
                                        color="#DCE8F7",
                                        size=13,
                                    ),
                                ],
                            ),
                            ft.IconButton(
                                icon=ft.Icons.REFRESH,
                                icon_color="#FFFFFF",
                                tooltip="Reset preview position and zoom",
                                on_click=reset_view,
                            ),
                            ft.Button(
                                "Draft building",
                                on_click=open_building_drafter,
                                tooltip="Draw editable walls, rooms, doors, stairs and roofs",
                            ),
                        ],
                    ),
                ),
                ft.Container(
                    bgcolor="#FFFFFF",
                    padding=ft.Padding.symmetric(horizontal=16, vertical=4),
                    content=ft.Row(
                        scroll=ft.ScrollMode.AUTO,
                        controls=[
                            ft.Text(
                                "No trees or roads | Grid: 100 units",
                                size=14,
                                color="#31475E",
                            ),
                            academic_selector,
                            jhs_selector,
                            jhs_b_selector,
                            tvl_a_selector,
                            tvl_b_selector,
                            jhs_c_selector,
                        ],
                    ),
                ),
                ft.Container(
                    bgcolor="#FFFFFF",
                    padding=ft.Padding.symmetric(horizontal=16, vertical=4),
                    content=editor.toolbar,
                ),
                ft.Container(
                    expand=True,
                    padding=8,
                    content=ft.Container(
                        expand=True,
                        bgcolor="#D5DEE8",
                        border_radius=12,
                        clip_behavior=ft.ClipBehavior.HARD_EDGE,
                        content=viewer,
                    ),
                ),
            ],
        )
    )


def main(page: ft.Page):
    """All campus placement and building drafting tools now share one editor."""
    from map.workspace_editor import MapWorkspaceEditor
    page.spacing=0
    page.bgcolor="#F5F7FB"
    page.theme_mode=ft.ThemeMode.LIGHT
    MapWorkspaceEditor(page).mount()


if __name__ == "__main__":
    ft.run(main, assets_dir=str(Path(__file__).resolve().parent.parent / "assets"))
