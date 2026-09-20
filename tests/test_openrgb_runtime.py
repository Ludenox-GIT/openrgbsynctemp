import json
import unittest
import sys
import os
import time
import struct
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from openrgb_temp_sync.openrgb_runtime import (
    build_openrgb_launch_args,
    RestartBudget,
    OpenRGBSupervisor,
    EngineState,
    DeviceDescriptor,
    WriteResult,
)
from openrgb_temp_sync.windows_runtime import PortStatus

class MockDevice:
    def __init__(self, name, modes=None, leds=None, **metadata):
        self.name = name
        self.modes = modes or []
        self.leds = leds or []
        self.zones = []
        self.colors = []
        for key, value in metadata.items():
            setattr(self, key, value)
        self.active_mode = 0 if self.modes else None
        # Tests model a device before the first mode refresh from OpenRGB.
        self.active_mode = None
        self.colors_applied = None
        self.mode_applied = None

    def set_mode(self, mode_name):
        self.active_mode = mode_name
        self.mode_applied = mode_name

    def set_colors(self, colors, fast=True):
        self.colors_applied = colors


class MockZone:
    def __init__(self, name, count, minimum=0, maximum=100):
        self.name = name
        self.id = 0
        self.leds = [object() for _ in range(count)]
        self.minimum = minimum
        self.maximum = maximum
        self.resize_calls = []

    def resize(self, size):
        self.resize_calls.append(size)
        self.leds = [object() for _ in range(size)]

class MockMode:
    def __init__(self, name):
        self.name = name

class FakeProcess:
    def __init__(self, exit_code=None):
        self.returncode = exit_code
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 1

    def kill(self):
        self.killed = True
        self.returncode = 1

    def wait(self, timeout=None):
        return self.returncode

