"""
Windows-specific runtime interfaces:
Process Job Objects, Port 6742 listener inspection, Scheduled Tasks, Mutex single-instance.
"""

import ctypes
import ipaddress
import logging
import os
import subprocess
import sys
from typing import List, Optional, Tuple

logger = logging.getLogger("WindowsRuntime")


def is_process_elevated() -> bool:
    """Return whether the current Windows token is elevated for SMBus/PawnIO access."""
    if os.name != "nt":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


class PortStatus:
    FREE = "FREE"
    COMPATIBLE_EXTERNAL = "COMPATIBLE_EXTERNAL"
    COMPATIBLE_OWNED = "COMPATIBLE_OWNED"
    UNSAFE_WILDCARD = "UNSAFE_WILDCARD"
    CONFLICT_FOREIGN_PROCESS = "CONFLICT_FOREIGN_PROCESS"


def is_loopback_address(address_str: str) -> bool:
    """Check if an IP address string represents a valid loopback interface."""
    cleaned = address_str.strip().lower()
    if cleaned in ("localhost", "::1"):
        return True
    try:
        ip = ipaddress.ip_address(cleaned)
        return ip.is_loopback
    except ValueError:
        return False


def classify_port_listener(
    is_listening: bool,
    bind_address: str = "127.0.0.1",
    process_name: str = "OpenRGB.exe"
) -> Tuple[str, str]:
    """Classify the safety and ownership of a port listener."""
    if not is_listening:
        return PortStatus.FREE, "Port is free"

    if not is_loopback_address(bind_address):
        return PortStatus.UNSAFE_WILDCARD, f"Port bound to non-loopback address: {bind_address}"

    proc_lower = process_name.lower()
    if "openrgb" in proc_lower:
        return PortStatus.COMPATIBLE_EXTERNAL, f"External OpenRGB detected ({process_name})"

    return PortStatus.CONFLICT_FOREIGN_PROCESS, f"Port occupied by foreign process: {process_name}"


def inspect_port_6742() -> Tuple[str, str, Optional[int]]:
    """
    Inspect local port 6742 using psutil or socket connection.
    Returns (status, description, pid).
    """
    try:
        import psutil
        for conn in psutil.net_connections(kind="tcp"):
            if conn.laddr and conn.laddr.port == 6742:
                bind_ip = conn.laddr.ip
                pid = conn.pid
                pname = "Unknown"
                if pid:
                    try:
                        pname = psutil.Process(pid).name()
                    except Exception:
                        pass
                status, desc = classify_port_listener(True, bind_ip, pname)
                return status, desc, pid
        return PortStatus.FREE, "Port is free", None
    except Exception as e:
        logger.debug(f"psutil port inspection fallback: {e}")

    # Fallback to loopback socket probe
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        res = s.connect_ex(("127.0.0.1", 6742))
        s.close()
        if res == 0:
            return PortStatus.COMPATIBLE_EXTERNAL, "Port 6742 open on 127.0.0.1", None
        return PortStatus.FREE, "Port is free", None
    except Exception:
        return PortStatus.FREE, "Port is free", None


def build_schtasks_create_command(exe_path: str) -> List[str]:
    """Build schtasks.exe command to create highest-privilege logon task."""
    return [
        "schtasks.exe",
        "/Create",
        "/F",
        "/TN", "OpenRGBTempSync",
        "/TR", f'"{exe_path}"',
        "/SC", "ONLOGON",
        "/RL", "HIGHEST"
    ]


def build_schtasks_delete_command() -> List[str]:
    """Build schtasks.exe command to remove startup task."""
    return [
        "schtasks.exe",
        "/Delete",
        "/F",
        "/TN", "OpenRGBTempSync"
    ]


def is_startup_task_installed() -> bool:
    """Check whether the OpenRGBTempSync scheduled task is registered."""
    try:
        res = subprocess.run(
            ["schtasks.exe", "/Query", "/TN", "OpenRGBTempSync"],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        )
        return res.returncode == 0
    except Exception:
        return False


