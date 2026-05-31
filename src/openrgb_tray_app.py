#!/usr/bin/env python3
"""
Delightful Newton - OpenRGB CPU Temp Sync System Tray App
Runs in the system tray, syncs CPU temperature to OpenRGB, and manages startup settings.
"""

import os
import sys
import ctypes


class NullWriter:
    def write(self, text):
        pass
    def flush(self):
        pass

if getattr(sys, 'frozen', False):
    sys.stdout = NullWriter()
    sys.stderr = NullWriter()

import time
import mmap
import threading
import json
import tkinter as tk
from tkinter import colorchooser, messagebox, ttk

import winreg as reg
from PIL import Image, ImageDraw
import pystray
from openrgb import OpenRGBClient
from openrgb.utils import RGBColor

# Core settings
POLL_INTERVAL = 2.0
REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_NAME = "OpenRGBTempSync"

# Helper to get configuration file path
def get_config_path():
    if getattr(sys, 'frozen', False):
        app_dir = os.path.dirname(sys.executable)
    else:
        app_dir = os.path.dirname(os.path.realpath(sys.argv[0]))
    return os.path.join(app_dir, "config.json")

# NVML Ctypes interfaces for GPU temperature reading
nvml_lib = None
nvml_handle = None
nvml_available = False

def init_nvml():
    global nvml_lib, nvml_handle, nvml_available
    try:
        # nvml.dll is usually in system32 path and handled automatically by Windows DLL search
        nvml_lib = ctypes.CDLL("nvml.dll")
        nvml_lib.nvmlInit()
        
        # Get handle for GPU index 0
        nvml_handle = ctypes.c_void_p()
        res = nvml_lib.nvmlDeviceGetHandleByIndex(0, ctypes.byref(nvml_handle))
        if res == 0: # 0 corresponds to NVML_SUCCESS
            nvml_available = True
            return True
    except Exception:
        pass
    nvml_lib = None
    nvml_handle = None
    nvml_available = False
    return False

def get_gpu_temperature():
    global nvml_lib, nvml_handle, nvml_available
    if not nvml_available or nvml_lib is None or nvml_handle is None:
        return None
    try:
        temp = ctypes.c_uint()
        # 0 corresponds to NVML_TEMPERATURE_GPU
        res = nvml_lib.nvmlDeviceGetTemperature(nvml_handle, 0, ctypes.byref(temp))
        if res == 0:
            return float(temp.value)
    except Exception:
        pass
    return None

def is_screensaver_running():
    try:
        SPI_GETSCREENSAVERRUNNING = 0x72
        is_running = ctypes.c_bool(False)
        result = ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETSCREENSAVERRUNNING, 
            0, 
            ctypes.byref(is_running), 
            0
        )
        return is_running.value if result else False
    except Exception:
        return False

def is_computer_locked():
    try:
        from ctypes import wintypes
        DESKTOP_SWITCHDESKTOP = 0x0100
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        user32.OpenDesktopW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        user32.OpenDesktopW.restype = wintypes.HANDLE
        user32.SwitchDesktop.argtypes = (wintypes.HANDLE,)
        user32.SwitchDesktop.restype = wintypes.BOOL
        user32.CloseDesktop.argtypes = (wintypes.HANDLE,)
        user32.CloseDesktop.restype = wintypes.BOOL
        
        hnd_dt = user32.OpenDesktopW('default', 0, False, DESKTOP_SWITCHDESKTOP)
        if not hnd_dt:
            return True
        result = user32.SwitchDesktop(hnd_dt)
        user32.CloseDesktop(hnd_dt)
        return not bool(result)
    except Exception:
        return False


# Default configuration values
DEFAULT_CONFIG = {
    "min_temp": 30.0,
    "mid_temp": 60.0,
    "max_temp": 75.0,
    "min_color": [0, 255, 0],     # Green
    "mid_color": [0, 0, 255],     # Blue
    "max_color": [255, 0, 0],     # Red
    "brightness": 100,            # 0 to 100
    "transition_speed": 5,         # 1 to 10
    "device_temp_source": {},     # Key: device name -> Value: "cpu" or "gpu"
    "stop_on_screensaver": False,
    "stop_on_lock": False
}



# Global config cache
config = dict(DEFAULT_CONFIG)

def load_config():
    global config
    config_path = get_config_path()
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for key in DEFAULT_CONFIG:
                    if key in data:
                        config[key] = data[key]
        except Exception:
            pass

def save_config(config_data):
    global config
    config = dict(config_data)
    config_path = get_config_path()
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4)
    except Exception:
        pass

# Load initial config on import
load_config()

