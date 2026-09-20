import unittest
import sys
import os

# Add src to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from openrgb_temp_sync.lighting import (
    map_temp_to_rgb,
    apply_ema,
    lerp_color,
    create_tray_image
)

class TestLighting(unittest.TestCase):
    def test_map_temp_below_or_at_min(self):
        # Default: 30=Green, 60=Blue, 75=Red
        color_below = map_temp_to_rgb(25.0, min_temp=30.0, mid_temp=60.0, max_temp=75.0,
                                      min_color=[0, 255, 0], mid_color=[0, 0, 255], max_color=[255, 0, 0])
        self.assertEqual(color_below, (0, 255, 0))

        color_at = map_temp_to_rgb(30.0, min_temp=30.0, mid_temp=60.0, max_temp=75.0,
                                   min_color=[0, 255, 0], mid_color=[0, 0, 255], max_color=[255, 0, 0])
        self.assertEqual(color_at, (0, 255, 0))

    def test_map_temp_above_or_at_max(self):
        color_at = map_temp_to_rgb(75.0, min_temp=30.0, mid_temp=60.0, max_temp=75.0,
                                   min_color=[0, 255, 0], mid_color=[0, 0, 255], max_color=[255, 0, 0])
        self.assertEqual(color_at, (255, 0, 0))

        color_above = map_temp_to_rgb(90.0, min_temp=30.0, mid_temp=60.0, max_temp=75.0,
                                      min_color=[0, 255, 0], mid_color=[0, 0, 255], max_color=[255, 0, 0])
        self.assertEqual(color_above, (255, 0, 0))

    def test_map_temp_mid(self):
        color_mid = map_temp_to_rgb(60.0, min_temp=30.0, mid_temp=60.0, max_temp=75.0,
                                    min_color=[0, 255, 0], mid_color=[0, 0, 255], max_color=[255, 0, 0])
        self.assertEqual(color_mid, (0, 0, 255))

    def test_map_temp_interpolation(self):
        # Exactly halfway between 30 and 60 is 45: halfway between (0, 255, 0) and (0, 0, 255) -> (0, 127, 127)
        color_half = map_temp_to_rgb(45.0, min_temp=30.0, mid_temp=60.0, max_temp=75.0,
                                     min_color=[0, 255, 0], mid_color=[0, 0, 255], max_color=[255, 0, 0])
        self.assertEqual(color_half, (0, 127, 127))

    def test_brightness_scaling(self):
        full = map_temp_to_rgb(30.0, min_temp=30.0, mid_temp=60.0, max_temp=75.0,
                               min_color=[0, 255, 0], mid_color=[0, 0, 255], max_color=[255, 0, 0],
                               brightness=100)
        self.assertEqual(full, (0, 255, 0))

        half = map_temp_to_rgb(30.0, min_temp=30.0, mid_temp=60.0, max_temp=75.0,
                               min_color=[0, 255, 0], mid_color=[0, 0, 255], max_color=[255, 0, 0],
                               brightness=50)
        self.assertEqual(half, (0, 127, 0))

        zero = map_temp_to_rgb(30.0, min_temp=30.0, mid_temp=60.0, max_temp=75.0,
                               min_color=[0, 255, 0], mid_color=[0, 0, 255], max_color=[255, 0, 0],
                               brightness=0)
        self.assertEqual(zero, (0, 0, 0))

    def test_apply_ema(self):
        # Initial smoothed temp
        self.assertAlmostEqual(apply_ema(None, 50.0, 0.15), 50.0)
        # Update with raw 60.0 and alpha 0.15: 0.15*60 + 0.85*50 = 9 + 42.5 = 51.5
        self.assertAlmostEqual(apply_ema(50.0, 60.0, 0.15), 51.5)

    def test_lerp_color(self):
        curr = (0.0, 0.0, 0.0)
        target = (100.0, 200.0, 50.0)
        # step_factor = 0.5
        result = lerp_color(curr, target, 0.5)
        self.assertEqual(result, (50.0, 100.0, 25.0))

    def test_create_tray_image(self):
        img = create_tray_image((0, 255, 0))
        self.assertIsNotNone(img)
        self.assertEqual(img.size, (64, 64))
        self.assertEqual(img.mode, "RGBA")

if __name__ == '__main__':
    unittest.main()