"""
UI Model and helpers for OpenRGB Temp Sync.
Handles device tree formatting, duplicate labeling, color conversions,
scope targeting, and Edit Zone transactional operations.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple
import colorsys
import re

from openrgb_temp_sync.openrgb_runtime import DeviceDescriptor, ZoneDescriptor
from openrgb_temp_sync.config import get_canonical_device_key, resolve_config_device_key


@dataclass
class ZoneTreeItem:
    key: str
    name: str
    index: int
    led_count: int
    leds_min: int
    leds_max: int
    resizable: bool
    descriptor: ZoneDescriptor


@dataclass
class DeviceTreeItem:
    key: str
    name: str
    display_label: str
    is_ambiguous: bool
    descriptor: DeviceDescriptor
    zones: List[ZoneTreeItem]


def format_device_label(
    desc: DeviceDescriptor,
    name_count: int,
    occurrence_index: int
) -> str:
    """Format distinguishable device label for duplicates and ambiguous hardware."""
    raw_name = desc.name or "Unknown Device"
    if name_count > 1:
        letter = chr(ord("A") + occurrence_index)
        if "DRAM" in raw_name.upper() or "RAM" in raw_name.upper():
            suffix = f" (RAM {letter})"
        else:
            suffix = f" (Device {letter})"
        label = f"{raw_name}{suffix}"
        if desc.ambiguous or desc.stable_key is None:
            label += f" [ambiguous - {desc.key.split('_')[-1]}]"
        return label
    return raw_name


def hex_to_rgb(hex_str: str) -> Optional[Tuple[int, int, int]]:
    """Parse #RRGGBB or RRGGBB string to (r, g, b) tuple; returns None if invalid."""
    if not isinstance(hex_str, str):
        return None
    cleaned = hex_str.strip()
    if cleaned.startswith("#"):
        cleaned = cleaned[1:]
    if not re.match(r"^[0-9a-fA-F]{6}$", cleaned):
        return None
    try:
        r = int(cleaned[0:2], 16)
        g = int(cleaned[2:4], 16)
        b = int(cleaned[4:6], 16)
        return r, g, b
    except ValueError:
        return None


def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    """Convert (r, g, b) tuple to #RRGGBB."""
    r = max(0, min(255, int(rgb[0])))
    g = max(0, min(255, int(rgb[1])))
    b = max(0, min(255, int(rgb[2])))
    return f"#{r:02x}{g:02x}{b:02x}"


def rgb_to_hsv(rgb: Tuple[int, int, int]) -> Tuple[int, int, int]:
    """Convert (r, g, b) in 0..255 to (h: 0..359, s: 0..100, v: 0..100)."""
    r = max(0, min(255, int(rgb[0]))) / 255.0
    g = max(0, min(255, int(rgb[1]))) / 255.0
    b = max(0, min(255, int(rgb[2]))) / 255.0
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    h_deg = int(round(h * 360.0)) % 360
    s_pct = int(round(s * 100.0))
    v_pct = int(round(v * 100.0))
    return h_deg, s_pct, v_pct


def hsv_to_rgb(h: int, s: int, v: int) -> Tuple[int, int, int]:
    """Convert (h: 0..360, s: 0..100, v: 0..100) to (r, g, b) in 0..255."""
    h_norm = (int(h) % 360) / 360.0
    s_norm = max(0.0, min(100.0, float(s))) / 100.0
    v_norm = max(0.0, min(100.0, float(v))) / 100.0
    r, g, b = colorsys.hsv_to_rgb(h_norm, s_norm, v_norm)
    return int(round(r * 255.0)), int(round(g * 255.0)), int(round(b * 255.0))


