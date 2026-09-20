"""
Runtime coordinator and lighting loop controller.
Orchestrates OpenRGB engine, sensor supervisor, color interpolation,
screensaver auto-pause, lights-off toggle, and status snapshots.
"""

import copy
import datetime
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from openrgb_temp_sync.config import ConfigManager, get_canonical_device_key, resolve_config_device_key
from openrgb_temp_sync.lighting import (
    apply_ema,
    create_tray_image,
    lerp_color,
    map_temp_to_rgb
)
from openrgb_temp_sync.openrgb_runtime import (
    EngineState,
    OpenRGBSupervisor
)
from openrgb_temp_sync.sensor_runtime import (
    SensorStatus,
    SensorSupervisor
)
from openrgb_temp_sync.windows_runtime import (
    inspect_port_6742,
    is_screensaver_active
)

logger = logging.getLogger("Controller")


class ControllerState:
    IDLE = "IDLE"
    STARTING = "STARTING"
    RUNNING_OWNED = "RUNNING_OWNED"
    RUNNING_EXTERNAL = "RUNNING_EXTERNAL"
    PAUSED = "PAUSED"
    LIGHTS_OFF = "LIGHTS_OFF"
    DEGRADED_ENGINE = "DEGRADED_ENGINE"
    DEGRADED_SENSOR = "DEGRADED_SENSOR"
    CONFLICT = "CONFLICT"
    STOPPING = "STOPPING"


