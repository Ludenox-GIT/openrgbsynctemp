"""
Settings GUI for OpenRGB Temp Sync.
OpenRGB-like Device -> Zone -> LED selection surface, Manual RGB/HSV/Hex color,
transactional Edit Zone dialog, and preserved thermal sync settings.
"""

import copy
import json
import logging
import threading
import time
import tkinter as tk
from tkinter import colorchooser, messagebox, simpledialog, ttk
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from openrgb_temp_sync.config import (
    merge_legacy_device_profiles,
    reconcile_device_profiles_on_save
)
from openrgb_temp_sync.ui_model import (
    ColorState,
    DeviceTreeItem,
    EditZoneTransaction,
    UIModel,
    ZoneTreeItem,
    build_target_colors,
    hex_to_rgb,
    hsv_to_rgb,
    rgb_to_hex,
    rgb_to_hsv
)

logger = logging.getLogger("OpenRGBUI")


class EditZoneDialog(tk.Toplevel):
    """Transactional Edit Zone dialog for resizable addressable RGB zones."""

    def __init__(
        self,
        parent: tk.Tk,
        supervisor: Any,
        controller: Any,
        config_manager: Any,
        device_item: DeviceTreeItem,
        zone_item: ZoneTreeItem,
        on_success: Callable[[], None]
    ):
        super().__init__(parent)
        self.title(f"Edit Zone — {zone_item.name}")
        self.geometry("380x330")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.supervisor = supervisor
        self.controller = controller
        self.config_manager = config_manager
        self.device_item = device_item
        self.zone_item = zone_item
        self.on_success = on_success

        self.bg_color = "#121214"
        self.card_bg = "#1e1e24"
        self.fg_color = "#ffffff"
        self.accent_color = "#4f46e5"
        self.accent_hover = "#6366f1"
        self.text_muted = "#a1a1aa"

        self.configure(bg=self.bg_color)

        pad = 12
        content = tk.Frame(self, bg=self.bg_color, padx=pad, pady=pad)
        content.pack(fill="both", expand=True)

        tk.Label(
            content,
            text=f"Edit Zone: {zone_item.name}",
            font=("Segoe UI", 11, "bold"),
            fg=self.fg_color,
            bg=self.bg_color
        ).pack(anchor="w", pady=(0, 4))

        tk.Label(
            content,
            text=f"Device: {device_item.display_label}",
            font=("Segoe UI", 8),
            fg=self.text_muted,
            bg=self.bg_color
        ).pack(anchor="w", pady=(0, 8))

        info_frame = tk.Frame(content, bg=self.card_bg, padx=10, pady=8, bd=1, relief="solid")
        info_frame.pack(fill="x", pady=(0, 10))

        tk.Label(
            info_frame,
            text=f"Current Count: {zone_item.led_count} LEDs",
            font=("Segoe UI", 9, "bold"),
            fg=self.fg_color,
            bg=self.card_bg
        ).pack(anchor="w")

        tk.Label(
            info_frame,
            text=f"Supported Range: {zone_item.leds_min} to {zone_item.leds_max} LEDs",
            font=("Segoe UI", 8),
            fg=self.text_muted,
            bg=self.card_bg
        ).pack(anchor="w", pady=(2, 4))

        tk.Label(
            info_frame,
            text="Notice: Software LED count configures data packets.\nHardware power limits and hub wiring apply separately.",
            font=("Segoe UI", 7),
            fg=self.text_muted,
            bg=self.card_bg,
            justify="left"
        ).pack(anchor="w")

        input_frame = tk.Frame(content, bg=self.bg_color)
        input_frame.pack(fill="x", pady=6)

        tk.Label(
            input_frame,
            text="New LED Count:",
            font=("Segoe UI", 9, "bold"),
            fg=self.fg_color,
            bg=self.bg_color
        ).pack(side="left", padx=(0, 8))

        self.count_var = tk.StringVar(value=str(zone_item.led_count))
        self.spin = tk.Spinbox(
            input_frame,
            from_=zone_item.leds_min,
            to=zone_item.leds_max,
            textvariable=self.count_var,
            width=8,
            font=("Segoe UI", 10),
            bg=self.card_bg,
            fg=self.fg_color,
            buttonbackground=self.card_bg
        )
        self.spin.pack(side="left")

        test_btn = tk.Button(
            content,
            text="Test / Find LED",
            font=("Segoe UI", 8),
            bg="#27272a",
            fg=self.fg_color,
            bd=0,
            padx=8,
            pady=3,
            command=self._find_led_test
        )
        test_btn.pack(anchor="w", pady=(4, 10))

        btn_frame = tk.Frame(content, bg=self.bg_color)
        btn_frame.pack(fill="x", side="bottom")

        apply_btn = tk.Button(
            btn_frame,
            text="Apply",
            font=("Segoe UI", 9, "bold"),
            bg=self.accent_color,
            fg=self.fg_color,
            activebackground=self.accent_hover,
            activeforeground=self.fg_color,
            bd=0,
            padx=14,
            pady=4,
            command=self._apply
        )
        apply_btn.pack(side="right", padx=(4, 0))

        cancel_btn = tk.Button(
            btn_frame,
            text="Cancel",
            font=("Segoe UI", 9),
            bg="#33333b",
            fg=self.fg_color,
            bd=0,
            padx=14,
            pady=4,
            command=self._cancel
        )
        cancel_btn.pack(side="right", padx=4)

    def _find_led_test(self):
        try:
            val = int(self.count_var.get())
        except ValueError:
            val = self.zone_item.led_count

        def worker():
            try:
                try:
                    from openrgb.utils import RGBColor
                    test_color = RGBColor(255, 255, 255)
                except ImportError:
                    test_color = (255, 255, 255)
                sup = self.supervisor
                dev_key = self.device_item.key
                sup.set_colors(dev_key, [test_color] * max(1, val), fast=True)
                time.sleep(1.2)
                sup.restore_device(dev_key)
            except Exception as ex:
                logger.warning("Find LED test failed: %s", ex)

        threading.Thread(target=worker, daemon=True).start()

    def _cancel(self):
        tx = EditZoneTransaction()
        tx.cancel()
        self.destroy()

    def _apply(self):
        tx = EditZoneTransaction()
        valid, val, err = tx.validate_count(
            self.count_var.get(),
            self.zone_item.leds_min,
            self.zone_item.leds_max
        )
        if not valid:
            messagebox.showerror("Invalid LED Count", err, parent=self)
            return

        target_key = getattr(self.device_item.descriptor, "stable_key", None) or self.device_item.key
        ok, msg = tx.apply(
            supervisor=self.supervisor,
            controller=self.controller,
            config_manager=self.config_manager,
            target_key=target_key,
            device_name=self.device_item.name,
            zone_index=self.zone_item.index,
            zone_name=self.zone_item.name,
            new_count=val,
            min_count=self.zone_item.leds_min,
            max_count=self.zone_item.leds_max
        )

        if not ok:
            messagebox.showerror("Resize Failed", msg, parent=self)
            return

        messagebox.showinfo("Zone Resized", msg, parent=self)
        if self.on_success:
            self.on_success()
        self.destroy()


