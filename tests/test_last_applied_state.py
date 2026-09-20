import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from openrgb_temp_sync.config import ConfigManager
from openrgb_temp_sync.controller import SyncController
from openrgb_temp_sync.openrgb_runtime import EngineState, WriteResult


class Mode:
    def __init__(self, name):
        self.name = name


class Device:
    def __init__(self, name):
        self.name = name
        self.modes = [Mode("Direct"), Mode("Rainbow")]
        self.active_mode = 1
        self.mode_applied = None
        self.colors_applied = None

    def set_mode(self, mode, save=False):
        name = getattr(mode, "name", str(mode))
        self.mode_applied = name
        self.active_mode = next((i for i, m in enumerate(self.modes) if m.name == name), self.active_mode)


class Supervisor:
    def __init__(self, devices):
        self.devices = devices
        self.state = EngineState.STOPPED
        self.status_message = "Stopped"
        self.mode_calls = []
        self.color_calls = []

    def start(self):
        self.state = EngineState.RUNNING_OWNED
        self.status_message = "Running"
        return self.state, self.status_message

    def stop(self):
        self.state = EngineState.STOPPED

    def get_devices(self):
        return self.devices

    def get_descriptors(self):
        from openrgb_temp_sync.openrgb_runtime import DeviceDescriptor
        return [DeviceDescriptor(key=d.name, stable_key=d.name, name=d.name, display_name=d.name, session_index=i)
                for i, d in enumerate(self.devices)]

    def set_device_mode(self, target_key, mode_name):
        self.mode_calls.append((target_key, mode_name))
        device = next(d for d in self.devices if d.name == target_key)
        device.set_mode(mode_name)
        return True

    def set_mode(self, target_key, mode_name, **kwargs):
        device = next(d for d in self.devices if d.name == target_key)
        device.set_mode(mode_name)
        return WriteResult(ok=True, target_key=target_key, operation="set_mode")

    def set_colors(self, target_key, colors, fast=True):
        self.color_calls.append((target_key, colors))
        device = next(d for d in self.devices if d.name == target_key)
        device.colors_applied = colors
        return WriteResult(ok=True, target_key=target_key, operation="set_colors")


class Sensor:
    def start(self):
        pass

    def stop(self):
        pass

    def get_status(self):
        return "OK"

    def get_latest_reading(self):
        return None

    def get_recent_stderr(self):
        return []


class TestLastAppliedState(unittest.TestCase):
    def test_last_applied_state_survives_config_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = ConfigManager(config_path=os.path.join(tmp, "config.json"))
            cfg = manager.get_config()
            cfg["last_applied"] = {
                "mode": "hardware_effect",
                "devices": {
                    "GPU Device": {
                        "mode": "hardware_effect",
                        "mode_name": "Rainbow",
                        "speed": 7,
                    }
                },
            }
            self.assertTrue(manager.save_config(cfg))

            reloaded = ConfigManager(config_path=os.path.join(tmp, "config.json"))
            reloaded.load_or_migrate()
            self.assertEqual(reloaded.get_config()["last_applied"]["mode"], "hardware_effect")
            self.assertEqual(
                reloaded.get_config()["last_applied"]["devices"]["GPU Device"]["mode_name"],
                "Rainbow",
            )

    def test_start_restores_last_temperature_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = ConfigManager(config_path=os.path.join(tmp, "config.json"))
            cfg = manager.get_config()
            cfg["last_applied"] = {
                "mode": "temperature",
                "devices": {"GPU Device": {"mode": "temperature"}},
            }
            manager.save_config(cfg)
            device = Device("GPU Device")
            supervisor = Supervisor([device])
            controller = SyncController(manager, supervisor, Sensor())

            controller.start()
            controller.stop()

            self.assertIn(("GPU Device", "Direct"), supervisor.mode_calls)
            self.assertEqual(controller.get_device_owner("GPU Device"), "thermal_direct")

    def test_start_restores_last_manual_colors(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = ConfigManager(config_path=os.path.join(tmp, "config.json"))
            cfg = manager.get_config()
            cfg["last_applied"] = {
                "mode": "manual",
                "devices": {
                    "GPU Device": {
                        "mode": "manual",
                        "colors": [[1, 2, 3]],
                    }
                },
            }
            manager.save_config(cfg)
            device = Device("GPU Device")
            supervisor = Supervisor([device])
            controller = SyncController(manager, supervisor, Sensor())

            controller.start()
            controller.stop()

            self.assertIn(("GPU Device", "Direct"), supervisor.mode_calls)
            self.assertEqual(controller.get_device_owner("GPU Device"), "manual_direct")
            self.assertEqual([(c.red, c.green, c.blue) for c in device.colors_applied], [(1, 2, 3)])

    def test_start_restores_last_hardware_effect(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = ConfigManager(config_path=os.path.join(tmp, "config.json"))
            cfg = manager.get_config()
            cfg["last_applied"] = {
                "mode": "hardware_effect",
                "devices": {
                    "GPU Device": {
                        "mode": "hardware_effect",
                        "mode_name": "Rainbow",
                        "speed": 7,
                    }
                },
            }
            manager.save_config(cfg)
            device = Device("GPU Device")
            supervisor = Supervisor([device])
            controller = SyncController(manager, supervisor, Sensor())

            controller.start()
            controller.stop()

            self.assertEqual(device.mode_applied, "Rainbow")
            self.assertEqual(controller.get_device_owner("GPU Device"), "hardware_mode")

    def test_remembering_one_device_keeps_temperature_state_for_other_devices(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = ConfigManager(config_path=os.path.join(tmp, "config.json"))
            gpu = Device("GPU Device")
            ram = Device("ENE DRAM A")
            supervisor = Supervisor([gpu, ram])
            controller = SyncController(manager, supervisor, Sensor())

            self.assertTrue(controller.remember_last_applied("hardware_effect", "GPU Device", mode_name="Rainbow"))
            saved = manager.get_config()["last_applied"]["devices"]
            self.assertEqual(saved["GPU Device"]["mode"], "hardware_effect")
            self.assertEqual(saved["ENE DRAM A"]["mode"], "temperature")

    def test_vendor_default_state_is_not_overwritten_on_startup(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = ConfigManager(config_path=os.path.join(tmp, "config.json"))
            cfg = manager.get_config()
            cfg["last_applied"] = {
                "mode": "vendor_default",
                "devices": {"GPU Device": {"mode": "vendor_default"}},
            }
            manager.save_config(cfg)
            device = Device("GPU Device")
            supervisor = Supervisor([device])
            controller = SyncController(manager, supervisor, Sensor())

            controller.start()
            controller.stop()

            self.assertIsNone(device.mode_applied)
            self.assertFalse(controller.can_apply_thermal_frame("GPU Device"))


if __name__ == "__main__":
    unittest.main()
