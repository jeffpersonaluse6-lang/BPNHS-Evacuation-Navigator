# Map editor interaction performance

## Bottlenecks found

Profiling the actual `pointer_move` path found repeated `refresh` → `render_scene`
work, whole-page Flet updates, re-created grid controls, repeated alignment-peer
tuple hashing, and inspector option lists recreated on click/release. A 1,000-item
stress fixture visited every object on every move. Its single-object Python handler
averaged about 24 ms; moving a 10-object bundle containing doors could take about
1.9 seconds per event because every room's geometry cache included **every** door.
Changing one doorway consequently invalidated unrelated rooms.

No mouse-move autosave was found. Undo snapshots were already gesture-based;
the optimization keeps that behavior rather than weakening history or saving early.

## Retained gesture pipeline

- `map/interaction.py` prepares selected-item slots, group bounds, visible graphics,
  opening candidates and alignment indices once at pointer-down.
- Translation changes existing Canvas/image coordinates. Shape lists and collision
  polygons are retained; groups preserve their relative coordinates and receive one
  targeted update, not a full editor refresh per child.
- Resizing/rotation regenerates geometry only for selected items and a selected
  building's visible children. Hidden floors and locked references stay untouched.
  Selected collision/debug overlays are finalized on release; actual wall strokes
  and walkable doorway cuts still render during resizing.
- Unchanged snapped geometry/overlays skip duplicate Flet patches. The existing
  16 ms input interval is retained; no extra low-rate throttle was introduced.
- Release consumes the final pointer position, commits one history entry, rebuilds
  accurate final geometry, and patches changed graphics/property controls only.
  Cancel restores original model data and original cached graphical baselines.
- Grid/background controls and unchanged dropdown options retain their identities.
  Selection changes do not rebuild the map. Normal structural changes still receive
  a full refresh when necessary.

`map/alignment.py` uses a gesture-local bounding-box index plus sorted edge/center
coordinates. Smart guides query nearby objects; equal-spacing compares local peers.
The neighborhood follows zoom and object size. Grid snapping, closest-snap choice,
reference-floor alignment, configurable screen-pixel snap distance and guide labels
remain available. `map/free_build.py` caches coordinate transforms instead of
looking up a building for every reference object's corner.

`navigation/collision.py` uses a spatial opening index. A wall's cache key includes
only openings near its real edge segments, so a door invalidates relevant walls
instead of every room. Rotation, mirroring and thin-wall collision still use the
same exact geometry calculations. This shared improvement does not import editor
UI into the main app.

## Repeatable checks

From `C:\BPNHS\BPNHS`:

```powershell
C:\BPNHS\.venv\Scripts\python.exe -u -B tools\profile_editor.py --objects 1000 --frames 60
C:\BPNHS\.venv\Scripts\python.exe -u -B tools\profile_editor.py --objects 1000 --frames 60 --patches
```

Add `--profile` to print hot paths; profiler overhead affects the reported times.
The script constructs synthetic mixed rooms/walls/railings/stairs/doors, moves a
10-object selection, resizes an object, and tests a building floor with 200 ghost
objects over the locked campus. It never loads or saves the user's map.

One 60-event run on this machine averaged **1.94 ms** for drag, **4.82 ms** for
10-object movement, **3.94 ms** for resize, and **2.64 ms** with ghost/map references
(Python handlers only). A separate run including installed Flet diff/serialization
averaged roughly **7–19 ms** per event across these operations; system load varies.
These are synthetic CPU measurements, not native-client FPS or end-to-end latency.
Network transport, Flutter painting and display/GPU behavior are not measured.

`tests/test_editor_performance.py` verifies work counts/control identities rather
than asserting hardware-dependent timings. It also exercises the real Flet patch
serializer, exact release coordinates, cancellation, group undo, static references,
hidden floor caches, nearest-opening geometry and retained background/options.
