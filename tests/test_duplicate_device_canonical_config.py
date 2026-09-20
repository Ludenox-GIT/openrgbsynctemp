import unittest
import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from openrgb_temp_sync.config import (
    ConfigManager,
    DEFAULT_CONFIG_V2,
    merge_legacy_device_profiles,
    reconcile_device_profiles_on_save,
    get_canonical_device_key,
    resolve_config_device_key,
)
from openrgb_temp_sync.controller import SyncController
from openrgb_temp_sync.openrgb_runtime import (
    DeviceDescriptor,
    EngineState,
    ModeDescriptor,
    WriteResult,
    ZoneDescriptor,
)
from openrgb_temp_sync.ui_model import EditZoneTransaction


class MockLed:
    def __init__(self, name):
        self.name = name


class MockDevice:
    def __init__(self, name, leds=None, zones=None):
        self.name = name
        self.leds = leds or [MockLed(f'LED {i}') for i in range(5)]
        self.zones = zones or []
        self.colors = []

    def set_colors(self, colors, fast=True):
        self.colors = list(colors)


class MockSupervisorWithResize:
    def __init__(self, descriptors, devices):
        self.state = EngineState.RUNNING_OWNED
        self.status_message = 'Running'
        self._descriptors = list(descriptors)
        self.devices = devices
        self.resized_zones = []
        self.colors_set = []
        self.restored = []
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
        return WriteResult(ok=True, target_key=target_key, operation='set_mode')

    def set_device_mode(self, target_key, mode_name):
        return True

    def set_colors(self, target_key, colors, fast=True):
        self.colors_set.append((target_key, colors))
        dev = self._target_map.get(target_key)
        if dev:
            dev.set_colors(colors, fast=fast)
        return WriteResult(ok=True, target_key=target_key, operation='set_colors')

    def resize_zone(self, target_key, zone_index, count):
        self.resized_zones.append((target_key, zone_index, count))
        # Update internal descriptor zone led_count
        new_descriptors = []
        for desc in self._descriptors:
            if desc.stable_key == target_key or desc.key == target_key:
                new_zones = []
                for z in desc.zones:
                    if z.index == zone_index:
                        new_z = ZoneDescriptor(
                            key=z.key,
                            name=z.name,
                            index=z.index,
                            led_count=count,
                            leds_min=z.leds_min,
                            leds_max=z.leds_max,
                            resizable=z.resizable,
                            zone_type=z.zone_type,
                        )
                        new_zones.append(new_z)
                    else:
                        new_zones.append(z)
                new_desc = DeviceDescriptor(
                    key=desc.key,
                    name=desc.name,
                    display_name=desc.display_name,
                    session_index=desc.session_index,
                    stable_key=desc.stable_key,
                    device_type=desc.device_type,
                    vendor_id=desc.vendor_id,
                    product_id=desc.product_id,
                    serial=desc.serial,
                    location=desc.location,
                    path=desc.path,
                    ambiguous=desc.ambiguous,
                    zones=tuple(new_zones),
                    modes=desc.modes,
                )
                new_descriptors.append(new_desc)
            else:
                new_descriptors.append(desc)
        self._descriptors = new_descriptors
        return True

    def refresh_inventory(self):
        return self.get_descriptors()


class MockSensorSupervisor:
    def get_status(self):
        return 'OK'

    def get_latest_reading(self):
        return None