class ColorState:
    """Manages synchronized RGB, HSV, and Hex color representation with clamping."""

    def __init__(self, r: int = 255, g: int = 0, b: int = 0):
        self._r = max(0, min(255, int(r)))
        self._g = max(0, min(255, int(g)))
        self._b = max(0, min(255, int(b)))

    def set_rgb(self, r: int, g: int, b: int) -> None:
        self._r = max(0, min(255, int(r)))
        self._g = max(0, min(255, int(g)))
        self._b = max(0, min(255, int(b)))

    def set_hex(self, hex_str: str) -> bool:
        parsed = hex_to_rgb(hex_str)
        if parsed is None:
            return False
        self._r, self._g, self._b = parsed
        return True

    def set_hsv(self, h: int, s: int, v: int) -> None:
        self._r, self._g, self._b = hsv_to_rgb(h, s, v)

    def get_rgb(self) -> Tuple[int, int, int]:
        return self._r, self._g, self._b

    def get_hex(self) -> str:
        return rgb_to_hex((self._r, self._g, self._b))

    def get_hsv(self) -> Tuple[int, int, int]:
        return rgb_to_hsv((self._r, self._g, self._b))


def build_target_colors(
    total_leds: int,
    current_colors: Optional[Sequence[Any]],
    selected_indices: Optional[Sequence[int]],
    new_color: Tuple[int, int, int]
) -> List[Any]:
    """
    Build device-wide color array with only selected_indices modified.
    Preserves all unselected LED colors from current_colors (or black if None).
    """
    if total_leds <= 0:
        return [new_color]

    if current_colors and len(current_colors) == total_leds:
        base = [c for c in current_colors]
    else:
        base = [(0, 0, 0)] * total_leds

    if selected_indices is None or len(selected_indices) == 0:
        target_indices = range(total_leds)
    else:
        target_indices = [i for i in selected_indices if 0 <= i < total_leds]

    for idx in target_indices:
        base[idx] = new_color

    return base


class UIModel:
    """Headless state and transformation model for settings GUI."""

    @staticmethod
    def build_device_tree_items(descriptors: List[DeviceDescriptor]) -> List[DeviceTreeItem]:
        """Convert descriptors into tree items with distinct labels and visible ambiguity."""
        if not descriptors:
            return []

        name_counts: Dict[str, int] = {}
        for desc in descriptors:
            raw_name = desc.name or "Unknown Device"
            name_counts[raw_name] = name_counts.get(raw_name, 0) + 1

        name_occurrences: Dict[str, int] = {}
        items: List[DeviceTreeItem] = []

        for desc in descriptors:
            raw_name = desc.name or "Unknown Device"
            occ = name_occurrences.get(raw_name, 0)
            name_occurrences[raw_name] = occ + 1

            display_label = format_device_label(desc, name_counts[raw_name], occ)

            zone_items = [
                ZoneTreeItem(
                    key=z.key,
                    name=z.name,
                    index=z.index,
                    led_count=z.led_count,
                    leds_min=z.leds_min,
                    leds_max=z.leds_max,
                    resizable=z.resizable,
                    descriptor=z
                )
                for z in desc.zones
            ]

            items.append(DeviceTreeItem(
                key=desc.key,
                name=desc.name,
                display_label=display_label,
                is_ambiguous=desc.ambiguous,
                descriptor=desc,
                zones=zone_items
            ))

        return items

    @staticmethod
    def is_zone_resizable(zone: ZoneDescriptor) -> bool:
        """Check if zone supports independent count resizing."""
        return bool(zone.resizable and zone.leds_min < zone.leds_max)



    @staticmethod
    def get_mode_capabilities(mode: Any) -> Dict[str, Any]:
        """Summarize capability gates and human-readable disable reasons for UI controls."""
        sup_speed = getattr(mode, "supports_speed", False)
        sup_bright = getattr(mode, "supports_brightness", False)
        sup_dir = getattr(mode, "supports_direction", False)
        sup_col = getattr(mode, "supports_mode_specific_color", False) or getattr(mode, "supports_per_led", False)
        sup_save = getattr(mode, "supports_save", False)
        dirs = list(getattr(mode, "directions_supported", ()))

        return {
            "supports_speed": sup_speed,
            "supports_brightness": sup_bright,
            "supports_direction": sup_dir,
            "supports_color": sup_col,
            "supports_save": sup_save,
            "speed_range": (getattr(mode, "speed_min", None), getattr(mode, "speed_max", None)),
            "brightness_range": (getattr(mode, "brightness_min", None), getattr(mode, "brightness_max", None)),
            "directions": dirs,
            "reasons": {
                "speed": None if sup_speed else "Speed unsupported by this mode",
                "brightness": None if sup_bright else "Brightness unsupported by this mode",
                "direction": None if sup_dir else "Direction unsupported by this mode",
                "color": None if sup_col else "Fixed or random color mode",
                "save": None if sup_save else "Save to device is not supported for this mode"
            }
        }

    @staticmethod
    def format_device_owner_label(owner: str, mode_name: Optional[str] = None) -> str:
        """Format human-readable description of current device control ownership."""
        if owner == "thermal_direct":
            return "Temperature Sync (Direct)"
        elif owner == "manual_direct":
            return "Manual Color (Direct)"
        elif owner == "hardware_mode":
            return f"Hardware Effect ({mode_name or "Active"})"
        elif owner == "resetting":
            return "Restored Pre-Sync Snapshot (Held)"
        elif owner == "unmanaged":
            return "Unmanaged"
        return str(owner)