# C-style structure definition matching Core Temp SDK
class CoreTempSharedDataEx(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        ("uiLoad", ctypes.c_uint * 256),
        ("uiTjMax", ctypes.c_uint * 128),
        ("uiCoreCnt", ctypes.c_uint),
        ("uiCPUCnt", ctypes.c_uint),
        ("fTemp", ctypes.c_float * 256),
        ("fVID", ctypes.c_float),
        ("fCPUSpeed", ctypes.c_float),
        ("fFSBSpeed", ctypes.c_float),
        ("fMultiplier", ctypes.c_float),
        ("sCPUName", ctypes.c_char * 100),
        ("ucFahrenheit", ctypes.c_ubyte),
        ("ucDeltaToTjMax", ctypes.c_ubyte),
        ("ucTdpSupported", ctypes.c_ubyte),
        ("ucPowerSupported", ctypes.c_ubyte),
        ("uiStructVersion", ctypes.c_uint),
        ("uiTdp", ctypes.c_uint * 128),
        ("fPower", ctypes.c_float * 128),
        ("fMultipliers", ctypes.c_float * 256),
    ]

# Core logic functions
def get_cpu_temperature():
    struct_size = ctypes.sizeof(CoreTempSharedDataEx)
    try:
        with mmap.mmap(-1, struct_size, tagname="CoreTempMappingObjectEx", access=mmap.ACCESS_READ) as mm:
            data = CoreTempSharedDataEx.from_buffer_copy(mm)
            core_count = data.uiCoreCnt
            if core_count == 0 or core_count > 256:
                return None
            temps = [data.fTemp[i] for i in range(core_count)]
            if not temps:
                return None
            avg_temp = sum(temps) / len(temps)
            if data.ucFahrenheit == 1:
                avg_temp = (avg_temp - 32) * 5 / 9
            return avg_temp
    except FileNotFoundError:
        return None
    except Exception:
        return None

def map_temp_to_rgb(temp, min_temp=None, mid_temp=None, max_temp=None, min_color=None, mid_color=None, max_color=None, brightness=None):
    global config
    
    # Resolve parameters from config if not provided
    min_t = min_temp if min_temp is not None else config["min_temp"]
    mid_t = mid_temp if mid_temp is not None else config["mid_temp"]
    max_t = max_temp if max_temp is not None else config["max_temp"]
    
    c_min = min_color if min_color is not None else config["min_color"]
    c_mid = mid_color if mid_color is not None else config["mid_color"]
    c_max = max_color if max_color is not None else config["max_color"]
    
    bright = brightness if brightness is not None else config["brightness"]

    if temp <= min_t:
        r, g, b = c_min
    elif temp >= max_t:
        r, g, b = c_max
    elif temp < mid_t:
        ratio = (temp - min_t) / (mid_t - min_t)
        r = int(c_min[0] + (c_mid[0] - c_min[0]) * ratio)
        g = int(c_min[1] + (c_mid[1] - c_min[1]) * ratio)
        b = int(c_min[2] + (c_mid[2] - c_min[2]) * ratio)
    else:
        ratio = (temp - mid_t) / (max_t - mid_t)
        r = int(c_mid[0] + (c_max[0] - c_mid[0]) * ratio)
        g = int(c_mid[1] + (c_max[1] - c_mid[1]) * ratio)
        b = int(c_mid[2] + (c_max[2] - c_mid[2]) * ratio)

    # Apply brightness
    factor = max(0, min(100, bright)) / 100.0
    r = int(r * factor)
    g = int(g * factor)
    b = int(b * factor)

    return max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))

# Startup Registry manager
def is_startup_enabled():
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, REG_KEY, 0, reg.KEY_READ) as key:
            reg.QueryValueEx(key, REG_NAME)
            return True
    except FileNotFoundError:
        return False
    except Exception:
        return False

def set_startup_state(enable):
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, REG_KEY, 0, reg.KEY_WRITE | reg.KEY_QUERY_VALUE) as key:
            if not enable:
                try:
                    reg.DeleteValue(key, REG_NAME)
                except FileNotFoundError:
                    pass
            else:
                if getattr(sys, 'frozen', False):
                    path = sys.executable
                else:
                    path = os.path.realpath(sys.argv[0])
                reg.SetValueEx(key, REG_NAME, 0, reg.REG_SZ, f'"{path}"')
    except Exception:
        pass

