# BPNHS map and building workspaces

From `C:\BPNHS\BPNHS`, run:

```powershell
C:\BPNHS\.venv\Scripts\flet.exe run src\map_editor.py
```

The Map Editor edits the campus; **Building** opens a dedicated Building Editor
for floor-by-floor free building over the entire map, with the campus faded and
locked behind it. There is no starter footprint or small building canvas.
This is an editing workspace, not a player scene transition.
This is a development tool, separate from `src/main.py`, which launches only the
user-facing navigator and reads the finished saved map. The older `map_preview.py`
launcher remains available for compatibility.
The toolbars scroll horizontally; Properties hides or shows the inspector to
give the map more room. Maximize the desktop window for a larger work surface.

## Resize the map canvas

In the main Map Editor, click **Map size**, enter the campus width and height,
then click **Resize map**. Each dimension supports 100–5000 map drawing units.
This changes the canvas, grid, editing bounds and saved player-world bounds;
it does not move, scale or delete buildings or their floor/roof objects.
Shrinking is rejected if placed content would be cut off; move that content inward
first. **Cancel** keeps the current size. Ctrl+Z/Ctrl+Y undo/redo the resize.
Click **Save map** and restart the main app to use the new world dimensions.
Canvas sizing is unavailable during Test walk or a staged Building Editor session.
Zoom controls still control only the view, not the saved canvas size.

## Buildings and layers

1. Choose **Building** to start a staged building on **Floor 1**. The entire map
   is the workspace, like tracing paper over the campus. Nothing is committed yet.
   No predefined rectangle appears, and you do not set a footprint first.
2. Draw rooms, walls, doors, openings, windows, railings, stairs, shapes and
   **Floor section** surfaces anywhere they belong on the visible map. Only the
   active floor's components are editable. Other real map objects remain faded,
   locked references: selection, handles, box selection, properties, grouping,
   deletion, duplication and copy/paste cannot change them.
3. Select your components to move them, use square handles to resize, and use
   the blue **↻** handle to rotate (click for 90 degrees, drag for any angle).
   Properties accepts component X/Y, width/height, rotation, colors and mirroring.
   Click **Apply properties** to commit field edits. Name the logical building
   with **Building name**. Floor section surfaces do not add collision by themselves.
4. Build each floor and press **Floor N Done → next** to mark it complete and
   continue upward. Free builds have no fixed floor-count limit; normal saved-file
   size and validation protections still apply. The floor panel shows completed floors with ✓
   and the active floor with Editing. Click a completed floor to deliberately edit
   it again. Completed/other floors stay faded and cannot be selected accidentally.
   Choose this building's floors or **Roof** in **Editing layer**.
   Every layer uses this same full-map workspace at the same world locations.
   Draw **Room**, **Wall**, **Door**, **Window**, **Stairs**, **Text**, shapes or other
   symbols there. Each floor stores independent editable objects.
5. Draw **Roof** objects on the building's Roof layer. The campus overview shows
   that layer above the building. Selecting a floor reveals its interior instead.
6. **Add Building to Map** fits the logical bounds to the objects from **all floors
   and the roof**, saves the complete building and map, then returns to the
   Map Editor. Object X/Y, dimensions, rotation, IDs, attachments, grouping, floor
   assignments, collision geometry and stair destinations are preserved. Nothing
   shifts when saving. An empty free build cannot be saved. Actual authored floor
   and roof components appear on the map, not a generic placeholder box.
   Cancel discards this staged session after confirmation if it has unsaved edits.
   Select an existing free building and **Edit This Building** to revise it;
   **Save Building Changes** updates its identity without adding a copy.
   **Remove current floor** confirms deletion and renumbers higher floors and
   explicit stair destinations. Stair flights leading to the removed floor
   are disabled rather than redirected to an unintended floor. Undo can restore them. Source images
   keep their original floor count. You can finish a single-floor building without
   pressing Done, or remove an unwanted empty next floor before saving.
7. In the Map Editor, select the whole building to change its placement.
   Moving, resizing, rotating or mirroring the building carries its floor and roof
   objects with it. **Duplicate** copies the placement and all editable layers.
   **Delete** removes the placement and its layers, not source images or draft files.

New free builds use map drawing coordinates directly; their saved floor frame and
origin preserve those positions when automatic bounds are fitted. Moving/resizing/
rotating the completed logical building still carries all of its components.
Existing image-based buildings retain their legacy 1436 × 751 frame and original
asset placement; their components can still be drawn anywhere over the visible
map using projection rather than clipping to that frame. Their floor-image count
is determined by their assets. Neither frame represents surveyed meters.
Zoom in to edit small details precisely.