class SettingsGUI:
    """Tkinter settings window running on the main thread."""

    def __init__(
        self,
        config_manager: Any,
        controller: Any,
        on_save_callback: Optional[Callable[[], None]] = None
    ):
        self.config_manager = config_manager
        self.controller = controller
        self.on_save_callback = on_save_callback

        self.root = tk.Tk()
        self.root.title("OpenRGB Temp Sync Settings")
        self.root.geometry("880x620")
        self.root.minsize(800, 550)
        self.root.withdraw()

        self.bg_color = "#121214"
        self.card_bg = "#1e1e24"
        self.fg_color = "#ffffff"
        self.accent_color = "#4f46e5"
        self.accent_hover = "#6366f1"
        self.text_muted = "#a1a1aa"

        self.root.configure(bg=self.bg_color)

        self.style = ttk.Style()
        self.style.theme_use("default")
        self.style.configure("TNotebook", background=self.bg_color, borderwidth=0)
        self.style.configure(
            "TNotebook.Tab",
            background=self.card_bg,
            foreground=self.fg_color,
            borderwidth=0,
            padding=[10, 5],
            font=("Segoe UI", 9, "bold")
        )
        self.style.map(
            "TNotebook.Tab",
            background=[("selected", self.accent_color)],
            foreground=[("selected", self.fg_color)]
        )
        self.style.configure(
            "Treeview",
            background=self.card_bg,
            foreground=self.fg_color,
            fieldbackground=self.card_bg,
            font=("Segoe UI", 8),
            borderwidth=0
        )
        self.style.map("Treeview", background=[("selected", self.accent_color)])

        self.tree_items: List[DeviceTreeItem] = []
        self.selected_device: Optional[DeviceTreeItem] = None
        self.selected_zone: Optional[ZoneTreeItem] = None
        self.selected_led_indices: List[int] = []

        self.color_state = ColorState(255, 0, 0)
        self.temp_devices_config: Dict[str, Any] = {}

        self._setup_header()
        self._setup_main_body()
        self._setup_bottom_bar()

        self.root.protocol("WM_DELETE_WINDOW", self.hide)

    def rgb_to_hex(self, rgb: Sequence[int]) -> str:
        return rgb_to_hex((int(rgb[0]), int(rgb[1]), int(rgb[2])))

    def _setup_header(self):
        header_frame = tk.Frame(self.root, bg=self.bg_color, padx=12, pady=6)
        header_frame.pack(fill="x")

        title_box = tk.Frame(header_frame, bg=self.bg_color)
        title_box.pack(side="left")

        tk.Label(
            title_box,
            text="OpenRGB Temp Sync",
            font=("Segoe UI", 12, "bold"),
            fg=self.fg_color,
            bg=self.bg_color
        ).pack(anchor="w")

        self.status_badge = tk.Label(
            title_box,
            text="Engine: Initializing...",
            font=("Segoe UI", 8),
            fg=self.text_muted,
            bg=self.bg_color
        )
        self.status_badge.pack(anchor="w")

        rescan_btn = tk.Button(
            header_frame,
            text="Rescan Devices",
            font=("Segoe UI", 8, "bold"),
            bg="#27272a",
            fg=self.fg_color,
            activebackground="#3f3f46",
            activeforeground=self.fg_color,
            bd=0,
            padx=10,
            pady=4,
            command=self._rescan_inventory
        )
        rescan_btn.pack(side="right", padx=4)

    def _setup_main_body(self):
        body = tk.Frame(self.root, bg=self.bg_color, padx=10, pady=4)
        body.pack(fill="both", expand=True)

        body.columnconfigure(0, weight=3, minsize=220)
        body.columnconfigure(1, weight=3, minsize=220)
        body.columnconfigure(2, weight=4, minsize=320)
        body.rowconfigure(0, weight=1)

        self._setup_left_tree(body)
        self._setup_center_selection(body)
        self._setup_right_tabs(body)

    def _setup_left_tree(self, parent: tk.Frame):
        tree_frame = tk.LabelFrame(
            parent,
            text=" Devices & Zones ",
            fg=self.accent_color,
            bg=self.bg_color,
            bd=1,
            relief="solid",
            font=("Segoe UI", 8, "bold"),
            padx=4,
            pady=4
        )
        tree_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        self.tree = ttk.Treeview(tree_frame, selectmode="browse", show="tree")
        scroll_y = tk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll_y.set)

        self.tree.pack(side="left", fill="both", expand=True)
        scroll_y.pack(side="right", fill="y")

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

    def _setup_center_selection(self, parent: tk.Frame):
        center_frame = tk.LabelFrame(
            parent,
            text=" Selection & LEDs ",
            fg=self.accent_color,
            bg=self.bg_color,
            bd=1,
            relief="solid",
            font=("Segoe UI", 8, "bold"),
            padx=6,
            pady=4
        )
        center_frame.grid(row=0, column=1, sticky="nsew", padx=4)

        self.sel_info_label = tk.Label(
            center_frame,
            text="No target selected",
            font=("Segoe UI", 9, "bold"),
            fg=self.fg_color,
            bg=self.bg_color,
            anchor="w"
        )
        self.sel_info_label.pack(fill="x", pady=(0, 2))

        self.sel_subinfo_label = tk.Label(
            center_frame,
            text="Select a device or zone on the left.",
            font=("Segoe UI", 8),
            fg=self.text_muted,
            bg=self.bg_color,
            anchor="w"
        )
        self.sel_subinfo_label.pack(fill="x", pady=(0, 4))

        self.edit_zone_btn = tk.Button(
            center_frame,
            text="Edit Zone LED Count...",
            font=("Segoe UI", 8, "bold"),
            bg=self.accent_color,
            fg=self.fg_color,
            activebackground=self.accent_hover,
            activeforeground=self.fg_color,
            bd=0,
            padx=8,
            pady=3,
            state="disabled",
            command=self._open_edit_zone_dialog
        )
        self.edit_zone_btn.pack(fill="x", pady=(0, 6))

        act_bar = tk.Frame(center_frame, bg=self.bg_color)
        act_bar.pack(fill="x", pady=(0, 4))

        tk.Button(
            act_bar,
            text="Select All",
            font=("Segoe UI", 7),
            bg="#27272a",
            fg=self.fg_color,
            bd=0,
            padx=6,
            pady=2,
            command=self._select_all_leds
        ).pack(side="left", padx=(0, 4))

        tk.Button(
            act_bar,
            text="Deselect All",
            font=("Segoe UI", 7),
            bg="#27272a",
            fg=self.fg_color,
            bd=0,
            padx=6,
            pady=2,
            command=self._deselect_all_leds
        ).pack(side="left")

        led_box_frame = tk.Frame(center_frame, bg=self.bg_color)
        led_box_frame.pack(fill="both", expand=True)

        self.led_listbox = tk.Listbox(
            led_box_frame,
            selectmode="extended",
            bg=self.card_bg,
            fg=self.fg_color,
            selectbackground=self.accent_color,
            selectforeground=self.fg_color,
            font=("Consolas", 9),
            bd=0,
            highlightthickness=0
        )
        led_scroll = tk.Scrollbar(led_box_frame, orient="vertical", command=self.led_listbox.yview)
        self.led_listbox.configure(yscrollcommand=led_scroll.set)

        self.led_listbox.pack(side="left", fill="both", expand=True)
        led_scroll.pack(side="right", fill="y")

        self.led_listbox.bind("<<ListboxSelect>>", self._on_led_select)

    def _setup_right_tabs(self, parent: tk.Frame):
        tab_frame = tk.Frame(parent, bg=self.bg_color)
        tab_frame.grid(row=0, column=2, sticky="nsew", padx=(4, 0))

        self.notebook = ttk.Notebook(tab_frame)
        self.notebook.pack(fill="both", expand=True)

        self.tab_manual = tk.Frame(self.notebook, bg=self.bg_color)
        self.tab_effects = tk.Frame(self.notebook, bg=self.bg_color)
        self.tab_temp = tk.Frame(self.notebook, bg=self.bg_color)

        self.notebook.add(self.tab_manual, text=" Manual ")
        self.notebook.add(self.tab_effects, text=" Effects ")
        self.notebook.add(self.tab_temp, text=" Temperature ")

        self._setup_manual_tab()
        self._setup_effects_tab()
        self._setup_temperature_tab()

    def _setup_manual_tab(self):
        container = tk.Frame(self.tab_manual, bg=self.bg_color, padx=10, pady=8)
        container.pack(fill="both", expand=True)

        scope_box = tk.LabelFrame(
            container,
            text=" Target Scope Preview ",
            fg=self.accent_color,
            bg=self.bg_color,
            bd=1,
            relief="solid",
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=4
        )
        scope_box.pack(fill="x", pady=(0, 8))

        self.scope_preview_label = tk.Label(
            scope_box,
            text="Select a target device/zone",
            font=("Segoe UI", 8),
            fg=self.fg_color,
            bg=self.bg_color,
            anchor="w"
        )
        self.scope_preview_label.pack(fill="x")

        color_row = tk.Frame(container, bg=self.bg_color)
        color_row.pack(fill="x", pady=(0, 8))

        self.swatch_canvas = tk.Canvas(
            color_row,
            width=64,
            height=32,
            bg="#ff0000",
            bd=1,
            relief="solid",
            highlightthickness=0
        )
        self.swatch_canvas.pack(side="left", padx=(0, 10))

        choose_btn = tk.Button(
            color_row,
            text="Choose Color...",
            font=("Segoe UI", 8),
            bg="#27272a",
            fg=self.fg_color,
            activebackground="#3f3f46",
            activeforeground=self.fg_color,
            bd=0,
            padx=10,
            pady=5,
            command=self._open_color_chooser
        )
        choose_btn.pack(side="left")

        presets_frame = tk.Frame(container, bg=self.bg_color)
        presets_frame.pack(fill="x", pady=(0, 8))

        swatch_colors = [
            ("#ff0000", "Red"),
            ("#00ff00", "Green"),
            ("#0000ff", "Blue"),
            ("#ffff00", "Yellow"),
            ("#00ffff", "Cyan"),
            ("#ff00ff", "Magenta"),
            ("#ffffff", "White"),
            ("#000000", "Off")
        ]
        for hex_code, name in swatch_colors:
            btn = tk.Button(
                presets_frame,
                bg=hex_code,
                width=2,
                height=1,
                bd=1,
                relief="solid",
                command=lambda h=hex_code: self._set_color_from_hex(h)
            )
            btn.pack(side="left", padx=2)

        hex_row = tk.Frame(container, bg=self.bg_color)
        hex_row.pack(fill="x", pady=2)

        tk.Label(hex_row, text="Hex:", font=("Segoe UI", 8, "bold"), fg=self.fg_color, bg=self.bg_color, width=6, anchor="w").pack(side="left")
        self.manual_hex_var = tk.StringVar(value="#ff0000")
        self.hex_entry = tk.Entry(hex_row, textvariable=self.manual_hex_var, width=10, font=("Consolas", 9), bg=self.card_bg, fg=self.fg_color, bd=1, relief="solid")
        self.hex_entry.pack(side="left", padx=4)
        self.hex_entry.bind("<Return>", lambda e: self._on_hex_entry_change())
        self.hex_entry.bind("<FocusOut>", lambda e: self._on_hex_entry_change())

        rgb_row = tk.Frame(container, bg=self.bg_color)
        rgb_row.pack(fill="x", pady=2)

        tk.Label(rgb_row, text="RGB:", font=("Segoe UI", 8, "bold"), fg=self.fg_color, bg=self.bg_color, width=6, anchor="w").pack(side="left")
        self.r_var = tk.IntVar(value=255)
        self.g_var = tk.IntVar(value=0)
        self.b_var = tk.IntVar(value=0)

        for var, col in [(self.r_var, "R"), (self.g_var, "G"), (self.b_var, "B")]:
            tk.Label(rgb_row, text=col, font=("Segoe UI", 7), fg=self.text_muted, bg=self.bg_color).pack(side="left")
            sp = tk.Spinbox(rgb_row, from_=0, to=255, textvariable=var, width=4, font=("Segoe UI", 8), bg=self.card_bg, fg=self.fg_color, buttonbackground=self.card_bg)
            sp.pack(side="left", padx=(1, 4))
            var.trace_add("write", lambda *a: self._on_rgb_vars_change())

        hsv_row = tk.Frame(container, bg=self.bg_color)
        hsv_row.pack(fill="x", pady=2)

        tk.Label(hsv_row, text="HSV:", font=("Segoe UI", 8, "bold"), fg=self.fg_color, bg=self.bg_color, width=6, anchor="w").pack(side="left")
        self.h_var = tk.IntVar(value=0)
        self.s_var = tk.IntVar(value=100)
        self.v_var = tk.IntVar(value=100)

        for var, col, mx in [(self.h_var, "H", 359), (self.s_var, "S", 100), (self.v_var, "V", 100)]:
            tk.Label(hsv_row, text=col, font=("Segoe UI", 7), fg=self.text_muted, bg=self.bg_color).pack(side="left")
            sp = tk.Spinbox(hsv_row, from_=0, to=mx, textvariable=var, width=4, font=("Segoe UI", 8), bg=self.card_bg, fg=self.fg_color, buttonbackground=self.card_bg)
            sp.pack(side="left", padx=(1, 4))
            var.trace_add("write", lambda *a: self._on_hsv_vars_change())

        self.apply_color_btn = tk.Button(
            container,
            text="Apply Color to Scope",
            font=("Segoe UI", 9, "bold"),
            bg=self.accent_color,
            fg=self.fg_color,
            activebackground=self.accent_hover,
            activeforeground=self.fg_color,
            bd=0,
            padx=12,
            pady=6,
            command=self._apply_manual_color
        )
        self.apply_color_btn.pack(fill="x", pady=(12, 4))

        self.apply_result_label = tk.Label(
            container,
            text="",
            font=("Segoe UI", 8),
            fg=self.text_muted,
            bg=self.bg_color,
            anchor="w"
        )
        self.apply_result_label.pack(fill="x")

    def _setup_effects_tab(self):
        container = tk.Frame(self.tab_effects, bg=self.bg_color, padx=10, pady=8)
        container.pack(fill="both", expand=True)

        tk.Label(
            container,
            text="Device Hardware Effects",
            font=("Segoe UI", 10, "bold"),
            fg=self.fg_color,
            bg=self.bg_color
        ).pack(anchor="w", pady=(0, 2))

        self.effects_target_label = tk.Label(
            container,
            text="Select a device from the tree to configure hardware modes.",
            font=("Segoe UI", 8),
            fg=self.text_muted,
            bg=self.bg_color
        )
        self.effects_target_label.pack(anchor="w", pady=(0, 6))

        mode_select_frame = tk.Frame(container, bg=self.card_bg, padx=8, pady=6, bd=1, relief="solid")
        mode_select_frame.pack(fill="x", pady=(0, 6))

        tk.Label(
            mode_select_frame,
            text="Hardware Mode:",
            font=("Segoe UI", 8, "bold"),
            fg=self.fg_color,
            bg=self.card_bg
        ).pack(side="left", padx=(0, 8))

        self.effects_mode_var = tk.StringVar()
        self.effects_mode_combo = ttk.Combobox(
            mode_select_frame,
            textvariable=self.effects_mode_var,
            state="disabled",
            width=20
        )
        self.effects_mode_combo.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.effects_mode_combo.bind("<<ComboboxSelected>>", self._on_effects_mode_changed)

        self.effects_params_frame = tk.LabelFrame(
            container,
            text=" Mode Parameters (Live Supported Only) ",
            fg=self.accent_color,
            bg=self.bg_color,
            bd=1,
            relief="solid",
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=6
        )
        self.effects_params_frame.pack(fill="x", pady=(0, 6))

        # Speed row
        speed_row = tk.Frame(self.effects_params_frame, bg=self.bg_color)
        speed_row.pack(fill="x", pady=2)
        tk.Label(speed_row, text="Speed:", width=10, anchor="w", fg=self.fg_color, bg=self.bg_color, font=("Segoe UI", 8)).pack(side="left")
        self.effects_speed_var = tk.IntVar(value=5)
        self.effects_speed_scale = tk.Scale(
            speed_row,
            from_=0,
            to=100,
            orient="horizontal",
            variable=self.effects_speed_var,
            bg=self.bg_color,
            fg=self.fg_color,
            troughcolor=self.card_bg,
            highlightthickness=0,
            state="disabled"
        )
        self.effects_speed_scale.pack(side="left", fill="x", expand=True, padx=4)
        self.effects_speed_reason = tk.Label(speed_row, text="", font=("Segoe UI", 7), fg=self.text_muted, bg=self.bg_color)
        self.effects_speed_reason.pack(side="right")

        # Brightness row
        bright_row = tk.Frame(self.effects_params_frame, bg=self.bg_color)
        bright_row.pack(fill="x", pady=2)
        tk.Label(bright_row, text="Brightness:", width=10, anchor="w", fg=self.fg_color, bg=self.bg_color, font=("Segoe UI", 8)).pack(side="left")
        self.effects_bright_var = tk.IntVar(value=100)
        self.effects_bright_scale = tk.Scale(
            bright_row,
            from_=0,
            to=100,
            orient="horizontal",
            variable=self.effects_bright_var,
            bg=self.bg_color,
            fg=self.fg_color,
            troughcolor=self.card_bg,
            highlightthickness=0,
            state="disabled"
        )
        self.effects_bright_scale.pack(side="left", fill="x", expand=True, padx=4)
        self.effects_bright_reason = tk.Label(bright_row, text="", font=("Segoe UI", 7), fg=self.text_muted, bg=self.bg_color)
        self.effects_bright_reason.pack(side="right")

        # Direction row
        dir_row = tk.Frame(self.effects_params_frame, bg=self.bg_color)
        dir_row.pack(fill="x", pady=2)
        tk.Label(dir_row, text="Direction:", width=10, anchor="w", fg=self.fg_color, bg=self.bg_color, font=("Segoe UI", 8)).pack(side="left")
        self.effects_dir_var = tk.StringVar()
        self.effects_dir_combo = ttk.Combobox(
            dir_row,
            textvariable=self.effects_dir_var,
            state="disabled",
            width=16
        )
        self.effects_dir_combo.pack(side="left", padx=4)
        self.effects_dir_reason = tk.Label(dir_row, text="", font=("Segoe UI", 7), fg=self.text_muted, bg=self.bg_color)
        self.effects_dir_reason.pack(side="right")

        # Color row
        col_row = tk.Frame(self.effects_params_frame, bg=self.bg_color)
        col_row.pack(fill="x", pady=2)
        tk.Label(col_row, text="Mode Color:", width=10, anchor="w", fg=self.fg_color, bg=self.bg_color, font=("Segoe UI", 8)).pack(side="left")
        self.effects_color_val = [255, 0, 0]
        self.effects_color_btn = tk.Button(
            col_row,
            text="Pick Color",
            width=8,
            bg="#dc2626",
            fg=self.fg_color,
            state="disabled",
            command=self._pick_effect_color
        )
        self.effects_color_btn.pack(side="left", padx=4)
        self.effects_color_reason = tk.Label(col_row, text="", font=("Segoe UI", 7), fg=self.text_muted, bg=self.bg_color)
        self.effects_color_reason.pack(side="right")

        tk.Label(
            container,
            text="Scope: Hardware effects execute on device controller and apply device-wide.",
            font=("Segoe UI", 7, "italic"),
            fg=self.text_muted,
            bg=self.bg_color,
            anchor="w"
        ).pack(fill="x", pady=(0, 6))

        actions_frame = tk.Frame(container, bg=self.bg_color)
        actions_frame.pack(fill="x", pady=2)

        self.apply_effect_btn = tk.Button(
            actions_frame,
            text="Apply Effect",
            bg=self.accent_color,
            fg=self.fg_color,
            activebackground=self.accent_hover,
            activeforeground=self.fg_color,
            bd=0,
            padx=10,
            pady=4,
            font=("Segoe UI", 8, "bold"),
            state="disabled",
            command=self._apply_hardware_effect
        )
        self.apply_effect_btn.pack(side="left", padx=(0, 6))

        self.save_to_device_btn = tk.Button(
            actions_frame,
            text="Save to Device (Flash)",
            bg="#374151",
            fg=self.fg_color,
            activebackground="#4b5563",
            activeforeground=self.fg_color,
            bd=0,
            padx=10,
            pady=4,
            font=("Segoe UI", 8),
            state="disabled",
            command=self._save_effect_to_device
        )
        self.save_to_device_btn.pack(side="left", padx=(0, 6))

        self.effects_save_reason = tk.Label(
            actions_frame,
            text="",
            font=("Segoe UI", 7),
            fg=self.text_muted,
            bg=self.bg_color
        )
        self.effects_save_reason.pack(side="left")

        self.effects_result_label = tk.Label(
            container,
            text="",
            font=("Segoe UI", 8),
            fg="#22c55e",
            bg=self.bg_color,
            anchor="w"
        )
        self.effects_result_label.pack(fill="x", pady=(4, 0))

    def _setup_temperature_tab(self):
        container = tk.Frame(self.tab_temp, bg=self.bg_color, padx=10, pady=8)
        container.pack(fill="both", expand=True)

        self.min_temp_var = tk.DoubleVar()
        self.mid_temp_var = tk.DoubleVar()
        self.max_temp_var = tk.DoubleVar()
        self.transition_speed_var = tk.IntVar()
        self.stop_on_screensaver_var = tk.BooleanVar()

        self.min_color_val = [0, 255, 0]
        self.mid_color_val = [0, 0, 255]
        self.max_color_val = [255, 0, 0]

        font_label = ("Segoe UI", 8, "bold")

        threshold_frame = tk.LabelFrame(
            container,
            text=" Temperature Thresholds & Colors ",
            fg=self.accent_color,
            bg=self.bg_color,
            bd=1,
            relief="solid",
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=8
        )
        threshold_frame.pack(fill="x", pady=(0, 6))

        threshold_frame.columnconfigure(0, weight=1)
        threshold_frame.columnconfigure(1, weight=1)
        threshold_frame.columnconfigure(2, weight=1)

        tk.Label(threshold_frame, text="Low / Idle", fg=self.fg_color, bg=self.bg_color, font=font_label).grid(row=0, column=0, sticky="w", pady=3)
        tk.Entry(threshold_frame, textvariable=self.min_temp_var, width=6, bg=self.card_bg, fg=self.fg_color, bd=1, relief="solid").grid(row=0, column=1, sticky="w", pady=3)
        self.min_btn = tk.Button(threshold_frame, width=5, height=1, bd=1, relief="solid")
        self.min_btn.grid(row=0, column=2, sticky="w", pady=3)

        tk.Label(threshold_frame, text="Medium", fg=self.fg_color, bg=self.bg_color, font=font_label).grid(row=1, column=0, sticky="w", pady=3)
        tk.Entry(threshold_frame, textvariable=self.mid_temp_var, width=6, bg=self.card_bg, fg=self.fg_color, bd=1, relief="solid").grid(row=1, column=1, sticky="w", pady=3)
        self.mid_btn = tk.Button(threshold_frame, width=5, height=1, bd=1, relief="solid")
        self.mid_btn.grid(row=1, column=2, sticky="w", pady=3)

        tk.Label(threshold_frame, text="High / Load", fg=self.fg_color, bg=self.bg_color, font=font_label).grid(row=2, column=0, sticky="w", pady=3)
        tk.Entry(threshold_frame, textvariable=self.max_temp_var, width=6, bg=self.card_bg, fg=self.fg_color, bd=1, relief="solid").grid(row=2, column=1, sticky="w", pady=3)
        self.max_btn = tk.Button(threshold_frame, width=5, height=1, bd=1, relief="solid")
        self.max_btn.grid(row=2, column=2, sticky="w", pady=3)

        def choose_thresh_color(color_list, button):
            initial_hex = self.rgb_to_hex(color_list)
            _, hex_color = colorchooser.askcolor(parent=self.root, title="Select Color", color=initial_hex)
            if hex_color:
                rgb = [int(hex_color[i:i+2], 16) for i in (1, 3, 5)]
                color_list[0] = rgb[0]
                color_list[1] = rgb[1]
                color_list[2] = rgb[2]
                button.configure(bg=hex_color, activebackground=hex_color)

        self.min_btn.configure(command=lambda: choose_thresh_color(self.min_color_val, self.min_btn))
        self.mid_btn.configure(command=lambda: choose_thresh_color(self.mid_color_val, self.mid_btn))
        self.max_btn.configure(command=lambda: choose_thresh_color(self.max_color_val, self.max_btn))

        speed_frame = tk.LabelFrame(
            container,
            text=" Color Transition Speed ",
            fg=self.accent_color,
            bg=self.bg_color,
            bd=1,
            relief="solid",
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=4
        )
        speed_frame.pack(fill="x", pady=4)
        tk.Scale(
            speed_frame,
            from_=1,
            to=10,
            orient="horizontal",
            variable=self.transition_speed_var,
            bg=self.bg_color,
            fg=self.fg_color,
            troughcolor=self.card_bg,
            highlightthickness=0
        ).pack(fill="x")

        integration_frame = tk.LabelFrame(
            container,
            text=" System Integration ",
            fg=self.accent_color,
            bg=self.bg_color,
            bd=1,
            relief="solid",
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=4
        )
        integration_frame.pack(fill="x", pady=4)
        tk.Checkbutton(
            integration_frame,
            text="Turn off LEDs when screensaver starts",
            variable=self.stop_on_screensaver_var,
            bg=self.bg_color,
            fg=self.fg_color,
            selectcolor=self.card_bg,
            activebackground=self.bg_color,
            activeforeground=self.fg_color,
            font=("Segoe UI", 8)
        ).pack(anchor="w", pady=2)

        owner_frame = tk.LabelFrame(
            container,
            text=" Target Device Control Ownership ",
            fg=self.accent_color,
            bg=self.bg_color,
            bd=1,
            relief="solid",
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=6
        )
        owner_frame.pack(fill="x", pady=(0, 6))

        self.device_owner_label = tk.Label(
            owner_frame,
            text="Select a device to view ownership status.",
            font=("Segoe UI", 8),
            fg=self.fg_color,
            bg=self.bg_color,
            anchor="w"
        )
        self.device_owner_label.pack(fill="x", pady=(0, 4))

        self.assign_thermal_btn = tk.Button(
            owner_frame,
            text="Assign to Temperature Sync (Direct Mode)",
            bg=self.accent_color,
            fg=self.fg_color,
            activebackground=self.accent_hover,
            activeforeground=self.fg_color,
            bd=0,
            padx=8,
            pady=3,
            font=("Segoe UI", 8, "bold"),
            command=self._assign_device_to_thermal
        )
        self.assign_thermal_btn.pack(anchor="w", pady=(0, 2))

        self.reset_device_btn = tk.Button(
            container,
            text="Restore Pre-Sync Snapshot",
            bg="#7f1d1d",
            fg=self.fg_color,
            activebackground="#991b1b",
            activeforeground=self.fg_color,
            bd=0,
            padx=8,
            pady=4,
            font=("Segoe UI", 8, "bold"),
            command=self._reset_or_resume_device
        )
        self.reset_device_btn.pack(fill="x", pady=(6, 2))

        self.factory_reset_btn = tk.Button(
            container,
            text="Restore Manufacturer Defaults",
            bg="#b91c1c",
            fg=self.fg_color,
            activebackground="#dc2626",
            activeforeground=self.fg_color,
            bd=0,
            padx=8,
            pady=4,
            font=("Segoe UI", 8, "bold"),
            command=self._factory_reset_action,
            state="disabled"
        )
        self.factory_reset_btn.pack(fill="x", pady=(0, 2))
        
        self.factory_reset_label = tk.Label(
            container,
            text="Select a device to see reset capability.",
            font=("Segoe UI", 7),
            fg=self.text_muted,
            bg=self.bg_color,
            anchor="w"
        )
        self.factory_reset_label.pack(fill="x", pady=(0, 6))

    def _setup_bottom_bar(self):
        profile_frame = tk.Frame(self.root, bg=self.bg_color, padx=12, pady=4)
        profile_frame.pack(fill="x", side="bottom")

        tk.Label(profile_frame, text="App Profile:", font=("Segoe UI", 8, "bold"), fg=self.fg_color, bg=self.bg_color).pack(side="left", padx=(0, 4))
        self.profile_var = tk.StringVar(value="Default")
        self.profile_combo = ttk.Combobox(profile_frame, textvariable=self.profile_var, state="readonly", width=14)
        self.profile_combo.pack(side="left", padx=(0, 6))

        tk.Button(
            profile_frame,
            text="Save Profile",
            bg="#27272a",
            fg=self.fg_color,
            bd=0,
            padx=6,
            pady=2,
            font=("Segoe UI", 8),
            command=self._save_profile_dialog
        ).pack(side="left", padx=2)

        tk.Button(
            profile_frame,
            text="Apply Profile",
            bg="#27272a",
            fg=self.fg_color,
            bd=0,
            padx=6,
            pady=2,
            font=("Segoe UI", 8),
            command=self._apply_profile_action
        ).pack(side="left", padx=2)

        tk.Button(
            profile_frame,
            text="Delete",
            bg="#27272a",
            fg=self.text_muted,
            bd=0,
            padx=6,
            pady=2,
            font=("Segoe UI", 8),
            command=self._delete_profile_action
        ).pack(side="left", padx=2)

        btn_frame = tk.Frame(self.root, bg=self.bg_color, pady=8, padx=12)
        btn_frame.pack(fill="x", side="bottom")

        save_btn = tk.Button(
            btn_frame,
            text="Save Settings",
            bg=self.accent_color,
            fg=self.fg_color,
            activebackground=self.accent_hover,
            activeforeground=self.fg_color,
            bd=0,
            padx=14,
            pady=5,
            font=("Segoe UI", 9, "bold"),
            command=self.save
        )
        save_btn.pack(side="right", padx=4)

        cancel_btn = tk.Button(
            btn_frame,
            text="Cancel",
            bg="#33333b",
            fg=self.fg_color,
            activebackground="#44444e",
            activeforeground=self.fg_color,
            bd=0,
            padx=14,
            pady=5,
            font=("Segoe UI", 9),
            command=self.hide
        )
        cancel_btn.pack(side="right", padx=4)

        diag_btn = tk.Button(
            btn_frame,
            text="Export Diagnostics",
            bg="#27272a",
            fg=self.text_muted,
            bd=0,
            padx=8,
            pady=5,
            font=("Segoe UI", 8),
            command=self._export_diag
        )
        diag_btn.pack(side="left", padx=4)

        retry_btn = tk.Button(
            btn_frame,
            text="Retry Engine",
            bg="#27272a",
            fg=self.text_muted,
            bd=0,
            padx=8,
            pady=5,
            font=("Segoe UI", 8),
            command=self._retry_engine
        )
        retry_btn.pack(side="left", padx=4)

    def _open_color_chooser(self):
        initial_hex = self.color_state.get_hex()
        _, hex_color = colorchooser.askcolor(parent=self.root, title="Choose Manual Color", color=initial_hex)
        if hex_color:
            self._set_color_from_hex(hex_color)

    def _set_color_from_hex(self, hex_code: str):
        if self.color_state.set_hex(hex_code):
            self._sync_color_widgets_from_state()

    def _on_hex_entry_change(self):
        val = self.manual_hex_var.get()
        if self.color_state.set_hex(val):
            self._sync_color_widgets_from_state()
        else:
            self.manual_hex_var.set(self.color_state.get_hex())

    def _on_rgb_vars_change(self):
        try:
            r = self.r_var.get()
            g = self.g_var.get()
            b = self.b_var.get()
            self.color_state.set_rgb(r, g, b)
            self.swatch_canvas.configure(bg=self.color_state.get_hex())
            self.manual_hex_var.set(self.color_state.get_hex())
            h, s, v = self.color_state.get_hsv()
            self.h_var.set(h)
            self.s_var.set(s)
            self.v_var.set(v)
        except (tk.TclError, ValueError):
            pass

    def _on_hsv_vars_change(self):
        try:
            h = self.h_var.get()
            s = self.s_var.get()
            v = self.v_var.get()
            self.color_state.set_hsv(h, s, v)
            self.swatch_canvas.configure(bg=self.color_state.get_hex())
            self.manual_hex_var.set(self.color_state.get_hex())
            r, g, b = self.color_state.get_rgb()
            self.r_var.set(r)
            self.g_var.set(g)
            self.b_var.set(b)
        except (tk.TclError, ValueError):
            pass

    def _sync_color_widgets_from_state(self):
        hx = self.color_state.get_hex()
        self.swatch_canvas.configure(bg=hx)
        self.manual_hex_var.set(hx)
        r, g, b = self.color_state.get_rgb()
        self.r_var.set(r)
        self.g_var.set(g)
        self.b_var.set(b)
        h, s, v = self.color_state.get_hsv()
        self.h_var.set(h)
        self.s_var.set(s)
        self.v_var.set(v)

    def _populate_device_tree(self):
        self.tree.delete(*self.tree.get_children())
        sup = getattr(self.controller, "openrgb_supervisor", self.controller)
        descriptors = sup.get_descriptors() if hasattr(sup, "get_descriptors") else []
        self.tree_items = UIModel.build_device_tree_items(descriptors)

        for dev_item in self.tree_items:
            dev_iid = dev_item.key
            self.tree.insert("", "end", iid=dev_iid, text=dev_item.display_label, open=True)

            for zone_item in dev_item.zones:
                zone_iid = f"zone:{dev_item.key}:{zone_item.index}"
                range_txt = f"{zone_item.leds_min}-{zone_item.leds_max}" if zone_item.resizable else "fixed"
                label = f"{zone_item.name} ({zone_item.led_count} LEDs, {range_txt})"
                self.tree.insert(dev_iid, "end", iid=zone_iid, text=label)

        if self.tree_items:
            first_iid = self.tree_items[0].key
            self.tree.selection_set(first_iid)
            self._select_tree_target(first_iid)
        else:
            self._clear_selection()

    def get_device_tree_labels(self) -> List[str]:
        """Return display labels of devices currently rendered in the tree."""
        return [item.display_label for item in self.tree_items]

    def _on_tree_select(self, event):
        selected_iids = self.tree.selection()
        if not selected_iids:
            return
        self._select_tree_target(selected_iids[0])

    def _select_tree_target(self, iid: str):
        if iid.startswith("zone:"):
            parts = iid.split(":", 2)
            dev_key = parts[1]
            zone_idx = int(parts[2])

            self.selected_device = next((d for d in self.tree_items if d.key == dev_key), None)
            self.selected_zone = self.selected_device.zones[zone_idx] if self.selected_device and zone_idx < len(self.selected_device.zones) else None

            if self.selected_device and self.selected_zone:
                self.sel_info_label.configure(text=f"{self.selected_device.display_label} > {self.selected_zone.name}")
                range_desc = f"Min: {self.selected_zone.leds_min}, Max: {self.selected_zone.leds_max}" if self.selected_zone.resizable else "Fixed (Non-resizable)"
                self.sel_subinfo_label.configure(text=f"LED Count: {self.selected_zone.led_count} ({range_desc})")

                if UIModel.is_zone_resizable(self.selected_zone.descriptor):
                    self.edit_zone_btn.configure(state="normal", text=f"Edit {self.selected_zone.name} LED Count...")
                else:
                    self.edit_zone_btn.configure(state="disabled", text=f"{self.selected_zone.name} (Non-resizable)")

                self._populate_led_listbox(count=self.selected_zone.led_count, prefix=f"{self.selected_zone.name} LED")
                self._update_scope_preview()
        else:
            dev_key = iid
            self.selected_device = next((d for d in self.tree_items if d.key == dev_key), None)
            self.selected_zone = None

            if self.selected_device:
                total_leds = sum(z.led_count for z in self.selected_device.zones)
                if total_leds == 0:
                    sup = getattr(self.controller, "openrgb_supervisor", self.controller)
                    raw_dev = sup._find_device(dev_key) if hasattr(sup, "_find_device") else None
                    total_leds = len(getattr(raw_dev, "leds", [])) if raw_dev else 0

                ambig_txt = " [Ambiguous Hardware]" if self.selected_device.is_ambiguous else ""
                self.sel_info_label.configure(text=f"{self.selected_device.display_label}{ambig_txt}")
                self.sel_subinfo_label.configure(text=f"Entire Device Scope ({total_leds} Total LEDs)")

                self.edit_zone_btn.configure(state="disabled", text="Edit Zone LED Count (Select Zone)")
                self._populate_led_listbox(count=total_leds, prefix="LED")
                self._update_scope_preview()
            self._update_effects_tab_for_selected_device()
            self._update_temperature_tab_owner_label()
        self._update_factory_reset_state()

    def _clear_selection(self):
        self.selected_device = None
        self.selected_zone = None
        self.selected_led_indices = []
        self.sel_info_label.configure(text="No OpenRGB devices detected.")
        self.sel_subinfo_label.configure(text="Check OpenRGB engine connection.")
        self.edit_zone_btn.configure(state="disabled", text="Edit Zone LED Count")
        self.led_listbox.delete(0, "end")
        self.scope_preview_label.configure(text="No target available.")
        self._update_factory_reset_state()

    def _populate_led_listbox(self, count: int, prefix: str = "LED"):
        self.led_listbox.delete(0, "end")
        self.selected_led_indices = []
        if count == 0:
            self.led_listbox.insert("end", "(No individual LEDs reported)")
            return
        for idx in range(count):
            self.led_listbox.insert("end", f"[{idx:02d}] {prefix} {idx + 1}")

    def _on_led_select(self, event):
        sel_indices = list(self.led_listbox.curselection())
        self.selected_led_indices = sel_indices
        self._update_scope_preview()

    def _select_all_leds(self):
        size = self.led_listbox.size()
        if size > 0 and self.led_listbox.get(0) != "(No individual LEDs reported)":
            self.led_listbox.select_set(0, "end")
            self.selected_led_indices = list(range(size))
        self._update_scope_preview()

    def _deselect_all_leds(self):
        self.led_listbox.selection_clear(0, "end")
        self.selected_led_indices = []
        self._update_scope_preview()

    def _update_scope_preview(self):
        if not self.selected_device:
            self.scope_preview_label.configure(text="Select a target device/zone")
            return

        dev_name = self.selected_device.display_label
        if self.selected_zone:
            z_name = self.selected_zone.name
            if self.selected_led_indices:
                indices_str = ", ".join(str(i) for i in self.selected_led_indices[:6])
                if len(self.selected_led_indices) > 6:
                    indices_str += f"... (+{len(self.selected_led_indices)-6} more)"
                txt = f"Target: {dev_name} > {z_name} > LEDs: [{indices_str}]"
            else:
                txt = f"Target: {dev_name} > {z_name} (All {self.selected_zone.led_count} LEDs)"
        else:
            if self.selected_led_indices:
                indices_str = ", ".join(str(i) for i in self.selected_led_indices[:6])
                if len(self.selected_led_indices) > 6:
                    indices_str += f"... (+{len(self.selected_led_indices)-6} more)"
                txt = f"Target: {dev_name} > LEDs: [{indices_str}]"
            else:
                total_leds = sum(z.led_count for z in self.selected_device.zones)
                txt = f"Target: {dev_name} (Entire Device, {total_leds} LEDs)"

        self.scope_preview_label.configure(text=txt)

    def _open_edit_zone_dialog(self):
        if not self.selected_device or not self.selected_zone:
            return
        sup = getattr(self.controller, "openrgb_supervisor", self.controller)
        EditZoneDialog(
            parent=self.root,
            supervisor=sup,
            controller=self.controller,
            config_manager=self.config_manager,
            device_item=self.selected_device,
            zone_item=self.selected_zone,
            on_success=self._on_zone_edit_success
        )

    def _on_zone_edit_success(self):
        saved_dev_key = self.selected_device.key if self.selected_device else None
        saved_zone_idx = self.selected_zone.index if self.selected_zone else None

        cfg = self.config_manager.get_config()
        sup = getattr(self.controller, "openrgb_supervisor", self.controller)
        descriptors = sup.get_descriptors() if hasattr(sup, "get_descriptors") else []
        self.temp_devices_config = merge_legacy_device_profiles(
            cfg.get("devices", {}),
            cfg.get("unmatched_legacy_profiles", {}),
            descriptors if descriptors else [getattr(d, "name", str(d)) for d in descriptors]
        )

        self._populate_device_tree()

        if saved_dev_key and saved_zone_idx is not None:
            zone_iid = f"zone:{saved_dev_key}:{saved_zone_idx}"
            if self.tree.exists(zone_iid):
                self.tree.selection_set(zone_iid)
                self._select_tree_target(zone_iid)

    def _apply_manual_color(self):
        if not self.selected_device:
            self.apply_result_label.configure(text="No device selected.", fg="#ef4444")
            return

        sup = getattr(self.controller, "openrgb_supervisor", self.controller)
        target_key = getattr(self.selected_device.descriptor, "stable_key", None) or self.selected_device.key
        raw_dev = sup._find_device(target_key) if hasattr(sup, "_find_device") else None

        # A manual per-LED write is only meaningful in a per-LED mode.  MSI
        # boards often remain in a hardware effect such as Rainbow wave; the
        # SDK accepts the packet but keeps returning the effect's old colors,
        # which used to surface as a misleading readback mismatch.  Negotiate
        # Direct first so Manual has a deterministic target mode.
        raw_modes = list(getattr(raw_dev, "modes", []) or []) if raw_dev is not None else []
        active_index = getattr(raw_dev, "active_mode", None) if raw_dev is not None else None
        active_mode = raw_modes[active_index] if isinstance(active_index, int) and 0 <= active_index < len(raw_modes) else None
        active_color_mode = getattr(active_mode, "color_mode", None)
        active_color_mode_name = str(getattr(active_color_mode, "name", active_color_mode)).upper()
        if raw_modes and active_mode is not None and active_color_mode not in (1, "1") and active_color_mode_name != "PER_LED":
            set_direct = getattr(sup, "set_device_mode", None)
            if not callable(set_direct) or not set_direct(target_key, "Direct"):
                message = "Current hardware effect does not accept per-LED colors; switching to Direct failed."
                self.apply_result_label.configure(text=message, fg="#ef4444")
                messagebox.showerror("Manual Color Unsupported", message, parent=self.root)
                return
            raw_dev = sup._find_device(target_key) if hasattr(sup, "_find_device") else raw_dev

        total_leds = 0
        if raw_dev and hasattr(raw_dev, "leds") and raw_dev.leds:
            total_leds = len(raw_dev.leds)
        elif raw_dev and hasattr(raw_dev, "colors") and raw_dev.colors:
            total_leds = len(raw_dev.colors)
        elif self.selected_device.zones:
            total_leds = sum(z.led_count for z in self.selected_device.zones)

        current_colors = getattr(raw_dev, "colors", None)
        target_indices = []

        if self.selected_zone:
            zone_offset = 0
            for z in self.selected_device.zones:
                if z.index == self.selected_zone.index:
                    break
                zone_offset += z.led_count

            if self.selected_led_indices:
                target_indices = [zone_offset + i for i in self.selected_led_indices if i < self.selected_zone.led_count]
            else:
                target_indices = list(range(zone_offset, zone_offset + self.selected_zone.led_count))
        else:
            if self.selected_led_indices:
                target_indices = [i for i in self.selected_led_indices if i < total_leds]
            else:
                target_indices = list(range(total_leds))

        rgb = self.color_state.get_rgb()

        try:
            from openrgb.utils import RGBColor
            color_obj = RGBColor(rgb[0], rgb[1], rgb[2])
        except ImportError:
            class DummyColor:
                def __init__(self, r, g, b):
                    self.red = int(r)
                    self.green = int(g)
                    self.blue = int(b)
                def pack(self):
                    import struct
                    return struct.pack("BBBx", self.red, self.green, self.blue)
            color_obj = DummyColor(rgb[0], rgb[1], rgb[2])

        payload = build_target_colors(
            total_leds=total_leds,
            current_colors=current_colors,
            selected_indices=target_indices,
            new_color=color_obj
        )

        if hasattr(self.controller, "set_device_owner"):
            self.controller.set_device_owner(target_key, "manual_direct")

        res = sup.set_colors(target_key, payload, fast=True)
        if res.ok:
            serial_colors = []
            for color in payload:
                if all(hasattr(color, channel) for channel in ("red", "green", "blue")):
                    serial_colors.append([int(color.red), int(color.green), int(color.blue)])
            remember = getattr(self.controller, "remember_last_applied", None)
            if callable(remember):
                remember("manual", target_key, colors=serial_colors)
            self.apply_result_label.configure(
                text=f"Applied {self.color_state.get_hex()} to {len(target_indices)} LED(s).",
                fg="#22c55e"
            )
            self._update_temperature_tab_owner_label()
        else:
            err_msg = f"Error [{res.error_code}]: {res.message}"
            self.apply_result_label.configure(text=err_msg, fg="#ef4444")
            messagebox.showerror("Color Write Failed", err_msg, parent=self.root)

    def _reset_or_resume_device(self):
        if not self.selected_device:
            return
        target_key = getattr(self.selected_device.descriptor, "stable_key", None) or self.selected_device.key
        is_reset = bool(getattr(self.controller, "is_device_reset", lambda _name: False)(target_key))
        action = "resume_device" if is_reset else "reset_device_to_original"
        handler = getattr(self.controller, action, None)
        if not callable(handler) or not handler(target_key):
            messagebox.showerror("Restore failed", "OpenRGB could not restore the pre-sync snapshot for this device.", parent=self.root)
            return
        remember = getattr(self.controller, "remember_last_applied", None)
        if callable(remember):
            remember("temperature" if is_reset else "vendor_default", target_key)
        if self.reset_device_btn is not None:
            self.reset_device_btn.configure(text="Resume Sync" if not is_reset else "Restore Pre-Sync Snapshot")
        self._update_temperature_tab_owner_label()
        self._update_factory_reset_state()

    def _rescan_inventory(self):
        sup = getattr(self.controller, "openrgb_supervisor", self.controller)
        if hasattr(sup, "refresh_inventory"):
            sup.refresh_inventory()
        self._populate_device_tree()
        snapshot = self.controller.get_status_snapshot()
        self.status_badge.configure(text=f"Engine: {snapshot.get('engine_label', 'Unknown')} | Status: {snapshot.get('status_text', 'Active')}")

    def show(self):
        """Marshal show window request onto Tk main thread."""
        self.root.after(0, self._show_impl)

    def _show_impl(self):
        cfg = self.config_manager.get_config()
        t = cfg["thermal"]
        self.min_temp_var.set(t["min_temp"])
        self.mid_temp_var.set(t["mid_temp"])
        self.max_temp_var.set(t["max_temp"])
        self.transition_speed_var.set(t["transition_speed"])
        self.stop_on_screensaver_var.set(cfg["behavior"]["stop_on_screensaver"])

        self.min_color_val = list(t["min_color"][:3])
        self.mid_color_val = list(t["mid_color"][:3])
        self.max_color_val = list(t["max_color"][:3])

        self.min_btn.configure(bg=self.rgb_to_hex(self.min_color_val))
        self.mid_btn.configure(bg=self.rgb_to_hex(self.mid_color_val))
        self.max_btn.configure(bg=self.rgb_to_hex(self.max_color_val))

        snapshot = self.controller.get_status_snapshot()
        self.status_badge.configure(text=f"Engine: {snapshot.get('engine_label', 'Active')} | Status: {snapshot.get('status_text', 'Connected')}")

        sup = getattr(self.controller, "openrgb_supervisor", self.controller)
        descriptors = sup.get_descriptors() if hasattr(sup, "get_descriptors") else []

        self.temp_devices_config = merge_legacy_device_profiles(
            cfg.get("devices", {}),
            cfg.get("unmatched_legacy_profiles", {}),
            descriptors if descriptors else [getattr(d, "name", str(d)) for d in descriptors]
        )

        self._populate_device_tree()
        self._sync_color_widgets_from_state()
        self._refresh_profile_list()

        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide(self):
        """Marshal hide window request onto Tk main thread."""
        self.root.after(0, self.root.withdraw)

    def save(self):
        min_t = self.min_temp_var.get()
        mid_t = self.mid_temp_var.get()
        max_t = self.max_temp_var.get()

        if not (min_t < mid_t < max_t):
            messagebox.showerror("Error", "Temperature thresholds must satisfy: Low < Mid < High", parent=self.root)
            return

        cfg = self.config_manager.get_config()
        cfg["thermal"]["min_temp"] = min_t
        cfg["thermal"]["mid_temp"] = mid_t
        cfg["thermal"]["max_temp"] = max_t
        cfg["thermal"]["min_color"] = self.min_color_val
        cfg["thermal"]["mid_color"] = self.mid_color_val
        cfg["thermal"]["max_color"] = self.max_color_val
        cfg["thermal"]["transition_speed"] = self.transition_speed_var.get()
        cfg["behavior"]["stop_on_screensaver"] = self.stop_on_screensaver_var.get()

        sup = getattr(self.controller, "openrgb_supervisor", self.controller)
        descriptors = sup.get_descriptors() if hasattr(sup, "get_descriptors") else []

        persisted_devs, remaining_unmatched = reconcile_device_profiles_on_save(
            self.temp_devices_config,
            cfg.get("unmatched_legacy_profiles", {}),
            descriptors=descriptors
        )
        cfg["devices"] = persisted_devs
        cfg["unmatched_legacy_profiles"] = remaining_unmatched

        try:
            self.config_manager.save_config(cfg)
        except Exception as ex:
            messagebox.showerror("Save Failed", f"Could not save configuration: {ex}", parent=self.root)
            return

        remember = getattr(self.controller, "remember_last_applied", None)
        if callable(remember):
            remember("temperature")

        if self.on_save_callback:
            self.on_save_callback()
        self.hide()

    def _export_diag(self):
        diag = self.controller.export_diagnostics()
        diag_str = json.dumps(diag, indent=2)
        top = tk.Toplevel(self.root)
        top.title("Diagnostics Export")
        top.geometry("450x350")
        txt = tk.Text(top, wrap="none", bg=self.card_bg, fg=self.fg_color)
        txt.insert("1.0", diag_str)
        txt.pack(fill="both", expand=True)

    def _retry_engine(self):
        self.controller.retry()
        self._rescan_inventory()


    def _update_effects_tab_for_selected_device(self):
        if not self.selected_device:
            self.effects_target_label.configure(text="No device selected.")
            self.effects_mode_combo.configure(state="disabled")
            self.effects_mode_combo["values"] = []
            self.effects_mode_var.set("")
            self.apply_effect_btn.configure(state="disabled")
            self.save_to_device_btn.configure(state="disabled")
            return

        self.effects_target_label.configure(text=f"Target: {self.selected_device.display_label}")
        modes = getattr(self.selected_device.descriptor, "modes", ()) or ()
        if modes:
            names = [m.name for m in modes]
            self.effects_mode_combo["values"] = names
            self.effects_mode_combo.configure(state="readonly")
            self.effects_mode_combo.current(0)
            self._on_effects_mode_changed()
        else:
            self.effects_mode_combo["values"] = []
            self.effects_mode_combo.configure(state="disabled")
            self.effects_mode_var.set("(No hardware modes advertised)")
            self.apply_effect_btn.configure(state="disabled")
            self.save_to_device_btn.configure(state="disabled")

    def _on_effects_mode_changed(self, event=None):
        if not self.selected_device:
            return
        mode_name = self.effects_mode_var.get()
        modes = getattr(self.selected_device.descriptor, "modes", ()) or ()
        mode = next((m for m in modes if m.name.lower() == mode_name.lower()), None)
        if not mode:
            return

        caps = UIModel.get_mode_capabilities(mode)

        # Speed
        if caps["supports_speed"]:
            s_min = caps["speed_range"][0] if caps["speed_range"][0] is not None else 0
            s_max = caps["speed_range"][1] if caps["speed_range"][1] is not None else 100
            self.effects_speed_scale.configure(state="normal", from_=s_min, to=s_max)
            cur_s = getattr(mode, "speed", None)
            if cur_s is not None:
                self.effects_speed_var.set(cur_s)
            self.effects_speed_reason.configure(text="")
        else:
            self.effects_speed_scale.configure(state="disabled")
            self.effects_speed_reason.configure(text="Speed unsupported")

        # Brightness
        if caps["supports_brightness"]:
            b_min = caps["brightness_range"][0] if caps["brightness_range"][0] is not None else 0
            b_max = caps["brightness_range"][1] if caps["brightness_range"][1] is not None else 100
            self.effects_bright_scale.configure(state="normal", from_=b_min, to=b_max)
            cur_b = getattr(mode, "brightness", None)
            if cur_b is not None:
                self.effects_bright_var.set(cur_b)
            self.effects_bright_reason.configure(text="")
        else:
            self.effects_bright_scale.configure(state="disabled")
            self.effects_bright_reason.configure(text="Brightness unsupported")

        # Direction
        if caps["supports_direction"] and caps["directions"]:
            self.effects_dir_combo.configure(state="readonly")
            self.effects_dir_combo["values"] = caps["directions"]
            self.effects_dir_combo.current(0)
            self.effects_dir_reason.configure(text="")
        else:
            self.effects_dir_combo["values"] = []
            self.effects_dir_combo.configure(state="disabled")
            self.effects_dir_reason.configure(text="Direction unsupported")

        # Color
        if getattr(mode, "supports_mode_specific_color", False):
            self.effects_color_btn.configure(state="normal")
            self.effects_color_reason.configure(text="")
        else:
            self.effects_color_btn.configure(state="disabled")
            self.effects_color_reason.configure(text="Fixed/random color mode")

        # Save to device
        if caps["supports_save"]:
            self.save_to_device_btn.configure(state="normal")
            self.effects_save_reason.configure(text="Mode supports flash save")
        else:
            self.save_to_device_btn.configure(state="disabled")
            self.effects_save_reason.configure(text="Save unsupported for mode")

        self.apply_effect_btn.configure(state="normal")

    def _pick_effect_color(self):
        initial_hex = rgb_to_hex(tuple(self.effects_color_val))
        _, hex_color = colorchooser.askcolor(parent=self.root, title="Select Mode Color", color=initial_hex)
        if hex_color:
            parsed = hex_to_rgb(hex_color)
            if parsed:
                self.effects_color_val = list(parsed)
                self.effects_color_btn.configure(bg=hex_color, activebackground=hex_color)

    def _apply_hardware_effect(self):
        if not self.selected_device:
            return
        target_key = self.selected_device.descriptor.stable_key or self.selected_device.key
        mode_name = self.effects_mode_var.get()
        modes = getattr(self.selected_device.descriptor, "modes", ()) or ()
        mode = next((m for m in modes if m.name.lower() == mode_name.lower()), None)
        if not mode:
            return

        speed = self.effects_speed_var.get() if mode.supports_speed else None
        brightness = self.effects_bright_var.get() if mode.supports_brightness else None
        direction = self.effects_dir_var.get() if mode.supports_direction else None

        colors = None
        if getattr(mode, "supports_mode_specific_color", False):
            try:
                from openrgb.utils import RGBColor
                colors = [RGBColor(self.effects_color_val[0], self.effects_color_val[1], self.effects_color_val[2])]
            except ImportError:
                class DummyRGB:
                    def __init__(self, r, g, b):
                        self.red, self.green, self.blue = r, g, b
                colors = [DummyRGB(self.effects_color_val[0], self.effects_color_val[1], self.effects_color_val[2])]

        handler = getattr(self.controller, "set_device_hardware_mode", None)
        if callable(handler):
            res = handler(
                target_key,
                mode_name,
                speed=speed,
                brightness=brightness,
                direction=direction,
                colors=colors,
                save=False
            )
        else:
            sup = getattr(self.controller, "openrgb_supervisor", self.controller)
            res = sup.set_mode(
                target_key,
                mode_name,
                speed=speed,
                brightness=brightness,
                direction=direction,
                colors=colors,
                save=False
            )

        if getattr(res, "ok", False):
            serial_colors = []
            for color in colors or []:
                if all(hasattr(color, channel) for channel in ("red", "green", "blue")):
                    serial_colors.append([int(color.red), int(color.green), int(color.blue)])
            remember = getattr(self.controller, "remember_last_applied", None)
            if callable(remember):
                remember(
                    "hardware_effect",
                    target_key,
                    mode_name=mode_name,
                    speed=speed,
                    brightness=brightness,
                    direction=direction,
                    colors=serial_colors,
                )
            self.effects_result_label.configure(
                text=f"Applied effect {mode_name} to {self.selected_device.name}.",
                fg="#22c55e"
            )
            self._update_temperature_tab_owner_label()
        else:
            err_code = getattr(res, "error_code", "error")
            err_msg = getattr(res, "message", "Unknown error")
            self.effects_result_label.configure(
                text=f"Failed [{err_code}]: {err_msg}",
                fg="#ef4444"
            )
            messagebox.showerror("Effect Apply Failed", f"[{err_code}]: {err_msg}", parent=self.root)

    def _save_effect_to_device(self):
        if not self.selected_device:
            return
        if not messagebox.askyesno(
            "Confirm Save to Device",
            "This will write the active lighting effect into device hardware flash/EEPROM.\n\nProceed?",
            parent=self.root
        ):
            return

        target_key = self.selected_device.descriptor.stable_key or self.selected_device.key
        sup = getattr(self.controller, "openrgb_supervisor", self.controller)
        save_fn = getattr(sup, "save_device_mode", None)
        if callable(save_fn):
            res = save_fn(target_key)
        else:
            res = None

        if getattr(res, "ok", False):
            self.effects_result_label.configure(
                text=f"Successfully saved effect to hardware flash on {self.selected_device.name}.",
                fg="#22c55e"
            )
            messagebox.showinfo("Saved to Device", "Mode successfully saved to device hardware memory.", parent=self.root)
        else:
            err_code = getattr(res, "error_code", "save_failed")
            err_msg = getattr(res, "message", "Hardware save failed")
            self.effects_result_label.configure(
                text=f"Hardware save failed [{err_code}]: {err_msg}",
                fg="#ef4444"
            )
            messagebox.showerror("Save Failed", f"[{err_code}]: {err_msg}", parent=self.root)

    
    def _update_factory_reset_state(self):
        if hasattr(self, "factory_reset_btn") and self.selected_device:
            target_key = getattr(self.selected_device.descriptor, "stable_key", None) or self.selected_device.key
            sup = getattr(self.controller, "openrgb_supervisor", None)
            if sup and hasattr(sup, "get_reset_capability"):
                cap = sup.get_reset_capability(target_key)
                if cap.status == "verified":
                    self.factory_reset_btn.config(state=tk.NORMAL)
                    if hasattr(self, "factory_reset_label"):
                        self.factory_reset_label.config(text=f"Available: {cap.reason}")
                else:
                    self.factory_reset_btn.config(state=tk.DISABLED)
                    if hasattr(self, "factory_reset_label"):
                        self.factory_reset_label.config(text=f"Unsupported: {cap.reason}")
            else:
                self.factory_reset_btn.config(state=tk.DISABLED)
                if hasattr(self, "factory_reset_label"):
                    self.factory_reset_label.config(text="Unsupported: Capability unknown")
        elif hasattr(self, "factory_reset_btn"):
            self.factory_reset_btn.config(state=tk.DISABLED)
            if hasattr(self, "factory_reset_label"):
                self.factory_reset_label.config(text="Select a device to see reset capability.")

    def _factory_reset_action(self):
        if not self.selected_device:
            return
        from tkinter import messagebox
        if not messagebox.askyesno("Restore Manufacturer Defaults", "This will permanently restore factory defaults if verified. Proceed?", parent=self.root):
            return
        
        target_key = getattr(self.selected_device.descriptor, "stable_key", None) or self.selected_device.key
        res = getattr(self.controller, "restore_manufacturer_defaults", lambda x: None)(target_key)
        if getattr(res, "ok", False):
            remember = getattr(self.controller, "remember_last_applied", None)
            if callable(remember):
                remember("vendor_default", target_key)
            messagebox.showinfo("Factory Reset", "Restored successfully.", parent=self.root)
        else:
            err = getattr(res, "message", "Unknown error")
            messagebox.showerror("Unsupported", f"Manufacturer reset rejected:\n{err}\n\nNote: Matching a color or OpenRGB reset-zone is not OEM reset.", parent=self.root)
        self._update_temperature_tab_owner_label()
        self._update_factory_reset_state()

    def _update_temperature_tab_owner_label(self):
        if hasattr(self, "device_owner_label") and self.selected_device:
            target_key = getattr(self.selected_device.descriptor, "stable_key", None) or self.selected_device.key
            owner = getattr(self.controller, "get_device_owner", lambda _: "thermal_direct")(target_key)
            label = UIModel.format_device_owner_label(owner)
            self.device_owner_label.configure(text=f"{self.selected_device.display_label} — Current: {label}")
            is_reset = getattr(self.controller, "is_device_reset", lambda _: False)(target_key)
            if hasattr(self, "reset_device_btn") and self.reset_device_btn is not None:
                self.reset_device_btn.configure(text="Resume Sync" if is_reset else "Restore Pre-Sync Snapshot")

    def _assign_device_to_thermal(self):
        if not self.selected_device:
            return
        target_key = getattr(self.selected_device.descriptor, "stable_key", None) or self.selected_device.key
        if hasattr(self.controller, "resume_device"):
            self.controller.resume_device(target_key)
        elif hasattr(self.controller, "set_device_owner"):
            self.controller.set_device_owner(target_key, "thermal_direct")
        remember = getattr(self.controller, "remember_last_applied", None)
        if callable(remember):
            remember("temperature", target_key)
        self._update_temperature_tab_owner_label()

    def _refresh_profile_list(self):
        if hasattr(self, "profile_combo") and hasattr(self.config_manager, "list_profiles"):
            profiles = self.config_manager.list_profiles()
            if "Default" not in profiles:
                profiles.insert(0, "Default")
            self.profile_combo["values"] = profiles
            cur = self.config_manager.get_config().get("active_profile", "Default")
            if cur in profiles:
                self.profile_var.set(cur)
            elif profiles:
                self.profile_var.set(profiles[0])

    def _save_profile_dialog(self):
        cur = self.profile_var.get() or "Profile_1"
        name = simpledialog.askstring("Save Profile", "Enter profile name:", initialvalue=cur, parent=self.root)
        if not name or not name.strip():
            return
        name = name.strip()
        if hasattr(self.config_manager, "save_profile"):
            if self.config_manager.save_profile(name, controller=self.controller):
                self._refresh_profile_list()
                self.profile_var.set(name)
                messagebox.showinfo("Profile Saved", f"Profile '{name}' saved successfully.", parent=self.root)
            else:
                messagebox.showerror("Error", f"Failed to save profile '{name}'.", parent=self.root)

    def _apply_profile_action(self):
        name = self.profile_var.get()
        if not name:
            return
        if hasattr(self.config_manager, "apply_profile"):
            if self.config_manager.apply_profile(name, controller=self.controller):
                self._show_impl()
                messagebox.showinfo("Profile Applied", f"Profile '{name}' applied successfully.", parent=self.root)
            else:
                messagebox.showerror("Error", f"Failed to apply profile '{name}'.", parent=self.root)

    def _delete_profile_action(self):
        name = self.profile_var.get()
        if not name or name == "Default":
            messagebox.showwarning("Warning", "Cannot delete default profile.", parent=self.root)
            return
        if messagebox.askyesno("Delete Profile", f"Delete profile '{name}'?", parent=self.root):
            if hasattr(self.config_manager, "delete_profile"):
                self.config_manager.delete_profile(name)
                self._refresh_profile_list()