# App Threading Controller
class SyncController:
    def __init__(self):
        self.running = False
        self.thread = None
        self.stop_event = threading.Event()
        self.status_text = "Status: Idle"
        self.devices = []
        self.auto_paused = False

    def start(self, icon):
        if self.running:
            return
        self.running = True
        self.stop_event.clear()
        self.status_text = "Status: Connecting..."
        icon.update_menu()
        self.thread = threading.Thread(target=self._run, args=(icon,), daemon=True)
        self.thread.start()

    def stop(self, icon):
        if not self.running:
            return
        self.running = False
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=1.0)
        self.status_text = "Status: Stopped"
        self.devices = []
        icon.icon = create_tray_image()
        icon.update_menu()

    def _run(self, icon):
        # Initialize NVIDIA NVML API for GPU temperature monitoring
        init_nvml()
        
        # Connect to OpenRGB
        client = None
        try:
            client = OpenRGBClient("127.0.0.1", 6742)
            devices = client.devices
            self.devices = devices
            if not devices:
                self.status_text = "Status: No Devices"
                self.running = False
                icon.update_menu()
                return

            # Attempt to set all devices to 'direct' mode on startup
            for device in devices:
                try:
                    for mode in device.modes:
                        if mode.name.lower() == 'direct':
                            device.set_mode(mode.name)
                            break
                except Exception:
                    pass

            self.status_text = "Status: Running"
            icon.update_menu()
        except Exception:
            self.status_text = "Status: Connect Fail (SDK?)"
            self.running = False
            self.devices = []
            icon.update_menu()
            return

        smoothed_cpu_temp = None
        smoothed_gpu_temp = None
        alpha_temp = 0.15  # EMA factor for temp smoothing
        
        # Track current color states for each LED to interpolate smoothly
        # Key format: "device_name:led_index" -> [r, g, b]
        current_led_colors = {}
        
        last_temp_read_time = 0.0
        temp_read_interval = 1.0  # Read raw temperature every 1.0 second
        
        # Main high-frequency loop (20Hz)
        while not self.stop_event.is_set():
            current_time = time.time()
            
            # 1. Read raw temperatures periodically
            if current_time - last_temp_read_time >= temp_read_interval:
                last_temp_read_time = current_time
                
                # Check auto-pause conditions
                should_pause = False
                if config.get("stop_on_screensaver", False) and is_screensaver_running():
                    should_pause = True
                if config.get("stop_on_lock", False) and is_computer_locked():
                    should_pause = True
                    
                if should_pause:
                    if not self.auto_paused:
                        self.auto_paused = True
                        self.status_text = "Status: Auto-Paused"
                        icon.update_menu()
                        # Set all devices to black (off) once to save power
                        off_color = RGBColor(0, 0, 0)
                        for device in self.devices:
                            try:
                                device.set_color(off_color)
                            except Exception:
                                pass
                else:
                    if self.auto_paused:
                        self.auto_paused = False
                        self.status_text = "Status: Running"
                        icon.update_menu()
                
                # CPU Temp
                raw_cpu_temp = get_cpu_temperature()
                if raw_cpu_temp is not None:
                    if smoothed_cpu_temp is None:
                        smoothed_cpu_temp = raw_cpu_temp
                    else:
                        smoothed_cpu_temp = (alpha_temp * raw_cpu_temp) + ((1 - alpha_temp) * smoothed_cpu_temp)
                
                # GPU Temp
                raw_gpu_temp = get_gpu_temperature()
                if raw_gpu_temp is not None:
                    if smoothed_gpu_temp is None:
                        smoothed_gpu_temp = raw_gpu_temp
                    else:
                        smoothed_gpu_temp = (alpha_temp * raw_gpu_temp) + ((1 - alpha_temp) * smoothed_gpu_temp)
            
            # We can run calculations if at least CPU temp is available and not auto-paused
            if smoothed_cpu_temp is not None and not self.auto_paused:
                # 2. Get transition speed factor from config
                speed_val = config.get("transition_speed", 5)
                # Keep within safe bounds [1, 10]
                speed_val = max(1, min(10, speed_val))
                step_factor = speed_val / 50.0  # 50ms step factor
                
                # 3. Calculate dynamic global tray icon color (smoothed CPU temp by default)
                r_icon, g_icon, b_icon = map_temp_to_rgb(smoothed_cpu_temp)
                icon.icon = create_tray_image((r_icon, g_icon, b_icon))
                
                device_led_bright = config.get("device_led_brightness", {})
                device_temp_source = config.get("device_temp_source", {})
                
                # 4. Interpolate and apply colors for each device
                for device in self.devices:
                    try:
                        # Determine temp source (cpu or gpu) - supporting per-LED configs with backwards compatibility
                        device_source_config = device_temp_source.get(device.name, "cpu")
                        if isinstance(device_source_config, str):
                            device_default_source = device_source_config
                            led_source_config = {}
                        else:
                            device_default_source = device_source_config.get("default", "cpu")
                            led_source_config = device_source_config
                            
                        led_count = len(device.leds)
                        if led_count > 0:
                            colors = []
                            device_bright_config = device_led_bright.get(device.name, {})
                            
                            for idx, led in enumerate(device.leds):
                                # Determine brightness
                                if led.name in device_bright_config:
                                    led_bright = device_bright_config[led.name]
                                else:
                                    led_bright = 100
                                    
                                # Determine temp source for this specific LED
                                led_source = led_source_config.get(led.name, device_default_source)
                                active_temp = smoothed_gpu_temp if (led_source == "gpu" and smoothed_gpu_temp is not None) else smoothed_cpu_temp
                                
                                if active_temp is None:
                                    target_r, target_g, target_b = 0, 0, 0
                                else:
                                    # Calculate target color for this LED
                                    target_r, target_g, target_b = map_temp_to_rgb(active_temp, brightness=led_bright)
                                
                                # Retrieve/Initialize current color state
                                led_key = f"{device.name}:{idx}"
                                if led_key not in current_led_colors:
                                    current_led_colors[led_key] = [float(target_r), float(target_g), float(target_b)]
                                    
                                curr_r, curr_g, curr_b = current_led_colors[led_key]
                                
                                # Lerp to target color
                                curr_r += (target_r - curr_r) * step_factor
                                curr_g += (target_g - curr_g) * step_factor
                                curr_b += (target_b - curr_b) * step_factor
                                
                                # Cache updated state
                                current_led_colors[led_key] = [curr_r, curr_g, curr_b]
                                
                                # Convert to integer color values for SDK (clamped to [0, 255])
                                colors.append(RGBColor(
                                    max(0, min(255, int(curr_r))),
                                    max(0, min(255, int(curr_g))),
                                    max(0, min(255, int(curr_b)))
                                ))
                                
                            device.set_colors(colors, fast=True)
                        else:
                            # Device with 0 leds (fallback)
                            led_source = device_default_source
                            active_temp = smoothed_gpu_temp if (led_source == "gpu" and smoothed_gpu_temp is not None) else smoothed_cpu_temp
                            if active_temp is None:
                                continue
                                
                            target_r, target_g, target_b = map_temp_to_rgb(active_temp, brightness=100)
                            device_key = f"{device.name}:default"
                            
                            if device_key not in current_led_colors:
                                current_led_colors[device_key] = [float(target_r), float(target_g), float(target_b)]
                                
                            curr_r, curr_g, curr_b = current_led_colors[device_key]
                            curr_r += (target_r - curr_r) * step_factor
                            curr_g += (target_g - curr_g) * step_factor
                            curr_b += (target_b - curr_b) * step_factor
                            current_led_colors[device_key] = [curr_r, curr_g, curr_b]
                            
                            device.set_color(RGBColor(
                                max(0, min(255, int(curr_r))),
                                max(0, min(255, int(curr_g))),
                                max(0, min(255, int(curr_b)))
                            ), fast=True)
                    except Exception:
                        try:
                            # Fallback without animation
                            active_temp = smoothed_gpu_temp if (device_default_source == "gpu" and smoothed_gpu_temp is not None) else smoothed_cpu_temp
                            if active_temp is not None:
                                r_led, g_led, b_led = map_temp_to_rgb(active_temp, brightness=100)
                                device.set_color(RGBColor(r_led, g_led, b_led))
                        except Exception:
                            pass
            time.sleep(0.05) # Run loop at 20Hz (50ms interval)