## Reopen a completed building

On the campus, choose **Select** and click anywhere inside a completed building's
bounds. The entire building is selected, including its floors and roof; you do not
need to click a tiny wall or stair. When exactly one free building is selected,
its **Building Name** and **Edit This Building** button appear in the selection
toolbar, even if the Properties inspector is hidden. These controls disappear
when selecting other objects or multiple objects. Older image buildings can still
be reopened through **Editing layer**.

**Edit This Building** opens the original Building Editor with the same ID, name,
transform, floors, components, manual groups, attachments and stair connections.
Saved free-building floors are marked complete; choose any floor to edit it again,
add floors with Done, remove floors, or select Roof. The other campus structures
remain faded, locked references. Edits are staged until you save them.

**Save Building Changes** recalculates bounds while preserving each component's
map position and updates the existing building and its layers in the saved map.
Collision remains derived from the updated geometry. The editor returns to the
campus with the updated building selected. Save errors keep the editing session
open and the original map intact. Editing a building never creates another ID.

**Cancel** offers **Keep Editing** or **Discard Changes** when current data differs
from the data loaded at the start of the session. Discard returns to the campus
with the original building untouched. If there are no changes, or all edits were
undone, Cancel returns immediately. Creating a new building still ends with
**Add Building to Map**. Save/load retains editable data across app restarts.

## Ghost floor references

When editing Floor 2 or higher, the directly preceding floor appears faded beneath
the current floor's editable objects. Floor 1 has no reference below it. The active
current-floor objects keep full opacity; no rectangular workspace outline is drawn.
Gray reference objects are not selectable, do not appear in Selected object, and
do not contribute to the active floor's collisions. Switch Editing layer to edit them.

Open **Floor references** to show/hide the previous floor, change reference opacity,
show all lower floors, or temporarily focus only on the current floor. Older floors
fade progressively further; Roof can reference the highest floor. These controls
update the view immediately without adding history entries or changing saved maps.
References also disappear during Test walk. Image-based buildings use their existing
registered floor images; editable room references show outlines without opaque fills.
The Building Editor defaults to showing all lower floors, with older floors faded
further. Other higher floors can be enabled through Floor references. Smart alignment
uses both reference-floor geometry and read-only proxies from the visible campus
without allowing reference objects to be selected or modified.

## Stair direction and continuous player exploration

**Stair Up** and **Stair Down** reuse the single Stair tool. Direction properties
reverse the progressive tread shading. Select a
stair to configure **Stair floor transition**, then **Apply stair settings**.
The selected stair shows blue UP/DOWN arrows and derived walking-area guides only
in the editor. The connection belongs to the stair, not a separate drawn zone.
A saved explicit destination must exist and agree with Up/Down.

Place matching stairs/landings at the same coordinates on connected floors. Up
travels from the bottom end toward the top/landing; Down reverses it.
Shadows and arrows never add collision; draw
railings alongside flights/balconies wherever movement must be constrained.

The main app retains all buildings and floor controls on one world map. Approaching
a footprint or authored **Entry / approach area** fades its roof over 140 ms.
**Roof reveal distance** controls the approach range in map units; floor entry keeps
the player's actual map coordinates and joystick input. Entry areas on Floor 1
belong to that building automatically; campus areas can be attached to a building.

Building entry keeps the player on Floor 1. Proximity, building bounds and unrelated
upper-floor geometry cannot activate another floor; only stair entry does. Ground-floor
exit restores the roof on departure. Explicitly non-fading roof objects stay visible.

### Stair-owned floor transitions

1. Create the connected floors using **Add floor** or **Floor Done → next**.
   Floor counts and connection choices are dynamic; there is no two-floor limit.
2. Place a **Stair** on a numbered building floor. Its invisible usable walking
   area automatically matches its full tread area. There is no separate
   activation-area object or drawing tool.
3. Select the stair and configure **From Floor**, **To Floor** and **Direction:
   Up / Down** in **Stair floor transition**. The default To Floor is adjacent
   in that direction; an unavailable floor means no active connection. Explicit
   targets must exist and agree with the direction. Changing From Floor moves
   the stair to that floor without changing its geometry. Click **Apply stair settings**.
