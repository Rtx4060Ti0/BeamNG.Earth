"""A lower neighbouring road must not create a step in a continuous carriageway."""
import unittest
import numpy as np
import grading


class NeighbourBlend(unittest.TestCase):
    def test_neighbour_crossing_separation_threshold_is_continuous(self):
        main = grading.Plan(np.array([[-30., 0.], [30., 0.]]), np.array([10., 10.]), 3.)
        side = grading.Plan(np.array([[-30., 5.5], [30., 5.5]]), np.array([5., 11.]), 2.)
        main.rid, side.rid = 1, 2
        x = np.linspace(-.5, .5, 101)
        z = grading.grade_points(x, np.zeros(len(x)), np.full(len(x), 10.), [main, side])
        self.assertLess(np.max(np.abs(np.diff(z))), .005)
        self.assertLess(np.max(np.abs(z - 10.)), .1)

    def test_equal_height_junction_still_blends(self):
        a = grading.Plan(np.array([[-30., 0.], [30., 0.]]), np.array([10., 10.]), 3.)
        b = grading.Plan(np.array([[0., -30.], [0., 30.]]), np.array([10., 10.]), 3.)
        a.rid, b.rid = 1, 2
        z = grading.grade_points(np.array([0., 1.]), np.array([0., 1.]), np.zeros(2), [a, b])
        np.testing.assert_allclose(z, 10.)


if __name__ == '__main__':
    unittest.main()