# Create a dynamic tray icon image (a neon circular logo)
def create_tray_image(color=(0, 255, 0)):
    image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    dc = ImageDraw.Draw(image)
    # Draw glowing outer ring
    dc.ellipse([4, 4, 60, 60], outline=color, width=4)
    # Draw central atom core
    dc.ellipse([20, 20, 44, 44], fill=color)
    return image

# Global App Setup
controller = SyncController()

class SettingsGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("OpenRGB Temp Sync Settings")
        self.root.geometry("480x560")
        self.root.resizable(False, False)
        self.root.withdraw() # Hide window initially
        
        # Dark Theme Palette
        self.bg_color = "#121214"
        self.card_bg = "#1e1e24"
        self.fg_color = "#ffffff"
        self.accent_color = "#4f46e5" # Indigo neon
        self.accent_hover = "#6366f1"
        self.text_muted = "#a1a1aa"
        
        self.root.configure(bg=self.bg_color)
        
        # Style configurations for ttk widgets
        self.style = ttk.Style()
        self.style.theme_use('default')
        self.style.configure('TNotebook', background=self.bg_color, borderwidth=0)
        self.style.configure('TNotebook.Tab', background=self.card_bg, foreground=self.fg_color, borderwidth=0, padding=[12, 6], font=("Segoe UI", 9, "bold"))
        self.style.map('TNotebook.Tab', background=[('selected', self.accent_color)], foreground=[('selected', self.fg_color)])
        
        self.style.configure('TCombobox', fieldbackground=self.card_bg, background=self.card_bg, foreground=self.fg_color)
        
        # Title Header
        header_frame = tk.Frame(self.root, bg=self.bg_color, pady=10)
        header_frame.pack(fill="x")
        tk.Label(header_frame, text="OpenRGB Temp Sync Settings", font=("Segoe UI", 14, "bold"), fg=self.fg_color, bg=self.bg_color).pack()
        
        # Notebook container
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=15, pady=5)
        
        # Tab Frames
        self.tab_general = tk.Frame(self.notebook, bg=self.bg_color)
        self.tab_advanced = tk.Frame(self.notebook, bg=self.bg_color)
        
        self.notebook.add(self.tab_general, text=" Color Settings ")
        self.notebook.add(self.tab_advanced, text=" Advanced Per-LED Brightness ")
        
        # Set up fields
        self.setup_general_tab()
        self.setup_advanced_tab()
        
        # Bottom Buttons
        btn_frame = tk.Frame(self.root, bg=self.bg_color, pady=12, padx=15)
        btn_frame.pack(fill="x", side="bottom")
        
        save_btn = tk.Button(btn_frame, text="Save Settings", bg=self.accent_color, fg=self.fg_color, activebackground=self.accent_hover, activeforeground=self.fg_color, bd=0, padx=15, pady=8, font=("Segoe UI", 10, "bold"), command=self.save)
        save_btn.pack(side="right", padx=5)
        
        cancel_btn = tk.Button(btn_frame, text="Cancel", bg="#33333b", fg=self.fg_color, activebackground="#44444e", activeforeground=self.fg_color, bd=0, padx=15, pady=8, font=("Segoe UI", 10, "bold"), command=self.hide)
        cancel_btn.pack(side="right", padx=5)
        
        self.root.protocol("WM_DELETE_WINDOW", self.hide)
        self.temp_led_brightness = {}
        self.temp_device_sources = {}

    def rgb_to_hex(self, rgb):
        return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

    def setup_general_tab(self):
        # Container frame
        container = tk.Frame(self.tab_general, bg=self.bg_color, padx=10, pady=5)
        container.pack(fill="both", expand=True)
        
        # Tkinter variables linked to configurations
        self.min_temp_var = tk.DoubleVar()
        self.mid_temp_var = tk.DoubleVar()
        self.max_temp_var = tk.DoubleVar()
        self.transition_speed_var = tk.IntVar()
        self.stop_on_screensaver_var = tk.BooleanVar()
        self.stop_on_lock_var = tk.BooleanVar()
        
        self.min_color_val = [0, 255, 0]
        self.mid_color_val = [0, 0, 255]
        self.max_color_val = [255, 0, 0]
        
        font_label = ("Segoe UI", 10, "bold")
        
        # Draw Threshold Frame
        threshold_frame = tk.LabelFrame(container, text=" Temperature Thresholds & Colors ", fg=self.accent_color, bg=self.bg_color, bd=1, relief="solid", highlightthickness=0, font=("Segoe UI", 9, "bold"), labelanchor="nw", padx=10, pady=15)
        threshold_frame.pack(fill="x", pady=10)
        
        threshold_frame.columnconfigure(0, weight=1)
        threshold_frame.columnconfigure(1, weight=2)
        threshold_frame.columnconfigure(2, weight=1)
        
        # Table Headers
        tk.Label(threshold_frame, text="Threshold", fg=self.text_muted, bg=self.bg_color, font=("Segoe UI", 8, "bold")).grid(row=0, column=0, sticky="w", pady=(0,5))
        tk.Label(threshold_frame, text="Temp (°C)", fg=self.text_muted, bg=self.bg_color, font=("Segoe UI", 8, "bold")).grid(row=0, column=1, sticky="w", pady=(0,5))
        tk.Label(threshold_frame, text="Color", fg=self.text_muted, bg=self.bg_color, font=("Segoe UI", 8, "bold")).grid(row=0, column=2, sticky="w", pady=(0,5))
        
        # Low Threshold Row
        tk.Label(threshold_frame, text="Low / Idle", fg=self.fg_color, bg=self.bg_color, font=font_label).grid(row=1, column=0, sticky="w", pady=8)
        self.min_entry = tk.Entry(threshold_frame, textvariable=self.min_temp_var, width=8, bg=self.card_bg, fg=self.fg_color, insertbackground=self.fg_color, bd=1, relief="solid")
        self.min_entry.grid(row=1, column=1, sticky="w", pady=8)
        
        self.min_btn = tk.Button(threshold_frame, width=6, height=1, bd=1, relief="solid")
        self.min_btn.grid(row=1, column=2, sticky="w", pady=8)
        
        # Mid Threshold Row
        tk.Label(threshold_frame, text="Medium", fg=self.fg_color, bg=self.bg_color, font=font_label).grid(row=2, column=0, sticky="w", pady=8)
        self.mid_entry = tk.Entry(threshold_frame, textvariable=self.mid_temp_var, width=8, bg=self.card_bg, fg=self.fg_color, insertbackground=self.fg_color, bd=1, relief="solid")
        self.mid_entry.grid(row=2, column=1, sticky="w", pady=8)
        
        self.mid_btn = tk.Button(threshold_frame, width=6, height=1, bd=1, relief="solid")
        self.mid_btn.grid(row=2, column=2, sticky="w", pady=8)
        
        # High Threshold Row
        tk.Label(threshold_frame, text="High / Load", fg=self.fg_color, bg=self.bg_color, font=font_label).grid(row=3, column=0, sticky="w", pady=8)
        self.max_entry = tk.Entry(threshold_frame, textvariable=self.max_temp_var, width=8, bg=self.card_bg, fg=self.fg_color, insertbackground=self.fg_color, bd=1, relief="solid")
        self.max_entry.grid(row=3, column=1, sticky="w", pady=8)
        
        self.max_btn = tk.Button(threshold_frame, width=6, height=1, bd=1, relief="solid")
        self.max_btn.grid(row=3, column=2, sticky="w", pady=8)
        
        # Color picker triggers
        def choose_color(color_list, button):
            initial_hex = self.rgb_to_hex(color_list)
            _, hex_color = colorchooser.askcolor(parent=self.root, title="Select Color", color=initial_hex)
            if hex_color:
                rgb = [int(hex_color[i:i+2], 16) for i in (1, 3, 5)]
                color_list[0] = rgb[0]
                color_list[1] = rgb[1]
                color_list[2] = rgb[2]
                button.configure(bg=hex_color, activebackground=hex_color)
                
        self.min_btn.configure(command=lambda: choose_color(self.min_color_val, self.min_btn))
        self.mid_btn.configure(command=lambda: choose_color(self.mid_color_val, self.mid_btn))
        self.max_btn.configure(command=lambda: choose_color(self.max_color_val, self.max_btn))
        


        # Transition Speed Slider Frame
        speed_frame = tk.LabelFrame(container, text=" Color Transition Speed ", fg=self.accent_color, bg=self.bg_color, bd=1, relief="solid", highlightthickness=0, font=("Segoe UI", 9, "bold"), labelanchor="nw", padx=10, pady=12)
        speed_frame.pack(fill="x", pady=5)
        
        speed_slider = tk.Scale(speed_frame, from_=1, to=10, orient="horizontal", variable=self.transition_speed_var, bg=self.bg_color, fg=self.fg_color, highlightthickness=0, activebackground=self.accent_color, troughcolor=self.card_bg)
        speed_slider.pack(fill="x", expand=True)

        # System Integration Frame (Lock/Screensaver auto-stop)
        integration_frame = tk.LabelFrame(container, text=" System Integration ", fg=self.accent_color, bg=self.bg_color, bd=1, relief="solid", highlightthickness=0, font=("Segoe UI", 9, "bold"), labelanchor="nw", padx=10, pady=10)
        integration_frame.pack(fill="x", pady=5)
        
        screensaver_check = tk.Checkbutton(integration_frame, text="Turn off LEDs when screensaver starts", variable=self.stop_on_screensaver_var, bg=self.bg_color, fg=self.fg_color, selectcolor=self.card_bg, activebackground=self.bg_color, activeforeground=self.fg_color, font=("Segoe UI", 9))
        screensaver_check.pack(anchor="w", pady=4)
        
        lock_check = tk.Checkbutton(integration_frame, text="Turn off LEDs when workstation locks", variable=self.stop_on_lock_var, bg=self.bg_color, fg=self.fg_color, selectcolor=self.card_bg, activebackground=self.bg_color, activeforeground=self.fg_color, font=("Segoe UI", 9))
        lock_check.pack(anchor="w", pady=4)

    def setup_advanced_tab(self):
        container = tk.Frame(self.tab_advanced, bg=self.bg_color, padx=10, pady=10)
        container.pack(fill="both", expand=True)
        
        # Device Selector
        selector_frame = tk.Frame(container, bg=self.bg_color)
        selector_frame.pack(fill="x", pady=(0, 5))
        
        tk.Label(selector_frame, text="Select Device:", fg=self.fg_color, bg=self.bg_color, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 10))
        
        self.device_combo = ttk.Combobox(selector_frame, state="readonly", width=35)
        self.device_combo.pack(side="left", fill="x", expand=True)
        self.device_combo.bind("<<ComboboxSelected>>", self.on_device_selected)
        
        self.gpu_status_label = tk.Label(selector_frame, text="", fg=self.text_muted, bg=self.bg_color, font=("Segoe UI", 8, "italic"))
        self.gpu_status_label.pack(side="left", padx=10)
        
        # If no devices
        self.no_dev_label = tk.Label(container, text="Connecting to OpenRGB SDK...", fg=self.text_muted, bg=self.bg_color, font=("Segoe UI", 10))
        
        # Device details container
        self.dev_frame = tk.Frame(container, bg=self.bg_color)

        
        # Quick apply panel
        quick_panel = tk.Frame(self.dev_frame, bg=self.card_bg, pady=8, padx=10, bd=1, relief="solid", highlightthickness=0)
        quick_panel.pack(fill="x", pady=(0, 10))
        
        tk.Label(quick_panel, text="Set all:", fg=self.fg_color, bg=self.card_bg, font=("Segoe UI", 9, "bold")).pack(side="left")
        
        self.quick_scale_var = tk.IntVar(value=100)
        quick_scale = tk.Scale(quick_panel, from_=0, to=100, orient="horizontal", variable=self.quick_scale_var, bg=self.card_bg, fg=self.fg_color, highlightthickness=0, length=120, showvalue=True)
        quick_scale.pack(side="left", padx=5)
        
        self.quick_source_combo = ttk.Combobox(quick_panel, values=["CPU", "GPU"], state="readonly", width=5)
        self.quick_source_combo.set("CPU")
        self.quick_source_combo.pack(side="left", padx=5)
        
        apply_all_btn = tk.Button(quick_panel, text="Apply All", bg=self.accent_color, fg=self.fg_color, activebackground=self.accent_hover, activeforeground=self.fg_color, bd=0, padx=10, pady=4, font=("Segoe UI", 8, "bold"), command=self.apply_settings_to_all_leds)
        apply_all_btn.pack(side="left", padx=5)
        
        # Scrollable area for LEDs
        self.scroll_container = tk.Frame(self.dev_frame, bg=self.bg_color)
        self.scroll_container.pack(fill="both", expand=True)
        
        self.canvas = tk.Canvas(self.scroll_container, bg=self.bg_color, highlightthickness=0)
        self.scrollbar = tk.Scrollbar(self.scroll_container, orient="vertical", command=self.canvas.yview)
        
        # We wrapper the frame that holds list of items inside Canvas
        self.scroll_frame = tk.Frame(self.canvas, bg=self.bg_color)
        
        self.scroll_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            )
        )
        
        self.canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw", width=420)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        # Support mouse scrolling
        def _on_mousewheel(event):
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self.canvas.bind_all("<MouseWheel>", _on_mousewheel)

    def on_device_selected(self, event):
        # Clear previous elements
        for child in self.scroll_frame.winfo_children():
            child.destroy()
            
        device_name = self.device_combo.get()
        if not device_name or not controller.devices:
            return
            
        device = None
        for dev in controller.devices:
            if dev.name == device_name:
                device = dev
                break
                
        if not device:
            return
            
        if device.name not in self.temp_device_sources:
            self.temp_device_sources[device.name] = {}
            
        device_sources = self.temp_device_sources[device.name]
        # Legacy compatibility: if temp_device_sources stored a string previously instead of a dict
        if isinstance(device_sources, str):
            device_sources = {"default": device_sources}
            self.temp_device_sources[device.name] = device_sources
            
        device_default_source = device_sources.get("default", "cpu")
            
        leds = device.leds
        if not leds:
            tk.Label(self.scroll_frame, text="No controllable LEDs on this device.", fg=self.text_muted, bg=self.bg_color, font=("Segoe UI", 10)).pack(pady=20)
            return
            
        if device.name not in self.temp_led_brightness:
            self.temp_led_brightness[device.name] = {}
            
        # List of all individual LEDs
        for led in leds:
            row = tk.Frame(self.scroll_frame, bg=self.bg_color, pady=6)
            row.pack(fill="x", padx=5)
            
            # Led Label
            tk.Label(row, text=led.name, fg=self.fg_color, bg=self.bg_color, font=("Segoe UI", 9), anchor="w", width=18).pack(side="left")
            
            # Dropdown combobox for CPU/GPU source
            led_source = device_sources.get(led.name, device_default_source)
            source_var = tk.StringVar(value="GPU" if led_source == "gpu" else "CPU")
            
            source_vals = ["CPU", "GPU"] if nvml_available else ["CPU"]
            source_combo = ttk.Combobox(row, textvariable=source_var, values=source_vals, state="readonly", width=4)
            source_combo.pack(side="left", padx=5)
            
            def make_source_callback(d_name, l_name, s_var):
                def callback(event):
                    if d_name not in self.temp_device_sources:
                        self.temp_device_sources[d_name] = {}
                    if isinstance(self.temp_device_sources[d_name], str):
                        self.temp_device_sources[d_name] = {"default": self.temp_device_sources[d_name]}
                    self.temp_device_sources[d_name][l_name] = s_var.get().lower()
                return callback
                
            source_combo.bind("<<ComboboxSelected>>", make_source_callback(device.name, led.name, source_var))
            
            # Get current individual brightness or default to 100
            led_bright = self.temp_led_brightness[device.name].get(led.name, 100)
            scale_var = tk.IntVar(value=led_bright)
            
            # Label percentage
            val_label = tk.Label(row, text=f"{led_bright}%", fg=self.text_muted, bg=self.bg_color, font=("Segoe UI", 9), width=5)
            
            def make_callback(d_name, l_name, var):
                def callback(*args):
                    if d_name not in self.temp_led_brightness:
                        self.temp_led_brightness[d_name] = {}
                    self.temp_led_brightness[d_name][l_name] = var.get()
                return callback
                
            scale = tk.Scale(row, from_=0, to=100, orient="horizontal", variable=scale_var, bg=self.bg_color, fg=self.fg_color, highlightthickness=0, length=120, showvalue=False)
            scale.pack(side="left", padx=5)
            val_label.pack(side="left")
            
            scale_var.trace_add("write", make_callback(device.name, led.name, scale_var))
            
            def update_label(label, var):
                return lambda *args: label.configure(text=f"{var.get()}%")
            scale_var.trace_add("write", update_label(val_label, scale_var))

    def apply_settings_to_all_leds(self):
        device_name = self.device_combo.get()
        if not device_name:
            return
        bright_val = self.quick_scale_var.get()
        source_val = self.quick_source_combo.get().lower()
        
        if device_name not in self.temp_led_brightness:
            self.temp_led_brightness[device_name] = {}
        if device_name not in self.temp_device_sources:
            self.temp_device_sources[device_name] = {}
        if isinstance(self.temp_device_sources[device_name], str):
            self.temp_device_sources[device_name] = {"default": self.temp_device_sources[device_name]}
            
        self.temp_device_sources[device_name]["default"] = source_val
        
        for dev in controller.devices:
            if dev.name == device_name:
                for led in dev.leds:
                    self.temp_led_brightness[device_name][led.name] = bright_val
                    self.temp_device_sources[device_name][led.name] = source_val
                break
                
        # Re-render list
        self.on_device_selected(None)

    def show(self):
        load_config() # Reload configuration values
        
        # Reset variables in General settings
        self.min_temp_var.set(config["min_temp"])
        self.mid_temp_var.set(config["mid_temp"])
        self.max_temp_var.set(config["max_temp"])
        self.transition_speed_var.set(config.get("transition_speed", 5))
        self.stop_on_screensaver_var.set(config.get("stop_on_screensaver", False))
        self.stop_on_lock_var.set(config.get("stop_on_lock", False))
        
        self.min_color_val = list(config["min_color"])
        self.mid_color_val = list(config["mid_color"])
        self.max_color_val = list(config["max_color"])
        
        self.min_btn.configure(bg=self.rgb_to_hex(self.min_color_val), activebackground=self.rgb_to_hex(self.min_color_val))
        self.mid_btn.configure(bg=self.rgb_to_hex(self.mid_color_val), activebackground=self.rgb_to_hex(self.mid_color_val))
        self.max_btn.configure(bg=self.rgb_to_hex(self.max_color_val), activebackground=self.rgb_to_hex(self.max_color_val))
        
        # Load advanced settings into temp dictionary
        self.temp_led_brightness = json.loads(json.dumps(config.get("device_led_brightness", {})))
        self.temp_device_sources = json.loads(json.dumps(config.get("device_temp_source", {})))
        
        # Check NVML availability and set GPU status label + Combobox options
        init_nvml()
        if nvml_available:
            self.quick_source_combo.configure(values=["CPU", "GPU"])
            self.gpu_status_label.configure(text="")
        else:
            self.quick_source_combo.configure(values=["CPU"])
            self.quick_source_combo.set("CPU")
            self.gpu_status_label.configure(text="(NVIDIA GPU not detected)")
        
        # Populate Combobox with active OpenRGB devices
        if controller.running and controller.devices:
            device_names = [dev.name for dev in controller.devices]
            self.device_combo['values'] = device_names
            if device_names:
                self.device_combo.current(0)
                self.on_device_selected(None)
                self.no_dev_label.pack_forget()
                self.dev_frame.pack(fill="both", expand=True)
            else:
                self.device_combo['values'] = []
                self.dev_frame.pack_forget()
                self.no_dev_label.configure(text="No controllable OpenRGB devices found.")
                self.no_dev_label.pack(pady=50)
        else:
            self.device_combo['values'] = []
            self.dev_frame.pack_forget()
            self.no_dev_label.configure(text="OpenRGB SDK disconnected.\nPlease ensure OpenRGB SDK server is enabled on port 6742.")
            self.no_dev_label.pack(pady=50)
            
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide(self):
        self.root.withdraw()

    def save(self):
        try:
            min_t = self.min_temp_var.get()
            mid_t = self.mid_temp_var.get()
            max_t = self.max_temp_var.get()
            
            if not (min_t < mid_t < max_t):
                messagebox.showerror("Error", "Temperature thresholds must satisfy:\nLow < Mid < High", parent=self.root)
                return
                
            new_config = {
                "min_temp": min_t,
                "mid_temp": mid_t,
                "max_temp": max_t,
                "min_color": self.min_color_val,
                "mid_color": self.mid_color_val,
                "max_color": self.max_color_val,
                "brightness": 100,
                "device_led_brightness": self.temp_led_brightness,
                "device_temp_source": self.temp_device_sources,
                "transition_speed": self.transition_speed_var.get(),
                "stop_on_screensaver": self.stop_on_screensaver_var.get(),
                "stop_on_lock": self.stop_on_lock_var.get()
            }
            
            save_config(new_config)
            self.hide()
        except tk.TclError:
            messagebox.showerror("Error", "Please enter valid numeric temperatures.", parent=self.root)