4. **Enable Stair Activator** turns the selected stair's transition on/off
   immediately, with Undo/Redo support. Disabled stairs remain visible and retain
   their collision settings, but never trigger floor or opacity changes. Save
   the map to persist this setting. Configure independent normal stairs for
   separate flights or floor connections.
5. **Stair speed multiplier** is optional (0.25–1.0). Blank inherits the player's
   stair-speed setting. Enabling/disabling a stair's transition is independent
   from its wall/railing collision. Moving, resizing, rotating or mirroring the
   stair immediately changes its derived activation area. No attachment is needed.
6. Save the building/map and use **Run evacuation demo** for a full transition test.
   **Test walk** remains an active-layer collision test, not a multi-floor simulation.

Enter at the stair arrow's tail: Up travels bottom-to-top, Down top-to-bottom
before rotation/mirroring. Spawning or side-entry halfway is not a valid source
entry. Progress continuously blends source/destination visibility from 0–100%;
turning back halfway reverses it smoothly. Reaching the far end commits the
destination. After completion, all stair connections stay disarmed until the
player's entire collision circle leaves the completed and overlapping destination
stair footprints, plus a 3-map-unit anti-jitter
margin. Walking across the landing cannot bounce floors. Re-entry must be intentional.
Only current-floor stair connections are candidates; an active transition exclusively
owns its flight until completion or cancellation. Runtime phases are ON_FLOOR,
ENTERING_STAIRS, TRANSITIONING, ARRIVED and WAIT_FOR_EXIT. A path crossing a disarmed
flight while exiting is not replayed after rearming. Swept source/end crossings
also detect stair areas thinner than a movement substep.
Only player navigation updates the transition, never object editing or other objects.
No teleport, scene load, viewer replacement or camera reset occurs.

Collision and opacity use this same transition. Before entry, only source-floor
barriers apply. During a partial blend, both source and destination barriers apply,
and movement stays within the flight's lateral stair corridor until an end is reached.
After completion, only destination-floor barriers apply. Author a clear, aligned
stair corridor and landings on both floors: a wall across either corridor will block
travel instead of becoming an invisible walk-through. Hidden unrelated upper floors
do not obstruct the ground-floor player. Non-fading floor objects still participate
in the overall floor blend; non-fading roof objects retain their separate behavior.

Stair settings save/load on the stair object itself. No invisible zone can become
accidentally selected, grouped or left behind. Deleting a stair removes its transition;
Undo restores both. Duplication preserves connections. Pasting/copying to another
floor updates From/To; deleting a floor disables flights targeting it and renumbers
the surviving connections, without redirecting a disabled flight unexpectedly.

Older saved files import through a one-way conversion: old linked/overlapping zones
become connections on the matching stair flight, and all old zone objects/fields
are removed from the loaded document. Conflicting connections fail safely rather
than silently dropping a route. Saving writes only stair-owned data. The normal
app has no old-zone trigger path or editor imports. Unmatched old zones produce
import diagnostics and require configuring the relevant stair manually.

Legacy double-stair objects are imported once as two independent normal Stairs
and ordinary landing/divider shapes, preserving their individual connections.
New saves contain no double-stair objects or right-flight properties. There is
no Double Stair tool, live model, renderer or special transition path.

This is a layered 2D prototype, not a 3D structural/falling simulation. Floors need
properly authored walls, landings and railings; safety routes need school validation.

## Multi-selection and complete structures

Drag Select from empty space to box-select active-floor objects. Selected groups
have individual outlines plus one larger bounds outline; drag any member or the
space inside these bounds to translate the complete selection with smart snapping.
Spacing and relative positions are retained. Click empty space or Esc to deselect.

**Group** / Ctrl+G saves a shared group ID; **Ungroup** / Ctrl+Shift+G restores
individual pieces, even if only part of the manual group is selected. Ungroup does
not change geometry, floor assignment, collision or attachment data; it collapses
the selection to one object so later ordinary clicks select individual pieces.
Ordinary clicks expand manual groups only, never attachment/proximity relationships.
With **Smart structure select** enabled, press **Select structure** to explicitly
select attachment parents/children and room-contained components temporarily.
This operation changes selection only, not saved group IDs. New doors/openings
attach to nearby walls; furniture/stairs/railings placed inside a room attach to it.
The inspector's **Attached to** control allows deliberate reassignment. Ordinary
clicks can move attached doorways individually without disabling smart selection; ungroup first if
it also belongs to a group. Reference/campus objects remain protected in a building session.

