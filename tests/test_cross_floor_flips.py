"""Persistent floor clipboard and geometric flips without opening native UI."""

from dataclasses import asdict,replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import flet as ft
from drafting.models import DraftItem,primitives
from map.scene import MapScene,CAMPUS,scope_key
from map.scene_store import save_scene,load_scene
from map.workspace_editor import MapWorkspaceEditor
from map.flips import flip_items
from map.alignment import bounds
from navigation.collision import barriers_for
from navigation.stairs import transitions,section_progress,indicators
from test_map_workspace import page_stub,keyboard
from player_fixtures import isolate_player_settings


class CrossFloorClipboardTests(unittest.TestCase):
    def setUp(self):
        isolate_player_settings(self)
        updater=patch.object(ft.Control,"update");updater.start();self.addCleanup(updater.stop)
        self.owner=MapWorkspaceEditor(page_stub(),MapScene());self.owner.mount()
        self.owner.choose_tool("building");self.editor=self.owner.builder
        self.parent=self.editor.building();self.floor1=self.editor.floor

    def layout(self):
        wall=DraftItem("wall",100,100,400,0,stroke=8,collision_thickness=16,
            group_id="original-group",parent_id=self.parent.id,text="wall")
        door=DraftItem("door",250,40,100,60,rotation=0,parent_id=wall.id,
            group_id="original-group",text="door")
        rail=DraftItem("railing",120,200,200,20,stroke=14,collision_thickness=22,
            rotation=17,mirrored=True,blocking=False,text="rail")
        stair=DraftItem("stairs",600,100,90,240,stair_from=1,stair_to=2,
            stair_speed_multiplier=.4,collision_thickness=10,text="stair")
        self.editor.items().extend([wall,door,rail,stair]);self.editor.refresh(properties=True)
        return wall,door,rail,stair

    def test_keyboard_copy_floor_done_paste_preserves_all_objects_and_exact_positions(self):
        originals=self.layout();editor=self.editor
        editor.page.on_keyboard_event(keyboard("a"));editor.page.on_keyboard_event(keyboard("c"))
        clipboard=editor.selection.clipboard
        editor.floor_done();floor2=editor.floor
        self.assertNotEqual(floor2,self.floor1)
        self.assertIs(editor.selection.clipboard,clipboard)
        editor.page.on_keyboard_event(keyboard("v"));copies=editor.items()
        self.assertEqual(len(copies),len(originals))
        self.assertEqual(editor.document.floors[self.floor1],list(originals))
        old_by_label={i.text:i for i in originals};new_by_label={i.text:i for i in copies}
        self.assertTrue({i.id for i in originals}.isdisjoint(i.id for i in copies))
        for item in copies:
            old=old_by_label[item.text];actual=asdict(item);expected=asdict(old)
            for key in ("id","parent_id","group_id","stair_from","stair_to","stair_enabled"):
                actual.pop(key);expected.pop(key)
            self.assertEqual(actual,expected)
        self.assertEqual(new_by_label["wall"].group_id,new_by_label["door"].group_id)
        self.assertNotEqual(new_by_label["wall"].group_id,"original-group")
        self.assertEqual(new_by_label["wall"].parent_id,self.parent.id)
        self.assertEqual(new_by_label["door"].parent_id,new_by_label["wall"].id)
        self.assertEqual(new_by_label["stair"].stair_from,2)
        self.assertFalse(new_by_label["stair"].stair_enabled)
        self.assertIsNone(new_by_label["stair"].stair_to)
        self.assertFalse(any(b.blocks(300,100,1) for b in barriers_for(copies)))
        self.assertTrue(any(b.blocks(180,100,1) for b in barriers_for(copies)))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"test-map.json";save_scene(editor.document,path)
            self.assertEqual(load_scene(path).snapshot(),editor.document.snapshot())
        editor.history(False);self.assertEqual(editor.items(),[])
        editor.history(True);self.assertEqual(editor.items(),copies)

    def test_repeated_paste_keeps_clipboard_and_stair_destinations_dynamic(self):
        self.layout();editor=self.editor;editor.select_all();editor.selection.copy()
        for _ in range(3):editor.add_floor()
        for n in (2,3):
            editor.change_scope(scope_key(editor.building(),f"Floor {n}"));editor.selection.paste()
            stair=next(i for i in editor.items() if i.kind=="stairs")
            self.assertEqual((stair.stair_from,stair.stair_to),(n,n+1));self.assertTrue(stair.stair_enabled)
        self.assertEqual(editor.selection.clipboard.source_scope,self.floor1)

    def test_floor_change_clears_hidden_inspector_focus_that_blocks_shortcuts(self):
        wall=self.layout()[0];editor=self.editor;editor.selection.select({wall.id});editor.selection.copy()
        editor.add_floor();editor.shortcuts.text_focused=True
        editor.change_scope(scope_key(editor.building(),"Floor 2"))
        editor.page.on_keyboard_event(keyboard("v"))
        self.assertEqual(len(editor.items()),2)  # The wall's manual group includes its door.

    def test_same_floor_paste_and_duplicate_keep_existing_offset(self):
        wall=self.layout()[0];editor=self.editor;editor.selection.select({wall.id});editor.selection.copy()
        editor.selection.paste();pasted=next(i for i in editor.selection.items() if i.kind=="wall")
        self.assertEqual((pasted.x,pasted.y),(wall.x+24,wall.y+24))
        editor.selection.duplicate();duplicate=next(i for i in editor.selection.items() if i.kind=="wall")
        self.assertEqual((duplicate.x,duplicate.y),(pasted.x+24,pasted.y+24))

    def test_paste_into_another_building_rebinds_parent_and_copied_attachment(self):
        originals=self.layout();editor=self.editor;editor.select_all();editor.selection.copy()
        editor.close();self.owner.choose_tool("building");other=self.owner.builder
        self.assertNotEqual(other.building_id,self.parent.id)
        other.selection.paste();copied={i.text:i for i in other.items()}
        self.assertEqual(copied["wall"].parent_id,other.building_id)
        self.assertEqual(copied["door"].parent_id,copied["wall"].id)
        self.assertEqual((copied["wall"].x,copied["wall"].y),(originals[0].x,originals[0].y))
        MapScene.from_json(other.document.to_json())


