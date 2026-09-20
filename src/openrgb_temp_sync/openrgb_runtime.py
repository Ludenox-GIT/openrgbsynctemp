"""
OpenRGB Engine lifecycle supervisor.
Supervises bundled OpenRGB server process on loopback (127.0.0.1:6742),
safely adopts external compatible server, rejects unsafe wildcard listeners,
and manages SDK client connection and Direct mode configuration.
"""

import logging
import os
import copy
import hashlib
import json
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from openrgb_temp_sync.config import get_canonical_device_key
from openrgb_temp_sync.windows_runtime import (
    PortStatus,
    WindowsJobObject,
    inspect_port_6742,
    is_process_elevated
)

logger = logging.getLogger("OpenRGBRuntime")


_MODE_DIRECTION_VALUES = {
    "left": 0,
    "right": 1,
    "up": 2,
    "down": 3,
    "horizontal": 4,
    "vertical": 5,
}


def _coerce_mode_direction(direction: Any) -> Optional[int]:
    """Convert UI direction labels to the integer expected by ModeData.pack()."""
    if isinstance(direction, bool):
        return int(direction)
    if isinstance(direction, int):
        return int(direction)
    if isinstance(direction, str):
        token = direction.strip().lower().replace("-", "_").replace(" ", "_")
        if token in _MODE_DIRECTION_VALUES:
            return _MODE_DIRECTION_VALUES[token]
        try:
            return int(token, 10)
        except ValueError:
            return None
    try:
        return int(direction)
    except (TypeError, ValueError):
        return None


def _normalize_rgb_triplet(color: Any) -> List[int]:
    """Convert RGBColor or tuple/list/sequence to JSON-safe [r, g, b] triplet (0-255)."""
    if hasattr(color, "red") and hasattr(color, "green") and hasattr(color, "blue"):
        return [max(0, min(255, int(color.red))), max(0, min(255, int(color.green))), max(0, min(255, int(color.blue)))]
    if hasattr(color, "r") and hasattr(color, "g") and hasattr(color, "b"):
        return [max(0, min(255, int(color.r))), max(0, min(255, int(color.g))), max(0, min(255, int(color.b)))]
    if isinstance(color, (list, tuple)) and len(color) >= 3:
        return [max(0, min(255, int(color[0]))), max(0, min(255, int(color[1]))), max(0, min(255, int(color[2])))]
    return [0, 0, 0]


@dataclass(frozen=True)
class ModeDescriptor:
    """Immutable, normalized mode metadata from one SDK inventory snapshot."""

    name: str
    flags: Tuple[str, ...] = ()
    index: int = 0
    value: int = 0
    speed_min: Optional[int] = None
    speed_max: Optional[int] = None
    speed: Optional[int] = None
    brightness_min: Optional[int] = None
    brightness_max: Optional[int] = None
    brightness: Optional[int] = None
    colors_min: Optional[int] = None
    colors_max: Optional[int] = None
    color_mode: Optional[str] = None
    direction: Optional[int] = None
    directions_supported: Tuple[str, ...] = ()

    @property
    def supports_speed(self) -> bool:
        return "speed" in self.flags

    @property
    def supports_brightness(self) -> bool:
        return "brightness" in self.flags

    @property
    def supports_direction(self) -> bool:
        return any(f in self.flags for f in ("direction_lr", "direction_ud", "direction_hv", "direction"))

    @property
    def supports_per_led(self) -> bool:
        return "per_led" in self.flags

    @property
    def supports_mode_specific_color(self) -> bool:
        return "mode_specific" in self.flags

    @property
    def supports_random_color(self) -> bool:
        return "random" in self.flags

    @property
    def supports_manual_save(self) -> bool:
        return "manual_save" in self.flags

    @property
    def supports_automatic_save(self) -> bool:
        return "automatic_save" in self.flags

    @property
    def supports_save(self) -> bool:
        return self.supports_manual_save or "save" in self.flags


@dataclass(frozen=True)
class ZoneDescriptor:
    """Immutable zone metadata; ``index`` is session-only."""

    key: str
    name: str
    index: int
    led_count: int
    leds_min: int
    leds_max: int
    resizable: bool
    zone_type: str = "unknown"


@dataclass(frozen=True)
class DeviceDescriptor:
    """Normalized device identity and capabilities for one inventory generation."""

    key: str
    name: str
    display_name: str
    session_index: int
    stable_key: Optional[str] = None
    device_type: str = "unknown"
    vendor_id: Optional[str] = None
    product_id: Optional[str] = None
    serial: Optional[str] = None
    location: Optional[str] = None
    path: Optional[str] = None
    ambiguous: bool = False
    zones: Tuple[ZoneDescriptor, ...] = ()
    modes: Tuple[ModeDescriptor, ...] = ()
    aliases: Tuple[str, ...] = ()
    identity_evidence: Tuple[Tuple[str, str], ...] = ()

    @property
    def device_id(self) -> str:
        return self.key


@dataclass(frozen=True)
class WriteResult:
    """Structured result for every adapter write/readback operation."""

    ok: bool
    target_key: Optional[str] = None
    operation: str = ""
    requested: Any = None
    readback: Any = None
    error_code: Optional[str] = None
    message: str = ""
    inventory_generation: int = 0

    @property
    def code(self) -> Optional[str]:
        return self.error_code

    def __bool__(self) -> bool:
        return self.ok



@dataclass(frozen=True)
class ResetCapability:
    status: str
    reason: str
    command: Optional[str] = None
    evidence: Optional[str] = None

def _first_metadata(device: Any, *names: str) -> Optional[str]:
    for name in names:
        value = getattr(device, name, None)
        if value is None:
            continue
        value = str(value).strip()
        if value:
            return value
    md = getattr(device, "metadata", None)
    if md is not None:
        for name in names:
            value = getattr(md, name, None)
            if value is None:
                continue
            value = str(value).strip()
            if value:
                return value
    return None


def _metadata_for_device(device: Any) -> dict[str, Optional[str]]:
    return {
        "device_type": _first_metadata(device, "device_type", "type", "description") or "unknown",
        "vendor_id": _first_metadata(device, "vendor_id", "vendor", "manufacturer_id"),
        "product_id": _first_metadata(device, "product_id", "product", "model"),
        "serial": _first_metadata(device, "serial", "serial_number", "serialnumber"),
        "location": _first_metadata(device, "location", "location_path", "topology"),
        "path": _first_metadata(device, "physical_path", "path", "device_path", "controller_path"),
    }


def _stable_identity_fingerprint(name: str, metadata: dict[str, Optional[str]]) -> tuple[str, bool]:
    """Return deterministic identity material and whether it has strong evidence."""
    evidence = {
        key: value for key, value in metadata.items()
        if value and key != "device_type"
    }
    # A display name, list index, or numeric SDK id alone is never enough to persist.
    strong = bool(evidence.get("serial") or evidence.get("location") or evidence.get("path"))
    parts = [("name", name), ("device_type", metadata.get("device_type") or "unknown")]
    parts.extend(sorted(evidence.items()))
    return json.dumps(parts, sort_keys=True), strong


