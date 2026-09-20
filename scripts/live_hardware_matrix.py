"""Run a reversible OpenRGB mode/color matrix against the local SDK server."""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from openrgb_temp_sync.config import ConfigManager
from openrgb_temp_sync.openrgb_runtime import EngineState, OpenRGBSupervisor


# The RTX 3060 controller advertises Pulse, but its firmware rejects the
# Pulse packet and immediately reports Direct.  Keep it visible in the report
# as an attempted/unsupported mode instead of hiding it as a pass.
KNOWN_HARDWARE_UNSUPPORTED = {
    ("Gigabyte AORUS GeForce RTX 3060 ELITE LHR", "Pulse"),
}


def active_mode_name(device: Any) -> str:
    active = getattr(device, "active_mode", None)
    modes = getattr(device, "modes", []) or []
    if isinstance(active, int) and 0 <= active < len(modes):
        return str(getattr(modes[active], "name", ""))
    return str(getattr(active, "name", active or ""))


def main() -> int:
    config = ConfigManager()
    config.load_or_migrate()
    persisted = config.get_vendor_baseline("vendor_default") or {}
    persisted_devices = persisted.get("devices", {}) if isinstance(persisted, dict) else {}

    supervisor = OpenRGBSupervisor(binary_path=None)
    state, message = supervisor.start()
    report: dict[str, Any] = {
        "engine_state": state,
        "engine_message": message,
        "inventory": [],
        "mode_tests": [],
        "color_tests": [],
        "restore_tests": [],
    }

    if state != EngineState.RUNNING_EXTERNAL:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 2

    descriptors = supervisor.get_descriptors()
    report["inventory"] = [
        {
            "name": desc.name,
            "stable_key": desc.stable_key,
            "zones": [{"name": zone.name, "leds": zone.led_count} for zone in desc.zones],
            "mode_count": len(desc.modes),
        }
        for desc in descriptors
    ]

    for desc in descriptors:
        target = desc.stable_key or desc.key
        device = supervisor._find_device(target)
        for mode in desc.modes:
            started = time.monotonic()
            try:
                if mode.name.strip().lower() == "direct":
                    ok = bool(supervisor.set_device_mode(target, mode.name))
                    error = "" if ok else "set_device_mode returned false"
                else:
                    result = supervisor.set_mode(target, mode.name)
                    ok = bool(result)
                    error = result.message if not ok else ""
                readback = active_mode_name(device)
                readback_ok = readback.strip().lower() == mode.name.strip().lower()
                report["mode_tests"].append(
                    {
                        "device": desc.name,
                        "mode": mode.name,
                        "ok": ok and readback_ok,
                        "unsupported": (not (ok and readback_ok)
                                        and (desc.name, mode.name) in KNOWN_HARDWARE_UNSUPPORTED),
                        "write_ok": ok,
                        "readback": readback,
                        "readback_ok": readback_ok,
                        "error": error,
                        "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
                    }
                )
            except Exception as exc:  # hardware matrix must continue to capture all failures
                report["mode_tests"].append(
                    {
                        "device": desc.name,
                        "mode": mode.name,
                        "ok": False,
                        "unsupported": (desc.name, mode.name) in KNOWN_HARDWARE_UNSUPPORTED,
                        "write_ok": False,
                        "readback": active_mode_name(device),
                        "readback_ok": False,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

        try:
            device = supervisor._find_device(target)
            from openrgb.utils import RGBColor

            # A mode matrix ends on the last advertised hardware effect.  A
            # per-LED color write is only meaningful in Direct mode, so make
            # the same transition the UI makes before validating readback.
            direct_ok = supervisor.set_device_mode(target, "Direct")
            colors = [RGBColor(255, 0, 0)] * len(getattr(device, "colors", []) or [])
            result = supervisor.set_colors(target, colors, fast=True) if colors else None
            report["color_tests"].append(
                {
                    "device": desc.name,
                    "ok": bool(direct_ok and result) if result is not None else False,
                    "direct_mode_ok": bool(direct_ok),
                    "error": ("could not enter Direct mode" if not direct_ok
                              else ("" if result is None or result.ok else result.message)),
                    "led_count": len(colors),
                }
            )
        except Exception as exc:
            report["color_tests"].append(
                {"device": desc.name, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
            )

    for desc in descriptors:
        target = desc.stable_key or desc.key
        entry = persisted_devices.get(target)
        if entry is None:
            entry = next(
                (
                    value
                    for value in persisted_devices.values()
                    if isinstance(value, dict) and value.get("stable_key") == target
                ),
                None,
            )
        if entry is None:
            report["restore_tests"].append({"device": desc.name, "ok": False, "error": "baseline missing"})
            continue
        try:
            ok = supervisor.restore_device_from_baseline(target, entry)
            device = supervisor._find_device(target)
            report["restore_tests"].append(
                {
                    "device": desc.name,
                    "ok": bool(ok),
                    "mode": active_mode_name(device),
                    "zones": [len(zone.leds) for zone in getattr(device, "zones", []) or []],
                }
            )
        except Exception as exc:
            report["restore_tests"].append(
                {"device": desc.name, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
            )

    report["summary"] = {
        "device_count": len(report["inventory"]),
        "mode_total": len(report["mode_tests"]),
        "mode_pass": sum(1 for item in report["mode_tests"] if item["ok"]),
        "mode_unsupported": sum(1 for item in report["mode_tests"] if item.get("unsupported")),
        "mode_fail": sum(1 for item in report["mode_tests"] if not item["ok"] and not item.get("unsupported")),
        "color_total": len(report["color_tests"]),
        "color_pass": sum(1 for item in report["color_tests"] if item["ok"]),
        "restore_total": len(report["restore_tests"]),
        "restore_pass": sum(1 for item in report["restore_tests"] if item["ok"]),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    supervisor.stop()
    return 0 if (
        report["summary"]["device_count"] == 4
        and report["summary"]["mode_fail"] == 0
        and report["summary"]["color_pass"] == report["summary"]["color_total"]
        and report["summary"]["restore_pass"] == report["summary"]["restore_total"]
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
