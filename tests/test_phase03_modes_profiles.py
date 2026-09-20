import os
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from openrgb_temp_sync.openrgb_runtime import (
    DeviceDescriptor,
    EngineState,
    ModeDescriptor,
    OpenRGBSupervisor,
    WriteResult,
    ZoneDescriptor,
)
from openrgb_temp_sync.controller import ControllerState, SyncController
from openrgb_temp_sync.config import ConfigManager, DEFAULT_CONFIG_V2, validate_config_v2
from openrgb_temp_sync.sensor_runtime import SensorReading, SensorStatus, SensorSupervisor
from openrgb_temp_sync.ui_model import UIModel


class MockSDKMode:
    def __init__(
        self,
        name,
        flags=0,
        speed_min=None,
        speed_max=None,
        speed=None,
        brightness_min=None,
        brightness_max=None,
        brightness=None,
        colors_min=None,
        colors_max=None,
        color_mode=None,
        direction=None,
        value=0,
    ):
        self.name = name
        self.flags = flags
        self.speed_min = speed_min
        self.speed_max = speed_max
        self.speed = speed
        self.brightness_min = brightness_min
        self.brightness_max = brightness_max
        self.brightness = brightness
        self.colors_min = colors_min
        self.colors_max = colors_max
        self.color_mode = color_mode
        self.direction = direction
        self.value = value


class MockSDKDevice:
    def __init__(self, name, modes=None, leds=None, zones=None, **metadata):
        self.name = name
        self.modes = modes or []
        self.leds = leds or []
        self.zones = zones or []
        self.colors = []
        for k, v in metadata.items():
            setattr(self, k, v)
        self.active_mode = 0 if self.modes else None
        self.mode_applied = None
        self.colors_applied = None
        self.save_called = False

    def set_mode(self, mode, save=False):
        if isinstance(mode, int):
            self.active_mode = mode
            self.mode_applied = self.modes[mode].name if mode < len(self.modes) else str(mode)
        elif hasattr(mode, "name"):
            self.mode_applied = mode.name
            for idx, m in enumerate(self.modes):
                if m.name.lower() == mode.name.lower():
                    self.active_mode = idx
                    break
        else:
            self.mode_applied = str(mode)
            for idx, m in enumerate(self.modes):
                if m.name.lower() == str(mode).lower():
                    self.active_mode = idx
                    break
        if save:
            self.save_called = True

    def save_mode(self):
        self.save_called = True

    def set_colors(self, colors, fast=True):
        self.colors_applied = colors


