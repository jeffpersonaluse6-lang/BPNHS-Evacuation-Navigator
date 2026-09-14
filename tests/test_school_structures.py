"""School structure tools, curved collisions, distinct roofs and cached fading."""

from dataclasses import replace
import math
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import flet as ft
from drafting.models import DraftItem,DraftDocument,primitives,validate_item
from drafting.handles import transform,handles
from drafting.circular import solid_arcs,wall_polygons
from drafting.roof import ROOF_KINDS
from map.scene import CAMPUS,MapScene,scope_key
from map.workspace_editor import MapWorkspaceEditor,MAP_TOOLS
from map.scene_renderer import item_shapes,render_scene
from map.scene_store import save_scene,load_scene
from map.world_renderer import WorldMapView
from map.flips import flip_items
from map.alignment import bounds
from navigation.collision import barriers_for,project_barriers,snap_opening_to_wall,move_with_collisions,PolygonBarrier
from navigation.models import NavigationState
from navigation.world import WorldNavigator
from test_map_workspace import page_stub,pointer
from player_fixtures import isolate_player_settings


def event(value):return SimpleNamespace(control=SimpleNamespace(value=value))


class CircularWallTests(unittest.TestCase):
    def wall(self):return DraftItem("circle_wall",100,100,400,400,stroke=8,collision_thickness=20)

    def test_rim_collision_is_circular_not_a_square_or_filled_disk(self):
        wall=self.wall();barriers=barriers_for([wall])
        self.assertFalse(any(b.blocks(300,300,10) for b in barriers))
        self.assertFalse(any(b.blocks(105,105,10) for b in barriers))
        for angle in range(0,360,7):
            a=math.radians(angle)
            for radius,blocked in ((175,False),(195,True),(205,True),(225,False)):
                x,y=300+radius*math.cos(a),300+radius*math.sin(a)
                self.assertEqual(any(b.blocks(x,y,2) for b in barriers),blocked)
        self.assertFalse(wall.contains(100,100,tolerance=0));self.assertFalse(wall.contains(300,300))
        self.assertTrue(wall.contains(500,300))
        moved=move_with_collisions(300,300,300,0,10,barriers,1000,1000)
        self.assertLess(moved[0],481);self.assertGreater(moved[0],470)

    def test_tangent_doors_and_openings_leave_passable_curved_gaps_at_every_rotation(self):
        for kind in ("door","double_door","opening"):
            for rotation in (0,37,90):
                for mirrored in (False,True):
                    wall=replace(self.wall(),x=600,y=450,rotation=rotation,mirrored=mirrored)
                    rim=wall.local_to_world(400,200)
                    door=snap_opening_to_wall(DraftItem(kind,0,0,100,12 if kind=="opening" else 60),[wall],rim)
                    door=replace(door,parent_id=wall.id)
                    self.assertEqual(door.width,100)
                    self.assertNotEqual(solid_arcs(wall,[door]),((0,2*math.pi),))
                    start=wall.local_to_world(320,200);end=wall.local_to_world(480,200)
                    moved=move_with_collisions(*start,end[0]-start[0],end[1]-start[1],10,barriers_for([wall,door]),2000,2000)
                    for a,b in zip(moved,end):self.assertAlmostEqual(a,b)
                    blocked=barriers_for([wall,door])
                    self.assertTrue(any(b.blocks(*wall.local_to_world(200,0),5) for b in blocked))

    def test_collision_thickness_does_not_change_visual_wall_or_accept_unrelated_door(self):
        wall=self.wall();thicker=replace(wall,collision_thickness=60)
        self.assertEqual(primitives(wall),primitives(thicker))
        unrelated=DraftItem("door",1000,1000,100,60)
        self.assertEqual(barriers_for([wall]),barriers_for([wall,unrelated]))
        self.assertEqual(barriers_for([replace(wall,blocking=False)]),[])
        self.assertFalse(any(b.blocks(300,300,2) for b in barriers_for([thicker])))

    def test_visual_and_debug_boundaries_are_annular_and_draw_calls_remain_small(self):
        wall=self.wall();polygon=wall_polygons(wall)[0];area=PolygonBarrier(polygon)
        self.assertFalse(area.blocks(300,300,0));self.assertTrue(area.blocks(498,300,0))
        self.assertLessEqual(len(item_shapes(wall,collisions=True)),3)
        self.assertNotEqual(item_shapes(wall),item_shapes(replace(wall,width=500,height=500)))

    def test_parent_nonuniform_scale_transforms_collision_without_filling_interior(self):
        wall=self.wall();barriers=project_barriers(barriers_for([wall]),lambda x,y:(x*2,y*.5),(2,.5))
        self.assertFalse(any(b.blocks(600,150,5) for b in barriers))
        self.assertTrue(any(b.blocks(1000,150,5) for b in barriers))

    def test_radius_handles_keep_circular_diameter_when_rotated_or_flipped(self):
        for kind in ("circle_wall","gazebo_roof"):
            item=DraftItem(kind,500,500,200,200,rotation=37,mirrored=True)
            for handle in ("e","w","n","s","se","nw"):
                start=handles(item)[handle]
                result=transform(item,handle,start,(start[0]+37,start[1]+19))
                self.assertAlmostEqual(result.width,result.height)
                validate_item(result)
            self.assertAlmostEqual(bounds(item)[0][1]-bounds(item)[0][0],200)


