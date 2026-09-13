import flet.testing as ftt


async def test_main_app_screen_loads(flet_app: ftt.FletTestApp):
    """The user-facing entry point opens navigation, never development tools."""
    tester = flet_app.tester

    await tester.pump_and_settle()

    assert (await tester.find_by_text("BPNHS Evacuation Navigator")).count == 1
    assert (await tester.find_by_text("Move user")).count == 1
    for label in ("BPNHS Map Workspace", "Railing / barrier", "Save map", "Edit map"):
        assert (await tester.find_by_text(label)).count == 0
