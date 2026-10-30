"""Overlapping bridge carriageways must cover their junction exactly once."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import roadmesh
from test_roads import FRAME


def deck(fid, y, z=10., level=1):
    return dict(m="road_asphalt_2lane", w=8., tl=10., n=[[0., y, z], [20., y, z]],
                deck=True, fixed=True, fid=fid, level=level)


def area(mesh, material=None):
    p, t, uv, mats, m = mesh
    if material is not None:
        t = t[m == mats.index(material)]
    normal = np.cross(p[t[:, 1]] - p[t[:, 0]], p[t[:, 2]] - p[t[:, 0]])
    return np.maximum(normal[:, 2], 0).sum()/2


class DeckJoinTest(unittest.TestCase):
    def test_overlapping_rendered_and_collision_surfaces(self):
        chunks = [deck("a", 0.), deck("b", 4.)]
        visual = roadmesh.build(FRAME, chunks, lambda a, b: a*0, (0., 0., 0.))
        solid = roadmesh.deck(chunks, (0., 0., 0.))
        self.assertAlmostEqual(area(visual), 20.*12., places=5)
        self.assertAlmostEqual(area(solid, roadmesh.DECK_TOP), 20.*(12.+2*roadmesh.PARAPET_W), places=5)
        p, t, uv, _, _ = visual
        np.testing.assert_allclose(uv, p[:, :2]/roadmesh.DECK_TOP_TILE_M)
        self.assertTrue(np.isfinite(p).all())

    def test_clipping_is_stable_between_tiles_and_input_order(self):
        chunks = [deck("a", 0.), deck("b", 4.)]
        def build(ch, box):
            return roadmesh.build(FRAME, ch, lambda a,b: a*0, (0.,0.,0.), clip=box, context=chunks)
        total = sum(area(build(chunks[::-1], box)) for box in ((0.,-10.,10.,10.), (10.,-10.,20.,10.)))
        self.assertAlmostEqual(total, 240., places=5)
        self.assertAlmostEqual(area(build(chunks, (0.,-10.,20.,10.))), total, places=5)

    def test_stacked_levels_and_separated_heights_remain(self):
        for high in (deck("b", 4., 10., 2), deck("b", 4., 16., 1)):
            visual = roadmesh.build(FRAME, [deck("a",0.), high], lambda a,b:a*0, (0.,0.,0.))
            self.assertAlmostEqual(area(visual), 320., places=5)

    def test_subordinate_markings_are_clipped_with_their_road(self):
        chunks = [deck("a", 0.), deck("b", 4.)]
        mark = dict(chunks[1], m="line_white", w=.15, n=[[0.,2.,10.],[20.,2.,10.]], deck=False)
        mesh = roadmesh.build(FRAME, chunks+[mark], lambda a,b:a*0, (0.,0.,0.))
        self.assertAlmostEqual(area(mesh, "line_white"), 0., places=5)