class EngineState:
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING_OWNED = "RUNNING_OWNED"
    RUNNING_EXTERNAL = "RUNNING_EXTERNAL"
    CONFLICT = "CONFLICT"
    DEGRADED = "DEGRADED"


def build_openrgb_launch_args(
    binary_path: str,
    host: str = "127.0.0.1",
    port: int = 6742,
    config_dir: Optional[str] = None
) -> List[str]:
    """Build verified command line arguments for bundled OpenRGB server."""
    args = [
        binary_path,
        "--server",
        "--server-host", str(host),
        "--server-port", str(port)
    ]
    if config_dir:
        args.extend(["--config", config_dir])
    return args


class RestartBudget:
    """Restricts child process restarts to at most max_restarts within window_seconds."""

    def __init__(self, max_restarts: int = 3, window_seconds: float = 60.0):
        self.max_restarts = max_restarts
        self.window_seconds = window_seconds
        self.timestamps: List[float] = []

    def record_and_check(self) -> bool:
        now = time.monotonic()
        self.timestamps = [t for t in self.timestamps if now - t < self.window_seconds]
        if len(self.timestamps) >= self.max_restarts:
            return False
        self.timestamps.append(now)
        return True



def normalize_mode_descriptor(mode: Any, index: int = 0) -> ModeDescriptor:
    """Normalize SDK mode object into immutable ModeDescriptor."""
    name = getattr(mode, "name", None)
    if not name or not isinstance(name, str):
        name = f"Mode {index}"
    else:
        name = str(name).strip()

    value = getattr(mode, "value", None)
    if not isinstance(value, int):
        value = getattr(mode, "id", index)
        if not isinstance(value, int):
            value = index

    flags_set: Set[str] = set()
    raw_flags = getattr(mode, "flags", None)
    if isinstance(raw_flags, int):
        if raw_flags & 1:
            flags_set.add("speed")
        if raw_flags & 2:
            flags_set.add("direction_lr")
            flags_set.add("direction")
        if raw_flags & 4:
            flags_set.add("direction_ud")
            flags_set.add("direction")
        if raw_flags & 8:
            flags_set.add("direction_hv")
            flags_set.add("direction")
        if raw_flags & 16:
            flags_set.add("brightness")
        if raw_flags & 32:
            flags_set.add("per_led")
        if raw_flags & 64:
            flags_set.add("mode_specific")
        if raw_flags & 128:
            flags_set.add("random")
        if raw_flags & 256:
            flags_set.add("manual_save")
        if raw_flags & 512:
            flags_set.add("automatic_save")
    elif isinstance(raw_flags, (list, tuple, set)):
        for item in raw_flags:
            flags_set.add(str(item).strip().lower())

    if getattr(mode, "has_speed", False):
        flags_set.add("speed")
    if getattr(mode, "has_brightness", False):
        flags_set.add("brightness")
    if getattr(mode, "has_direction", False):
        flags_set.add("direction")
    if getattr(mode, "manual_save", False):
        flags_set.add("manual_save")
    if getattr(mode, "automatic_save", False):
        flags_set.add("automatic_save")

    def _safe_int(val: Any) -> Optional[int]:
        if val is None:
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    speed_min = _safe_int(getattr(mode, "speed_min", None))
    speed_max = _safe_int(getattr(mode, "speed_max", None))
    speed = _safe_int(getattr(mode, "speed", None))
    brightness_min = _safe_int(getattr(mode, "brightness_min", None))
    brightness_max = _safe_int(getattr(mode, "brightness_max", None))
    brightness = _safe_int(getattr(mode, "brightness", None))
    colors_min = _safe_int(getattr(mode, "colors_min", None))
    colors_max = _safe_int(getattr(mode, "colors_max", None))
    direction = _safe_int(getattr(mode, "direction", None))

    dirs: List[str] = []
    if "direction_lr" in flags_set:
        dirs.extend(["left", "right"])
    if "direction_ud" in flags_set:
        dirs.extend(["up", "down"])
    if "direction_hv" in flags_set:
        dirs.extend(["horizontal", "vertical"])
    if not dirs and "direction" in flags_set:
        dirs.extend(["left", "right", "up", "down"])

    color_mode_raw = getattr(mode, "color_mode", None)
    color_mode_str = None
    if color_mode_raw is not None:
        if hasattr(color_mode_raw, "name"):
            color_mode_str = str(color_mode_raw.name).lower()
        else:
            color_mode_str = str(color_mode_raw).lower()

    return ModeDescriptor(
        name=name,
        flags=tuple(sorted(flags_set)),
        index=index,
        value=value,
        speed_min=speed_min,
        speed_max=speed_max,
        speed=speed,
        brightness_min=brightness_min,
        brightness_max=brightness_max,
        brightness=brightness,
        colors_min=colors_min,
        colors_max=colors_max,
        color_mode=color_mode_str,
        direction=direction,
        directions_supported=tuple(dirs)
    )

