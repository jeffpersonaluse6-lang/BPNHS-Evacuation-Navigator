"""Gate persistence and collision tests."""
import unittest
from drafting.models import DraftDocument, DraftItem, validate_item
from navigation.collision import barriers_for_item

class GateTests(unittest.TestCase):
    def gate(self, kind="main_gate", open_=False, rotation=0):
        return DraftItem(kind,100,100,240 if kind=="main_gate" else 150,40,
                         rotation=rotation,stroke=10,collision_thickness=12,
                         gate_open=open_,text="Gate")

    def test_gate_types_validate(self):
        validate_item(self.gate("main_gate"))
        validate_item(self.gate("secondary_gate"))

    def test_gate_state_round_trips_json(self):
        doc=DraftDocument()
        doc.floors["Floor 1"]=[self.gate(open_=True)]
        loaded=DraftDocument.from_json(doc.to_json())
        self.assertTrue(loaded.floors["Floor 1"][0].gate_open)

    def test_open_gate_center_is_walkable(self):
        gate=self.gate(open_=True)
        barriers=barriers_for_item(gate)
        cx,cy=gate.local_to_world(gate.width/2,gate.height/2)
        self.assertFalse(any(b.blocks(cx,cy,1) for b in barriers))

    def test_closed_gate_blocks_center(self):
        gate=self.gate(open_=False)
        barriers=barriers_for_item(gate)
        cx,cy=gate.local_to_world(gate.width/2,gate.height/2)
        self.assertTrue(any(b.blocks(cx,cy,1) for b in barriers))

    def test_open_gate_posts_still_block(self):
        gate=self.gate(open_=True)
        barriers=barriers_for_item(gate)
        px,py=gate.local_to_world(0,gate.height/2)
        self.assertTrue(any(b.blocks(px,py,1) for b in barriers))

    def test_rotated_closed_gate_still_blocks(self):
        gate=self.gate(open_=False,rotation=90)
        barriers=barriers_for_item(gate)
        cx,cy=gate.local_to_world(gate.width/2,gate.height/2)
        self.assertTrue(any(b.blocks(cx,cy,1) for b in barriers))

if __name__=="__main__":
    unittest.main()
