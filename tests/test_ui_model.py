import unittest
import sys
import os
from unittest.mock import MagicMock, call

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from openrgb_temp_sync.openrgb_runtime import (
    DeviceDescriptor,
    ZoneDescriptor,
    ModeDescriptor,
    WriteResult,
    EngineState
)
from openrgb_temp_sync.ui_model import (
    UIModel,
    ColorState,
    EditZoneTransaction,
    DeviceTreeItem,
    format_device_label,
    hex_to_rgb,
    rgb_to_hex,
    rgb_to_hsv,
    hsv_to_rgb,
    build_target_colors
)


class TestUIModel(unittest.TestCase):
    def setUp(self):
        self.ram1 = DeviceDescriptor(
            key="ENE DRAM_idx0",
            name="ENE DRAM",
            display_name="ENE DRAM",
            session_index=0,
            stable_key=None,
            ambiguous=True,
            zones=(
                ZoneDescriptor(key="ENE DRAM_idx0_z0", name="DRAM Zone", index=0, led_count=5, leds_min=5, leds_max=5, resizable=False),
            )
        )
        self.ram2 = DeviceDescriptor(
            key="ENE DRAM_idx1",
            name="ENE DRAM",
            display_name="ENE DRAM",
            session_index=1,
            stable_key=None,
            ambiguous=True,
            zones=(
                ZoneDescriptor(key="ENE DRAM_idx1_z0", name="DRAM Zone", index=0, led_count=5, leds_min=5, leds_max=5, resizable=False),
            )
        )
        self.mobo = DeviceDescriptor(
            key="MSI B550_abc",
            name="MSI B550",
            display_name="MSI B550",
            session_index=2,
            stable_key="MSI B550_abc",
            ambiguous=False,
            zones=(
                ZoneDescriptor(key="mobo_z0", name="JRGB1", index=0, led_count=1, leds_min=1, leds_max=1, resizable=False),
                ZoneDescriptor(key="mobo_z1", name="JRGB2", index=1, led_count=1, leds_min=1, leds_max=1, resizable=False),
                ZoneDescriptor(key="mobo_z2", name="JRAINBOW1", index=2, led_count=60, leds_min=0, leds_max=200, resizable=True),
                ZoneDescriptor(key="mobo_z3", name="JRAINBOW2", index=3, led_count=40, leds_min=0, leds_max=200, resizable=True),
            )
        )

    def test_duplicate_device_labels_and_stable_keys(self):
        items = UIModel.build_device_tree_items([self.ram1, self.ram2, self.mobo])
        self.assertEqual(len(items), 3)

        # Distinguishable labels
        self.assertIn("RAM A", items[0].display_label)
        self.assertIn("RAM B", items[1].display_label)
        self.assertNotEqual(items[0].display_label, items[1].display_label)

        # Keys match descriptor keys
        self.assertEqual(items[0].key, "ENE DRAM_idx0")
        self.assertEqual(items[1].key, "ENE DRAM_idx1")

        # Ambiguity is visible
        self.assertTrue(items[0].is_ambiguous)
        self.assertTrue(items[1].is_ambiguous)
        self.assertFalse(items[2].is_ambiguous)

    def test_empty_descriptors_handled_without_crashing(self):
        items = UIModel.build_device_tree_items([])
        self.assertEqual(items, [])

    def test_color_conversions_and_validation(self):
        # Hex to RGB
        self.assertEqual(hex_to_rgb("#ff0000"), (255, 0, 0))
        self.assertEqual(hex_to_rgb("00ff00"), (0, 255, 0))
        self.assertEqual(hex_to_rgb("#123456"), (18, 52, 86))

        # Invalid Hex
        self.assertIsNone(hex_to_rgb("not-hex"))
        self.assertIsNone(hex_to_rgb("#12345"))
        self.assertIsNone(hex_to_rgb("#1234567"))

        # RGB to Hex
        self.assertEqual(rgb_to_hex((255, 0, 0)), "#ff0000")
        self.assertEqual(rgb_to_hex((0, 255, 0)), "#00ff00")

        # RGB <-> HSV
        h, s, v = rgb_to_hsv((255, 0, 0))
        self.assertEqual((h, s, v), (0, 100, 100))
        self.assertEqual(hsv_to_rgb(0, 100, 100), (255, 0, 0))

        h, s, v = rgb_to_hsv((0, 255, 0))
        self.assertEqual((h, s, v), (120, 100, 100))
        self.assertEqual(hsv_to_rgb(120, 100, 100), (0, 255, 0))

        # ColorState clamps and validates
        cs = ColorState()
        cs.set_rgb(300, -10, 50)
        self.assertEqual(cs.get_rgb(), (255, 0, 50))
        self.assertEqual(cs.get_hex(), "#ff0032")

    def test_selection_scope_color_application(self):
        # Initial 5 LEDs all black
        initial_colors = [(0, 0, 0)] * 5

        # Select only LED index 2
        new_colors = build_target_colors(
            total_leds=5,
            current_colors=initial_colors,
            selected_indices=[2],
            new_color=(255, 0, 0)
        )
        self.assertEqual(new_colors[2], (255, 0, 0))
        self.assertEqual(new_colors[0], (0, 0, 0))
        self.assertEqual(new_colors[1], (0, 0, 0))
        self.assertEqual(new_colors[3], (0, 0, 0))
        self.assertEqual(new_colors[4], (0, 0, 0))

        # Multi-selection: LEDs 1 and 3
        new_colors2 = build_target_colors(
            total_leds=5,
            current_colors=new_colors,
            selected_indices=[1, 3],
            new_color=(0, 255, 0)
        )
        self.assertEqual(new_colors2[1], (0, 255, 0))
        self.assertEqual(new_colors2[3], (0, 255, 0))
        self.assertEqual(new_colors2[2], (255, 0, 0))  # Previous write preserved
        self.assertEqual(new_colors2[0], (0, 0, 0))

    def test_capability_disabled_controls(self):
        # JRAINBOW1 is resizable (0-200)
        jrainbow = self.mobo.zones[2]
        self.assertTrue(jrainbow.resizable)
        self.assertTrue(UIModel.is_zone_resizable(jrainbow))

        # JRGB1 is non-resizable (1-1)
        jrgb = self.mobo.zones[0]
        self.assertFalse(jrgb.resizable)
        self.assertFalse(UIModel.is_zone_resizable(jrgb))

    def test_edit_zone_validation_and_bounds(self):
        tx = EditZoneTransaction()
        # Invalid integer
        valid, val, err = tx.validate_count("abc", min_count=0, max_count=200)
        self.assertFalse(valid)
        self.assertIn("whole number", err.lower())

        # Below minimum
        valid, val, err = tx.validate_count("-1", min_count=0, max_count=200)
        self.assertFalse(valid)
        self.assertIn("between", err.lower())

        # Above maximum
        valid, val, err = tx.validate_count("250", min_count=0, max_count=200)
        self.assertFalse(valid)
        self.assertIn("between", err.lower())

        # Valid count
        valid, val, err = tx.validate_count("72", min_count=0, max_count=200)
        self.assertTrue(valid)
        self.assertEqual(val, 72)

    def test_edit_zone_cancel_does_not_write_or_persist(self):
        mock_sup = MagicMock()
        mock_ctrl = MagicMock()
        mock_cfg_mgr = MagicMock()

        tx = EditZoneTransaction()
        tx.cancel()

        mock_sup.resize_zone.assert_not_called()
        mock_ctrl.resize_zone.assert_not_called()
        mock_cfg_mgr.save_config.assert_not_called()

    def test_edit_zone_apply_success_and_readback_persistence(self):
        mock_sup = MagicMock()
        mock_sup.resize_zone.return_value = True

        # Fresh descriptor returned upon inventory refresh
        updated_zone = ZoneDescriptor(key="mobo_z2", name="JRAINBOW1", index=2, led_count=72, leds_min=0, leds_max=200, resizable=True)
        updated_mobo = DeviceDescriptor(
            key="MSI B550_abc",
            name="MSI B550",
            display_name="MSI B550",
            session_index=2,
            zones=(updated_zone,)
        )
        mock_sup.get_descriptors.return_value = [updated_mobo]

        mock_ctrl = MagicMock()
        mock_cfg_mgr = MagicMock()
        mock_cfg_mgr.get_config.return_value = {"devices": {}}

        tx = EditZoneTransaction()
        ok, msg = tx.apply(
            supervisor=mock_sup,
            controller=mock_ctrl,
            config_manager=mock_cfg_mgr,
            target_key="MSI B550_abc",
            device_name="MSI B550",
            zone_index=2,
            zone_name="JRAINBOW1",
            new_count=72,
            min_count=0,
            max_count=200
        )

        self.assertTrue(ok)
        mock_sup.resize_zone.assert_called_once_with("MSI B550_abc", 2, 72)
        mock_sup.refresh_inventory.assert_called_once()
        mock_cfg_mgr.save_config.assert_called_once()

    def test_edit_zone_apply_failure_on_supervisor_rejection(self):
        mock_sup = MagicMock()
        mock_sup.resize_zone.return_value = False

        mock_ctrl = MagicMock()
        mock_cfg_mgr = MagicMock()

        tx = EditZoneTransaction()
        ok, msg = tx.apply(
            supervisor=mock_sup,
            controller=mock_ctrl,
            config_manager=mock_cfg_mgr,
            target_key="MSI B550_abc",
            device_name="MSI B550",
            zone_index=2,
            zone_name="JRAINBOW1",
            new_count=72,
            min_count=0,
            max_count=200
        )

        self.assertFalse(ok)
        self.assertIn("rejected", msg.lower())
        mock_cfg_mgr.save_config.assert_not_called()

    def test_edit_zone_apply_failure_on_readback_mismatch(self):
        mock_sup = MagicMock()
        mock_sup.resize_zone.return_value = True

        # Readback returns old count (60 instead of 72)
        stale_zone = ZoneDescriptor(key="mobo_z2", name="JRAINBOW1", index=2, led_count=60, leds_min=0, leds_max=200, resizable=True)
        mobo = DeviceDescriptor(
            key="MSI B550_abc",
            name="MSI B550",
            display_name="MSI B550",
            session_index=2,
            zones=(stale_zone,)
        )
        mock_sup.get_descriptors.return_value = [mobo]

        mock_ctrl = MagicMock()
        mock_cfg_mgr = MagicMock()

        tx = EditZoneTransaction()
        ok, msg = tx.apply(
            supervisor=mock_sup,
            controller=mock_ctrl,
            config_manager=mock_cfg_mgr,
            target_key="MSI B550_abc",
            device_name="MSI B550",
            zone_index=2,
            zone_name="JRAINBOW1",
            new_count=72,
            min_count=0,
            max_count=200
        )

        self.assertFalse(ok)
        self.assertIn("mismatch", msg.lower())
        mock_cfg_mgr.save_config.assert_not_called()



    def test_edit_zone_apply_failure_restores_owner_on_supervisor_rejection(self):
        mock_sup = MagicMock()
        mock_sup.resize_zone.return_value = False

        mock_ctrl = MagicMock()
        mock_ctrl.get_device_owner.return_value = "thermal_direct"
        mock_cfg_mgr = MagicMock()

        tx = EditZoneTransaction()
        ok, msg = tx.apply(
            supervisor=mock_sup,
            controller=mock_ctrl,
            config_manager=mock_cfg_mgr,
            target_key="MSI B550_abc",
            device_name="MSI B550",
            zone_index=2,
            zone_name="JRAINBOW1",
            new_count=72,
            min_count=0,
            max_count=200
        )

        self.assertFalse(ok)
        self.assertEqual(
            mock_ctrl.set_device_owner.call_args_list,
            [
                call("MSI B550_abc", "manual_direct"),
                call("MSI B550_abc", "thermal_direct")
            ]
        )

    def test_edit_zone_apply_failure_restores_owner_on_readback_mismatch(self):
        mock_sup = MagicMock()
        mock_sup.resize_zone.return_value = True

        stale_zone = ZoneDescriptor(key="mobo_z2", name="JRAINBOW1", index=2, led_count=60, leds_min=0, leds_max=200, resizable=True)
        mobo = DeviceDescriptor(
            key="MSI B550_abc",
            name="MSI B550",
            display_name="MSI B550",
            session_index=2,
            zones=(stale_zone,)
        )
        mock_sup.get_descriptors.return_value = [mobo]

        mock_ctrl = MagicMock()
        mock_ctrl.get_device_owner.return_value = "thermal_direct"
        mock_cfg_mgr = MagicMock()

        tx = EditZoneTransaction()
        ok, msg = tx.apply(
            supervisor=mock_sup,
            controller=mock_ctrl,
            config_manager=mock_cfg_mgr,
            target_key="MSI B550_abc",
            device_name="MSI B550",
            zone_index=2,
            zone_name="JRAINBOW1",
            new_count=72,
            min_count=0,
            max_count=200
        )

        self.assertFalse(ok)
        self.assertEqual(
            mock_ctrl.set_device_owner.call_args_list,
            [
                call("MSI B550_abc", "manual_direct"),
                call("MSI B550_abc", "thermal_direct")
            ]
        )

    def test_edit_zone_apply_failure_restores_owner_on_missing_readback(self):
        mock_sup = MagicMock()
        mock_sup.resize_zone.return_value = True
        mock_sup.get_descriptors.return_value = []

        mock_ctrl = MagicMock()
        mock_ctrl.get_device_owner.return_value = "thermal_direct"
        mock_cfg_mgr = MagicMock()

        tx = EditZoneTransaction()
        ok, msg = tx.apply(
            supervisor=mock_sup,
            controller=mock_ctrl,
            config_manager=mock_cfg_mgr,
            target_key="MSI B550_abc",
            device_name="MSI B550",
            zone_index=2,
            zone_name="JRAINBOW1",
            new_count=72,
            min_count=0,
            max_count=200
        )

        self.assertFalse(ok)
        self.assertIn("missing", msg.lower())
        self.assertEqual(
            mock_ctrl.set_device_owner.call_args_list,
            [
                call("MSI B550_abc", "manual_direct"),
                call("MSI B550_abc", "thermal_direct")
            ]
        )

    def test_edit_zone_apply_failure_restores_owner_on_missing_zone(self):
        mock_sup = MagicMock()
        mock_sup.resize_zone.return_value = True
        mobo = DeviceDescriptor(
            key="MSI B550_abc",
            name="MSI B550",
            display_name="MSI B550",
            session_index=2,
            zones=()
        )
        mock_sup.get_descriptors.return_value = [mobo]

        mock_ctrl = MagicMock()
        mock_ctrl.get_device_owner.return_value = "thermal_direct"
        mock_cfg_mgr = MagicMock()

        tx = EditZoneTransaction()
        ok, msg = tx.apply(
            supervisor=mock_sup,
            controller=mock_ctrl,
            config_manager=mock_cfg_mgr,
            target_key="MSI B550_abc",
            device_name="MSI B550",
            zone_index=2,
            zone_name="JRAINBOW1",
            new_count=72,
            min_count=0,
            max_count=200
        )

        self.assertFalse(ok)
        self.assertIn("zone descriptor missing", msg.lower())
        self.assertEqual(
            mock_ctrl.set_device_owner.call_args_list,
            [
                call("MSI B550_abc", "manual_direct"),
                call("MSI B550_abc", "thermal_direct")
            ]
        )

    def test_edit_zone_apply_failure_restores_owner_on_config_save_exception(self):
        mock_sup = MagicMock()
        mock_sup.resize_zone.return_value = True

        updated_zone = ZoneDescriptor(key="mobo_z2", name="JRAINBOW1", index=2, led_count=72, leds_min=0, leds_max=200, resizable=True)
        mobo = DeviceDescriptor(
            key="MSI B550_abc",
            name="MSI B550",
            display_name="MSI B550",
            session_index=2,
            zones=(updated_zone,)
        )
        mock_sup.get_descriptors.return_value = [mobo]

        mock_ctrl = MagicMock()
        mock_ctrl.get_device_owner.return_value = "thermal_direct"
        mock_cfg_mgr = MagicMock()
        mock_cfg_mgr.get_config.return_value = {"devices": {}}
        mock_cfg_mgr.save_config.side_effect = IOError("disk write error")

        tx = EditZoneTransaction()
        ok, msg = tx.apply(
            supervisor=mock_sup,
            controller=mock_ctrl,
            config_manager=mock_cfg_mgr,
            target_key="MSI B550_abc",
            device_name="MSI B550",
            zone_index=2,
            zone_name="JRAINBOW1",
            new_count=72,
            min_count=0,
            max_count=200
        )

        self.assertFalse(ok)
        self.assertIn("persist", msg.lower())
        self.assertEqual(
            mock_ctrl.set_device_owner.call_args_list,
            [
                call("MSI B550_abc", "manual_direct"),
                call("MSI B550_abc", "thermal_direct")
            ]
        )

    def test_edit_zone_apply_leaves_owner_manual_direct_on_success(self):
        mock_sup = MagicMock()
        mock_sup.resize_zone.return_value = True

        updated_zone = ZoneDescriptor(key="mobo_z2", name="JRAINBOW1", index=2, led_count=72, leds_min=0, leds_max=200, resizable=True)
        mobo = DeviceDescriptor(
            key="MSI B550_abc",
            name="MSI B550",
            display_name="MSI B550",
            session_index=2,
            zones=(updated_zone,)
        )
        mock_sup.get_descriptors.return_value = [mobo]

        mock_ctrl = MagicMock()
        mock_ctrl.get_device_owner.return_value = "thermal_direct"
        mock_cfg_mgr = MagicMock()
        mock_cfg_mgr.get_config.return_value = {"devices": {}}

        tx = EditZoneTransaction()
        ok, msg = tx.apply(
            supervisor=mock_sup,
            controller=mock_ctrl,
            config_manager=mock_cfg_mgr,
            target_key="MSI B550_abc",
            device_name="MSI B550",
            zone_index=2,
            zone_name="JRAINBOW1",
            new_count=72,
            min_count=0,
            max_count=200
        )

        self.assertTrue(ok)
        self.assertEqual(
            mock_ctrl.set_device_owner.call_args_list,
            [call("MSI B550_abc", "manual_direct")]
        )

    def test_edit_zone_readback_target_key_disappears_duplicate_names_asserts_failure(self):
        zone1 = ZoneDescriptor(key="ram1_z0", name="Zone 0", index=0, led_count=5, leds_min=1, leds_max=10, resizable=True)
        dev1 = DeviceDescriptor(
            key="ENE DRAM_ramA",
            name="ENE DRAM",
            display_name="ENE DRAM",
            session_index=0,
            stable_key="ENE DRAM_ramA",
            zones=(zone1,)
        )
        zone2 = ZoneDescriptor(key="ram2_z0", name="Zone 0", index=0, led_count=5, leds_min=1, leds_max=10, resizable=True)
        dev2 = DeviceDescriptor(
            key="ENE DRAM_ramB",
            name="ENE DRAM",
            display_name="ENE DRAM",
            session_index=1,
            stable_key="ENE DRAM_ramB",
            zones=(zone2,)
        )

        mock_sup = MagicMock()
        mock_sup.resize_zone.return_value = True
        mock_sup.get_descriptors.return_value = [dev1, dev2]

        mock_ctrl = MagicMock()
        mock_ctrl.get_device_owner.return_value = "thermal_direct"
        mock_cfg_mgr = MagicMock()

        tx = EditZoneTransaction()
        ok, msg = tx.apply(
            supervisor=mock_sup,
            controller=mock_ctrl,
            config_manager=mock_cfg_mgr,
            target_key="ENE DRAM_disappeared_key",
            device_name="ENE DRAM",
            zone_index=0,
            zone_name="Zone 0",
            new_count=5,
            min_count=1,
            max_count=10
        )

        self.assertFalse(ok)
        self.assertIn("missing", msg.lower())
        mock_cfg_mgr.save_config.assert_not_called()
        self.assertEqual(
            mock_ctrl.set_device_owner.call_args_list,
            [
                call("ENE DRAM_disappeared_key", "manual_direct"),
                call("ENE DRAM_disappeared_key", "thermal_direct")
            ]
        )

    def test_edit_zone_readback_rejects_duplicate_names_when_target_key_absent(self):
        dev1 = DeviceDescriptor(
            key="ENE DRAM_ramA",
            name="ENE DRAM",
            display_name="ENE DRAM",
            session_index=0,
            zones=(ZoneDescriptor(key="ram1_z0", name="Zone 0", index=0, led_count=5, leds_min=1, leds_max=10, resizable=True),)
        )
        dev2 = DeviceDescriptor(
            key="ENE DRAM_ramB",
            name="ENE DRAM",
            display_name="ENE DRAM",
            session_index=1,
            zones=(ZoneDescriptor(key="ram2_z0", name="Zone 0", index=0, led_count=5, leds_min=1, leds_max=10, resizable=True),)
        )

        mock_sup = MagicMock()
        mock_sup.resize_zone.return_value = True
        mock_sup.get_descriptors.return_value = [dev1, dev2]

        mock_ctrl = MagicMock()
        mock_ctrl.get_device_owner.return_value = "thermal_direct"
        mock_cfg_mgr = MagicMock()

        tx = EditZoneTransaction()
        ok, msg = tx.apply(
            supervisor=mock_sup,
            controller=mock_ctrl,
            config_manager=mock_cfg_mgr,
            target_key="",
            device_name="ENE DRAM",
            zone_index=0,
            zone_name="Zone 0",
            new_count=5,
            min_count=1,
            max_count=10
        )

        self.assertFalse(ok)
        mock_cfg_mgr.save_config.assert_not_called()
        self.assertEqual(
            mock_ctrl.set_device_owner.call_args_list,
            [
                call("ENE DRAM", "manual_direct"),
                call("ENE DRAM", "thermal_direct")
            ]
        )

    def test_edit_zone_readback_rejects_ambiguous_device_descriptor(self):
        dev = DeviceDescriptor(
            key="ENE DRAM_idx0",
            name="ENE DRAM",
            display_name="ENE DRAM",
            session_index=0,
            ambiguous=True,
            zones=(ZoneDescriptor(key="ram_z0", name="Zone 0", index=0, led_count=5, leds_min=1, leds_max=10, resizable=True),)
        )

        mock_sup = MagicMock()
        mock_sup.resize_zone.return_value = True
        mock_sup.get_descriptors.return_value = [dev]

        mock_ctrl = MagicMock()
        mock_ctrl.get_device_owner.return_value = "thermal_direct"
        mock_cfg_mgr = MagicMock()

        tx = EditZoneTransaction()
        ok, msg = tx.apply(
            supervisor=mock_sup,
            controller=mock_ctrl,
            config_manager=mock_cfg_mgr,
            target_key="ENE DRAM_idx0",
            device_name="ENE DRAM",
            zone_index=0,
            zone_name="Zone 0",
            new_count=5,
            min_count=1,
            max_count=10
        )

        self.assertFalse(ok)
        self.assertIn("ambiguous", msg.lower())
        mock_cfg_mgr.save_config.assert_not_called()
        self.assertEqual(
            mock_ctrl.set_device_owner.call_args_list,
            [
                call("ENE DRAM_idx0", "manual_direct"),
                call("ENE DRAM_idx0", "thermal_direct")
            ]
        )


if __name__ == '__main__':
    unittest.main()
