"""Save/load the map workspace — atomic writes, no asset edits."""

from pathlib import Path
import os
import tempfile
from .scene import MapScene

ASSETS_DIR=Path(__file__).resolve().parent.parent/"assets"
SCENE_FILE=ASSETS_DIR/"map_workspace.json"


def load_scene(path=SCENE_FILE):
    path=Path(path)
    if path.exists(): return MapScene.from_json(path.read_text(encoding="utf-8-sig"))
    from .placements import BUILDINGS_ON_MAP
    return MapScene(BUILDINGS_ON_MAP)


def save_scene(scene,path=SCENE_FILE):
    path=Path(path)
    data=scene.to_json()
    # Validate first so a bad file doesn't overwrite the last good save.
    MapScene.from_json(data)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode="w",encoding="utf-8",dir=path.parent,
                prefix=".map-workspace-",suffix=".tmp",delete=False) as file:
            temporary=Path(file.name)
            file.write(data)
        os.replace(temporary,path)
    finally:
        if temporary and temporary.exists(): temporary.unlink()
    scene.dirty=False
