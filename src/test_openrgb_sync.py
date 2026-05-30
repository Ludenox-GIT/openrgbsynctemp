import unittest
from openrgb_temp_sync import map_temp_to_rgb

class TestOpenRGBTempSync(unittest.TestCase):
    def test_map_temp_to_rgb_low_threshold(self):
        # Temp below or equal to min_temp should return solid Green (0, 255, 0)
        self.assertEqual(map_temp_to_rgb(25.0, 30.0, 60.0, 75.0), (0, 255, 0))
        self.assertEqual(map_temp_to_rgb(30.0, 30.0, 60.0, 75.0), (0, 255, 0))

    def test_map_temp_to_rgb_high_threshold(self):
        # Temp above or equal to max_temp should return solid Red (255, 0, 0)
        self.assertEqual(map_temp_to_rgb(80.0, 30.0, 60.0, 75.0), (255, 0, 0))
        self.assertEqual(map_temp_to_rgb(75.0, 30.0, 60.0, 75.0), (255, 0, 0))

    def test_map_temp_to_rgb_mid_threshold(self):
        # Midpoint (60.0) should be solid Blue (0, 0, 255)
        self.assertEqual(map_temp_to_rgb(60.0, 30.0, 60.0, 75.0), (0, 0, 255))
        
        # Quarter point (45.0) (between Green and Blue) should be Teal
        r, g, b = map_temp_to_rgb(45.0, 30.0, 60.0, 75.0)
        self.assertEqual(r, 0)
        self.assertTrue(0 < g < 255)
        self.assertTrue(0 < b < 255)
        self.assertEqual(g, 127)
        self.assertEqual(b, 127)

        # Three-quarters point (67.5) (between Blue and Red) should be Purple
        r, g, b = map_temp_to_rgb(67.5, 30.0, 60.0, 75.0)
        self.assertTrue(0 < r < 255)
        self.assertEqual(g, 0)
        self.assertTrue(0 < b < 255)
        self.assertEqual(r, 127)
        self.assertEqual(b, 127)

    def test_map_temp_to_rgb_custom_colors(self):
        # Custom colors: Yellow [255, 255, 0], Cyan [0, 255, 255], Magenta [255, 0, 255]
        min_c = [255, 255, 0]
        mid_c = [0, 255, 255]
        max_c = [255, 0, 255]
        
        # At min threshold (<= 30.0) -> Yellow
        self.assertEqual(map_temp_to_rgb(25.0, 30.0, 60.0, 75.0, min_c, mid_c, max_c), (255, 255, 0))
        # At mid threshold (60.0) -> Cyan
        self.assertEqual(map_temp_to_rgb(60.0, 30.0, 60.0, 75.0, min_c, mid_c, max_c), (0, 255, 255))
        # At max threshold (>= 75.0) -> Magenta
        self.assertEqual(map_temp_to_rgb(80.0, 30.0, 60.0, 75.0, min_c, mid_c, max_c), (255, 0, 255))

    def test_map_temp_to_rgb_brightness(self):
        # Brightness at 50% should scale colors down by half
        min_c = [200, 100, 50]
        mid_c = [0, 0, 250]
        max_c = [100, 0, 0]
        
        # 50% brightness at min threshold
        self.assertEqual(map_temp_to_rgb(25.0, 30.0, 60.0, 75.0, min_c, mid_c, max_c, 50), (100, 50, 25))
        # 10% brightness at mid threshold
        self.assertEqual(map_temp_to_rgb(60.0, 30.0, 60.0, 75.0, min_c, mid_c, max_c, 10), (0, 0, 25))
        # 0% brightness (completely off)
        self.assertEqual(map_temp_to_rgb(80.0, 30.0, 60.0, 75.0, min_c, mid_c, max_c, 0), (0, 0, 0))

if __name__ == '__main__':
    unittest.main()