settings_app = None

def setup_tray():
    # Helper functions for menu callbacks
    def on_exit(icon, item):
        controller.stop(icon)
        icon.stop()
        # Thread-safe destroy Tkinter mainloop on main thread

        if settings_app is not None:
            settings_app.root.after(0, settings_app.root.destroy)

    def toggle_sync(icon, item):
        if controller.running:
            controller.stop(icon)
        else:
            controller.start(icon)

    def toggle_startup_option(icon, item):
        state = not is_startup_enabled()
        set_startup_state(state)
        icon.update_menu()

    # Define system tray menu
    menu = pystray.Menu(
        pystray.MenuItem(lambda text: controller.status_text, lambda: None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            lambda text: "Stop Sync" if controller.running else "Start Sync",
            toggle_sync
        ),
        pystray.MenuItem("Settings", lambda icon, item: settings_app.show()),
        pystray.MenuItem(
            "Start with Windows",
            toggle_startup_option,
            checked=lambda item: is_startup_enabled()
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit", on_exit)
    )

    icon = pystray.Icon(
        "OpenRGBTempSync",
        icon=create_tray_image(),
        title="OpenRGB Temp Sync",
        menu=menu
    )

    # Automatically start sync in background
    controller.start(icon)
    if is_startup_enabled():
        set_startup_state(True)
        
    # Start pystray icon loop in a background thread so Tkinter can run on main thread
    threading.Thread(target=icon.run, daemon=True).start()

if __name__ == "__main__":
    # 1. Initialize settings window in main thread
    settings_app = SettingsGUI()
    
    # 2. Set up system tray icon in background thread
    setup_tray()
    
    # 3. Block and process GUI events safely on Main Thread
    settings_app.root.mainloop()


