import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('audit_france_index', Path(__file__).resolve().parents[2] / 'tools/audit_france_index.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class AuditRules(unittest.TestCase):
    def check(self, **tags):
        return audit.inspect({'highway': 'residential', **tags}, 3, 1, 2)

    def test_real_units_and_angles(self):
        self.assertAlmostEqual(audit.metres('6\'6"'), 1.9812)
        self.assertEqual(audit.metres('2.5 m'), 2.5)
        self.assertAlmostEqual(audit.grade('45°'), 100)
        self.assertEqual(audit.grade('-12 %'), -12)
        self.assertIsNone(audit.metres('NaN'))

    def test_missing_tags_are_not_errors(self):
        self.assertEqual(self.check(), [])
        self.assertEqual(self.check(bridge='yes'), [])
        self.assertEqual(self.check(tunnel='yes', layer='-1'), [])

    def test_reviews_are_class_specific(self):
        self.assertIn('incline_extreme_review', self.check(highway='motorway', incline='11%'))
        self.assertNotIn('incline_extreme_review', self.check(highway='steps', incline='45°'))
        self.assertNotIn('narrow_motor_road_review', self.check(highway='footway', width='.8'))
        self.assertIn('narrow_motor_road_review', self.check(width='1.5'))

    def test_degenerate_reference_and_conflicts(self):
        self.assertIn('degenerate_way', audit.inspect({}, 2, 7, 7))
        self.assertNotIn('degenerate_way', audit.inspect({}, 5, 7, 7))
        self.assertIn('bridge_and_tunnel_review', self.check(bridge='yes', tunnel='yes'))
        self.assertEqual(self.check(incline='up/down', oneway='reversible'), [])


if __name__ == '__main__':
    unittest.main()
