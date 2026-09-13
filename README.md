# Bpnhs app

## Run the app

### Main application (normal users)

From `C:\BPNHS\BPNHS`, run:

```powershell
C:\BPNHS\.venv\Scripts\flet.exe run src\main.py
```

This starts the BPNHS Evacuation Navigator only. It reads the finished map from
`src/assets/map_workspace.json` (or an empty canvas when no saved workspace
exists). Buildings, floors, roofs and railing/wall collisions are shared map data;
editing tools, save controls, coordinate overlays and editor buttons are not part
of the user-facing application.

The player is a simple blue dot. **Player size** adjusts its diameter from 8–52
map units (20 by default) without changing buildings or collision clearance.
Click the blue dot or **Select player** to open **Collision radius (map units)**.
Use the slider (1–100) or enter a fractional radius and press Enter. A cyan
collision circle updates immediately and follows the player's center. Radius is
independent of dot diameter and stays constant through building/floor changes.
**Save player settings** saves both sizes to `src/assets/player_settings.json`;
**Load player settings** restores them, and both applications load them at startup.
These settings never change the saved map. In the editor, use **Test walk** then
select the player for the same control; **Deselect player** hides the guide.
Joystick movement uses a smooth trailing camera that continues settling after
you stop. Following changes only camera position, preserving zoom, rotation and
authored building dimensions; floor changes affect visibility, not scale.
If you pan away before entering Move user mode, the camera smoothly returns
before allowing movement, keeping the player visible. Manual gestures in Map
mode stop automatic follow. The editor's evacuation demo uses the same behavior.

### Map editor (separate development tool)

From `C:\BPNHS\BPNHS`, run:

```powershell
C:\BPNHS\.venv\Scripts\flet.exe run src\map_editor.py
```

This launches the editor with the shared `src/assets` folder for all floors,
roofs, and saved drafts. The older `src/map_preview.py` entry point still works.
Neither entry point is launched or imported by `src/main.py`.

**Map size** changes the campus canvas width and height (100–5000 map units per
dimension). Click **Resize map**, then **Save map** to persist the new size for
both applications. Objects stay in place and are not scaled or deleted. Shrinking
is blocked if it would clip existing content. Ctrl+Z/Ctrl+Y undo/redo a resize.

Outdoor objects are edited on the main map canvas. **Building** opens a dedicated
Building Editor over the **entire map**, with the existing campus faded and locked.
There is no starter rectangle, small drawing area or footprint setup. Draw Floor 1
where the building actually belongs, press **Floor 1 Done → next** to continue
upward, and use **Add Building to Map** to save the complete structure and return.
Bounds are calculated from all your components without shifting their coordinates.
There is no fixed floor-count limit for free builds (saved-file size and object
validation still apply). Select a completed free building on the campus and click
**Edit This Building** beside its name to reopen all its floors and objects.
**Save Building Changes** updates its existing ID and returns to the campus;
**Cancel** offers Keep Editing / Discard Changes when there are unsaved edits.
Selecting a building floor also opens this dedicated workspace.
**Floor section** adds a visible, non-blocking floor surface; **Roof** adds roofing.

Box-select multiple components, **Group/Ungroup**, and move/duplicate/delete them
together. Ordinary clicks expand only intentionally created manual groups, never
attachments or proximity. **Select structure** explicitly selects related parts
temporarily when **Smart structure select** is enabled; it does not create groups.
**Ungroup** removes the complete selected manual group, preserves attachments, and
returns to a single-object selection. Ctrl+C/V copies/pastes editor
bundles, including all floors when copying a building.

**Railing / barrier** draws thicker, visible rails with posts. The inspector's
**Railing thickness** slider updates immediately and keeps one undo entry per
adjustment. Visual strokes and **Collision Thickness** are separate settings;
the initial collision width matches the default rails/posts. **Blocks player** controls
collision; **Show collisions** displays their physical boundaries. **Test walk**
checks the active layer using the joystick. The editor-only **Run evacuation demo**
preview uses the same unsaved scene; its **Edit map** button returns to the workspace
without losing it. Those development controls do not exist in the normal app.

**Save map** stores the entire editable scene in `src/assets/map_workspace.json`
and reloads it on the next launch. Existing image assets are not changed. PNG
floor-plan lines are references, not automatic collision walls: trace them with
**Room**, **Wall** or **Railing / barrier** where movement must be blocked.

