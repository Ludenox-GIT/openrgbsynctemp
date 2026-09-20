import unittest
import sys
import os
import tempfile
import shutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from openrgb_temp_sync.controller import SyncController, ControllerState
from openrgb_temp_sync.config import ConfigManager
from openrgb_temp_sync.openrgb_runtime import EngineState, WriteResult


class MockOpenRGBSupervisor:
    def __init__(self, state=EngineState.STOPPED, msg='Stopped', devices=None):
        self.state = state
        self.status_message = msg
        self.devices = devices or []
        self.restored = []
        self.resized = []
        self.colors_set = []

    def start(self):
        return self.state, self.status_message

    def stop(self):
        self.state = EngineState.STOPPED
        self.status_message = 'Stopped'

    def get_devices(self):
        return self.devices
    def get_descriptors(self):
        from openrgb_temp_sync.openrgb_runtime import DeviceDescriptor
        descs = []
        for idx, dev in enumerate(self.devices):
            name = getattr(dev, "name", "Device")
            descs.append(DeviceDescriptor(key=name, name=name, display_name=name, session_index=idx, stable_key=name))
        return descs

    def is_owned(self):
        return self.state == EngineState.RUNNING_OWNED

    def restore_device(self, device_name):
        self.restored.append(device_name)
        return True

    def set_device_mode(self, target_key, mode_name):
        for dev in self.devices:
            if getattr(dev, "name", "") == target_key:
                for m in getattr(dev, "modes", []):
                    if getattr(m, "name", "").lower() == mode_name.lower():
                        if hasattr(dev, "set_mode"):
                            dev.set_mode(getattr(m, "name", mode_name))
                        return True
        return False

    def resize_zone(self, device_name, zone_index, size):
        self.resized.append((device_name, zone_index, size))
        return True

    def set_colors(self, target_key, colors, fast=True):
        self.colors_set.append((target_key, colors))
        return WriteResult(ok=True, target_key=target_key)


class MockSensorSupervisor:
    def __init__(self):
        self.status = 'OK'

    def start(self):
        pass

    def stop(self):
        pass

    def get_status(self):
        return self.status

    def get_latest_reading(self):
        return None

    def get_recent_stderr(self):
        return []


