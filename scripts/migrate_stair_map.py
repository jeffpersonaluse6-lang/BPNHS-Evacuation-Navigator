"""One-time saved-map conversion, with an exclusive backup and change check."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from map.scene import MapScene
from map.scene_store import save_scene


def migrate(path):
    path=Path(path).resolve(strict=True)
    original=path.read_bytes();scene=MapScene.from_json(original.decode("utf-8-sig"))
    if b'"activator_' not in original and b'"floor_activator"' not in original:
        print("Map already uses stair-owned transitions; no changes.");return
    if scene.migration_notes:raise ValueError("Resolve migration warnings before saving: "+"; ".join(scene.migration_notes))
    backup=path.with_name(path.stem+".before-stair-transitions"+path.suffix)
    if backup.exists():raise FileExistsError(f"Backup already exists; preserved: {backup}")
    if path.read_bytes()!=original:raise RuntimeError("Map changed during migration; no map content was overwritten")
    with backup.open("xb") as file:file.write(original)
    if path.read_bytes()!=original:raise RuntimeError(f"Map changed before saving; preserved original backup: {backup}")
    save_scene(scene,path)
    print(f"Migrated map: {path}")
    print(f"Original map backup: {backup}")
    print("Stair geometry, other objects and floors preserved; standalone zones removed.")


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("path",type=Path)
    args=parser.parse_args();migrate(args.path)