def set_startup_task_state(enable: bool, exe_path: Optional[str] = None) -> bool:
    """Install or remove scheduled startup task, and clean up legacy registry entry."""
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    if enable:
        target_exe = exe_path or (sys.executable if getattr(sys, "frozen", False) else sys.argv[0])
        cmd = build_schtasks_create_command(target_exe)
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, creationflags=creationflags)
            if res.returncode == 0:
                _cleanup_legacy_registry_run()
                return True
            return False
        except Exception:
            return False
    else:
        cmd = build_schtasks_delete_command()
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, creationflags=creationflags)
            _cleanup_legacy_registry_run()
            return res.returncode == 0
        except Exception:
            return False


def _cleanup_legacy_registry_run():
    """Remove legacy HKCU Run entry if present."""
    if os.name != "nt":
        return
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_WRITE | winreg.KEY_QUERY_VALUE
        ) as key:
            try:
                winreg.DeleteValue(key, "OpenRGBTempSync")
            except FileNotFoundError:
                pass
    except Exception:
        pass


def is_screensaver_active() -> bool:
    """Check if Windows screensaver is currently active."""
    if os.name != "nt":
        return False
    try:
        SPI_GETSCREENSAVERRUNNING = 0x72
        is_running = ctypes.c_bool(False)
        res = ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETSCREENSAVERRUNNING, 0, ctypes.byref(is_running), 0
        )
        return is_running.value if res else False
    except Exception:
        return False


class SingleInstanceGuard:
    """Named Windows Mutex to ensure exactly one instance of the app runs."""

    def __init__(self, mutex_name: str = "Local\\OpenRGBTempSync_SingleInstance"):
        self.mutex_name = mutex_name
        self.mutex_handle = None
        self.already_running = False

    def acquire(self) -> bool:
        if os.name != "nt":
            return True
        ERROR_ALREADY_EXISTS = 183
        self.mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, False, self.mutex_name)
        last_err = ctypes.windll.kernel32.GetLastError()
        if last_err == ERROR_ALREADY_EXISTS:
            self.already_running = True
            return False
        return True

    def release(self):
        if self.mutex_handle and os.name == "nt":
            try:
                ctypes.windll.kernel32.CloseHandle(self.mutex_handle)
            except Exception:
                pass
            self.mutex_handle = None


class WindowsJobObject:
    """Manages child processes under a Job Object with kill-on-close limit."""

    def __init__(self):
        self.handle = None
        self._setup()

    def _setup(self):
        if os.name != "nt":
            return
        try:
            k32 = ctypes.windll.kernel32
            k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
            k32.CreateJobObjectW.restype = ctypes.c_void_p
            k32.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
            k32.SetInformationJobObject.restype = ctypes.c_bool
            k32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            k32.AssignProcessToJobObject.restype = ctypes.c_bool
            k32.CloseHandle.argtypes = [ctypes.c_void_p]
            k32.CloseHandle.restype = ctypes.c_bool

            self.handle = k32.CreateJobObjectW(None, None)
            if not self.handle:
                return

            # Set JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
            class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("PerProcessUserTimeLimit", ctypes.c_int64),
                    ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", ctypes.c_uint32),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", ctypes.c_uint32),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", ctypes.c_uint32),
                    ("SchedulingClass", ctypes.c_uint32),
                ]

            class IO_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("ReadOperationCount", ctypes.c_uint64),
                    ("WriteOperationCount", ctypes.c_uint64),
                    ("OtherOperationCount", ctypes.c_uint64),
                    ("ReadTransferCount", ctypes.c_uint64),
                    ("WriteTransferCount", ctypes.c_uint64),
                    ("OtherTransferCount", ctypes.c_uint64),
                ]

            class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                    ("IoInfo", IO_COUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryLimit", ctypes.c_size_t),
                    ("PeakJobMemoryLimit", ctypes.c_size_t),
                ]

            info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

            JobObjectExtendedLimitInformation = 9
            ctypes.windll.kernel32.SetInformationJobObject(
                self.handle,
                JobObjectExtendedLimitInformation,
                ctypes.byref(info),
                ctypes.sizeof(info)
            )
        except Exception as e:
            logger.debug(f"Job Object init notice: {e}")

    def assign_process(self, process_handle) -> bool:
        if not self.handle or os.name != "nt":
            return False
        try:
            res = ctypes.windll.kernel32.AssignProcessToJobObject(self.handle, int(process_handle))
            return bool(res)
        except Exception:
            return False

    def close(self):
        if self.handle and os.name == "nt":
            try:
                ctypes.windll.kernel32.CloseHandle(self.handle)
            except Exception:
                pass
            self.handle = None