class FlipGeometryTests(unittest.TestCase):
    def objects(self):
        return [DraftItem(kind,350+index*27,250+index*11,120,
                -55 if kind in {"wall","line","railing"} else 160,
                rotation=37,mirrored=bool(index%2),stroke=8,collision_thickness=16,
                group_id="same-group",stair_from=2,stair_to=3,stair_speed_multiplier=.5)
            for index,kind in enumerate(("room","wall","railing","stairs","door","double_door",
                "opening","window","rectangle","floor","roof","ellipse","line","text","dimension"))]

    def assert_point(self,actual,expected):
        for a,b in zip(actual,expected):self.assertAlmostEqual(a,b,places=7)

    def test_single_multiple_and_group_flips_reflect_every_drawn_point_exactly(self):
        objects=self.objects()
        for items in ([item] for item in objects):self.check_reflection(items)
        self.check_reflection(objects)

    def check_reflection(self,items):
        boxes=[bounds(i) for i in items]
        center=tuple((min(b[a][0] for b in boxes)+max(b[a][1] for b in boxes))/2 for a in (0,1))
        for vertical in (True,False):
            flipped=flip_items(items,vertical)
            for original in items:
                changed=flipped[original.id]
                for key,value in asdict(original).items():
                    if key not in {"x","y","rotation","mirrored"}:self.assertEqual(getattr(changed,key),value)
                points=[(0,0),(original.width/2,original.height/2),(original.width,original.height)]
                points.extend(p for shape in primitives(original) for p in shape.get("points",[]))
                for p in points:
                    x,y=original.local_to_world(*p)
                    self.assert_point(changed.local_to_world(*p),(x,2*center[1]-y) if vertical else (2*center[0]-x,y))
            restored=flip_items(flipped.values(),vertical)
            for original in items:
                item=restored[original.id]
                self.assert_point((item.x,item.y),(original.x,original.y))
                self.assertEqual((item.rotation,item.mirrored),(original.rotation,original.mirrored))

    def test_collision_and_doorway_gaps_are_reflected_with_the_objects(self):
        wall=DraftItem("wall",100,100,500,0,collision_thickness=16)
        door=DraftItem("door",250,40,100,60,parent_id=wall.id)
        rail=DraftItem("railing",120,200,200,0,collision_thickness=22)
        items=[wall,door,rail];flipped=list(flip_items(items).values())
        boxes=[bounds(i) for i in items];cy=(min(b[1][0] for b in boxes)+max(b[1][1] for b in boxes))/2
        before=barriers_for(items);after=barriers_for(flipped)
        for x in (120,180,249,270,300,330,351,500):
            for y in (90,99,100,101,110,190,200,210):
                for radius in (0,2,10):
                    self.assertEqual(any(b.blocks(x,y,radius) for b in before),
                        any(b.blocks(x,2*cy-y,radius) for b in after))
        self.assertFalse(any(b.blocks(300,2*cy-100,2) for b in after))

    def test_stair_progress_and_arrow_flip_without_reversing_floor_connection(self):
        for direction,to in (("up",3),("down",1)):
            stair=DraftItem("stairs",200,100,120,240,stair_from=2,stair_to=to,stair_direction=direction)
            changed=flip_items([stair])[stair.id]
            old=transitions(stair,2,4)[0];new=transitions(changed,2,4)[0]
            self.assertEqual((new.source,new.target,new.direction),(2,to,direction))
            for p in (0,.25,.5,.75,1):
                x,y=stair.local_to_world(60,240*(1-p) if direction=="up" else 240*p)
                self.assertAlmostEqual(section_progress(new,(x,440-y))[0],p)
            for (start,end,_), (new_start,new_end,_) in zip(indicators(stair),indicators(changed)):
                for a,b in ((start,new_start),(end,new_end)):
                    x,y=stair.local_to_world(*a);self.assert_point(changed.local_to_world(*b),(x,440-y))

    def test_editor_buttons_and_group_flip_are_single_undoable_edits(self):
        isolate_player_settings(self)
        with patch.object(ft.Control,"update"):
            editor=MapWorkspaceEditor(page_stub(),MapScene());editor.choose_tool("building");editor=editor.builder
            editor.add_floor();editor.add_floor();editor.change_scope(scope_key(editor.building(),"Floor 2"))
            items=self.objects();editor.items().extend(items);editor.selection.select({items[0].id})
            before=editor.document.snapshot()
            buttons={c.content:c for c in editor.control.controls[1].controls if isinstance(c,ft.Button)}
            self.assertIn("Flip Horizontal",buttons);self.assertNotIn("Flip Vertical",buttons)
            inspector=editor.sidebar.content.controls
            self.assertIs(inspector[inspector.index(editor.mirror)+1],editor.flip_vertical_button)
            editor.refresh(properties=True);self.assertFalse(editor.flip_vertical_button.disabled)
            editor.flip_vertical_button.on_click(None)
            after=editor.document.snapshot();self.assertNotEqual(after,before)
            self.assertEqual(MapScene.from_json(editor.document.to_json()).snapshot(),after)
            self.assertEqual(len(editor.selection.items()),len(items))
            self.assertEqual({i.group_id for i in editor.items()},{"same-group"})
            self.assertEqual(set(i.id for i in editor.items()),set(i.id for i in items))
            editor.history(False);self.assertEqual(editor.document.snapshot(),before)
            editor.history(True);self.assertEqual(editor.document.snapshot(),after)


if __name__=="__main__":unittest.main()
