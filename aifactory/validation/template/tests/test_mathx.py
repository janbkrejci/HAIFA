import unittest

from sandbox import mathx


class ModuleTest(unittest.TestCase):
    def test_exports_a_list(self) -> None:
        self.assertIsInstance(mathx.__all__, list)


@unittest.skipUnless(hasattr(mathx, "clamp"), "clamp is not there yet (M01-S01-T01)")
class ClampTest(unittest.TestCase):
    def test_clamp(self) -> None:
        self.assertEqual(mathx.clamp(5, 0, 3), 3)
        self.assertEqual(mathx.clamp(-1, 0, 3), 0)
        self.assertEqual(mathx.clamp(2, 0, 3), 2)
        self.assertIn("clamp", mathx.__all__)


@unittest.skipUnless(hasattr(mathx, "lerp"), "lerp is not there yet (M01-S01-T02)")
class LerpTest(unittest.TestCase):
    def test_lerp(self) -> None:
        self.assertEqual(mathx.lerp(0, 10, 0.5), 5.0)
        self.assertEqual(mathx.lerp(2, 4, 0), 2)
        self.assertEqual(mathx.lerp(2, 4, 1), 4)
        self.assertIn("lerp", mathx.__all__)
