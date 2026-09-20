"""
Configuration manager for OpenRGB Temp Sync.
Schema v2 support, atomic writes, timestamped backups, and lossless v1 migration.
"""

import copy
import datetime
import json
import os
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_CONFIG_V2: Dict[str, Any] = {
    "schema_version": 2,
    "thermal": {
        "min_temp": 30.0,
        "mid_temp": 60.0,
        "max_temp": 75.0,
        "min_color": [0, 255, 0],
        "mid_color": [0, 0, 255],
        "max_color": [255, 0, 0],
        "brightness": 100,
        "ema_factor": 0.15,
        "transition_speed": 5
    },
    "behavior": {
        "stop_on_screensaver": False,
        "startup_enabled": False,
        "lights_off_persisted": False
    },
    "devices": {},
    "unmatched_legacy_profiles": {},
    "runtime": {
        "engine_port": 6742,
        "last_migration_version": None,
        "diagnostic_mode": False
    },
    "last_applied": {
        "mode": "temperature",
        "devices": {},
        "saved_at": None
    },
    "profiles": {},
    "active_profile": "Default",
    "vendor_baselines": {}
}


def get_default_local_appdata_dir() -> str:
    """Resolve %LOCALAPPDATA%\\OpenRGBTempSync."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        local_app_data = os.path.expanduser("~")
    path = os.path.join(local_app_data, "OpenRGBTempSync")
    os.makedirs(path, exist_ok=True)
    return path


def validate_config_v2(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate schema v2 data, clamping invalid bounds and repairing corrupted fields."""
    cfg = copy.deepcopy(DEFAULT_CONFIG_V2)

    if not isinstance(data, dict):
        return cfg

    cfg["schema_version"] = 2

    # Thermal validation
    thermal_in = data.get("thermal", {})
    if not isinstance(thermal_in, dict):
        thermal_in = {}

    try:
        min_t = float(thermal_in.get("min_temp", cfg["thermal"]["min_temp"]))
        mid_t = float(thermal_in.get("mid_temp", cfg["thermal"]["mid_temp"]))
        max_t = float(thermal_in.get("max_temp", cfg["thermal"]["max_temp"]))
    except (ValueError, TypeError):
        min_t, mid_t, max_t = 30.0, 60.0, 75.0

    if not (min_t < mid_t < max_t):
        min_t, mid_t, max_t = 30.0, 60.0, 75.0

    cfg["thermal"]["min_temp"] = min_t
    cfg["thermal"]["mid_temp"] = mid_t
    cfg["thermal"]["max_temp"] = max_t

    def validate_rgb(color_in, default_rgb):
        if isinstance(color_in, (list, tuple)) and len(color_in) >= 3:
            try:
                return [max(0, min(255, int(c))) for c in color_in[:3]]
            except (ValueError, TypeError):
                pass
        return default_rgb

    cfg["thermal"]["min_color"] = validate_rgb(thermal_in.get("min_color"), [0, 255, 0])
    cfg["thermal"]["mid_color"] = validate_rgb(thermal_in.get("mid_color"), [0, 0, 255])
    cfg["thermal"]["max_color"] = validate_rgb(thermal_in.get("max_color"), [255, 0, 0])

    try:
        bright = int(thermal_in.get("brightness", 100))
        cfg["thermal"]["brightness"] = max(0, min(100, bright))
    except (ValueError, TypeError):
        cfg["thermal"]["brightness"] = 100

    try:
        speed = int(thermal_in.get("transition_speed", 5))
        cfg["thermal"]["transition_speed"] = max(1, min(10, speed))
    except (ValueError, TypeError):
        cfg["thermal"]["transition_speed"] = 5

    try:
        ema = float(thermal_in.get("ema_factor", 0.15))
        if 0.01 <= ema <= 1.0:
            cfg["thermal"]["ema_factor"] = ema
        else:
            cfg["thermal"]["ema_factor"] = 0.15
    except (ValueError, TypeError):
        cfg["thermal"]["ema_factor"] = 0.15

    # Behavior validation
    behavior_in = data.get("behavior", {})
    if isinstance(behavior_in, dict):
        cfg["behavior"]["stop_on_screensaver"] = bool(behavior_in.get("stop_on_screensaver", False))
        cfg["behavior"]["startup_enabled"] = bool(behavior_in.get("startup_enabled", False))
        cfg["behavior"]["lights_off_persisted"] = bool(behavior_in.get("lights_off_persisted", False))

    # Devices & Unmatched profiles
    devices_in = data.get("devices", {})
    if isinstance(devices_in, dict):
        cfg["devices"] = copy.deepcopy(devices_in)

    unmatched_in = data.get("unmatched_legacy_profiles", {})
    if isinstance(unmatched_in, dict):
        cfg["unmatched_legacy_profiles"] = copy.deepcopy(unmatched_in)

    # Runtime
    runtime_in = data.get("runtime", {})
    if isinstance(runtime_in, dict):
        cfg["runtime"]["engine_port"] = 6742
        cfg["runtime"]["last_migration_version"] = runtime_in.get("last_migration_version")
        cfg["runtime"]["diagnostic_mode"] = bool(runtime_in.get("diagnostic_mode", False))

    # Profiles validation
    last_applied_in = data.get("last_applied", {})
    if isinstance(last_applied_in, dict):
        mode = str(last_applied_in.get("mode", "temperature"))
        allowed_modes = {"temperature", "manual", "hardware_effect", "vendor_default", "mixed"}
        cfg["last_applied"]["mode"] = mode if mode in allowed_modes else "temperature"
        devices_in = last_applied_in.get("devices", {})
        if isinstance(devices_in, dict):
            cfg["last_applied"]["devices"] = {
                str(key): copy.deepcopy(value)
                for key, value in devices_in.items()
                if isinstance(value, dict)
            }
        saved_at = last_applied_in.get("saved_at")
        cfg["last_applied"]["saved_at"] = str(saved_at) if saved_at is not None else None

    profiles_in = data.get("profiles", {})
    if isinstance(profiles_in, dict):
        cfg["profiles"] = copy.deepcopy(profiles_in)
    else:
        cfg["profiles"] = {}
    cfg["active_profile"] = str(data.get("active_profile", "Default"))

    # Vendor baselines validation
    baselines_in = data.get("vendor_baselines", {})
    if isinstance(baselines_in, dict):
        cfg["vendor_baselines"] = copy.deepcopy(baselines_in)
    else:
        cfg["vendor_baselines"] = {}

    return cfg


