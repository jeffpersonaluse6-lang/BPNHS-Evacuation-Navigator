"""Scoped editing shortcuts shared by the map and floating drafting editor."""


def history_shortcut(event):
    if not (getattr(event, "ctrl", False) or getattr(event, "meta", False)):
        return None
    if getattr(event, "alt", False):
        return None
    key = event.key.lower()
    if key == "z":
        return "redo" if getattr(event, "shift", False) else "undo"
    return "redo" if key == "y" else None


def nudge_shortcut(event):
    """Arrow labels vary by platform; return movement in active-layer units."""
    if getattr(event, "alt", False) or getattr(event, "meta", False):
        return None
    key = "".join(event.key.lower().split()).replace("arrow", "")
    direction = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1)}.get(key)
    if direction is None:
        return None
    step = 0.1 if getattr(event, "ctrl", False) else 10 if getattr(event, "shift", False) else 1
    return direction[0] * step, direction[1] * step


class EditorShortcuts:
    """Restore earlier handlers; leave focused text editing and navigation alone."""

    def __init__(self, page, undo, redo, blocked=lambda: False, duplicate=None, nudge=None, actions=None):
        self.page, self.undo, self.redo, self.blocked = page, undo, redo, blocked
        self.duplicate = duplicate
        self.nudge = nudge
        self.actions = actions or {}
        self.text_focused = False
        self.installed = False
        self.handler = self.handle

    def install(self):
        if not self.installed:
            self.previous = getattr(self.page, "on_keyboard_event", None)
            self.page.on_keyboard_event = self.handler
            self.installed = True

    def remove(self):
        if self.installed and self.page.on_keyboard_event == self.handler:
            self.page.on_keyboard_event = self.previous
        self.installed = False

    def watch_text(self, control):
        control.on_focus = lambda event: setattr(self, "text_focused", True)
        control.on_blur = lambda event: setattr(self, "text_focused", False)

    def handle(self, event):
        if self.text_focused or self.blocked():
            return
        action = history_shortcut(event)
        key = event.key.lower()
        command = ("shift+" if getattr(event,"shift",False) else "") + key
        command = command if (getattr(event,"ctrl",False) or getattr(event,"meta",False)) else "plain:"+command
        if action:
            (self.redo if action == "redo" else self.undo)()
        elif (self.duplicate is not None and event.key.lower() == "d"
              and (getattr(event, "ctrl", False) or getattr(event, "meta", False))
              and not getattr(event, "alt", False) and not getattr(event, "shift", False)):
            self.duplicate()
        elif command in self.actions and not getattr(event,"alt",False):
            self.actions[command]()
        elif self.nudge is not None:
            movement = nudge_shortcut(event)
            if movement is not None:
                self.nudge(*movement)