class TestDuplicateDeviceCanonicalConfig(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, 'config.json')
        self.cfg_mgr = ConfigManager(config_path=self.config_path)

        self.ram_a_zone = ZoneDescriptor(
            key='ramA_z0', name='JRAINBOW1', index=0, led_count=10, leds_min=1, leds_max=100, resizable=True
        )
        self.ram_b_zone = ZoneDescriptor(
            key='ramB_z0', name='JRAINBOW1', index=0, led_count=20, leds_min=1, leds_max=100, resizable=True
        )
        self.mobo_zone = ZoneDescriptor(
            key='mobo_z0', name='JRAINBOW1', index=0, led_count=40, leds_min=1, leds_max=100, resizable=True
        )

        self.ram_a_desc = DeviceDescriptor(
            key='ENE DRAM_ramA',
            name='ENE DRAM',
            display_name='ENE DRAM',
            session_index=0,
            stable_key='ENE DRAM_ramA',
            zones=(self.ram_a_zone,),
            modes=(ModeDescriptor(name='Direct', index=0, flags=('per_led',)),)
        )
        self.ram_b_desc = DeviceDescriptor(
            key='ENE DRAM_ramB',
            name='ENE DRAM',
            display_name='ENE DRAM',
            session_index=1,
            stable_key='ENE DRAM_ramB',
            zones=(self.ram_b_zone,),
            modes=(ModeDescriptor(name='Direct', index=0, flags=('per_led',)),)
        )
        self.mobo_desc = DeviceDescriptor(
            key='MSI B550_key',
            name='MSI B550',
            display_name='MSI B550',
            session_index=2,
            stable_key='MSI B550_key',
            zones=(self.mobo_zone,),
            modes=(ModeDescriptor(name='Direct', index=0, flags=('per_led',)),)
        )

        self.dev_ram_a = MockDevice('ENE DRAM')
        self.dev_ram_b = MockDevice('ENE DRAM')
        self.dev_mobo = MockDevice('MSI B550')

        self.descriptors = [self.ram_a_desc, self.ram_b_desc, self.mobo_desc]
        self.supervisor = MockSupervisorWithResize(
            descriptors=self.descriptors,
            devices=[self.dev_ram_a, self.dev_ram_b, self.dev_mobo]
        )
        self.sensor_sup = MockSensorSupervisor()
        self.controller = SyncController(
            config_manager=self.cfg_mgr,
            openrgb_supervisor=self.supervisor,
            sensor_supervisor=self.sensor_sup
        )
        self.controller.smoothed_cpu_temp = 45.0
        self.controller.smoothed_gpu_temp = 55.0

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_independent_zone_led_counts_survive_save_load_apply(self):
        tx = EditZoneTransaction()

        # 1. Resize RAM A to 15
        ok_a, msg_a = tx.apply(
            supervisor=self.supervisor,
            controller=self.controller,
            config_manager=self.cfg_mgr,
            target_key='ENE DRAM_ramA',
            device_name='ENE DRAM',
            zone_index=0,
            zone_name='JRAINBOW1',
            new_count=15,
            min_count=1,
            max_count=100
        )
        self.assertTrue(ok_a, msg_a)

        # 2. Resize RAM B to 25
        ok_b, msg_b = tx.apply(
            supervisor=self.supervisor,
            controller=self.controller,
            config_manager=self.cfg_mgr,
            target_key='ENE DRAM_ramB',
            device_name='ENE DRAM',
            zone_index=0,
            zone_name='JRAINBOW1',
            new_count=25,
            min_count=1,
            max_count=100
        )
        self.assertTrue(ok_b, msg_b)

        # Check config persisted under canonical stable keys, NOT collapsed under 'ENE DRAM'
        cfg = self.cfg_mgr.get_config()
        self.assertNotIn('ENE DRAM', cfg['devices'], 'Duplicate name must not be used as persistent config key')
        self.assertIn('ENE DRAM_ramA', cfg['devices'])
        self.assertIn('ENE DRAM_ramB', cfg['devices'])
        self.assertEqual(cfg['devices']['ENE DRAM_ramA']['zone_led_counts']['JRAINBOW1'], 15)
        self.assertEqual(cfg['devices']['ENE DRAM_ramB']['zone_led_counts']['JRAINBOW1'], 25)

        # 3. Verify controller._apply_saved_zone_sizes applies distinct counts
        self.supervisor.resized_zones.clear()
        self.controller._apply_saved_zone_sizes()
        resized = self.supervisor.resized_zones
        self.assertIn(('ENE DRAM_ramA', 0, 15), resized)
        self.assertIn(('ENE DRAM_ramB', 0, 25), resized)

    def test_independent_profile_values_survive_save_load_apply(self):
        cfg = self.cfg_mgr.get_config()
        cfg['devices']['ENE DRAM_ramA'] = {
            'owner': 'thermal_direct',
            'temp_source': {'LED 0': 'gpu'},
            'zone_led_counts': {'JRAINBOW1': 15}
        }
        cfg['devices']['ENE DRAM_ramB'] = {
            'owner': 'hardware_mode',
            'temp_source': {'LED 0': 'cpu'},
            'zone_led_counts': {'JRAINBOW1': 25}
        }
        self.cfg_mgr.save_config(cfg)

        self.assertTrue(self.cfg_mgr.save_profile('DualRAM_Profile'))
        loaded = self.cfg_mgr.load_profile('DualRAM_Profile')
        self.assertIsNotNone(loaded)
        self.assertIn('ENE DRAM_ramA', loaded['devices'])
        self.assertIn('ENE DRAM_ramB', loaded['devices'])
        self.assertEqual(loaded['devices']['ENE DRAM_ramA']['temp_source']['LED 0'], 'gpu')
        self.assertEqual(loaded['devices']['ENE DRAM_ramB']['temp_source']['LED 0'], 'cpu')

        # Mutate config and controller
        self.controller.set_device_owner('ENE DRAM_ramA', 'manual_direct')
        self.controller.set_device_owner('ENE DRAM_ramB', 'thermal_direct')

        # Apply profile
        self.assertTrue(self.cfg_mgr.apply_profile('DualRAM_Profile', controller=self.controller))
        self.assertEqual(self.controller.get_device_owner('ENE DRAM_ramA'), 'thermal_direct')
        self.assertEqual(self.controller.get_device_owner('ENE DRAM_ramB'), 'hardware_mode')

        applied_cfg = self.cfg_mgr.get_config()
        self.assertEqual(applied_cfg['devices']['ENE DRAM_ramA']['zone_led_counts']['JRAINBOW1'], 15)
        self.assertEqual(applied_cfg['devices']['ENE DRAM_ramB']['zone_led_counts']['JRAINBOW1'], 25)

    def test_unique_legacy_msi_b550_resolves(self):
        cfg = self.cfg_mgr.get_config()
        cfg['devices'] = {
            'MSI B550': {
                'owner': 'manual_direct',
                'zone_led_counts': {'JRAINBOW1': 60},
                'temp_source': {'LED 0': 'gpu'}
            }
        }
        cfg['unmatched_legacy_profiles'] = {
            'MSI B550': {
                'default_source': 'gpu',
                'temp_source': {'LED 0': 'gpu'}
            }
        }
        self.cfg_mgr.save_config(cfg)

        # 1. merge_legacy_device_profiles resolves unique legacy name to stable_key
        merged = merge_legacy_device_profiles(
            cfg['devices'],
            cfg['unmatched_legacy_profiles'],
            self.descriptors
        )
        self.assertIn('MSI B550_key', merged)
        self.assertEqual(merged['MSI B550_key']['zone_led_counts']['JRAINBOW1'], 60)

        # 2. _apply_saved_zone_sizes applies legacy unique device
        self.supervisor.resized_zones.clear()
        self.controller._apply_saved_zone_sizes()
        self.assertIn(('MSI B550_key', 0, 60), self.supervisor.resized_zones)

        # 3. reconcile_device_profiles_on_save removes resolved unique legacy from unmatched
        persisted, remaining = reconcile_device_profiles_on_save(
            merged,
            cfg['unmatched_legacy_profiles'],
            descriptors=self.descriptors
        )
        self.assertIn('MSI B550_key', persisted)
        self.assertNotIn('MSI B550', remaining)

    def test_ambiguous_ene_dram_preserved_unmatched_and_rejected(self):
        cfg = self.cfg_mgr.get_config()
        cfg['devices'] = {}
        cfg['unmatched_legacy_profiles'] = {
            'ENE DRAM': {
                'default_source': 'gpu',
                'zone_led_counts': {'JRAINBOW1': 8}
            }
        }
        self.cfg_mgr.save_config(cfg)

        # 1. merge_legacy_device_profiles must NOT merge ambiguous ENE DRAM into devices
        merged = merge_legacy_device_profiles(
            cfg['devices'],
            cfg['unmatched_legacy_profiles'],
            self.descriptors
        )
        self.assertNotIn('ENE DRAM', merged)
        self.assertNotIn('ENE DRAM_ramA', merged)
        self.assertNotIn('ENE DRAM_ramB', merged)

        # 2. reconcile_device_profiles_on_save keeps ambiguous ENE DRAM in remaining unmatched
        persisted, remaining = reconcile_device_profiles_on_save(
            merged,
            cfg['unmatched_legacy_profiles'],
            descriptors=self.descriptors
        )
        self.assertNotIn('ENE DRAM', persisted)
        self.assertIn('ENE DRAM', remaining)
        self.assertEqual(remaining['ENE DRAM']['default_source'], 'gpu')

        # 3. controller._apply_saved_zone_sizes does not resize RAM A or RAM B with ambiguous counts
        self.supervisor.resized_zones.clear()
        self.controller._apply_saved_zone_sizes()
        for target_key, _, _ in self.supervisor.resized_zones:
            self.assertNotIn(target_key, ('ENE DRAM_ramA', 'ENE DRAM_ramB', 'ENE DRAM'))

        # 4. Profile application with ambiguous 'ENE DRAM' does NOT mutate RAM A or RAM B
        ambig_profile = {
            'name': 'LegacyAmbig',
            'devices': {
                'ENE DRAM': {'owner': 'manual_direct'}
            }
        }
        self.cfg_mgr.save_profile('LegacyAmbig', profile_data=ambig_profile)
        self.cfg_mgr.apply_profile('LegacyAmbig', controller=self.controller)
        self.assertEqual(self.controller.get_device_owner('ENE DRAM_ramA'), 'thermal_direct')
        self.assertEqual(self.controller.get_device_owner('ENE DRAM_ramB'), 'thermal_direct')

        # 5. Thermal frame does not apply ambiguous legacy profile source
        self.supervisor.colors_set.clear()
        self.controller._dispatch_thermal_frame()
        # Since RAM A and RAM B have no valid temp from ambiguous legacy config, they should not get written
        # or use default 'cpu' rather than ambiguous 'gpu'
        # Check that ENE DRAM ambiguous config is in unmatched_legacy_profiles
        post_cfg = self.cfg_mgr.get_config()
        self.assertIn('ENE DRAM', post_cfg.get('unmatched_legacy_profiles', {}))

    def test_ambiguous_legacy_in_devices_preserved_on_merge_and_reconcile(self):
        cfg = self.cfg_mgr.get_config()
        cfg['devices'] = {
            'ENE DRAM': {
                'default_source': 'gpu',
                'zone_led_counts': {'JRAINBOW1': 8},
                'temp_source': {'LED 0': 'gpu'},
            }
        }
        cfg['unmatched_legacy_profiles'] = {}
        self.cfg_mgr.save_config(cfg)

        # 1. merge_legacy_device_profiles preserves ambiguous legacy name in returned editable map
        # without assigning it to either duplicate descriptor
        merged = merge_legacy_device_profiles(
            cfg['devices'],
            cfg['unmatched_legacy_profiles'],
            self.descriptors
        )
        self.assertIn('ENE DRAM', merged)
        self.assertNotIn('ENE DRAM_ramA', merged)
        self.assertNotIn('ENE DRAM_ramB', merged)

        # 2. reconcile_device_profiles_on_save moves ambiguous profile to remaining_unmatched
        # and excludes it from persisted canonical devices
        persisted, remaining = reconcile_device_profiles_on_save(
            merged,
            cfg['unmatched_legacy_profiles'],
            descriptors=self.descriptors
        )
        self.assertNotIn('ENE DRAM', persisted)
        self.assertNotIn('ENE DRAM_ramA', persisted)
        self.assertNotIn('ENE DRAM_ramB', persisted)
        self.assertIn('ENE DRAM', remaining)
        self.assertEqual(remaining['ENE DRAM']['default_source'], 'gpu')
        self.assertEqual(remaining['ENE DRAM']['zone_led_counts']['JRAINBOW1'], 8)

        # 3. controller._apply_saved_zone_sizes does not apply ambiguous counts to duplicate hardware
        self.supervisor.resized_zones.clear()
        self.controller._apply_saved_zone_sizes()
        for target_key, _, _ in self.supervisor.resized_zones:
            self.assertNotIn(target_key, ('ENE DRAM_ramA', 'ENE DRAM_ramB', 'ENE DRAM'))

        # 4. Thermal frame does not apply ambiguous legacy source (gpu) to duplicate hardware
        self.controller.smoothed_cpu_temp = 30.0
        self.controller.smoothed_gpu_temp = 75.0
        self.supervisor.colors_set.clear()
        self.controller._dispatch_thermal_frame()
        colors_dict = dict(self.supervisor.colors_set)
        ram_a_colors = colors_dict.get('ENE DRAM_ramA', [])
        self.assertTrue(len(ram_a_colors) > 0)
        self.assertEqual(ram_a_colors[0].red, 0)
        self.assertGreater(ram_a_colors[0].green, 200)


    def test_legacy_same_name_zone_sizes_ignored_for_duplicate_strong_identity_descriptors(self):
        # Two same-name descriptors each have stable keys/strong identity (ambiguous == False)
        self.assertFalse(self.ram_a_desc.ambiguous)
        self.assertFalse(self.ram_b_desc.ambiguous)
        self.assertIsNotNone(self.ram_a_desc.stable_key)
        self.assertIsNotNone(self.ram_b_desc.stable_key)
        self.assertEqual(self.ram_a_desc.name, self.ram_b_desc.name)

        cfg = self.cfg_mgr.get_config()
        cfg['devices'] = {
            'ENE DRAM': {
                'zone_led_counts': {'JRAINBOW1': 8},
            },
            'MSI B550': {
                'zone_led_counts': {'JRAINBOW1': 50},
            },
        }
        cfg['unmatched_legacy_profiles'] = {}
        self.cfg_mgr.save_config(cfg)

        self.supervisor.resized_zones.clear()
        self.controller._apply_saved_zone_sizes()

        # Legacy name fallback must not resize either RAM module with duplicate name
        resized_targets = [item[0] for item in self.supervisor.resized_zones]
        self.assertNotIn('ENE DRAM_ramA', resized_targets)
        self.assertNotIn('ENE DRAM_ramB', resized_targets)
        self.assertNotIn('ENE DRAM', resized_targets)

        # Unique legacy name MSI B550 must be resized successfully
        self.assertIn(('MSI B550_key', 0, 50), self.supervisor.resized_zones)

        # Canonical stable-key entries continue to work for duplicates
        cfg['devices']['ENE DRAM_ramA'] = {'zone_led_counts': {'JRAINBOW1': 16}}
        cfg['devices']['ENE DRAM_ramB'] = {'zone_led_counts': {'JRAINBOW1': 24}}
        self.cfg_mgr.save_config(cfg)

        self.supervisor.resized_zones.clear()
        self.controller._apply_saved_zone_sizes()

        self.assertIn(('ENE DRAM_ramA', 0, 16), self.supervisor.resized_zones)
        self.assertIn(('ENE DRAM_ramB', 0, 24), self.supervisor.resized_zones)


if __name__ == '__main__':
    unittest.main()