class TestController(unittest.TestCase):
    def setUp(self):
        self.config_mgr = ConfigManager()
        self.controller = SyncController(config_manager=self.config_mgr)

    def test_controller_initial_snapshot(self):
        snapshot = self.controller.get_status_snapshot()
        self.assertIn('state', snapshot)
        self.assertEqual(snapshot['state'], ControllerState.IDLE)
        self.assertFalse(snapshot['is_lights_off'])
        self.assertEqual(snapshot['device_count'], 0)

    def test_controller_toggle_lights_off(self):
        self.controller.set_lights_off(True)
        snapshot = self.controller.get_status_snapshot()
        self.assertTrue(snapshot['is_lights_off'])
        self.assertEqual(snapshot['state'], ControllerState.LIGHTS_OFF)

        self.controller.set_lights_off(False)
        snapshot = self.controller.get_status_snapshot()
        self.assertFalse(snapshot['is_lights_off'])

    def test_status_snapshot_surfaces_degraded_openrgb_socket(self):
        mock_engine = MockOpenRGBSupervisor(
            state=EngineState.DEGRADED,
            msg='OpenRGB SDK disconnected; retry engine'
        )
        ctrl = SyncController(
            config_manager=self.config_mgr,
            openrgb_supervisor=mock_engine,
            sensor_supervisor=MockSensorSupervisor()
        )

        snapshot = ctrl.get_status_snapshot()

        self.assertEqual(snapshot['engine_label'], 'OpenRGB')
        self.assertEqual(snapshot['status_text'], 'OpenRGB SDK disconnected; retry engine')

    def test_reset_device_restores_original_and_excludes_it_from_sync(self):
        mock_engine = MockOpenRGBSupervisor(state=EngineState.RUNNING_OWNED, msg='Running')
        ctrl = SyncController(
            config_manager=self.config_mgr,
            openrgb_supervisor=mock_engine,
            sensor_supervisor=MockSensorSupervisor()
        )

        self.assertTrue(ctrl.reset_device_to_original('MSI B550'))
        self.assertEqual(mock_engine.restored, ['MSI B550'])
        self.assertTrue(ctrl.is_device_reset('MSI B550'))
        self.assertTrue(ctrl.resume_device('MSI B550'))
        self.assertFalse(ctrl.is_device_reset('MSI B550'))

    def test_reset_device_falls_back_to_confirmed_vendor_default_snapshot(self):
        class SnapshotFallbackSupervisor(MockOpenRGBSupervisor):
            def __init__(self):
                super().__init__(state=EngineState.RUNNING_OWNED, msg='Running')
                self.persisted_restores = []

            def restore_device(self, device_name):
                return False

            def restore_device_from_baseline(self, device_name, baseline):
                self.persisted_restores.append((device_name, baseline))
                return True

        temp_dir = tempfile.mkdtemp()
        try:
            config_path = os.path.join(temp_dir, "config.json")
            config_mgr = ConfigManager(config_path=config_path, backup_dir=os.path.join(temp_dir, "backups"))
            config_mgr.capture_vendor_baseline(
                "vendor_default",
                {"MSI_B550": {"stable_key": "MSI_B550", "name": "MSI B550", "colors": [[1, 2, 3]]}}
            )
            mock_engine = SnapshotFallbackSupervisor()
            ctrl = SyncController(
                config_manager=config_mgr,
                openrgb_supervisor=mock_engine,
                sensor_supervisor=MockSensorSupervisor()
            )

            self.assertTrue(ctrl.reset_device_to_original('MSI B550'))
            self.assertEqual(len(mock_engine.persisted_restores), 1)
            self.assertEqual(mock_engine.persisted_restores[0][1]["colors"], [[1, 2, 3]])
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_redacted_diagnostics_export(self):
        diag = self.controller.export_diagnostics()
        self.assertIn('app_version', diag)
        self.assertIn('controller_state', diag)
        self.assertIn('engine_status', diag)
        self.assertIn('sensor_status', diag)
        self.assertIn('port_6742', diag)
        self.assertNotIn('password', diag)
        self.assertNotIn('token', diag)

    def test_start_engine_degraded_maps_to_degraded_state(self):
        mock_sup = MockOpenRGBSupervisor(state=EngineState.DEGRADED, msg='Bundled OpenRGB failed to initialize')
        mock_sensor = MockSensorSupervisor()
        ctrl = SyncController(
            config_manager=self.config_mgr,
            openrgb_supervisor=mock_sup,
            sensor_supervisor=mock_sensor
        )

        ctrl.start()
        self.assertEqual(ctrl.state, ControllerState.DEGRADED_ENGINE)
        self.assertFalse(ctrl.running, 'Controller must not claim running when engine is degraded')
        self.assertIsNone(ctrl._loop_thread, 'Lighting loop thread must not run when engine is degraded')

    def test_start_engine_stopped_maps_to_degraded_state(self):
        mock_sup = MockOpenRGBSupervisor(state=EngineState.STOPPED, msg='Engine stopped')
        mock_sensor = MockSensorSupervisor()
        ctrl = SyncController(
            config_manager=self.config_mgr,
            openrgb_supervisor=mock_sup,
            sensor_supervisor=mock_sensor
        )

        ctrl.start()
        self.assertEqual(ctrl.state, ControllerState.DEGRADED_ENGINE)
        self.assertFalse(ctrl.running, 'Controller must not claim running when engine is stopped')
        self.assertIsNone(ctrl._loop_thread)

    def test_sensor_health_blocks_writes_and_recovers(self):
        mock_engine = MockOpenRGBSupervisor(state=EngineState.RUNNING_OWNED, msg='Running')
        mock_sensor = MockSensorSupervisor()
        mock_sensor.status = 'OFFLINE'
        ctrl = SyncController(
            config_manager=self.config_mgr,
            openrgb_supervisor=mock_engine,
            sensor_supervisor=mock_sensor
        )
        ctrl.state = ControllerState.RUNNING_OWNED
        self.assertFalse(ctrl._sensor_allows_updates())
        self.assertEqual(ctrl.state, ControllerState.DEGRADED_SENSOR)
        self.assertIn('Sensor unavailable', ctrl.status_text)

        mock_sensor.status = 'OK'
        self.assertTrue(ctrl._sensor_allows_updates())
        self.assertEqual(ctrl.state, ControllerState.RUNNING_OWNED)

    def test_serialized_owner_transition_blocks_thermal_overwrite(self):
        mock_engine = MockOpenRGBSupervisor(state=EngineState.RUNNING_OWNED, msg='Running')
        ctrl = SyncController(
            config_manager=self.config_mgr,
            openrgb_supervisor=mock_engine,
            sensor_supervisor=MockSensorSupervisor()
        )
        self.assertTrue(ctrl.reset_device_to_original('MSI B550'))
        self.assertEqual(ctrl.get_device_owner('MSI B550'), 'resetting')
        self.assertFalse(ctrl.can_apply_thermal_frame('MSI B550'))

    def test_resume_negotiates_direct_mode(self):
        mock_engine = MockOpenRGBSupervisor(state=EngineState.RUNNING_OWNED, msg='Running')
        ctrl = SyncController(
            config_manager=self.config_mgr,
            openrgb_supervisor=mock_engine,
            sensor_supervisor=MockSensorSupervisor()
        )
        ctrl.reset_device_to_original('MSI B550')
        self.assertTrue(ctrl.resume_device('MSI B550'))
        self.assertEqual(ctrl.get_device_owner('MSI B550'), 'thermal_direct')

    def test_lights_off_honors_unmanaged_and_held_state(self):
        mock_engine = MockOpenRGBSupervisor(state=EngineState.RUNNING_OWNED, msg='Running')
        ctrl = SyncController(
            config_manager=self.config_mgr,
            openrgb_supervisor=mock_engine,
            sensor_supervisor=MockSensorSupervisor()
        )
        ctrl.reset_device_to_original('RAM-A')
        ctrl.set_lights_off(True)
        self.assertTrue(ctrl.is_device_reset('RAM-A'))
        ctrl.set_lights_off(False)
        self.assertTrue(ctrl.is_device_reset('RAM-A'))


    def test_resume_negotiates_direct_mode_calls_set_mode_direct_on_device(self):
        class MockMode:
            def __init__(self, name):
                self.name = name

        class MockDev:
            def __init__(self, name):
                self.name = name
                self.modes = [MockMode("Static"), MockMode("Direct")]
                self.mode_set = []

            def set_mode(self, mode):
                self.mode_set.append(mode)

        mock_dev = MockDev("MSI B550")
        mock_engine = MockOpenRGBSupervisor(state=EngineState.RUNNING_OWNED, msg="Running", devices=[mock_dev])
        ctrl = SyncController(
            config_manager=self.config_mgr,
            openrgb_supervisor=mock_engine,
            sensor_supervisor=MockSensorSupervisor()
        )
        ctrl.reset_device_to_original("MSI B550")
        self.assertTrue(ctrl.resume_device("MSI B550"))
        self.assertEqual(mock_dev.mode_set, ["Direct"])

    def test_lights_off_serialized_records_writes_and_skips_held_targets(self):
        class MockDev:
            def __init__(self, name):
                self.name = name

        mock_dev1 = MockDev("Motherboard")
        mock_dev2 = MockDev("RAM-A")
        mock_engine = MockOpenRGBSupervisor(state=EngineState.RUNNING_OWNED, msg="Running", devices=[mock_dev1, mock_dev2])
        ctrl = SyncController(
            config_manager=self.config_mgr,
            openrgb_supervisor=mock_engine,
            sensor_supervisor=MockSensorSupervisor()
        )
        ctrl.reset_device_to_original("RAM-A")
        ctrl.set_lights_off(True)
        targets_written = [call[0] for call in mock_engine.colors_set]
        self.assertIn("Motherboard", targets_written)
        self.assertNotIn("RAM-A", targets_written)

    def test_run_loop_thermal_frame_routes_through_supervisor_set_colors(self):
        class MockLed:
            def __init__(self, name):
                self.name = name

        class MockDev:
            def __init__(self, name):
                self.name = name
                self.leds = [MockLed("LED 0")]

        mock_dev = MockDev("GPU")
        mock_engine = MockOpenRGBSupervisor(state=EngineState.RUNNING_OWNED, msg="Running", devices=[mock_dev])
        ctrl = SyncController(
            config_manager=self.config_mgr,
            openrgb_supervisor=mock_engine,
            sensor_supervisor=MockSensorSupervisor()
        )
        ctrl.smoothed_cpu_temp = 50.0
        ctrl._dispatch_thermal_frame()
        targets_written = [call[0] for call in mock_engine.colors_set]
        self.assertIn("GPU", targets_written)

if __name__ == '__main__':
    unittest.main()
