from drafting.models import DraftItem, KINDS, primitives, validate_item
from map.selection import owner_for
from map.workspace_editor import LINE_KINDS, MAP_TOOLS, MapWorkspaceEditor


def test_road_kind_is_valid_and_draws_as_resizable_rectangle():
    assert "road" in KINDS
    road = DraftItem(
        "road", 10, 20, 180, 70,
        stroke=2, color="#6B7280", fill="#9CA3AF",
        text="Road / Path", blocking=False,
    )
    validate_item(road)
    shapes = primitives(road)
    assert shapes
    shape = shapes[0]
    assert shape["closed"] is True
    assert shape["fill"] == "#9CA3AF"
    assert shape["points"] == [(0, 0), (180, 0), (180, 70), (0, 70)]


def test_map_editor_exposes_road_tool_as_area_not_line_kind():
    assert ("road", "Road / Path") in MAP_TOOLS
    assert "road" not in LINE_KINDS


def test_workspace_creates_non_blocking_road_area():
    editor = object.__new__(MapWorkspaceEditor)

    class _Value:
        value = "Room"

    editor.properties = {"text": _Value()}
    road = editor.create_item("road", 10, 20, 200, 80)
    assert road.kind == "road"
    assert road.text == "Road / Path"
    assert road.blocking is False
    assert road.fill == "#9CA3AF"
    assert road.color == "#6B7280"
    assert road.stroke == 2


def test_road_does_not_auto_attach_to_room():
    room = DraftItem("room", 0, 0, 500, 500)
    road = DraftItem("road", 100, 100, 200, 80, blocking=False)
    assert owner_for(road, [room]) is None


def test_road_hit_testing_uses_full_rectangle():
    road = DraftItem("road", 0, 0, 200, 80, blocking=False)
    assert road.contains(100, 70, tolerance=0)
    assert not road.contains(100, 90, tolerance=0)
