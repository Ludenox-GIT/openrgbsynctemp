"""
Pure lighting and color calculations for OpenRGB Temp Sync.
No hardware, network, or UI dependencies.
"""

from typing import Tuple, List, Optional, Union

try:
    from PIL import Image, ImageDraw
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


def map_temp_to_rgb(
    temp: float,
    min_temp: float = 30.0,
    mid_temp: float = 60.0,
    max_temp: float = 75.0,
    min_color: Union[Tuple[int, int, int], List[int]] = (0, 255, 0),
    mid_color: Union[Tuple[int, int, int], List[int]] = (0, 0, 255),
    max_color: Union[Tuple[int, int, int], List[int]] = (255, 0, 0),
    brightness: int = 100
) -> Tuple[int, int, int]:
    """
    Map a temperature in Celsius to an RGB color tuple using a two-segment gradient.
    Applies brightness scaling (0-100) and clamps all outputs to [0, 255].
    """
    # Safety check for thresholds
    if min_temp >= mid_temp:
        mid_temp = min_temp + 1.0
    if mid_temp >= max_temp:
        max_temp = mid_temp + 1.0

    c_min = tuple(min_color[:3])
    c_mid = tuple(mid_color[:3])
    c_max = tuple(max_color[:3])

    if temp <= min_temp:
        r, g, b = c_min
    elif temp >= max_temp:
        r, g, b = c_max
    elif temp < mid_temp:
        ratio = (temp - min_temp) / (mid_temp - min_temp)
        r = int(c_min[0] + (c_mid[0] - c_min[0]) * ratio)
        g = int(c_min[1] + (c_mid[1] - c_min[1]) * ratio)
        b = int(c_min[2] + (c_mid[2] - c_min[2]) * ratio)
    else:
        ratio = (temp - mid_temp) / (max_temp - mid_temp)
        r = int(c_mid[0] + (c_max[0] - c_mid[0]) * ratio)
        g = int(c_mid[1] + (c_max[1] - c_mid[1]) * ratio)
        b = int(c_mid[2] + (c_max[2] - c_mid[2]) * ratio)

    # Apply brightness factor (0 to 100)
    factor = max(0.0, min(100.0, float(brightness))) / 100.0
    r = int(r * factor)
    g = int(g * factor)
    b = int(b * factor)

    return (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))


def apply_ema(smoothed_temp: Optional[float], raw_temp: float, alpha: float = 0.15) -> float:
    """
    Exponential Moving Average smoothing for temperature.
    alpha: 0.15 is default responsive smoothing factor.
    """
    if smoothed_temp is None:
        return float(raw_temp)
    alpha = max(0.01, min(1.0, float(alpha)))
    return (alpha * float(raw_temp)) + ((1.0 - alpha) * float(smoothed_temp))


def lerp_color(
    current_rgb: Tuple[float, float, float],
    target_rgb: Tuple[float, float, float],
    step_factor: float
) -> Tuple[float, float, float]:
    """
    Linear interpolation between current RGB float state and target RGB float state.
    """
    curr_r, curr_g, curr_b = current_rgb
    target_r, target_g, target_b = target_rgb
    factor = max(0.0, min(1.0, float(step_factor)))
    new_r = curr_r + (target_r - curr_r) * factor
    new_g = curr_g + (target_g - curr_g) * factor
    new_b = curr_b + (target_b - curr_b) * factor
    return (new_r, new_g, new_b)


def create_tray_image(color: Union[Tuple[int, int, int], List[int]] = (0, 255, 0)):
    """
    Create a dynamic tray icon image (neon circular logo with core atom).
    Returns a PIL.Image instance, or None if PIL is unavailable.
    """
    if not PIL_AVAILABLE:
        return None
    rgb = tuple(color[:3])
    image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    dc = ImageDraw.Draw(image)
    # Glowing outer ring
    dc.ellipse([4, 4, 60, 60], outline=rgb, width=4)
    # Central core
    dc.ellipse([20, 20, 44, 44], fill=rgb)
    return image