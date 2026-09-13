"""Actual building images, ordered bottom-to-top in a shared map footprint."""

from dataclasses import dataclass

import flet as ft


ASSET_FOLDER = "BPNHS MAP/ACADEMIC-BUILDING SHS"
ACADEMIC_LAYERS = (
    ("Ground Floor", f"{ASSET_FOLDER}/FixGroundFloor.png"),
    ("Floor 2", f"{ASSET_FOLDER}/Floor2.png"),
    ("Floor 3", f"{ASSET_FOLDER}/Floor3.png"),
    ("Floor 4", f"{ASSET_FOLDER}/FixFloor4.png"),
)
ACADEMIC_ROOF = f"{ASSET_FOLDER}/roofblue.jpg"
LAYER_NAMES = tuple(name for name, _ in ACADEMIC_LAYERS) + ("Roof",)

# Original pixel dimensions and measured outer-wall bounds (not alpha bounds:
# some PNGs have stray white pixels outside the building). No assets are edited.
FLOOR_IMAGE_BOUNDS = {
    "Ground Floor": ((1658, 949), (57, 53, 1600, 879)),
    "Floor 2": ((1735, 907), (57, 13, 1673, 872)),
    "Floor 3": ((1735, 907), (57, 13, 1673, 872)),
    "Floor 4": ((1654, 951), (33, 23, 1630, 868)),
}

# Preserve the ground floor's existing footprint within the placement rectangle.
FLOOR_FOOTPRINT = (57 / 1658, 53 / 949, 1543 / 1658, 826 / 949)

# One rectangular roof: left, top, width, height as placement fractions.
# Keep the same left edge so half the fire-exit stairs remains exposed.
ROOF_FOOTPRINT = (0.0835, 0.0558, 0.8815, 0.8707)

JHS_ASSET_FOLDER = "BPNHS MAP/JHS BUILDING A"
JHS_LAYERS = (
    ("Ground Floor", f"{JHS_ASSET_FOLDER}/GroundFloor.png"),
    ("Floor 2", f"{JHS_ASSET_FOLDER}/Floor2.png"),
    ("Floor 3", f"{JHS_ASSET_FOLDER}/Floor3.png"),
    ("Floor 4", f"{JHS_ASSET_FOLDER}/Floor4.png"),
)
JHS_IMAGE_BOUNDS = {
    "Ground Floor": ((1658, 949), (69, 52, 1596, 874)),
    "Floor 2": ((1734, 907), (54, 13, 1680, 873)),
    "Floor 3": ((1734, 907), (54, 13, 1680, 873)),
    "Floor 4": ((1654, 951), (33, 24, 1628, 868)),
}
JHS_FOOTPRINT = (69 / 1658, 52 / 949, 1527 / 1658, 822 / 949)
# Mirrored building: its fire exit is on the right, so stop at its midpoint.
JHS_ROOF_FOOTPRINT = (69 / 1658, 52 / 949, 1450 / 1658, 822 / 949)

JHS_B_ASSET_FOLDER = "BPNHS MAP/JHS BUILDING B"
JHS_B_LAYERS = (
    ("Ground Floor", f"{JHS_B_ASSET_FOLDER}/GroundFloorB.png"),
    ("Floor 2", f"{JHS_B_ASSET_FOLDER}/Floor2B.png"),
)
# Register the main building walls, not the exterior ground-floor step edges.
JHS_B_IMAGE_BOUNDS = {
    "Ground Floor": ((1854, 848), (5, 9, 1841, 746)),
    "Floor 2": ((1895, 830), (7, 10, 1878, 732)),
}
JHS_B_FOOTPRINT = (5 / 1854, 9 / 848, 1836 / 1854, 737 / 848)
JHS_B_ROOF_FOOTPRINT = (84 / 1854, 9 / 848, 1757 / 1854, 737 / 848)

TVL_A_ASSET_FOLDER = "BPNHS MAP/TVL BUILDING A"
TVL_A_LAYERS = (
    ("Ground Floor", f"{TVL_A_ASSET_FOLDER}/GroundFloorTVLA.png"),
    ("Floor 2", f"{TVL_A_ASSET_FOLDER}/Floor2TVLA.png"),
)
TVL_A_IMAGE_BOUNDS = {
    "Ground Floor": ((1597, 985), (84, 22, 1556, 916)),
    "Floor 2": ((1632, 964), (44, 20, 1589, 908)),
}
TVL_A_FOOTPRINT = (84 / 1597, 22 / 985, 1472 / 1597, 894 / 985)

JHS_C_ASSET_FOLDER = "BPNHS MAP/JHS BUILDING C"
JHS_C_LAYERS = (
    ("Ground Floor", f"{JHS_C_ASSET_FOLDER}/JHS BUILDING C.png"),
)
# Clip the exterior PNG margins at render time; leave the asset unchanged.
JHS_C_IMAGE_BOUNDS = {
    "Ground Floor": ((887, 1774), (131, 14, 758, 1748)),
}
JHS_C_FOOTPRINT = (0.0, 0.0, 1.0, 1.0)


@dataclass(frozen=True)
class BuildingLayerStyle:
    label: str
    layers: tuple[tuple[str, str], ...]
    image_bounds: dict
    footprint: tuple[float, float, float, float]
    roof_source: str
    roof_footprint: tuple[float, float, float, float]
    ground_floor_bottom_extension: bool = False
    roof_image_bounds: tuple[tuple[int, int], tuple[int, int, int, int]] | None = None
    flip_vertical: bool = False