**Room** creates collision along its perimeter automatically, leaving its interior
free. **Door**, **Double door** and **Opening** cut walkable gaps in aligned room
walls and standalone walls; click a wall to align a new doorway. Moving/resizing
either object updates the solid wall sections, including collision guides. Doors
currently represent open passages; windows do not cut wall collision.

Select a room, wall, railing or staircase to edit **Collision Thickness** in
Properties. Drag its slider or enter a width (greater than 0, up to 200 drawing
units) for an immediate cyan collision preview. Visual size and strokes stay fixed.
The physical width is saved per object and supports undo/redo. Stair collision is
optional and covers sides/dividers, leaving treads and both ends walkable. Existing
maps retain their previous collision defaults until those settings are edited.

The initial layout has been cleared for manual rebuilding. The map keeps its
3000 × 1200 canvas; old placements are backed up separately in
`backups/map-before-reset-20260913.json`. To restore that layout, use **Load map**
in the editor and then **Save map**. Assets and tools have not been removed.

See [the editing guide](src/docs/BUILDING_DRAFTING.md) for layers, shortcuts,
importing older drafts, and export limitations.

Higher-floor editing now shows the previous floor as a non-selectable faded
reference. **Floor references** controls visibility, opacity, multiple lower floors
and current-floor focus. **Smart alignment**, **Equal spacing** and **Snap distance
(px)** provide temporary magenta positioning guides alongside optional grid snapping.
These preferences and guides belong only to the editor, not saved maps or the main app.
Smart alignment can also use the locked campus and ghost floors without making
those reference objects selectable or editable. Completed free buildings display
their actual ground-floor/roof components rather than a placeholder building box.

Dragging now updates retained selected graphics and guides rather than rebuilding
the entire editor. Resizing redraws only affected geometry; collisions and history
are finalized on release. Locked map/ghost references stay static. Smart alignment
and doorway collision use spatial lookups, and unchanged grid/property controls
are reused. See [performance checks](src/docs/EDITOR_PERFORMANCE.md) for profiling
results and the synthetic benchmark command (it never edits your saved map).

In the main app, buildings and all floor layers stay on the same map. Roofs fade
on approach, but entering a building always starts on Floor 1. **Floor Activator**
zones explicitly control floor changes; stair drawings and proximity alone do not.
In the Building Editor, create the destination floor first, return to the source
floor, draw a zone over its stair flight and configure **From Floor**, **To Floor**,
**Direction** and **Connected staircase**, then **Apply activator**. Add a separate
return zone on the destination floor. **Show Floor Activators** toggles the purple
editor-only areas and arrows; they never appear in the main app.

Entering at the arrow's tail starts a continuous floor blend; walking back reverses
it. Collision uses the same transition: the source floor before entry, both floors
during the blend, and the destination floor after completion. Keep the stair corridor
clear on both floors. No camera reset, teleport or joystick interruption occurs.
Existing maps still load, but their stairs need manually placed activators to change
floors. See the editing guide for setup and edge handling. This remains a 2D
demonstration, not certified emergency guidance.

If launching the nested editor directly through Flet, pass the assets path:

```powershell
C:\BPNHS\.venv\Scripts\flet.exe run --assets C:\BPNHS\BPNHS\src\assets src\map\campus.py
```

### uv

Run as a desktop app:

```bash
uv run flet run
```

Run as a web app:

```bash
uv run flet run --web
```

For more details on running the app, refer to the [Getting Started Guide](https://flet.dev/docs/).

## Build the app

### Android

```bash
flet build apk -v
```

For more details on building and signing `.apk` or `.aab`, refer to the [Android Packaging Guide](https://flet.dev/docs/publish/android/).

### iOS

```bash
flet build ipa -v
```

For more details on building and signing `.ipa`, refer to the [iOS Packaging Guide](https://flet.dev/docs/publish/ios/).

### macOS

```bash
flet build macos -v
```

For more details on building macOS package, refer to the [macOS Packaging Guide](https://flet.dev/docs/publish/macos/).

### Linux

```bash
flet build linux -v
```

For more details on building Linux package, refer to the [Linux Packaging Guide](https://flet.dev/docs/publish/linux/).

### Windows

```bash
flet build windows -v
```

For more details on building Windows package, refer to the [Windows Packaging Guide](https://flet.dev/docs/publish/windows/).

### Web

```bash
flet build web -v
```

For more details on building Web app, refer to the [Web Packaging Guide](https://flet.dev/docs/publish/web/).
