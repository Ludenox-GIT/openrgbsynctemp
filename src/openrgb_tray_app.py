#!/usr/bin/env python3
"""
OpenRGB Temp Sync - Single Tray Application Entrypoint.
Orchestrates OpenRGB engine, sensor bridge, settings GUI, and system tray.
"""

import logging
import os
import sys
import threading
import time

from openrgb_temp_sync.config import (
    ConfigManager,
    get_default_local_appdata_dir
)
from openrgb_temp_sync.controller import SyncController
from openrgb_temp_sync.lighting import create_tray_image
from openrgb_temp_sync.openrgb_runtime import OpenRGBSupervisor
from openrgb_temp_sync.sensor_runtime import SensorSupervisor
from openrgb_temp_sync.ui import SettingsGUI
from openrgb_temp_sync.windows_runtime import (
    SingleInstanceGuard,
    WindowsJobObject,
    is_startup_task_installed,
    set_startup_task_state
)

# Setup logging
log_dir = os.path.join(get_default_local_appdata_dir(), "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "app.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(name)s) %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("App")

if getattr(sys, "frozen", False):
    try:
        null_fd = os.open("nul", os.O_WRONLY)
        os.dup2(null_fd, 1)
        os.dup2(null_fd, 2)
    except Exception:
        pass


def resolve_resource_path(relative_path: str) -> str:
    """Resolve resource path relative to repo root (dev/source mode) or install dir (frozen mode)."""
    if getattr(sys, "frozen", False):
        # PyInstaller 6 onedir stores Python internals under `_internal`, while
        # our vendor children are staged beside the main executable. Try both
        # locations so the installed layout and one-file/dev fallback agree.
        base_dirs = []
        meipass_dir = getattr(sys, "_MEIPASS", None)
        exe_dir = os.path.dirname(sys.executable)
        if meipass_dir:
            base_dirs.append(meipass_dir)
        if exe_dir not in base_dirs:
            base_dirs.append(exe_dir)

        flat_name = os.path.basename(relative_path)
        for base_dir in base_dirs:
            direct_path = os.path.normpath(os.path.join(base_dir, relative_path))
            if os.path.exists(direct_path):
                return direct_path
            flat_path = os.path.normpath(os.path.join(base_dir, flat_name))
            if os.path.exists(flat_path):
                return flat_path

        # Return the install-dir candidate for a useful error message when the
        # asset is genuinely missing.
        return os.path.normpath(os.path.join(exe_dir, relative_path))
    else:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        if os.path.basename(current_dir).lower() == "src":
            repo_root = os.path.dirname(current_dir)
        else:
            repo_root = current_dir
        return os.path.normpath(os.path.join(repo_root, relative_path))


def main():
    logger.info("Starting OpenRGB Temp Sync application...")

    # 1. Single-instance guard
    guard = SingleInstanceGuard()
    if not guard.acquire():
        logger.info("Another instance is already running. Handing off activation and exiting.")
        sys.exit(0)

    # 2. Windows Job Object for child process supervision
    job_object = WindowsJobObject()

    # 3. Locate child executables
    openrgb_exe = resolve_resource_path("vendor/OpenRGB/OpenRGB.exe")
    if not os.path.exists(openrgb_exe):
        openrgb_exe = resolve_resource_path("OpenRGB.exe")

    sensor_exe = resolve_resource_path("vendor/sensor-bridge/OpenRGBTempSync.SensorBridge.exe")
    if not os.path.exists(sensor_exe):
        sensor_exe = resolve_resource_path("OpenRGBTempSync.SensorBridge.exe")

    openrgb_config_dir = os.path.join(get_default_local_appdata_dir(), "openrgb_config")
    os.makedirs(openrgb_config_dir, exist_ok=True)

    # 4. Initialize components
    config_mgr = ConfigManager()
    config_mgr.load_or_migrate()

    openrgb_sup = OpenRGBSupervisor(
        binary_path=openrgb_exe,
        config_dir=openrgb_config_dir,
        job_object=job_object,
        # OpenRGB exposes its SDK port before SMBus/ENE DRAM detection ends.
        device_detection_delay_seconds=12.0,
        require_elevation=True
    )

    sensor_sup = SensorSupervisor(bridge_path=sensor_exe, job_object=job_object)

    controller = SyncController(
        config_manager=config_mgr,
        openrgb_supervisor=openrgb_sup,
        sensor_supervisor=sensor_sup
    )

    # 5. Initialize Tkinter Settings GUI on Main Thread
    settings_gui = SettingsGUI(config_manager=config_mgr, controller=controller)

    # 6. Setup system tray if pystray is installed
    tray_icon = None
    try:
        import pystray

        def on_exit(icon, item):
            controller.stop()
            icon.stop()
            settings_gui.root.after(0, settings_gui.root.destroy)
            job_object.close()
            guard.release()

        def toggle_sync(icon, item):
            if controller.running:
                controller.stop()
            else:
                controller.start(lambda rgb: _update_icon_color(icon, rgb))

        def toggle_lights(icon, item):
            controller.set_lights_off(not controller.lights_off)

        def toggle_startup(icon, item):
            state = not is_startup_task_installed()
            set_startup_task_state(state)
            icon.update_menu()

        def _update_icon_color(icon, rgb):
            try:
                icon.icon = create_tray_image(rgb)
            except Exception:
                pass

        menu = pystray.Menu(
            pystray.MenuItem(lambda text: f"Status: {controller.get_status_snapshot()['status_text']}", lambda: None, enabled=False),
            pystray.MenuItem(lambda text: f"Engine: {controller.get_status_snapshot()['engine_label']}", lambda: None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda text: "Stop Sync" if controller.running else "Start Sync", toggle_sync),
            pystray.MenuItem(lambda text: "Turn Lights On" if controller.lights_off else "Turn Lights Off", toggle_lights),
            pystray.MenuItem("Settings", lambda icon, item: settings_gui.show()),
            pystray.MenuItem("Start with Windows", toggle_startup, checked=lambda item: is_startup_task_installed()),
            pystray.MenuItem("Retry Engine", lambda icon, item: controller.retry()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", on_exit)
        )

        tray_icon = pystray.Icon(
            "OpenRGBTempSync",
            icon=create_tray_image((0, 255, 0)),
            title="OpenRGB Temp Sync",
            menu=menu
        )

        controller.start(lambda rgb: _update_icon_color(tray_icon, rgb))
        threading.Thread(target=tray_icon.run, daemon=True).start()

    except ImportError:
        logger.warning("pystray not installed; running in GUI mode only.")
        controller.start()

    try:
        settings_gui.root.mainloop()
    except Exception as e:
        logger.error(f"Error in mainloop: {e}")
    finally:
        controller.stop()
        job_object.close()
        guard.release()


if __name__ == "__main__":
    main()
