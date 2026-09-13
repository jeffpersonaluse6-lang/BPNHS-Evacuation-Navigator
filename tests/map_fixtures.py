"""Synthetic asset-backed test buildings; never used as the real map layout."""

from map.layers import BUILDING_LAYER_STYLES
from map.placements import PlacedBuilding

EXAMPLE_PLACEMENTS = [
    PlacedBuilding(style.label.upper(),55+index*280,50,250,200,"#F1DF65",
        opens=style.label,layer_style=key)
    for index,(key,style) in enumerate(BUILDING_LAYER_STYLES.items())
]
