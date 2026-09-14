"""Player size/collision settings, saved to disk."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile

PLAYER_SETTINGS_FILE = Path(__file__).resolve().parents[1]/"assets"/"player_settings.json"


@dataclass(frozen=True)
class PlayerSettings:
    visual_size: float = 20.0
    collision_radius: float = 26.0
    player_speed: float = 120.0
    stair_speed_multiplier: float = .65

    def __post_init__(self):
        for name,low,high in (("visual_size",8,52),("collision_radius",1,100),
                ("player_speed",10,600),("stair_speed_multiplier",.25,1)):
            value=getattr(self,name)
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not low<=value<=high:
                raise ValueError(f"{name} must be a finite number between {low} and {high}.")


def load_player_settings(path=PLAYER_SETTINGS_FILE):
    path=Path(path)
    if not path.exists():return PlayerSettings()
    data=json.loads(path.read_text(encoding="utf-8-sig"))
    if (not isinstance(data,dict) or data.get("schema")!="bpnhs-player"
            or type(data.get("version")) is not int or data["version"]!=1):
        raise ValueError("Unsupported player settings file.")
    return PlayerSettings(data.get("visual_size",20),data.get("collision_radius",26),
        data.get("player_speed",120),data.get("stair_speed_multiplier",.65))


def save_player_settings(settings,path=PLAYER_SETTINGS_FILE):
    settings=PlayerSettings(settings.visual_size,settings.collision_radius,
        settings.player_speed,settings.stair_speed_multiplier)
    data=json.dumps({"schema":"bpnhs-player","version":1,
        "visual_size":settings.visual_size,"collision_radius":settings.collision_radius,
        "player_speed":settings.player_speed,"stair_speed_multiplier":settings.stair_speed_multiplier},indent=2,allow_nan=False)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode="w",encoding="utf-8",dir=path.parent,
                prefix=".player-settings-",suffix=".tmp",delete=False) as file:
            temporary=Path(file.name);file.write(data)
        os.replace(temporary,path)
    finally:
        if temporary and temporary.exists():temporary.unlink()