class SchoolStructureEditorTests(unittest.TestCase):
    def setUp(self):
        isolate_player_settings(self)
        updater=patch.object(ft.Control,"update");updater.start();self.addCleanup(updater.stop)
        self.editor=MapWorkspaceEditor(page_stub(),MapScene())

    def select(self,item):
        self.editor.items().append(item);self.editor.selection.select({item.id},False)
        self.editor.refresh(properties=True)

    def test_tools_create_separate_types_with_sensible_defaults(self):
        for kind in ("circle_wall","gazebo_roof","court_roof"):
            self.assertIn(kind,dict(MAP_TOOLS));self.assertIn(kind,self.editor.tool_buttons)
            item=self.editor.create_item(kind,100,100,300,300)
            validate_item(item);self.assertTrue(primitives(item))
            if kind=="circle_wall":self.assertEqual(item.collision_thickness,8)
            else:self.assertFalse(barriers_for([item]))
        normal=self.editor.create_item("roof",0,0,800,450)
        court=self.editor.create_item("court_roof",0,0,800,450)
        gazebo=self.editor.create_item("gazebo_roof",0,0,450,450)
        self.assertNotEqual(primitives(normal),primitives(court))
        self.assertNotEqual(primitives(normal),primitives(gazebo))
        self.assertFalse(gazebo.contains(0,0,tolerance=0));self.assertTrue(gazebo.contains(225,225))

    def test_radius_diameter_visual_thickness_and_collision_controls_support_undo(self):
        item=self.editor.create_item("circle_wall",100,100,300,300);self.select(item)
        controls=self.editor.structures;self.assertTrue(controls.circle_control.visible)
        self.assertTrue(self.editor.collision_editor.control.visible)
        controls.radius.value="200";controls.resize(True)
        changed=self.editor.selected_item();self.assertEqual((changed.width,changed.height),(400,400))
        self.assertEqual(changed.local_to_world(200,200),item.local_to_world(150,150))
        controls.diameter.value="350";controls.resize(False)
        self.assertEqual(self.editor.selected_item().width,350)
        self.editor.collision_editor.type_value(event("32"));changed=self.editor.selected_item()
        self.assertEqual(changed.collision_thickness,32);self.assertEqual(changed.stroke,8)
        self.editor.properties["stroke"].value="12";self.editor.apply_properties()
        self.assertEqual(self.editor.selected_item().collision_thickness,32)
        self.editor.history(False);self.assertEqual(self.editor.selected_item().stroke,8)

    def test_new_shapes_copy_between_floors_group_flip_duplicate_and_roundtrip(self):
        self.editor.choose_tool("building");editor=self.editor.builder
        items=[editor.create_item(kind,100+index*400,100,300,300) for index,kind in
            enumerate(("circle_wall","gazebo_roof","court_roof"))]
        editor.items().extend(items);editor.selection.select({i.id for i in items})
        editor.selection.group();editor.selection.copy();editor.floor_done();editor.selection.paste()
        self.assertEqual([i.kind for i in editor.items()],[i.kind for i in items])
        self.assertEqual([(i.x,i.y) for i in editor.items()],[(i.x,i.y) for i in items])
        self.assertEqual(len({i.group_id for i in editor.items()}),1)
        editor.selection.flip();editor.selection.duplicate();self.assertEqual(len(editor.items()),6)
        before=editor.document.snapshot()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"structures.json";save_scene(editor.document,path)
            self.assertEqual(load_scene(path).snapshot(),before)
        editor.selection.delete();self.assertEqual(len(editor.items()),3)
        editor.history(False);self.assertEqual(editor.document.snapshot(),before)

    def test_roof_opacity_updates_editor_immediately_and_is_saved(self):
        for kind in ROOF_KINDS:
            self.editor.document.floors[CAMPUS]=[]
            item=self.editor.create_item(kind,100,100,320,320);self.select(item)
            self.assertTrue(self.editor.structures.opacity.visible)
            self.editor.structures.change_opacity(event("0.4"))
            changed=self.editor.selected_item();self.assertEqual(changed.opacity,.4)
            self.assertEqual(self.editor.vector_cache[item.id][1].opacity,.4)
            self.assertEqual(MapScene.from_json(self.editor.document.to_json()).snapshot(),self.editor.document.snapshot())
            self.editor.history(False);self.assertEqual(self.editor.selected_item().opacity,1)

    def test_invalid_radius_opacity_and_diameter_do_not_mutate_document(self):
        item=self.editor.create_item("gazebo_roof",100,100,320,320);self.select(item)
        before=self.editor.document.snapshot()
        for value in ("-1","nan","inf","100001"):
            self.editor.structures.diameter.value=value;self.editor.structures.resize(False)
            self.assertEqual(self.editor.document.snapshot(),before)
        for value in ("-1","nan","inf","1.1"):
            self.editor.structures.change_opacity(event(value));self.assertEqual(self.editor.document.snapshot(),before)

    def test_editor_and_runtime_controls_encode_for_flet_desktop(self):
        import msgpack
        from flet.messaging.protocol import configure_encode_object_for_msgpack
        self.editor.document.floors[CAMPUS]=[self.editor.create_item(kind,100+n*400,100,300,300)
            for n,kind in enumerate(("circle_wall","gazebo_roof","court_roof"))]
        self.editor.refresh(properties=True)
        encoder=configure_encode_object_for_msgpack(ft.Control)
        self.assertTrue(msgpack.packb(self.editor.control,default=encoder))
        self.assertTrue(msgpack.packb(WorldMapView(self.editor.document).control,default=encoder))