class TestPhase03ModesAndProfiles(unittest.TestCase):
    def test_mode_descriptor_normalization_and_flags(self):
        supervisor = OpenRGBSupervisor(binary_path=None)
        # 1 = HAS_SPEED, 16 = HAS_BRIGHTNESS, 2 = HAS_DIRECTION_LR, 32 = HAS_PER_LED_COLOR, 256 = manual_save
        rainbow_mode = MockSDKMode(
            "Rainbow Wave",
            flags=1 | 16 | 2 | 256,
            speed_min=1,
            speed_max=10,
            speed=5,
            brightness_min=0,
            brightness_max=100,
            brightness=80,
            direction=0,
        )
        direct_mode = MockSDKMode("Direct", flags=32)
        static_mode = MockSDKMode("Static", flags=16 | 64)

        dev = MockSDKDevice("GPU Device", modes=[rainbow_mode, direct_mode, static_mode])
        descs = supervisor.refresh_inventory([dev])
        self.assertEqual(len(descs), 1)
        device_desc = descs[0]
        self.assertEqual(len(device_desc.modes), 3)

        rb_desc = device_desc.modes[0]
        self.assertEqual(rb_desc.name, "Rainbow Wave")
        self.assertTrue(rb_desc.supports_speed)
        self.assertTrue(rb_desc.supports_brightness)
        self.assertTrue(rb_desc.supports_direction)
        self.assertFalse(rb_desc.supports_per_led)
        self.assertTrue(rb_desc.supports_manual_save)
        self.assertEqual(rb_desc.speed_min, 1)
        self.assertEqual(rb_desc.speed_max, 10)

        dir_desc = device_desc.modes[1]
        self.assertEqual(dir_desc.name, "Direct")
        self.assertTrue(dir_desc.supports_per_led)
        self.assertFalse(dir_desc.supports_speed)
        self.assertFalse(dir_desc.supports_manual_save)

    def test_mode_normalization_handles_partial_data_and_missing_flags(self):
        supervisor = OpenRGBSupervisor(binary_path=None)
        broken_mode = object()  # completely bare object
        dev = MockSDKDevice("Partial Device", modes=[broken_mode])
        descs = supervisor.refresh_inventory([dev])
        self.assertEqual(len(descs), 1)
        m = descs[0].modes[0]
        self.assertFalse(m.supports_speed)
        self.assertFalse(m.supports_brightness)
        self.assertFalse(m.supports_manual_save)

    def test_supervisor_set_mode_with_parameters_and_structured_result(self):
        supervisor = OpenRGBSupervisor(binary_path=None)
        rainbow_mode = MockSDKMode("Rainbow", flags=1 | 16 | 256, speed_min=1, speed_max=10)
        direct_mode = MockSDKMode("Direct", flags=32)
        dev = MockSDKDevice("MSI GPU", modes=[rainbow_mode, direct_mode])
        supervisor.refresh_inventory([dev])

        res = supervisor.set_mode("MSI GPU", "Rainbow", speed=7, brightness=50)
        self.assertIsInstance(res, WriteResult)
        self.assertTrue(res.ok)
        self.assertEqual(dev.mode_applied, "Rainbow")

        # Unsupported parameter: speed on Direct mode
        res_bad = supervisor.set_mode("MSI GPU", "Direct", speed=5)
        self.assertFalse(res_bad.ok)
        self.assertEqual(res_bad.error_code, "unsupported_parameter")

    def test_save_to_device_explicit_and_gated_by_capability(self):
        supervisor = OpenRGBSupervisor(binary_path=None)
        saveable_mode = MockSDKMode("Breathing", flags=16 | 256)  # 256 = manual_save
        unsaveable_mode = MockSDKMode("Direct", flags=32)
        dev = MockSDKDevice("Keyboard", modes=[saveable_mode, unsaveable_mode])
        supervisor.refresh_inventory([dev])

        # Setting unsaveable mode with save=True must be rejected
        res = supervisor.set_mode("Keyboard", "Direct", save=True)
        self.assertFalse(res.ok)
        self.assertEqual(res.error_code, "save_unsupported")
        self.assertFalse(dev.save_called)

        # Setting saveable mode with save=True succeeds
        res_ok = supervisor.set_mode("Keyboard", "Breathing", save=True)
        self.assertTrue(res_ok.ok)
        self.assertTrue(dev.save_called)

    def test_hardware_mode_quiesces_thermal_frames_and_resume_negotiates_direct(self):
        supervisor = OpenRGBSupervisor(binary_path=None)
        dev_msi = MockSDKDevice("MSI B550", modes=[MockSDKMode("Direct", flags=32), MockSDKMode("Rainbow", flags=1)])
        dev_gpu = MockSDKDevice("GPU Device", modes=[MockSDKMode("Direct", flags=32), MockSDKMode("Wave", flags=1)])
        dev_ram = MockSDKDevice("ENE DRAM", modes=[MockSDKMode("Direct", flags=32), MockSDKMode("Static", flags=16)])

        supervisor.refresh_inventory([dev_msi, dev_gpu, dev_ram])
        controller = SyncController(openrgb_supervisor=supervisor)

        # Assign GPU to hardware effect, RAM to manual direct, MSI to thermal
        controller.set_device_owner("GPU Device", "hardware_mode")
        controller.set_device_owner("ENE DRAM", "manual_direct")
        controller.set_device_owner("MSI B550", "thermal_direct")

        self.assertFalse(controller.can_apply_thermal_frame("GPU Device"))
        self.assertFalse(controller.can_apply_thermal_frame("ENE DRAM"))
        self.assertTrue(controller.can_apply_thermal_frame("MSI B550"))

        # Resume GPU device to thermal sync
        controller.resume_device("GPU Device")
        self.assertEqual(controller.get_device_owner("GPU Device"), "thermal_direct")
        self.assertTrue(controller.can_apply_thermal_frame("GPU Device"))
        self.assertEqual(dev_gpu.mode_applied, "Direct")

    def test_missing_gpu_sensor_does_not_silently_remap_to_cpu(self):
        supervisor = OpenRGBSupervisor(binary_path=None)
        dev_gpu = MockSDKDevice("GPU Device", modes=[MockSDKMode("Direct", flags=32)])
        supervisor.refresh_inventory([dev_gpu])

        cfg_mgr = ConfigManager()
        cfg = cfg_mgr.get_config()
        cfg["devices"]["GPU Device"] = {"default_source": "gpu", "led_brightness": {}, "temp_source": {}}
        cfg_mgr.save_config(cfg)

        controller = SyncController(config_manager=cfg_mgr, openrgb_supervisor=supervisor)
        controller.smoothed_cpu_temp = 70.0
        controller.smoothed_gpu_temp = None  # Missing GPU sensor

        # When GPU sensor is missing, thermal frame dispatch should NOT write colors computed from CPU temp
        dev_gpu.colors_applied = None
        controller._dispatch_thermal_frame()
        self.assertIsNone(dev_gpu.colors_applied)

    def test_missing_cpu_does_not_block_gpu_only_thermal(self):
        supervisor = OpenRGBSupervisor(binary_path=None)
        dev_gpu = MockSDKDevice("GPU Device", modes=[MockSDKMode("Direct", flags=32)])
        supervisor.refresh_inventory([dev_gpu])

        cfg_mgr = ConfigManager()
        cfg = cfg_mgr.get_config()
        cfg["devices"]["GPU Device"] = {"default_source": "gpu", "led_brightness": {}, "temp_source": {}}
        cfg_mgr.save_config(cfg)

        controller = SyncController(config_manager=cfg_mgr, openrgb_supervisor=supervisor)
        controller.smoothed_cpu_temp = None  # Missing CPU sensor
        controller.smoothed_gpu_temp = 65.0  # GPU sensor available

        dev_gpu.colors_applied = None
        controller._dispatch_thermal_frame()
        # GPU device must receive colors calculated from GPU temp
        self.assertIsNotNone(dev_gpu.colors_applied)

    def test_stale_sensor_degrades_thermal_without_altering_manual_or_effect_devices(self):
        supervisor = OpenRGBSupervisor(binary_path=None)
        dev_effect = MockSDKDevice("GPU Device", modes=[MockSDKMode("Wave", flags=1)])
        dev_manual = MockSDKDevice("ENE DRAM", modes=[MockSDKMode("Direct", flags=32)])
        dev_thermal = MockSDKDevice("MSI B550", modes=[MockSDKMode("Direct", flags=32)])
        supervisor.refresh_inventory([dev_effect, dev_manual, dev_thermal])

        controller = SyncController(openrgb_supervisor=supervisor)
        controller.set_device_owner("GPU Device", "hardware_mode")
        controller.set_device_owner("ENE DRAM", "manual_direct")
        controller.set_device_owner("MSI B550", "thermal_direct")

        # Mock sensor supervisor reporting STALE
        controller.sensor_supervisor.get_status = lambda: SensorStatus.STALE

        # Sensor check fails
        allowed = controller._sensor_allows_updates()
        self.assertFalse(allowed)
        self.assertEqual(controller.state, ControllerState.DEGRADED_SENSOR)

        # Device ownerships must NOT be altered or wiped
        self.assertEqual(controller.get_device_owner("GPU Device"), "hardware_mode")
        self.assertEqual(controller.get_device_owner("ENE DRAM"), "manual_direct")
        self.assertEqual(controller.get_device_owner("MSI B550"), "thermal_direct")

    def test_app_profiles_save_load_and_migration(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg_path = os.path.join(temp_dir, "config.json")
            cfg_mgr = ConfigManager(config_path=cfg_path)

            cfg = cfg_mgr.get_config()
            cfg["devices"]["MSI B550"] = {"owner": "thermal_direct", "default_source": "cpu"}
            cfg["devices"]["GPU Device"] = {"owner": "hardware_mode", "mode": "Wave"}
            cfg_mgr.save_config(cfg)

            # Save named profile
            self.assertTrue(cfg_mgr.save_profile("Gaming_Profile"))
            profiles = cfg_mgr.list_profiles()
            self.assertIn("Gaming_Profile", profiles)

            # Modify current config
            cfg["devices"]["MSI B550"]["owner"] = "manual_direct"
            cfg_mgr.save_config(cfg)

            # Loading profile retrieves saved settings without automatically overriding active config
            loaded = cfg_mgr.load_profile("Gaming_Profile")
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["devices"]["MSI B550"]["owner"], "thermal_direct")

            # Verify unmanaged devices are not overwritten when profile is applied
            controller = SyncController(config_manager=cfg_mgr)
            controller.set_device_owner("Unmanaged Dev", "unmanaged")
            controller.reset_device_to_original = lambda name: True
            controller._manual_reset_devices.add("Reset Dev")

            # Applying profile respects unmanaged and resetting devices
            applied = cfg_mgr.apply_profile("Gaming_Profile", controller=controller)
            self.assertTrue(applied)
            self.assertEqual(controller.get_device_owner("Unmanaged Dev"), "unmanaged")
            self.assertTrue(controller.is_device_reset("Reset Dev"))



    def test_readback_mismatch_surfaced(self):
        supervisor = OpenRGBSupervisor(binary_path=None)
        mode1 = MockSDKMode("Static", flags=16)
        mode2 = MockSDKMode("Breathing", flags=1)
        dev = MockSDKDevice("Stub Device", modes=[mode1, mode2])
        supervisor.refresh_inventory([dev])

        # Force device to ignore mode change
        dev.set_mode = lambda m, save=False: None
        dev.active_mode = 0  # remains Static

        res = supervisor.set_mode("Stub Device", "Breathing")
        self.assertFalse(res.ok)
        self.assertEqual(res.error_code, "readback_mismatch")

    def test_save_to_device_write_failure_surfaced(self):
        supervisor = OpenRGBSupervisor(binary_path=None)
        mode = MockSDKMode("Static", flags=16 | 256)
        dev = MockSDKDevice("Faulty Device", modes=[mode])
        supervisor.refresh_inventory([dev])

        def failing_save():
            raise IOError("EEPROM I2C NACK")

        dev.save_mode = failing_save
        res = supervisor.save_device_mode("Faulty Device")
        self.assertFalse(res.ok)
        self.assertEqual(res.error_code, "save_failed")
        self.assertIn("EEPROM", res.message)

    def test_unknown_device_and_zone_counts_retained_in_profiles(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg_path = os.path.join(temp_dir, "config.json")
            cfg_mgr = ConfigManager(config_path=cfg_path)

            cfg = cfg_mgr.get_config()
            cfg["devices"]["Unknown Controller"] = {
                "owner": "manual_direct",
                "zone_led_counts": {"Zone 1": 24}
            }
            cfg["devices"]["ENE DRAM (RAM A)"] = {
                "owner": "thermal_direct",
                "zone_led_counts": {"DRAM Zone": 8}
            }
            cfg["devices"]["ENE DRAM (RAM B)"] = {
                "owner": "hardware_mode",
                "zone_led_counts": {"DRAM Zone": 8}
            }
            cfg_mgr.save_config(cfg)

            self.assertTrue(cfg_mgr.save_profile("DualRAM_Custom"))
            loaded = cfg_mgr.load_profile("DualRAM_Custom")

            self.assertIn("Unknown Controller", loaded["devices"])
            self.assertEqual(loaded["devices"]["Unknown Controller"]["zone_led_counts"]["Zone 1"], 24)
            self.assertEqual(loaded["devices"]["ENE DRAM (RAM A)"]["owner"], "thermal_direct")
            self.assertEqual(loaded["devices"]["ENE DRAM (RAM B)"]["owner"], "hardware_mode")

    def test_ui_model_mode_capabilities_and_owner_labels(self):
        mode = ModeDescriptor(
            name="Rainbow Wave",
            flags=("brightness", "direction_lr", "manual_save", "speed"),
            speed_min=1,
            speed_max=10,
            brightness_min=0,
            brightness_max=100,
            directions_supported=("left", "right")
        )
        caps = UIModel.get_mode_capabilities(mode)
        self.assertTrue(caps["supports_speed"])
        self.assertTrue(caps["supports_brightness"])
        self.assertTrue(caps["supports_direction"])
        self.assertTrue(caps["supports_save"])
        self.assertEqual(caps["speed_range"], (1, 10))
        self.assertEqual(caps["directions"], ["left", "right"])
        self.assertIsNone(caps["reasons"]["speed"])

        # Unsupported mode
        direct_mode = ModeDescriptor(name="Direct", flags=("per_led",))
        dir_caps = UIModel.get_mode_capabilities(direct_mode)
        self.assertFalse(dir_caps["supports_speed"])
        self.assertIsNotNone(dir_caps["reasons"]["speed"])
        self.assertFalse(dir_caps["supports_save"])
        self.assertIsNotNone(dir_caps["reasons"]["save"])

        # Owner labels
        self.assertEqual(UIModel.format_device_owner_label("thermal_direct"), "Temperature Sync (Direct)")
        self.assertEqual(UIModel.format_device_owner_label("manual_direct"), "Manual Color (Direct)")
        self.assertEqual(UIModel.format_device_owner_label("hardware_mode", "Wave"), "Hardware Effect (Wave)")
        self.assertEqual(UIModel.format_device_owner_label("resetting"), "Restored Pre-Sync Snapshot (Held)")
        self.assertEqual(UIModel.format_device_owner_label("unmanaged"), "Unmanaged")

    def test_repeated_mode_transitions_maintain_owner_integrity(self):
        supervisor = OpenRGBSupervisor(binary_path=None)
        dev = MockSDKDevice("MSI B550", modes=[MockSDKMode("Direct", flags=32), MockSDKMode("Breathing", flags=1 | 16)])
        supervisor.refresh_inventory([dev])
        controller = SyncController(openrgb_supervisor=supervisor)

        # 1. Thermal direct by default
        self.assertEqual(controller.get_device_owner("MSI B550"), "thermal_direct")

        # 2. Switch to manual direct
        controller.set_device_owner("MSI B550", "manual_direct")
        self.assertEqual(controller.get_device_owner("MSI B550"), "manual_direct")
        self.assertFalse(controller.can_apply_thermal_frame("MSI B550"))

        # 3. Switch to hardware effect
        res = controller.set_device_hardware_mode("MSI B550", "Breathing", speed=5)
        self.assertTrue(res.ok)
        self.assertEqual(controller.get_device_owner("MSI B550"), "hardware_mode")
        self.assertFalse(controller.can_apply_thermal_frame("MSI B550"))

        # 4. Resume to thermal sync
        controller.resume_device("MSI B550")
        self.assertEqual(controller.get_device_owner("MSI B550"), "thermal_direct")
        self.assertTrue(controller.can_apply_thermal_frame("MSI B550"))
        self.assertEqual(dev.mode_applied, "Direct")


if __name__ == "__main__":
    unittest.main()
