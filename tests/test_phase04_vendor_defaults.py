import os
import sys
import unittest
import threading

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
from dataclasses import dataclass
from openrgb_temp_sync.openrgb_runtime import OpenRGBSupervisor, DeviceDescriptor, ResetCapability
from openrgb_temp_sync.openrgb_runtime import WriteResult
from openrgb_temp_sync.controller import SyncController
from openrgb_temp_sync.ui import SettingsGUI
import tkinter as tk

class DummyClient:
    def __init__(self):
        self.devices = []

class DummySupervisor(OpenRGBSupervisor):
    def __init__(self):
        self.client = DummyClient()
        self.client_thread = None
        self._inventory_generation = 1
        self._descriptors = []
    
    @property
    def inventory_generation(self):
        return 1

class TestPhase04(unittest.TestCase):
    def test_get_reset_capability(self):
        sup = DummySupervisor()
        sup._descriptors = [
            DeviceDescriptor('msi', 'MSI MAG B550 TOMAHAWK', 'MSI', 0, stable_key='msi'),
            DeviceDescriptor('ram', 'ENE DRAM', 'ENE', 1, stable_key='ram'),
            DeviceDescriptor('gpu', 'Gigabyte RTX 3060', 'Gigabyte', 2, stable_key='gpu'),
            DeviceDescriptor('other', 'Random Device', 'Random', 3, stable_key='other'),
        ]
        
        self.assertEqual(sup.get_reset_capability('msi').status, 'unverified')
        self.assertEqual(sup.get_reset_capability('ram').status, 'unverified')
        self.assertEqual(sup.get_reset_capability('gpu').status, 'unverified')
        self.assertEqual(sup.get_reset_capability('other').status, 'unsupported')
        
    def test_restore_manufacturer_defaults_unsupported_performs_no_writes(self):
        sup = DummySupervisor()
        sup._descriptors = [
            DeviceDescriptor('msi', 'MSI MAG B550 TOMAHAWK', 'MSI', 0, stable_key='msi'),
        ]
        res = sup.restore_manufacturer_defaults('msi')
        self.assertFalse(res.ok)
        self.assertEqual(res.error_code, 'reset_rejected')
        
    def test_controller_restore_manufacturer_defaults_unchanged_on_rejection(self):
        sup = DummySupervisor()
        sup._descriptors = [
            DeviceDescriptor('msi', 'MSI MAG B550 TOMAHAWK', 'MSI', 0, stable_key='msi'),
        ]
        c = SyncController(sup, None)
        c.set_device_owner('msi', 'thermal_direct')
        res = c.restore_manufacturer_defaults('msi')
        self.assertFalse(res.ok)
        self.assertEqual(c.get_device_owner('msi'), 'thermal_direct')

    def test_controller_successful_manufacturer_reset_holds_device_unmanaged(self):
        class VerifiedSupervisor(DummySupervisor):
            def __init__(self):
                super().__init__()
                self._sdk_lock = threading.RLock()

            def get_reset_capability(self, target_key):
                return ResetCapability('verified', 'verified')

            def restore_manufacturer_defaults(self, target_key):
                return WriteResult(ok=True, target_key=target_key, operation='restore_manufacturer_defaults')

        sup = VerifiedSupervisor()
        sup._descriptors = [
            DeviceDescriptor('msi', 'Verified Board', 'Board', 0, stable_key='msi'),
        ]
        c = SyncController(openrgb_supervisor=sup)
        c.set_device_owner('msi', 'thermal_direct')

        res = c.restore_manufacturer_defaults('msi')

        self.assertTrue(res.ok)
        self.assertEqual(c.get_device_owner('msi'), 'unmanaged')
        self.assertTrue(c.is_device_reset('msi'))
