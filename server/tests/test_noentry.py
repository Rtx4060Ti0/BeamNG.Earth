"""Mapped one-way restrictions, not invented one-way streets."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import furniture
import roads


def arm(fid, end, direction=0, reverse=False, z=0.):
    p = np.array([[0., 0., z], [*end, z]])
    if reverse:
        p = p[::-1].copy()
    return fid, roads.Spec(6., "paved", True, "residential", direction != 0, dir=direction), p, 0.


class NoEntryTest(unittest.TestCase):
    def test_wrong_end_and_geometry_direction(self):
        peers = [arm("b", (-60.,0.)), arm("c", (0.,60.))]
        a = arm("a", (60.,0.), -1)
        b = arm("a", (60.,0.), 1, reverse=True)
        box = (-100.,-100.,100.,100.)
        signs = furniture.no_entry_signs([a]+peers,box)
        self.assertEqual(len(signs),1)
        self.assertEqual(signs,furniture.no_entry_signs([b]+peers,box))
        self.assertGreater(signs[0][1],0.)
        self.assertLess(signs[0][2],-3.)
        self.assertEqual(furniture.no_entry_signs([arm("a",(60.,0.),1)]+peers,box),[])
        self.assertEqual(furniture.no_entry_signs([arm("a",(60.,0.))]+peers,box),[])

    def test_no_sign_at_shape_split_or_grade_separation(self):
        a = arm("a",(60.,0.),-1)
        b = arm("b",(-60.,0.))
        box = (-100.,-100.,100.,100.)
        self.assertEqual(furniture.no_entry_signs([a,b],box),[])
        self.assertEqual(furniture.no_entry_signs([a,b,arm("c",(0.,60.),z=6.)],box),[])

    def test_one_owner_at_tile_boundary(self):
        rs=[arm("a",(60.,0.),-1),arm("b",(-60.,0.)),arm("c",(0.,60.))]
        full=furniture.no_entry_signs(rs,(-100.,-100.,100.,100.))
        tiled=furniture.no_entry_signs(rs,(-100.,-100.,0.,100.))+furniture.no_entry_signs(rs,(0.,-100.,100.,100.))
        self.assertEqual(full,tiled)

