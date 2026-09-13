"""Building/floor image rendering — no editor imports."""

import math
import flet as ft
from .layers import build_building_layers
from .placements import PlacedBuilding

def building_control(
    building: PlacedBuilding, *, show_coordinates: bool = False, **layers,
) -> ft.Control:
    control=_unrotated_building_control(building,show_coordinates=show_coordinates,**layers)
    if building.mirrored:
        # Flip instead of overwriting TVL B's existing vertical reflection.
        control.left=control.top=0
        control=ft.Stack(left=building.left,top=building.top,width=building.width,height=building.height,
            scale=ft.Scale(scale_x=-1,scale_y=1,alignment=ft.Alignment.CENTER),controls=[control])
    if building.rotation:
        control.rotate=ft.Rotate(angle=math.radians(building.rotation),alignment=ft.Alignment.TOP_LEFT)
    return control


def _unrotated_building_control(
    building: PlacedBuilding, academic_layer: str = "Roof", jhs_layer: str = "Roof",
    jhs_b_layer: str = "Roof",
    tvl_a_layer: str = "Roof",
    tvl_b_layer: str = "Roof",
    jhs_c_layer: str = "Roof",
    show_coordinates: bool = False,
) -> ft.Control:
    if building.layer_style:
        top_layer = {
            "academic": academic_layer, "jhs": jhs_layer, "jhs_b": jhs_b_layer,
            "tvl_a": tvl_a_layer,
            "tvl_b": tvl_b_layer,
            "jhs_c": jhs_c_layer,
        }[building.layer_style]
        layers = build_building_layers(
            building.width, building.height, top_layer, building.layer_style
        )
        layers.left = building.left
        layers.top = building.top
        return layers
    if building.image_src:
        # Render the raw asset — no roof, color, or label overlay.
        return ft.Image(
            src=building.image_src,
            left=building.left,
            top=building.top,
            width=building.width,
            height=building.height,
            fit=ft.BoxFit.FILL,
            semantics_label=f"{building.label} ground floor plan",
            error_content=ft.Text("Floor-plan image could not be loaded."),
        )

    label_size = max(8, min(19, building.width / 10, building.height / 3))
    detail_size = max(7, min(12, label_size - 3))
    details = building.subtitle
    if show_coordinates and building.width >= 80 and building.height >= 50:
        coordinates = f"x={building.left}, y={building.top}"
        details = f"{details}\n{coordinates}" if details else coordinates

    return ft.Container(
        left=building.left,
        top=building.top,
        width=building.width,
        height=building.height,
        bgcolor=building.color,
        border_radius=6,
        border=ft.Border.all(3, "#FFFFFF"),
        alignment=ft.Alignment.CENTER,
        content=ft.Column(
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=1,
            controls=[
                ft.Text(
                    building.label,
                    color=building.text_color,
                    size=label_size,
                    weight=ft.FontWeight.BOLD,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    details,
                    color=building.text_color,
                    size=detail_size,
                    text_align=ft.TextAlign.CENTER,
                    visible=bool(details) and building.width >= 65,
                ),
            ],
        ),
    )
