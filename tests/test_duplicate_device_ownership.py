import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from openrgb_temp_sync.controller import SyncController, ControllerState
from openrgb_temp_sync.config import ConfigManager
from openrgb_temp_sync.openrgb_runtime import (
    DeviceDescriptor,
    EngineState,
    ModeDescriptor,
    OpenRGBSupervisor,
    WriteResult,
    ZoneDescriptor,
)


class MockLed:
    def __init__(self, name):
        self.name = name


class MockDevice:
    def __init__(self, name, leds=None, zones=None, modes=None):
        self.name = name
        self.leds = leds or [MockLed(f'LED {i}') for i in range(5)]
        self.zones = zones or []
        self.modes = modes or []
        self.colors = []
        self.active_mode = 0 if self.modes else None

    def set_colors(self, colors, fast=True):
        self.colors = list(colors)

    def set_mode(self, mode):
        self.active_mode = mode


class MockSupervisorForDuplicates:
    def __init__(self, descriptors, devices):
        self.state = EngineState.RUNNING_OWNED
        self.status_message = 'Running'
        self._descriptors = descriptors
        self.devices = devices
        self.restored = []
        self.colors_set = []
        self.modes_set = []
        self._target_map = {}
        for desc, dev in zip(descriptors, devices):
            key = desc.stable_key or desc.key
            self._target_map[key] = dev
            self._target_map[desc.key] = dev

    def get_devices(self):
        return self.devices

    def get_descriptors(self):
        return list(self._descriptors)

    def is_owned(self):
        return True

    def _find_device(self, target_key):
        return self._target_map.get(target_key)

    def restore_device(self, target_key):
        self.restored.append(target_key)
        return True

    def set_mode(self, target_key, mode_name, **kwargs):
        self.modes_set.append((target_key, mode_name))
        return WriteResult(ok=True, target_key=target_key, operation='set_mode')

    def set_device_mode(self, target_key, mode_name):
        self.modes_set.append((target_key, mode_name))
        return True

    def set_colors(self, target_key, colors, fast=True):
        self.colors_set.append((target_key, colors))
        dev = self._target_map.get(target_key)
        if dev:
            dev.set_colors(colors, fast=fast)
        return WriteResult(ok=True, target_key=target_key, operation='set_colors')


class MockSensorSupervisor:
    def get_status(self):
        return 'OK'

    def get_latest_reading(self):
        return None


