import unittest
import sys
import os
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from openrgb_temp_sync.openrgb_runtime import (
    DeviceDescriptor,
    ZoneDescriptor,
    WriteResult,
    EngineState
)
from openrgb_temp_sync.config import ConfigManager
from openrgb_temp_sync.ui import SettingsGUI


class DummyDevice:
    def __init__(self, name, leds=None, zones=None, modes=None, active_mode=0):
        self.name = name
        self.leds = leds or []
        self.zones = zones or []
        self.colors = [(0, 0, 0)] * len(self.leds)
        self.modes = modes or []
        self.active_mode = active_mode

    def set_colors(self, colors, fast=True):
        self.colors = list(colors)


class DummyZone:
    def __init__(self, name, count, minimum=0, maximum=100, resizable=True):
        self.name = name
        self.leds = [object() for _ in range(count)]
        self.minimum = minimum
        self.maximum = maximum
        if resizable:
            self.resize = lambda s: setattr(self, "leds", [object() for _ in range(s)])


class MockSupervisor:
    def __init__(self, descriptors=None, devices=None):
        self._descriptors = descriptors or []
        self._devices = devices or []
        self.colors_set = []
        self.resized = []
        self.direct_mode_calls = []

    def get_reset_capability(self, target_key):
        class Cap:
            def __init__(self, s, r): self.status = s; self.reason = r
        if "MSI" in target_key or "ENE" in target_key or "Gigabyte" in target_key:
            return Cap("unverified", "Known risk path")
        elif "verified_device" in target_key:
            return Cap("verified", "Supported path")
        return Cap("unsupported", "Not supported")

    def get_descriptors(self):
        return list(self._descriptors)

    def get_devices(self):
        return list(self._devices)

    def _find_device(self, key):
        for dev in self._devices:
            if getattr(dev, "name", "") == key:
                return dev
        for desc, dev in zip(self._descriptors, self._devices):
            if desc.key == key:
                return dev
        return None

    def set_colors(self, target_key, colors, fast=True):
        self.colors_set.append((target_key, colors))
        return WriteResult(ok=True, target_key=target_key, operation="set_colors")

    def set_device_mode(self, target_key, mode_name):
        self.direct_mode_calls.append((target_key, mode_name))
        for index, dev in enumerate(self._devices):
            descriptor_match = index < len(self._descriptors) and self._descriptors[index].key == target_key
            if (getattr(dev, "name", "") == target_key or descriptor_match) and getattr(dev, "modes", None):
                for index, mode in enumerate(dev.modes):
                    if getattr(mode, "name", "").lower() == mode_name.lower():
                        dev.active_mode = index
                        return True
        return False

    def resize_zone(self, target_key, zone_index, size):
        self.resized.append((target_key, zone_index, size))
        return True

    def refresh_inventory(self):
        return self._descriptors


class MockController:
    def __init__(self, supervisor=None):
        self.openrgb_supervisor = supervisor or MockSupervisor()
        self.running = True
        self.owners = {}

    def get_status_snapshot(self):
        return {
            "engine_label": "MockEngine",
            "status_text": "Connected",
            "device_count": len(self.openrgb_supervisor.get_descriptors()),
            "devices": [d.name for d in self.openrgb_supervisor.get_descriptors()]
        }

    def get_devices(self):
        return self.openrgb_supervisor.get_devices()

    def get_device_owner(self, dev_name):
        return self.owners.get(dev_name, "thermal_direct")

    def set_device_owner(self, dev_name, owner):
        self.owners[dev_name] = owner

    def can_apply_thermal_frame(self, dev_name):
        return self.get_device_owner(dev_name) == "thermal_direct"

    def export_diagnostics(self):
        return {"diagnostics": "ok"}

    def retry(self):
        pass