class TestOpenRGBRuntime(unittest.TestCase):
    def test_build_openrgb_launch_args(self):
        args = build_openrgb_launch_args(
            r"C:\Program Files\OpenRGB Temp Sync\OpenRGB.exe",
            host="127.0.0.1",
            port=6742,
            config_dir=r"C:\Users\test\AppData\Local\OpenRGBTempSync\openrgb_config"
        )
        self.assertEqual(args[0], r"C:\Program Files\OpenRGB Temp Sync\OpenRGB.exe")
        self.assertIn("--server", args)
        self.assertIn("--server-host", args)
        idx_host = args.index("--server-host")
        self.assertEqual(args[idx_host + 1], "127.0.0.1")
        self.assertIn("--server-port", args)
        idx_port = args.index("--server-port")
        self.assertEqual(args[idx_port + 1], "6742")
        self.assertIn("--config", args)

    def test_restart_budget(self):
        budget = RestartBudget(max_restarts=3, window_seconds=60.0)
        self.assertTrue(budget.record_and_check())
        self.assertTrue(budget.record_and_check())
        self.assertTrue(budget.record_and_check())
        self.assertFalse(budget.record_and_check())

    def test_device_direct_mode_negotiation(self):
        supervisor = OpenRGBSupervisor(binary_path=None)
        dev1 = MockDevice("MSI B550", modes=[MockMode("static"), MockMode("direct")])
        dev2 = MockDevice("ENE DRAM", modes=[MockMode("breathing")])
        
        supervisor.configure_devices_direct_mode([dev1, dev2])
        self.assertEqual(dev1.active_mode, "direct")
        self.assertIsNone(dev2.active_mode)

    def test_set_device_mode_prefers_openrgb_custom_mode_for_direct(self):
        class CustomModeDevice(MockDevice):
            def __init__(self):
                super().__init__("MSI B550", modes=[MockMode("Direct"), MockMode("Static")], device_type="0")
                self.custom_mode_calls = 0

            def set_custom_mode(self):
                self.custom_mode_calls += 1
                self.active_mode = 0
                self.mode_applied = "Direct"

        device = CustomModeDevice()
        supervisor = OpenRGBSupervisor(binary_path=None)
        descriptor = supervisor.refresh_inventory([device])[0]

        self.assertTrue(supervisor.set_device_mode(descriptor.key, "Direct"))
        self.assertEqual(device.custom_mode_calls, 1)
        self.assertIsNone(device.colors_applied)

    def test_set_device_mode_uses_generic_direct_for_dram(self):
        """SetCustomMode is unsafe on ENE DRAM; use the normal Direct mode packet."""
        class DramDevice(MockDevice):
            def __init__(self):
                super().__init__("ENE DRAM", modes=[MockMode("Rainbow"), MockMode("Direct")], device_type="1")
                self.custom_mode_calls = 0
                self.generic_mode_calls = 0

            def set_custom_mode(self):
                self.custom_mode_calls += 1
                raise AssertionError("DRAM must not receive SetCustomMode")

            def set_mode(self, mode_name, save=False):
                self.generic_mode_calls += 1
                super().set_mode(mode_name)

        device = DramDevice()
        supervisor = OpenRGBSupervisor(binary_path=None)
        descriptor = supervisor.refresh_inventory([device])[0]

        self.assertTrue(supervisor.set_device_mode(descriptor.key, "Direct"))
        self.assertEqual(device.custom_mode_calls, 0)
        self.assertEqual(device.generic_mode_calls, 1)

    def test_set_device_mode_does_not_use_custom_mode_for_ene_dram(self):
        class DramDevice(MockDevice):
            def __init__(self):
                super().__init__("ENE DRAM", modes=[MockMode("Direct"), MockMode("Rainbow")])
                self.custom_mode_calls = 0

            def set_custom_mode(self):
                self.custom_mode_calls += 1
                raise AssertionError("SetCustomMode must not be used for ENE DRAM")

        device = DramDevice()
        supervisor = OpenRGBSupervisor(binary_path=None)
        descriptor = supervisor.refresh_inventory([device])[0]

        self.assertTrue(supervisor.set_device_mode(descriptor.key, "Direct"))
        self.assertEqual(device.custom_mode_calls, 0)
        self.assertEqual(device.mode_applied.name, "Direct")

    def test_set_device_mode_marks_supervisor_degraded_when_safe_custom_mode_disconnects(self):
        class OpenRGBDisconnected(ConnectionError):
            pass

        class DisconnectingMsiDevice(MockDevice):
            def __init__(self):
                super().__init__("MSI B550", modes=[MockMode("Direct"), MockMode("Static")])
                self.custom_mode_calls = 0

            def set_custom_mode(self):
                self.custom_mode_calls += 1
                raise OpenRGBDisconnected("SDK server disconnected")

        device = DisconnectingMsiDevice()
        supervisor = OpenRGBSupervisor(binary_path=None)
        descriptor = supervisor.refresh_inventory([device])[0]

        self.assertFalse(supervisor.set_device_mode(descriptor.key, "Direct"))
        self.assertEqual(device.custom_mode_calls, 1)
        self.assertEqual(supervisor.state, EngineState.DEGRADED)
        self.assertIn("disconnected", supervisor.status_message.lower())

    def test_set_mode_converts_ui_direction_label_to_sdk_integer(self):
        """The SDK ModeData.direction field must be an integer/ModeDirections value."""
        class StrictMode(MockMode):
            def pack(self, _version):
                # Reproduce the openrgb-python serializer: a UI string causes
                # the exact ``required argument is not an integer`` failure.
                struct.pack("I", self.direction if self.direction is not None else 0)

        class StrictDevice(MockDevice):
            def set_mode(self, mode, save=False):
                mode.pack(4)
                self.active_mode = self.modes.index(mode)
                self.mode_applied = mode.name

        mode = StrictMode("Rainbow")
        mode.flags = 2  # HAS_DIRECTION_LR
        mode.direction = 0
        device = StrictDevice("ENE DRAM", modes=[mode])
        supervisor = OpenRGBSupervisor(binary_path=None)
        descriptor = supervisor.refresh_inventory([device])[0]

        result = supervisor.set_mode(descriptor.key, "Rainbow", direction="left")

        self.assertTrue(result.ok, result.message)
        self.assertEqual(device.modes[0].direction, 0)

    def test_set_mode_maps_all_openrgb_direction_families(self):
        """LR, UD, and HV labels use OpenRGB's stable 0..5 direction values."""
        expected = {
            "left": (2, 0),
            "right": (2, 1),
            "up": (4, 2),
            "down": (4, 3),
            "horizontal": (8, 4),
            "vertical": (8, 5),
        }

        class StrictMode(MockMode):
            def pack(self, _version):
                struct.pack("I", self.direction if self.direction is not None else 0)

        class StrictDevice(MockDevice):
            def set_mode(self, mode, save=False):
                mode.pack(4)
                self.active_mode = self.modes.index(mode)
                self.mode_applied = mode.name

        for label, (flags, value) in expected.items():
            with self.subTest(direction=label):
                mode = StrictMode("Effect")
                mode.flags = flags
                mode.direction = 0
                device = StrictDevice("Direction Device", modes=[mode])
                supervisor = OpenRGBSupervisor(binary_path=None)
                descriptor = supervisor.refresh_inventory([device])[0]

                result = supervisor.set_mode(descriptor.key, "Effect", direction=label)

                self.assertTrue(result.ok, result.message)
                self.assertEqual(mode.direction, value)

    def test_supervisor_restores_captured_device_baseline(self):
        supervisor = OpenRGBSupervisor(binary_path=None)
        device = MockDevice("MSI B550", modes=[MockMode("Direct"), MockMode("Static")], leds=[object()])
        device.active_mode = 1
        device.colors = [(1, 2, 3)]
        device.zones = [MockZone("JRAINBOW1", 0, minimum=0, maximum=200)]

        supervisor._capture_device_baselines([device])
        device.zones[0].resize(60)
        device.active_mode = 0
        device.colors = [(9, 9, 9)]

        self.assertTrue(supervisor.restore_device("MSI B550"))
        self.assertEqual(device.zones[0].resize_calls[-1], 0)
        self.assertEqual(device.mode_applied.name, "Static")
        self.assertEqual(device.colors_applied, [(1, 2, 3)])

    def test_restore_device_falls_back_to_mode_name_when_sdk_rejects_mode_object(self):
        class IntOnlyModeDevice(MockDevice):
            def set_mode(self, mode, *args, **kwargs):
                if not isinstance(mode, (str, int)):
                    raise TypeError("required argument is not an integer")
                self.active_mode = mode
                self.mode_applied = mode

        supervisor = OpenRGBSupervisor(binary_path=None)
        device = IntOnlyModeDevice(
            "ENE DRAM",
            modes=[MockMode("Direct"), MockMode("Rainbow")],
            leds=[object()]
        )
        device.active_mode = 1
        device.colors = [(1, 2, 3)]
        supervisor.refresh_inventory([device])

        device.active_mode = 0
        device.colors = [(9, 9, 9)]

        self.assertTrue(supervisor.restore_device("ENE DRAM"))
        self.assertEqual(device.mode_applied, "Rainbow")
        self.assertEqual(device.colors_applied, [(1, 2, 3)])

    def test_restore_device_falls_back_when_sdk_rejects_mode_object_with_value_error(self):
        class ValueErrorModeDevice(MockDevice):
            def set_mode(self, mode, *args, **kwargs):
                if not isinstance(mode, (str, int)):
                    raise ValueError("mode packet requires an integer")
                self.active_mode = mode
                self.mode_applied = mode

        supervisor = OpenRGBSupervisor(binary_path=None)
        device = ValueErrorModeDevice(
            "ENE DRAM",
            modes=[MockMode("Direct"), MockMode("Rainbow")],
            leds=[object()]
        )
        device.active_mode = 1
        device.colors = [(1, 2, 3)]
        supervisor.refresh_inventory([device])

        device.active_mode = 0
        device.colors = [(9, 9, 9)]

        self.assertTrue(supervisor.restore_device("ENE DRAM"))
        self.assertEqual(device.mode_applied, "Rainbow")
        self.assertEqual(device.colors_applied, [(1, 2, 3)])

    def test_restore_device_accepts_persisted_vendor_baseline_when_runtime_snapshot_missing(self):
        supervisor = OpenRGBSupervisor(binary_path=None)
        device = MockDevice(
            "ENE DRAM",
            modes=[MockMode("Direct"), MockMode("Rainbow")],
            leds=[object()]
        )
        device.active_mode = 1
        device.colors = [(1, 2, 3)]
        descriptor = supervisor.refresh_inventory([device])[0]
        persisted = next(iter(supervisor.serialize_vendor_baseline().values()))
        supervisor._device_baselines = {}

        device.active_mode = 0
        device.colors = [(9, 9, 9)]

        self.assertTrue(supervisor.restore_device(descriptor.key, persisted_baseline=persisted))
        self.assertEqual(device.mode_applied.name, "Rainbow")
        self.assertEqual(device.colors_applied, [(1, 2, 3)])

    def test_restore_device_prefers_explicit_persisted_baseline_over_runtime_snapshot(self):
        supervisor = OpenRGBSupervisor(binary_path=None)
        device = MockDevice(
            "MSI B550",
            modes=[MockMode("Direct"), MockMode("Static"), MockMode("Rainbow wave")],
            leds=[object()],
        )
        device.active_mode = 1
        device.colors = [(1, 2, 3)]
        descriptor = supervisor.refresh_inventory([device])[0]
        # Capture a runtime snapshot that differs from the requested vendor
        # baseline, then verify the explicit baseline wins.
        persisted = {
            "stable_key": descriptor.stable_key,
            "name": device.name,
            "mode_name": "Rainbow wave",
            "active_mode": 2,
            "colors": [[4, 5, 6]],
            "zone_led_counts": [],
        }
        device.active_mode = 0
        device.colors = [(9, 9, 9)]

        self.assertTrue(supervisor.restore_device_from_baseline(descriptor.key, persisted))
        self.assertEqual(device.mode_applied.name, "Rainbow wave")
        self.assertEqual(device.colors_applied, [(4, 5, 6)])

    def test_restore_device_enters_direct_before_restoring_zone_counts(self):
        class DirectZoneDevice(MockDevice):
            def __init__(self):
                super().__init__("MSI B550", modes=[MockMode("Direct"), MockMode("Rainbow wave")])
                self.active_mode = 1
                self.colors = [(1, 2, 3)]
                self.zones = [MockZone("JRAINBOW1", 2, minimum=0, maximum=200)]
                self.custom_mode_calls = 0

            def set_custom_mode(self):
                self.custom_mode_calls += 1
                self.active_mode = 0

            def set_mode(self, mode_name, *args, **kwargs):
                self.mode_applied = mode_name
                self.active_mode = 1 if getattr(mode_name, "name", mode_name) == "Rainbow wave" else 0

        supervisor = OpenRGBSupervisor(binary_path=None)
        device = DirectZoneDevice()
        supervisor.refresh_inventory([device])
        device.zones[0].resize(0)

        self.assertTrue(supervisor.restore_device("MSI B550"))
        self.assertEqual(device.custom_mode_calls, 1)
        self.assertEqual(len(device.zones[0].leds), 2)

    def test_supervisor_resizes_only_within_zone_limits(self):
        supervisor = OpenRGBSupervisor(binary_path=None)
        device = MockDevice("MSI B550")
        zone = MockZone("JRAINBOW1", 0, minimum=0, maximum=200)
        device.zones = [zone]
        supervisor.devices = [device]

        self.assertTrue(supervisor.resize_zone("MSI B550", 0, 60))
        self.assertEqual(len(zone.leds), 60)
        self.assertFalse(supervisor.resize_zone("MSI B550", 0, 201))
        self.assertEqual(len(zone.leds), 60)

    @patch("openrgb_temp_sync.openrgb_runtime.inspect_port_6742")
    def test_supervisor_early_exit_returns_degraded(self, mock_port_inspect):
        mock_port_inspect.return_value = (PortStatus.FREE, "Port is free", None)
        fake_proc = FakeProcess(exit_code=127)
        fake_binary = os.path.abspath(__file__)

        supervisor = OpenRGBSupervisor(
            binary_path=fake_binary,
            readiness_timeout_seconds=0.3,
            popen_factory=lambda *a, **kw: fake_proc,
            port_checker=lambda: False
        )
        state, msg = supervisor.start()
        self.assertEqual(state, EngineState.DEGRADED)
        self.assertIn("prematurely", msg.lower())
        self.assertFalse(supervisor.is_owned())

    @patch("openrgb_temp_sync.openrgb_runtime.is_process_elevated", return_value=False)
    @patch("openrgb_temp_sync.openrgb_runtime.inspect_port_6742")
    def test_supervisor_rejects_bundled_engine_without_elevation(self, mock_port_inspect, _mock_elevated):
        mock_port_inspect.return_value = (PortStatus.FREE, "Port is free", None)
        supervisor = OpenRGBSupervisor(
            binary_path=os.path.abspath(__file__),
            require_elevation=True,
        )

        state, msg = supervisor.start()

        self.assertEqual(state, EngineState.DEGRADED)
        self.assertIn("administrator", msg.lower())

    @patch("openrgb_temp_sync.openrgb_runtime.inspect_port_6742")
    def test_supervisor_readiness_timeout_returns_degraded(self, mock_port_inspect):
        mock_port_inspect.return_value = (PortStatus.FREE, "Port is free", None)
        fake_proc = FakeProcess(exit_code=None)
        fake_binary = os.path.abspath(__file__)

        supervisor = OpenRGBSupervisor(
            binary_path=fake_binary,
            readiness_timeout_seconds=0.2,
            popen_factory=lambda *a, **kw: fake_proc,
            port_checker=lambda: False
        )
        state, msg = supervisor.start()
        self.assertEqual(state, EngineState.DEGRADED)
        self.assertIn("timed out", msg.lower())
        self.assertTrue(fake_proc.terminated)
        self.assertFalse(supervisor.is_owned())

    @patch("openrgb_temp_sync.openrgb_runtime.inspect_port_6742")
    def test_supervisor_readiness_success_returns_running_owned(self, mock_port_inspect):
        mock_port_inspect.return_value = (PortStatus.FREE, "Port is free", None)
        fake_proc = FakeProcess(exit_code=None)
        fake_binary = os.path.abspath(__file__)

        supervisor = OpenRGBSupervisor(
            binary_path=fake_binary,
            readiness_timeout_seconds=0.5,
            popen_factory=lambda *a, **kw: fake_proc,
            port_checker=lambda: True,
            client_connector=lambda: True
        )
        state, msg = supervisor.start()
        self.assertEqual(state, EngineState.RUNNING_OWNED)
        self.assertTrue(supervisor.is_owned())

        supervisor.stop()
        self.assertTrue(fake_proc.terminated)
        self.assertFalse(supervisor.is_owned())

    @patch("openrgb_temp_sync.openrgb_runtime.inspect_port_6742")
    def test_supervisor_waits_for_hardware_detection_before_sdk_connect(self, mock_port_inspect):
        mock_port_inspect.return_value = (PortStatus.FREE, "Port is free", None)
        fake_proc = FakeProcess(exit_code=None)
        fake_binary = os.path.abspath(__file__)
        connector = Mock(return_value=True)

        supervisor = OpenRGBSupervisor(
            binary_path=fake_binary,
            readiness_timeout_seconds=0.5,
            device_detection_delay_seconds=0.01,
            popen_factory=lambda *a, **kw: fake_proc,
            port_checker=lambda: True,
            client_connector=connector
        )
        state, _ = supervisor.start()
        self.assertEqual(state, EngineState.RUNNING_OWNED)
        connector.assert_called_once_with()
        supervisor.stop()

    @patch("openrgb_temp_sync.openrgb_runtime.inspect_port_6742")
    def test_supervisor_preserves_external_server_safety(self, mock_port_inspect):
        mock_port_inspect.return_value = (PortStatus.COMPATIBLE_EXTERNAL, "Compatible External OpenRGB", 4321)
        fake_binary = os.path.abspath(__file__)

        supervisor = OpenRGBSupervisor(binary_path=fake_binary, client_connector=lambda: True)
        state, msg = supervisor.start()
        self.assertEqual(state, EngineState.RUNNING_EXTERNAL)
        self.assertFalse(supervisor.is_owned(), "External server must never be marked as owned")

        supervisor.stop()
        self.assertEqual(supervisor.state, EngineState.STOPPED)
        self.assertIsNone(supervisor._process)

    @patch("openrgb_temp_sync.openrgb_runtime.inspect_port_6742")
    def test_supervisor_owned_client_connector_failure_cleans_up_and_degrades(self, mock_port_inspect):
        mock_port_inspect.return_value = (PortStatus.FREE, "Port is free", None)
        fake_proc = FakeProcess(exit_code=None)
        fake_binary = os.path.abspath(__file__)

        supervisor = OpenRGBSupervisor(
            binary_path=fake_binary,
            readiness_timeout_seconds=0.5,
            popen_factory=lambda *a, **kw: fake_proc,
            port_checker=lambda: True,
            client_connector=lambda: False
        )
        state, msg = supervisor.start()
        self.assertEqual(state, EngineState.DEGRADED)
        self.assertIn("failed", msg.lower())
        self.assertTrue(fake_proc.terminated, "Owned process must undergo bounded cleanup on connector failure")
        self.assertFalse(supervisor.is_owned())
        self.assertIsNone(supervisor._process)

    @patch("openrgb_temp_sync.openrgb_runtime.inspect_port_6742")
    def test_supervisor_external_client_connector_failure_retains_safety_and_degrades(self, mock_port_inspect):
        mock_port_inspect.return_value = (PortStatus.COMPATIBLE_EXTERNAL, "Compatible External OpenRGB", 4321)
        fake_binary = os.path.abspath(__file__)

        supervisor = OpenRGBSupervisor(binary_path=fake_binary, client_connector=lambda: False)
        state, msg = supervisor.start()
        self.assertEqual(state, EngineState.DEGRADED)
        self.assertIn("failed", msg.lower())
        self.assertFalse(supervisor.is_owned(), "External server must never be marked as owned on failure")
        self.assertIsNone(supervisor._process, "External server process must never be tracked or killed")

    @patch.object(OpenRGBSupervisor, "_check_port_ready", return_value=False)
    def test_supervisor_connect_client_returns_boolean(self, mock_port_ready):
        supervisor = OpenRGBSupervisor(binary_path=None)
        # When port is not ready, must deterministically return False without connecting
        result = supervisor._connect_client()
        self.assertIsInstance(result, bool)
        self.assertFalse(result)

    @patch("openrgb.OpenRGBClient")
    def test_supervisor_disconnects_failed_sdk_client(self, mock_client_cls):
        class FailingClient:
            def __init__(self):
                self.disconnect = Mock()

            @property
            def devices(self):
                raise TimeoutError("offline")

        client = FailingClient()
        mock_client_cls.return_value = client
        # A failed constructor/device handshake must not leave the SDK socket open.
        supervisor = OpenRGBSupervisor(binary_path=None)
        supervisor._check_port_ready = lambda: True
        result = supervisor._connect_client()
        self.assertFalse(result)
        client.disconnect.assert_called_once()

    @patch("openrgb.OpenRGBClient")
    def test_connect_client_does_not_write_direct_mode(self, mock_client_cls):
        device = MockDevice("MSI B550", modes=[MockMode("Static"), MockMode("Direct")])
        client = Mock(devices=[device])
        mock_client_cls.return_value = client

        supervisor = OpenRGBSupervisor(binary_path=None)
        supervisor._check_port_ready = lambda: True

        self.assertTrue(supervisor._connect_client())
        self.assertIsNone(device.mode_applied)

    def test_set_colors_refreshes_readback_before_reporting_success(self):
        class ReadbackDevice(MockDevice):
            def __init__(self):
                super().__init__("Readback Device")
                self._pending_colors = None

            def set_colors(self, colors, fast=True):
                self._pending_colors = list(colors)

            def update(self):
                self.colors = list(self._pending_colors or [])

        device = ReadbackDevice()
        supervisor = OpenRGBSupervisor(binary_path=None)
        descriptor = supervisor.refresh_inventory([device])[0]

        requested = [(255, 0, 0)]
        result = supervisor.set_colors(descriptor.key, requested, fast=True)

        self.assertTrue(result.ok)
        self.assertEqual(result.readback, requested)

    def test_set_colors_reports_readback_mismatch_when_missing(self):
        device = MockDevice("No Readback Device")
        device.colors = None
        supervisor = OpenRGBSupervisor(binary_path=None)
        descriptor = supervisor.refresh_inventory([device])[0]

        result = supervisor.set_colors(descriptor.key, [(255, 0, 0)])

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "readback_mismatch")

    def test_set_colors_reports_readback_mismatch_when_stale(self):
        device = MockDevice("Stale Readback Device")
        device.colors = [(0, 0, 0)]
        supervisor = OpenRGBSupervisor(binary_path=None)
        descriptor = supervisor.refresh_inventory([device])[0]

        result = supervisor.set_colors(descriptor.key, [(255, 0, 0)])

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "readback_mismatch")

    def test_same_name_devices_get_separate_session_identity_and_baselines(self):
        supervisor = OpenRGBSupervisor(binary_path=None)
        ram_a = MockDevice("ENE DRAM", serial="RAM-A")
        ram_b = MockDevice("ENE DRAM", serial="RAM-B")
        ram_a.colors = [(1, 2, 3)]
        ram_b.colors = [(4, 5, 6)]

        descriptors = supervisor.refresh_inventory([ram_a, ram_b])

        self.assertEqual(len({item.key for item in descriptors}), 2)
        self.assertEqual(len(supervisor._device_baselines), 2)
        self.assertNotEqual(descriptors[0].key, descriptors[1].key)
        self.assertTrue(all(item.stable_key for item in descriptors))

    def test_ambiguous_duplicate_name_rejects_write(self):
        supervisor = OpenRGBSupervisor(binary_path=None)
        supervisor.refresh_inventory([MockDevice("ENE DRAM"), MockDevice("ENE DRAM")])

        result = supervisor.set_colors("ENE DRAM", [(255, 0, 0)])

        self.assertIsInstance(result, WriteResult)
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "ambiguous")

    def test_rescan_preserves_stable_key_when_sdk_index_changes(self):
        supervisor = OpenRGBSupervisor(binary_path=None)
        first = supervisor.refresh_inventory([
            MockDevice("ENE DRAM", serial="RAM-A"),
            MockDevice("ENE DRAM", serial="RAM-B"),
        ])
        first_keys = {item.serial: item.key for item in first}

        second = supervisor.refresh_inventory([
            MockDevice("ENE DRAM", serial="RAM-B"),
            MockDevice("ENE DRAM", serial="RAM-A"),
        ])

        self.assertEqual(first_keys, {item.serial: item.key for item in second})
        self.assertEqual([item.session_index for item in second], [0, 1])


    def test_serialize_vendor_baseline_canonical_keys_evidence_and_json_safe(self):
        supervisor = OpenRGBSupervisor(binary_path=None)
        ram_a = MockDevice("ENE DRAM", serial="RAM-A", vendor_id="0x0b05", product_id="0x18f3", location="DIMM_1")
        ram_b = MockDevice("ENE DRAM", serial="RAM-B", vendor_id="0x0b05", product_id="0x18f3", location="DIMM_2")
        gpu = MockDevice("Gigabyte AORUS RTX 3060 ELITE LHR", vendor_id="0x1458", product_id="0x403c")
        mb = MockDevice("MSI MAG B550 TOMAHAWK", path="msi_tomahawk_path")

        ram_a.colors = [(255, 0, 0), (0, 255, 0)]
        ram_b.colors = [(0, 0, 255), (255, 255, 0)]
        gpu.colors = [(255, 255, 255)]
        mb.colors = [(10, 20, 30)]

        zone_a = MockZone("Zone 0", count=2)
        ram_a.zones = [zone_a]
        zone_b = MockZone("Zone 0", count=2)
        ram_b.zones = [zone_b]
        zone_gpu = MockZone("GPU Zone", count=1)
        gpu.zones = [zone_gpu]
        zone_mb = MockZone("MB Zone", count=1)
        mb.zones = [zone_mb]

        class MockModeObj:
            def __init__(self, name, value=1):
                self.name = name
                self.value = value

        gpu.modes = [MockModeObj("Static", 0), MockModeObj("Breathe", 1)]
        gpu.active_mode = 1

        supervisor.refresh_inventory([ram_a, ram_b, gpu, mb])
        baseline = supervisor.serialize_vendor_baseline()

        # Two same-name ENE DRAM devices retain independent baseline entries
        self.assertEqual(len(baseline), 4)
        self.assertNotIn("ENE DRAM", baseline, "Ambiguous display name must never be the canonical key")

        # Check JSON-safety and round-trip
        json_str = json.dumps(baseline)
        roundtripped = json.loads(json_str)
        self.assertEqual(roundtripped, baseline)

        # Check GPU entry details
        gpu_keys = [k for k, v in baseline.items() if v["name"] == "Gigabyte AORUS RTX 3060 ELITE LHR"]
        self.assertEqual(len(gpu_keys), 1)
        gpu_entry = baseline[gpu_keys[0]]
        self.assertEqual(gpu_entry["active_mode"], 1)
        self.assertEqual(gpu_entry["mode_name"], "Breathe")
        self.assertEqual(gpu_entry["colors"], [[255, 255, 255]])
        self.assertEqual(gpu_entry["zone_led_counts"], [1])
        self.assertEqual(gpu_entry["vendor_id"], "0x1458")
        self.assertEqual(gpu_entry["product_id"], "0x403c")
        self.assertIn("identity_evidence", gpu_entry)

    def test_serialize_vendor_baseline_is_read_only(self):
        class MutatorTrackingDevice(MockDevice):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.mutator_called = []

            def set_mode(self, *args, **kwargs):
                self.mutator_called.append("set_mode")
                return super().set_mode(*args, **kwargs)

            def set_colors(self, *args, **kwargs):
                self.mutator_called.append("set_colors")
                return super().set_colors(*args, **kwargs)

            def set_color(self, *args, **kwargs):
                self.mutator_called.append("set_color")

            def resize(self, *args, **kwargs):
                self.mutator_called.append("resize")

            def save_mode(self, *args, **kwargs):
                self.mutator_called.append("save_mode")

            def save(self, *args, **kwargs):
                self.mutator_called.append("save")

            def configure_direct(self, *args, **kwargs):
                self.mutator_called.append("configure_direct")

        device = MutatorTrackingDevice("MSI MAG B550 TOMAHAWK")
        device.colors = [(100, 150, 200)]
        supervisor = OpenRGBSupervisor(binary_path=None)
        supervisor.refresh_inventory([device])
        device.mutator_called.clear()

        _ = supervisor.serialize_vendor_baseline()
        self.assertEqual(device.mutator_called, [], "Capture must not call any SDK mutator methods")

    def test_vendor_baseline_keeps_manufacturer_reset_fail_closed(self):
        supervisor = OpenRGBSupervisor(binary_path=None)
        device = MockDevice("MSI MAG B550 TOMAHAWK")
        desc = supervisor.refresh_inventory([device])[0]
        _ = supervisor.serialize_vendor_baseline()

        # Baseline capture must not verify OEM reset
        cap = supervisor.get_reset_capability(desc.key)
        self.assertNotEqual(cap.status, "verified")

        res = supervisor.restore_manufacturer_defaults(desc.key)
        self.assertFalse(res.ok)
        self.assertIn(res.error_code, ("reset_rejected", "not_implemented"))

if __name__ == '__main__':
    unittest.main()