class EditZoneTransaction:
    """Transactional wrapper for zone resize: validate -> resize -> readback -> persist."""

    def validate_count(self, count_str: str, min_count: int, max_count: int) -> Tuple[bool, int, str]:
        try:
            val = int(count_str.strip())
        except (ValueError, TypeError, AttributeError):
            return False, 0, "Enter a whole number."
        if val < min_count or val > max_count:
            return False, val, f"Count must be between {min_count} and {max_count}."
        return True, val, ""

    def cancel(self) -> None:
        """Cancel stages without writing to hardware or configuration."""
        pass

    def apply(
        self,
        supervisor: Any,
        controller: Any,
        config_manager: Any,
        target_key: str,
        device_name: str,
        zone_index: int,
        zone_name: str,
        new_count: int,
        min_count: int,
        max_count: int
    ) -> Tuple[bool, str]:
        """
        Execute zone resize transaction:
        1. Validate integer and bounds.
        2. Capture current owner and set owner to manual_direct so background thermal frames pause.
        3. Invoke supervisor.resize_zone.
        4. Re-read fresh descriptor from supervisor.
        5. Verify exact readback equality with strict identity matching.
        6. Persist to configuration only after readback matches.
        7. On any failure, restore captured owner to prevent permanently stopping thermal ownership.
        """
        if new_count < min_count or new_count > max_count:
            return False, f"Count must be between {min_count} and {max_count}."

        prev_owner: Optional[str] = None
        owner_target = target_key or device_name
        if hasattr(controller, "get_device_owner") and callable(getattr(controller, "get_device_owner")):
            try:
                prev_owner = controller.get_device_owner(owner_target)
            except Exception:
                prev_owner = None

        if hasattr(controller, "set_device_owner") and callable(getattr(controller, "set_device_owner")):
            controller.set_device_owner(owner_target, "manual_direct")

        def _fail(msg: str) -> Tuple[bool, str]:
            if prev_owner is not None and hasattr(controller, "set_device_owner") and callable(getattr(controller, "set_device_owner")):
                try:
                    controller.set_device_owner(owner_target, prev_owner)
                except Exception:
                    pass
            return False, msg

        resize_fn = getattr(supervisor, "resize_zone", None)
        if not callable(resize_fn):
            return _fail("Supervisor does not support zone resizing.")

        try:
            if not resize_fn(target_key, zone_index, new_count):
                return _fail("OpenRGB rejected this LED count for the selected zone.")
        except Exception as ex:
            return _fail(f"OpenRGB error during zone resize: {ex}")

        # Re-read fresh inventory
        try:
            if hasattr(supervisor, "refresh_inventory"):
                res = supervisor.refresh_inventory()
                if isinstance(res, list) and res:
                    fresh_descriptors = res
                elif hasattr(supervisor, "get_descriptors"):
                    fresh_descriptors = supervisor.get_descriptors()
                else:
                    fresh_descriptors = []
            elif hasattr(supervisor, "get_descriptors"):
                fresh_descriptors = supervisor.get_descriptors()
            else:
                fresh_descriptors = []
        except Exception as ex:
            return _fail(f"Failed to refresh inventory: {ex}")

        # Find updated device with strict identity matching
        matching_dev = None
        if target_key:
            exact_matches = [
                d for d in fresh_descriptors
                if getattr(d, "key", None) == target_key or (
                    getattr(d, "stable_key", None) is not None and getattr(d, "stable_key", None) == target_key
                )
            ]
            if len(exact_matches) == 1:
                candidate = exact_matches[0]
                if getattr(candidate, "ambiguous", False):
                    return _fail("Zone readback failed: device identity is ambiguous.")
                matching_dev = candidate
            elif len(exact_matches) > 1:
                return _fail("Zone readback failed: ambiguous device key match.")
            else:
                return _fail("Zone readback failed: target device descriptor missing.")
        else:
            name_matches = [d for d in fresh_descriptors if getattr(d, "name", None) == device_name]
            if len(name_matches) == 1:
                candidate = name_matches[0]
                if getattr(candidate, "ambiguous", False):
                    return _fail("Zone readback failed: device identity is ambiguous.")
                matching_dev = candidate
            elif len(name_matches) > 1:
                return _fail("Zone readback failed: duplicate devices found with name, target key required.")
            else:
                return _fail("Zone readback failed: device descriptor missing.")

        if not matching_dev:
            return _fail("Zone readback failed: device descriptor missing.")

        # Find updated zone by index or name
        readback_zone = None
        for z in getattr(matching_dev, "zones", []) or []:
            if getattr(z, "index", None) == zone_index or getattr(z, "name", None) == zone_name:
                readback_zone = z
                break
        if readback_zone is None and hasattr(matching_dev, "zones") and matching_dev.zones and zone_index < len(matching_dev.zones):
            readback_zone = matching_dev.zones[zone_index]

        if not readback_zone:
            return _fail("Zone readback failed: zone descriptor missing.")

        if getattr(readback_zone, "led_count", None) != new_count:
            return _fail(
                f"Zone resize readback mismatch: expected {new_count} LEDs, "
                f"but OpenRGB reported {readback_zone.led_count} LEDs."
            )

        # Persist to config only after exact readback verified
        try:
            import copy
            cfg = config_manager.get_config()
            persist_key = get_canonical_device_key(matching_dev, fresh_descriptors)
            devices_cfg = cfg.setdefault("devices", {})
            if persist_key not in devices_cfg:
                name = getattr(matching_dev, "name", device_name)
                name_matches = [
                    d for d in fresh_descriptors
                    if getattr(d, "name", None) == name or getattr(d, "display_name", None) == name
                ]
                if len(name_matches) == 1 and name in devices_cfg:
                    devices_cfg[persist_key] = copy.deepcopy(devices_cfg.pop(name))
                else:
                    devices_cfg[persist_key] = {
                        "default_source": "cpu",
                        "led_brightness": {},
                        "temp_source": {},
                        "zone_led_counts": {}
                    }
            dev_cfg = devices_cfg[persist_key]
            dev_cfg.setdefault("zone_led_counts", {})[zone_name] = new_count
            config_manager.save_config(cfg)
        except Exception as ex:
            return _fail(f"Failed to persist zone count to config: {ex}")

        return True, f"Successfully resized {zone_name} to {new_count} LEDs."
