from drafting.models import DraftItem, KINDS, primitives, validate_item
from map.selection import owner_for
from map.workspace_editor import MAP_STAMPS, MAP_TOOLS, MapWorkspaceEditor


def test_evacuation_area_kind_and_primitives():
    assert "evacuation_area" in KINDS
    item = DraftItem(
        "evacuation_area", 100, 120, 220, 140,
        fill="#DCFCE7", color="#16A34A", stroke=3,
        text="Evacuation Area", blocking=False,
    )
    validate_item(item)
    shapes = primitives(item)
    assert shapes
    assert shapes[0]["closed"] is True
    assert shapes[0]["fill"] == "#DCFCE7"


def test_map_editor_exposes_evacuation_area_tool_and_stamp():
    assert ("evacuation_area", "Evacuation Area") in MAP_TOOLS
    assert MAP_STAMPS["evacuation_area"] == (220, 140)


def test_workspace_creates_non_blocking_green_evacuation_area():
    editor = object.__new__(MapWorkspaceEditor)

    class _Value:
        value = "Room"

    editor.properties = {"text": _Value()}
    item = editor.create_item("evacuation_area", 10, 20, 220, 140)

    assert item.kind == "evacuation_area"
    assert item.text == "Evacuation Area"
    assert item.blocking is False
    assert item.fill == "#DCFCE7"
    assert item.color == "#16A34A"
    assert item.stroke == 3


def test_evacuation_area_does_not_auto_attach_to_room():
    room = DraftItem("room", 0, 0, 500, 500)
    area = DraftItem(
        "evacuation_area", 100, 100, 200, 120,
        blocking=False,
    )
    assert owner_for(area, [room]) is None