Duplicate / Ctrl+D, Delete, Ctrl+C/V, Ctrl+A and arrow nudges operate on the whole
selection. Copy/paste uses an editor-memory bundle, not the system clipboard, and
keeps building floor/roof contents. Cloning remaps component, parent and group IDs;
copying a room does not accidentally attach it to the original. Group moves and
bundle operations each form one undoable edit; collision recomputes from geometry.

**Cross-floor Copy/Paste:** select objects (or Ctrl+A for the current floor),
Copy / Ctrl+C, switch floors with the floor buttons or picker, then Paste / Ctrl+V.
The session clipboard survives floor changes. On a different floor, pasted
objects keep their exact floor coordinates, dimensions, rotation and other
properties. They receive new object/group IDs; copied attachments are rebound
inside the new bundle and building-root attachments belong to the destination
building. The source floor stays unchanged. Stair From Floor becomes the current
floor; explicit To Floor keeps its relative floor offset. If that destination
doesn't exist, only that stair's activator is disabled and its target cleared,
with a status message—walls and the rest of the layout still paste normally.
Configure the connection after adding the necessary floor. Same-floor Paste and
Duplicate keep their existing 24-unit offset. Paste supports Undo/Redo and saving.

**Flip Horizontal / Flip Vertical:** use Flip Horizontal in the toolbar or
Flip Vertical directly below **Mirror horizontally** in the Properties panel to mirror
a single item, multiple selected items or a manual group about the selection's
center line in floor coordinates. Press the same button again to revert, or use
Undo. Rotation and the shared mirror transform reflect drawing, wall/railing
collision, door/window geometry and stair walking progress together. IDs,
grouping, attachments, dimensions and collision thickness remain unchanged.
Stair Up/Down and From/To Floor keep their intended floor connection; the
world-space entrance and exit positions mirror with the stair. The existing
single-item horizontal mirror property is also still available.

Bulk selections intentionally expose movement, grouping and bundle actions rather
than applying one member's resize/property fields to the others.

## Smart alignment and spacing

**Smart alignment** and **Equal spacing** are enabled by default and can be toggled
independently from **Snap to grid**. **Snap distance (px)** controls the small capture
distance (default 6 screen pixels), taking viewer zoom and building scale into account.

Moving objects or resizing their handles can align left/right/top/bottom bounds and
horizontal/vertical centers with other objects on the active layer, or with the center
of the campus/floor frame. Room centers act as alignment targets too. Rotated objects
use their bounding extents in floor coordinates; resizing preserves the opposite
anchor. New walls and symbols also use smart snapping. Rotation keeps its existing
optional 15-degree grid-snap behavior rather than positional alignment.

Magenta guides identify the aligned edge/center while dragging or resizing. Guides
clear on release, cancellation, tool changes or floor changes. Their line/label sizes
stay consistent at different zoom levels. Equal-spacing guides can match the gap
before/after two neighboring objects, or center an object between them; they apply
while moving/placing rather than resizing. Neighboring objects must overlap across
the other axis to form a row/column. Both spacing intervals are marked on the map.

When grid and smart snapping are enabled, the closer candidate wins; the result is
not forced onto the grid afterward. Arrow-key nudges and numeric property edits
remain exact and bypass automatic snapping. All these guides and preferences are
editor-only: they are not exported, saved into map data, or shown in the main app.

## Room walls, doorways and railings

Railings use noticeably thicker twin strokes and posts (default thickness 10:
rail strokes 4, post strokes 5). **Railing thickness** in the inspector adjusts
these live with one undo entry per slider gesture. New railings initially use a
collision width covering the default posts/strokes. **Collision Thickness** then
controls the physical envelope independently; making the visual rail thicker or
thinner keeps its saved collision width. Selection and bounds fitting follow the
visual envelope, while cyan guides follow the physical one. Both settings survive
save/load, duplication and floor edits.

**Collision Thickness** appears in Properties for rooms, walls, railings and stairs.
It is the full physical width across the wall/barrier centerline, in native drawing
units rather than screen pixels. A visual stroke of 4 and collision thickness of 12
produces a 4-unit visible wall with a 12-unit physical barrier. The slider updates
the selected object's cyan boundary immediately and keeps one Undo entry per drag.
The numeric field accepts positive widths up to 200, including fractional values.
Changing either control enables Show collisions; use that checkbox to hide guides
later. **Blocks player** can still disable an object's physical collision.

