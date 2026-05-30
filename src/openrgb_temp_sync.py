#!/usr/bin/env python3
"""
Delightful Newton - OpenRGB CPU Temperature Sync
Syncs AMD Ryzen / Intel CPU temperature (read via Core Temp) with RGB LED lighting.
"""

import argparse
import ctypes
import mmap
import time
import sys
from openrgb import OpenRGBClient
from openrgb.utils import RGBColor

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

def get_cpu_temperature():
    """Reads the current CPU temperature from Core Temp shared memory."""
    struct_size = ctypes.sizeof(CoreTempSharedDataEx)
    try:
        # Open existing named memory mapping from Core Temp
        with mmap.mmap(-1, struct_size, tagname="CoreTempMappingObjectEx", access=mmap.ACCESS_READ) as mm:
            data = CoreTempSharedDataEx.from_buffer_copy(mm)
            
            # Access temperature sensors (average active cores)
            core_count = data.uiCoreCnt
            if core_count == 0 or core_count > 256:
                return None
                
            temps = [data.fTemp[i] for i in range(core_count)]
            if not temps:
                return None
                
            # Compute average core temperature
            avg_temp = sum(temps) / len(temps)
            
            # Core Temp lists TjMax or Fahrenheit indicators
            if data.ucFahrenheit == 1:
                # Convert Fahrenheit to Celsius
                avg_temp = (avg_temp - 32) * 5 / 9
                
            return avg_temp
    except FileNotFoundError:
        # File mapping object not found (Core Temp app not running)
        return None
    except Exception as e:
        print(f"[-] Error reading Core Temp memory: {e}", file=sys.stderr)
        return None

def map_temp_to_rgb(temp, min_temp, mid_temp, max_temp, min_color=[0, 255, 0], mid_color=[0, 0, 255], max_color=[255, 0, 0], brightness=100):
    """Maps temperature to a smooth RGB gradient with customizable colors and brightness."""
    if temp <= min_temp:
        r, g, b = min_color
    elif temp >= max_temp:
        r, g, b = max_color
    elif temp < mid_temp:
        ratio = (temp - min_temp) / (mid_temp - min_temp)
        r = int(min_color[0] + (mid_color[0] - min_color[0]) * ratio)
        g = int(min_color[1] + (mid_color[1] - min_color[1]) * ratio)
        b = int(min_color[2] + (mid_color[2] - min_color[2]) * ratio)
    else:
        ratio = (temp - mid_temp) / (max_temp - mid_temp)
        r = int(mid_color[0] + (max_color[0] - mid_color[0]) * ratio)
        g = int(mid_color[1] + (max_color[1] - mid_color[1]) * ratio)
        b = int(mid_color[2] + (max_color[2] - mid_color[2]) * ratio)

    # Apply brightness
    factor = max(0, min(100, brightness)) / 100.0
    r = int(r * factor)
    g = int(g * factor)
    b = int(b * factor)

    return max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))

def main():
    parser = argparse.ArgumentParser(description="Syncs CPU temperature with OpenRGB LED lighting.")
    parser.add_argument("--host", default="127.0.0.1", help="OpenRGB SDK server host address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=6742, help="OpenRGB SDK server port number (default: 6742)")
    parser.add_argument("--interval", type=float, default=2.0, help="Polling interval in seconds (default: 2.0)")
    parser.add_argument("--min-temp", type=float, default=30.0, help="Minimum temperature threshold in °C (Green) (default: 30.0)")
    parser.add_argument("--mid-temp", type=float, default=60.0, help="Middle temperature threshold in °C (Blue) (default: 60.0)")
    parser.add_argument("--max-temp", type=float, default=75.0, help="Maximum temperature threshold in °C (Red) (default: 75.0)")
    parser.add_argument("--simulate", action="store_true", help="Run in color simulation testing mode")
    
    args = parser.parse_args()

    print("==================================================")
    print("  Delightful Newton: OpenRGB Temp Sync Controller")
    print("==================================================")
    
    # 1. Connect to OpenRGB Server
    print(f"[*] Connecting to OpenRGB Server at {args.host}:{args.port}...")
    try:
        client = OpenRGBClient(args.host, args.port)
        devices = client.devices
        if not devices:
            print("[-] Connected, but no RGB devices were detected by OpenRGB.")
            sys.exit(1)
        print(f"[+] Connected successfully! Found {len(devices)} RGB devices:")
        for idx, dev in enumerate(devices):
            print(f"    {idx + 1}. {dev.name} ({len(dev.leds)} LEDs)")
    except Exception as e:
        print(f"[-] Failed to connect to OpenRGB SDK server: {e}")
        print("    Please ensure:")
        print("    1. OpenRGB is running.")
        print("    2. 'SDK Server' is turned ON in the 'SDK Server' settings tab.")
        sys.exit(1)

    print("\n[*] Starting monitoring loop... (Press Ctrl+C to stop)")
    print(f"[*] Settings: Range {args.min_temp}°C - {args.max_temp}°C | Poll Interval: {args.interval}s")
    
    sim_temp = args.min_temp
    sim_direction = 1.5  # Temp change rate per interval during simulation

    try:
        while True:
            # 2. Query Temperature
            if args.simulate:
                # Simulate thermal changes
                temp = sim_temp
                sim_temp += sim_direction
                if sim_temp >= args.max_temp + 5 or sim_temp <= args.min_temp - 5:
                    sim_direction = -sim_direction  # Reverse heating/cooling
            else:
                temp = get_cpu_temperature()
            
            # 3. Handle temperature readings
            if temp is None:
                print("[-] Waiting for Core Temp... (Make sure the Core Temp app is running as Administrator)", end="\r")
                time.sleep(args.interval)
                continue
                
            # 4. Map temperature to colors
            r, g, b = map_temp_to_rgb(temp, args.min_temp, args.mid_temp, args.max_temp)
            color = RGBColor(r, g, b)
            
            # Print update status line
            sim_flag = "[SIMULATION] " if args.simulate else ""
            print(f"[+] {sim_flag}CPU Temperature: {temp:.1f}°C  ==> Color: RGB({r}, {g}, {b})     ", end="\r")
            
            # 5. Apply colors to all OpenRGB devices
            for device in devices:
                try:
                    # Use fast=True if supported by binding to prevent socket locks
                    device.set_color(color, fast=True)
                except Exception:
                    try:
                        device.set_color(color)
                    except Exception as dev_err:
                        # Fail silently on single device updates
                        pass
                        
            time.sleep(args.interval)
            
    except KeyboardInterrupt:
        print("\n[*] Monitoring stopped by user. Resetting lights to neutral white...")
        # Reset color to soft neutral white on exit
        neutral = RGBColor(200, 200, 200)
        for device in client.devices:
            try:
                device.set_color(neutral)
            except Exception:
                pass
        print("[+] Lights reset. Goodbye!")

if __name__ == "__main__":
    main()