class TestSettingsGUI(unittest.TestCase):
    def setUp(self):
        self.cfg_mgr = ConfigManager()
        self.ram_a = DeviceDescriptor(
            key="ENE DRAM_idx0",
            name="ENE DRAM",
            display_name="ENE DRAM",
            session_index=0,
            ambiguous=True,
            zones=(ZoneDescriptor(key="ENE DRAM_idx0_z0", name="DRAM Zone", index=0, led_count=5, leds_min=5, leds_max=5, resizable=False),)
        )
        self.ram_b = DeviceDescriptor(
            key="ENE DRAM_idx1",
            name="ENE DRAM",
            display_name="ENE DRAM",
            session_index=1,
            ambiguous=True,
            zones=(ZoneDescriptor(key="ENE DRAM_idx1_z0", name="DRAM Zone", index=0, led_count=5, leds_min=5, leds_max=5, resizable=False),)
        )
        self.mobo = DeviceDescriptor(
            key="MSI B550_key",
            name="MSI B550",
            display_name="MSI B550",
            session_index=2,
            zones=(
                ZoneDescriptor(key="mobo_z0", name="JRGB1", index=0, led_count=1, leds_min=1, leds_max=1, resizable=False),
                ZoneDescriptor(key="mobo_z1", name="JRAINBOW1", index=1, led_count=60, leds_min=0, leds_max=200, resizable=True),
            )
        )

        dev_ram_a = DummyDevice("ENE DRAM", leds=[object()]*5)
        dev_ram_b = DummyDevice("ENE DRAM", leds=[object()]*5)
        dev_mobo = DummyDevice("MSI B550", leds=[object()]*61, zones=[
            DummyZone("JRGB1", 1, 1, 1, resizable=False),
            DummyZone("JRAINBOW1", 60, 0, 200, resizable=True),
        ])

        self.supervisor = MockSupervisor(
            descriptors=[self.ram_a, self.ram_b, self.mobo],
            devices=[dev_ram_a, dev_ram_b, dev_mobo]
        )
        self.controller = MockController(self.supervisor)

    def test_gui_creation_and_tabs(self):
        gui = SettingsGUI(config_manager=self.cfg_mgr, controller=self.controller)
        try:
            gui.show()
            gui.root.update_idletasks()
            gui.root.update()

            tab_texts = [gui.notebook.tab(i, "text").strip() for i in range(gui.notebook.index("end"))]
            self.assertTrue(any("Manual" in t for t in tab_texts))
            self.assertTrue(any("Effects" in t for t in tab_texts))
            self.assertTrue(any("Temperature" in t for t in tab_texts))

            self.assertIsNotNone(gui.min_temp_var)
            self.assertIsNotNone(gui.mid_temp_var)
            self.assertIsNotNone(gui.max_temp_var)
        finally:
            gui.root.destroy()

    def test_duplicate_devices_rendered_distinctly(self):
        gui = SettingsGUI(config_manager=self.cfg_mgr, controller=self.controller)
        try:
            gui.show()
            gui.root.update_idletasks()
            gui.root.update()

            labels = gui.get_device_tree_labels()
            self.assertTrue(any("RAM A" in l for l in labels))
            self.assertTrue(any("RAM B" in l for l in labels))
        finally:
            gui.root.destroy()

    def test_empty_devices_does_not_crash(self):
        empty_ctrl = MockController(MockSupervisor([], []))
        gui = SettingsGUI(config_manager=self.cfg_mgr, controller=empty_ctrl)
        try:
            gui.show()
            gui.root.update_idletasks()
            gui.root.update()
            labels = gui.get_device_tree_labels()
            self.assertEqual(labels, [])
        finally:
            gui.root.destroy()

    def test_manual_color_application_targets_selected_device(self):
        gui = SettingsGUI(config_manager=self.cfg_mgr, controller=self.controller)
        try:
            gui.show()
            gui.root.update_idletasks()
            gui.root.update()

            # Select RAM A
            gui._select_tree_target("ENE DRAM_idx0")
            gui.color_state.set_rgb(255, 0, 0)
            gui._apply_manual_color()

            # Verify write occurred on RAM A key
            self.assertEqual(len(self.supervisor.colors_set), 1)
            target_key, payload = self.supervisor.colors_set[0]
            self.assertEqual(target_key, "ENE DRAM_idx0")
            self.assertEqual(len(payload), 5)
            self.assertEqual(self.controller.get_device_owner("ENE DRAM_idx0"), "manual_direct")
            self.assertEqual(self.controller.get_device_owner("ENE DRAM_idx1"), "thermal_direct")

            # RAM B was NOT touched
            self.assertNotIn("ENE DRAM_idx1", [t[0] for t in self.supervisor.colors_set])
        finally:
            gui.root.destroy()

    def test_manual_color_switches_non_per_led_effect_to_direct(self):
        class Mode:
            def __init__(self, name, color_mode):
                self.name = name
                self.color_mode = color_mode

        effect_device = DummyDevice(
            "MSI B550",
            leds=[object()] * 2,
            modes=[Mode("Direct", 1), Mode("Rainbow wave", 3)],
            active_mode=1,
        )
        descriptor = DeviceDescriptor(
            key="MSI B550_key",
            name="MSI B550",
            display_name="MSI B550",
            session_index=0,
            zones=(ZoneDescriptor(key="z0", name="ONBOARD", index=0, led_count=2, leds_min=2, leds_max=2, resizable=False),),
        )
        supervisor = MockSupervisor([descriptor], [effect_device])
        controller = MockController(supervisor)
        gui = SettingsGUI(config_manager=self.cfg_mgr, controller=controller)
        try:
            gui.show()
            gui.root.update_idletasks()
            gui.root.update()
            gui._select_tree_target("MSI B550_key")
            gui.color_state.set_rgb(255, 255, 255)
            gui._apply_manual_color()

            self.assertEqual(supervisor.direct_mode_calls, [("MSI B550_key", "Direct")])
            self.assertEqual(len(supervisor.colors_set), 1)
        finally:
            gui.root.destroy()

    def test_edit_zone_button_state_for_resizable_vs_fixed(self):
        gui = SettingsGUI(config_manager=self.cfg_mgr, controller=self.controller)
        try:
            gui.show()
            gui.root.update_idletasks()
            gui.root.update()

            # Select JRAINBOW1 (resizable) -> button normal
            gui._select_tree_target("zone:MSI B550_key:1")
            self.assertEqual(str(gui.edit_zone_btn["state"]), "normal")

            # Select JRGB1 (fixed) -> button disabled
            gui._select_tree_target("zone:MSI B550_key:0")
            self.assertEqual(str(gui.edit_zone_btn["state"]), "disabled")
        finally:
            gui.root.destroy()

    def test_select_all_and_deselect_all_leds(self):
        gui = SettingsGUI(config_manager=self.cfg_mgr, controller=self.controller)
        try:
            gui.show()
            gui.root.update_idletasks()
            gui.root.update()

            gui._select_tree_target("ENE DRAM_idx0")
            gui._select_all_leds()
            self.assertEqual(len(gui.selected_led_indices), 5)

            gui._deselect_all_leds()
            self.assertEqual(len(gui.selected_led_indices), 0)
        finally:
            gui.root.destroy()



    def test_factory_reset_button_state(self):
        gui = SettingsGUI(config_manager=self.cfg_mgr, controller=self.controller)
        try:
            gui.show()
            gui.root.update_idletasks()
            gui.root.update()

            # Select ENE -> disabled
            gui._select_tree_target("ENE DRAM_idx0")
            self.assertEqual(str(gui.factory_reset_btn["state"]), "disabled")
            self.assertIn("Unsupported", gui.factory_reset_label.cget("text"))

            # Add verified device
            verified_desc = DeviceDescriptor(
                key="verified_device_1",
                name="Verified Device",
                display_name="Verified Device",
                session_index=3,
                zones=()
            )
            self.supervisor._descriptors.append(verified_desc)
            self.supervisor._devices.append(DummyDevice("Verified Device", leds=[]))
            gui._rescan_inventory()
            
            gui._select_tree_target("verified_device_1")
            self.assertEqual(str(gui.factory_reset_btn["state"]), "normal")
            self.assertIn("Available", gui.factory_reset_label.cget("text"))
        finally:
            gui.root.destroy()

    def test_factory_reset_snapshot_buttons_exist(self):
        gui = SettingsGUI(config_manager=self.cfg_mgr, controller=self.controller)
        try:
            gui.show()
            gui.root.update_idletasks()
            gui.root.update()

            self.assertIsNotNone(gui.reset_device_btn)
            self.assertIsNotNone(gui.factory_reset_btn)
            
            # verify snapshot button has the correct command mapped
            self.assertEqual(gui.reset_device_btn.cget("text"), "Restore Pre-Sync Snapshot")
        finally:
            gui.root.destroy()

if __name__ == '__main__':
    unittest.main()