Wall and room collision is split around aligned doorway gaps at every thickness;
increasing the width never places collision across the doorway. Railings retain
rounded physical ends. Stairs can optionally block along their left/right sides,
with open ends and walkable treads. Set a stair's
Collision Thickness or enable Blocks player and Apply properties to add those
barriers. Physical collision thickness is independent of the stair's floor connection.

Older JSON maps without a collision-thickness value keep their previous wall/rail
collision and non-blocking stair behavior. Editing visual wall/rail properties
captures that existing physical width so later visual edits do not change it.
An explicit physical width is saved with its object, reused by player navigation,
and preserved by editing, grouping, save/load and Undo/Redo. Collision guides and
controls belong only to the editor.

**Room** automatically creates thin collision walls along all four perimeter
edges. Its interior is free space. **Wall** creates an independent solid wall
segment. Both block movement by default; their collisions follow position,
dimensions, rotation and mirroring, not a large room-sized collision box.

Choose **Door**, **Double door** or **Opening** and click a wall to align a new
walkable gap. Door width is the gap width; the symbol's bottom baseline lies on
the wall. Opening uses its rectangle's centerline. You can move, resize or rotate
these symbols afterward. Only aligned, overlapping doorways cut wall segments;
the large door swing arc does not remove nearby walls. Windows never cut collision.

Room/Wall collision is split automatically into just the solid wall sections on
either side of every doorway, regardless of drawing order. Moving/resizing a wall
or doorway recalculates the sections; deleting a doorway restores the wall, and
deleting a wall removes its collision. Undo/redo and save/load reconstruct the
same geometry. No manually maintained invisible collision boxes are stored.

Door symbols currently represent open passages: they do not add separate closed-door
collision. A passage must be wider than twice the configured player collision
radius to pass naturally (52 map units with the default 26-unit radius).
Zoom and drawing scale do not change that physical clearance.

- Choose **Railing / barrier** and drag between its endpoints anywhere on the
  current editing layer, or click to place a starter railing. It looks like two
  thin rails with regularly spaced posts, rather than a filled wall.
- Select a railing to move it, drag its endpoint handles to change its length,
  or use its rotation handle. Properties supports signed line dx/dy, rotation,
  **Length**, color and thickness. Duplicate and Delete work like other objects.
- **Blocks player** is enabled by default for rooms, railings and walls. Uncheck it and
  apply properties only for decorative objects that should not obstruct movement.
- **Show collisions** draws cyan boundaries around solid wall sections and capsule
  boundaries around railings, using the same geometry as the movement solver.
  Doorway gaps have no collision outline. The player has its own radius, so its center
  stops outside that boundary. These outlines are not evacuation-route guidance.
- Place stair and balcony railings on the appropriate floor layer; place outdoor
  barriers along pathways or restricted areas on Campus. Collision affects only
  the active campus/floor, not railings on different floors or the roof.
- **Test walk** temporarily locks editing and shows a joystick on this map.
  Hold the joystick to move continuously; walls and railings physically stop
  movement and allow sliding along their edges. **Finish test walk** returns to
  editing. The camera follows actual movement, including on rotated buildings.

PNG floor plans remain visual references: their black pixels are not automatically
converted into editable walls or collision. Trace any boundary that must block
movement using Room, Wall or Railing. Rectangles, door masks, stairs and window
symbols do not independently block movement, except explicitly enabled stair side
barriers. Railings remain independent barriers:
placing a door symbol over a railing does not cut it.

Collision guides belong only to the editor's **Show collisions** mode. They never
appear in the normal main application; only the finished walls and symbols do.

## Everyday editing

**Selected object** provides another way to pick objects on the active layer.
**Pan** drags the map; scroll/pinch and zoom buttons change zoom. **Reset view**
restores the camera. **Snap to grid** is optional; **Straight walls** affects Wall
draws only, leaving railings and lines free-direction.

Select any object and use **← ↑ → ↓** to nudge it by **1 drawing unit**.
**Shift+arrow** moves **10 units**; **Ctrl+arrow** moves **0.1 unit** for fine
positioning. Nudging bypasses grid snapping, follows the campus map axes even
inside rotated/mirrored buildings, and changes position only—not size or rotation.
Moving a whole building carries its floor/roof objects too. Keyboard movement
updates collision guides and supports Undo/Redo like mouse movement. Arrow keys
are left to normal text navigation when a property field has focus; click Select
or select an object on the map before nudging. Nudging is disabled during test
walking, dialogs, exports and active mouse gestures. Use Save map to keep edits.