def migrate_v1_to_v2(v1_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Losslessly convert v1 schema to schema v2.
    Preserves all thresholds, colors, transition speeds, per-LED brightness, and source mappings.
    """
    cfg = copy.deepcopy(DEFAULT_CONFIG_V2)

    if not isinstance(v1_data, dict):
        return cfg

    # Thermal settings
    if "min_temp" in v1_data:
        cfg["thermal"]["min_temp"] = float(v1_data["min_temp"])
    if "mid_temp" in v1_data:
        cfg["thermal"]["mid_temp"] = float(v1_data["mid_temp"])
    if "max_temp" in v1_data:
        cfg["thermal"]["max_temp"] = float(v1_data["max_temp"])

    if "min_color" in v1_data:
        cfg["thermal"]["min_color"] = list(v1_data["min_color"][:3])
    if "mid_color" in v1_data:
        cfg["thermal"]["mid_color"] = list(v1_data["mid_color"][:3])
    if "max_color" in v1_data:
        cfg["thermal"]["max_color"] = list(v1_data["max_color"][:3])

    if "brightness" in v1_data:
        cfg["thermal"]["brightness"] = int(v1_data["brightness"])
    if "transition_speed" in v1_data:
        cfg["thermal"]["transition_speed"] = int(v1_data["transition_speed"])

    # Behavior
    if "stop_on_screensaver" in v1_data:
        cfg["behavior"]["stop_on_screensaver"] = bool(v1_data["stop_on_screensaver"])

    # Device mappings
    v1_brightness = v1_data.get("device_led_brightness", {})
    v1_sources = v1_data.get("device_temp_source", {})

    all_devices = set(v1_brightness.keys()) | set(v1_sources.keys())

    for dev_name in all_devices:
        dev_bright = v1_brightness.get(dev_name, {})
        if not isinstance(dev_bright, dict):
            dev_bright = {}

        raw_source = v1_sources.get(dev_name, "cpu")
        if isinstance(raw_source, str):
            default_source = raw_source
            led_sources = {}
        elif isinstance(raw_source, dict):
            default_source = raw_source.get("default", "cpu")
            led_sources = {k: v for k, v in raw_source.items() if k != "default"}
        else:
            default_source = "cpu"
            led_sources = {}

        cfg["unmatched_legacy_profiles"][dev_name] = {
            "device_name": dev_name,
            "default_source": default_source,
            "led_brightness": dev_bright,
            "temp_source": led_sources
        }

    if "vendor_baselines" in v1_data and isinstance(v1_data["vendor_baselines"], dict):
        cfg["vendor_baselines"] = copy.deepcopy(v1_data["vendor_baselines"])
    cfg["runtime"]["last_migration_version"] = "1.0-legacy"
    return validate_config_v2(cfg)



def get_canonical_device_key(descriptor: Any, descriptors: Optional[List[Any]] = None) -> str:
    """
    Return the canonical config key for a descriptor.
    Prefers stable_key when available. If absent, falls back to display name only if
    the device name is unique across descriptors; otherwise falls back to key or name.
    """
    if isinstance(descriptor, str):
        return descriptor

    stable_key = getattr(descriptor, "stable_key", None)
    if stable_key:
        return str(stable_key)

    name = getattr(descriptor, "name", None) or getattr(descriptor, "display_name", None) or ""
    if name and descriptors:
        matches = [
            d for d in descriptors
            if getattr(d, "name", None) == name or getattr(d, "display_name", None) == name
        ]
        if len(matches) == 1:
            return name

    key = getattr(descriptor, "key", None)
    return str(key or name)


def resolve_config_device_key(target: str, descriptors: List[Any]) -> Optional[str]:
    """
    Map target (exact stable_key, key, or legacy name) to canonical config key.
    Returns:
      - canonical key if target matches exact key or unique legacy name.
      - None if target is ambiguous (multiple matches) or unknown.
    """
    if not target or not isinstance(target, str) or not descriptors:
        return None

    # 1. Exact match on stable_key or key
    for d in descriptors:
        stable_key = getattr(d, "stable_key", None)
        key = getattr(d, "key", None)
        if (stable_key and stable_key == target) or (key and key == target):
            return get_canonical_device_key(d, descriptors)

    # 2. Compatibility fallback for unique legacy display name
    name_matches = [
        d for d in descriptors
        if (d == target if isinstance(d, str) else (getattr(d, "name", None) == target or getattr(d, "display_name", None) == target))
    ]
    if len(name_matches) == 1:
        return get_canonical_device_key(name_matches[0], descriptors)
    elif len(name_matches) > 1:
        return None

    return None


def merge_legacy_device_profiles(
    devices: Dict[str, Any],
    unmatched_legacy: Dict[str, Any],
    detected_devices: Any
) -> Dict[str, Any]:
    """
    Merge exact-name legacy profiles into editable devices view for currently detected devices.
    Preserves existing device configurations in devices dict under canonical stable keys.
    Ambiguous legacy names remain in unmatched_legacy and are not silently applied.
    """
    merged = copy.deepcopy(devices) if isinstance(devices, dict) else {}
    unmatched = unmatched_legacy if isinstance(unmatched_legacy, dict) else {}

    if not detected_devices:
        return merged

    first_item = detected_devices[0] if isinstance(detected_devices, (list, tuple)) and detected_devices else None
    is_descriptor_list = hasattr(first_item, "name") or hasattr(first_item, "key") or hasattr(first_item, "stable_key")

    if is_descriptor_list:
        descriptors = list(detected_devices)

        # 1. Clean up or migrate existing keys in merged
        for k in list(merged.keys()):
            matches = [
                d for d in descriptors
                if getattr(d, "name", None) == k or getattr(d, "display_name", None) == k
            ]
            if len(matches) > 1:
                # Ambiguous legacy name: preserve in merged so reconcile_device_profiles_on_save
                # can safely move it to unmatched_legacy_profiles on save. Do not assign to duplicate devices.
                continue
            elif len(matches) == 1:
                canonical_k = get_canonical_device_key(matches[0], descriptors)
                if canonical_k != k:
                    if canonical_k not in merged:
                        merged[canonical_k] = merged.pop(k)
                    else:
                        del merged[k]

        # 2. Merge unmatched legacy profiles for detected unique descriptors
        for desc in descriptors:
            canonical_key = get_canonical_device_key(desc, descriptors)
            if canonical_key in merged:
                continue

            name = getattr(desc, "name", "")
            matches = [
                d for d in descriptors
                if getattr(d, "name", "") == name or getattr(d, "display_name", "") == name
            ]
            if len(matches) == 1 and name in unmatched:
                merged[canonical_key] = copy.deepcopy(unmatched[name])
                merged[canonical_key]["device_name"] = name
    else:
        detected_names = list(detected_devices)
        name_counts = {}
        for n in detected_names:
            name_counts[n] = name_counts.get(n, 0) + 1

        for name, count in name_counts.items():
            if count > 1:
                # Ambiguous legacy name: preserve in merged so reconcile_device_profiles_on_save
                # can safely move it to unmatched_legacy_profiles on save.
                continue
            elif count == 1:
                if name not in merged and name in unmatched:
                    merged[name] = copy.deepcopy(unmatched[name])

    return merged


def reconcile_device_profiles_on_save(
    temp_devices_config: Dict[str, Any],
    unmatched_legacy: Dict[str, Any],
    descriptors: Optional[List[Any]] = None
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    On save, keep unknown and ambiguous unmatched profiles in unmatched_legacy_profiles,
    and persist matched device settings into devices.
    Returns (persisted_devices, remaining_unmatched_legacy).
    """
    persisted = copy.deepcopy(temp_devices_config) if isinstance(temp_devices_config, dict) else {}
    unmatched = copy.deepcopy(unmatched_legacy) if isinstance(unmatched_legacy, dict) else {}

    if descriptors:
        for name, profile in list(persisted.items()):
            matches = [
                d for d in descriptors
                if (d == name if isinstance(d, str) else (getattr(d, "name", None) == name or getattr(d, "display_name", None) == name))
            ]
            if len(matches) > 1:
                unmatched[name] = copy.deepcopy(profile)
                del persisted[name]

        remaining_unmatched = {}
        for legacy_name, profile in unmatched.items():
            resolved_key = resolve_config_device_key(legacy_name, descriptors)
            if resolved_key is not None and resolved_key in persisted:
                continue
            if legacy_name not in persisted:
                remaining_unmatched[legacy_name] = copy.deepcopy(profile)

        return persisted, remaining_unmatched
    else:
        remaining_unmatched = {
            name: copy.deepcopy(profile)
            for name, profile in unmatched.items()
            if name not in persisted
        }
        return persisted, remaining_unmatched


class ConfigManager:
    """Manages persistent config with atomic writes, backup, and legacy migration."""

    def __init__(self, config_path: Optional[str] = None, backup_dir: Optional[str] = None):
        if config_path:
            self.config_path = config_path
            self.state_dir = os.path.dirname(os.path.abspath(config_path))
        else:
            self.state_dir = get_default_local_appdata_dir()
            self.config_path = os.path.join(self.state_dir, "config.json")

        if backup_dir:
            self.backup_dir = backup_dir
        else:
            self.backup_dir = os.path.join(self.state_dir, "backups")

        os.makedirs(self.backup_dir, exist_ok=True)
        self._config: Dict[str, Any] = copy.deepcopy(DEFAULT_CONFIG_V2)
        self._loaded: bool = False

    def get_config(self) -> Dict[str, Any]:
        return copy.deepcopy(self._config)

    def load_or_migrate(self, legacy_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Load existing schema v2 config or migrate from legacy v1 config.
        Never mutates or deletes the legacy file.
        """
        # 1. Try loading existing v2 config
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("schema_version") == 2:
                    self._config = validate_config_v2(data)
                    self._loaded = True
                    return self.get_config()
                else:
                    # Legacy content at v2 path
                    self._create_backup(data, prefix="config.v1.raw")
                    self._config = migrate_v1_to_v2(data)
                    self._loaded = True
                    self.save_config(self._config)
                    return self.get_config()
            except Exception:
                pass

        # 2. Look for legacy file if provided or in cwd/exe dir
        candidate_paths = []
        if legacy_path:
            candidate_paths.append(legacy_path)
        if getattr(sys, "frozen", False):
            candidate_paths.append(os.path.join(os.path.dirname(sys.executable), "config.json"))
        candidate_paths.append(os.path.join(os.getcwd(), "config.json"))

        for path in candidate_paths:
            if path and os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self._create_backup(data, prefix="config.v1")
                    self._config = migrate_v1_to_v2(data)
                    self._loaded = True
                    self.save_config(self._config)
                    return self.get_config()
                except Exception:
                    pass

        # 3. Use default config
        self._config = copy.deepcopy(DEFAULT_CONFIG_V2)
        self._loaded = True
        return self.get_config()

    def save_config(self, new_config: Dict[str, Any]) -> bool:
        """Atomically persist config to disk."""
        validated = validate_config_v2(new_config)
        if not validated.get("profiles") and self._config.get("profiles"):
            validated["profiles"] = copy.deepcopy(self._config["profiles"])
            if validated.get("active_profile") == "Default" and self._config.get("active_profile"):
                validated["active_profile"] = self._config.get("active_profile")
        if not self._loaded:
            baselines = None
            if not new_config.get("vendor_baselines"):
                if os.path.exists(self.config_path):
                    try:
                        with open(self.config_path, "r", encoding="utf-8") as f:
                            disk_data = json.load(f)
                        if isinstance(disk_data, dict) and disk_data.get("vendor_baselines"):
                            baselines = disk_data.get("vendor_baselines")
                    except Exception:
                        pass
                if not baselines and self._config.get("vendor_baselines"):
                    baselines = self._config.get("vendor_baselines")
            if baselines:
                validated["vendor_baselines"] = copy.deepcopy(baselines)
        else:
            if "vendor_baselines" not in new_config and self._config.get("vendor_baselines"):
                validated["vendor_baselines"] = copy.deepcopy(self._config["vendor_baselines"])
        temp_fd, temp_path = tempfile.mkstemp(
            prefix="config_", suffix=".tmp", dir=self.state_dir
        )
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                json.dump(validated, f, indent=4)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, self.config_path)
            self._config = validated
            self._loaded = True
            return True
        except Exception:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
            return False

    def _create_backup(self, data: Dict[str, Any], prefix: str = "config.bak") -> Optional[str]:
        """Write timestamped backup file."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"{prefix}.{timestamp}.json"
        backup_path = os.path.join(self.backup_dir, backup_filename)
        try:
            with open(backup_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            return backup_path
        except Exception:
            return None

    def save_profile(
        self,
        name: str,
        profile_data: Optional[Dict[str, Any]] = None,
        controller: Optional[Any] = None
    ) -> bool:
        """Save a named application profile into persistent config with atomic write and backup."""
        cfg = self.get_config()
        if profile_data is not None and isinstance(profile_data, dict):
            p = copy.deepcopy(profile_data)
        else:
            devs = copy.deepcopy(cfg.get("devices", {}))
            if controller is not None and hasattr(controller, "get_device_owner"):
                for dev_k, dev_v in devs.items():
                    if isinstance(dev_v, dict):
                        o = controller.get_device_owner(dev_k)
                        if o not in ("unknown", "ambiguous"):
                            dev_v["owner"] = o
            p = {
                "name": name,
                "created_at": datetime.datetime.now().isoformat(),
                "thermal": copy.deepcopy(cfg.get("thermal", {})),
                "behavior": copy.deepcopy(cfg.get("behavior", {})),
                "devices": devs,
                "last_applied": copy.deepcopy(cfg.get("last_applied", {})),
                "unmatched_legacy_profiles": copy.deepcopy(cfg.get("unmatched_legacy_profiles", {}))
            }
        p["name"] = name
        if "profiles" not in cfg or not isinstance(cfg["profiles"], dict):
            cfg["profiles"] = {}
        cfg["profiles"][name] = p
        cfg["active_profile"] = name
        return self.save_config(cfg)

    def load_profile(self, name: str) -> Optional[Dict[str, Any]]:
        """Retrieve named profile data without modifying active device runtime or config."""
        cfg = self.get_config()
        profiles = cfg.get("profiles", {})
        if isinstance(profiles, dict) and name in profiles:
            return copy.deepcopy(profiles[name])
        return None

    def list_profiles(self) -> List[str]:
        """Return names of all persisted application profiles."""
        cfg = self.get_config()
        profiles = cfg.get("profiles", {})
        if isinstance(profiles, dict):
            return list(profiles.keys())
        return []

    def delete_profile(self, name: str) -> bool:
        """Delete a saved application profile."""
        cfg = self.get_config()
        profiles = cfg.get("profiles", {})
        if isinstance(profiles, dict) and name in profiles:
            del profiles[name]
            cfg["profiles"] = profiles
            self._config["profiles"] = profiles
            if cfg.get("active_profile") == name:
                cfg["active_profile"] = "Default"
            return self.save_config(cfg)
        return False

    def apply_profile(self, name: str, controller: Optional[Any] = None) -> bool:
        """
        Explicitly apply a named profile to active config and runtime.
        Does not override devices currently held in reset or marked unmanaged.
        Canonical stable keys are persisted; ambiguous legacy names are retained in
        unmatched_legacy_profiles and never applied to duplicate hardware.
        """
        profile = self.load_profile(name)
        if profile is None:
            return False

        cfg = self.get_config()
        if "thermal" in profile and isinstance(profile["thermal"], dict):
            cfg["thermal"] = copy.deepcopy(profile["thermal"])
        if "behavior" in profile and isinstance(profile["behavior"], dict):
            cfg["behavior"] = copy.deepcopy(profile["behavior"])
        if "last_applied" in profile and isinstance(profile["last_applied"], dict):
            cfg["last_applied"] = copy.deepcopy(profile["last_applied"])
        cfg["active_profile"] = name

        profile_devs = profile.get("devices", {})
        if isinstance(profile_devs, dict):
            if controller is not None:
                for dev_name, dev_cfg in profile_devs.items():
                    target_key = dev_name
                    if hasattr(controller, "resolve_target_key"):
                        resolved = controller.resolve_target_key(dev_name)
                        if resolved:
                            target_key = resolved
                        else:
                            owner_status = (
                                controller.get_device_owner(dev_name)
                                if hasattr(controller, "get_device_owner")
                                else "unknown"
                            )
                            if owner_status == "ambiguous":
                                cfg.setdefault("unmatched_legacy_profiles", {})[dev_name] = copy.deepcopy(dev_cfg)
                                continue

                    is_reset = False
                    if hasattr(controller, "is_device_reset"):
                        is_reset = controller.is_device_reset(target_key)
                    current_owner = None
                    if hasattr(controller, "get_device_owner"):
                        current_owner = controller.get_device_owner(target_key)

                    if is_reset or current_owner in ("resetting", "unmanaged"):
                        continue

                    cfg.setdefault("devices", {})[target_key] = copy.deepcopy(dev_cfg)
                    if dev_name != target_key and dev_name in cfg.get("devices", {}):
                        del cfg["devices"][dev_name]

                    new_owner = dev_cfg.get("owner")
                    if new_owner and hasattr(controller, "set_device_owner"):
                        controller.set_device_owner(target_key, new_owner)
            else:
                cfg["devices"] = copy.deepcopy(profile_devs)

        return self.save_config(cfg)
    def capture_vendor_baseline(
        self,
        name: Optional[str] = None,
        baseline: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Save a named or timestamped vendor baseline snapshot without overwriting thermal/device profiles.
        Stored under canonical stable keys.
        """
        if baseline is None:
            baseline = {}
        if not name:
            name = datetime.datetime.now().strftime("baseline_%Y%m%d_%H%M%S")

        cfg = self.get_config()
        if "vendor_baselines" not in cfg or not isinstance(cfg["vendor_baselines"], dict):
            cfg["vendor_baselines"] = {}

        if isinstance(baseline, dict) and "devices" in baseline and isinstance(baseline["devices"], dict):
            devices = copy.deepcopy(baseline["devices"])
        else:
            devices = copy.deepcopy(baseline)

        entry: Dict[str, Any] = {
            "name": name,
            "captured_at": datetime.datetime.now().isoformat(),
            "devices": devices,
        }
        if isinstance(baseline, dict):
            for k, v in baseline.items():
                if k not in entry:
                    entry[k] = copy.deepcopy(v)

        cfg["vendor_baselines"][name] = entry
        return self.save_config(cfg)

    def get_vendor_baseline(self, name: str) -> Optional[Dict[str, Any]]:
        """Retrieve named vendor baseline data without modifying active device runtime or config."""
        cfg = self.get_config()
        baselines = cfg.get("vendor_baselines", {})
        if isinstance(baselines, dict) and name in baselines:
            return copy.deepcopy(baselines[name])
        return None

    def list_vendor_baselines(self) -> List[str]:
        """Return list of saved vendor baseline snapshot names."""
        cfg = self.get_config()
        baselines = cfg.get("vendor_baselines", {})
        if isinstance(baselines, dict):
            return list(baselines.keys())
        return []

    def delete_vendor_baseline(self, name: str) -> bool:
        """Delete a saved vendor baseline snapshot."""
        cfg = self.get_config()
        baselines = cfg.get("vendor_baselines", {})
        if isinstance(baselines, dict) and name in baselines:
            del baselines[name]
            cfg["vendor_baselines"] = baselines
            self._config["vendor_baselines"] = baselines
            return self.save_config(cfg)
        return False
