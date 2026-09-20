import unittest
import os
import sys
import re
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from openrgb_tray_app import resolve_resource_path

class TestInstalledLayout(unittest.TestCase):
    def setUp(self):
        self.repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.spec_file = os.path.join(self.repo_root, "OpenRGBTempSync.spec")
        self.iss_file = os.path.join(self.repo_root, "installer", "OpenRGBTempSync.iss")

    def test_spec_file_properties(self):
        self.assertTrue(os.path.exists(self.spec_file), "OpenRGBTempSync.spec must exist")
        with open(self.spec_file, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("openrgb_tray_app.py", content)
        self.assertIn("COLLECT", content, "Release build must be onedir (using COLLECT)")
        self.assertIn("requireAdministrator", content, "Spec manifest must requireAdministrator")
        self.assertIn("uac_admin=True", content, "PyInstaller build must request an elevated app token")

    def test_installer_script_properties(self):
        self.assertTrue(os.path.exists(self.iss_file), "OpenRGBTempSync.iss must exist")
        with open(self.iss_file, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("AppId", content)
        self.assertIn("OpenRGB Temp Sync", content)
        self.assertIn("PrivilegesRequired=admin", content)
        self.assertIn("schtasks", content.lower(), "Installer must register scheduled task for startup")

        # Semantics check: must not blindly taskkill by image name
        self.assertNotIn("taskkill.exe\" /F /IM", content)
        self.assertNotIn("taskkill.exe /F /IM", content)
        # Must restrict uninstaller process termination to installed path {app}
        self.assertIn("{app}", content)
        # Startup task must quote /TR path safely
        self.assertIn(r'/TR ""\""{app}\{#MyAppExeName}\""""', content)

        # Uninstaller powershell command must have balanced braces after Inno Setup unescaping
        ps_match = re.search(r'Filename:\s*"powershell\.exe";\s*Parameters:\s*"-NoProfile.*?Command\s*""(.*?)"""', content)
        self.assertIsNotNone(ps_match, "Uninstaller powershell command must be present")
        ps_body = ps_match.group(1).replace("{{", "{")
        self.assertEqual(ps_body.count("{"), ps_body.count("}"), "Uninstaller powershell command must have balanced braces after Inno unescaping")

    def test_stop_bat_safety_properties(self):
        stop_bat = os.path.join(self.repo_root, "stop.bat")
        self.assertTrue(os.path.exists(stop_bat), "stop.bat must exist")
        with open(stop_bat, "r", encoding="utf-8") as f:
            content = f.read()

        # Must not blindly kill by image name
        self.assertNotIn("taskkill", content.lower(), "stop.bat must not use blind taskkill")
        # Must scope process termination to app directory
        self.assertIn("APP_DIR", content)
        self.assertIn("StartsWith", content)

    def test_no_sensitive_embedded_config_in_source(self):
        cfg_file = os.path.join(self.repo_root, "config.json")
        self.assertFalse(os.path.exists(cfg_file), "User machine-specific config.json must not be embedded in repository root")

    def test_resolve_resource_path_dev_mode(self):
        # In dev mode, resource path must resolve to repo root, never src/vendor
        resolved = resolve_resource_path("vendor/OpenRGB/OpenRGB.exe")
        expected = os.path.normpath(os.path.join(self.repo_root, "vendor", "OpenRGB", "OpenRGB.exe"))
        self.assertEqual(resolved, expected)

        src_vendor = os.path.normpath(os.path.join(self.repo_root, "src", "vendor", "OpenRGB", "OpenRGB.exe"))
        self.assertNotEqual(resolved.lower(), src_vendor.lower())

    def test_resolve_resource_path_frozen_mode(self):
        old_frozen = getattr(sys, "frozen", False)
        old_exe = sys.executable
        try:
            sys.frozen = True
            fake_install_dir = r"C:\Program Files\OpenRGB Temp Sync"
            sys.executable = os.path.join(fake_install_dir, "OpenRGBTempSync.exe")

            resolved = resolve_resource_path("OpenRGB.exe")
            expected = os.path.normpath(os.path.join(fake_install_dir, "OpenRGB.exe"))
            self.assertEqual(resolved, expected)
        finally:
            if not old_frozen and hasattr(sys, "frozen"):
                del sys.frozen
            sys.executable = old_exe

    def test_resolve_resource_path_frozen_onedir_falls_back_to_exe_dir(self):
        old_frozen = getattr(sys, "frozen", False)
        old_exe = sys.executable
        old_meipass = getattr(sys, "_MEIPASS", None)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                install_dir = os.path.join(tmp, "install")
                internal_dir = os.path.join(install_dir, "_internal")
                os.makedirs(os.path.join(install_dir, "vendor", "OpenRGB"), exist_ok=True)
                os.makedirs(internal_dir, exist_ok=True)
                expected = os.path.join(install_dir, "vendor", "OpenRGB", "OpenRGB.exe")
                with open(expected, "wb") as f:
                    f.write(b"test")

                sys.frozen = True
                sys._MEIPASS = internal_dir
                sys.executable = os.path.join(install_dir, "OpenRGBTempSync.exe")
                resolved = resolve_resource_path("vendor/OpenRGB/OpenRGB.exe")
                self.assertEqual(os.path.normcase(resolved), os.path.normcase(expected))
        finally:
            if not old_frozen and hasattr(sys, "frozen"):
                del sys.frozen
            sys.executable = old_exe
            if old_meipass is None and hasattr(sys, "_MEIPASS"):
                del sys._MEIPASS
            elif old_meipass is not None:
                sys._MEIPASS = old_meipass


    def test_installer_uninstaller_config_retention_prompt(self):
        with open(self.iss_file, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("CurUninstallStepChanged", content)
        self.assertIn("{localappdata}\\OpenRGBTempSync", content)
        self.assertIn("mbConfirmation, MB_YESNO", content)
        self.assertIn("DelTree(LocalAppDir, True, True, True);", content)

    def test_resolve_resource_path_sensor_bridge_dev_mode(self):
        resolved = resolve_resource_path("vendor/sensor-bridge/OpenRGBTempSync.SensorBridge.exe")
        expected = os.path.normpath(os.path.join(self.repo_root, "vendor", "sensor-bridge", "OpenRGBTempSync.SensorBridge.exe"))
        self.assertEqual(resolved, expected)

    def test_dist_layout_integrity_if_present(self):
        dist_dir = os.path.join(self.repo_root, "dist", "OpenRGBTempSync")
        if not os.path.exists(dist_dir):
            self.skipTest("dist/OpenRGBTempSync not present")
        main_exe = os.path.join(dist_dir, "OpenRGBTempSync.exe")
        self.assertTrue(os.path.isfile(main_exe), "dist must contain OpenRGBTempSync.exe")
        self.assertGreater(os.path.getsize(main_exe), 0, "OpenRGBTempSync.exe must not be empty")

        notices = os.path.join(dist_dir, "licenses", "THIRD-PARTY-NOTICES.md")
        self.assertTrue(os.path.isfile(notices), "dist must contain licenses/THIRD-PARTY-NOTICES.md")

        vendor_dir = os.path.join(dist_dir, "vendor")
        if os.path.exists(vendor_dir):
            openrgb_nested = os.path.join(vendor_dir, "OpenRGB", "OpenRGB.exe")
            openrgb_flat = os.path.join(dist_dir, "OpenRGB.exe")
            self.assertTrue(os.path.isfile(openrgb_nested) or os.path.isfile(openrgb_flat),
                            "OpenRGB.exe must be present in dist bundle")

            sensor_nested = os.path.join(vendor_dir, "sensor-bridge", "OpenRGBTempSync.SensorBridge.exe")
            sensor_flat = os.path.join(dist_dir, "OpenRGBTempSync.SensorBridge.exe")
            self.assertTrue(os.path.isfile(sensor_nested) or os.path.isfile(sensor_flat),
                            "SensorBridge executable must be present in dist bundle")

if __name__ == '__main__':
    unittest.main()