**Bring front** and **Send back** change overlap within the layer. Keep Room fills
behind walls and symbols. **Ctrl+D** duplicates, **Ctrl+Z** undoes, and **Ctrl+Y**
(or **Ctrl+Shift+Z**) redoes. History includes building placements, floor objects,
railings and imports together. These shortcuts leave focused text fields to their
normal text editing and are disabled during test walking or file dialogs.

## Player speed and gameplay performance

In the main app or evacuation demo, use **Select player** to open **Player Speed**.
The default is **120 map units/second**, reduced from 300. Use the slider or submit
a numeric value from 10–600. **Stair speed multiplier** defaults to **0.65** (65% of
walking speed), adjustable from 0.25–1.0. It applies on a stair footprint and during
an active transition, including when entering stairs partway through a frame.
Appearance, collision radius and speed remain independent. **Save player settings**
persists all of them; older size/radius-only files load the new speed defaults
without rewriting the file. Editor/demo handoff preserves unsaved settings too.

Normal gameplay targets 60 updates/second, using measured elapsed time rather
than fixed pixels per tick. Delayed frames up to half a second retain elapsed time
and integrate bounded physics/camera steps, with one UI submission per frame.
Longer window-suspension/debugger pauses are discarded to prevent resume teleports.
The deadline scheduler includes update cost instead of adding another full sleep
after every update. The camera interpolates toward the player, trails slightly,
settles after stopping, and uses a viewport visibility guard. Zoom, rotation and
building dimensions do not change while following.

Building transforms, stair footprints, derived flight connections and collision geometry are
compiled once per loaded scene. Spatial indices limit entry, collision, roof and
stair work to nearby objects; during transitions only the owning flight updates.
The renderer touches only the active/previous floor layers and nearby fading roofs.
Camera changes update a retained root transform, not rebuilt map geometry.
Locked editor Test walk likewise moves a retained dot/preview and uses a cached
collision index, rather than refreshing every object/property per tick.

For a repeatable Python/Flet-patch stress profile, run:

```powershell
python tests/benchmark_navigation.py --buildings 200 --floors 20 --ticks 60 --speed 300
```

This measures simulation and real Flet object-diff work, not native display FPS
or GPU painting. Regression tests cover timing, batching, cache reuse, thin zones,
floor locks and synchronized visibility/collision.

## Saving, older drafts and exports

- **Save map** writes the full editable scene to `src/assets/map_workspace.json`.
  Buildings, transforms, floor/roof objects, collision flags and drawing order
  reload together on the next launch. Nothing is saved automatically. Back up
  this JSON file to keep a copy of your work.
- **Load map** opens a workspace JSON, asking before discarding unsaved edits.
  Invalid saved data is reported without silently replacing its file.
- **Import editable draft** brings an older `bpnhs-draft` JSON into a new building's
  floor and roof layers as individually editable objects, not a flattened image.
  **Edit selected draft** converts an older SVG placement when its sibling draft
  JSON is available in assets. For PNG buildings it opens Floor 1 for overlay edits.
- **Run evacuation demo** opens an editor-only preview of the current scene,
  including unsaved collisions. Its **Edit map** button returns to the same workspace
  and history. The normal main application has neither that button nor editing tools.
- **Export placements** provides copyable Python building coordinates for the
  original constants-based workflow in `map/placements.py`. It does not include
  floor objects or barriers; use Save map for the complete scene.
- **Export vectors SVG/PNG** exports the active layer's editable vector objects
  without grid, selection or collision guides. It does not embed raster floor-plan
  images, building image layers or the entire composed campus. Exported pictures
  are not a replacement for the editable workspace JSON.

Saving/exporting preserves existing source image assets and old draft JSON files.
The JSON format is specific to this editor, not DWG/DXF. The source-tree desktop
prototype saves beside its assets; packaged/mobile builds need an app-data storage
location before distribution.

This is a drafting and movement prototype, not certified CAD or an emergency-route
verification tool. School safety personnel must validate geometry and evacuation
routes before real emergency use.

## Code separation

Drag/resize gestures use retained selected controls and nearby alignment targets.
The faded map and lower-floor control trees are not rebuilt per mouse movement.
Collision/debug guides are finalized after resizing; doorway cuts remain accurate
in the saved data and player demo. Undo keeps one entry per completed gesture.
See [interaction performance](EDITOR_PERFORMANCE.md) for details and profiling.