class OpenRGBSupervisor:
    """Supervises OpenRGB engine, lifecycle, port safety, and SDK connection."""

    def __init__(
        self,
        binary_path: Optional[str] = None,
        host: str = "127.0.0.1",
        port: int = 6742,
        config_dir: Optional[str] = None,
        job_object: Optional[WindowsJobObject] = None,
        readiness_timeout_seconds: float = 5.0,
        device_detection_delay_seconds: float = 0.0,
        require_elevation: bool = False,
        popen_factory: Optional[Callable[..., Any]] = None,
        port_checker: Optional[Callable[[], bool]] = None,
        client_connector: Optional[Callable[[], bool]] = None
    ):
        self.binary_path = binary_path
        self.host = host
        self.port = port
        self.config_dir = config_dir
        self.job_object = job_object
        self.readiness_timeout_seconds = readiness_timeout_seconds
        # OpenRGB starts its SDK listener before the hardware scan finishes.
        # SMBus-backed RAM can therefore be absent from the first device list.
        self.device_detection_delay_seconds = max(0.0, float(device_detection_delay_seconds))
        self.require_elevation = bool(require_elevation)
        self._popen_factory = popen_factory or subprocess.Popen
        self._port_checker = port_checker or self._check_port_ready
        self._client_connector = client_connector or self._connect_client

        self.state = EngineState.STOPPED
        self.status_message = "Engine stopped"
        self.restart_budget = RestartBudget(max_restarts=3, window_seconds=60.0)

        self._process: Optional[Any] = None
        self._is_owned = False
        self._client: Any = None
        self.devices: List[Any] = []
        self._device_baselines: dict[str, dict[str, Any]] = {}
        self._sdk_lock = threading.RLock()
        self.inventory_generation: int = 0
        self._descriptors: List[DeviceDescriptor] = []
        self._target_map: dict[str, Any] = {}
        self._ambiguous_targets: set[str] = set()

    def _check_port_ready(self) -> bool:
        """Check whether TCP port is accepting connections on loopback."""
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.3)
        try:
            sock.connect((self.host, self.port))
            return True
        except Exception:
            return False
        finally:
            sock.close()

    def is_owned(self) -> bool:
        return self._is_owned

    def get_devices(self) -> List[Any]:
        with self._sdk_lock:
            return list(self.devices)

    def get_descriptors(self) -> List[DeviceDescriptor]:
        with self._sdk_lock:
            return list(self._descriptors)

    def refresh_inventory(self, devices: Optional[List[Any]] = None) -> List[DeviceDescriptor]:
        with self._sdk_lock:
            if devices is not None:
                self.devices = list(devices)
            elif self._client is not None:
                try:
                    self.devices = list(getattr(self._client, "devices", []) or [])
                except Exception:
                    self.devices = []

            self.inventory_generation += 1
            self._target_map.clear()
            self._ambiguous_targets.clear()

            name_counts: dict[str, int] = {}
            for dev in self.devices:
                name = getattr(dev, "name", "") or "Unknown Device"
                name_counts[name] = name_counts.get(name, 0) + 1

            descriptors: List[DeviceDescriptor] = []

            for idx, dev in enumerate(self.devices):
                name = getattr(dev, "name", "") or "Unknown Device"
                metadata = _metadata_for_device(dev)
                fp_json, strong = _stable_identity_fingerprint(name, metadata)

                if strong:
                    h = hashlib.sha256(fp_json.encode("utf-8")).hexdigest()[:12]
                    stable_key = f"{name}_{h}"
                    key = stable_key
                else:
                    stable_key = None
                    key = f"{name}_idx{idx}"

                ambiguous = False
                if name_counts[name] > 1 and not strong:
                    ambiguous = True

                zones: List[ZoneDescriptor] = []
                for zi, zone in enumerate(getattr(dev, "zones", []) or []):
                    zname = getattr(zone, "name", f"Zone {zi}")
                    min_l, max_l = self._zone_limits(dev, zi, zone)
                    current_l = len(getattr(zone, "leds", []) or [])
                    zones.append(ZoneDescriptor(
                        key=f"{key}_z{zi}",
                        name=zname,
                        index=zi,
                        led_count=current_l,
                        leds_min=min_l,
                        leds_max=max_l,
                        resizable=hasattr(zone, "resize")
                    ))

                modes: List[ModeDescriptor] = []
                for mi, mode in enumerate(getattr(dev, "modes", []) or []):
                    modes.append(self._normalize_mode(mode, mi))

                desc = DeviceDescriptor(
                    key=key,
                    name=name,
                    display_name=name,
                    session_index=idx,
                    stable_key=stable_key,
                    device_type=metadata.get("device_type") or "unknown",
                    vendor_id=metadata.get("vendor_id"),
                    product_id=metadata.get("product_id"),
                    serial=metadata.get("serial"),
                    location=metadata.get("location"),
                    path=metadata.get("path"),
                    ambiguous=ambiguous,
                    zones=tuple(zones),
                    modes=tuple(modes)
                )
                descriptors.append(desc)

                self._target_map[key] = dev
                if stable_key:
                    self._target_map[stable_key] = dev

            for name, count in name_counts.items():
                if count > 1:
                    self._ambiguous_targets.add(name)
                else:
                    single_dev = next((d for d, desc in zip(self.devices, descriptors) if desc.name == name), None)
                    if single_dev is not None:
                        self._target_map[name] = single_dev

            self._descriptors = descriptors
            self._capture_device_baselines(self.devices)
            return descriptors

    def _resolve_target(self, target_key: str) -> Tuple[Optional[Any], Optional[str]]:
        if target_key in self._ambiguous_targets:
            return None, "ambiguous"
        dev = self._target_map.get(target_key)
        if dev is not None:
            return dev, None
        for desc, d in zip(self._descriptors, self.devices):
            if desc.key == target_key or desc.stable_key == target_key or desc.name == target_key:
                if desc.name in self._ambiguous_targets and target_key == desc.name:
                    return None, "ambiguous"
                return d, None
        for d in self.devices:
            if getattr(d, "name", "") == target_key:
                # Count occurrences of this name across self.devices
                matches = [dev for dev in self.devices if getattr(dev, "name", "") == target_key]
                if len(matches) > 1:
                    return None, "ambiguous"
                return d, None
        return None, "device_not_found"

    def _capture_device_baselines(self, devices: List[Any]):
        previous = self._device_baselines
        baselines: dict[str, dict[str, Any]] = {}
        for idx, device in enumerate(devices):
            name = getattr(device, "name", "") or "Unknown"
            active_mode = getattr(device, "active_mode", None)
            modes = getattr(device, "modes", []) or []
            mode = None
            if isinstance(active_mode, int) and 0 <= active_mode < len(modes):
                mode = copy.deepcopy(modes[active_mode])

            desc = self._descriptors[idx] if idx < len(self._descriptors) else None
            key = desc.key if desc else (f"{name}_{idx}" if not name else name)

            entry = {
                "device": device,
                "active_mode": active_mode,
                "mode": mode,
                "colors": copy.deepcopy(getattr(device, "colors", [])),
                "zone_sizes": [len(getattr(zone, "leds", []) or []) for zone in getattr(device, "zones", [])],
            }
            # Inventory rescans happen while thermal sync is active (for example
            # after a zone edit).  They must not replace the original pre-sync
            # snapshot with the current thermal frame.  Stable identities make it
            # safe to carry the first capture across SDK object refreshes; an
            # unstable duplicate-name key is intentionally recaptured.
            if key in previous and (desc is not None and (desc.stable_key or not desc.ambiguous)):
                entry = previous[key]
            baselines[key] = entry
            if name not in self._ambiguous_targets and name not in baselines:
                baselines[name] = entry

        self._device_baselines = baselines

    def serialize_vendor_baseline(self) -> Dict[str, Any]:
        """
        Serialize the current live inventory into JSON-safe baseline data keyed by canonical descriptor key.
        Read-only against SDK objects: does not call set_mode, set_colors, resize, save_mode, or configure_direct.
        Baseline snapshots represent saved vendor states, not OEM factory-reset protocols.
        """
        with self._sdk_lock:
            descriptors = self.get_descriptors()
            if not descriptors and self.devices:
                descriptors = self.refresh_inventory(self.devices)

            result: Dict[str, Any] = {}
            for idx, desc in enumerate(descriptors):
                dev = self.devices[idx] if idx < len(self.devices) else self._find_device(desc.key)
                canonical_key = get_canonical_device_key(desc, descriptors)

                # Active mode and mode name
                active_mode = getattr(dev, "active_mode", None) if dev is not None else None
                mode_name = None
                if isinstance(active_mode, int):
                    dev_modes = getattr(dev, "modes", []) or []
                    if 0 <= active_mode < len(dev_modes):
                        m_obj = dev_modes[active_mode]
                        mode_name = getattr(m_obj, "name", None) or (m_obj.get("name") if isinstance(m_obj, dict) else None)
                    if not mode_name and desc.modes and 0 <= active_mode < len(desc.modes):
                        mode_name = desc.modes[active_mode].name
                elif dev is not None and hasattr(dev, "mode"):
                    m = getattr(dev, "mode")
                    mode_name = getattr(m, "name", str(m)) if m else None

                # Per-LED colors as RGB triplets
                raw_colors = getattr(dev, "colors", []) if dev is not None else []
                colors_triplets: List[List[int]] = []
                if raw_colors:
                    for c in raw_colors:
                        colors_triplets.append(_normalize_rgb_triplet(c))

                # Per-zone LED counts
                zone_led_counts: List[int] = []
                if dev is not None and getattr(dev, "zones", None) is not None:
                    for z in getattr(dev, "zones", []):
                        leds = getattr(z, "leds", [])
                        zone_led_counts.append(len(leds) if leds is not None else 0)
                elif desc.zones:
                    zone_led_counts = [z.led_count for z in desc.zones]

                identity_evidence = {
                    "name": desc.name,
                    "key": desc.key,
                    "stable_key": desc.stable_key,
                    "device_type": desc.device_type,
                    "vendor_id": desc.vendor_id,
                    "product_id": desc.product_id,
                    "serial": desc.serial,
                    "location": desc.location,
                    "path": desc.path,
                }

                result[canonical_key] = {
                    "canonical_key": canonical_key,
                    "name": desc.name,
                    "key": desc.key,
                    "stable_key": desc.stable_key,
                    "device_type": desc.device_type,
                    "vendor_id": desc.vendor_id,
                    "product_id": desc.product_id,
                    "serial": desc.serial,
                    "location": desc.location,
                    "path": desc.path,
                    "active_mode": active_mode,
                    "mode_name": mode_name,
                    "colors": colors_triplets,
                    "zone_led_counts": zone_led_counts,
                    "identity_evidence": identity_evidence,
                }

            return result

    def capture_vendor_baseline(self) -> Dict[str, Any]:
        """Alias for serialize_vendor_baseline."""
        return self.serialize_vendor_baseline()

    def _find_device(self, target_key: str) -> Optional[Any]:
        dev, err = self._resolve_target(target_key)
        return dev

    def _zone_limits(self, device: Any, zone_index: int, zone: Any) -> Tuple[int, int]:
        data_zones = getattr(getattr(device, "data", None), "zones", []) or []
        data_zone = data_zones[zone_index] if zone_index < len(data_zones) else None
        minimum = getattr(data_zone, "leds_min", getattr(zone, "minimum", len(getattr(zone, "leds", []))))
        maximum = getattr(data_zone, "leds_max", getattr(zone, "maximum", len(getattr(zone, "leds", []))))
        return int(minimum), int(maximum)

    def resize_zone(self, target_key: str, zone_index: int, size: int) -> bool:
        """Resize a manually-configurable OpenRGB zone and verify requested size against readback."""
        with self._sdk_lock:
            device = self._find_device(target_key)
            if device is None:
                return False
            zones = getattr(device, "zones", []) or []
            if not isinstance(zone_index, int) or not 0 <= zone_index < len(zones):
                return False
            zone = zones[zone_index]
            minimum, maximum = self._zone_limits(device, zone_index, zone)
            try:
                requested = int(size)
            except (TypeError, ValueError):
                return False
            if requested < minimum or requested > maximum or not hasattr(zone, "resize"):
                return False
            try:
                zone.resize(requested)
                readback_len = len(getattr(zone, "leds", []) or [])
                if readback_len != requested:
                    logger.warning("Zone resize readback mismatch for %s / zone %d: requested %d, got %d",
                                   target_key, zone_index, requested, readback_len)
                    return False
                logger.info("Resized %s / %s to %d LEDs", target_key, getattr(zone, "name", zone_index), requested)
                return True
            except Exception:
                logger.warning("Could not resize %s / %s", target_key, getattr(zone, "name", zone_index), exc_info=True)
                return False

    
    def get_reset_capability(self, target_key: str) -> ResetCapability:
        """
        Query manufacturer factory reset capability.
        Saved vendor baselines are persistent state snapshots, not true OEM resets.
        Hardware manufacturer reset remains unverified/unsupported and fail-closed.
        """
        dev = None
        for d in self._descriptors:
            if d.key == target_key or d.stable_key == target_key:
                dev = d
                break
        if not dev:
            return ResetCapability('unsupported', 'Device not found or ambiguous')
        
        name = dev.name.lower()
        if 'msi mag b550 tomahawk' in name:
            return ResetCapability('unverified', 'Unproven reset command for MSI MAG B550 TOMAHAWK')
        if 'ene dram' in name or 'g.skill' in name:
            return ResetCapability('unverified', 'Unproven reset command for ENE/G.SKILL DRAM')
        if 'rtx 3060' in name and 'gigabyte' in name:
            return ResetCapability('unverified', 'Unproven reset command for Gigabyte RTX 3060')
        
        return ResetCapability('unsupported', f'No verified factory reset available for {dev.name}')

    def restore_manufacturer_defaults(self, target_key: str) -> WriteResult:
        cap = self.get_reset_capability(target_key)
        if cap.status != 'verified':
            return WriteResult(
                ok=False,
                target_key=target_key,
                operation='restore_manufacturer_defaults',
                error_code='reset_rejected',
                message=cap.reason,
                inventory_generation=self.inventory_generation
            )
        
        return WriteResult(
            ok=False,
            target_key=target_key,
            operation='restore_manufacturer_defaults',
            error_code='not_implemented',
            message='No devices are currently verified for reset.',
            inventory_generation=self.inventory_generation
        )

    def set_colors(self, target_key: str, colors: List[Any], fast: bool = True) -> WriteResult:
        """Thread-safe, serialized color write with capability validation."""
        with self._sdk_lock:
            device, err = self._resolve_target(target_key)
            if device is None:
                return WriteResult(
                    ok=False,
                    target_key=target_key,
                    operation="set_colors",
                    requested=colors,
                    error_code=err or "device_not_found",
                    message=f"Cannot target device '{target_key}': {err}",
                    inventory_generation=self.inventory_generation
                )
            try:
                if hasattr(device, "set_colors"):
                    device.set_colors(colors, fast=fast)
                elif hasattr(device, "set_color"):
                    if colors:
                        device.set_color(colors[0])
                if hasattr(device, "update"):
                    device.update()
                readback = getattr(device, "colors", None)
                if readback is None:
                    return WriteResult(
                        ok=False,
                        target_key=target_key,
                        operation="set_colors",
                        requested=colors,
                        readback=readback,
                        error_code="readback_mismatch",
                        message="Color readback was unavailable after write",
                        inventory_generation=self.inventory_generation
                    )
                requested_values = [self._color_value(color) for color in colors]
                readback_values = [self._color_value(color) for color in readback]
                if requested_values != readback_values:
                    return WriteResult(
                        ok=False,
                        target_key=target_key,
                        operation="set_colors",
                        requested=colors,
                        readback=readback,
                        error_code="readback_mismatch",
                        message=f"Color readback mismatch: expected {colors}, got {readback}",
                        inventory_generation=self.inventory_generation
                    )
                return WriteResult(
                    ok=True,
                    target_key=target_key,
                    operation="set_colors",
                    requested=colors,
                    readback=readback,
                    inventory_generation=self.inventory_generation
                )
            except Exception as ex:
                disconnected = isinstance(ex, ConnectionError) or "disconnected" in ex.__class__.__name__.lower()
                if disconnected:
                    self._mark_sdk_disconnected(ex)
                logger.warning("Color write failed for %s: %s", target_key, ex)
                return WriteResult(
                    ok=False,
                    target_key=target_key,
                    operation="set_colors",
                    requested=colors,
                    error_code="sdk_disconnected" if disconnected else "write_error",
                    message=("OpenRGB SDK disconnected; retry engine" if disconnected else str(ex)),
                    inventory_generation=self.inventory_generation
                )

    @staticmethod
    def _color_value(color: Any) -> Any:
        """Normalize SDK RGBColor values and tuple-like test values for comparison."""
        if all(hasattr(color, channel) for channel in ("red", "green", "blue")):
            return (color.red, color.green, color.blue)
        if isinstance(color, (tuple, list)):
            return tuple(color)
        return color

    def restore_device(
        self,
        target_key: str,
        persisted_baseline: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Restore one device from its runtime snapshot or a saved vendor snapshot."""
        with self._sdk_lock:
            runtime_baseline = self._device_baselines.get(target_key)
            device = self._find_device(target_key) or (
                runtime_baseline.get("device") if runtime_baseline else None
            )
            if device is None and runtime_baseline:
                device = runtime_baseline.get("device")
            if device is None:
                return False

            # An explicit persisted baseline is authoritative.  The runtime
            # snapshot is intentionally kept for the temporary sync/reset
            # flow, but must not shadow the vendor_default snapshot when the
            # user asks for a true restore.
            baseline = runtime_baseline
            if persisted_baseline is not None:
                baseline = dict(persisted_baseline)
                baseline["device"] = device
                baseline["zone_sizes"] = list(baseline.get("zone_led_counts", []))
                baseline["active_mode"] = baseline.get("active_mode")
                baseline["mode_name"] = baseline.get("mode_name")
                baseline["colors"] = copy.deepcopy(baseline.get("colors", []))

            if not baseline:
                for b_entry in self._device_baselines.values():
                    if b_entry.get("device") is device:
                        baseline = b_entry
                        break
            if not baseline:
                return False

            try:
                mode = copy.deepcopy(baseline.get("mode"))
                mode_name = baseline.get("mode_name") or getattr(mode, "name", None)
                if mode is None and mode_name and hasattr(device, "modes"):
                    mode = next(
                        (candidate for candidate in (getattr(device, "modes", []) or [])
                         if str(getattr(candidate, "name", "")).strip().lower() == str(mode_name).strip().lower()),
                        None,
                    )

                # OpenRGB only accepts Configure/ResizeZone while the
                # controller is in Direct mode.  A persisted MSI baseline can
                # be a hardware effect (for example Rainbow wave), so enter
                # Direct temporarily before restoring JRAINBOW counts.
                baseline_zone_sizes = list(baseline.get("zone_sizes", []))
                needs_zone_resize = any(
                    hasattr(zone, "resize") and len(getattr(zone, "leds", []) or []) != size
                    for zone, size in zip(getattr(device, "zones", []) or [], baseline_zone_sizes)
                )
                if needs_zone_resize:
                    direct_applied = False
                    set_custom_mode = getattr(device, "set_custom_mode", None)
                    if callable(set_custom_mode):
                        try:
                            set_custom_mode()
                            direct_applied = True
                        except (TypeError, ValueError):
                            pass
                    if not direct_applied and hasattr(device, "set_mode"):
                        direct_mode = next(
                            (candidate for candidate in (getattr(device, "modes", []) or [])
                             if str(getattr(candidate, "name", "")).strip().lower() == "direct"),
                            None,
                        )
                        if direct_mode is not None:
                            try:
                                device.set_mode(direct_mode)
                                direct_applied = True
                            except (TypeError, ValueError):
                                pass
                    if not direct_applied:
                        raise ValueError("Direct mode is required before restoring zone LED counts")

                    for zone, size in zip(getattr(device, "zones", []) or [], baseline_zone_sizes):
                        if hasattr(zone, "resize") and len(getattr(zone, "leds", []) or []) != size:
                            zone.resize(size)
                    if any(
                        len(getattr(zone, "leds", []) or []) != size
                        for zone, size in zip(getattr(device, "zones", []) or [], baseline_zone_sizes)
                    ):
                        raise ValueError("Zone LED count readback mismatch during restore")

                mode_applied = False
                if mode is not None and hasattr(device, "set_mode"):
                    try:
                        device.set_mode(mode, force=True)
                        mode_applied = True
                    except (TypeError, ValueError):
                        try:
                            device.set_mode(mode)
                            mode_applied = True
                        except (TypeError, ValueError):
                            pass

                if not mode_applied and mode_name and hasattr(device, "set_mode"):
                    try:
                        device.set_mode(mode_name)
                        mode_applied = True
                    except (TypeError, ValueError):
                        pass

                if not mode_applied and baseline.get("active_mode") is not None and hasattr(device, "set_mode"):
                    device.set_mode(baseline["active_mode"])

                # The Python SDK's set_mode() can return without raising even
                # when the controller rejects the packet (for example a
                # hardware effect that is not supported by this firmware).
                # Do not report a successful restore until the controller's
                # fresh active-mode readback agrees with the saved baseline.
                if mode_name and hasattr(device, "active_mode"):
                    expected_name = str(mode_name).strip().lower()
                    active_name = ""
                    for attempt in range(3):
                        active = getattr(device, "active_mode", None)
                        active_name = ""
                        if isinstance(active, int):
                            active_modes = getattr(device, "modes", []) or []
                            if 0 <= active < len(active_modes):
                                active_name = str(getattr(active_modes[active], "name", ""))
                        elif isinstance(active, str):
                            active_name = active
                        else:
                            active_name = str(getattr(active, "name", ""))
                        if active_name.strip().lower() == expected_name:
                            break
                        update = getattr(device, "update", None)
                        if attempt < 2 and callable(update):
                            time.sleep(0.05)
                            update()
                    if active_name and active_name.strip().lower() != expected_name:
                        raise ValueError(
                            f"Mode restore readback mismatch: expected {mode_name}, got {active_name}"
                        )

                colors = copy.deepcopy(baseline.get("colors", []))
                # Persisted JSON snapshots contain RGB triplets.  Rehydrate
                # them to the shape accepted by the active SDK/device object.
                if colors and isinstance(colors[0], list):
                    existing_colors = getattr(device, "colors", []) or []
                    if existing_colors and all(hasattr(existing_colors[0], channel) for channel in ("red", "green", "blue")):
                        try:
                            from openrgb.utils import RGBColor
                            colors = [RGBColor(int(c[0]), int(c[1]), int(c[2])) for c in colors]
                        except ImportError:
                            pass
                    else:
                        colors = [tuple(c[:3]) if isinstance(c, list) else c for c in colors]

                color_mode = getattr(mode, "color_mode", None)
                if color_mode is None and mode_name and hasattr(device, "active_mode"):
                    active_idx = getattr(device, "active_mode", None)
                    if isinstance(active_idx, int):
                        active_modes = getattr(device, "modes", []) or []
                        if 0 <= active_idx < len(active_modes):
                            color_mode = getattr(active_modes[active_idx], "color_mode", None)
                is_per_led = color_mode is None or getattr(color_mode, "name", "") == "PER_LED" or color_mode == 1
                if colors and is_per_led and hasattr(device, "set_colors"):
                    device.set_colors(colors)
                logger.info("Restored original LED state for %s", target_key)
                return True
            except Exception as exc:
                if isinstance(exc, ConnectionError) or "disconnected" in exc.__class__.__name__.lower():
                    self._mark_sdk_disconnected(exc)
                logger.warning("Could not restore original LED state for %s", target_key, exc_info=True)
                return False

    def restore_device_from_baseline(self, target_key: str, baseline: Dict[str, Any]) -> bool:
        """Restore one device from a persisted vendor baseline entry."""
        return self.restore_device(target_key, persisted_baseline=baseline)

    def start(self) -> Tuple[str, str]:
        """
        Inspects port and launches bundled engine or adopts compatible external engine.
        Returns (state, status_message).
        """
        port_status, desc, _ = inspect_port_6742()

        if port_status == PortStatus.UNSAFE_WILDCARD:
            self.state = EngineState.CONFLICT
            self.status_message = f"Blocked: {desc}"
            logger.error(self.status_message)
            return self.state, self.status_message

        if port_status == PortStatus.CONFLICT_FOREIGN_PROCESS:
            self.state = EngineState.CONFLICT
            self.status_message = f"Conflict: {desc}"
            logger.error(self.status_message)
            return self.state, self.status_message

        if port_status == PortStatus.COMPATIBLE_EXTERNAL:
            self._is_owned = False
            conn_ok = False
            try:
                conn_ok = bool(self._client_connector())
            except Exception as e:
                logger.warning(f"External OpenRGB SDK connection notice: {e}")
                conn_ok = False

            if not conn_ok:
                self.state = EngineState.DEGRADED
                self.status_message = "External OpenRGB detected but SDK connection failed"
                logger.warning(self.status_message)
                return self.state, self.status_message

            self.state = EngineState.RUNNING_EXTERNAL
            self.status_message = "Connected to External OpenRGB"
            logger.info(self.status_message)
            return self.state, self.status_message

        # Port is FREE: launch bundled engine if binary is present
        if not self.binary_path or not os.path.exists(self.binary_path):
            self.state = EngineState.DEGRADED
            self.status_message = "Bundled OpenRGB executable not found"
            logger.warning(self.status_message)
            return self.state, self.status_message

        if self.require_elevation and not is_process_elevated():
            self.state = EngineState.DEGRADED
            self.status_message = "Administrator elevation is required for SMBus/PawnIO devices"
            logger.error(self.status_message)
            return self.state, self.status_message

        if not self.restart_budget.record_and_check():
            self.state = EngineState.DEGRADED
            self.status_message = "OpenRGB crash restart limit exceeded (3 in 60s)"
            logger.error(self.status_message)
            return self.state, self.status_message

        self.state = EngineState.STARTING
        self.status_message = "Launching bundled OpenRGB engine..."

        args = build_openrgb_launch_args(self.binary_path, self.host, self.port, self.config_dir)
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

        try:
            self._process = self._popen_factory(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags
            )
            self._is_owned = True
            if self.job_object and self._process:
                try:
                    if hasattr(self._process, "_handle"):
                        self.job_object.assign_process(self._process._handle)
                except Exception:
                    pass

            deadline = time.monotonic() + self.readiness_timeout_seconds
            is_ready = False

            while time.monotonic() < deadline:
                if self._process.poll() is not None:
                    exit_code = self._process.returncode
                    self.state = EngineState.DEGRADED
                    self.status_message = f"Bundled OpenRGB exited prematurely with code {exit_code}"
                    logger.error(self.status_message)
                    self._is_owned = False
                    self._process = None
                    return self.state, self.status_message

                if self._port_checker():
                    is_ready = True
                    break

                time.sleep(0.1)

            if not is_ready:
                self.state = EngineState.DEGRADED
                self.status_message = f"Bundled OpenRGB readiness timed out after {self.readiness_timeout_seconds}s"
                logger.error(self.status_message)
                if self._process and self._process.poll() is None:
                    try:
                        self._process.terminate()
                        self._process.wait(timeout=1.0)
                    except Exception:
                        pass
                self._is_owned = False
                self._process = None
                return self.state, self.status_message

            if self.device_detection_delay_seconds:
                # Keep the child supervised while SMBus/I2C detectors register
                # DRAM and motherboard controllers after the SDK port opens.
                detection_deadline = time.monotonic() + self.device_detection_delay_seconds
                while time.monotonic() < detection_deadline:
                    if self._process.poll() is not None:
                        exit_code = self._process.returncode
                        self.state = EngineState.DEGRADED
                        self.status_message = f"Bundled OpenRGB exited during device detection with code {exit_code}"
                        logger.error(self.status_message)
                        self._is_owned = False
                        self._process = None
                        return self.state, self.status_message
                    remaining = detection_deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    time.sleep(min(0.1, remaining))

            conn_ok = False
            try:
                conn_ok = bool(self._client_connector())
            except Exception as e:
                logger.warning(f"Bundled OpenRGB SDK connection notice: {e}")
                conn_ok = False

            if not conn_ok:
                self.state = EngineState.DEGRADED
                self.status_message = "Bundled OpenRGB started but SDK client connection failed"
                logger.error(self.status_message)
                if self._process and self._process.poll() is None:
                    try:
                        self._process.terminate()
                        self._process.wait(timeout=1.0)
                    except Exception:
                        try:
                            self._process.kill()
                        except Exception:
                            pass
                self._is_owned = False
                self._process = None
                return self.state, self.status_message

            self.state = EngineState.RUNNING_OWNED
            self.status_message = "Bundled OpenRGB running"
            return self.state, self.status_message

        except Exception as e:
            self.state = EngineState.DEGRADED
            self.status_message = f"Failed to start OpenRGB: {e}"
            logger.error(self.status_message)
            self._is_owned = False
            self._process = None
            return self.state, self.status_message

    def _connect_client(self) -> bool:
        """Connect OpenRGB SDK client if openrgb library is installed. Returns True on success."""
        # Avoid constructing the third-party client when the endpoint is already offline.
        # Its constructor opens a socket before raising on connect failure, which cannot
        # be reclaimed reliably if construction never returns an object.
        if not self._check_port_ready():
            self.devices = []
            return False
        try:
            from openrgb import OpenRGBClient
            self._client = OpenRGBClient(self.host, self.port)
            devs = self._client.devices or []
            self.refresh_inventory(devs)
            logger.info(f"OpenRGB SDK connected. Discovered {len(self.devices)} devices.")
            return True
        except ImportError:
            logger.warning("openrgb-python not installed in local runtime; SDK client unavailable.")
            self.devices = []
            return False
        except Exception as e:
            logger.warning(f"OpenRGB SDK connection notice: {e}")
            self._disconnect_client()
            self.devices = []
            return False

    def _disconnect_client(self):
        """Close the SDK socket when a handshake fails or the supervisor stops."""
        client = self._client
        self._client = None
        if client is not None:
            try:
                disconnect = getattr(client, "disconnect", None)
                if callable(disconnect):
                    disconnect()
            except Exception:
                logger.debug("OpenRGB SDK disconnect failed", exc_info=True)

    def _mark_sdk_disconnected(self, exc: BaseException) -> None:
        """Fail closed when the single OpenRGB SDK socket drops mid-operation."""
        self.state = EngineState.DEGRADED
        self.status_message = "OpenRGB SDK disconnected; retry engine"
        self._disconnect_client()
        logger.warning("OpenRGB SDK disconnected during operation: %s", exc)

    def _normalize_mode(self, mode: Any, index: int = 0) -> ModeDescriptor:
        return normalize_mode_descriptor(mode, index)

    def set_mode(
        self,
        target_key: str,
        mode: Union[str, int],
        speed: Optional[int] = None,
        brightness: Optional[int] = None,
        direction: Optional[Union[str, int]] = None,
        colors: Optional[List[Any]] = None,
        save: bool = False
    ) -> WriteResult:
        with self._sdk_lock:
            device, err = self._resolve_target(target_key)
            if device is None:
                return WriteResult(
                    ok=False,
                    target_key=target_key,
                    operation="set_mode",
                    error_code=err or "not_found",
                    message=f"Target {target_key} could not be resolved: {err}",
                    inventory_generation=getattr(self, "inventory_generation", 0)
                )

            dev_modes = getattr(device, "modes", []) or []
            target_mode_idx = None
            target_mode_obj = None

            if isinstance(mode, int):
                if 0 <= mode < len(dev_modes):
                    target_mode_idx = mode
                    target_mode_obj = dev_modes[mode]
            else:
                mode_str = str(mode).strip().lower()
                for mi, m in enumerate(dev_modes):
                    m_name = getattr(m, "name", "").strip().lower()
                    if m_name == mode_str:
                        target_mode_idx = mi
                        target_mode_obj = m
                        break

            if target_mode_obj is None:
                return WriteResult(
                    ok=False,
                    target_key=target_key,
                    operation="set_mode",
                    requested=mode,
                    error_code="mode_not_found",
                    message=f"Mode {mode} not found on target {target_key}",
                    inventory_generation=getattr(self, "inventory_generation", 0)
                )

            mode_desc = self._normalize_mode(target_mode_obj, target_mode_idx)

            if speed is not None:
                if not mode_desc.supports_speed:
                    return WriteResult(
                        ok=False,
                        target_key=target_key,
                        operation="set_mode",
                        requested={"mode": mode_desc.name, "speed": speed},
                        error_code="unsupported_parameter",
                        message=f"Speed parameter unsupported for mode {mode_desc.name}",
                        inventory_generation=getattr(self, "inventory_generation", 0)
                    )
                if mode_desc.speed_min is not None and mode_desc.speed_max is not None:
                    speed = max(mode_desc.speed_min, min(mode_desc.speed_max, int(speed)))
                if hasattr(target_mode_obj, "speed"):
                    try:
                        target_mode_obj.speed = speed
                    except Exception:
                        pass

            if brightness is not None:
                if not mode_desc.supports_brightness:
                    return WriteResult(
                        ok=False,
                        target_key=target_key,
                        operation="set_mode",
                        requested={"mode": mode_desc.name, "brightness": brightness},
                        error_code="unsupported_parameter",
                        message=f"Brightness parameter unsupported for mode {mode_desc.name}",
                        inventory_generation=getattr(self, "inventory_generation", 0)
                    )
                if mode_desc.brightness_min is not None and mode_desc.brightness_max is not None:
                    brightness = max(mode_desc.brightness_min, min(mode_desc.brightness_max, int(brightness)))
                if hasattr(target_mode_obj, "brightness"):
                    try:
                        target_mode_obj.brightness = brightness
                    except Exception:
                        pass

            if direction is not None:
                if not mode_desc.supports_direction:
                    return WriteResult(
                        ok=False,
                        target_key=target_key,
                        operation="set_mode",
                        requested={"mode": mode_desc.name, "direction": direction},
                        error_code="unsupported_parameter",
                        message=f"Direction parameter unsupported for mode {mode_desc.name}",
                        inventory_generation=getattr(self, "inventory_generation", 0)
                    )
                direction_value = _coerce_mode_direction(direction)
                if direction_value is None:
                    return WriteResult(
                        ok=False,
                        target_key=target_key,
                        operation="set_mode",
                        requested={"mode": mode_desc.name, "direction": direction},
                        error_code="invalid_parameter",
                        message=f"Invalid direction parameter: {direction}",
                        inventory_generation=getattr(self, "inventory_generation", 0)
                    )
                if hasattr(target_mode_obj, "direction"):
                    try:
                        target_mode_obj.direction = direction_value
                    except Exception:
                        pass

            if colors is not None and hasattr(target_mode_obj, "colors"):
                try:
                    target_mode_obj.colors = colors
                except Exception:
                    pass

            if save:
                if not mode_desc.supports_save:
                    return WriteResult(
                        ok=False,
                        target_key=target_key,
                        operation="save_mode",
                        requested={"mode": mode_desc.name, "save": True},
                        error_code="save_unsupported",
                        message=f"Save to device unsupported for mode {mode_desc.name}",
                        inventory_generation=getattr(self, "inventory_generation", 0)
                    )

            try:
                if hasattr(device, "set_mode"):
                    applied = False
                    if save:
                        try:
                            device.set_mode(target_mode_obj, save=True)
                            applied = True
                        except (TypeError, ValueError):
                            pass
                    if not applied:
                        try:
                            device.set_mode(target_mode_obj)
                            applied = True
                        except (TypeError, ValueError):
                            pass
                    if not applied:
                        try:
                            device.set_mode(mode_desc.name)
                            applied = True
                        except (TypeError, ValueError):
                            pass
                    if not applied:
                        try:
                            device.set_mode(target_mode_idx)
                            applied = True
                        except (TypeError, ValueError):
                            pass
                    if save and hasattr(device, "save_mode"):
                        try:
                            device.save_mode()
                        except Exception:
                            pass
                elif save and hasattr(device, "save_mode"):
                    device.save_mode()
            except Exception as ex:
                disconnected = isinstance(ex, ConnectionError) or "disconnected" in ex.__class__.__name__.lower()
                if disconnected:
                    self._mark_sdk_disconnected(ex)
                return WriteResult(
                    ok=False,
                    target_key=target_key,
                    operation="set_mode",
                    requested=mode_desc.name,
                    error_code="sdk_disconnected" if disconnected else "sdk_error",
                    message=("OpenRGB SDK disconnected; retry engine" if disconnected
                             else f"Error setting mode on device: {ex}"),
                    inventory_generation=getattr(self, "inventory_generation", 0)
                )

            active_mode = getattr(device, "active_mode", None)
            mode_applied = getattr(device, "mode_applied", None)
            readback_match = True
            if active_mode is not None:
                if isinstance(active_mode, int):
                    readback_match = (active_mode == target_mode_idx)
                elif isinstance(active_mode, str):
                    readback_match = (active_mode.lower() == mode_desc.name.lower())
                elif hasattr(active_mode, "name"):
                    readback_match = (active_mode.name.lower() == mode_desc.name.lower())
            elif mode_applied is not None:
                readback_match = (str(mode_applied).lower() == mode_desc.name.lower())

            if not readback_match:
                return WriteResult(
                    ok=False,
                    target_key=target_key,
                    operation="set_mode",
                    requested=mode_desc.name,
                    readback=active_mode,
                    error_code="readback_mismatch",
                    message=f"Mode readback mismatch: expected {mode_desc.name}, got {active_mode}",
                    inventory_generation=getattr(self, "inventory_generation", 0)
                )

            return WriteResult(
                ok=True,
                target_key=target_key,
                operation="set_mode",
                requested=mode_desc.name,
                readback=active_mode if active_mode is not None else mode_desc.name,
                message=f"Successfully set mode {mode_desc.name} on {target_key}",
                inventory_generation=getattr(self, "inventory_generation", 0)
            )

    def set_device_mode(self, target_key: str, mode_name: str) -> bool:
        # OpenRGB's SDK exposes a dedicated SetCustomMode packet for returning
        # a controller to software/per-LED control.  Some hardware (notably
        # MSI Mystic Light) lists a "Direct" mode but ignores the generic
        # UpdateMode packet when leaving a hardware effect.  The packet is
        # unsafe for ENE DRAM/GPU controllers on this OpenRGB SDK and can
        # disconnect the single SDK client, so only use it for a known
        # motherboard target and verify the fresh active-mode readback.
        if str(mode_name).strip().lower() == "direct":
            with self._sdk_lock:
                device, _ = self._resolve_target(target_key)
                if device is not None:
                    descriptor = next(
                        (
                            desc for desc in self._descriptors
                            if desc.key == target_key or desc.stable_key == target_key
                        ),
                        None,
                    )
                    device_type = str(
                        getattr(descriptor, "device_type", None)
                        or getattr(device, "device_type", "")
                    ).strip().lower()
                    device_name = str(getattr(device, "name", "")).strip().lower()
                    custom_mode_safe = (
                        device_type in {"0", "motherboard", "mainboard", "device_type.motherboard"}
                        or ("msi" in device_name and "b550" in device_name)
                    )
                    modes = getattr(device, "modes", []) or []
                    has_direct = any(
                        str(getattr(mode, "name", "")).strip().lower() == "direct"
                        for mode in modes
                    )
                    set_custom_mode = getattr(device, "set_custom_mode", None)
                    if custom_mode_safe and has_direct and callable(set_custom_mode):
                        try:
                            set_custom_mode()
                            active_mode = getattr(device, "active_mode", None)
                            if isinstance(active_mode, int) and 0 <= active_mode < len(modes):
                                active_name = str(getattr(modes[active_mode], "name", "")).strip().lower()
                            elif isinstance(active_mode, str):
                                active_name = active_mode.strip().lower()
                            else:
                                active_name = str(getattr(active_mode, "name", "")).strip().lower()
                            return active_name == "direct"
                        except Exception as exc:
                            if isinstance(exc, ConnectionError) or "disconnected" in exc.__class__.__name__.lower():
                                self._mark_sdk_disconnected(exc)
                                return False
                            logger.warning("OpenRGB custom mode negotiation failed for %s", target_key, exc_info=True)
        return bool(self.set_mode(target_key, mode_name))

    def save_device_mode(self, target_key: str) -> WriteResult:
        with self._sdk_lock:
            device, err = self._resolve_target(target_key)
            if device is None:
                return WriteResult(
                    ok=False,
                    target_key=target_key,
                    operation="save_mode",
                    error_code=err or "not_found",
                    message=f"Target {target_key} could not be resolved: {err}",
                    inventory_generation=getattr(self, "inventory_generation", 0)
                )
            dev_modes = getattr(device, "modes", []) or []
            active_idx = getattr(device, "active_mode", 0)
            if not isinstance(active_idx, int) or active_idx < 0 or active_idx >= len(dev_modes):
                active_idx = 0
            if dev_modes:
                curr_mode = dev_modes[active_idx]
                mode_desc = self._normalize_mode(curr_mode, active_idx)
                if not mode_desc.supports_save:
                    return WriteResult(
                        ok=False,
                        target_key=target_key,
                        operation="save_mode",
                        error_code="save_unsupported",
                        message=f"Save to device is not supported for mode {mode_desc.name}",
                        inventory_generation=getattr(self, "inventory_generation", 0)
                    )
            if hasattr(device, "save_mode"):
                try:
                    device.save_mode()
                    return WriteResult(
                        ok=True,
                        target_key=target_key,
                        operation="save_mode",
                        message=f"Successfully saved mode to hardware on {target_key}",
                        inventory_generation=getattr(self, "inventory_generation", 0)
                    )
                except Exception as ex:
                    return WriteResult(
                        ok=False,
                        target_key=target_key,
                        operation="save_mode",
                        error_code="save_failed",
                        message=f"Hardware save failed: {ex}",
                        inventory_generation=getattr(self, "inventory_generation", 0)
                    )
            return WriteResult(
                ok=False,
                target_key=target_key,
                operation="save_mode",
                error_code="save_unsupported",
                message="Device SDK does not support save_mode operation",
                inventory_generation=getattr(self, "inventory_generation", 0)
            )

    def configure_devices_direct_mode(self, devices: List[Any]):
        """Attempt to set all devices to 'direct' mode for responsive frame updates."""
        for device in devices:
            try:
                modes = getattr(device, "modes", [])
                for mode in modes:
                    mode_name = getattr(mode, "name", "")
                    if mode_name.lower() == "direct":
                        device.set_mode(mode_name)
                        break
            except Exception:
                pass

    def stop(self):
        """Clean shutdown. Terminates only owned child process; never kills external OpenRGB."""
        with self._sdk_lock:
            self._disconnect_client()
            self.devices = []
            self._descriptors = []
            self._target_map.clear()
            self._ambiguous_targets.clear()
            self._device_baselines = {}

            if self._is_owned and self._process and self._process.poll() is None:
                try:
                    self._process.terminate()
                    self._process.wait(timeout=2.0)
                except Exception:
                    try:
                        self._process.kill()
                    except Exception:
                        pass

            self._process = None
            self._is_owned = False
            self.state = EngineState.STOPPED
            self.status_message = "Engine stopped"
