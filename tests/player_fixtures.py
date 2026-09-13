"""Keep controller tests independent of the developer's real preferences file."""

from unittest.mock import patch
from navigation.player_settings import PlayerSettings


def isolate_player_settings(case):
    for target in ("navigation.app.load_player_settings","map.workspace_editor.load_player_settings"):
        replacement=patch(target,return_value=PlayerSettings())
        replacement.start();case.addCleanup(replacement.stop)
