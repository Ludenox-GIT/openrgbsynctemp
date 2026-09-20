import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from openrgb_temp_sync.windows_runtime import (
    build_schtasks_create_command,
    build_schtasks_delete_command,
    is_loopback_address,
    classify_port_listener,
    PortStatus,
    WindowsJobObject
)
from openrgb_temp_sync.config import ConfigManager
from openrgb_temp_sync.ui import SettingsGUI


class MockController:
    def __init__(self):
        self.openrgb_supervisor = self
        self.running = False

    def get_status_snapshot(self):
        return {
            "engine_label": "None",
            "status_text": "Idle",
            "device_count": 0,
            "devices": []
        }

    def get_devices(self):
        return []

    def export_diagnostics(self):
        return {"test": True}

    def retry(self):
        pass


class TestWindowsRuntime(unittest.TestCase):
    def test_build_schtasks_create_command(self):
        cmd = build_schtasks_create_command(r"C:\Program Files\OpenRGB Temp Sync\OpenRGBTempSync.exe")
        self.assertIn("schtasks.exe", cmd[0].lower())
        self.assertIn("/Create", cmd)
        self.assertIn("/TN", cmd)
        self.assertIn("OpenRGBTempSync", cmd)
        self.assertIn("/SC", cmd)
        self.assertIn("ONLOGON", cmd)
        self.assertIn("/RL", cmd)
        self.assertIn("HIGHEST", cmd)

    def test_build_schtasks_delete_command(self):
        cmd = build_schtasks_delete_command()
        self.assertIn("schtasks.exe", cmd[0].lower())
        self.assertIn("/Delete", cmd)
        self.assertIn("/TN", cmd)
        self.assertIn("OpenRGBTempSync", cmd)

    def test_is_loopback_address(self):
        self.assertTrue(is_loopback_address("127.0.0.1"))
        self.assertTrue(is_loopback_address("127.0.0.2"))
        self.assertTrue(is_loopback_address("::1"))
        self.assertFalse(is_loopback_address("0.0.0.0"))
        self.assertFalse(is_loopback_address("192.168.1.50"))
        self.assertFalse(is_loopback_address("10.0.0.1"))

    def test_classify_port_listener_free(self):
        status, details = classify_port_listener(is_listening=False)
        self.assertEqual(status, PortStatus.FREE)

    def test_classify_port_listener_wildcard(self):
        status, details = classify_port_listener(is_listening=True, bind_address="0.0.0.0", process_name="OpenRGB.exe")
        self.assertEqual(status, PortStatus.UNSAFE_WILDCARD)

    def test_classify_port_listener_compatible_external(self):
        status, details = classify_port_listener(is_listening=True, bind_address="127.0.0.1", process_name="OpenRGB.exe")
        self.assertEqual(status, PortStatus.COMPATIBLE_EXTERNAL)

    def test_classify_port_listener_foreign(self):
        status, details = classify_port_listener(is_listening=True, bind_address="127.0.0.1", process_name="some_other_app.exe")
        self.assertEqual(status, PortStatus.CONFLICT_FOREIGN_PROCESS)

    def test_windows_job_object_lifecycle(self):
        job = WindowsJobObject()
        if os.name == "nt":
            self.assertIsNotNone(job.handle, "Job object handle must be initialized on Windows")
            # Calling close must release the handle
            job.close()
            self.assertIsNone(job.handle)
        else:
            self.assertIsNone(job.handle)

    def test_settings_gui_initialization_and_thread_safe_show(self):
        cfg_mgr = ConfigManager()
        ctrl = MockController()
        gui = SettingsGUI(config_manager=cfg_mgr, controller=ctrl)
        try:
            # Verify show schedules execution on main thread via root.after
            gui.show()
            # Process scheduled idle events
            gui.root.update_idletasks()
            gui.root.update()
            self.assertIsNotNone(gui.temp_devices_config)
            gui.hide()
            gui.root.update_idletasks()
        finally:
            gui.root.destroy()

if __name__ == '__main__':
    unittest.main()