class SyncController:
    """Coordinates lighting synchronization, sensors, engine state, and UI snapshots."""

    def __init__(
        self,
        config_manager: Optional[ConfigManager] = None,
        openrgb_supervisor: Optional[OpenRGBSupervisor] = None,
        sensor_supervisor: Optional[SensorSupervisor] = None
    ):
        self.config_manager = config_manager or ConfigManager()
        self.openrgb_supervisor = openrgb_supervisor or OpenRGBSupervisor()
        self.sensor_supervisor = sensor_supervisor or SensorSupervisor()

        self.state = ControllerState.IDLE
        self.status_text = "Idle"
        self.running = False
        self.lights_off = False
        self.auto_paused = False

        self._stop_event = threading.Event()
        self._loop_thread: Optional[threading.Thread] = None
        self._icon_update_cb: Optional[Callable[[Any], None]] = None

        self.smoothed_cpu_temp: Optional[float] = None
        self.smoothed_gpu_temp: Optional[float] = None
        self.current_led_colors: Dict[str, List[float]] = {}
        self._manual_reset_devices: set[str] = set()
        self._device_owners: Dict[str, str] = {}

    def resolve_target_key(self, target: str) -> Optional[str]:
        """
        Resolve canonical device key from descriptor key/stable_key or unique legacy name.
        Returns canonical key if unique/exact, None if ambiguous or unknown.
        """
        if not target or not isinstance(target, str):
            return None

        sup = self.openrgb_supervisor
        descriptors = getattr(sup, "get_descriptors", lambda: [])()
        if descriptors:
            # 1. Exact match on descriptor key or stable_key (canonical identity)
            for desc in descriptors:
                if desc.key == target or (desc.stable_key and desc.stable_key == target):
                    return desc.stable_key or desc.key

            # 2. Match on distinct display label if formatted (e.g. from UIModel)
            try:
                from openrgb_temp_sync.ui_model import UIModel
                tree_items = UIModel.build_device_tree_items(descriptors)
                for item in tree_items:
                    if item.display_label == target:
                        return getattr(item.descriptor, "stable_key", None) or item.key
            except Exception:
                pass

            # 3. Compatibility fallback for unique legacy display name
            name_matches = [
                desc for desc in descriptors
                if desc.name == target or getattr(desc, "display_name", "") == target
            ]
            if len(name_matches) == 1:
                single_desc = name_matches[0]
                return single_desc.stable_key or single_desc.key
            elif len(name_matches) > 1:
                logger.warning("Target '%s' is ambiguous (matches %d devices)", target, len(name_matches))
                return None

            if target in self._device_owners or target in self._manual_reset_devices:
                return target

            return None

        devices = getattr(sup, "get_devices", lambda: [])()
        if devices:
            name_matches = [d for d in devices if getattr(d, "name", "") == target]
            if len(name_matches) == 1:
                return getattr(name_matches[0], "name", target)
            elif len(name_matches) > 1:
                logger.warning("Target '%s' is ambiguous across devices", target)
                return None

            if target in self._device_owners or target in self._manual_reset_devices:
                return target

            return None

        return target

    def is_device_reset(self, device_target: str) -> bool:
        """Return whether a device is being held at its restored/original state."""
        resolved = self.resolve_target_key(device_target)
        if resolved is None:
            return False
        return resolved in self._manual_reset_devices

    def get_device_owner(self, device_target: str) -> str:
        """Return owner state: unmanaged, resetting, manual_direct, hardware_mode, thermal_direct."""
        resolved = self.resolve_target_key(device_target)
        if resolved is None:
            sup = self.openrgb_supervisor
            descriptors = getattr(sup, "get_descriptors", lambda: [])()
            if descriptors:
                matches = [d for d in descriptors if d.name == device_target or getattr(d, "display_name", "") == device_target]
                if len(matches) > 1:
                    return "ambiguous"
            devices = getattr(sup, "get_devices", lambda: [])()
            if devices:
                matches = [d for d in devices if getattr(d, "name", "") == device_target]
                if len(matches) > 1:
                    return "ambiguous"
            return "unknown"
        if resolved in self._manual_reset_devices:
            if self._device_owners.get(resolved) != "unmanaged":
                return "resetting"
        return self._device_owners.get(resolved, "thermal_direct")

    def set_device_owner(self, device_target: str, owner: str) -> bool:
        """Set owner state for device. Rejects ambiguous targets."""
        resolved = self.resolve_target_key(device_target)
        if resolved is None:
            logger.warning("Cannot set owner: target '%s' is ambiguous or unknown", device_target)
            return False
        self._device_owners[resolved] = owner
        return True

    def _inventory_target_keys(self) -> List[str]:
        """Return stable, non-ambiguous keys for the current inventory."""
        descriptors = getattr(self.openrgb_supervisor, "get_descriptors", lambda: [])()
        if descriptors:
            return [
                d.stable_key or d.key
                for d in descriptors
                if not getattr(d, "ambiguous", False) and (d.stable_key or d.key)
            ]
        return [
            getattr(device, "name", "")
            for device in getattr(self.openrgb_supervisor, "get_devices", lambda: [])()
            if getattr(device, "name", "")
        ]

    def remember_last_applied(
        self,
        mode: str,
        target_key: Optional[str] = None,
        **state: Any
    ) -> bool:
        """Persist the last successfully applied app/device mode."""
        allowed = {"temperature", "manual", "hardware_effect", "vendor_default"}
        if mode not in allowed:
            return False

        cfg = self.config_manager.get_config()
        last = cfg.get("last_applied", {})
        if not isinstance(last, dict):
            last = {}
        entries = last.get("devices", {})
        if not isinstance(entries, dict):
            entries = {}
        else:
            entries = copy.deepcopy(entries)

        # Seed a complete inventory the first time a per-device action is saved,
        # so changing one device does not forget the others on the next boot.
        if target_key is not None and not entries:
            entries = {key: {"mode": "temperature"} for key in self._inventory_target_keys()}

        if target_key is None:
            if not entries:
                entries = {key: {"mode": "temperature"} for key in self._inventory_target_keys()}
        else:
            resolved = self.resolve_target_key(target_key) or target_key
            entry = {"mode": mode}
            entry.update(copy.deepcopy(state))
            entries[resolved] = entry

        modes = {
            str(entry.get("mode"))
            for entry in entries.values()
            if isinstance(entry, dict) and entry.get("mode")
        }
        last["mode"] = next(iter(modes)) if len(modes) == 1 else "mixed"
        last["devices"] = entries
        last["saved_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cfg["last_applied"] = last
        return self.config_manager.save_config(cfg)

    @staticmethod
    def _restore_rgb_colors(raw_colors: Any) -> List[Any]:
        if not isinstance(raw_colors, list):
            return []
        try:
            from openrgb.utils import RGBColor
        except ImportError:
            class RGBColor:
                def __init__(self, red, green, blue):
                    self.red, self.green, self.blue = int(red), int(green), int(blue)
        colors = []
        for raw in raw_colors:
            if isinstance(raw, (list, tuple)) and len(raw) >= 3:
                try:
                    colors.append(RGBColor(int(raw[0]), int(raw[1]), int(raw[2])))
                except (TypeError, ValueError):
                    continue
        return colors

    def _restore_last_applied_state(self) -> None:
        """Restore the persisted per-device state after OpenRGB inventory is ready."""
        cfg = self.config_manager.get_config()
        last = cfg.get("last_applied", {})
        if not isinstance(last, dict):
            return
        entries = last.get("devices", {})
        if not isinstance(entries, dict) or not entries:
            if last.get("mode", "temperature") == "temperature":
                entries = {key: {"mode": "temperature"} for key in self._inventory_target_keys()}
            else:
                return

        sup = self.openrgb_supervisor
        for target_key, entry in entries.items():
            if not isinstance(entry, dict):
                continue
            resolved = self.resolve_target_key(target_key)
            if resolved is None:
                logger.warning("Cannot restore last state: target '%s' is missing or ambiguous", target_key)
                continue
            mode = entry.get("mode", last.get("mode", "temperature"))

            if mode == "vendor_default":
                self._manual_reset_devices.add(resolved)
                self._device_owners[resolved] = "unmanaged"
                continue

            self._manual_reset_devices.discard(resolved)
            if mode == "temperature":
                self._device_owners[resolved] = "thermal_direct"
                set_direct = getattr(sup, "set_device_mode", None)
                if callable(set_direct) and not set_direct(resolved, "Direct"):
                    logger.warning("Could not restore Direct mode for %s", resolved)
                continue

            if mode == "manual":
                self._device_owners[resolved] = "manual_direct"
                set_direct = getattr(sup, "set_device_mode", None)
                if callable(set_direct) and not set_direct(resolved, "Direct"):
                    logger.warning("Could not restore Manual Direct mode for %s", resolved)
                    continue
                colors = self._restore_rgb_colors(entry.get("colors"))
                if colors and hasattr(sup, "set_colors"):
                    result = sup.set_colors(resolved, colors, fast=True)
                    if not getattr(result, "ok", False):
                        logger.warning("Could not restore manual colors for %s", resolved)
                continue

            if mode == "hardware_effect":
                mode_name = entry.get("mode_name")
                if not mode_name or not hasattr(sup, "set_mode"):
                    logger.warning("Last hardware effect for %s has no restorable mode", resolved)
                    continue
                params = {
                    name: entry[name]
                    for name in ("speed", "brightness", "direction")
                    if entry.get(name) is not None
                }
                colors = self._restore_rgb_colors(entry.get("colors"))
                if colors:
                    params["colors"] = colors
                result = sup.set_mode(resolved, mode_name, **params, save=False)
                if getattr(result, "ok", False):
                    self._device_owners[resolved] = "hardware_mode"
                else:
                    logger.warning("Could not restore hardware effect for %s", resolved)

    def can_apply_thermal_frame(self, device_target: str) -> bool:
        """Return True if device accepts thermal updates."""
        resolved = self.resolve_target_key(device_target)
        if resolved is None:
            return False
        if resolved in self._manual_reset_devices:
            return False
        owner = self.get_device_owner(resolved)
        return owner == "thermal_direct"

    def _clear_device_color_cache(self, device_target: str):
        resolved = self.resolve_target_key(device_target)
        keys_to_clear = set()
        if resolved:
            keys_to_clear.add(resolved)
        if device_target and device_target != resolved:
            sup = self.openrgb_supervisor
            descriptors = getattr(sup, "get_descriptors", lambda: [])()
            ambiguous = False
            if descriptors:
                ambiguous = len([d for d in descriptors if d.name == device_target]) > 1
            if not ambiguous:
                keys_to_clear.add(device_target)

        if not keys_to_clear:
            return

        prefixes = tuple(f"{k}:" for k in keys_to_clear)
        self.current_led_colors = {
            key: value for key, value in self.current_led_colors.items()
            if not key.startswith(prefixes)
        }

    def reset_device_to_original(self, device_target: str) -> bool:
        """Restore pre-sync snapshot and transition owner to resetting."""
        restore = getattr(self.openrgb_supervisor, "restore_device", None)
        if not callable(restore):
            return False
        resolved = self.resolve_target_key(device_target)
        if resolved is None:
            logger.warning("Cannot reset device: target '%s' is ambiguous or unknown", device_target)
            return False
        self._manual_reset_devices.add(resolved)
        self.set_device_owner(resolved, "resetting")
        restored = bool(restore(resolved))
        if not restored:
            # Runtime snapshots can be unavailable after a reconnect or a
            # stale SDK session.  Fall back to the user-confirmed persistent
            # vendor baseline, which is a snapshot restore—not an OEM reset.
            baseline_entry = self.config_manager.get_vendor_baseline("vendor_default")
            persisted_devices = baseline_entry.get("devices", {}) if isinstance(baseline_entry, dict) else {}
            persisted = None
            if isinstance(persisted_devices, dict):
                persisted = persisted_devices.get(resolved) or persisted_devices.get(device_target)
                if persisted is None:
                    matches = [
                        value for value in persisted_devices.values()
                        if isinstance(value, dict)
                        and (
                            value.get("canonical_key") == resolved
                            or value.get("stable_key") == resolved
                            or value.get("name") == device_target
                        )
                    ]
                    if len(matches) == 1:
                        persisted = matches[0]

            restore_persisted = getattr(self.openrgb_supervisor, "restore_device_from_baseline", None)
            if persisted is not None and callable(restore_persisted):
                restored = bool(restore_persisted(resolved, persisted))

        if not restored:
            self._manual_reset_devices.discard(resolved)
            self.set_device_owner(resolved, "thermal_direct")
            return False
        self._clear_device_color_cache(resolved)
        return True

    def resume_device(self, device_target: str) -> bool:
        """Resume thermal sync for a device, negotiating Direct mode."""
        resolved = self.resolve_target_key(device_target)
        if resolved is None:
            logger.warning("Cannot resume device: target '%s' is ambiguous or unknown", device_target)
            return False
        was_reset = resolved in self._manual_reset_devices
        self._manual_reset_devices.discard(resolved)
        self.set_device_owner(resolved, "thermal_direct")
        self._clear_device_color_cache(resolved)

        sup = self.openrgb_supervisor
        if hasattr(sup, "set_device_mode"):
            sup.set_device_mode(resolved, "Direct")
        elif hasattr(sup, "configure_devices_direct_mode"):
            if hasattr(sup, "_find_device"):
                dev = sup._find_device(resolved)
                if dev is not None:
                    sup.configure_devices_direct_mode([dev])

        if self.smoothed_cpu_temp is not None or self.smoothed_gpu_temp is not None:
            try:
                self._dispatch_thermal_frame()
            except Exception:
                pass

        return was_reset

    def set_device_hardware_mode(
        self,
        target_key: str,
        mode_name: str,
        speed: Optional[int] = None,
        brightness: Optional[int] = None,
        direction: Optional[Any] = None,
        colors: Optional[List[Any]] = None,
        save: bool = False
    ) -> Any:
        """Apply a hardware lighting effect through supervisor and transition owner."""
        sup = self.openrgb_supervisor
        if not hasattr(sup, "set_mode"):
            return None
        resolved = self.resolve_target_key(target_key) or target_key
        res = sup.set_mode(
            resolved,
            mode_name,
            speed=speed,
            brightness=brightness,
            direction=direction,
            colors=colors,
            save=save
        )
        if getattr(res, "ok", False):
            self.set_device_owner(resolved, "hardware_mode")
            self._clear_device_color_cache(resolved)
        return res

    def resize_zone(self, device_target: str, zone_index: int, size: int) -> bool:
        """Resize an addressable zone through OpenRGB's SDK and resume that device."""
        resize = getattr(self.openrgb_supervisor, "resize_zone", None)
        resolved = self.resolve_target_key(device_target)
        if resolved is None:
            logger.warning("Cannot resize zone: target '%s' is ambiguous or unknown", device_target)
            return False
        if not callable(resize) or not resize(resolved, zone_index, size):
            return False
        self._manual_reset_devices.discard(resolved)
        self._clear_device_color_cache(resolved)
        return True

    def _apply_saved_zone_sizes(self):
        """Apply persisted addressable-zone counts once devices are connected."""
        cfg = self.config_manager.get_config()
        device_configs = cfg.get("devices", {})
        unmatched = cfg.get("unmatched_legacy_profiles", {})
        sup = self.openrgb_supervisor
        descriptors = getattr(sup, "get_descriptors", lambda: [])()
        if descriptors:
            name_counts: Dict[str, int] = {}
            for d in descriptors:
                d_name = getattr(d, "name", "")
                if d_name:
                    name_counts[d_name] = name_counts.get(d_name, 0) + 1
                disp_name = getattr(d, "display_name", "")
                if disp_name and disp_name != d_name:
                    name_counts[disp_name] = name_counts.get(disp_name, 0) + 1

            for desc in descriptors:
                if getattr(desc, "ambiguous", False):
                    continue
                canonical_key = get_canonical_device_key(desc, descriptors)
                target_key = desc.stable_key or desc.key
                dev_cfg = device_configs.get(canonical_key)
                if not dev_cfg and canonical_key != target_key:
                    dev_cfg = device_configs.get(target_key)
                if not dev_cfg:
                    name = getattr(desc, "name", "")
                    disp_name = getattr(desc, "display_name", "")
                    if name and name_counts.get(name, 0) == 1:
                        dev_cfg = device_configs.get(name) or unmatched.get(name)
                    elif disp_name and name_counts.get(disp_name, 0) == 1:
                        dev_cfg = device_configs.get(disp_name) or unmatched.get(disp_name)
                if not isinstance(dev_cfg, dict):
                    continue
                zone_counts = dev_cfg.get("zone_led_counts", {})
                if not isinstance(zone_counts, dict):
                    continue
                for zone in getattr(desc, "zones", []) or []:
                    zone_name = getattr(zone, "name", "")
                    zone_index = getattr(zone, "index", 0)
                    if zone_name not in zone_counts:
                        continue
                    try:
                        self.resize_zone(target_key, zone_index, int(zone_counts[zone_name]))
                    except (TypeError, ValueError):
                        logger.warning("Ignoring invalid saved LED count for %s / %s", target_key, zone_name)
        else:
            devices = sup.get_devices() if hasattr(sup, "get_devices") else []
            name_counts = {}
            for d in devices:
                d_name = getattr(d, "name", "")
                if d_name:
                    name_counts[d_name] = name_counts.get(d_name, 0) + 1
            for device in devices:
                device_name = getattr(device, "name", "")
                if not device_name or name_counts.get(device_name, 0) != 1:
                    continue
                zone_counts = device_configs.get(device_name, {}).get("zone_led_counts", {})
                if not isinstance(zone_counts, dict):
                    continue
                zones = getattr(device, "zones", []) or []
                for zone_index, zone in enumerate(zones):
                    zone_name = getattr(zone, "name", "")
                    if zone_name not in zone_counts:
                        continue
                    try:
                        self.resize_zone(device_name, zone_index, int(zone_counts[zone_name]))
                    except (TypeError, ValueError):
                        logger.warning("Ignoring invalid saved LED count for %s / %s", device_name, zone_name)

    def get_status_snapshot(self) -> Dict[str, Any]:
        """Return a thread-safe immutable snapshot of runtime state for the UI and tray."""
        devices = self.openrgb_supervisor.get_devices()
        reading = self.sensor_supervisor.get_latest_reading()

        engine_label = "None"
        if self.openrgb_supervisor.state == EngineState.RUNNING_OWNED:
            engine_label = "Bundled OpenRGB"
        elif self.openrgb_supervisor.state == EngineState.RUNNING_EXTERNAL:
            engine_label = "External OpenRGB"
        elif self.openrgb_supervisor.state == EngineState.DEGRADED:
            engine_label = "OpenRGB"

        status_text = self.status_text
        if self.openrgb_supervisor.state == EngineState.DEGRADED:
            # A dropped SDK socket must not leave the UI claiming Running while
            # the lighting loop has stopped accepting writes.
            status_text = self.openrgb_supervisor.status_message or "OpenRGB engine degraded"

        return {
            "state": self.state,
            "status_text": status_text,
            "is_running": self.running,
            "is_lights_off": self.lights_off,
            "is_paused": self.auto_paused,
            "engine_label": engine_label,
            "engine_state": self.openrgb_supervisor.state,
            "sensor_status": self.sensor_supervisor.get_status(),
            "cpu_temp": reading.cpu_temp if reading else self.smoothed_cpu_temp,
            "gpu_temp": reading.gpu_temp if reading else self.smoothed_gpu_temp,
            "cpu_source": reading.cpu_source if reading else "None",
            "gpu_source": reading.gpu_source if reading else "None",
            "device_count": len(devices),
            "devices": [getattr(d, "name", "Device") for d in devices]
        }

    def export_diagnostics(self) -> Dict[str, Any]:
        """Generate redacted diagnostic summary omitting sensitive user files or full config."""
        port_status, port_desc, port_pid = inspect_port_6742()
        snapshot = self.get_status_snapshot()

        return {
            "app_version": "1.0.0",
            "controller_state": self.state,
            "status_text": self.status_text,
            "engine_status": self.openrgb_supervisor.status_message,
            "engine_owned": self.openrgb_supervisor.is_owned(),
            "sensor_status": self.sensor_supervisor.get_status(),
            "port_6742": {
                "status": port_status,
                "description": port_desc,
                "pid": port_pid
            },
            "cpu_temp": snapshot["cpu_temp"],
            "gpu_temp": snapshot["gpu_temp"],
            "cpu_source": snapshot["cpu_source"],
            "gpu_source": snapshot["gpu_source"],
            "device_count": snapshot["device_count"],
            "device_names": snapshot["devices"],
            "sensor_stderr_recent": self.sensor_supervisor.get_recent_stderr()
        }

    def set_lights_off(self, off: bool):
        """Toggle lights off black state."""
        self.lights_off = off
        if off:
            self.state = ControllerState.LIGHTS_OFF
            self.status_text = "Lights Off"
            self._send_black_to_all()
        else:
            self.state = ControllerState.RUNNING_OWNED if self.running else ControllerState.IDLE
            self.status_text = "Running" if self.running else "Stopped"

    def _send_black_to_all(self):
        """Send RGB(0,0,0) once to all controllable devices to conserve power."""
        sup = self.openrgb_supervisor
        descriptors = getattr(sup, "get_descriptors", lambda: [])()
        targets = []
        if descriptors:
            for desc in descriptors:
                if desc.ambiguous:
                    continue
                target_key = desc.stable_key or desc.key
                targets.append((target_key, desc.name))
        else:
            devices = sup.get_devices() if hasattr(sup, "get_devices") else []
            for dev in devices:
                dev_name = getattr(dev, "name", "")
                targets.append((dev_name, dev_name))

        try:
            from openrgb.utils import RGBColor
            off_color = RGBColor(0, 0, 0)
        except ImportError:
            class DummyColor:
                def __init__(self, r, g, b):
                    self.red = r
                    self.green = g
                    self.blue = b
            off_color = DummyColor(0, 0, 0)

        for target_key, dev_name in targets:
            owner = self.get_device_owner(target_key)
            if owner != "thermal_direct":
                continue
            if not self.can_apply_thermal_frame(target_key):
                continue
            if hasattr(sup, "set_colors"):
                sup.set_colors(target_key, [off_color], fast=True)
            elif hasattr(sup, "_find_device"):
                dev = sup._find_device(target_key)
                if dev is not None and hasattr(dev, "set_color"):
                    try:
                        dev.set_color(off_color)
                    except Exception:
                        pass

    def _sensor_allows_updates(self) -> bool:
        """Gate LED writes on a healthy, non-stale sensor stream."""
        sensor_status = self.sensor_supervisor.get_status()

        if self.lights_off:
            return False

        if sensor_status in (SensorStatus.OFFLINE, SensorStatus.STALE, SensorStatus.FATAL):
            self.state = ControllerState.DEGRADED_SENSOR
            self.status_text = f"Sensor unavailable ({sensor_status})"
            maybe_restart = getattr(self.sensor_supervisor, "maybe_restart", None)
            if callable(maybe_restart):
                try:
                    maybe_restart()
                except Exception:
                    logger.debug("Sensor helper restart attempt failed", exc_info=True)
            return False

        if sensor_status == SensorStatus.STARTING:
            self.status_text = "Starting sensors..."
            return False

        if sensor_status == SensorStatus.OK and self.state == ControllerState.DEGRADED_SENSOR:
            self.state = (
                ControllerState.RUNNING_EXTERNAL
                if self.openrgb_supervisor.state == EngineState.RUNNING_EXTERNAL
                else ControllerState.RUNNING_OWNED
            )
            self.status_text = "Running (External OpenRGB)" if self.state == ControllerState.RUNNING_EXTERNAL else "Running"

        return sensor_status == SensorStatus.OK

    def start(self, icon_update_cb: Optional[Callable[[Any], None]] = None):
        """Start OpenRGB engine, sensor bridge, and high-frequency lighting loop."""
        if self.running:
            return

        self.running = True
        self.lights_off = False
        self.auto_paused = False
        self._stop_event.clear()
        self._icon_update_cb = icon_update_cb

        self.state = ControllerState.STARTING
        self.status_text = "Starting..."

        # 1. Start OpenRGB engine
        engine_state, engine_msg = self.openrgb_supervisor.start()
        if engine_state == EngineState.CONFLICT:
            self.state = ControllerState.CONFLICT
            self.status_text = engine_msg
            self.running = False
            return
        elif engine_state in (EngineState.DEGRADED, EngineState.STOPPED):
            self.state = ControllerState.DEGRADED_ENGINE
            self.status_text = engine_msg or "Engine degraded or stopped"
            self.running = False
            return
        elif engine_state == EngineState.RUNNING_EXTERNAL:
            self.state = ControllerState.RUNNING_EXTERNAL
            self.status_text = "Running (External OpenRGB)"
        elif engine_state == EngineState.RUNNING_OWNED:
            self.state = ControllerState.RUNNING_OWNED
            self.status_text = "Running"
        else:
            self.state = ControllerState.DEGRADED_ENGINE
            self.status_text = engine_msg or "Unknown engine state"
            self.running = False
            return

        self._manual_reset_devices.clear()
        self.current_led_colors.clear()
        self._apply_saved_zone_sizes()
        self._restore_last_applied_state()

        # 2. Start Sensor bridge
        self.sensor_supervisor.start()

        # 3. Spawn lighting loop thread (20 Hz)
        self._loop_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._loop_thread.start()

    def stop(self):
        """Stop lighting loop and child processes."""
        if not self.running:
            return
        self.state = ControllerState.STOPPING
        self.status_text = "Stopping..."
        self.running = False
        self._stop_event.set()

        if self._loop_thread:
            self._loop_thread.join(timeout=1.0)
            self._loop_thread = None

        self.sensor_supervisor.stop()
        self.openrgb_supervisor.stop()

        self.state = ControllerState.IDLE
        self.status_text = "Stopped"

    def retry(self):
        """Restart engine and sensor subsystems."""
        self.stop()
        time.sleep(0.5)
        self.start(self._icon_update_cb)

    def _run_loop(self):
        """Main 20 Hz synchronization loop."""
        alpha = float(self.config_manager.get_config()["thermal"].get("ema_factor", 0.15))
        last_poll_time = 0.0

        try:
            from openrgb.utils import RGBColor
        except ImportError:
            class RGBColor:
                def __init__(self, r, g, b):
                    self.red = int(r)
                    self.green = int(g)
                    self.blue = int(b)

        while not self._stop_event.is_set():
            now = time.monotonic()

            if self.openrgb_supervisor.state not in (EngineState.RUNNING_OWNED, EngineState.RUNNING_EXTERNAL):
                time.sleep(0.5)
                continue

            if not self._sensor_allows_updates():
                time.sleep(0.2)
                continue

            if self.lights_off:
                self._send_black_to_all()
                time.sleep(0.2)
                continue

            cfg = self.config_manager.get_config()

            # Check screensaver pause
            should_pause = False
            if cfg["behavior"].get("stop_on_screensaver", False) and is_screensaver_active():
                should_pause = True

            if should_pause:
                if not self.auto_paused:
                    self.auto_paused = True
                    self.status_text = "Auto-Paused (Screensaver)"
                    self._send_black_to_all()
                time.sleep(0.5)
                continue
            else:
                if self.auto_paused:
                    self.auto_paused = False
                    self.status_text = "Running"

                        # Periodic temperature update (1 Hz)
            if now - last_poll_time >= 1.0:
                last_poll_time = now
                reading = self.sensor_supervisor.get_latest_reading()

                raw_cpu = reading.cpu_temp if reading else None
                raw_gpu = reading.gpu_temp if reading else None

                if raw_cpu is not None:
                    self.smoothed_cpu_temp = apply_ema(self.smoothed_cpu_temp, raw_cpu, alpha)
                if raw_gpu is not None:
                    self.smoothed_gpu_temp = apply_ema(self.smoothed_gpu_temp, raw_gpu, alpha)

            if self.smoothed_cpu_temp is not None or self.smoothed_gpu_temp is not None:
                self._dispatch_thermal_frame()

            time.sleep(0.05)  # 20 Hz

    def _dispatch_thermal_frame(self):
        """Calculate and route thermal colors through supervisor using stable descriptor keys."""
        cfg = self.config_manager.get_config()
        thermal = cfg["thermal"]
        speed_val = max(1, min(10, int(thermal.get("transition_speed", 5))))
        step_factor = speed_val / 50.0

        try:
            from openrgb.utils import RGBColor
        except ImportError:
            class RGBColor:
                def __init__(self, r, g, b):
                    self.red = int(r)
                    self.green = int(g)
                    self.blue = int(b)

        # Update tray icon color
        if self.smoothed_cpu_temp is not None:
            r_icon, g_icon, b_icon = map_temp_to_rgb(
                self.smoothed_cpu_temp,
                min_temp=thermal["min_temp"],
                mid_temp=thermal["mid_temp"],
                max_temp=thermal["max_temp"],
                min_color=thermal["min_color"],
                mid_color=thermal["mid_color"],
                max_color=thermal["max_color"],
                brightness=thermal.get("brightness", 100)
            )
            if self._icon_update_cb:
                try:
                    self._icon_update_cb((r_icon, g_icon, b_icon))
                except Exception:
                    pass

        sup = self.openrgb_supervisor
        descriptors = getattr(sup, "get_descriptors", lambda: [])()
        device_configs = cfg.get("devices", {})
        unmatched = cfg.get("unmatched_legacy_profiles", {})

        target_items = []
        if descriptors:
            for desc in descriptors:
                if desc.ambiguous:
                    logger.warning("Skipping ambiguous target %s (%s)", desc.name, desc.key)
                    continue
                target_key = desc.stable_key or desc.key
                if not target_key:
                    continue
                dev = getattr(sup, "_target_map", {}).get(target_key)
                if dev is None and hasattr(sup, "_find_device"):
                    dev = sup._find_device(target_key)
                target_items.append((target_key, desc.name, dev))
        else:
            devices = sup.get_devices() if hasattr(sup, "get_devices") else []
            for dev in devices:
                d_name = getattr(dev, "name", "Device")
                target_items.append((d_name, d_name, dev))

        for target_key, dev_name, dev in target_items:
            if not self.can_apply_thermal_frame(target_key):
                continue
            try:
                desc = next(
                    (d for d in descriptors if getattr(d, "key", None) == target_key or getattr(d, "stable_key", None) == target_key),
                    None
                ) if descriptors else None
                canonical_key = get_canonical_device_key(desc, descriptors) if desc else target_key

                dev_cfg = device_configs.get(canonical_key)
                if not dev_cfg and canonical_key != target_key:
                    dev_cfg = device_configs.get(target_key)
                if not dev_cfg:
                    name_matches = [
                        d for d in descriptors
                        if getattr(d, "name", "") == dev_name or getattr(d, "display_name", "") == dev_name
                    ] if descriptors else []
                    if len(name_matches) == 1:
                        dev_cfg = device_configs.get(dev_name, unmatched.get(dev_name, {}))
                    elif not descriptors:
                        dev_cfg = device_configs.get(dev_name, unmatched.get(dev_name, {}))
                    else:
                        dev_cfg = {}
                if not isinstance(dev_cfg, dict):
                    dev_cfg = {}
                default_src = dev_cfg.get("default_source", "cpu")
                led_sources = dev_cfg.get("temp_source", {})
                led_brights = dev_cfg.get("led_brightness", {})

                leds = getattr(dev, "leds", []) if dev else []
                if leds:
                    has_valid_temp = False
                    for idx, led in enumerate(leds):
                        led_name = getattr(led, "name", f"LED {idx}")
                        src = led_sources.get(led_name, default_src)
                        temp = self.smoothed_gpu_temp if src == "gpu" else self.smoothed_cpu_temp
                        if temp is not None:
                            has_valid_temp = True
                            break
                    if not has_valid_temp:
                        continue

                    colors = []
                    for idx, led in enumerate(leds):
                        led_name = getattr(led, "name", f"LED {idx}")
                        src = led_sources.get(led_name, default_src)
                        temp = self.smoothed_gpu_temp if src == "gpu" else self.smoothed_cpu_temp
                        bright = int(led_brights.get(led_name, 100))

                        led_key = f"{target_key}:{idx}"
                        if temp is not None:
                            tgt_r, tgt_g, tgt_b = map_temp_to_rgb(
                                temp,
                                min_temp=thermal["min_temp"],
                                mid_temp=thermal["mid_temp"],
                                max_temp=thermal["max_temp"],
                                min_color=thermal["min_color"],
                                mid_color=thermal["mid_color"],
                                max_color=thermal["max_color"],
                                brightness=bright
                            )
                            if led_key not in self.current_led_colors:
                                self.current_led_colors[led_key] = [float(tgt_r), float(tgt_g), float(tgt_b)]

                            curr_rgb = tuple(self.current_led_colors[led_key])
                            next_rgb = lerp_color(curr_rgb, (float(tgt_r), float(tgt_g), float(tgt_b)), step_factor)
                            self.current_led_colors[led_key] = list(next_rgb)
                        else:
                            if led_key in self.current_led_colors:
                                next_rgb = tuple(self.current_led_colors[led_key])
                            else:
                                next_rgb = (0.0, 0.0, 0.0)

                        colors.append(RGBColor(
                            max(0, min(255, int(next_rgb[0]))),
                            max(0, min(255, int(next_rgb[1]))),
                            max(0, min(255, int(next_rgb[2])))
                        ))

                    if hasattr(sup, "set_colors"):
                        sup.set_colors(target_key, colors, fast=True)
                    elif dev is not None and hasattr(dev, "set_colors"):
                        dev.set_colors(colors, fast=True)
                else:
                    src = default_src
                    temp = self.smoothed_gpu_temp if src == "gpu" else self.smoothed_cpu_temp
                    if temp is not None:
                        tgt_r, tgt_g, tgt_b = map_temp_to_rgb(
                            temp,
                            min_temp=thermal["min_temp"],
                            mid_temp=thermal["mid_temp"],
                            max_temp=thermal["max_temp"],
                            min_color=thermal["min_color"],
                            mid_color=thermal["mid_color"],
                            max_color=thermal["max_color"],
                            brightness=100
                        )
                        color = RGBColor(tgt_r, tgt_g, tgt_b)
                        if hasattr(sup, "set_colors"):
                            sup.set_colors(target_key, [color], fast=True)
                        elif dev is not None and hasattr(dev, "set_color"):
                            dev.set_color(color)
            except Exception:
                pass
    def restore_manufacturer_defaults(self, target_key: str) -> 'WriteResult':
        if not self.openrgb_supervisor:
            from openrgb_temp_sync.openrgb_runtime import WriteResult
            return WriteResult(
                ok=False,
                target_key=target_key,
                operation='restore_manufacturer_defaults',
                error_code='no_supervisor',
                message='Supervisor unavailable'
            )
        
        res = self.openrgb_supervisor.restore_manufacturer_defaults(target_key)
        if getattr(res, "ok", False):
            resolved = self.resolve_target_key(target_key) or target_key
            self._manual_reset_devices.add(resolved)
            self._device_owners[resolved] = "unmanaged"
            self._clear_device_color_cache(resolved)
        # We do not change ownership or claim success on rejection.
        return res