class RoofRuntimeTests(unittest.TestCase):
    def test_standalone_roofs_fade_by_shape_without_geometry_rebuilding(self):
        for kind,width,height in (("gazebo_roof",400,400),("court_roof",1000,500)):
            scene=MapScene();roof=DraftItem(kind,100,100,width,height,fill="#AA7744",opacity=.8,approach_distance=20)
            scene.floors[CAMPUS]=[roof];view=WorldMapView(scene);nav=WorldNavigator(scene,NavigationState())
            control=view.object_roofs.records[roof.id][2];shapes=control.content.shapes
            with patch("map.roof_fading.item_shapes",side_effect=AssertionError("geometry rebuild")):
                view.update(nav,(100+width/2,100+height/2));self.assertEqual(control.opacity,0)
                view.update(nav,(2500,1100));self.assertEqual(control.opacity,.8)
                self.assertIs(control.content.shapes,shapes)
            self.assertEqual((roof.width,roof.height),(width,height))
            self.assertFalse(nav.campus_barriers)

    def test_nonfading_roof_keeps_user_opacity_and_gazebo_corner_is_not_inside(self):
        scene=MapScene();roof=DraftItem("gazebo_roof",100,100,400,400,opacity=.6,approach_distance=0)
        scene.floors[CAMPUS]=[roof];view=WorldMapView(scene);nav=WorldNavigator(scene,NavigationState())
        control=view.object_roofs.records[roof.id][2]
        view.update(nav,(105,105));self.assertEqual(control.opacity,.6)
        view.update(nav,(300,300));self.assertEqual(control.opacity,0)
        scene.floors[CAMPUS]=[replace(roof,fade_when_obstructing=False)];view=WorldMapView(scene)
        view.update(nav,(300,300));self.assertEqual(view.object_roofs.records[roof.id][2].opacity,.6)

    def test_roof_floor_assignment_and_ghost_editor_are_shared_not_runtime_tools(self):
        scene=MapScene();parent=DraftItem("building",100,100,600,400,floor_count=2)
        roof=DraftItem("court_roof",0,0,1436,751,fill="#AACCDD")
        scene.floors={CAMPUS:[parent],scope_key(parent,"Floor 1"):[],scope_key(parent,"Floor 2"):[],scope_key(parent,"Roof"):[roof]}
        view=WorldMapView(scene);self.assertIn((parent.id,"Roof"),view.layers)
        self.assertIn(roof.id,view.object_roofs.records)
        self.assertEqual(len(view.layers[parent.id,"Roof"][0].content.controls[0].shapes),0)
        nav=WorldNavigator(scene,NavigationState());nav.enter(parent)
        view.update(nav,scene.project(scope_key(parent,"Roof"),700,300))
        self.assertEqual(view.layers[parent.id,"Roof"][0].opacity,0)
        self.assertEqual(nav.state.floor,1)
        MapScene.from_json(scene.to_json())

    def test_exported_svg_has_distinct_roofs_and_opacity(self):
        doc=DraftDocument();floor=next(iter(doc.floors))
        doc.floors[floor]=[DraftItem(k,100+n*300,100,280,280,fill="#BB8844",opacity=.5)
            for n,k in enumerate(("circle_wall","gazebo_roof","court_roof"))]
        root=ET.fromstring(doc.svg(floor));self.assertEqual(len(root.findall("{http://www.w3.org/2000/svg}g")),2)
        self.assertEqual(DraftDocument.from_json(doc.to_json()).snapshot(),doc.snapshot())


if __name__=="__main__":unittest.main()