- `main.py`: user-facing application entry point; imports runtime navigation only.
- `map_editor.py`, `map_preview.py`: separate development/editor entry points.
- `map/placements.py`, `map/building_renderer.py`: editor-free defaults and image
  rendering used by both applications. `map/campus.py` remains editor-only.
- `map/workspace_editor.py`: shared workspace, tools, properties and shortcuts.
- `map/interaction.py`: editor-only retained drag/resize/draw updates and gesture caches.
- `map/railing_editor.py`: live thickness controls and gesture-based undo.
- `map/collision_editor.py`: live physical thickness editing and collision previews.
- `map/stair_editor.py`: stair-owned floor connections and selection-only flight guides.
- `map/scene.py`: campus/building layers, geometry projection and scene validation.
- `map/scene_renderer.py`: image layers, editable vectors and collision guides.
- `map/reference_layers.py`: editor-only ghost floors and visibility preferences.
- `map/alignment.py`: editor-only edge/center snapping and equal-spacing geometry.
- `map/building_editor.py`: full-map staged building sessions and locked references.
- `map/free_build.py`: automatic bounds fitting and locked alignment-coordinate proxies.
- `map/selection.py`: structural selection, multi-object operations and ID remapping.
- `map/world_renderer.py`: retained player-facing floor/roof layers.
- `navigation/world.py`, `navigation/stairs.py`: player-only floor transitions,
  edge handling and synchronized visibility/collision, without editor imports.
- `navigation/stairs.py`: reusable stair flight geometry and direction indicators.
- `map/scene_store.py`: explicit editable scene persistence.
- `drafting/models.py`, `drafting/handles.py`: reusable drafting geometry/history.
- `drafting/migrations.py`: one-way legacy import, without a competing runtime system.
- `navigation/collision.py`: movement collision shared by editor and player demo.
- `spatial.py`: deterministic bounding-box lookup for openings and alignment candidates.
- `navigation/app.py`: player demo using the same scene and floor objects.
- `navigation/camera.py`: runtime pan/zoom/rotation transform and smooth, bounded follow.
- `navigation/player_settings.py`: validated, atomic player-preference persistence.
- `navigation/player_controls.py`: selected-player radius inspector and centered guide.
- `map/demo_preview.py`: editor-only preview buttons, isolated from the main app.

### Player display and runtime camera

The normal application and **Run evacuation demo** show a simple blue dot.
**Player size** changes its display diameter (8–52 map units, initially 20) around
the same center. It does not resize buildings, alter collision clearance, or
write to the saved map. **Test walk** uses the saved dot size for its basic
active-layer collision preview.

Click the dot or **Select player** (in **Test walk** for the editor) to show
**Collision radius (map units)** and the cyan collision-circle preview. The
slider ranges from 1 to 100; the text field also accepts fractional values when
you press Enter. Dot diameter and physical radius are independent. Collision
uses the new radius immediately, including walls, railings, stair-side barriers,
door clearance, floor transitions and map edges. The circle stays centered and
retains its map-unit radius across building scales; zoom transforms the guide
with the map. Hidden/deselected guides do not disable collision.

**Save player settings** persists both sizes independently of map data, in
`src/assets/player_settings.json`. **Load player settings** restores both sizes;
startup also loads them in the app, demo, and editor. Changes are live but disk
save is explicit. Invalid files are retained, with defaults used at startup;
failed loads keep the current live settings. **Save map** does not save player
preferences. Resizing preserves the current position, rather than teleporting
out of overlaps. If a larger circle overlaps a wall, reduce it or move away
before enlarging. Scaled-down image buildings may need a smaller radius to fit
their correspondingly narrower doorways. **Deselect player** hides the guide and
inspector. The normal app never imports or launches editor tools.
Switching from the editor to **Run evacuation demo** and back also preserves
live unsaved player preferences; disk persistence still requires the save button.

Runtime following translates the retained world canvas without changing any
building dimensions, zoom, or rotation. Elapsed-time interpolation produces a
soft trail while moving and settles toward the player after stopping, including
after **Finish moving**. A viewport-edge guard prevents movement from taking a
visible player off-screen. Returning from a manually panned-away view is gradual;
joystick travel waits until the player is visible. Map-mode gestures cancel
automatic settling so you can freely inspect the map.
