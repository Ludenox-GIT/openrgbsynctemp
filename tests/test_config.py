import unittest
import sys
import os
import tempfile
import json
import shutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from openrgb_temp_sync.config import (
    ConfigManager,
    DEFAULT_CONFIG_V2,
    validate_config_v2,
    migrate_v1_to_v2,
    merge_legacy_device_profiles,
    reconcile_device_profiles_on_save
)

class TestConfig(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.test_dir, "config.json")
        self.backup_dir = os.path.join(self.test_dir, "backups")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_default_config_schema(self):
        cfg = DEFAULT_CONFIG_V2
        self.assertEqual(cfg["schema_version"], 2)
        self.assertEqual(cfg["thermal"]["min_temp"], 30.0)
        self.assertEqual(cfg["thermal"]["mid_temp"], 60.0)
        self.assertEqual(cfg["thermal"]["max_temp"], 75.0)
        self.assertEqual(cfg["runtime"]["engine_port"], 6742)
        self.assertIn("devices", cfg)
        self.assertIn("unmatched_legacy_profiles", cfg)

    def test_validation_fixes_thresholds(self):
        invalid_thermal = {
            "min_temp": 80.0,
            "mid_temp": 60.0,
            "max_temp": 40.0
        }
        validated = validate_config_v2({"thermal": invalid_thermal})
        t = validated["thermal"]
        self.assertTrue(t["min_temp"] < t["mid_temp"] < t["max_temp"])

    def test_validation_clamps_colors_and_speeds(self):
        data = {
            "thermal": {
                "min_color": [300, -10, 50],
                "transition_speed": 99,
                "ema_factor": 1.5
            }
        }
        validated = validate_config_v2(data)
        t = validated["thermal"]
        self.assertEqual(t["min_color"], [255, 0, 50])
        self.assertEqual(t["transition_speed"], 10)
        self.assertEqual(t["ema_factor"], 0.15)

    def test_migrate_v1_to_v2(self):
        legacy_v1 = {
            "min_temp": 32.0,
            "mid_temp": 58.0,
            "max_temp": 82.0,
            "min_color": [10, 200, 10],
            "mid_color": [10, 10, 200],
            "max_color": [200, 10, 10],
            "brightness": 90,
            "transition_speed": 6,
            "stop_on_screensaver": True,
            "device_temp_source": {
                "ENE DRAM": {"default": "cpu", "LED 1": "gpu"},
                "Motherboard": "gpu"
            },
            "device_led_brightness": {
                "ENE DRAM": {"LED 1": 50, "LED 2": 80}
            }
        }
        v2 = migrate_v1_to_v2(legacy_v1)
        self.assertEqual(v2["schema_version"], 2)
        self.assertEqual(v2["thermal"]["min_temp"], 32.0)
        self.assertEqual(v2["thermal"]["mid_temp"], 58.0)
        self.assertEqual(v2["thermal"]["max_temp"], 82.0)
        self.assertEqual(v2["thermal"]["transition_speed"], 6)
        self.assertEqual(v2["behavior"]["stop_on_screensaver"], True)
        self.assertIn("ENE DRAM", v2["unmatched_legacy_profiles"])
        self.assertIn("Motherboard", v2["unmatched_legacy_profiles"])
        ene = v2["unmatched_legacy_profiles"]["ENE DRAM"]
        self.assertEqual(ene["led_brightness"]["LED 1"], 50)
        self.assertEqual(ene["temp_source"]["LED 1"], "gpu")

    def test_atomic_save_and_backup(self):
        mgr = ConfigManager(config_path=self.config_path, backup_dir=self.backup_dir)
        cfg = mgr.get_config()
        cfg["thermal"]["min_temp"] = 35.0
        mgr.save_config(cfg)

        self.assertTrue(os.path.exists(self.config_path))
        with open(self.config_path, "r", encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved["thermal"]["min_temp"], 35.0)

        # Test backup on migration when v2 does not exist yet
        legacy_file = os.path.join(self.test_dir, "legacy_config.json")
        with open(legacy_file, "w", encoding="utf-8") as f:
            json.dump({"min_temp": 28.0, "max_temp": 70.0}, f)

        mig_config_path = os.path.join(self.test_dir, "migrated_v2_config.json")
        mgr_legacy = ConfigManager(config_path=mig_config_path, backup_dir=self.backup_dir)
        mgr_legacy.load_or_migrate(legacy_path=legacy_file)
        self.assertTrue(os.path.exists(legacy_file), "Original legacy config must not be deleted")
        self.assertTrue(os.path.exists(mig_config_path), "Migrated v2 config must be saved")

        # Check backup folder contains a backup file
        backups = os.listdir(self.backup_dir)
        self.assertGreater(len(backups), 0)

    def test_merge_and_reconcile_legacy_device_profiles(self):
        devices = {
            "Existing Dev": {"default_source": "cpu", "led_brightness": {"LED 0": 50}}
        }
        unmatched = {
            "Detected Legacy Dev": {"default_source": "gpu", "led_brightness": {"LED 1": 80}},
            "Unknown Legacy Dev": {"default_source": "cpu", "led_brightness": {"LED 0": 100}}
        }

        # 1. Merge when showing settings with detected devices
        detected_names = ["Existing Dev", "Detected Legacy Dev"]
        merged_view = merge_legacy_device_profiles(devices, unmatched, detected_names)

        # Existing device keeps its config
        self.assertEqual(merged_view["Existing Dev"]["led_brightness"]["LED 0"], 50)
        # Detected legacy device is merged into editable view
        self.assertIn("Detected Legacy Dev", merged_view)
        self.assertEqual(merged_view["Detected Legacy Dev"]["default_source"], "gpu")
        # Unknown legacy device is not in editable view
        self.assertNotIn("Unknown Legacy Dev", merged_view)

        # 2. Reconcile on save
        # User edits the detected legacy dev
        merged_view["Detected Legacy Dev"]["default_source"] = "cpu"
        persisted, remaining_unmatched = reconcile_device_profiles_on_save(merged_view, unmatched)

        # Persisted has both
        self.assertIn("Existing Dev", persisted)
        self.assertIn("Detected Legacy Dev", persisted)
        self.assertEqual(persisted["Detected Legacy Dev"]["default_source"], "cpu")

        # Unknown legacy profile is preserved
        self.assertIn("Unknown Legacy Dev", remaining_unmatched)
        self.assertEqual(remaining_unmatched["Unknown Legacy Dev"]["default_source"], "cpu")
        # Matched legacy profile is no longer unmatched
        self.assertNotIn("Detected Legacy Dev", remaining_unmatched)


    def test_vendor_baselines_default_and_validation(self):
        cfg = DEFAULT_CONFIG_V2
        self.assertIn("vendor_baselines", cfg)
        self.assertEqual(cfg["vendor_baselines"], {})

        # Validation preserves valid dict
        custom_baseline = {
            "default_snapshot": {
                "name": "default_snapshot",
                "devices": {"DEV_1": {"name": "DEV_1", "colors": [[255, 0, 0]]}}
            }
        }
        validated = validate_config_v2({"vendor_baselines": custom_baseline})
        self.assertEqual(validated["vendor_baselines"], custom_baseline)

        # Validation handles malformed vendor_baselines
        validated_malformed = validate_config_v2({"vendor_baselines": "not_a_dict"})
        self.assertEqual(validated_malformed["vendor_baselines"], {})

    def test_capture_and_get_vendor_baseline_persistence(self):
        mgr = ConfigManager(config_path=self.config_path, backup_dir=self.backup_dir)
        initial_cfg = mgr.get_config()
        sample_baseline = {
            "ENE_DRAM_1": {
                "name": "ENE DRAM",
                "stable_key": "ENE_DRAM_1",
                "colors": [[255, 0, 0], [0, 255, 0]],
                "zone_led_counts": [8]
            },
            "MSI_B550": {
                "name": "MSI MAG B550 TOMAHAWK",
                "stable_key": "MSI_B550",
                "colors": [[0, 0, 255]],
                "zone_led_counts": [4]
            }
        }
        success = mgr.capture_vendor_baseline("vendor_default", sample_baseline)
        self.assertTrue(success)

        # Retrieve saved baseline
        loaded = mgr.get_vendor_baseline("vendor_default")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["devices"]["ENE_DRAM_1"]["colors"], [[255, 0, 0], [0, 255, 0]])
        # Test JSON round-trip
        dumped = json.dumps(loaded)
        reloaded = json.loads(dumped)
        self.assertEqual(reloaded, loaded)

        # Verify thermal and device profiles were not overwritten
        current_cfg = mgr.get_config()
        self.assertEqual(current_cfg["thermal"], initial_cfg["thermal"])
        self.assertEqual(current_cfg["devices"], initial_cfg["devices"])
        self.assertEqual(current_cfg["profiles"], initial_cfg["profiles"])

        # Test timestamped auto-naming when name is None
        mgr.capture_vendor_baseline(None, sample_baseline)
        baselines = mgr.list_vendor_baselines()
        self.assertIn("vendor_default", baselines)
        self.assertEqual(len(baselines), 2)
        auto_name = [b for b in baselines if b != "vendor_default"][0]
        self.assertTrue(auto_name.startswith("baseline_"))

    def test_legacy_or_malformed_config_preserves_vendor_baselines(self):
        legacy_v1_with_baselines = {
            "min_temp": 30.0,
            "max_temp": 75.0,
            "vendor_baselines": {
                "persisted_snapshot": {"name": "persisted_snapshot", "devices": {}}
            }
        }
        migrated = migrate_v1_to_v2(legacy_v1_with_baselines)
        self.assertIn("vendor_baselines", migrated)
        self.assertIn("persisted_snapshot", migrated["vendor_baselines"])

    def test_fresh_manager_save_preserves_on_disk_vendor_baselines(self):
        seed_mgr = ConfigManager(config_path=self.config_path, backup_dir=self.backup_dir)
        baseline_snapshot = {
            "DEV_1": {
                "name": "GPU",
                "stable_key": "DEV_1",
                "colors": [[128, 64, 32]]
            }
        }
        self.assertTrue(seed_mgr.capture_vendor_baseline("vendor_default", baseline_snapshot))

        with open(self.config_path, "r", encoding="utf-8") as f:
            disk_cfg = json.load(f)
        self.assertIn("vendor_default", disk_cfg.get("vendor_baselines", {}))

        fresh_mgr = ConfigManager(config_path=self.config_path, backup_dir=self.backup_dir)
        new_cfg = {"thermal": {"min_temp": 33.0}}
        saved = fresh_mgr.save_config(new_cfg)
        self.assertTrue(saved)

        with open(self.config_path, "r", encoding="utf-8") as f:
            persisted_cfg = json.load(f)
        self.assertIn("vendor_default", persisted_cfg.get("vendor_baselines", {}))
        self.assertEqual(
            persisted_cfg["vendor_baselines"]["vendor_default"]["devices"]["DEV_1"]["colors"],
            [[128, 64, 32]]
        )

    def test_fresh_manager_get_config_save_preserves_on_disk_vendor_baselines(self):
        seed_mgr = ConfigManager(config_path=self.config_path, backup_dir=self.backup_dir)
        baseline_snapshot = {
            "DEV_1": {
                "name": "GPU",
                "stable_key": "DEV_1",
                "colors": [[128, 64, 32]]
            }
        }
        self.assertTrue(seed_mgr.capture_vendor_baseline("vendor_default", baseline_snapshot))

        fresh_mgr = ConfigManager(config_path=self.config_path, backup_dir=self.backup_dir)
        cfg = fresh_mgr.get_config()
        self.assertEqual(cfg.get("vendor_baselines"), {})
        cfg["thermal"]["min_temp"] = 34.0
        self.assertTrue(fresh_mgr.save_config(cfg))

        with open(self.config_path, "r", encoding="utf-8") as f:
            persisted_cfg = json.load(f)
        self.assertIn("vendor_default", persisted_cfg.get("vendor_baselines", {}))
        self.assertEqual(
            persisted_cfg["vendor_baselines"]["vendor_default"]["devices"]["DEV_1"]["colors"],
            [[128, 64, 32]]
        )
        self.assertEqual(persisted_cfg["thermal"]["min_temp"], 34.0)

        reloaded_mgr = ConfigManager(config_path=self.config_path, backup_dir=self.backup_dir)
        loaded_cfg = reloaded_mgr.load_or_migrate()
        self.assertIn("vendor_default", loaded_cfg.get("vendor_baselines", {}))
        self.assertEqual(loaded_cfg["thermal"]["min_temp"], 34.0)

    def test_explicit_vendor_baselines_persist_correctly(self):
        seed_mgr = ConfigManager(config_path=self.config_path, backup_dir=self.backup_dir)
        seed_mgr.capture_vendor_baseline("initial_snapshot", {"DEV_OLD": {"colors": [[0, 0, 0]]}})

        fresh_mgr = ConfigManager(config_path=self.config_path, backup_dir=self.backup_dir)
        explicit_baselines = {
            "explicit_snapshot": {
                "name": "explicit_snapshot",
                "captured_at": "2026-09-20T12:00:00",
                "devices": {"DEV_NEW": {"colors": [[255, 255, 255]]}}
            }
        }
        cfg_to_save = {
            "thermal": {"min_temp": 35.0},
            "vendor_baselines": explicit_baselines
        }
        self.assertTrue(fresh_mgr.save_config(cfg_to_save))

        with open(self.config_path, "r", encoding="utf-8") as f:
            persisted_cfg = json.load(f)
        self.assertIn("explicit_snapshot", persisted_cfg.get("vendor_baselines", {}))
        self.assertEqual(
            persisted_cfg["vendor_baselines"]["explicit_snapshot"]["devices"]["DEV_NEW"]["colors"],
            [[255, 255, 255]]
        )

    def test_delete_last_vendor_baseline_persists_empty_state_without_resurrection(self):
        mgr = ConfigManager(config_path=self.config_path, backup_dir=self.backup_dir)
        sample_baseline = {
            "DEV_1": {
                "name": "GPU",
                "stable_key": "DEV_1",
                "colors": [[128, 64, 32]]
            }
        }
        self.assertTrue(mgr.capture_vendor_baseline("vendor_default", sample_baseline))
        mgr.load_or_migrate()
        self.assertIn("vendor_default", mgr.list_vendor_baselines())

        # Delete last remaining vendor baseline
        self.assertTrue(mgr.delete_vendor_baseline("vendor_default"))
        self.assertEqual(mgr.list_vendor_baselines(), [])

        # Verify disk state directly has empty vendor_baselines and did not resurrect
        with open(self.config_path, "r", encoding="utf-8") as f:
            disk_cfg = json.load(f)
        self.assertEqual(disk_cfg.get("vendor_baselines"), {})

        # Verify reloading manager also confirms empty baselines
        reloaded_mgr = ConfigManager(config_path=self.config_path, backup_dir=self.backup_dir)
        reloaded_mgr.load_or_migrate()
        self.assertEqual(reloaded_mgr.list_vendor_baselines(), [])

if __name__ == '__main__':
    unittest.main()