class TestDuplicateDeviceOwnership(unittest.TestCase):
    def setUp(self):
        self.ram_a_desc = DeviceDescriptor(
            key='ENE DRAM_ramA',
            name='ENE DRAM',
            display_name='ENE DRAM',
            session_index=0,
            stable_key='ENE DRAM_ramA',
            zones=(ZoneDescriptor(key='ramA_z0', name='DRAM Zone', index=0, led_count=5, leds_min=5, leds_max=5, resizable=False),),
            modes=(ModeDescriptor(name='Direct', index=0, flags=('per_led',)),)
        )
        self.ram_b_desc = DeviceDescriptor(
            key='ENE DRAM_ramB',
            name='ENE DRAM',
            display_name='ENE DRAM',
            session_index=1,
            stable_key='ENE DRAM_ramB',
            zones=(ZoneDescriptor(key='ramB_z0', name='DRAM Zone', index=0, led_count=5, leds_min=5, leds_max=5, resizable=False),),
            modes=(ModeDescriptor(name='Direct', index=0, flags=('per_led',)),)
        )
        self.mobo_desc = DeviceDescriptor(
            key='MSI B550_key',
            name='MSI B550',
            display_name='MSI B550',
            session_index=2,
            stable_key='MSI B550_key',
            zones=(),
            modes=(ModeDescriptor(name='Direct', index=0, flags=('per_led',)),)
        )

        self.dev_ram_a = MockDevice('ENE DRAM')
        self.dev_ram_b = MockDevice('ENE DRAM')
        self.dev_mobo = MockDevice('MSI B550')

        self.supervisor = MockSupervisorForDuplicates(
            descriptors=[self.ram_a_desc, self.ram_b_desc, self.mobo_desc],
            devices=[self.dev_ram_a, self.dev_ram_b, self.dev_mobo]
        )
        self.config_mgr = ConfigManager()
        self.controller = SyncController(
            config_manager=self.config_mgr,
            openrgb_supervisor=self.supervisor,
            sensor_supervisor=MockSensorSupervisor()
        )
        self.controller.smoothed_cpu_temp = 45.0

    def test_duplicate_devices_independent_owners(self):
        # Independent ownership transitions for RAM A and RAM B
        self.assertEqual(self.controller.get_device_owner('ENE DRAM_ramA'), 'thermal_direct')
        self.assertEqual(self.controller.get_device_owner('ENE DRAM_ramB'), 'thermal_direct')

        self.controller.set_device_owner('ENE DRAM_ramA', 'manual_direct')
        self.assertEqual(self.controller.get_device_owner('ENE DRAM_ramA'), 'manual_direct')
        self.assertEqual(self.controller.get_device_owner('ENE DRAM_ramB'), 'thermal_direct')
        self.assertFalse(self.controller.can_apply_thermal_frame('ENE DRAM_ramA'))
        self.assertTrue(self.controller.can_apply_thermal_frame('ENE DRAM_ramB'))

        self.controller.set_device_owner('ENE DRAM_ramB', 'hardware_mode')
        self.assertEqual(self.controller.get_device_owner('ENE DRAM_ramA'), 'manual_direct')
        self.assertEqual(self.controller.get_device_owner('ENE DRAM_ramB'), 'hardware_mode')
        self.assertFalse(self.controller.can_apply_thermal_frame('ENE DRAM_ramB'))

    def test_reset_and_resume_targets_single_duplicate_device(self):
        # Resetting RAM A must not reset RAM B
        self.assertTrue(self.controller.reset_device_to_original('ENE DRAM_ramA'))
        self.assertEqual(self.supervisor.restored, ['ENE DRAM_ramA'])
        self.assertTrue(self.controller.is_device_reset('ENE DRAM_ramA'))
        self.assertFalse(self.controller.is_device_reset('ENE DRAM_ramB'))
        self.assertEqual(self.controller.get_device_owner('ENE DRAM_ramA'), 'resetting')
        self.assertEqual(self.controller.get_device_owner('ENE DRAM_ramB'), 'thermal_direct')

        # Resuming RAM A restores thermal_direct and does not affect RAM B
        self.assertTrue(self.controller.resume_device('ENE DRAM_ramA'))
        self.assertFalse(self.controller.is_device_reset('ENE DRAM_ramA'))
        self.assertFalse(self.controller.is_device_reset('ENE DRAM_ramB'))
        self.assertEqual(self.controller.get_device_owner('ENE DRAM_ramA'), 'thermal_direct')
        self.assertEqual(self.controller.get_device_owner('ENE DRAM_ramB'), 'thermal_direct')

    def test_thermal_writes_continue_to_unheld_duplicate_device(self):
        # When RAM A is manual_direct, thermal writes must continue to RAM B
        self.controller.set_device_owner('ENE DRAM_ramA', 'manual_direct')
        self.supervisor.colors_set.clear()

        self.controller._dispatch_thermal_frame()
        written_targets = [t[0] for t in self.supervisor.colors_set]
        self.assertNotIn('ENE DRAM_ramA', written_targets)
        self.assertIn('ENE DRAM_ramB', written_targets)
        self.assertIn('MSI B550_key', written_targets)

        # When RAM A resumes, both RAM devices receive thermal writes
        self.controller.resume_device('ENE DRAM_ramA')
        self.supervisor.colors_set.clear()

        self.controller._dispatch_thermal_frame()
        written_targets = [t[0] for t in self.supervisor.colors_set]
        self.assertIn('ENE DRAM_ramA', written_targets)
        self.assertIn('ENE DRAM_ramB', written_targets)

    def test_ambiguous_legacy_name_rejected(self):
        # Querying or mutating ambiguous display name ENE DRAM must be rejected
        self.assertFalse(self.controller.set_device_owner('ENE DRAM', 'manual_direct'))
        self.assertEqual(self.controller.get_device_owner('ENE DRAM'), 'ambiguous')
        self.assertFalse(self.controller.can_apply_thermal_frame('ENE DRAM'))
        self.assertFalse(self.controller.is_device_reset('ENE DRAM'))
        self.assertFalse(self.controller.reset_device_to_original('ENE DRAM'))
        self.assertFalse(self.controller.resume_device('ENE DRAM'))

        # Both devices remain unaffected in thermal_direct
        self.assertEqual(self.controller.get_device_owner('ENE DRAM_ramA'), 'thermal_direct')
        self.assertEqual(self.controller.get_device_owner('ENE DRAM_ramB'), 'thermal_direct')
        self.assertFalse(self.controller.is_device_reset('ENE DRAM_ramA'))
        self.assertFalse(self.controller.is_device_reset('ENE DRAM_ramB'))

    def test_unique_legacy_name_compatibility_resolver(self):
        # Unique display name 'MSI B550' resolves cleanly to 'MSI B550_key'
        self.assertEqual(self.controller.resolve_target_key('MSI B550'), 'MSI B550_key')
        self.assertTrue(self.controller.set_device_owner('MSI B550', 'manual_direct'))
        self.assertEqual(self.controller.get_device_owner('MSI B550'), 'manual_direct')
        self.assertEqual(self.controller.get_device_owner('MSI B550_key'), 'manual_direct')

        self.assertTrue(self.controller.reset_device_to_original('MSI B550'))
        self.assertEqual(self.supervisor.restored, ['MSI B550_key'])
        self.assertTrue(self.controller.is_device_reset('MSI B550'))
        self.assertTrue(self.controller.is_device_reset('MSI B550_key'))

        self.assertTrue(self.controller.resume_device('MSI B550'))
        self.assertFalse(self.controller.is_device_reset('MSI B550'))
        self.assertEqual(self.controller.get_device_owner('MSI B550'), 'thermal_direct')



    def test_lights_off_skips_held_duplicate_and_touches_active_duplicate(self):
        self.controller.reset_device_to_original("ENE DRAM_ramA")
        self.supervisor.colors_set.clear()

        self.controller.set_lights_off(True)
        written_targets = [t[0] for t in self.supervisor.colors_set]
        self.assertNotIn("ENE DRAM_ramA", written_targets)
        self.assertIn("ENE DRAM_ramB", written_targets)
        self.assertIn("MSI B550_key", written_targets)

    def test_hardware_mode_targets_single_duplicate_device(self):
        res = self.controller.set_device_hardware_mode("ENE DRAM_ramA", "Direct")
        self.assertTrue(res.ok)
        self.assertEqual(self.controller.get_device_owner("ENE DRAM_ramA"), "hardware_mode")
        self.assertEqual(self.controller.get_device_owner("ENE DRAM_ramB"), "thermal_direct")
        self.assertFalse(self.controller.can_apply_thermal_frame("ENE DRAM_ramA"))
        self.assertTrue(self.controller.can_apply_thermal_frame("ENE DRAM_ramB"))

if __name__ == '__main__':
    unittest.main()
