# Plan - RGB Temp Colors & Brightness Customization

This plan details how to implement customizable RGB temperature colors for three thresholds (Low, Mid, High) and a global brightness slider in the OpenRGB Temp Sync tray application, including a settings GUI window and persistent storage.

---

## User Review Required

- **Settings Access:** A new item `"Settings"` will be added to the system tray menu. Clicking it will open a custom styled dark-theme configuration window.
- **Tkinter GUI:** We will use Python's built-in `tkinter` library to build the settings GUI window. This keeps the application extremely lightweight and avoids adding huge external packages like PyQt/PySide.
- **Live Reload:** Saving the settings will immediately apply the new colors and brightness to the active temperature sync thread without needing to restart the app.

---

## Proposed Changes

### Configuration Storage
A new `config.json` file will be created in the same folder as the executable to persist settings:
```json
{
  "min_temp": 30.0,
  "mid_temp": 60.0,
  "max_temp": 75.0,
  "min_color": [0, 255, 0],
  "mid_color": [0, 0, 255],
  "max_color": [255, 0, 0],
  "brightness": 100
}
```

### [MODIFY] [openrgb_tray_app.py](file:///C:/Users/DO%20DO/Documents/antigravity/delightful-newton/src/openrgb_tray_app.py)

#### 1. Configuration Lifecycle
- Add functions `load_config()` and `save_config(config_data)` using `os.path.dirname(sys.executable)` to ensure portability.
- Define a global configuration dict that gets dynamically loaded on app startup.

#### 2. Settings GUI Window (Tkinter)
- Create `open_settings_ui()` running in a dedicated thread.
- **Theme:** Styled with a dark-theme color palette matching the application design system:
  - Background: `#1e1e2e` (Deep navy/charcoal)
  - Text: `#ffffff`
  - Accents/Buttons: `#4f46e5` (Indigo neon) / `#2e303f`
- **Fields:**
  - Temperature inputs for Low (`min_temp`), Mid (`mid_temp`), and High (`max_temp`) thresholds.
  - Color picker buttons for each threshold showing the selected color.
  - A horizontal slider for brightness (0% - 100%).
- **Callbacks:**
  - Click on color preview -> opens `tkinter.colorchooser.askcolor()`.
  - "Save" -> validates input, writes to `config.json`, updates global memory configuration, closes window.
  - "Cancel" -> discards edits, closes window.

#### 3. Color Sync Integration
- Update `map_temp_to_rgb(temp)` to interpolate channels dynamically between the user's custom threshold colors (`min_color`, `mid_color`, `max_color`).
- Apply the global brightness scaling factor (`brightness / 100.0`) to the final RGB color values before sending them to OpenRGB.

---

## Verification Plan

### Automated/Unit Verification
- Run [test_openrgb_sync.py](file:///C:/Users/DO%20DO/Documents/antigravity/delightful-newton/src/test_openrgb_sync.py) to confirm color calculations are still correct and apply brightness logic. We will modify it to test custom color inputs and scaling factors.

### Manual Verification
1. Run `python src/openrgb_tray_app.py` in development mode.
2. Right-click the tray icon and click **"Settings"**.
3. Change the colors (e.g., change Mid from Blue to Yellow) and adjust brightness to 50%.
4. Save and verify that the config file is updated and that the OpenRGB lighting adjusts immediately.
5. Compile the app using `pyinstaller` and verify that the executable `OpenRGBTempSync.exe` runs correctly and saves settings.