BUILDING_LAYER_STYLES = {
    "academic": BuildingLayerStyle(
        "Academic Building", ACADEMIC_LAYERS, FLOOR_IMAGE_BOUNDS,
        FLOOR_FOOTPRINT, ACADEMIC_ROOF, ROOF_FOOTPRINT,
    ),
    "jhs": BuildingLayerStyle(
        "JHS Building A", JHS_LAYERS, JHS_IMAGE_BOUNDS,
        JHS_FOOTPRINT, f"{JHS_ASSET_FOLDER}/roofblue.jpg", JHS_ROOF_FOOTPRINT,
    ),
    "jhs_b": BuildingLayerStyle(
        "JHS Building B", JHS_B_LAYERS, JHS_B_IMAGE_BOUNDS,
        JHS_B_FOOTPRINT, f"{JHS_B_ASSET_FOLDER}/rooforange.png",
        JHS_B_ROOF_FOOTPRINT, ground_floor_bottom_extension=True,
        roof_image_bounds=((569, 439), (10, 10, 554, 423)),
    ),
    "tvl_a": BuildingLayerStyle(
        "TVL Building A", TVL_A_LAYERS, TVL_A_IMAGE_BOUNDS,
        TVL_A_FOOTPRINT, ACADEMIC_ROOF, TVL_A_FOOTPRINT,
    ),
    "tvl_b": BuildingLayerStyle(
        "TVL Building B", ACADEMIC_LAYERS, FLOOR_IMAGE_BOUNDS,
        FLOOR_FOOTPRINT, ACADEMIC_ROOF, ROOF_FOOTPRINT,
        flip_vertical=True,
    ),
    "jhs_c": BuildingLayerStyle(
        "JHS Building C", JHS_C_LAYERS, JHS_C_IMAGE_BOUNDS,
        JHS_C_FOOTPRINT, f"{JHS_C_ASSET_FOLDER}/roofyellow.jpg",
        JHS_C_FOOTPRINT,
    ),
}


def building_layer_names(building_key: str) -> tuple[str, ...]:
    """Only offer floors that actually exist for the chosen building."""
    return tuple(name for name, _ in BUILDING_LAYER_STYLES[building_key].layers) + ("Roof",)


def _roof_control(style: BuildingLayerStyle, width: float, height: float, visible: bool):
    """Fit the opaque roof area, not a PNG's transparent canvas margins."""
    left, top, roof_width, roof_height = style.roof_footprint
    target_width = roof_width * width
    target_height = roof_height * height
    image = ft.Image(
        src=style.roof_source, width=target_width, height=target_height,
        fit=ft.BoxFit.FILL, semantics_label=f"{style.label} rectangular roof",
        error_content=ft.Text("Could not load roof."),
    )
    if style.roof_image_bounds is None:
        image.left = left * width
        image.top = top * height
        image.visible = visible
        return image
    (image_width, image_height), (x0, y0, x1, y1) = style.roof_image_bounds
    scale_x = target_width / (x1 - x0)
    scale_y = target_height / (y1 - y0)
    image.left = -x0 * scale_x
    image.top = -y0 * scale_y
    image.width = image_width * scale_x
    image.height = image_height * scale_y
    return ft.Container(
        left=left * width, top=top * height,
        width=target_width, height=target_height, visible=visible,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        content=ft.Stack(width=target_width, height=target_height, controls=[image]),
    )


def _aligned_floor(
    name: str, source: str, width: float, height: float,
    visible: bool, style: BuildingLayerStyle,
):
    """Map each image's outer walls to the same bounds using render-time clipping."""
    (image_width, image_height), (x0, y0, x1, y1) = style.image_bounds[name]
    left, top, footprint_width, footprint_height = style.footprint
    target_width = footprint_width * width
    target_height = footprint_height * height
    scale_x = target_width / (x1 - x0)
    scale_y = target_height / (y1 - y0)
    viewport_height = target_height
    if name == "Ground Floor" and style.ground_floor_bottom_extension:
        viewport_height += (image_height - y1) * scale_y
    return ft.Container(
        left=left * width,
        top=top * height,
        width=target_width,
        height=viewport_height,
        visible=visible,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        content=ft.Stack(
            width=target_width,
            height=viewport_height,
            controls=[
                ft.Image(
                    src=source,
                    left=-x0 * scale_x,
                    top=-y0 * scale_y,
                    width=image_width * scale_x,
                    height=image_height * scale_y,
                    fit=ft.BoxFit.FILL,
                    semantics_label=f"{style.label} {name}",
                    error_content=ft.Text(f"Could not load {name}."),
                )
            ],
        ),
    )


def build_building_layers(
    width: float,
    height: float,
    top_layer: str = "Roof",
    building_key: str = "academic",
) -> ft.Stack:
    """Keep floors registered to wall bounds and show only the active floor."""
    style = BUILDING_LAYER_STYLES[building_key]
    if top_layer not in building_layer_names(building_key):
        raise ValueError(f"Unknown building layer: {top_layer}")
    selected_floor = style.layers[-1][0] if top_layer == "Roof" else top_layer
    controls: list[ft.Control] = [
        _aligned_floor(name, source, width, height, name == selected_floor, style)
        for name, source in style.layers
    ]
    controls.append(_roof_control(style, width, height, top_layer == "Roof"))
    stack = ft.Stack(width=width, height=height, controls=controls)
    if style.flip_vertical:
        # Reflect top-to-bottom; preserve the left/right stair locations.
        stack.scale = ft.Scale(scale_x=1, scale_y=-1, alignment=ft.Alignment.CENTER)
    return stack


