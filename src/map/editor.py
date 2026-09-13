"""Standalone campus placement editor — doesn't touch navigation data."""

from dataclasses import replace
import math
import re
import flet as ft
from editor_shortcuts import EditorShortcuts
from .geometry import MIN_BUILDING_SIZE, hit_resize_handle, resize_building, resize_handles
from .history import PlacementChange
from .export import placement_code


class CampusPlacementEditor:
    """Drag whole building stacks in campus coordinates, even after zooming."""

    def __init__(self, page, placements, map_builder, width, height, building_builder=None):
        self.page = page
        self.placements = list(placements)
        self.map_builder = map_builder
        self.building_builder = building_builder
        self.width, self.height = width, height
        self.layer_options = {}
        self.viewer = None
        self.selected = None
        self.drag_index = None
        self.drag_original = None
        self.drag_handle = None
        self.drag_start = None
        self.grab_offset = (0, 0)
        self.history = []
        self.redo_history = []
        self.building_controls = []
        self.outline = None
        self.handle_controls = {}
        self.shortcuts = EditorShortcuts(page, self.undo, self.redo, duplicate=self.duplicate_building)
        self.shortcuts.install()
        self.clipboard = ft.Clipboard()
        self.move_switch = ft.Switch(
            label="Edit buildings", value=True, on_change=self.change_mode,
        )
        self.selection = ft.Dropdown(
            label="Selected building", width=240,
            options=[ft.DropdownOption(str(i), b.label) for i, b in enumerate(placements)],
            on_select=self.select_from_list,
        )
        self.coordinates = ft.Text("Select a building; drag its edges or corners to resize.", size=13)
        self.size_fields = {key: ft.TextField(label=key.title(), width=100,
            dense=True, disabled=True, on_submit=self.apply_size) for key in ("width", "height")}
        for field in self.size_fields.values():
            self.shortcuts.watch_text(field)
        self.size_button = ft.Button("Apply size", disabled=True, on_click=self.apply_size)
        self.duplicate_button = ft.Button("Duplicate building", icon=ft.Icons.CONTENT_COPY,
            disabled=True, on_click=self.duplicate_building,
            tooltip="Ctrl+D: copy the selected building, including its floor/roof layers.")
        self.delete_button = ft.Button("Delete building", icon=ft.Icons.DELETE_OUTLINE,
            color="#B42318", disabled=True, on_click=self.delete_building,
            tooltip="Remove the selected building from the map. Source assets are kept. Ctrl+Z restores it.")
        self.undo_button = ft.Button("Undo", disabled=True, on_click=self.undo, tooltip="Ctrl+Z")
        self.redo_button = ft.Button("Redo", disabled=True, on_click=self.redo, tooltip="Ctrl+Y")
        self.toolbar = ft.Column(spacing=3, controls=[
            ft.Row(scroll=ft.ScrollMode.AUTO, spacing=8, controls=[
                self.move_switch, self.selection, self.duplicate_button, self.delete_button,
                *self.size_fields.values(), self.size_button,
                self.undo_button, self.redo_button,
                ft.Button("Export placements", on_click=self.export_dialog),
            ]),
            self.coordinates,
            ft.Text("Temporary edits: export before closing. Turn Edit buildings off to pan.", size=12),
        ])

    def build_content(self):
        canvas = self.map_builder(placements=self.placements, **self.layer_options)
        self.map_canvas = canvas
        # Keep one stationary gesture surface so flipped/moved images
        # don't shift coordinates mid-drag.
        self.building_controls = canvas.controls[-len(self.placements):] if self.placements else []
        self.outline = ft.Container(
            visible=False, border=ft.Border.all(2, "#155EEF"),
            ignore_interactions=True,
        )
        canvas.controls.append(self.outline)
        self.handle_controls = {key: ft.Container(width=12, height=12, visible=False,
            bgcolor="#FFFFFF", border=ft.Border.all(2, "#155EEF"),
            ignore_interactions=True) for key in ("nw", "n", "ne", "e", "se", "s", "sw", "w")}
        canvas.controls.extend(self.handle_controls.values())
        self.update_outline()
        if not self.move_switch.value:
            return canvas
        return ft.GestureDetector(
            width=self.width, height=self.height, content=canvas,
            drag_interval=16, mouse_cursor=ft.MouseCursor.MOVE,
            on_pan_down=self.start_drag, on_pan_start=self.ensure_drag_started,
            on_pan_update=self.drag, on_pan_end=self.end_drag,
            on_pan_cancel=self.end_drag, on_tap_down=self.select_at_pointer,
        )

    def refresh(self):
        if self.viewer is not None:
            self.viewer.content = self.build_content()
            self.viewer.update()

    def building_at(self, x, y):
        # Top-most building wins on overlap.
        return next((i for i in range(len(self.placements) - 1, -1, -1)
                     if self.placements[i].area.contains(x, y)), None)

    def select_at_pointer(self, event):
        if self.move_switch.value:
            if self.selected is not None and hit_resize_handle(self.placements[self.selected],
                    event.local_position.x, event.local_position.y):
                return
            self.select(self.building_at(event.local_position.x, event.local_position.y))

    def select(self, index):
        self.selected = index
        self.selection.value = None if index is None else str(index)
        self.update_outline()
        self.update_coordinates()
        self.update_size_fields()
        self.page.update()

    def select_from_list(self, event):
        self.select(int(event.control.value))

    def update_coordinates(self):
        if self.selected is None:
            self.coordinates.value = "Select a building; drag its edges or corners to resize."
        else:
            b = self.placements[self.selected]
            self.coordinates.value = f"left={b.left:g}, top={b.top:g} | size={b.width:g} x {b.height:g}"

    def update_size_fields(self):
        for key, field in self.size_fields.items():
            field.disabled = self.selected is None
            field.value = "" if self.selected is None else f"{getattr(self.placements[self.selected], key):g}"
        self.size_button.disabled = self.selected is None
        self.duplicate_button.disabled = self.selected is None
        self.delete_button.disabled = self.selected is None

    def update_outline(self):
        if self.outline is None:
            return
        self.outline.visible = self.selected is not None
        for control in self.handle_controls.values():
            control.visible = self.selected is not None and bool(self.move_switch.value)
        if self.selected is not None:
            b = self.placements[self.selected]
            self.outline.left, self.outline.top = b.left, b.top
            self.outline.width, self.outline.height = b.width, b.height
            for key, (x, y) in resize_handles(b).items():
                self.handle_controls[key].left, self.handle_controls[key].top = x - 6, y - 6

    def start_drag(self, event):
        if not self.move_switch.value:
            return
        # Clean up a missed cancellation/end event.
        self.end_drag()
        point = event.local_position
        handle = hit_resize_handle(self.placements[self.selected], point.x, point.y) if self.selected is not None else None
        index = self.selected if handle else self.building_at(point.x, point.y)
        self.select(index)
        if index is not None:
            b = self.placements[index]
            self.drag_index = index
            self.drag_original = b
            self.drag_handle = handle
            self.drag_start = (point.x, point.y)
            self.grab_offset = (point.x - b.left, point.y - b.top)

    def ensure_drag_started(self, event):
        if self.drag_index is None:
            self.start_drag(event)

    def drag(self, event):
        if self.drag_index is None or not self.move_switch.value:
            return
        index = self.drag_index
        b = self.placements[index]
        point = event.local_position
        if self.drag_handle:
            changed = resize_building(self.drag_original, self.drag_handle, self.drag_start,
                (point.x, point.y), self.width, self.height)
            if changed == b:
                return
            self.placements[index] = changed
            self.replace_building_control(index)
            self.update_outline()
            self.update_coordinates()
            self.page.update()
            return
        # Already in map space — don't divide by screen zoom.
        left = round(max(0, min(self.width - b.width, point.x - self.grab_offset[0])), 1)
        top = round(max(0, min(self.height - b.height, point.y - self.grab_offset[1])), 1)
        self.placements[index] = replace(b, left=left, top=top)
        control = self.building_controls[index]
        control.left, control.top = left, top
        self.update_outline()
        self.update_coordinates()
        self.page.update()

    def end_drag(self, event=None):
        if self.drag_index is not None:
            if self.placements[self.drag_index] != self.drag_original:
                self.remember(self.drag_index, self.drag_original)
                self.update_size_fields()
                self.page.update()
        self.drag_index = None
        self.drag_original = None
        self.drag_handle = self.drag_start = None

    def replace_building_control(self, index):
        old = self.building_controls[index]
        b = self.placements[index]
        control = (self.building_builder(b, **self.layer_options) if self.building_builder else
                   self.map_builder(placements=[b], **self.layer_options).controls[-1])
        self.map_canvas.controls[self.map_canvas.controls.index(old)] = control
        self.building_controls[index] = control

    def remember(self, index, original):
        self.record_change(PlacementChange(index, original, self.placements[index]))

    def record_change(self, change):
        self.history.append(change)
        self.history = self.history[-100:]
        self.redo_history.clear()
        self.update_history_buttons()

    def update_history_buttons(self):
        self.undo_button.disabled = not self.history
        self.redo_button.disabled = not self.redo_history

    def apply_size(self, event=None):
        self.end_drag()
        if self.selected is None:
            return
        b = self.placements[self.selected]
        try:
            width, height = (float(self.size_fields[key].value) for key in ("width", "height"))
            if (not all(math.isfinite(n) and n >= MIN_BUILDING_SIZE for n in (width, height))
                    or width > self.width - b.left or height > self.height - b.top):
                raise ValueError("Size must be at least 24 units and fit inside the map.")
        except (ValueError, TypeError) as error:
            self.coordinates.value = f"Size not applied: {error}"
            self.page.update()
            return
        changed = replace(b, width=round(width, 1), height=round(height, 1))
        if changed != b:
            self.placements[self.selected] = changed
            self.remember(self.selected, b)
            self.replace_building_control(self.selected)
        self.update_outline()
        self.update_coordinates()
        self.update_size_fields()
        self.page.update()

    def change_mode(self, event):
        self.end_drag()
        self.viewer.pan_enabled = not self.move_switch.value
        self.refresh()

    def undo(self, event=None):
        self.end_drag()
        if not self.history:
            return
        change = self.history.pop()
        change.apply(self.placements, reverse=True)
        self.redo_history.append(change)
        self.refresh_after_change(change.index)

    def redo(self, event=None):
        self.end_drag()
        if not self.redo_history:
            return
        change = self.redo_history.pop()
        change.apply(self.placements)
        self.history.append(change)
        self.refresh_after_change(change.index)

    def refresh_after_change(self, index):
        self.selected = min(index, len(self.placements) - 1) if self.placements else None
        self.update_selection_options()
        self.update_history_buttons()
        self.update_coordinates()
        self.update_size_fields()
        self.refresh()
        self.page.update()

    def delete_building(self, event=None):
        self.end_drag()
        if self.selected is None:
            return
        index = self.selected
        building = self.placements.pop(index)
        self.record_change(PlacementChange(index, building, None))
        self.refresh_after_change(index)
        self.coordinates.value = f"Removed {building.label} from the map. Ctrl+Z to restore; source assets kept."
        self.page.update()

    def duplicate_building(self, event=None):
        self.end_drag()
        if self.selected is None:
            return
        source = self.placements[self.selected]
        base = re.sub(r" \(copy(?: \d+)?\)$", "", source.label)
        used_labels = {b.label for b in self.placements}
        number = 1
        label = f"{base} (copy)"
        while label in used_labels:
            number += 1
            label = f"{base} (copy {number})"

        def offset(position, size, limit):
            moved = max(0, min(limit - size, position + 24))
            # Nudge inward at the right/bottom edge instead of stacking.
            return round(moved if moved != position else max(0, position - 24), 1)

        copy = replace(source, label=label,
            left=offset(source.left, source.width, self.width),
            top=offset(source.top, source.height, self.height))
        self.add_building(copy)

    def update_selection_options(self):
        self.selection.options = [ft.DropdownOption(str(i), b.label) for i, b in enumerate(self.placements)]
        self.selection.value = None if self.selected is None else str(self.selected)

    def add_building(self, building):
        self.end_drag()
        self.selected = len(self.placements)
        self.placements.append(building)
        self.remember(self.selected, None)
        self.update_selection_options()
        self.move_switch.value = True
        if self.viewer is not None:
            self.viewer.pan_enabled = False
        self.update_coordinates()
        self.update_size_fields()
        self.refresh()
        self.page.update()

    def export_text(self):
        return placement_code(self.placements)

    def export_dialog(self, event=None):
        self.end_drag()
        export = self.export_text()
        status = ft.Text("Replace BUILDINGS_ON_MAP in src/map/placements.py with this code.", size=13)

        async def copy(event):
            try:
                await self.clipboard.set(export)
                status.value = "Copied! Paste over BUILDINGS_ON_MAP in src/map/placements.py and save."
            except Exception:
                status.value = "Clipboard unavailable: select the text below and copy it manually."
            status.update()

        self.page.show_dialog(ft.AlertDialog(
            title=ft.Text("Export building placements"),
            content=ft.Column(tight=True, width=650, controls=[
                status,
                ft.TextField(value=export, read_only=True, multiline=True,
                             min_lines=10, max_lines=15, text_size=12),
            ]),
            actions=[ft.Button("Copy all placements", on_click=copy),
                     ft.TextButton("Close", on_click=lambda event: self.page.pop_dialog())],
        ))
