import os
import time
import customtkinter as ctk
from tkinter import messagebox, simpledialog
from config import config
from mouse import Mouse,connect_to_makcu, test_move
import main
from main import (
    start_aimbot, stop_aimbot, is_aimbot_running,
    reload_model, get_model_classes, get_model_size
)
import glob
from gui_sections import *
from aim_system.pid import PIDAimSection
from gui_callbacks import *
from gui_constants import NEON, BG, neon_button
from config_manager import ConfigManager
import numpy as np
import cv2

# Windows-specific imports for debug window always-on-top functionality
try:
    import win32gui
    import win32con
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False
    print("[INFO] win32gui not available - debug window always-on-top not supported")

ctk.set_appearance_mode("dark")


class EventuriGUI(ctk.CTk, GUISections, GUICallbacks):
    def __init__(self):
        super().__init__()
        self.title("EVENTURI-AI for MAKCU")
        
        # Get screen dimensions for responsive design
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        # Set initial size (90% of screen)
        initial_width = int(screen_width * 0.9)
        initial_height = int(screen_height * 0.9)
        
        # Center the window
        x = (screen_width - initial_width) // 2
        y = (screen_height - initial_height) // 2
        
        self.geometry(f"{initial_width}x{initial_height}+{x}+{y}")
        self.configure(bg=BG)
        self.resizable(True, True)  # Allow resizing
        self.minsize(900, 700)  # Set minimum size
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # Configure grid weights for responsiveness
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Initialize config manager
        self.config_manager = ConfigManager()

        # Internal state
        self._makcu_connected = False
        self._last_model = None
        self.error_text = ctk.StringVar(value="")
        self.aimbot_status = ctk.StringVar(value="Stopped")
        self.connection_status = ctk.StringVar(value="Disconnected")
        self.connection_color = ctk.StringVar(value="#b71c1c")
        self.model_name = ctk.StringVar(value=config.model_path)
        self.model_size = ctk.StringVar(value="")
        self.aim_humanize_var = ctk.BooleanVar(value=bool(config.aim_humanization))
        self.debug_checkbox_var = ctk.BooleanVar(value=False)
        self.input_check_var = ctk.BooleanVar(value=False)
        self.aim_button_mask_var = ctk.BooleanVar(value=bool(getattr(config, "aim_button_mask", False)))
        self.trigger_button_mask_var = ctk.BooleanVar(value=bool(getattr(config, "trigger_button_mask", False)))
        self._building = True
        self.fps_var = ctk.StringVar(value="FPS: 0")
        self._updating_conf = False
        self._updating_imgsz = False
        self.always_on_var = ctk.BooleanVar(value=bool(getattr(config, "always_on_aim", False)))
        self.trigger_enabled_var   = ctk.BooleanVar(value=bool(getattr(config, "trigger_enabled", False)))
        self.trigger_always_on_var = ctk.BooleanVar(value=bool(getattr(config, "trigger_always_on", False)))
        self.trigger_btn_var       = ctk.IntVar(value=int(getattr(config, "trigger_button", 0)))

        # Triggerbot Modes (Enhanced with CH341PAR improvements)
        self.trigger_mode_var = ctk.StringVar(value=getattr(config, "trigger_mode", "normal"))  # Firing modes: spray, burst, normal
        self.spray_initial_delay_ms_var = ctk.IntVar(value=int(getattr(config, "spray_initial_delay_ms", 50)))
        self.spray_cooldown_ms_var = ctk.IntVar(value=int(getattr(config, "spray_cooldown_ms", 80)))
        self.burst_shots_var = ctk.IntVar(value=int(getattr(config, "burst_shots", 3)))
        self.burst_delay_ms_var = ctk.IntVar(value=int(getattr(config, "burst_delay_ms", 40)))
        self.burst_cooldown_ms_var = ctk.IntVar(value=int(getattr(config, "burst_cooldown_ms", 200)))
        self.burst_hold_duration_ms_var = ctk.IntVar(value=int(getattr(config, "burst_hold_duration_ms", 500)))
        self.target_switch_delay_ms_var = ctk.IntVar(value=int(getattr(config, "target_switch_delay_ms", 100)))

        # RCS (Recoil Control System) variables
        self.rcs_enabled_var = ctk.BooleanVar(value=bool(getattr(config, "rcs_enabled", False)))
        self.rcs_ads_only_var = ctk.BooleanVar(value=bool(getattr(config, "rcs_ads_only", False)))
        self.rcs_y_random_enabled_var = ctk.BooleanVar(value=bool(getattr(config, "rcs_y_random_enabled", False)))
        self.current_config_name = ctk.StringVar(value="config_profile")
        
        # Always on top variable
        self.always_on_top_var = ctk.BooleanVar(value=bool(getattr(config, "always_on_top", False)))

        # Aiming axis toggles
        self.normal_enable_x_var = ctk.BooleanVar(value=bool(getattr(config, "normal_enable_x", True)))
        self.normal_enable_y_var = ctk.BooleanVar(value=bool(getattr(config, "normal_enable_y", True)))
        self.bezier_enable_x_var = ctk.BooleanVar(value=bool(getattr(config, "bezier_enable_x", True)))
        self.bezier_enable_y_var = ctk.BooleanVar(value=bool(getattr(config, "bezier_enable_y", True)))
        self.silent_enable_x_var = ctk.BooleanVar(value=bool(getattr(config, "silent_enable_x", True)))
        self.silent_enable_y_var = ctk.BooleanVar(value=bool(getattr(config, "silent_enable_y", True)))
        self.smooth_enable_x_var = ctk.BooleanVar(value=bool(getattr(config, "smooth_enable_x", True)))
        self.smooth_enable_y_var = ctk.BooleanVar(value=bool(getattr(config, "smooth_enable_y", True)))

        # Build UI and initialize
        self.build_responsive_ui()
        self._building = False
        self.refresh_all()
        self.poll_fps()

        # Auto-connect on startup and start polling status
        self.on_connect()
        self.after(500, self._poll_connection_status)
        
        # Initialize debounced save mechanism
        self._save_timer = None
        
        # Apply always on top setting if enabled
        if getattr(config, "always_on_top", False):
            try:
                self.attributes("-topmost", True)
                print("[INFO] Always on top enabled on startup")
            except Exception as e:
                print(f"[WARN] Failed to set always on top on startup: {e}")

        # Bind resize event
        self.bind("<Configure>", self.on_window_resize)

    def _schedule_config_save(self):
        """Debounced config save to prevent system freeze from excessive file I/O"""
        # Cancel any existing save timer
        if self._save_timer is not None:
            self.after_cancel(self._save_timer)
        
        # Schedule a new save after 500ms delay
        self._save_timer = self.after(500, self._perform_config_save)
    
    def _perform_config_save(self):
        """Actually perform the config save"""
        try:
            config.save()
            self._save_timer = None
            # Debug: Config saved (removed for cleaner output)
        except Exception as e:
            print(f"[ERROR] Failed to save config: {e}")
            self._save_timer = None

    def build_responsive_ui(self):
        """Build the responsive UI with proper scaling"""
        
        # Create main scrollable frame
        self.main_frame = ctk.CTkScrollableFrame(
            self, 
            fg_color=BG,
            scrollbar_button_color=NEON,
            scrollbar_button_hover_color="#d50000",
            scrollbar_fg_color="#1a1a1a"
        )
        self.main_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        # Configure main frame grid
        self.main_frame.grid_columnconfigure(0, weight=1)
        
        # --- STATUS BAR (Enhanced) ---
        self.build_status_bar()
        
        # Create two-column layout for larger screens
        self.content_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.content_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        self.content_frame.grid_columnconfigure(0, weight=1)
        self.content_frame.grid_columnconfigure(1, weight=1)
        
        # Left column
        self.left_column = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.left_column.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        self.left_column.grid_columnconfigure(0, weight=1)
        
        # Right column  
        self.right_column = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.right_column.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        self.right_column.grid_columnconfigure(0, weight=1)
        
        # Build sections in columns
        self.build_left_column()
        self.build_right_column()
        
        # Footer
        self.build_footer()

    def build_status_bar(self):
        """Enhanced status bar with better visual indicators"""
        status_frame = ctk.CTkFrame(self.main_frame, fg_color="#1a1a1a", height=80)
        status_frame.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        status_frame.grid_columnconfigure(1, weight=1)
        status_frame.grid_propagate(False)
        
        # --- Connection status with visual indicator (left) ---
        conn_frame = ctk.CTkFrame(status_frame, fg_color="transparent")
        conn_frame.grid(row=0, column=0, sticky="nsw", padx=10, pady=0)
        conn_frame.grid_rowconfigure(0, weight=1)
        
        # Connection indicator circle
        self.conn_indicator = ctk.CTkFrame(
            conn_frame, width=10, height=10, corner_radius=5, fg_color="#b71c1c"
        )
        self.conn_indicator.grid(row=0, column=0, padx=(0, 8))
        self.conn_indicator.grid_propagate(False)
        
        conn_text_frame = ctk.CTkFrame(conn_frame, fg_color="transparent")
        conn_text_frame.grid(row=0, column=1)
        ctk.CTkLabel(
            conn_text_frame, 
            text="MAKCU Device", 
            font=("Segoe UI", 12, "bold"),
            text_color="#ccc"
        ).grid(row=0, column=0, sticky="w")
        self.conn_status_lbl = ctk.CTkLabel(
            conn_text_frame,
            textvariable=self.connection_status,
            font=("Segoe UI", 14, "bold"),
            text_color=self.connection_color.get()
        )
        self.conn_status_lbl.grid(row=1, column=0, sticky="w", pady=(0, 27))
        
        # --- Info panel (center/right) ---
        info_frame = ctk.CTkFrame(status_frame, fg_color="#2a2a2a", corner_radius=10)
        info_frame.grid(row=0, column=1, sticky="ew", padx=15, pady=10)
        info_frame.grid_columnconfigure((0, 1, 2), weight=1)
        
        # --- Aimbot status ---
        aimbot_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
        aimbot_frame.grid(row=0, column=0, padx=10, pady=8, sticky="nsew")
        ctk.CTkLabel(aimbot_frame, text="Aimbot", font=("Segoe UI", 11), text_color="#ccc") \
            .grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(aimbot_frame, textvariable=self.aimbot_status, font=("Segoe UI", 13, "bold"), text_color=NEON) \
            .grid(row=1, column=0, sticky="w")
        
        # --- Model info ---
        model_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
        model_frame.grid(row=0, column=1, padx=10, pady=8, sticky="nsew")
        ctk.CTkLabel(model_frame, text="AI Model", font=("Segoe UI", 11), text_color="#ccc") \
            .grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(model_frame, textvariable=self.model_name, font=("Segoe UI", 12, "bold"), text_color="#00bcd4") \
            .grid(row=1, column=0, sticky="w")
        ctk.CTkLabel(model_frame, textvariable=self.model_size, font=("Segoe UI", 10), text_color="#888") \
            .grid(row=2, column=0, sticky="w")
        
        # --- FPS ---
        fps_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
        fps_frame.grid(row=0, column=2, padx=10, pady=8, sticky="nsew")
        ctk.CTkLabel(fps_frame, text="Performance", font=("Segoe UI", 11), text_color="#ccc") \
            .grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(fps_frame, textvariable=self.fps_var, font=("Segoe UI", 13, "bold"), text_color="#00e676") \
            .grid(row=1, column=0, sticky="w")
        
        # --- Error display (full width below status) ---
        self.error_frame = ctk.CTkFrame(status_frame, fg_color="transparent")
        self.error_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=15)
        self.error_lbl = ctk.CTkLabel(
            self.error_frame, 
            textvariable=self.error_text, 
            font=("Segoe UI", 11, "bold"),
            text_color=NEON,
            wraplength=800
        )
        self.error_lbl.grid(row=0, column=0, sticky="ew")
        self.error_frame.grid_columnconfigure(0, weight=1)

    def build_left_column(self):
        row = 0
        self.build_device_controls(self.left_column, row); row += 1
        # NEW:
        self.build_capture_controls(self.left_column, row); row += 1
        # Detection, Aim, Mode, Dynamic, etc. follow:
        self.build_detection_settings(self.left_column, row); row += 1
        self.build_aim_settings(self.left_column, row); row += 1
        self.build_rcs_settings(self.left_column, row); row += 1
        self.build_aimbot_mode(self.left_column, row); row += 1
        self.build_smoothing_controls(self.left_column, row); row += 1
        self.dynamic_frame = ctk.CTkFrame(self.left_column, fg_color=BG)
        self.dynamic_frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        self.dynamic_frame.grid_columnconfigure(0, weight=1)

    def build_right_column(self):
        """Build right column content"""
        row = 0
        
        # Model Settings
        self.build_model_settings(self.right_column, row)
        row += 1
        
        # Class Selection
        self.build_class_selection(self.right_column, row); row += 1

        # Triggerbot section here
        self.build_triggerbot_settings(self.right_column, row); row += 1
        self.build_triggerbot_mode(self.right_column, row); row += 1 # Firing modes: spray, burst, normal
        self.triggerbot_dynamic_frame = ctk.CTkFrame(self.right_column, fg_color=BG)
        self.triggerbot_dynamic_frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        self.triggerbot_dynamic_frame.grid_columnconfigure(0, weight=1)
        row += 1 # Increment row after placing dynamic frame

        # (Magnet Trigger removed)

        # Profile Controls
        self.build_profile_controls(self.right_column, row); row += 1
        
        # Main Controls
        self.build_main_controls(self.right_column, row)

    def build_magnet_trigger_settings(self, parent, row):
        pass
        # No separate per-mode controls; nothing else to render

    def _save_bool(self, key, val):
        setattr(config, key, bool(val))
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception:
            pass

    def _save_int(self, key, val):
        setattr(config, key, int(val))
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception:
            pass

    def _save_float(self, key, val):
        setattr(config, key, float(val))
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception:
            pass

    def build_device_controls(self, parent, row):
        """MAKCU device controls (top section)"""
        frame = ctk.CTkFrame(parent, fg_color="#1a1a1a")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text="🔌 Device Controls", font=("Segoe UI", 16, "bold"),
                    text_color="#00e676").grid(row=0, column=0, columnspan=3, pady=(15, 10), padx=15, sticky="w")

        self.connect_btn = neon_button(frame, text="Connect to MAKCU", command=self.on_connect, width=150, height=35)
        self.connect_btn.grid(row=1, column=0, padx=15, pady=(0, 15), sticky="w")

        ctk.CTkButton(frame, text="Test Move", command=test_move, width=100, height=35,
                    fg_color="#333", hover_color="#555").grid(row=1, column=1, padx=10, pady=(0, 15), sticky="w")
        
        self.input_check_checkbox = ctk.CTkCheckBox(
            frame, text="Input Monitor", variable=self.input_check_var,
            command=self.on_input_check_toggle, text_color="#fff"
        )
        self.input_check_checkbox.grid(row=1, column=2, padx=15, pady=(0, 15), sticky="w")

        self.button_mask_switch = ctk.CTkSwitch(
        frame,
        text="Aim Button Masking",
        variable=self.aim_button_mask_var,
        command=self.on_aim_button_mask_toggle,
        text_color="#fff"
    )
        self.button_mask_switch.grid(row=1, column=3, padx=15, pady=(0, 15), sticky="w")
        
        self.trigger_button_mask_switch = ctk.CTkSwitch(
            frame,
            text="Trigger Button Masking",
            variable=self.trigger_button_mask_var,
            command=self.on_trigger_button_mask_toggle,
            text_color="#fff"
        )
        self.trigger_button_mask_switch.grid(row=2, column=0, columnspan=2, padx=15, pady=(0, 15), sticky="w")
        
        # Always on top checkbox
        self.always_on_top_checkbox = ctk.CTkCheckBox(
            frame, 
            text="Always On Top", 
            variable=self.always_on_top_var,
            command=self.on_always_on_top_toggle, 
            text_color="#fff"
        )
        self.always_on_top_checkbox.grid(row=2, column=2, columnspan=2, padx=15, pady=(0, 15), sticky="w")

    def build_capture_controls(self, parent, row):
        """Capture controls (bottom section): capture method + NDI source + toggles"""
        frame = ctk.CTkFrame(parent, fg_color="#1a1a1a")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text="📷 Capture Controls", font=("Segoe UI", 16, "bold"),
                    text_color="#00e676").grid(row=0, column=0, columnspan=4, pady=(15, 10), padx=15, sticky="w")

        # Capture Method
        ctk.CTkLabel(frame, text="Capture Method:", font=("Segoe UI", 14), text_color="#ffffff")\
            .grid(row=1, column=0, sticky="w", padx=15)
        self.capture_mode_var = ctk.StringVar(value=config.capturer_mode.upper())
        self.capture_mode_menu = ctk.CTkOptionMenu(
            frame, values=["CaptureCard", "NDI", "DXGI", "UDP"], variable=self.capture_mode_var,
            command=self.on_capture_mode_change, width=110
        )
        self.capture_mode_menu.grid(row=1, column=1, sticky="w", padx=(5, 15), pady=10)

        # --- NDI-only block (shown only when capture mode = NDI) ---
        self.ndi_block = ctk.CTkFrame(frame, fg_color="transparent")
        # we'll grid/place this in _update_ndi_controls_state()
        # internal grid for the block
        self.ndi_block.grid_columnconfigure(1, weight=1)
        
        # --- UDP-only block (shown only when capture mode = UDP) ---
        self.udp_block = ctk.CTkFrame(frame, fg_color="transparent")
        # we'll grid/place this in _update_udp_controls_state()
        self.udp_block.grid_columnconfigure(1, weight=1)
        
        # UDP IP Address
        ctk.CTkLabel(self.udp_block, text="UDP IP:", font=("Segoe UI", 14), text_color="#ffffff")\
            .grid(row=0, column=0, sticky="w", padx=15)
        self.udp_ip_var = ctk.StringVar(value=getattr(config, "udp_ip", "192.168.0.01"))
        self.udp_ip_entry = ctk.CTkEntry(self.udp_block, textvariable=self.udp_ip_var, width=120)
        self.udp_ip_entry.grid(row=0, column=1, sticky="w", padx=(5, 15), pady=5)
        self.udp_ip_entry.bind("<Return>", self.on_udp_ip_change)
        self.udp_ip_entry.bind("<FocusOut>", self.on_udp_ip_change)
        
        # UDP Port
        ctk.CTkLabel(self.udp_block, text="UDP Port:", font=("Segoe UI", 14), text_color="#ffffff")\
            .grid(row=1, column=0, sticky="w", padx=15)
        self.udp_port_var = ctk.StringVar(value=str(getattr(config, "udp_port", 1234)))
        self.udp_port_entry = ctk.CTkEntry(self.udp_block, textvariable=self.udp_port_var, width=120)
        self.udp_port_entry.grid(row=1, column=1, sticky="w", padx=(5, 15), pady=5)
        self.udp_port_entry.bind("<Return>", self.on_udp_port_change)
        self.udp_port_entry.bind("<FocusOut>", self.on_udp_port_change)
        
        # UDP Status
        self.udp_status_label = ctk.CTkLabel(self.udp_block, text="Status: Not Connected", 
                                           font=("Segoe UI", 12), text_color="#ff6b6b")
        self.udp_status_label.grid(row=2, column=0, columnspan=2, sticky="w", padx=15, pady=5)

        # NDI Source dropdown (auto-refreshing)
        ctk.CTkLabel(self.ndi_block, text="NDI Source:", font=("Segoe UI", 14), text_color="#ffffff")\
            .grid(row=0, column=0, sticky="w", padx=15)
        self.ndi_source_var = ctk.StringVar(value=self._initial_ndi_source_value())
        self.ndi_source_menu = ctk.CTkOptionMenu(
            self.ndi_block,
            values=self._ndi_menu_values(),
            variable=self.ndi_source_var,
            command=self.on_ndi_source_change,
            width=260
        )
        self.ndi_source_menu.grid(row=0, column=1, sticky="w", padx=(5, 15), pady=(0, 8))

        # Main PC Resolution (width × height)
        ctk.CTkLabel(self.ndi_block, text="Main PC Resolution:", font=("Segoe UI", 14), text_color="#ffffff")\
            .grid(row=1, column=0, sticky="w", padx=15, pady=(0, 10))

        res_wrap = ctk.CTkFrame(self.ndi_block, fg_color="transparent")
        res_wrap.grid(row=1, column=1, sticky="w", padx=(5, 15), pady=(0, 10))

        self.main_res_w_entry = ctk.CTkEntry(res_wrap, width=90, justify="center")
        self.main_res_w_entry.pack(side="left")
        self.main_res_w_entry.insert(0, str(getattr(config, "main_pc_width", 1920)))

        ctk.CTkLabel(res_wrap, text=" × ", font=("Segoe UI", 14), text_color="#ffffff")\
            .pack(side="left", padx=6)

        self.main_res_h_entry = ctk.CTkEntry(res_wrap, width=90, justify="center")
        self.main_res_h_entry.pack(side="left")
        self.main_res_h_entry.insert(0, str(getattr(config, "main_pc_height", 1080)))

        def _commit_main_res(event=None):
            try:
                w = int(self.main_res_w_entry.get().strip())
                h = int(self.main_res_h_entry.get().strip())
                w = max(320, min(7680, w))
                h = max(240, min(4320, h))
                config.main_pc_width = w
                config.main_pc_height = h
                self.main_res_w_entry.delete(0, "end"); self.main_res_w_entry.insert(0, str(w))
                self.main_res_h_entry.delete(0, "end"); self.main_res_h_entry.insert(0, str(h))
                if hasattr(config, "save") and callable(config.save):
                    config.save()
            except Exception:
                self.main_res_w_entry.delete(0, "end"); self.main_res_w_entry.insert(0, str(getattr(config, "main_pc_width", 1920)))
                self.main_res_h_entry.delete(0, "end"); self.main_res_h_entry.insert(0, str(getattr(config, "main_pc_height", 1080)))

        self.main_res_w_entry.bind("<Return>", _commit_main_res)
        self.main_res_h_entry.bind("<Return>", _commit_main_res)
        self.main_res_w_entry.bind("<FocusOut>", _commit_main_res)
        self.main_res_h_entry.bind("<FocusOut>", _commit_main_res)

        # Toggles
        self.debug_checkbox = ctk.CTkCheckBox(
            frame, text="Debug Window", variable=self.debug_checkbox_var,
            command=self.on_debug_toggle, text_color="#fff"
        )
        self.debug_checkbox.grid(row=4, column=0, sticky="w", padx=15, pady=(5, 8))
        
        # Debug Text Info checkbox (only visible when debug window is enabled)
        self.debug_text_info_var = ctk.BooleanVar(value=config.show_debug_text_info)
        self.debug_text_info_checkbox = ctk.CTkCheckBox(
            frame, text="  ↳ Text Info", variable=self.debug_text_info_var,
            command=self.on_debug_text_info_toggle, text_color="#fff"
        )
        self.debug_text_info_checkbox.grid(row=5, column=0, sticky="w", padx=15, pady=(0, 8))
        
        # Debug Always on Top checkbox (only visible when debug window is enabled)
        self.debug_always_on_top_var = ctk.BooleanVar(value=getattr(config, "debug_always_on_top", False))
        self.debug_always_on_top_checkbox = ctk.CTkCheckBox(
            frame, text="  ↳ Always on Top", variable=self.debug_always_on_top_var,
            command=self.on_debug_always_on_top_toggle, text_color="#fff"
        )
        self.debug_always_on_top_checkbox.grid(row=6, column=0, sticky="w", padx=15, pady=(0, 15))

        # Initial enable/disable state
        self._update_ndi_controls_state()
        self._update_udp_controls_state()

        # Start polling for source list updates
        self.after(1000, self._poll_ndi_sources)

    def _ndi_menu_values(self):
        # Show something friendly when empty
        return config.ndi_sources if config.ndi_sources else ["(no NDI sources found)"]

    def _initial_ndi_source_value(self):
        # If we have a persisted selection and it still exists, use it; else first
        sel = config.ndi_selected_source
        if isinstance(sel, str) and sel in config.ndi_sources:
            return sel
        # fallbacks
        return config.ndi_sources[0] if config.ndi_sources else "(no NDI sources found)"

    def _update_ndi_controls_state(self):
        is_ndi = (self.capture_mode_var.get().upper() == "NDI")

        # Show/hide the whole NDI block
        try:
            if is_ndi:
                self.ndi_block.grid(row=2, column=0, columnspan=2, sticky="ew")
            else:
                self.ndi_block.grid_remove()
        except Exception:
            pass
    
    def _update_udp_controls_state(self):
        """Update UDP controls visibility"""
        is_udp = (self.capture_mode_var.get().upper() == "UDP")

        # Show/hide the whole UDP block
        try:
            if is_udp:
                self.udp_block.grid(row=3, column=0, columnspan=2, sticky="ew")
                # Update UDP status
                self._update_udp_status()
            else:
                self.udp_block.grid_remove()
        except Exception:
            pass
    
    def _update_udp_status(self):
        """Update UDP connection status"""
        try:
            # Check if UDP is connected (this would need to be implemented in capture.py)
            status_text = f"Status: {config.udp_ip}:{config.udp_port}"
            self.udp_status_label.configure(text=status_text, text_color="#4caf50")
        except Exception:
            self.udp_status_label.configure(text="Status: Not Connected", text_color="#ff6b6b")
    
    def on_udp_ip_change(self, event=None):
        """Handle UDP IP address change"""
        try:
            new_ip = self.udp_ip_var.get().strip()
            if new_ip and new_ip != config.udp_ip:
                config.udp_ip = new_ip
                self.error_text.set(f"🌐 UDP IP set to: {new_ip}")
                self._update_udp_status()
                # Restart aimbot if running to apply new settings
                if is_aimbot_running():
                    stop_aimbot()
                    start_aimbot()
                config.save()
        except Exception as e:
            self.error_text.set(f"❌ Invalid UDP IP: {e}")
    
    def on_udp_port_change(self, event=None):
        """Handle UDP port change"""
        try:
            new_port = int(self.udp_port_var.get().strip())
            if 1 <= new_port <= 65535 and new_port != config.udp_port:
                config.udp_port = new_port
                self.error_text.set(f"🔌 UDP Port set to: {new_port}")
                self._update_udp_status()
                # Restart aimbot if running to apply new settings
                if is_aimbot_running():
                    stop_aimbot()
                    start_aimbot()
                config.save()
        except ValueError:
            self.error_text.set("❌ Invalid UDP port - must be 1-65535")

        # Enable/disable internal controls just in case
        try:
            state = "normal" if is_ndi else "disabled"
            self.ndi_source_menu.configure(state=state)
            self.main_res_w_entry.configure(state=state)
            self.main_res_h_entry.configure(state=state)
        except Exception:
            pass

        try:
            self.debug_checkbox.grid_configure(row=4 if is_ndi else 2)
        except Exception:
            pass

    def _poll_ndi_sources(self):
        latest = list(config.ndi_sources) if isinstance(config.ndi_sources, list) else []

        # 1) Always push the latest values into the menu
        if not latest:
            latest = ["(Start Aimbot to find avalible NDI sources)"]

        try:
            self.ndi_source_menu.configure(values=latest)
        except Exception:
            # widget not ready yet, try again next tick
            self.after(1000, self._poll_ndi_sources)
            return

        # 2) Keep the selection sensible
        current = self.ndi_source_var.get()
        if current not in latest:
            if isinstance(config.ndi_selected_source, str) and config.ndi_selected_source in latest:
                choice = config.ndi_selected_source
            else:
                choice = latest[0]


            self.ndi_source_var.set(choice)
            try:
                self.ndi_source_menu.set(choice)
            except Exception:
                pass

            if self.capture_mode_var.get().upper() == "NDI" and not choice.startswith("("):
                config.ndi_selected_source = choice
                config.save()

        # 3) Reflect enable/disable based on mode
        self._update_ndi_controls_state()

        # tick again
        self.after(1000, self._poll_ndi_sources)
    
    
    def build_triggerbot_settings(self, parent, row):
        """Standalone Triggerbot section (right column)."""
        frame = ctk.CTkFrame(parent, fg_color="#1a1a1a")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text="🧨 Triggerbot", font=("Segoe UI", 16, "bold"),
                    text_color="#00e676").grid(row=0, column=0, columnspan=2,
                                                pady=(15, 10), padx=15, sticky="w")

        # --- toggles
        toggles = ctk.CTkFrame(frame, fg_color="transparent")
        toggles.grid(row=1, column=0, columnspan=2, sticky="ew", padx=15, pady=(0, 10))
        toggles.grid_columnconfigure(1, weight=1)

        def _on_enabled_then_focus():
            self.on_trigger_enabled_toggle()
            if self.trigger_enabled_var.get():
                try:
                    self.tb_radius_entry.focus_set()
                    self.tb_radius_entry.select_range(0, "end")
                except Exception:
                    pass

        ctk.CTkSwitch(toggles, text="Enabled", text_color="#fff",
                    variable=self.trigger_enabled_var,
                    command=_on_enabled_then_focus).pack(side="left", padx=(0, 15))

        ctk.CTkSwitch(toggles, text="Always on", text_color="#fff",
                    variable=self.trigger_always_on_var,
                    command=self.on_trigger_always_on_toggle).pack(side="left")

        # --- Detection Method Toggle ---
        detection_frame = ctk.CTkFrame(frame, fg_color="transparent")
        detection_frame.grid(row=1, column=2, sticky="ew", padx=15, pady=(0, 10))
        
        ctk.CTkLabel(detection_frame, text="Detection:", font=("Segoe UI", 12, "bold"), text_color="#fff").pack(side="left", padx=(0, 5))
        
        initial_detection_method = getattr(config, "trigger_detection_method", "ai").title()
        # Debug: Creating detection method dropdown (removed for cleaner output)
        
        self.trigger_detection_method_var = ctk.StringVar(value=initial_detection_method)
        self.trigger_detection_method_menu = ctk.CTkOptionMenu(
            detection_frame,
            values=["AI", "Color"],
            variable=self.trigger_detection_method_var,
            command=self.on_trigger_detection_method_change,
            font=("Segoe UI", 11),
            text_color="#fff",
            width=80
        )
        self.trigger_detection_method_menu.pack(side="left")
        
        # Debug: Detection method dropdown created (removed for cleaner output)
        

        # --- hotkey row
        ctk.CTkLabel(frame, text="Trigger Key:", font=("Segoe UI", 12, "bold"),
                    text_color="#fff").grid(row=2, column=0, sticky="w", padx=15, pady=(0, 8))
        btns = ctk.CTkFrame(frame, fg_color="transparent")
        btns.grid(row=2, column=1, sticky="w", padx=15, pady=(0, 8))
        for i, txt in enumerate(["Left", "Right", "Middle", "Side 4", "Side 5"]):
            ctk.CTkRadioButton(btns, text=txt, variable=self.trigger_btn_var, value=i,
                            command=self.update_trigger_button, text_color="#fff").pack(side="left", padx=8)

        # --- params
        params = ctk.CTkFrame(frame, fg_color="#2a2a2a", corner_radius=10)
        params.grid(row=3, column=0, columnspan=2, sticky="ew", padx=15, pady=(5, 15))
        params.grid_columnconfigure((1,3,5,7), weight=1)

        # validators
        v_int   = self.register(lambda s: (s == "") or s.isdigit())
        def _is_float(s):
            if s == "" or s == ".": return True
            try: float(s); return True
            except: return False
        v_float = self.register(_is_float)

        def _entry(parent, value, width=80, vcmd=None):
            e = ctk.CTkEntry(parent, width=width, justify="center",
                            font=("Segoe UI", 12, "bold"), text_color=NEON)
            e.insert(0, value)
            if vcmd is not None:
                # validate on keypress
                e.configure(validate="key", validatecommand=(vcmd, "%P"))
            return e

        ctk.CTkLabel(params, text="Radius(px)", font=("Segoe UI", 12, "bold"),
                    text_color="#fff").grid(row=0, column=0, padx=(10,6), pady=10, sticky="w")
        self.tb_radius_entry = _entry(params, str(getattr(config, "trigger_radius_px", 8)),
                                    vcmd=v_int);  self.tb_radius_entry.grid(row=0, column=1, sticky="w")

        ctk.CTkLabel(params, text="Delay(ms)", font=("Segoe UI", 12, "bold"),
                    text_color="#fff").grid(row=0, column=2, padx=(16,6), pady=10, sticky="w")
        self.tb_delay_entry  = _entry(params, str(getattr(config, "trigger_delay_ms", 30)),
                                    vcmd=v_int);  self.tb_delay_entry.grid(row=0, column=3, sticky="w")

        ctk.CTkLabel(params, text="Cooldown(ms)", font=("Segoe UI", 12, "bold"),
                    text_color="#fff").grid(row=0, column=4, padx=(16,6), pady=10, sticky="w")
        self.tb_cd_entry     = _entry(params, str(getattr(config, "trigger_cooldown_ms", 120)),
                                    vcmd=v_int); self.tb_cd_entry.grid(row=0, column=5, sticky="w")

        ctk.CTkLabel(params, text="Min conf", font=("Segoe UI", 12, "bold"),
                    text_color="#fff").grid(row=0, column=6, padx=(16,6), pady=10, sticky="w")
        self.tb_conf_entry   = _entry(params, f"{getattr(config, 'trigger_min_conf', 0.35):.2f}",
                                    vcmd=v_float); self.tb_conf_entry.grid(row=0, column=7, sticky="w")

        def _commit_tb_numbers(event=None):
            try:
                # ints
                r  = int(self.tb_radius_entry.get() or 0)
                d  = int(self.tb_delay_entry.get() or 0)
                cd = int(self.tb_cd_entry.get() or 0)
                # float
                cf = float(self.tb_conf_entry.get() or 0.0)

                # basic bounds
                r  = max(1, min(200, r))
                d  = max(0, min(1000, d))
                cd = max(0, min(2000, cd))
                cf = max(0.0, min(1.0, cf))

                config.trigger_radius_px   = r
                config.trigger_delay_ms    = d
                config.trigger_cooldown_ms = cd
                config.trigger_min_conf    = cf

                # normalize UI
                self.tb_radius_entry.delete(0, "end"); self.tb_radius_entry.insert(0, str(r))
                self.tb_delay_entry.delete(0, "end");  self.tb_delay_entry.insert(0, str(d))
                self.tb_cd_entry.delete(0, "end");     self.tb_cd_entry.insert(0, str(cd))
                self.tb_conf_entry.delete(0, "end");   self.tb_conf_entry.insert(0, f"{cf:.2f}")

                # Debounced save - prevent excessive file I/O that can freeze the system
                self._schedule_config_save()
            except Exception as e:
                print(f"[WARN] Bad triggerbot param: {e}")
                # revert to config
                self.tb_radius_entry.delete(0,"end"); self.tb_radius_entry.insert(0, str(getattr(config, "trigger_radius_px", 8)))
                self.tb_delay_entry.delete(0,"end");  self.tb_delay_entry.insert(0, str(getattr(config, "trigger_delay_ms", 30)))
                self.tb_cd_entry.delete(0,"end");     self.tb_cd_entry.insert(0, str(getattr(config, "trigger_cooldown_ms", 120)))
                self.tb_conf_entry.delete(0,"end");   self.tb_conf_entry.insert(0, f"{getattr(config, 'trigger_min_conf', 0.35):.2f}")

        for w in (self.tb_radius_entry, self.tb_delay_entry, self.tb_cd_entry, self.tb_conf_entry):
            w.bind("<Return>", _commit_tb_numbers)
            w.bind("<FocusOut>", _commit_tb_numbers)

        # --- Enhanced Color Detection HSV Settings ---
        self.color_frame = ctk.CTkFrame(frame, fg_color="#1e1e1e", corner_radius=15, border_width=2, border_color="#00e676")
        self.color_frame.grid(row=4, column=0, columnspan=2, sticky="ew", padx=15, pady=(10, 20))
        self.color_frame.grid_columnconfigure((1,3,5), weight=1)
        
        # Enhanced header with gradient-like effect
        header_frame = ctk.CTkFrame(self.color_frame, fg_color="#00e676", corner_radius=10)
        header_frame.grid(row=0, column=0, columnspan=6, sticky="ew", padx=10, pady=(15, 10))
        
        ctk.CTkLabel(header_frame, text="🌈 Color Detection Settings", 
                    font=("Segoe UI", 14, "bold"), text_color="#000").pack(pady=8)

        # HSV Section with better organization
        hsv_section = ctk.CTkFrame(self.color_frame, fg_color="#2d2d2d", corner_radius=8)
        hsv_section.grid(row=1, column=0, columnspan=6, sticky="ew", padx=10, pady=(0, 10))
        hsv_section.grid_columnconfigure((1,3,5), weight=1)
        
        ctk.CTkLabel(hsv_section, text="🎨 HSV Color Range", font=("Segoe UI", 12, "bold"),
                    text_color="#ff9800").grid(row=0, column=0, columnspan=6, padx=10, pady=(10, 5), sticky="w")

        # Color Preview Section
        preview_frame = ctk.CTkFrame(hsv_section, fg_color="#1a1a1a", corner_radius=8)
        preview_frame.grid(row=1, column=0, columnspan=6, sticky="ew", padx=10, pady=(5, 10))
        
        ctk.CTkLabel(preview_frame, text="🎨 Color Preview:", font=("Segoe UI", 11, "bold"),
                    text_color="#fff").pack(side="left", padx=(10, 5), pady=8)
        
        self.color_preview = ctk.CTkFrame(preview_frame, width=100, height=30, corner_radius=6,
                                         fg_color="#ff0000")  # Default red
        self.color_preview.pack(side="left", padx=(5, 10), pady=8)
        self.color_preview.pack_propagate(False)  # Keep fixed size

        # Enhanced HSV controls with sliders
        # Hue (Red theme)
        ctk.CTkLabel(hsv_section, text="🔴 Hue (0-179):", font=("Segoe UI", 11, "bold"), 
                    text_color="#f44336").grid(row=2, column=0, padx=(15,5), pady=(5,2), sticky="w")
        
        hue_frame = ctk.CTkFrame(hsv_section, fg_color="transparent")
        hue_frame.grid(row=3, column=0, columnspan=6, sticky="ew", padx=15, pady=(0,8))
        hue_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(hue_frame, text="Min:", text_color="#f44336", width=40).grid(row=0, column=0, sticky="w")
        self.hsv_h_min_slider = ctk.CTkSlider(hue_frame, from_=0, to=179, number_of_steps=179,
                                             command=self.update_hsv_preview, button_color="#f44336", progress_color="#f44336")
        self.hsv_h_min_slider.set(getattr(config, "trigger_hsv_h_min", 0))
        self.hsv_h_min_slider.grid(row=0, column=1, sticky="ew", padx=(5,10))
        self.hsv_h_min_value = ctk.CTkLabel(hue_frame, text="0", text_color="#f44336", width=30)
        self.hsv_h_min_value.grid(row=0, column=2)
        
        ctk.CTkLabel(hue_frame, text="Max:", text_color="#f44336", width=40).grid(row=1, column=0, sticky="w")
        self.hsv_h_max_slider = ctk.CTkSlider(hue_frame, from_=0, to=179, number_of_steps=179,
                                             command=self.update_hsv_preview, button_color="#f44336", progress_color="#f44336")
        self.hsv_h_max_slider.set(getattr(config, "trigger_hsv_h_max", 179))
        self.hsv_h_max_slider.grid(row=1, column=1, sticky="ew", padx=(5,10))
        self.hsv_h_max_value = ctk.CTkLabel(hue_frame, text="179", text_color="#f44336", width=30)
        self.hsv_h_max_value.grid(row=1, column=2)

        # Saturation (Green theme)
        ctk.CTkLabel(hsv_section, text="🟢 Saturation (0-255):", font=("Segoe UI", 11, "bold"), 
                    text_color="#4caf50").grid(row=4, column=0, padx=(15,5), pady=(5,2), sticky="w")
        
        sat_frame = ctk.CTkFrame(hsv_section, fg_color="transparent")
        sat_frame.grid(row=5, column=0, columnspan=6, sticky="ew", padx=15, pady=(0,8))
        sat_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(sat_frame, text="Min:", text_color="#4caf50", width=40).grid(row=0, column=0, sticky="w")
        self.hsv_s_min_slider = ctk.CTkSlider(sat_frame, from_=0, to=255, number_of_steps=255,
                                             command=self.update_hsv_preview, button_color="#4caf50", progress_color="#4caf50")
        self.hsv_s_min_slider.set(getattr(config, "trigger_hsv_s_min", 0))
        self.hsv_s_min_slider.grid(row=0, column=1, sticky="ew", padx=(5,10))
        self.hsv_s_min_value = ctk.CTkLabel(sat_frame, text="0", text_color="#4caf50", width=30)
        self.hsv_s_min_value.grid(row=0, column=2)
        
        ctk.CTkLabel(sat_frame, text="Max:", text_color="#4caf50", width=40).grid(row=1, column=0, sticky="w")
        self.hsv_s_max_slider = ctk.CTkSlider(sat_frame, from_=0, to=255, number_of_steps=255,
                                             command=self.update_hsv_preview, button_color="#4caf50", progress_color="#4caf50")
        self.hsv_s_max_slider.set(getattr(config, "trigger_hsv_s_max", 255))
        self.hsv_s_max_slider.grid(row=1, column=1, sticky="ew", padx=(5,10))
        self.hsv_s_max_value = ctk.CTkLabel(sat_frame, text="255", text_color="#4caf50", width=30)
        self.hsv_s_max_value.grid(row=1, column=2)

        # Value/Brightness (Blue theme)
        ctk.CTkLabel(hsv_section, text="🔵 Value/Brightness (0-255):", font=("Segoe UI", 11, "bold"), 
                    text_color="#2196f3").grid(row=6, column=0, padx=(15,5), pady=(5,2), sticky="w")
        
        val_frame = ctk.CTkFrame(hsv_section, fg_color="transparent")
        val_frame.grid(row=7, column=0, columnspan=6, sticky="ew", padx=15, pady=(0,15))
        val_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(val_frame, text="Min:", text_color="#2196f3", width=40).grid(row=0, column=0, sticky="w")
        self.hsv_v_min_slider = ctk.CTkSlider(val_frame, from_=0, to=255, number_of_steps=255,
                                             command=self.update_hsv_preview, button_color="#2196f3", progress_color="#2196f3")
        self.hsv_v_min_slider.set(getattr(config, "trigger_hsv_v_min", 0))
        self.hsv_v_min_slider.grid(row=0, column=1, sticky="ew", padx=(5,10))
        self.hsv_v_min_value = ctk.CTkLabel(val_frame, text="0", text_color="#2196f3", width=30)
        self.hsv_v_min_value.grid(row=0, column=2)
        
        ctk.CTkLabel(val_frame, text="Max:", text_color="#2196f3", width=40).grid(row=1, column=0, sticky="w")
        self.hsv_v_max_slider = ctk.CTkSlider(val_frame, from_=0, to=255, number_of_steps=255,
                                             command=self.update_hsv_preview, button_color="#2196f3", progress_color="#2196f3")
        self.hsv_v_max_slider.set(getattr(config, "trigger_hsv_v_max", 255))
        self.hsv_v_max_slider.grid(row=1, column=1, sticky="ew", padx=(5,10))
        self.hsv_v_max_value = ctk.CTkLabel(val_frame, text="255", text_color="#2196f3", width=30)
        self.hsv_v_max_value.grid(row=1, column=2)

        # Timing & Detection Section
        timing_section = ctk.CTkFrame(self.color_frame, fg_color="#2d2d2d", corner_radius=8)
        timing_section.grid(row=2, column=0, columnspan=6, sticky="ew", padx=10, pady=(0, 15))
        timing_section.grid_columnconfigure((1,3,5), weight=1)
        
        ctk.CTkLabel(timing_section, text="⚡ Detection & Timing", font=("Segoe UI", 12, "bold"),
                    text_color="#ff9800").grid(row=0, column=0, columnspan=6, padx=10, pady=(10, 5), sticky="w")

        # Enhanced timing controls with sliders
        timing_controls = ctk.CTkFrame(timing_section, fg_color="transparent")
        timing_controls.grid(row=1, column=0, columnspan=6, sticky="ew", padx=15, pady=(5,15))
        timing_controls.grid_columnconfigure((1,3,5), weight=1)
        
        # Radius slider
        ctk.CTkLabel(timing_controls, text="🎯 Radius:", font=("Segoe UI", 11, "bold"), 
                    text_color="#9c27b0").grid(row=0, column=0, padx=(0,5), pady=5, sticky="w")
        self.color_radius_slider = ctk.CTkSlider(timing_controls, from_=1, to=100, number_of_steps=99,
                                               command=self.update_color_radius, button_color="#9c27b0", progress_color="#9c27b0")
        self.color_radius_slider.set(getattr(config, "trigger_color_radius_px", 20))
        self.color_radius_slider.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        self.color_radius_value = ctk.CTkLabel(timing_controls, text="20", text_color="#9c27b0", width=30)
        self.color_radius_value.grid(row=0, column=2, padx=5, pady=5)
        
        # Delay slider
        ctk.CTkLabel(timing_controls, text="⏱️ Delay:", font=("Segoe UI", 11, "bold"), 
                    text_color="#ff5722").grid(row=0, column=3, padx=(15,5), pady=5, sticky="w")
        self.color_delay_slider = ctk.CTkSlider(timing_controls, from_=0, to=500, number_of_steps=100,
                                              command=self.update_color_delay, button_color="#ff5722", progress_color="#ff5722")
        self.color_delay_slider.set(getattr(config, "trigger_color_delay_ms", 50))
        self.color_delay_slider.grid(row=0, column=4, sticky="ew", padx=5, pady=5)
        self.color_delay_value = ctk.CTkLabel(timing_controls, text="50", text_color="#ff5722", width=30)
        self.color_delay_value.grid(row=0, column=5, padx=5, pady=5)
        
        # Cooldown slider
        ctk.CTkLabel(timing_controls, text="❄️ Cooldown:", font=("Segoe UI", 11, "bold"), 
                    text_color="#03a9f4").grid(row=1, column=0, padx=(0,5), pady=5, sticky="w")
        self.color_cooldown_slider = ctk.CTkSlider(timing_controls, from_=0, to=1000, number_of_steps=100,
                                                 command=self.update_color_cooldown, button_color="#03a9f4", progress_color="#03a9f4")
        self.color_cooldown_slider.set(getattr(config, "trigger_color_cooldown_ms", 200))
        self.color_cooldown_slider.grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        self.color_cooldown_value = ctk.CTkLabel(timing_controls, text="200", text_color="#03a9f4", width=30)
        self.color_cooldown_value.grid(row=1, column=2, padx=5, pady=5)

        # Add helpful tooltips/info
        info_frame = ctk.CTkFrame(self.color_frame, fg_color="#1a1a1a", corner_radius=6)
        info_frame.grid(row=3, column=0, columnspan=6, sticky="ew", padx=10, pady=(0, 15))
        
        info_text = "💡 Tip: Adjust HSV values to target specific colors. H=Hue (0-179), S=Saturation (0-255), V=Value/Brightness (0-255)"
        ctk.CTkLabel(info_frame, text=info_text, font=("Segoe UI", 10), 
                    text_color="#ffc107", wraplength=600).pack(padx=10, pady=8)
        
        # Set initial visibility based on current detection method
        initial_method = getattr(config, "trigger_detection_method", "ai").lower()
        # Debug: Color frame created (removed for cleaner output)
        
        if initial_method != "color":
            self.color_frame.grid_remove()  # Hide initially if not color
            # Debug: Color frame hidden (removed for cleaner output)
        else:
            # Debug: Color frame visible (removed for cleaner output)
            pass
        
        # Schedule visibility update after GUI is fully built
        self.after(200, self._update_color_frame_visibility)
        
        # Add debug check after 1 second
        # Debug: Color frame existence check (removed for cleaner output)

        # Initialize color preview with current HSV values
        self.after(100, self.update_hsv_preview)

        self._update_trigger_widgets_state()

    def build_gan_smoothing_section(self, parent, row):
        """Advanced Human-like Movement & Smoothing (Based on GAN-Aimbot Research)"""
        frame = ctk.CTkFrame(parent, fg_color="#0d1117", corner_radius=15, border_width=2, border_color="#ff6b35")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 15))
        frame.grid_columnconfigure(0, weight=1)
        
        # Research-inspired header
        header_frame = ctk.CTkFrame(frame, fg_color="#ff6b35", corner_radius=10)
        header_frame.grid(row=0, column=0, sticky="ew", padx=15, pady=(15, 10))
        
        ctk.CTkLabel(header_frame, text="🧠 GAN-Aimbot Research: Human-like Movement", 
                    font=("Segoe UI", 14, "bold"), text_color="#000").pack(pady=8)
        
        # Enable/Disable toggle
        control_frame = ctk.CTkFrame(frame, fg_color="transparent")
        control_frame.grid(row=1, column=0, sticky="ew", padx=15, pady=(0, 10))
        
        self.gan_smoothing_enabled_var = ctk.BooleanVar(value=getattr(config, "gan_smoothing_enabled", False))
        ctk.CTkSwitch(control_frame, text="Enable GAN-based Human-like Movement", 
                     text_color="#fff", font=("Segoe UI", 12, "bold"),
                     variable=self.gan_smoothing_enabled_var,
                     command=self.on_gan_smoothing_toggle).pack(side="left", padx=10, pady=5)
        
        # Human Behavior Simulation Section
        behavior_section = ctk.CTkFrame(frame, fg_color="#1c2128", corner_radius=10)
        behavior_section.grid(row=2, column=0, sticky="ew", padx=15, pady=(0, 10))
        behavior_section.grid_columnconfigure((1,3), weight=1)
        
        ctk.CTkLabel(behavior_section, text="🎯 Human Behavior Simulation", font=("Segoe UI", 12, "bold"),
                    text_color="#58a6ff").grid(row=0, column=0, columnspan=4, padx=10, pady=(10, 5), sticky="w")
        
        # Movement Variability (Research: GANs add realistic noise)
        ctk.CTkLabel(behavior_section, text="🌊 Movement Variability:", font=("Segoe UI", 11, "bold"), 
                    text_color="#f85149").grid(row=1, column=0, padx=(15,5), pady=5, sticky="w")
        self.movement_variability_slider = ctk.CTkSlider(behavior_section, from_=0.0, to=2.0, number_of_steps=200,
                                                        command=self.update_movement_variability, button_color="#f85149", progress_color="#f85149")
        self.movement_variability_slider.set(getattr(config, "movement_variability", 0.3))
        self.movement_variability_slider.grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        self.movement_variability_value = ctk.CTkLabel(behavior_section, text="0.30", text_color="#f85149", width=40)
        self.movement_variability_value.grid(row=1, column=2, padx=5, pady=5)
        
        # Human Reaction Delay (Research: Humans have natural delays)
        ctk.CTkLabel(behavior_section, text="⏱️ Reaction Delay (ms):", font=("Segoe UI", 11, "bold"), 
                    text_color="#a5a5a5").grid(row=2, column=0, padx=(15,5), pady=5, sticky="w")
        self.reaction_delay_slider = ctk.CTkSlider(behavior_section, from_=0, to=200, number_of_steps=200,
                                                  command=self.update_reaction_delay, button_color="#a5a5a5", progress_color="#a5a5a5")
        self.reaction_delay_slider.set(getattr(config, "human_reaction_delay_ms", 50))
        self.reaction_delay_slider.grid(row=2, column=1, sticky="ew", padx=5, pady=5)
        self.reaction_delay_value = ctk.CTkLabel(behavior_section, text="50", text_color="#a5a5a5", width=40)
        self.reaction_delay_value.grid(row=2, column=2, padx=5, pady=5)
        
        # Overshoot Probability (Research: Humans overshoot and correct)
        ctk.CTkLabel(behavior_section, text="🎯 Overshoot Chance (%):", font=("Segoe UI", 11, "bold"), 
                    text_color="#7ee787").grid(row=3, column=0, padx=(15,5), pady=5, sticky="w")
        self.overshoot_chance_slider = ctk.CTkSlider(behavior_section, from_=0, to=50, number_of_steps=50,
                                                    command=self.update_overshoot_chance, button_color="#7ee787", progress_color="#7ee787")
        self.overshoot_chance_slider.set(getattr(config, "overshoot_chance_percent", 15))
        self.overshoot_chance_slider.grid(row=3, column=1, sticky="ew", padx=5, pady=5)
        self.overshoot_chance_value = ctk.CTkLabel(behavior_section, text="15", text_color="#7ee787", width=40)
        self.overshoot_chance_value.grid(row=3, column=2, padx=5, pady=5)
        
        # Micro-corrections (Research: Humans make small adjustments)
        ctk.CTkLabel(behavior_section, text="🔧 Micro-corrections:", font=("Segoe UI", 11, "bold"), 
                    text_color="#ffa657").grid(row=4, column=0, padx=(15,5), pady=(5,15), sticky="w")
        self.micro_corrections_slider = ctk.CTkSlider(behavior_section, from_=0.0, to=1.0, number_of_steps=100,
                                                     command=self.update_micro_corrections, button_color="#ffa657", progress_color="#ffa657")
        self.micro_corrections_slider.set(getattr(config, "micro_corrections_intensity", 0.4))
        self.micro_corrections_slider.grid(row=4, column=1, sticky="ew", padx=5, pady=(5,15))
        self.micro_corrections_value = ctk.CTkLabel(behavior_section, text="0.40", text_color="#ffa657", width=40)
        self.micro_corrections_value.grid(row=4, column=2, padx=5, pady=(5,15))
        
        # Advanced Movement Patterns Section
        patterns_section = ctk.CTkFrame(frame, fg_color="#1c2128", corner_radius=10)
        patterns_section.grid(row=3, column=0, sticky="ew", padx=15, pady=(0, 10))
        patterns_section.grid_columnconfigure((1,3), weight=1)
        
        ctk.CTkLabel(patterns_section, text="🌀 Advanced Movement Patterns", font=("Segoe UI", 12, "bold"),
                    text_color="#58a6ff").grid(row=0, column=0, columnspan=4, padx=10, pady=(10, 5), sticky="w")
        
        # Trajectory Smoothness (Research: Human movement has natural curves)
        ctk.CTkLabel(patterns_section, text="📈 Trajectory Smoothness:", font=("Segoe UI", 11, "bold"), 
                    text_color="#d2a8ff").grid(row=1, column=0, padx=(15,5), pady=5, sticky="w")
        self.trajectory_smoothness_slider = ctk.CTkSlider(patterns_section, from_=0.1, to=2.0, number_of_steps=190,
                                                         command=self.update_trajectory_smoothness, button_color="#d2a8ff", progress_color="#d2a8ff")
        self.trajectory_smoothness_slider.set(getattr(config, "trajectory_smoothness", 0.8))
        self.trajectory_smoothness_slider.grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        self.trajectory_smoothness_value = ctk.CTkLabel(patterns_section, text="0.80", text_color="#d2a8ff", width=40)
        self.trajectory_smoothness_value.grid(row=1, column=2, padx=5, pady=5)
        
        # Fatigue Simulation (Research: Human performance degrades over time)
        ctk.CTkLabel(patterns_section, text="😴 Fatigue Simulation:", font=("Segoe UI", 11, "bold"), 
                    text_color="#f78166").grid(row=2, column=0, padx=(15,5), pady=5, sticky="w")
        self.fatigue_simulation_slider = ctk.CTkSlider(patterns_section, from_=0.0, to=1.0, number_of_steps=100,
                                                      command=self.update_fatigue_simulation, button_color="#f78166", progress_color="#f78166")
        self.fatigue_simulation_slider.set(getattr(config, "fatigue_simulation", 0.2))
        self.fatigue_simulation_slider.grid(row=2, column=1, sticky="ew", padx=5, pady=5)
        self.fatigue_simulation_value = ctk.CTkLabel(patterns_section, text="0.20", text_color="#f78166", width=40)
        self.fatigue_simulation_value.grid(row=2, column=2, padx=5, pady=5)
        
        # Context Awareness (Research: Movement depends on previous actions)
        ctk.CTkLabel(patterns_section, text="🧠 Context Memory (frames):", font=("Segoe UI", 11, "bold"), 
                    text_color="#79c0ff").grid(row=3, column=0, padx=(15,5), pady=(5,15), sticky="w")
        self.context_memory_slider = ctk.CTkSlider(patterns_section, from_=5, to=50, number_of_steps=45,
                                                  command=self.update_context_memory, button_color="#79c0ff", progress_color="#79c0ff")
        self.context_memory_slider.set(getattr(config, "context_memory_frames", 20))
        self.context_memory_slider.grid(row=3, column=1, sticky="ew", padx=5, pady=(5,15))
        self.context_memory_value = ctk.CTkLabel(patterns_section, text="20", text_color="#79c0ff", width=40)
        self.context_memory_value.grid(row=3, column=2, padx=5, pady=(5,15))
        
        # Anti-Detection Features Section
        anti_detect_section = ctk.CTkFrame(frame, fg_color="#1c2128", corner_radius=10)
        anti_detect_section.grid(row=4, column=0, sticky="ew", padx=15, pady=(0, 15))
        anti_detect_section.grid_columnconfigure((1,3), weight=1)
        
        ctk.CTkLabel(anti_detect_section, text="🛡️ Anti-Detection Features", font=("Segoe UI", 12, "bold"),
                    text_color="#58a6ff").grid(row=0, column=0, columnspan=4, padx=10, pady=(10, 5), sticky="w")
        
        # Performance Variation (Research: Humans don't perform consistently)
        ctk.CTkLabel(anti_detect_section, text="📊 Performance Variation:", font=("Segoe UI", 11, "bold"), 
                    text_color="#ff7b72").grid(row=1, column=0, padx=(15,5), pady=5, sticky="w")
        self.performance_variation_slider = ctk.CTkSlider(anti_detect_section, from_=0.0, to=0.5, number_of_steps=50,
                                                         command=self.update_performance_variation, button_color="#ff7b72", progress_color="#ff7b72")
        self.performance_variation_slider.set(getattr(config, "performance_variation", 0.15))
        self.performance_variation_slider.grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        self.performance_variation_value = ctk.CTkLabel(anti_detect_section, text="0.15", text_color="#ff7b72", width=40)
        self.performance_variation_value.grid(row=1, column=2, padx=5, pady=5)
        
        # Miss Intentionally (Research: Humans occasionally miss on purpose)
        ctk.CTkLabel(anti_detect_section, text="🎯 Intentional Miss Rate (%):", font=("Segoe UI", 11, "bold"), 
                    text_color="#f0883e").grid(row=2, column=0, padx=(15,5), pady=5, sticky="w")
        self.intentional_miss_slider = ctk.CTkSlider(anti_detect_section, from_=0, to=20, number_of_steps=20,
                                                    command=self.update_intentional_miss, button_color="#f0883e", progress_color="#f0883e")
        self.intentional_miss_slider.set(getattr(config, "intentional_miss_percent", 5))
        self.intentional_miss_slider.grid(row=2, column=1, sticky="ew", padx=5, pady=5)
        self.intentional_miss_value = ctk.CTkLabel(anti_detect_section, text="5", text_color="#f0883e", width=40)
        self.intentional_miss_value.grid(row=2, column=2, padx=5, pady=5)
        
        # Axis Correlation (Research: Humans move X and Y axes differently)
        ctk.CTkLabel(anti_detect_section, text="🔄 Axis Independence:", font=("Segoe UI", 11, "bold"), 
                    text_color="#56d364").grid(row=3, column=0, padx=(15,5), pady=(5,15), sticky="w")
        self.axis_independence_slider = ctk.CTkSlider(anti_detect_section, from_=0.0, to=1.0, number_of_steps=100,
                                                     command=self.update_axis_independence, button_color="#56d364", progress_color="#56d364")
        self.axis_independence_slider.set(getattr(config, "axis_independence", 0.7))
        self.axis_independence_slider.grid(row=3, column=1, sticky="ew", padx=5, pady=(5,15))
        self.axis_independence_value = ctk.CTkLabel(anti_detect_section, text="0.70", text_color="#56d364", width=40)
        self.axis_independence_value.grid(row=3, column=2, padx=5, pady=(5,15))
        
        # Research Information Panel
        research_info = ctk.CTkFrame(frame, fg_color="#0d1117", corner_radius=8, border_width=1, border_color="#30363d")
        research_info.grid(row=5, column=0, sticky="ew", padx=15, pady=(0, 15))
        
        research_text = ("📚 Based on 'GAN-Aimbots: Using Machine Learning for Cheating in First Person Shooters' (IEEE 2022)\n"
                        "🔬 This system mimics human mouse movement patterns to remain undetectable by anti-cheat systems\n"
                        "🎯 Features: Gaussian noise injection, trajectory smoothing, intentional overshooting, fatigue simulation")
        
        ctk.CTkLabel(research_info, text=research_text, font=("Segoe UI", 10), 
                    text_color="#8b949e", wraplength=700, justify="left").pack(padx=15, pady=10)

    def build_triggerbot_mode(self, parent, row):
        """Triggerbot firing mode selection (Spray, Burst, Normal)"""
        frame = ctk.CTkFrame(parent, fg_color="#1a1a1a")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        
        ctk.CTkLabel(frame, text="⚙️ Trigger Mode", font=("Segoe UI", 16, "bold"), text_color="#00e676").grid(row=0, column=0, pady=(15, 10), padx=15, sticky="w")
        
        mode_frame = ctk.CTkFrame(frame, fg_color="transparent")
        mode_frame.grid(row=1, column=0, padx=15, pady=(0, 15))
        
        # Original firing modes
        for name in ["spray", "burst", "normal"]:
            ctk.CTkRadioButton(
                mode_frame, 
                text=name.title(), 
                variable=self.trigger_mode_var, 
                value=name, 
                command=self.update_trigger_mode, 
                text_color="#fff",
                font=("Segoe UI", 12, "bold")
            ).pack(side="left", padx=15)


    def add_spray_mode_settings(self):
        f = ctk.CTkFrame(self.triggerbot_dynamic_frame, fg_color="#1a1a1a")
        f.pack(fill="x", pady=5)
        f.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(f, text="💨 Spray Mode Settings", font=("Segoe UI", 14, "bold"), text_color="#00e676").grid(row=0, column=0, columnspan=2, pady=(10, 5), padx=10, sticky="w")

        ctk.CTkLabel(f, text="Initial Delay (ms):", text_color="#fff").grid(row=1, column=0, sticky="w", padx=10, pady=2)
        initial_delay_slider = ctk.CTkSlider(f, from_=0, to=500, number_of_steps=100, command=self.update_spray_initial_delay)
        initial_delay_slider.set(config.spray_initial_delay_ms)
        initial_delay_slider.grid(row=1, column=1, sticky="ew", padx=(5, 5), pady=2)
        self.spray_initial_delay_label = ctk.CTkLabel(f, text=str(config.spray_initial_delay_ms), text_color=NEON, width=50)
        self.spray_initial_delay_label.grid(row=1, column=2, padx=10, pady=2)

        ctk.CTkLabel(f, text="Cooldown (ms):", text_color="#fff").grid(row=2, column=0, sticky="w", padx=10, pady=(2, 10))
        cooldown_slider = ctk.CTkSlider(f, from_=0, to=500, number_of_steps=100, command=self.update_spray_cooldown)
        cooldown_slider.set(config.spray_cooldown_ms)
        cooldown_slider.grid(row=2, column=1, sticky="ew", padx=(5, 5), pady=(2, 10))
        self.spray_cooldown_label = ctk.CTkLabel(f, text=str(config.spray_cooldown_ms), text_color=NEON, width=50)
        self.spray_cooldown_label.grid(row=2, column=2, padx=10, pady=(2, 10))

    def add_burst_mode_settings(self):
        f = ctk.CTkFrame(self.triggerbot_dynamic_frame, fg_color="#1a1a1a")
        f.pack(fill="x", pady=5)
        f.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(f, text="💥 Burst Mode Settings", font=("Segoe UI", 14, "bold"), text_color="#00e676").grid(row=0, column=0, columnspan=2, pady=(10, 5), padx=10, sticky="w")

        ctk.CTkLabel(f, text="Hold Duration (ms):", text_color="#fff").grid(row=1, column=0, sticky="w", padx=10, pady=2)
        hold_duration_slider = ctk.CTkSlider(f, from_=100, to=2000, number_of_steps=95, command=self.update_burst_hold_duration)
        hold_duration_slider.set(getattr(config, "burst_hold_duration_ms", 500))
        hold_duration_slider.grid(row=1, column=1, sticky="ew", padx=(5, 5), pady=2)
        self.burst_hold_duration_label = ctk.CTkLabel(f, text=str(getattr(config, "burst_hold_duration_ms", 500)), text_color=NEON, width=50)
        self.burst_hold_duration_label.grid(row=1, column=2, padx=10, pady=2)

        ctk.CTkLabel(f, text="Cooldown after Burst (ms):", text_color="#fff").grid(row=2, column=0, sticky="w", padx=10, pady=(2, 10))
        cooldown_slider = ctk.CTkSlider(f, from_=0, to=1000, number_of_steps=100, command=self.update_burst_cooldown)
        cooldown_slider.set(config.burst_cooldown_ms)
        cooldown_slider.grid(row=2, column=1, sticky="ew", padx=(5, 5), pady=(2, 10))
        self.burst_cooldown_label = ctk.CTkLabel(f, text=str(config.burst_cooldown_ms), text_color=NEON, width=50)
        self.burst_cooldown_label.grid(row=2, column=2, padx=10, pady=(2, 10))

    def add_normal_mode_settings(self):
        f = ctk.CTkFrame(self.triggerbot_dynamic_frame, fg_color="#1a1a1a")
        f.pack(fill="x", pady=5)
        f.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(f, text="⚙️ Normal Mode Settings", font=("Segoe UI", 14, "bold"), text_color="#00e676").grid(row=0, column=0, columnspan=2, pady=(10, 5), padx=10, sticky="w")

        # Show different controls based on detection method
        if getattr(config, "trigger_detection_method", "ai") == "ai":
            # AI Detection controls
            ctk.CTkLabel(f, text="AI Delay (ms):", text_color="#fff").grid(row=1, column=0, sticky="w", padx=10, pady=2)
            delay_slider = ctk.CTkSlider(f, from_=0, to=500, number_of_steps=100, command=self.update_taps_delay)
            delay_slider.set(config.trigger_delay_ms)
            delay_slider.grid(row=1, column=1, sticky="ew", padx=(5, 5), pady=2)
            self.taps_delay_label = ctk.CTkLabel(f, text=str(config.trigger_delay_ms), text_color=NEON, width=50)
            self.taps_delay_label.grid(row=1, column=2, padx=10, pady=2)

            ctk.CTkLabel(f, text="AI Cooldown (ms):", text_color="#fff").grid(row=2, column=0, sticky="w", padx=10, pady=2)
            cooldown_slider = ctk.CTkSlider(f, from_=0, to=1000, number_of_steps=100, command=self.update_taps_cooldown)
            cooldown_slider.set(config.trigger_cooldown_ms)
            cooldown_slider.grid(row=2, column=1, sticky="ew", padx=(5, 5), pady=2)
            self.taps_cooldown_label = ctk.CTkLabel(f, text=str(config.trigger_cooldown_ms), text_color=NEON, width=50)
            self.taps_cooldown_label.grid(row=2, column=2, padx=10, pady=2)
        else:
            # Color Detection controls
            ctk.CTkLabel(f, text="Color Delay (ms):", text_color="#fff").grid(row=1, column=0, sticky="w", padx=10, pady=2)
            color_delay_slider = ctk.CTkSlider(f, from_=0, to=500, number_of_steps=100, command=self.update_color_delay)
            color_delay_slider.set(getattr(config, "trigger_color_delay_ms", 50))
            color_delay_slider.grid(row=1, column=1, sticky="ew", padx=(5, 5), pady=2)
            self.color_delay_label = ctk.CTkLabel(f, text=str(getattr(config, "trigger_color_delay_ms", 50)), text_color=NEON, width=50)
            self.color_delay_label.grid(row=1, column=2, padx=10, pady=2)

            ctk.CTkLabel(f, text="Color Cooldown (ms):", text_color="#fff").grid(row=2, column=0, sticky="w", padx=10, pady=2)
            color_cooldown_slider = ctk.CTkSlider(f, from_=0, to=1000, number_of_steps=100, command=self.update_color_cooldown)
            color_cooldown_slider.set(getattr(config, "trigger_color_cooldown_ms", 200))
            color_cooldown_slider.grid(row=2, column=1, sticky="ew", padx=(5, 5), pady=2)
            self.color_cooldown_label = ctk.CTkLabel(f, text=str(getattr(config, "trigger_color_cooldown_ms", 200)), text_color=NEON, width=50)
            self.color_cooldown_label.grid(row=2, column=2, padx=10, pady=2)

        ctk.CTkLabel(f, text="Time Between Shots (ms):", text_color="#fff").grid(row=3, column=0, sticky="w", padx=10, pady=(2, 10))
        shot_delay_slider = ctk.CTkSlider(f, from_=0, to=500, number_of_steps=100, command=self.update_normal_shot_delay)
        shot_delay_slider.set(getattr(config, "normal_shot_delay_ms", 50))
        shot_delay_slider.grid(row=3, column=1, sticky="ew", padx=(5, 5), pady=(2, 10))
        self.normal_shot_delay_label = ctk.CTkLabel(f, text=str(getattr(config, "normal_shot_delay_ms", 50)), text_color=NEON, width=50)
        self.normal_shot_delay_label.grid(row=3, column=2, padx=10, pady=(2, 10))
        
        # Add color detection controls if in color mode
        if getattr(config, "trigger_detection_method", "ai") == "color":
            self.add_color_detection_controls(f)

    def add_color_detection_controls(self, parent):
        """Add HSV color detection controls to the triggerbot frame"""
        # Color picker section
        color_frame = ctk.CTkFrame(parent, fg_color="#2a2a2a", corner_radius=8)
        color_frame.grid(row=4, column=0, columnspan=3, sticky="ew", padx=10, pady=(10, 5))
        color_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(color_frame, text="🎨 Color Detection", font=("Segoe UI", 12, "bold"), text_color="#00e676").grid(row=0, column=0, columnspan=3, pady=(8, 5), padx=10, sticky="w")
        
        # Color radius
        ctk.CTkLabel(color_frame, text="Detection Radius (px):", text_color="#fff").grid(row=1, column=0, sticky="w", padx=10, pady=2)
        radius_slider = ctk.CTkSlider(color_frame, from_=5, to=50, number_of_steps=45, command=self.update_color_radius)
        radius_slider.set(getattr(config, "trigger_color_radius_px", 20))
        radius_slider.grid(row=1, column=1, sticky="ew", padx=(5, 5), pady=2)
        self.color_radius_label = ctk.CTkLabel(color_frame, text=str(getattr(config, "trigger_color_radius_px", 20)), text_color=NEON, width=50)
        self.color_radius_label.grid(row=1, column=2, padx=10, pady=2)
        
        # RGB color picker
        ctk.CTkLabel(color_frame, text="Target Color (RGB):", text_color="#fff").grid(row=2, column=0, sticky="w", padx=10, pady=2)
        
        # Color preview
        self.color_preview = ctk.CTkFrame(color_frame, width=40, height=20, fg_color="#FF0000")
        self.color_preview.grid(row=2, column=1, sticky="w", padx=(5, 10), pady=2)
        
        # Color picker button
        color_picker_btn = ctk.CTkButton(color_frame, text="Pick Color", command=self.open_color_picker, width=80, height=25)
        color_picker_btn.grid(row=2, column=2, padx=10, pady=2)
        
        # RGB sliders
        ctk.CTkLabel(color_frame, text="Red:", text_color="#fff").grid(row=3, column=0, sticky="w", padx=10, pady=2)
        self.color_red_slider = ctk.CTkSlider(color_frame, from_=0, to=255, number_of_steps=255, command=self.update_color_rgb)
        self.color_red_slider.set(getattr(config, "target_color_r", 255))
        self.color_red_slider.grid(row=3, column=1, sticky="ew", padx=(5, 5), pady=2)
        self.color_red_value = ctk.CTkLabel(color_frame, text=str(getattr(config, "target_color_r", 255)), text_color=NEON, width=50)
        self.color_red_value.grid(row=3, column=2, padx=10, pady=2)
        
        ctk.CTkLabel(color_frame, text="Green:", text_color="#fff").grid(row=4, column=0, sticky="w", padx=10, pady=2)
        self.color_green_slider = ctk.CTkSlider(color_frame, from_=0, to=255, number_of_steps=255, command=self.update_color_rgb)
        self.color_green_slider.set(getattr(config, "target_color_g", 0))
        self.color_green_slider.grid(row=4, column=1, sticky="ew", padx=(5, 5), pady=2)
        self.color_green_value = ctk.CTkLabel(color_frame, text=str(getattr(config, "target_color_g", 0)), text_color=NEON, width=50)
        self.color_green_value.grid(row=4, column=2, padx=10, pady=2)
        
        ctk.CTkLabel(color_frame, text="Blue:", text_color="#fff").grid(row=5, column=0, sticky="w", padx=10, pady=2)
        self.color_blue_slider = ctk.CTkSlider(color_frame, from_=0, to=255, number_of_steps=255, command=self.update_color_rgb)
        self.color_blue_slider.set(getattr(config, "target_color_b", 0))
        self.color_blue_slider.grid(row=5, column=1, sticky="ew", padx=(5, 5), pady=2)
        self.color_blue_value = ctk.CTkLabel(color_frame, text=str(getattr(config, "target_color_b", 0)), text_color=NEON, width=50)
        self.color_blue_value.grid(row=5, column=2, padx=10, pady=2)
        
        # Color tolerance
        ctk.CTkLabel(color_frame, text="Color Tolerance:", text_color="#fff").grid(row=6, column=0, sticky="w", padx=10, pady=(2, 8))
        tolerance_slider = ctk.CTkSlider(color_frame, from_=1, to=50, number_of_steps=49, command=self.update_color_tolerance)
        tolerance_slider.set(getattr(config, "color_tolerance", 20))
        tolerance_slider.grid(row=6, column=1, sticky="ew", padx=(5, 5), pady=(2, 8))
        self.color_tolerance_value = ctk.CTkLabel(color_frame, text=str(getattr(config, "color_tolerance", 20)), text_color=NEON, width=50)
        self.color_tolerance_value.grid(row=6, column=2, padx=10, pady=(2, 8))

    def update_trigger_mode(self):
        # Add small delay to prevent rapid mode changes
        current_time = time.time()
        if hasattr(self, '_last_mode_change_time'):
            if current_time - self._last_mode_change_time < 0.1:  # 100ms cooldown
                return
        self._last_mode_change_time = current_time
        
        config.trigger_mode = self.trigger_mode_var.get()
        self.update_triggerbot_dynamic_frame()
        try:
            if hasattr(config, "save") and callable(config.save):
                self._schedule_config_save()
        except Exception as e:
            print(f"[WARN] Failed to save trigger_mode: {e}")

    def update_spray_initial_delay(self, val):
        val = int(round(float(val)))
        config.spray_initial_delay_ms = val
        self.spray_initial_delay_label.configure(text=str(val))
        self._schedule_config_save()

    def update_spray_cooldown(self, val):
        val = int(round(float(val)))
        config.spray_cooldown_ms = val
        self.spray_cooldown_label.configure(text=str(val))
        self._schedule_config_save()

    def update_burst_hold_duration(self, val):
        val = int(round(float(val)))
        config.burst_hold_duration_ms = val
        self.burst_hold_duration_label.configure(text=str(val))
        self._schedule_config_save()

    def update_burst_delay(self, val):
        val = int(round(float(val)))
        config.burst_delay_ms = val
        self.burst_delay_label.configure(text=str(val))
        self._schedule_config_save()

    def update_burst_cooldown(self, val):
        val = int(round(float(val)))
        config.burst_cooldown_ms = val
        self.burst_cooldown_label.configure(text=str(val))
        self._schedule_config_save()

    def update_taps_delay(self, val):
        val = int(round(float(val)))
        config.trigger_delay_ms = val
        self.taps_delay_label.configure(text=str(val))
        self._schedule_config_save()

    def update_taps_cooldown(self, val):
        val = int(round(float(val)))
        config.trigger_cooldown_ms = val
        self.taps_cooldown_label.configure(text=str(val))
        self._schedule_config_save()

    def update_normal_shot_delay(self, val):
        val = int(round(float(val)))
        config.normal_shot_delay_ms = val
        self.normal_shot_delay_label.configure(text=str(val))
        self._schedule_config_save()

    def update_color_delay(self, val):
        val = int(round(float(val)))
        config.trigger_color_delay_ms = val
        self.color_delay_label.configure(text=str(val))
        self._schedule_config_save()

    def update_color_cooldown(self, val):
        val = int(round(float(val)))
        config.trigger_color_cooldown_ms = val
        self.color_cooldown_label.configure(text=str(val))
        self._schedule_config_save()

    def update_color_radius(self, val):
        val = int(round(float(val)))
        config.trigger_color_radius_px = val
        self.color_radius_label.configure(text=str(val))
        self._schedule_config_save()

    def update_color_rgb(self, val=None):
        """Update color preview and HSV values from RGB sliders"""
        try:
            r = int(self.color_red_slider.get())
            g = int(self.color_green_slider.get())
            b = int(self.color_blue_slider.get())
            
            # Update labels
            self.color_red_value.configure(text=str(r))
            self.color_green_value.configure(text=str(g))
            self.color_blue_value.configure(text=str(b))
            
            # Convert RGB to HSV
            rgb_color = np.array([[[b, g, r]]], dtype=np.uint8)  # BGR format for OpenCV
            hsv_color = cv2.cvtColor(rgb_color, cv2.COLOR_BGR2HSV)
            h, s, v = hsv_color[0][0]
            
            # Update color preview
            hex_color = f"#{r:02x}{g:02x}{b:02x}"
            self.color_preview.configure(fg_color=hex_color)
            
            # Update config
            config.target_color_r = r
            config.target_color_g = g
            config.target_color_b = b
            
            # Get tolerance and calculate HSV ranges
            tolerance = int(getattr(config, 'color_tolerance', 20))
            
            # Calculate HSV ranges with tolerance
            h_min = max(0, h - tolerance)
            h_max = min(179, h + tolerance)
            s_min = max(0, s - tolerance)
            s_max = min(255, s + tolerance)
            v_min = max(0, v - tolerance)
            v_max = min(255, v + tolerance)
            
            # Update HSV config
            config.trigger_hsv_h_min = h_min
            config.trigger_hsv_h_max = h_max
            config.trigger_hsv_s_min = s_min
            config.trigger_hsv_s_max = s_max
            config.trigger_hsv_v_min = v_min
            config.trigger_hsv_v_max = v_max
            
            print(f"[INFO] Color updated: RGB({r},{g},{b}) -> HSV({h},{s},{v}) ±{tolerance}")
            
            # Save configuration
            self._schedule_config_save()
            
        except Exception as e:
            print(f"[WARN] Failed to update color: {e}")

    def update_color_tolerance(self, val):
        """Update color tolerance and recalculate HSV ranges"""
        tolerance = int(val)
        config.color_tolerance = tolerance
        self.color_tolerance_value.configure(text=str(tolerance))
        # Trigger RGB update to recalculate HSV ranges
        self.update_color_rgb()

    def open_color_picker(self):
        """Open color picker dialog"""
        try:
            from tkinter import colorchooser
            color = colorchooser.askcolor(title="Select Target Color")
            if color[0]:  # color[0] is RGB tuple, color[1] is hex
                r, g, b = [int(c) for c in color[0]]
                
                # Update sliders
                self.color_red_slider.set(r)
                self.color_green_slider.set(g)
                self.color_blue_slider.set(b)
                
                # Update color preview and HSV
                self.update_color_rgb()
                
                print(f"[INFO] Color picker: Selected RGB({r},{g},{b})")
        except Exception as e:
            print(f"[WARN] Color picker failed: {e}")

    def update_target_switch_delay(self, val):
        val = int(round(float(val)))
        config.target_switch_delay_ms = val
        self.target_switch_delay_entry.delete(0, "end")
        self.target_switch_delay_entry.insert(0, str(val))
        self._schedule_config_save()

    def on_trigger_detection_method_change(self, value):
        """Handle trigger detection method change (AI/Color)"""
        method = value.lower()
        config.trigger_detection_method = method
        print(f"[INFO] Triggerbot detection method changed to: {method.upper()}")
        
        # DIRECT COLOR FRAME HANDLING (FIXED VERSION)
        # Debug: Real callback (removed for cleaner output)
        
        try:
            if hasattr(self, 'color_frame') and self.color_frame is not None:
                if method == "color":
                    # Debug: Showing color frame (removed for cleaner output)
                    self.color_frame.grid(row=4, column=0, columnspan=2, sticky="ew", padx=15, pady=(5, 15))
                    print("[INFO] ✅ HSV color settings SHOWN")
                else:
                    # Debug: Hiding color frame (removed for cleaner output)
                    self.color_frame.grid_remove()
                    print("[INFO] ❌ HSV color settings HIDDEN")
                
                # Force GUI update
                self.update_idletasks()
                # Debug: Color frame handling completed (removed for cleaner output)
            else:
                print("[ERROR] 🚨 Color frame not available in real callback!")
        except Exception as e:
            print(f"[ERROR] 🚨 Real callback failed: {e}")
        
        # Update the triggerbot dynamic frame to show appropriate controls
        self.update_triggerbot_dynamic_frame()
        
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save trigger_detection_method: {e}")

    def on_target_switch_delay_entry_commit(self, event=None):
        """Handle target switch delay entry input"""
        try:
            val = int(self.target_switch_delay_entry.get().strip())
            val = max(0, min(500, val))  # Clamp to valid range
            config.target_switch_delay_ms = val
            self.target_switch_delay_slider.set(val)
            self.target_switch_delay_entry.delete(0, "end")
            self.target_switch_delay_entry.insert(0, str(val))
            config.save()
        except Exception:
            # Revert to current config value on error
            self.target_switch_delay_entry.delete(0, "end")
            self.target_switch_delay_entry.insert(0, str(getattr(config, "target_switch_delay_ms", 100)))

    def update_triggerbot_dynamic_frame(self):
        for w in self.triggerbot_dynamic_frame.winfo_children():
            w.destroy()
        mode = config.trigger_mode
        if mode == "spray":
            self.add_spray_mode_settings()
        elif mode == "burst":
            self.add_burst_mode_settings()
        elif mode == "normal":
            self.add_normal_mode_settings()

    def build_detection_settings(self, parent, row):
        """Enhanced detection settings with better layout"""
        frame = ctk.CTkFrame(parent, fg_color="#1a1a1a")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        frame.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(frame, text="🎯 Detection Settings", font=("Segoe UI", 16, "bold"), text_color="#00e676").grid(row=0, column=0, pady=(15, 10), padx=15, sticky="w")
        
        # Settings grid
        settings_frame = ctk.CTkFrame(frame, fg_color="transparent")
        settings_frame.grid(row=1, column=0, sticky="ew", padx=15, pady=(0, 15))
        settings_frame.grid_columnconfigure(0, weight=0)  # Label column
        settings_frame.grid_columnconfigure(1, weight=1)  # Slider column
        settings_frame.grid_columnconfigure(2, weight=0)  # Value column
        settings_frame.grid_rowconfigure(0, weight=0)
        settings_frame.grid_rowconfigure(1, weight=0)
        settings_frame.grid_rowconfigure(2, weight=0)
        settings_frame.grid_rowconfigure(3, weight=0)  # Spacing row 1
        settings_frame.grid_rowconfigure(4, weight=0)  # Spacing row 2
        settings_frame.grid_rowconfigure(5, weight=0)  # Spacing row 3
        settings_frame.grid_rowconfigure(6, weight=0)  # Checkbox row
        settings_frame.grid_rowconfigure(7, weight=0)  # Presets row
        
        # Confidence (row 0)
        ctk.CTkLabel(settings_frame, text="Confidence", font=("Segoe UI", 12, "bold"), text_color="#fff")\
            .grid(row=0, column=0, sticky="w", pady=5)

        self.conf_slider = ctk.CTkSlider(
            settings_frame, from_=0.05, to=0.95, number_of_steps=18, command=self.update_conf
        )
        self.conf_slider.grid(row=0, column=1, sticky="ew", padx=(10, 5), pady=5)
        self.conf_slider.set(config.conf)

        # Manual entry (replaces the old value label)
        self.conf_entry = ctk.CTkEntry(
            settings_frame, width=70, justify="center",
            font=("Segoe UI", 12, "bold"), text_color=NEON
        )
        self.conf_entry.grid(row=0, column=2, pady=5)
        self.conf_entry.insert(0, f"{config.conf:.2f}")

        self.conf_entry.bind("<Return>", self.on_conf_entry_commit)
        self.conf_entry.bind("<FocusOut>", self.on_conf_entry_commit)
        
        # Resolution (row 1)
        ctk.CTkLabel(settings_frame, text="Model Image Size", font=("Segoe UI", 12, "bold"), text_color="#fff")\
            .grid(row=1, column=0, sticky="w", pady=5)

        self.imgsz_slider = ctk.CTkSlider(
            settings_frame, from_=128, to=1280, number_of_steps=36, command=self.update_imgsz
        )
        self.imgsz_slider.grid(row=1, column=1, sticky="ew", padx=(10, 5), pady=5)
        self.imgsz_slider.set(config.imgsz)

        # Manual entry (replaces the value label)
        self.imgsz_entry = ctk.CTkEntry(
            settings_frame, width=70, justify="center",
            font=("Segoe UI", 12, "bold"), text_color=NEON
        )
        self.imgsz_entry.grid(row=1, column=2, pady=5)
        self.imgsz_entry.insert(0, str(config.imgsz))

        # Commit on Enter or focus-out
        self.imgsz_entry.bind("<Return>", self.on_imgsz_entry_commit)
        self.imgsz_entry.bind("<FocusOut>", self.on_imgsz_entry_commit)
        
        # Max Detections
        ctk.CTkLabel(settings_frame, text="Max Detections", font=("Segoe UI", 12, "bold"), text_color="#fff").grid(row=2, column=0, sticky="w", pady=5)
        self.max_detect_slider = ctk.CTkSlider(settings_frame, from_=1, to=100, number_of_steps=99, command=self.update_max_detect)
        self.max_detect_slider.grid(row=2, column=1, sticky="ew", padx=(10, 5), pady=5)
        self.max_detect_label = ctk.CTkLabel(settings_frame, text=str(config.max_detect), font=("Segoe UI", 12, "bold"), text_color=NEON, width=50)
        self.max_detect_label.grid(row=2, column=2, pady=5)

        # Color Outline Filter Toggle - Make it super visible!
        print(f"[DEBUG] About to create color outline filter checkbox...")

        # Create a dedicated frame for the checkbox to make it stand out
        checkbox_frame = ctk.CTkFrame(settings_frame, fg_color="#2a2a2a", corner_radius=10, border_width=2, border_color="#00FF00", height=80)
        checkbox_frame.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(15, 15), padx=15)
        print(f"[DEBUG] Checkbox frame positioned at row=6, column=0, columnspan=3")

        checkbox_frame.grid_columnconfigure(0, weight=1)
        checkbox_frame.grid_columnconfigure(1, weight=1)

        # Add some padding inside the frame
        checkbox_frame.grid_rowconfigure(0, weight=1, uniform="checkbox")
        checkbox_frame.grid_rowconfigure(1, weight=1, uniform="checkbox")
        checkbox_frame.grid_columnconfigure(0, weight=1, uniform="checkbox")
        print(f"[DEBUG] Checkbox frame configured with weights")

        self.outline_filter_var = ctk.BooleanVar(value=bool(config.color_outline_filter_enabled))
        print(f"[DEBUG] 🎨 Creating checkbox with initial value: {config.color_outline_filter_enabled}")
        print(f"[DEBUG] 🎨 BooleanVar value: {self.outline_filter_var.get()}")
        
        self.outline_filter_checkbox = ctk.CTkCheckBox(
            checkbox_frame,
            text="🎯 ENEMY OUTLINE FILTER 🎯",
            variable=self.outline_filter_var,
            onvalue=True, offvalue=False,
            command=self.toggle_outline_filter,
            text_color="#00FF00",  # Bright green to make it visible
            font=("Segoe UI", 16, "bold"),  # Even larger font
            fg_color="#444444",  # Darker background
            hover_color="#666666",  # Lighter hover
            border_color="#00FF00",  # Green border
            checkmark_color="#000000"  # Black checkmark
        )
        self.outline_filter_checkbox.grid(row=0, column=0, columnspan=2, sticky="w", pady=5, padx=10)
        print(f"[DEBUG] Color outline filter checkbox created! Initial value: {config.color_outline_filter_enabled}")
        print(f"[DEBUG] Checkbox widget: {self.outline_filter_checkbox}")
        print(f"[DEBUG] Checkbox parent: {self.outline_filter_checkbox.master}")

        # Outline filter help text - make it more visible too
        outline_help = ctk.CTkLabel(checkbox_frame, text="🎯 Only target ENEMIES (red/yellow/purple outlines) - Avoid teammates (no outlines)",
                            text_color="#00FF00", font=("Segoe UI", 12, "bold"),  # Green and bold
                            fg_color="#1a1a1a")  # Background to make it stand out
        outline_help.grid(row=1, column=0, columnspan=2, pady=(5, 10), padx=10, sticky="w")
        print(f"[DEBUG] Help text created: {outline_help}")

        # Quick presets - moved to row 7 with much more spacing to avoid overlap
        preset_frame = ctk.CTkFrame(settings_frame, fg_color="#2a2a2a", corner_radius=8)
        preset_frame.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(20, 0))  # Reduced padding since no HSV settings
        
        ctk.CTkLabel(preset_frame, text="Quick Presets:", font=("Segoe UI", 10, "bold"), text_color="#ccc").pack(pady=(8, 5))
        
        preset_buttons = ctk.CTkFrame(preset_frame, fg_color="transparent")
        preset_buttons.pack(pady=(0, 8))
        
        def set_conf_preset(value):
                value = round(float(value), 2)
                config.conf = value
                self.conf_slider.set(value)
                self._set_entry_text(self.conf_entry, f"{value:.2f}")
        
        ctk.CTkButton(preset_buttons, text="Strict (0.8)", command=lambda: set_conf_preset(0.8), width=80, height=25).pack(side="left", padx=2)
        ctk.CTkButton(preset_buttons, text="Normal (0.5)", command=lambda: set_conf_preset(0.5), width=80, height=25).pack(side="left", padx=2)
        ctk.CTkButton(preset_buttons, text="Loose (0.2)", command=lambda: set_conf_preset(0.2), width=80, height=25).pack(side="left", padx=2)

    def build_aim_settings(self, parent, row):
        """Aim configuration settings"""
        frame = ctk.CTkFrame(parent, fg_color="#1a1a1a")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        frame.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(frame, text="🎮 Aim Settings", font=("Segoe UI", 16, "bold"), text_color="#00e676").grid(row=0, column=0, pady=(15, 10), padx=15, sticky="w")
        
        settings_frame = ctk.CTkFrame(frame, fg_color="transparent")
        settings_frame.grid(row=1, column=0, sticky="ew", padx=15, pady=(0, 15))
        settings_frame.grid_columnconfigure(1, weight=1)

        # Aim always on (toggle under Smoothing)
        self.always_on_switch = ctk.CTkSwitch(
            settings_frame,
            text="Aim always on",
            variable=self.always_on_var,
            command=self.on_always_on_toggle,
            text_color="#fff"
        )
        self.always_on_switch.grid(row=0, column=0, columnspan=3, sticky="w", pady=(8, 5))
        
        # Mouse Movement Multiplier Section (moved to top)
        mouse_multiplier_frame = ctk.CTkFrame(settings_frame, fg_color="#2a2a2a", corner_radius=8)
        mouse_multiplier_frame.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(5, 10))
        mouse_multiplier_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(mouse_multiplier_frame, text="🖱️ Mouse Movement", font=("Segoe UI", 12, "bold"), text_color="#00e676").grid(row=0, column=0, columnspan=3, pady=(8, 5), padx=10, sticky="w")
        
        # Mouse Movement Sync Toggle
        self.mouse_movement_sync_var = ctk.BooleanVar(value=getattr(config, "mouse_movement_sync_enabled", False))
        self.mouse_movement_sync_switch = ctk.CTkSwitch(
            mouse_multiplier_frame,
            text="🔗 Sync X/Y Movement",
            variable=self.mouse_movement_sync_var,
            command=self.on_mouse_movement_sync_toggle,
            text_color="#fff"
        )
        self.mouse_movement_sync_switch.grid(row=1, column=0, columnspan=3, sticky="w", padx=10, pady=(5, 2))
        
        # X-Axis Movement Multiplier
        ctk.CTkLabel(mouse_multiplier_frame, text="X-Axis Speed", font=("Segoe UI", 11), text_color="#fff").grid(row=2, column=0, sticky="w", padx=10, pady=2)
        self.mouse_multiplier_x_slider = ctk.CTkSlider(mouse_multiplier_frame, from_=0.0, to=5.0, number_of_steps=500, command=self.update_mouse_multiplier_x)
        self.mouse_multiplier_x_slider.grid(row=2, column=1, sticky="ew", padx=(10, 5), pady=2)
        self.mouse_multiplier_x_entry = ctk.CTkEntry(mouse_multiplier_frame, width=60, justify="center", font=("Segoe UI", 11, "bold"), text_color=NEON)
        self.mouse_multiplier_x_entry.grid(row=2, column=2, padx=10, pady=2)
        self.mouse_multiplier_x_entry.insert(0, f"{getattr(config, 'mouse_movement_multiplier_x', 1.0):.2f}")
        self.mouse_multiplier_x_entry.bind("<Return>", self.on_mouse_multiplier_x_entry_commit)
        self.mouse_multiplier_x_entry.bind("<FocusOut>", self.on_mouse_multiplier_x_entry_commit)
        
        # Y-Axis Movement Multiplier
        ctk.CTkLabel(mouse_multiplier_frame, text="Y-Axis Speed", font=("Segoe UI", 11), text_color="#fff").grid(row=3, column=0, sticky="w", padx=10, pady=2)
        self.mouse_multiplier_y_slider = ctk.CTkSlider(mouse_multiplier_frame, from_=0.0, to=5.0, number_of_steps=500, command=self.update_mouse_multiplier_y)
        self.mouse_multiplier_y_slider.grid(row=3, column=1, sticky="ew", padx=(10, 5), pady=2)
        self.mouse_multiplier_y_entry = ctk.CTkEntry(mouse_multiplier_frame, width=60, justify="center", font=("Segoe UI", 11, "bold"), text_color=NEON)
        self.mouse_multiplier_y_entry.grid(row=3, column=2, padx=10, pady=2)
        self.mouse_multiplier_y_entry.insert(0, f"{getattr(config, 'mouse_movement_multiplier_y', 1.0):.2f}")
        self.mouse_multiplier_y_entry.bind("<Return>", self.on_mouse_multiplier_y_entry_commit)
        self.mouse_multiplier_y_entry.bind("<FocusOut>", self.on_mouse_multiplier_y_entry_commit)
        
        # Movement Enable/Disable Toggles
        movement_toggles_frame = ctk.CTkFrame(mouse_multiplier_frame, fg_color="transparent")
        movement_toggles_frame.grid(row=4, column=0, columnspan=3, sticky="ew", padx=10, pady=(5, 8))
        
        self.mouse_movement_x_enabled_var = ctk.BooleanVar(value=getattr(config, "mouse_movement_enabled_x", True))
        self.mouse_movement_x_enabled_switch = ctk.CTkSwitch(
            movement_toggles_frame,
            text="Enable X",
            variable=self.mouse_movement_x_enabled_var,
            command=self.on_mouse_movement_x_enabled_toggle,
            text_color="#fff"
        )
        self.mouse_movement_x_enabled_switch.pack(side="left", padx=(0, 20))
        
        self.mouse_movement_y_enabled_var = ctk.BooleanVar(value=getattr(config, "mouse_movement_enabled_y", True))
        self.mouse_movement_y_enabled_switch = ctk.CTkSwitch(
            movement_toggles_frame,
            text="Enable Y",
            variable=self.mouse_movement_y_enabled_var,
            command=self.on_mouse_movement_y_enabled_toggle,
            text_color="#fff"
        )
        self.mouse_movement_y_enabled_switch.pack(side="left")
        
        # Mouse Button Selection (moved to top)
        ctk.CTkLabel(settings_frame, text="Aim Key:", font=("Segoe UI", 12, "bold"), text_color="#fff").grid(row=2, column=0, sticky="nw", pady=(10, 5))
        
        self.btn_var = ctk.IntVar(value=config.selected_mouse_button)
        btn_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
        btn_frame.grid(row=2, column=1, columnspan=2, sticky="ew", pady=(10, 5))
        
        for i, txt in enumerate(["Left", "Right", "Middle", "Side 4", "Side 5"]):
            ctk.CTkRadioButton(btn_frame, text=txt, variable=self.btn_var, value=i, command=self.update_mouse_btn, text_color="#fff").pack(side="left", padx=8)
        
        # Secondary Aim Keybind Section (moved up for better visibility)
        secondary_frame = ctk.CTkFrame(settings_frame, fg_color="#2a2a2a", corner_radius=8)
        secondary_frame.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(5, 10))
        secondary_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(secondary_frame, text="🎯 Secondary Aim Keybind", font=("Segoe UI", 12, "bold"), text_color="#00e676").grid(row=0, column=0, columnspan=3, pady=(8, 5), padx=10, sticky="w")
        
        # Secondary aim enable switch
        self.secondary_aim_enabled_var = ctk.BooleanVar(value=bool(getattr(config, "secondary_aim_enabled", False)))
        self.secondary_aim_enabled_switch = ctk.CTkSwitch(
            secondary_frame,
            text="Enable Secondary Aim",
            variable=self.secondary_aim_enabled_var,
            command=self.on_secondary_aim_enabled_toggle,
            text_color="#fff"
        )
        self.secondary_aim_enabled_switch.grid(row=1, column=0, columnspan=3, sticky="w", pady=(5, 10), padx=10)
        
        # Secondary aim button selection
        ctk.CTkLabel(secondary_frame, text="Secondary Button:", font=("Segoe UI", 11, "bold"), text_color="#fff").grid(row=2, column=0, sticky="w", padx=10, pady=5)
        
        self.secondary_aim_button_var = ctk.IntVar(value=int(getattr(config, "secondary_aim_button", 2)))
        secondary_buttons_frame = ctk.CTkFrame(secondary_frame, fg_color="transparent")
        secondary_buttons_frame.grid(row=2, column=1, sticky="w", padx=10, pady=5)
        
        for i, txt in enumerate(["Left", "Right", "Middle", "Side 4", "Side 5"]):
            ctk.CTkRadioButton(secondary_buttons_frame, text=txt, variable=self.secondary_aim_button_var, value=i,
                            command=self.update_secondary_aim_button, text_color="#fff").pack(side="left", padx=8)
        
        # Height Targeting Section
        height_frame = ctk.CTkFrame(settings_frame, fg_color="#2a2a2a", corner_radius=8)
        height_frame.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(5, 10))
        height_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(height_frame, text="🎯 Height Targeting", font=("Segoe UI", 12, "bold"), text_color="#00e676").grid(row=0, column=0, columnspan=3, pady=(8, 5), padx=10, sticky="w")
        
        # Height Targeting Enable Toggle
        self.height_targeting_var = ctk.BooleanVar(value=getattr(config, "height_targeting_enabled", True))
        self.height_targeting_switch = ctk.CTkSwitch(
            height_frame,
            text="Enable Height Targeting",
            variable=self.height_targeting_var,
            command=self.on_height_targeting_toggle,
            text_color="#fff"
        )
        self.height_targeting_switch.grid(row=1, column=0, columnspan=3, sticky="w", padx=10, pady=(5, 2))
        
        # Target Height
        ctk.CTkLabel(height_frame, text="Target Height", font=("Segoe UI", 11, "bold"), text_color="#fff").grid(row=2, column=0, sticky="w", padx=10, pady=2)
        self.target_height_slider = ctk.CTkSlider(height_frame, from_=0.0, to=1.0, number_of_steps=100, command=self.update_target_height)
        self.target_height_slider.grid(row=2, column=1, sticky="ew", padx=(10, 5), pady=2)
        self.target_height_entry = ctk.CTkEntry(height_frame, width=60, justify="center", font=("Segoe UI", 11, "bold"), text_color=NEON)
        self.target_height_entry.grid(row=2, column=2, padx=10, pady=2)
        self.target_height_entry.insert(0, f"{config.target_height:.3f}")
        self.target_height_entry.bind("<Return>", self.on_target_height_entry_commit)
        self.target_height_entry.bind("<FocusOut>", self.on_target_height_entry_commit)
        
        # Height Deadzone Toggle
        self.height_deadzone_var = ctk.BooleanVar(value=getattr(config, "height_deadzone_enabled", True))
        self.height_deadzone_switch = ctk.CTkSwitch(
            height_frame,
            text="Enable Deadzone",
            variable=self.height_deadzone_var,
            command=self.on_height_deadzone_toggle,
            text_color="#fff"
        )
        self.height_deadzone_switch.grid(row=3, column=0, columnspan=3, sticky="w", padx=10, pady=(5, 2))
        
        # Deadzone Min
        ctk.CTkLabel(height_frame, text="Deadzone Min", font=("Segoe UI", 11), text_color="#fff").grid(row=4, column=0, sticky="w", padx=10, pady=2)
        self.deadzone_min_slider = ctk.CTkSlider(height_frame, from_=0.0, to=1.0, number_of_steps=100, command=self.update_deadzone_min)
        self.deadzone_min_slider.grid(row=4, column=1, sticky="ew", padx=(10, 5), pady=2)
        self.deadzone_min_entry = ctk.CTkEntry(height_frame, width=60, justify="center", font=("Segoe UI", 11, "bold"), text_color=NEON)
        self.deadzone_min_entry.grid(row=4, column=2, padx=10, pady=2)
        self.deadzone_min_entry.insert(0, f"{config.height_deadzone_min:.3f}")
        self.deadzone_min_entry.bind("<Return>", self.on_deadzone_min_entry_commit)
        self.deadzone_min_entry.bind("<FocusOut>", self.on_deadzone_min_entry_commit)
        
        # Deadzone Max
        ctk.CTkLabel(height_frame, text="Deadzone Max", font=("Segoe UI", 11), text_color="#fff").grid(row=5, column=0, sticky="w", padx=10, pady=2)
        self.deadzone_max_slider = ctk.CTkSlider(height_frame, from_=0.0, to=1.0, number_of_steps=100, command=self.update_deadzone_max)
        self.deadzone_max_slider.grid(row=5, column=1, sticky="ew", padx=(10, 5), pady=2)
        self.deadzone_max_entry = ctk.CTkEntry(height_frame, width=60, justify="center", font=("Segoe UI", 11, "bold"), text_color=NEON)
        self.deadzone_max_entry.grid(row=5, column=2, padx=10, pady=2)
        self.deadzone_max_entry.insert(0, f"{config.height_deadzone_max:.3f}")
        self.deadzone_max_entry.bind("<Return>", self.on_deadzone_max_entry_commit)
        self.deadzone_max_entry.bind("<FocusOut>", self.on_deadzone_max_entry_commit)
        
        # Deadzone Tolerance
        ctk.CTkLabel(height_frame, text="Deadzone Tolerance", font=("Segoe UI", 11), text_color="#fff").grid(row=6, column=0, sticky="w", padx=10, pady=(2, 8))
        self.deadzone_tolerance_slider = ctk.CTkSlider(height_frame, from_=0.0, to=20.0, number_of_steps=200, command=self.update_deadzone_tolerance)
        self.deadzone_tolerance_slider.grid(row=6, column=1, sticky="ew", padx=(10, 5), pady=(2, 8))
        self.deadzone_tolerance_entry = ctk.CTkEntry(height_frame, width=60, justify="center", font=("Segoe UI", 11, "bold"), text_color=NEON)
        self.deadzone_tolerance_entry.grid(row=6, column=2, padx=10, pady=(2, 8))
        self.deadzone_tolerance_entry.insert(0, f"{config.height_deadzone_tolerance:.1f}")
        self.deadzone_tolerance_entry.bind("<Return>", self.on_deadzone_tolerance_entry_commit)
        self.deadzone_tolerance_entry.bind("<FocusOut>", self.on_deadzone_tolerance_entry_commit)

        # FOV X Size
        ctk.CTkLabel(settings_frame, text="FOV X Size", font=("Segoe UI", 12, "bold"), text_color="#fff")\
            .grid(row=5, column=0, sticky="w", pady=5)

        self.fov_x_slider = ctk.CTkSlider(
            settings_frame, from_=20, to=500, command=self.update_fov_x, number_of_steps=180
        )
        self.fov_x_slider.grid(row=5, column=1, sticky="ew", padx=(10, 5), pady=5)

        self.fov_x_entry = ctk.CTkEntry(
            settings_frame, width=70, justify="center",
            font=("Segoe UI", 12, "bold"), text_color=NEON
        )
        self.fov_x_entry.grid(row=5, column=2, pady=5)
        self.fov_x_entry.insert(0, str(getattr(config, "fov_x_size", config.region_size)))
        self.fov_x_entry.bind("<Return>", self.on_fov_x_entry_commit)
        self.fov_x_entry.bind("<FocusOut>", self.on_fov_x_entry_commit)

        # FOV Y Size
        ctk.CTkLabel(settings_frame, text="FOV Y Size", font=("Segoe UI", 12, "bold"), text_color="#fff")\
            .grid(row=6, column=0, sticky="w", pady=5)

        self.fov_y_slider = ctk.CTkSlider(
            settings_frame, from_=20, to=500, command=self.update_fov_y, number_of_steps=180
        )
        self.fov_y_slider.grid(row=6, column=1, sticky="ew", padx=(10, 5), pady=5)

        self.fov_y_entry = ctk.CTkEntry(
            settings_frame, width=70, justify="center",
            font=("Segoe UI", 12, "bold"), text_color=NEON
        )
        self.fov_y_entry.grid(row=6, column=2, pady=5)
        self.fov_y_entry.insert(0, str(getattr(config, "fov_y_size", config.region_size)))
        self.fov_y_entry.bind("<Return>", self.on_fov_y_entry_commit)
        self.fov_y_entry.bind("<FocusOut>", self.on_fov_y_entry_commit)

        # FOV Sync Checkbox
        self.fov_sync_var = ctk.BooleanVar(value=bool(getattr(config, "fov_sync_enabled", False)))
        self.fov_sync_checkbox = ctk.CTkCheckBox(
            settings_frame, text="Sync", variable=self.fov_sync_var,
            command=self.on_fov_sync_toggle, font=("Segoe UI", 10, "bold")
        )
        self.fov_sync_checkbox.grid(row=5, column=3, rowspan=2, padx=(5, 10), pady=5)

        # guard to avoid feedback loops
        self._updating_fov_x = False
        self._updating_fov_y = False

        # Player Y Offset
        ctk.CTkLabel(settings_frame, text="Y Offset", font=("Segoe UI", 12, "bold"), text_color="#fff").grid(row=7, column=0, sticky="w", pady=5)
        self.offset_slider = ctk.CTkSlider(settings_frame, from_=0, to=20, command=self.update_offset, number_of_steps=20)
        self.offset_slider.grid(row=7, column=1, sticky="ew", padx=(10, 5), pady=5)
        self.offset_value = ctk.CTkLabel(settings_frame, text=str(config.player_y_offset), font=("Segoe UI", 12, "bold"), text_color=NEON, width=50)
        self.offset_value.grid(row=7, column=2, pady=5)
        

        # X-Center Targeting Section
        x_center_frame = ctk.CTkFrame(settings_frame, fg_color="#2a2a2a", corner_radius=8)
        x_center_frame.grid(row=10, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        x_center_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(x_center_frame, text="🎯 X-Center Targeting", font=("Segoe UI", 12, "bold"), text_color="#00e676").grid(row=0, column=0, columnspan=3, pady=(8, 5), padx=10, sticky="w")
        
        # X-Center Targeting Enable Toggle
        self.x_center_targeting_var = ctk.BooleanVar(value=config.x_center_targeting_enabled)
        self.x_center_targeting_switch = ctk.CTkSwitch(
            x_center_frame,
            text="X-Center Targeting",
            variable=self.x_center_targeting_var,
            command=self.on_x_center_targeting_toggle,
            text_color="#fff"
        )
        self.x_center_targeting_switch.grid(row=1, column=0, columnspan=3, sticky="w", padx=10, pady=(5, 2))
        
        # X-Center Tolerance Percentage
        ctk.CTkLabel(x_center_frame, text="Tolerance %", font=("Segoe UI", 11), text_color="#fff").grid(row=2, column=0, sticky="w", padx=10, pady=2)
        self.x_center_tolerance_slider = ctk.CTkSlider(x_center_frame, from_=0.0, to=50.0, number_of_steps=500, command=self.update_x_center_tolerance)
        self.x_center_tolerance_slider.grid(row=2, column=1, sticky="ew", padx=(10, 5), pady=2)
        self.x_center_tolerance_entry = ctk.CTkEntry(x_center_frame, width=60, justify="center", font=("Segoe UI", 11, "bold"), text_color=NEON)
        self.x_center_tolerance_entry.grid(row=2, column=2, padx=10, pady=(2, 8))
        self.x_center_tolerance_entry.insert(0, f"{config.x_center_tolerance_percent:.1f}")
        self.x_center_tolerance_entry.bind("<Return>", self.on_x_center_tolerance_entry_commit)
        self.x_center_tolerance_entry.bind("<FocusOut>", self.on_x_center_tolerance_entry_commit)
        
        # Target Switch Delay Section
        target_switch_frame = ctk.CTkFrame(settings_frame, fg_color="#2a2a2a", corner_radius=8)
        target_switch_frame.grid(row=11, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        target_switch_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(target_switch_frame, text="🔄 Target Switch Delay", font=("Segoe UI", 12, "bold"), text_color="#00e676").grid(row=0, column=0, columnspan=3, pady=(8, 5), padx=10, sticky="w")
        
        # Target Switch Delay
        ctk.CTkLabel(target_switch_frame, text="Switch Delay (ms)", font=("Segoe UI", 11), text_color="#fff").grid(row=1, column=0, sticky="w", padx=10, pady=2)
        self.target_switch_delay_slider = ctk.CTkSlider(target_switch_frame, from_=0, to=500, number_of_steps=100, command=self.update_target_switch_delay)
        self.target_switch_delay_slider.grid(row=1, column=1, sticky="ew", padx=(10, 5), pady=2)
        self.target_switch_delay_entry = ctk.CTkEntry(target_switch_frame, width=60, justify="center", font=("Segoe UI", 11, "bold"), text_color=NEON)
        self.target_switch_delay_entry.grid(row=1, column=2, padx=10, pady=(2, 8))
        self.target_switch_delay_entry.insert(0, f"{getattr(config, 'target_switch_delay_ms', 100)}")
        self.target_switch_delay_entry.bind("<Return>", self.on_target_switch_delay_entry_commit)
        self.target_switch_delay_entry.bind("<FocusOut>", self.on_target_switch_delay_entry_commit)
        

    def build_aimbot_mode(self, parent, row):
        """Aimbot mode selection"""
        frame = ctk.CTkFrame(parent, fg_color="#1a1a1a")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        
        ctk.CTkLabel(frame, text="⚡ Aimbot Mode", font=("Segoe UI", 16, "bold"), text_color="#00e676").grid(row=0, column=0, pady=(15, 10), padx=15, sticky="w")
        
        self.mode_var = ctk.StringVar(value=config.mode)
        mode_frame = ctk.CTkFrame(frame, fg_color="transparent")
        mode_frame.grid(row=1, column=0, padx=15, pady=(0, 15))
        
        for name in ["normal", "bezier", "silent", "smooth", "pid", "gan"]:
            display_name = "GAN" if name == "gan" else name.title()
            ctk.CTkRadioButton(
                mode_frame, 
                text=display_name, 
                variable=self.mode_var, 
                value=name, 
                command=self.update_mode, 
                text_color="#fff",
                font=("Segoe UI", 12, "bold")
            ).pack(side="left", padx=15)

    def build_smoothing_controls(self, parent, row):
        """Smoothing controls section"""
        frame = ctk.CTkFrame(parent, fg_color="#1a1a1a")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        frame.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(frame, text="🎯 Smoothing Controls", font=("Segoe UI", 16, "bold"), text_color="#00e676").grid(row=0, column=0, pady=(15, 10), padx=15, sticky="w")
        
        settings_frame = ctk.CTkFrame(frame, fg_color="transparent")
        settings_frame.grid(row=1, column=0, sticky="ew", padx=15, pady=(0, 15))
        settings_frame.grid_columnconfigure(1, weight=1)
        
        # X Smoothing
        ctk.CTkLabel(settings_frame, text="X Smoothing", font=("Segoe UI", 12, "bold"), text_color="#fff").grid(row=0, column=0, sticky="w", pady=5)
        self.in_game_sens_x_slider = ctk.CTkSlider(settings_frame, from_=0.1, to=20, number_of_steps=199, command=self.update_in_game_sens_x)
        self.in_game_sens_x_slider.grid(row=0, column=1, sticky="ew", padx=(10, 5), pady=5)
        self.in_game_sens_x_value = ctk.CTkLabel(settings_frame, text=f"{getattr(config, 'in_game_sens_x', config.in_game_sens):.2f}", font=("Segoe UI", 12, "bold"), text_color=NEON, width=50)
        self.in_game_sens_x_value.grid(row=0, column=2, pady=5)

        # Y Smoothing
        ctk.CTkLabel(settings_frame, text="Y Smoothing", font=("Segoe UI", 12, "bold"), text_color="#fff").grid(row=1, column=0, sticky="w", pady=5)
        self.in_game_sens_y_slider = ctk.CTkSlider(settings_frame, from_=0.1, to=20, number_of_steps=199, command=self.update_in_game_sens_y)
        self.in_game_sens_y_slider.grid(row=1, column=1, sticky="ew", padx=(10, 5), pady=5)
        self.in_game_sens_y_value = ctk.CTkLabel(settings_frame, text=f"{getattr(config, 'in_game_sens_y', config.in_game_sens):.2f}", font=("Segoe UI", 12, "bold"), text_color=NEON, width=50)
        self.in_game_sens_y_value.grid(row=1, column=2, pady=5)

        # Smoothing Sync Checkbox
        self.smoothing_sync_var = ctk.BooleanVar(value=bool(getattr(config, "smoothing_sync_enabled", False)))
        self.smoothing_sync_checkbox = ctk.CTkCheckBox(
            settings_frame, text="Sync", variable=self.smoothing_sync_var,
            command=self.on_smoothing_sync_toggle, font=("Segoe UI", 10, "bold")
        )
        self.smoothing_sync_checkbox.grid(row=0, column=3, rowspan=2, padx=(5, 10), pady=5)

    def build_rcs_settings(self, parent, row):
        """Build RCS (Recoil Control System) settings section"""
        frame = ctk.CTkFrame(parent, fg_color="#1a1a1a", corner_radius=8)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        frame.grid_columnconfigure(0, weight=1)
        
        # RCS Header with toggle
        header_frame = ctk.CTkFrame(frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=15, pady=(15, 5))
        header_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(header_frame, text="🎯 RCS (Recoil Control)", 
                    font=("Segoe UI", 16, "bold"), 
                    text_color="#00e676").grid(row=0, column=0, sticky="w")
        
        # RCS Enable Toggle
        self.rcs_enabled_switch = ctk.CTkSwitch(
            header_frame,
            text="Enable RCS",
            variable=self.rcs_enabled_var,
            command=self.on_rcs_enabled_toggle,
            text_color="#fff"
        )
        self.rcs_enabled_switch.grid(row=0, column=1, sticky="e")
        
        # ADS Only checkbox
        self.rcs_ads_only_checkbox = ctk.CTkCheckBox(
            header_frame,
            text="ADS Only",
            variable=self.rcs_ads_only_var,
            command=self.on_rcs_ads_only_toggle,
            text_color="#fff",
            font=("Segoe UI", 11)
        )
        self.rcs_ads_only_checkbox.grid(row=1, column=1, sticky="e", pady=(5, 0))
        
        # RCS Settings Frame
        settings_frame = ctk.CTkFrame(frame, fg_color="#2a2a2a", corner_radius=8)
        settings_frame.grid(row=1, column=0, sticky="ew", padx=15, pady=(5, 15))
        settings_frame.grid_columnconfigure(1, weight=1)
        
        # X-Axis Recoil Compensation
        ctk.CTkLabel(settings_frame, text="🔽 X-Axis Compensation", 
                    font=("Segoe UI", 12, "bold"), 
                    text_color="#00e676").grid(row=0, column=0, columnspan=3, pady=(10, 5), padx=10, sticky="w")
        
        # X-Axis Strength
        ctk.CTkLabel(settings_frame, text="Strength", 
                    font=("Segoe UI", 11, "bold"), 
                    text_color="#fff").grid(row=1, column=0, sticky="w", padx=10, pady=2)
        self.rcs_x_strength_slider = ctk.CTkSlider(settings_frame, from_=0.1, to=5.0, 
                                                  number_of_steps=490, command=self.update_rcs_x_strength)
        self.rcs_x_strength_slider.grid(row=1, column=1, sticky="ew", padx=(10, 5), pady=2)
        self.rcs_x_strength_entry = ctk.CTkEntry(settings_frame, width=60, justify="center", 
                                                font=("Segoe UI", 11, "bold"), text_color=NEON)
        self.rcs_x_strength_entry.grid(row=1, column=2, padx=10, pady=2)
        self.rcs_x_strength_entry.insert(0, f"{config.rcs_x_strength:.2f}")
        self.rcs_x_strength_entry.bind("<Return>", self.on_rcs_x_strength_entry_commit)
        self.rcs_x_strength_entry.bind("<FocusOut>", self.on_rcs_x_strength_entry_commit)
        
        # X-Axis Delay
        ctk.CTkLabel(settings_frame, text="Delay (ms)", 
                    font=("Segoe UI", 11, "bold"), 
                    text_color="#fff").grid(row=2, column=0, sticky="w", padx=10, pady=2)
        self.rcs_x_delay_slider = ctk.CTkSlider(settings_frame, from_=1, to=100, 
                                               number_of_steps=99, command=self.update_rcs_x_delay)
        self.rcs_x_delay_slider.grid(row=2, column=1, sticky="ew", padx=(10, 5), pady=2)
        self.rcs_x_delay_entry = ctk.CTkEntry(settings_frame, width=60, justify="center", 
                                             font=("Segoe UI", 11, "bold"), text_color=NEON)
        self.rcs_x_delay_entry.grid(row=2, column=2, padx=10, pady=2)
        self.rcs_x_delay_entry.insert(0, f"{int(config.rcs_x_delay * 1000)}")
        self.rcs_x_delay_entry.bind("<Return>", self.on_rcs_x_delay_entry_commit)
        self.rcs_x_delay_entry.bind("<FocusOut>", self.on_rcs_x_delay_entry_commit)
        
        # Y-Axis Random Jitter Section
        ctk.CTkLabel(settings_frame, text="↔️ Y-Axis Random Jitter", 
                    font=("Segoe UI", 12, "bold"), 
                    text_color="#00e676").grid(row=3, column=0, columnspan=3, pady=(15, 5), padx=10, sticky="w")
        
        # Y-Axis Random Enable
        self.rcs_y_random_switch = ctk.CTkSwitch(
            settings_frame,
            text="Enable Y-Axis Random Jitter",
            variable=self.rcs_y_random_enabled_var,
            command=self.on_rcs_y_random_toggle,
            text_color="#fff"
        )
        self.rcs_y_random_switch.grid(row=4, column=0, columnspan=3, sticky="w", padx=10, pady=(5, 5))
        
        # Y-Axis Random Strength
        ctk.CTkLabel(settings_frame, text="Jitter Strength", 
                    font=("Segoe UI", 11, "bold"), 
                    text_color="#fff").grid(row=5, column=0, sticky="w", padx=10, pady=2)
        self.rcs_y_strength_slider = ctk.CTkSlider(settings_frame, from_=0.1, to=3.0, 
                                                  number_of_steps=290, command=self.update_rcs_y_strength)
        self.rcs_y_strength_slider.grid(row=5, column=1, sticky="ew", padx=(10, 5), pady=2)
        self.rcs_y_strength_entry = ctk.CTkEntry(settings_frame, width=60, justify="center", 
                                                font=("Segoe UI", 11, "bold"), text_color=NEON)
        self.rcs_y_strength_entry.grid(row=5, column=2, padx=10, pady=2)
        self.rcs_y_strength_entry.insert(0, f"{config.rcs_y_random_strength:.2f}")
        self.rcs_y_strength_entry.bind("<Return>", self.on_rcs_y_strength_entry_commit)
        self.rcs_y_strength_entry.bind("<FocusOut>", self.on_rcs_y_strength_entry_commit)
        
        # Y-Axis Random Delay
        ctk.CTkLabel(settings_frame, text="Jitter Delay (ms)", 
                    font=("Segoe UI", 11, "bold"), 
                    text_color="#fff").grid(row=6, column=0, sticky="w", padx=10, pady=(2, 10))
        self.rcs_y_delay_slider = ctk.CTkSlider(settings_frame, from_=1, to=100, 
                                               number_of_steps=99, command=self.update_rcs_y_delay)
        self.rcs_y_delay_slider.grid(row=6, column=1, sticky="ew", padx=(10, 5), pady=(2, 10))
        self.rcs_y_delay_entry = ctk.CTkEntry(settings_frame, width=60, justify="center", 
                                             font=("Segoe UI", 11, "bold"), text_color=NEON)
        self.rcs_y_delay_entry.grid(row=6, column=2, padx=10, pady=(2, 10))
        self.rcs_y_delay_entry.insert(0, f"{int(config.rcs_y_random_delay * 1000)}")
        self.rcs_y_delay_entry.bind("<Return>", self.on_rcs_y_delay_entry_commit)
        self.rcs_y_delay_entry.bind("<FocusOut>", self.on_rcs_y_delay_entry_commit)
        
        # RCS Sync Checkboxes
        self.rcs_strength_sync_var = ctk.BooleanVar(value=bool(getattr(config, "rcs_strength_sync_enabled", False)))
        self.rcs_strength_sync_checkbox = ctk.CTkCheckBox(
            settings_frame, text="Sync", variable=self.rcs_strength_sync_var,
            command=self.on_rcs_strength_sync_toggle, font=("Segoe UI", 10, "bold")
        )
        self.rcs_strength_sync_checkbox.grid(row=1, column=3, rowspan=1, padx=(5, 10), pady=2)
        
        self.rcs_delay_sync_var = ctk.BooleanVar(value=bool(getattr(config, "rcs_delay_sync_enabled", False)))
        self.rcs_delay_sync_checkbox = ctk.CTkCheckBox(
            settings_frame, text="Sync", variable=self.rcs_delay_sync_var,
            command=self.on_rcs_delay_sync_toggle, font=("Segoe UI", 10, "bold")
        )
        self.rcs_delay_sync_checkbox.grid(row=2, column=3, rowspan=1, padx=(5, 10), pady=2)
        
        # Initialize slider values
        self.rcs_x_strength_slider.set(config.rcs_x_strength)
        self.rcs_x_delay_slider.set(config.rcs_x_delay * 1000)  # Convert to ms
        self.rcs_y_strength_slider.set(config.rcs_y_random_strength)
        self.rcs_y_delay_slider.set(config.rcs_y_random_delay * 1000)  # Convert to ms

    def build_model_settings(self, parent, row):
        """AI Model configuration"""
        frame = ctk.CTkFrame(parent, fg_color="#1a1a1a")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        frame.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(frame, text="🤖 AI Model", font=("Segoe UI", 16, "bold"), text_color="#00e676").grid(row=0, column=0, pady=(15, 10), padx=15, sticky="w")
        
        model_controls = ctk.CTkFrame(frame, fg_color="transparent")
        model_controls.grid(row=1, column=0, sticky="ew", padx=15, pady=(0, 10))
        model_controls.grid_columnconfigure(0, weight=1)
        
        self.model_menu = ctk.CTkOptionMenu(model_controls, values=self.get_model_list(), command=self.select_model)
        self.model_menu.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        
        neon_button(model_controls, text="Reload", command=self.reload_model, width=80).grid(row=0, column=1)
        
        # Class display
        ctk.CTkLabel(frame, text="Available Classes:", font=("Segoe UI", 12, "bold"), text_color="#fff").grid(row=2, column=0, sticky="w", padx=15, pady=(10, 5))
        
        self.class_listbox = ctk.CTkTextbox(frame, height=80, fg_color="#2a2a2a", text_color="#fff", font=("Segoe UI", 11))
        self.class_listbox.grid(row=3, column=0, sticky="ew", padx=15, pady=(0, 15))

    def build_class_selection(self, parent, row):
        """Target class selection"""
        frame = ctk.CTkFrame(parent, fg_color="#1a1a1a")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(frame, text="🎯 Target Classes", font=("Segoe UI", 16, "bold"), text_color="#00e676").grid(row=0, column=0, columnspan=2, pady=(15, 10), padx=15, sticky="w")
        
        ctk.CTkLabel(frame, text="Player Class:", font=("Segoe UI", 12, "bold"), text_color="#fff").grid(row=1, column=0, sticky="w", padx=15, pady=5)
        self.player_class_var = ctk.StringVar(value=config.custom_player_label)
        self.player_class_menu = ctk.CTkOptionMenu(frame, values=self.get_available_classes(), variable=self.player_class_var, command=self.set_player_class)
        self.player_class_menu.grid(row=1, column=1, sticky="ew", padx=15, pady=5)
        
        ctk.CTkLabel(frame, text="Head Class:", font=("Segoe UI", 12, "bold"), text_color="#fff").grid(row=2, column=0, sticky="w", padx=15, pady=5)
        self.head_class_var = ctk.StringVar(value=config.custom_head_label or "None")
        self.head_class_menu = ctk.CTkOptionMenu(frame, values=["None"] + self.get_available_classes(), variable=self.head_class_var, command=self.set_head_class)
        self.head_class_menu.grid(row=2, column=1, sticky="ew", padx=15, pady=(5, 15))

    def build_profile_controls(self, parent, row):
        """Advanced Profile Management with ConfigManager"""
        frame = ctk.CTkFrame(parent, fg_color="#1a1a1a")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        frame.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(frame, text="💾 Profile Management", font=("Segoe UI", 16, "bold"), text_color="#00e676").grid(row=0, column=0, pady=(15, 10), padx=15, sticky="w")
        
        # Profile selection section
        selection_frame = ctk.CTkFrame(frame, fg_color="transparent")
        selection_frame.grid(row=1, column=0, sticky="ew", padx=15, pady=(0, 10))
        selection_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(selection_frame, text="Current Profile:", font=("Segoe UI", 12, "bold"), text_color="#fff").grid(row=0, column=0, sticky="w", pady=5)
        
        self.profile_var = ctk.StringVar(value=self.current_config_name.get())
        self.profile_menu = ctk.CTkOptionMenu(
            selection_frame, 
            values=self.get_profile_list(), 
            variable=self.profile_var,
            command=self.on_profile_select,
            width=200
        )
        self.profile_menu.grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=5)
        
        # Profile action buttons - Row 1
        btn_frame1 = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame1.grid(row=2, column=0, padx=15, pady=(0, 5))
        
        neon_button(btn_frame1, text="📁 Create New", command=self.create_profile_dialog, width=100).pack(side="left", padx=(0, 5))
        ctk.CTkButton(btn_frame1, text="✏️ Rename", command=self.rename_profile_dialog, width=100, fg_color="#333").pack(side="left", padx=(0, 5))
        ctk.CTkButton(btn_frame1, text="🗑️ Delete", command=self.delete_profile_dialog, width=100, fg_color="#d32f2f").pack(side="left", padx=(0, 5))
        
        # Profile action buttons - Row 2
        btn_frame2 = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame2.grid(row=3, column=0, padx=15, pady=(0, 15))
        
        ctk.CTkButton(btn_frame2, text="💾 Save Current", command=self.save_current_profile, width=100, fg_color="#2e7d32").pack(side="left", padx=(0, 5))
        ctk.CTkButton(btn_frame2, text="📂 Load Selected", command=self.load_selected_profile, width=100, fg_color="#1976d2").pack(side="left", padx=(0, 5))
        ctk.CTkButton(btn_frame2, text="🔄 Reset Defaults", command=self.reset_defaults, width=100, fg_color="#333").pack(side="left")

    def build_main_controls(self, parent, row):
        """Main aimbot controls"""
        frame = ctk.CTkFrame(parent, fg_color="#1a1a1a")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        
        ctk.CTkLabel(frame, text="🚀 Aimbot Controls", font=("Segoe UI", 16, "bold"), text_color="#00e676").grid(row=0, column=0, pady=(15, 10), padx=15, sticky="w")
        
        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.grid(row=1, column=0, padx=15, pady=(0, 15))
        
        neon_button(btn_frame, text="🎯 START AIMBOT", command=self.start_aimbot, width=150, height=45, font=("Segoe UI", 14, "bold")).pack(side="left", padx=(0, 15))
        ctk.CTkButton(btn_frame, text="⏹ STOP", command=self.stop_aimbot, width=100, height=45, fg_color="#333", font=("Segoe UI", 14, "bold")).pack(side="left")

    def build_footer(self):
        """Footer with credits"""
        footer = ctk.CTkFrame(self.main_frame, fg_color="transparent", height=40)
        footer.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        footer.grid_propagate(False)
        
        ctk.CTkLabel(
            footer,
            text="Made with ♥ by Ahmo934 and Jealousyhaha for Makcu Community",
            font=("Segoe UI", 12, "bold"),
            text_color=NEON
        ).pack(expand=True)

    def on_window_resize(self, event):
        """Handle window resize events for responsive layout"""
        if event.widget == self:
            width = self.winfo_width()
            
            # Switch to single column layout on smaller screens
            if width < 1200:
                self.switch_to_single_column()
            else:
                self.switch_to_two_column()

    def switch_to_single_column(self):
        """Switch to single column layout for smaller screens"""
        if hasattr(self, '_is_single_column') and self._is_single_column:
            return
            
        self._is_single_column = True
        
        # Reconfigure content frame
        self.content_frame.grid_columnconfigure(1, weight=0)
        
        # Move right column content to left column
        for widget in self.right_column.winfo_children():
            widget.grid_forget()
        
        self.right_column.grid_forget()
        self.left_column.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=0)

    def switch_to_two_column(self):
        """Switch to two column layout for larger screens"""
        if hasattr(self, '_is_single_column') and not self._is_single_column:
            return
            
        self._is_single_column = False
        
        # Reconfigure content frame
        self.content_frame.grid_columnconfigure(1, weight=1)
        
        # Restore two column layout
        self.left_column.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        self.right_column.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        
        # Rebuild right column if needed
        if not self.right_column.winfo_children():
            self.build_right_column()

    def on_connect(self):
        """Enhanced connection with visual feedback"""
        Mouse.cleanup()  # Ensure mouse is clean before connecting
        if connect_to_makcu():
            config.makcu_connected = True
            config.makcu_status_msg = "Connected"
            self.connection_status.set("Connected")
            self.connection_color.set("#00FF00")
            self.conn_indicator.configure(fg_color="#00FF00")
            self.error_text.set("✅ MAKCU device connected successfully!")
        else:
            config.makcu_connected = False
            config.makcu_status_msg = "Connection Failed"
            self.connection_status.set("Disconnected")
            self.connection_color.set("#b71c1c")
            self.conn_indicator.configure(fg_color="#b71c1c")
            self.error_text.set("❌ Failed to connect to MAKCU device")
        
        self.conn_status_lbl.configure(text_color=self.connection_color.get())

    def _poll_connection_status(self):
        """Enhanced status polling with visual updates"""
        if config.makcu_connected:
            self.connection_status.set("Connected")
            self.connection_color.set("#00FF00")
            self.conn_indicator.configure(fg_color="#00FF00")
        else:
            self.connection_status.set("Disconnected")
            self.connection_color.set("#b71c1c")
            self.conn_indicator.configure(fg_color="#b71c1c")
        
        self.conn_status_lbl.configure(text_color=self.connection_color.get())
        self.after(500, self._poll_connection_status)

    # Include all the callback methods from gui_callbacks.py
    def refresh_all(self):
        # Initialize FOV X and Y controls
        try:
            self.fov_x_slider.set(getattr(config, "fov_x_size", config.region_size))
            self._set_entry_text(self.fov_x_entry, str(getattr(config, "fov_x_size", config.region_size)))
            self.fov_y_slider.set(getattr(config, "fov_y_size", config.region_size))
            self._set_entry_text(self.fov_y_entry, str(getattr(config, "fov_y_size", config.region_size)))
            
            # Initialize sync variables
            if hasattr(self, 'fov_sync_var'):
                self.fov_sync_var.set(bool(getattr(config, "fov_sync_enabled", False)))
        except Exception:
            pass  # FOV X/Y controls may not exist yet during initial setup
        
        # Initialize height targeting controls
        try:
            # Update height targeting main toggle
            self.height_targeting_var.set(bool(getattr(config, "height_targeting_enabled", True)))
            self.target_height_slider.set(config.target_height)
            self._set_entry_text(self.target_height_entry, f"{config.target_height:.3f}")
            self.height_deadzone_var.set(bool(getattr(config, "height_deadzone_enabled", True)))
            self.deadzone_min_slider.set(config.height_deadzone_min)
            self._set_entry_text(self.deadzone_min_entry, f"{config.height_deadzone_min:.3f}")
            self.deadzone_max_slider.set(config.height_deadzone_max)
            self._set_entry_text(self.deadzone_max_entry, f"{config.height_deadzone_max:.3f}")
            self.deadzone_tolerance_slider.set(config.height_deadzone_tolerance)
            self._set_entry_text(self.deadzone_tolerance_entry, f"{config.height_deadzone_tolerance:.1f}")
            
            # Update control states based on height targeting toggle
            height_state = "normal" if config.height_targeting_enabled else "disabled"
            self.target_height_slider.configure(state=height_state)
            self.target_height_entry.configure(state=height_state)
            self.height_deadzone_switch.configure(state=height_state)
            
            # Update control states based on deadzone toggle (only if height targeting is enabled)
            deadzone_state = "normal" if (config.height_targeting_enabled and config.height_deadzone_enabled) else "disabled"
            self.deadzone_min_slider.configure(state=deadzone_state)
            self.deadzone_max_slider.configure(state=deadzone_state)
            self.deadzone_tolerance_slider.configure(state=deadzone_state)
            self.deadzone_min_entry.configure(state=deadzone_state)
            self.deadzone_max_entry.configure(state=deadzone_state)
            self.deadzone_tolerance_entry.configure(state=deadzone_state)
        except Exception:
            pass  # Height controls may not exist yet during initial setup
        
        # Initialize X-center targeting controls
        try:
            self.x_center_targeting_var.set(bool(getattr(config, "x_center_targeting_enabled", False)))
            self.x_center_tolerance_slider.set(config.x_center_tolerance_percent)
            self._set_entry_text(self.x_center_tolerance_entry, f"{config.x_center_tolerance_percent:.1f}")
        except Exception:
            pass  # X-center controls may not exist yet during initial setup
        
        # Initialize mouse movement multiplier controls
        try:
            # Mouse movement sync and X/Y multipliers
            self.mouse_movement_sync_var.set(getattr(config, "mouse_movement_sync_enabled", False))
            self.mouse_multiplier_x_slider.set(getattr(config, 'mouse_movement_multiplier_x', 1.0))
            self._set_entry_text(self.mouse_multiplier_x_entry, f"{getattr(config, 'mouse_movement_multiplier_x', 1.0):.2f}")
            self.mouse_multiplier_y_slider.set(getattr(config, 'mouse_movement_multiplier_y', 1.0))
            self._set_entry_text(self.mouse_multiplier_y_entry, f"{getattr(config, 'mouse_movement_multiplier_y', 1.0):.2f}")
            
            # Movement enable/disable toggles
            self.mouse_movement_x_enabled_var.set(getattr(config, "mouse_movement_enabled_x", True))
            self.mouse_movement_y_enabled_var.set(getattr(config, "mouse_movement_enabled_y", True))
        except Exception:
            pass  # Mouse multiplier controls may not exist yet during initial setup
        
        # Initialize enhanced silent mode controls
        try:
            self.silent_strength_slider.set(config.silent_strength)
            self._set_entry_text(self.silent_strength_entry, f"{config.silent_strength:.3f}")
            self.silent_auto_fire_var.set(bool(getattr(config, "silent_auto_fire", False)))
            self.silent_speed_mode_var.set(bool(getattr(config, "silent_speed_mode", True)))
            self.silent_use_bezier_var.set(bool(getattr(config, "silent_use_bezier", False)))
            self.silent_fire_delay_slider.set(config.silent_fire_delay)
            self._set_entry_text(self.silent_fire_delay_entry, f"{config.silent_fire_delay:.3f}")
            self.silent_return_delay_slider.set(config.silent_return_delay)
            self._set_entry_text(self.silent_return_delay_entry, f"{config.silent_return_delay:.3f}")
        except Exception:
            pass  # Silent controls may not exist yet during initial setup
        self.offset_slider.set(config.player_y_offset)
        self.offset_value.configure(text=str(config.player_y_offset))
        self.btn_var.set(config.selected_mouse_button)
        self.mode_var.set(config.mode)
        self.model_name.set(os.path.basename(config.model_path))
        self.model_menu.set(os.path.basename(config.model_path))
        self.model_size.set(get_model_size(config.model_path))
        self.aimbot_status.set("Running" if is_aimbot_running() else "Stopped")
        self.conf_slider.set(config.conf)
        self._set_entry_text(self.conf_entry, f"{config.conf:.2f}")
        
        # Initialize X and Y smoothing controls
        try:
            self.in_game_sens_x_slider.set(getattr(config, "in_game_sens_x", config.in_game_sens))
            self.in_game_sens_x_value.configure(text=f"{getattr(config, 'in_game_sens_x', config.in_game_sens):.2f}")
            self.in_game_sens_y_slider.set(getattr(config, "in_game_sens_y", config.in_game_sens))
            self.in_game_sens_y_value.configure(text=f"{getattr(config, 'in_game_sens_y', config.in_game_sens):.2f}")
            
            # Initialize smoothing sync variable
            if hasattr(self, 'smoothing_sync_var'):
                self.smoothing_sync_var.set(bool(getattr(config, "smoothing_sync_enabled", False)))
        except Exception:
            pass  # X/Y smoothing controls may not exist yet during initial setup
        self.always_on_var.set(bool(getattr(config, "always_on_aim", False)))
        self.imgsz_slider.set(config.imgsz)
        self._set_entry_text(self.imgsz_entry, str(config.imgsz))
        self.max_detect_slider.set(config.max_detect)
        self.max_detect_label.configure(text=str(config.max_detect))
        self.load_class_list()
        self.update_dynamic_frame()
        self.debug_checkbox_var.set(config.show_debug_window)
        
        try:
            self.debug_text_info_var.set(bool(getattr(config, "show_debug_text_info", True)))
            self.debug_always_on_top_var.set(bool(getattr(config, "debug_always_on_top", False)))
            self._update_debug_text_info_visibility()
        except Exception:
            pass  # Debug controls may not exist yet during initial setup
        
        # Initialize profile management
        try:
            self.refresh_profile_list()
            # Ensure triggerbot dynamic frame is updated
            self.update_triggerbot_dynamic_frame()
        except Exception:
            pass  # Profile controls may not exist yet during initial setup
        self.input_check_var.set(False)
        
        # Ensure button masking values are properly loaded from config
        aim_mask_value = bool(getattr(config, "aim_button_mask", False))
        trigger_mask_value = bool(getattr(config, "trigger_button_mask", False))
        
        self.aim_button_mask_var.set(aim_mask_value)
        self.trigger_button_mask_var.set(trigger_mask_value)
        
        # Call the toggle callbacks to ensure functionality is properly initialized
        # This ensures the button masking actually works, not just the GUI state
        self.on_aim_button_mask_toggle()
        self.on_trigger_button_mask_toggle()
        
        # Debug: Print button masking values after refresh
        # Debug: After refresh_all status (removed for cleaner output)
        self.capture_mode_var.set(config.capturer_mode.upper())
        self.capture_mode_menu.set(config.capturer_mode.upper())
        self.trigger_enabled_var.set(bool(getattr(config, "trigger_enabled", False)))
        self.trigger_always_on_var.set(bool(getattr(config, "trigger_always_on", False)))
        self.trigger_btn_var.set(int(getattr(config, "trigger_button", 0)))

        # Update new triggerbot mode variables
        self.trigger_mode_var.set(getattr(config, "trigger_mode", "normal"))
        
        # Update trigger detection method
        try:
            method = getattr(config, "trigger_detection_method", "ai")
            self.trigger_detection_method_var.set(method.upper())
            self.trigger_detection_method_menu.set(method.upper())
        except Exception:
            pass  # Detection method controls may not exist yet during initial setup

        # Update color outline filter
        try:
            self.outline_filter_var.set(config.color_outline_filter_enabled)
        except Exception:
            pass  # Outline filter controls may not exist yet during initial setup
        self.spray_initial_delay_ms_var.set(int(getattr(config, "spray_initial_delay_ms", 50)))
        self.spray_cooldown_ms_var.set(int(getattr(config, "spray_cooldown_ms", 80)))
        self.burst_shots_var.set(int(getattr(config, "burst_shots", 3)))
        self.burst_delay_ms_var.set(int(getattr(config, "burst_delay_ms", 40)))
        self.burst_cooldown_ms_var.set(int(getattr(config, "burst_cooldown_ms", 200)))
        self.burst_hold_duration_ms_var.set(int(getattr(config, "burst_hold_duration_ms", 500)))
        self.target_switch_delay_ms_var.set(int(getattr(config, "target_switch_delay_ms", 100)))
        
        # Update normal mode shot delay
        try:
            if hasattr(self, 'normal_shot_delay_label'):
                normal_shot_delay = int(getattr(config, "normal_shot_delay_ms", 50))
                self.normal_shot_delay_label.configure(text=str(normal_shot_delay))
        except Exception:
            pass  # Normal shot delay label may not exist yet during initial setup
        
        # Update normal mode taps delay and cooldown labels
        try:
            if hasattr(self, 'taps_delay_label'):
                self.taps_delay_label.configure(text=str(config.trigger_delay_ms))
            if hasattr(self, 'taps_cooldown_label'):
                self.taps_cooldown_label.configure(text=str(config.trigger_cooldown_ms))
        except Exception:
            pass  # Taps labels may not exist yet during initial setup
        
        # Update burst mode hold duration label
        try:
            if hasattr(self, 'burst_hold_duration_label'):
                burst_hold_duration = int(getattr(config, "burst_hold_duration_ms", 500))
                self.burst_hold_duration_label.configure(text=str(burst_hold_duration))
        except Exception:
            pass  # Burst hold duration label may not exist yet during initial setup
        
        # Update target switch delay
        try:
            if hasattr(self, 'target_switch_delay_entry'):
                target_switch_delay = int(getattr(config, "target_switch_delay_ms", 100))
                self.target_switch_delay_slider.set(target_switch_delay)
                self.target_switch_delay_entry.delete(0, "end")
                self.target_switch_delay_entry.insert(0, str(target_switch_delay))
        except Exception:
            pass  # Target switch delay controls may not exist yet during initial setup

        # Update secondary aim settings
        try:
            self.secondary_aim_enabled_var.set(bool(getattr(config, "secondary_aim_enabled", False)))
            self.secondary_aim_button_var.set(int(getattr(config, "secondary_aim_button", 2)))
        except Exception:
            pass  # Secondary aim controls may not exist yet during initial setup

        # Update aiming axis toggles
        self.normal_enable_x_var.set(bool(getattr(config, "normal_enable_x", True)))
        self.normal_enable_y_var.set(bool(getattr(config, "normal_enable_y", True)))
        self.bezier_enable_x_var.set(bool(getattr(config, "bezier_enable_x", True)))
        self.bezier_enable_y_var.set(bool(getattr(config, "bezier_enable_y", True)))
        self.silent_enable_x_var.set(bool(getattr(config, "silent_enable_x", True)))
        self.silent_enable_y_var.set(bool(getattr(config, "silent_enable_y", True)))
        self.smooth_enable_x_var.set(bool(getattr(config, "smooth_enable_x", True)))
        self.smooth_enable_y_var.set(bool(getattr(config, "smooth_enable_y", True)))

        # Update RCS variables
        self.rcs_enabled_var.set(bool(getattr(config, "rcs_enabled", False)))
        self.rcs_ads_only_var.set(bool(getattr(config, "rcs_ads_only", False)))
        self.rcs_y_random_enabled_var.set(bool(getattr(config, "rcs_y_random_enabled", False)))
        
        # Update RCS slider and entry values
        try:
            self.rcs_x_strength_slider.set(config.rcs_x_strength)
            self.rcs_x_strength_entry.delete(0, "end")
            self.rcs_x_strength_entry.insert(0, f"{config.rcs_x_strength:.2f}")
            self.rcs_x_delay_slider.set(config.rcs_x_delay * 1000)  # Convert to ms
            self.rcs_x_delay_entry.delete(0, "end")
            self.rcs_x_delay_entry.insert(0, f"{int(config.rcs_x_delay * 1000)}")
            self.rcs_y_strength_slider.set(config.rcs_y_random_strength)
            self.rcs_y_strength_entry.delete(0, "end")
            self.rcs_y_strength_entry.insert(0, f"{config.rcs_y_random_strength:.2f}")
            self.rcs_y_delay_slider.set(config.rcs_y_random_delay * 1000)  # Convert to ms
            self.rcs_y_delay_entry.delete(0, "end")
            self.rcs_y_delay_entry.insert(0, f"{int(config.rcs_y_random_delay * 1000)}")
            
            # Initialize RCS sync variables
            if hasattr(self, 'rcs_strength_sync_var'):
                self.rcs_strength_sync_var.set(bool(getattr(config, "rcs_strength_sync_enabled", False)))
            if hasattr(self, 'rcs_delay_sync_var'):
                self.rcs_delay_sync_var.set(bool(getattr(config, "rcs_delay_sync_enabled", False)))
        except Exception:
            pass  # RCS controls may not exist yet during initial setup

        # Update triggerbot settings (after all trigger variables are set)
        try:
            # Update trigger widget states first
            self._update_trigger_widgets_state()
            # Then set the values from config
            self.tb_radius_entry.delete(0,"end"); self.tb_radius_entry.insert(0, str(config.trigger_radius_px))
            self.tb_delay_entry.delete(0,"end");  self.tb_delay_entry.insert(0, str(config.trigger_delay_ms))
            self.tb_cd_entry.delete(0,"end");     self.tb_cd_entry.insert(0, str(config.trigger_cooldown_ms))
            self.tb_conf_entry.delete(0,"end");   self.tb_conf_entry.insert(0, f"{config.trigger_min_conf:.2f}")
        except Exception:
            pass  

        # NDI source menu initial state
        try:
            self.ndi_source_menu.configure(values=self._ndi_menu_values())
            if isinstance(config.ndi_selected_source, str) and \
            config.ndi_selected_source in self._ndi_menu_values():
                self.ndi_source_var.set(config.ndi_selected_source)
            elif self._ndi_menu_values():
                self.ndi_source_var.set(self._ndi_menu_values()[0])
        except Exception:
            pass

        self._update_ndi_controls_state()

        # Main PC resolution entries
        try:
            self.main_res_w_entry.delete(0, "end"); self.main_res_w_entry.insert(0, str(config.main_pc_width))
            self.main_res_h_entry.delete(0, "end"); self.main_res_h_entry.insert(0, str(config.main_pc_height))
        except Exception:
            pass


    def on_capture_mode_change(self, value: str):
        m = {"CaptureCard": "capturecard", "NDI": "ndi", "DXGI": "dxgi", "UDP": "udp"}
        internal = m.get((value or "").upper(), "capturecard")
        if config.capturer_mode != internal:
            config.capturer_mode = internal
            self.error_text.set(f"🔁 Capture method set to: {value}")
            self._update_ndi_controls_state()
            self._update_udp_controls_state()
            if is_aimbot_running():
                stop_aimbot(); start_aimbot()
            config.save()
        else:
            self._update_ndi_controls_state()

    def on_ndi_source_change(self, value: str):
        if self.capture_mode_var.get().upper() != "NDI":
            return
        if value and not value.startswith("("):
            config.ndi_selected_source = value
            self.ndi_source_var.set(value)
            try:
                self.ndi_source_menu.set(value)
            except Exception:
                pass
            self.error_text.set(f"🔁 NDI source: {value}")
            config.save()

    def update_fov(self, val):
        """Called by the slider."""
        if self._updating_fov:
            return
        self._apply_fov(int(round(val)), source="slider")

    def on_fov_entry_commit(self, event=None):
        """Called when user presses Enter or leaves the entry."""
        try:
            val = int(self.fov_entry.get().strip())
        except Exception:
            # revert to current config if invalid
            self._set_entry_text(self.fov_entry, str(config.region_size))
            return
        self._apply_fov(val, source="entry")

    def _apply_fov(self, value, source="code"):
        MIN_FOV, MAX_FOV = 20, 500
        value = max(MIN_FOV, min(MAX_FOV, int(value)))

        # prevent recursion loops
        self._updating_fov = True
        try:
            config.region_size = value
            # keep slider and entry in sync
            if source != "slider":
                self.fov_slider.set(value)
            if source != "entry":
                self._set_entry_text(self.fov_entry, str(value))
        finally:
            self._updating_fov = False

    def on_trigger_enabled_toggle(self):
        config.trigger_enabled = bool(self.trigger_enabled_var.get())
        self._update_trigger_widgets_state()
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save trigger_enabled: {e}")

    def on_trigger_always_on_toggle(self):
        config.trigger_always_on = bool(self.trigger_always_on_var.get())
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save trigger_always_on: {e}")

    def update_trigger_button(self):
        config.trigger_button = int(self.trigger_btn_var.get())
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save trigger_button: {e}")

    def _update_trigger_widgets_state(self):
        state = "normal" if self.trigger_enabled_var.get() else "disabled"
        try:
            # Update state only - values will be set by refresh_all after this
            self.tb_radius_entry.configure(state=state)
            self.tb_delay_entry.configure(state=state)
            self.tb_cd_entry.configure(state=state)
            self.tb_conf_entry.configure(state=state)
        except Exception:
            pass

    def update_offset(self, val):
        config.player_y_offset = int(round(val))
        self.offset_value.configure(text=str(config.player_y_offset))
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save player_y_offset: {e}")

    def update_mouse_btn(self):
        config.selected_mouse_button = self.btn_var.get()
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save selected_mouse_button: {e}")

    def update_mode(self):
        old_mode = config.mode
        config.mode = self.mode_var.get()
        # Debug: Mode changed (removed for cleaner output)
        self.update_dynamic_frame()

    def update_conf(self, val):
        """Called by the slider."""
        if getattr(self, "_updating_conf", False):
            return
        self._apply_conf(float(val), source="slider")

    def on_conf_entry_commit(self, event=None):
        """Called when user presses Enter or leaves the entry."""
        raw = self.conf_entry.get().strip()
        # allow ".3" style
        if raw.startswith("."):
            raw = "0" + raw
        try:
            val = float(raw)
        except Exception:
            # revert to current config if invalid
            self._set_entry_text(self.conf_entry, f"{config.conf:.2f}")
            return
        self._apply_conf(val, source="entry")

    def _apply_conf(self, value, source="code"):
        MIN_C, MAX_C = 0.05, 0.95
        # clamp and round to 2 decimals
        value = max(MIN_C, min(MAX_C, float(value)))
        value = round(value, 2)

        self._updating_conf = True
        try:
            config.conf = value
            # keep slider and entry in sync
            if source != "slider":
                self.conf_slider.set(value)
            if source != "entry":
                self._set_entry_text(self.conf_entry, f"{value:.2f}")
        finally:
            self._updating_conf = False

    def _set_entry_text(self, entry, text):
        entry.delete(0, "end")
        entry.insert(0, text)


    def update_imgsz(self, val):
        """Called by the slider."""
        if self._updating_imgsz:
            return
        self._apply_imgsz(int(round(float(val))), source="slider")

    def on_imgsz_entry_commit(self, event=None):
        """Called when user presses Enter or leaves the entry."""
        raw = self.imgsz_entry.get().strip()
        try:
            val = int(raw)
        except Exception:
            # revert to current config if invalid
            self._set_entry_text(self.imgsz_entry, str(config.imgsz))
            return
        self._apply_imgsz(val, source="entry")

    def _snap_to_multiple(self, value, base=32):
        """Snap to nearest multiple of 'base' (YOLO-friendly)."""
        if base <= 1:
            return value
        down = (value // base) * base
        up = down + base
        # choose nearest; prefer 'up' on ties
        return up if (value - down) >= (up - value) else down

    def _apply_imgsz(self, value, source="code"):
        MIN_S, MAX_S = 128, 1280
        value = max(MIN_S, min(MAX_S, int(value)))
        value = self._snap_to_multiple(value, base=32)

        self._updating_imgsz = True
        try:
            config.imgsz = value
            # keep slider and entry in sync
            if source != "slider":
                self.imgsz_slider.set(value)
            if source != "entry":
                self._set_entry_text(self.imgsz_entry, str(value))
        finally:
            self._updating_imgsz = False

    def update_max_detect(self, val):
        val = int(round(float(val)))
        config.max_detect = val
        self.max_detect_label.configure(text=str(val))

    def on_always_on_toggle(self):
        value = bool(self.always_on_var.get())
        config.always_on_aim = value
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save config.always_on_aim: {e}")

    def on_rcs_enabled_toggle(self):
        """Handle RCS enable/disable toggle"""
        value = bool(self.rcs_enabled_var.get())
        config.rcs_enabled = value
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save config.rcs_enabled: {e}")
    
    def on_rcs_y_random_toggle(self):
        """Handle RCS Y-axis random jitter toggle"""
        value = bool(self.rcs_y_random_enabled_var.get())
        config.rcs_y_random_enabled = value
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save config.rcs_y_random_enabled: {e}")
    
    def on_always_on_top_toggle(self):
        """Handle always on top toggle"""
        value = bool(self.always_on_top_var.get())
        config.always_on_top = value
        
        # Apply always on top setting to main window
        try:
            self.attributes("-topmost", value)
            print(f"[INFO] Always on top {'enabled' if value else 'disabled'}")
        except Exception as e:
            print(f"[WARN] Failed to set always on top: {e}")
        
        # Save the setting
        try:
            if hasattr(config, "save") and callable(config.save):
                self._schedule_config_save()
        except Exception as e:
            print(f"[WARN] Failed to save always_on_top setting: {e}")

    def on_rcs_ads_only_toggle(self):
        """Handle RCS ADS only toggle"""
        value = bool(self.rcs_ads_only_var.get())
        config.rcs_ads_only = value
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save config.rcs_ads_only: {e}")

    def update_rcs_x_strength(self, val):
        """Update RCS X-axis strength value"""
        value = round(float(val), 2)
        config.rcs_x_strength = value
        self.rcs_x_strength_entry.delete(0, "end")
        self.rcs_x_strength_entry.insert(0, f"{value:.2f}")
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save config.rcs_x_strength: {e}")
        
        # Auto-sync Y to X if sync is enabled
        if hasattr(self, 'rcs_strength_sync_var') and self.rcs_strength_sync_var.get():
            self._sync_rcs_strength_y_to_x()
    
    def update_rcs_x_delay(self, val):
        """Update RCS X-axis delay value (convert from ms to seconds)"""
        value_ms = int(round(float(val)))
        value_s = value_ms / 1000.0  # Convert to seconds
        config.rcs_x_delay = value_s
        self.rcs_x_delay_entry.delete(0, "end")
        self.rcs_x_delay_entry.insert(0, f"{value_ms}")
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save config.rcs_x_delay: {e}")
        
        # Auto-sync Y to X if sync is enabled
        if hasattr(self, 'rcs_delay_sync_var') and self.rcs_delay_sync_var.get():
            self._sync_rcs_delay_y_to_x()
    
    def update_rcs_y_strength(self, val):
        """Update RCS Y-axis random strength value"""
        value = round(float(val), 2)
        config.rcs_y_random_strength = value
        self.rcs_y_strength_entry.delete(0, "end")
        self.rcs_y_strength_entry.insert(0, f"{value:.2f}")
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save config.rcs_y_random_strength: {e}")
        
        # Handle sync - if RCS strength sync is enabled, sync X to Y
        if getattr(config, "rcs_strength_sync_enabled", False):
            self._sync_rcs_strength_x_to_y(value)
    
    def update_rcs_y_delay(self, val):
        """Update RCS Y-axis random delay value (convert from ms to seconds)"""
        value_ms = int(round(float(val)))
        value_s = value_ms / 1000.0  # Convert to seconds
        config.rcs_y_random_delay = value_s
        self.rcs_y_delay_entry.delete(0, "end")
        self.rcs_y_delay_entry.insert(0, f"{value_ms}")
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save config.rcs_y_random_delay: {e}")
        
        # Handle sync - if RCS delay sync is enabled, sync X to Y
        if getattr(config, "rcs_delay_sync_enabled", False):
            self._sync_rcs_delay_x_to_y(value_ms)

    def on_rcs_x_strength_entry_commit(self, event=None):
        """Handle RCS X-axis strength entry input"""
        try:
            value = float(self.rcs_x_strength_entry.get().strip())
            value = max(0.1, min(5.0, round(value, 2)))
            config.rcs_x_strength = value
            self.rcs_x_strength_slider.set(value)
            self.rcs_x_strength_entry.delete(0, "end")
            self.rcs_x_strength_entry.insert(0, f"{value:.2f}")
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception:
            self.rcs_x_strength_entry.delete(0, "end")
            self.rcs_x_strength_entry.insert(0, f"{config.rcs_x_strength:.2f}")
    
    def on_rcs_x_delay_entry_commit(self, event=None):
        """Handle RCS X-axis delay entry input (convert from ms to seconds)"""
        try:
            value_ms = int(self.rcs_x_delay_entry.get().strip())
            value_ms = max(1, min(100, value_ms))
            value_s = value_ms / 1000.0  # Convert to seconds
            config.rcs_x_delay = value_s
            self.rcs_x_delay_slider.set(value_ms)
            self.rcs_x_delay_entry.delete(0, "end")
            self.rcs_x_delay_entry.insert(0, f"{value_ms}")
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception:
            self.rcs_x_delay_entry.delete(0, "end")
            self.rcs_x_delay_entry.insert(0, f"{int(config.rcs_x_delay * 1000)}")
    
    def on_rcs_y_strength_entry_commit(self, event=None):
        """Handle RCS Y-axis random strength entry input"""
        try:
            value = float(self.rcs_y_strength_entry.get().strip())
            value = max(0.1, min(3.0, round(value, 2)))
            config.rcs_y_random_strength = value
            self.rcs_y_strength_slider.set(value)
            self.rcs_y_strength_entry.delete(0, "end")
            self.rcs_y_strength_entry.insert(0, f"{value:.2f}")
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception:
            self.rcs_y_strength_entry.delete(0, "end")
            self.rcs_y_strength_entry.insert(0, f"{config.rcs_y_random_strength:.2f}")
    
    def on_rcs_y_delay_entry_commit(self, event=None):
        """Handle RCS Y-axis random delay entry input (convert from ms to seconds)"""
        try:
            value_ms = int(self.rcs_y_delay_entry.get().strip())
            value_ms = max(1, min(100, value_ms))
            value_s = value_ms / 1000.0  # Convert to seconds
            config.rcs_y_random_delay = value_s
            self.rcs_y_delay_slider.set(value_ms)
            self.rcs_y_delay_entry.delete(0, "end")
            self.rcs_y_delay_entry.insert(0, f"{value_ms}")
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception:
            self.rcs_y_delay_entry.delete(0, "end")
            self.rcs_y_delay_entry.insert(0, f"{int(config.rcs_y_random_delay * 1000)}")

    def update_in_game_sens(self, val):
        config.in_game_sens = round(float(val), 2)
        self.in_game_sens_value.configure(text=f"{config.in_game_sens:.2f}")

    def update_in_game_sens_x(self, val):
        config.in_game_sens_x = round(float(val), 2)
        self.in_game_sens_x_value.configure(text=f"{config.in_game_sens_x:.2f}")
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save in_game_sens_x: {e}")
        
        # Auto-sync Y to X if sync is enabled
        if hasattr(self, 'smoothing_sync_var') and self.smoothing_sync_var.get():
            self._sync_smoothing_y_to_x()

    def update_in_game_sens_y(self, val):
        config.in_game_sens_y = round(float(val), 2)
        self.in_game_sens_y_value.configure(text=f"{config.in_game_sens_y:.2f}")
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save in_game_sens_y: {e}")
        
        # Handle sync - if smoothing sync is enabled, sync X to Y
        if getattr(config, "smoothing_sync_enabled", False):
            self._sync_smoothing_x_to_y(config.in_game_sens_y)

    def update_fov_x(self, val):
        """Called by the FOV X slider."""
        if getattr(self, "_updating_fov_x", False):
            return
        self._apply_fov_x(int(round(val)), source="slider")

    def on_fov_x_entry_commit(self, event=None):
        """Called when user presses Enter or leaves the FOV X entry."""
        try:
            val = int(self.fov_x_entry.get().strip())
        except Exception:
            self._set_entry_text(self.fov_x_entry, str(getattr(config, "fov_x_size", config.region_size)))
            return
        self._apply_fov_x(val, source="entry")

    def _apply_fov_x(self, value, source="code"):
        MIN_FOV, MAX_FOV = 20, 500
        value = max(MIN_FOV, min(MAX_FOV, int(value)))
        self._updating_fov_x = True
        try:
            config.fov_x_size = value
            config.region_size = max(config.fov_x_size, getattr(config, "fov_y_size", config.region_size))
            if source != "slider":
                self.fov_x_slider.set(value)
            if source != "entry":
                self._set_entry_text(self.fov_x_entry, str(value))
            
            # Auto-sync Y to X if sync is enabled
            if hasattr(self, 'fov_sync_var') and self.fov_sync_var.get():
                self._sync_fov_y_to_x()
        finally:
            self._updating_fov_x = False

    def update_fov_y(self, val):
        """Called by the FOV Y slider."""
        if getattr(self, "_updating_fov_y", False):
            return
        self._apply_fov_y(int(round(val)), source="slider")

    def on_fov_y_entry_commit(self, event=None):
        """Called when user presses Enter or leaves the FOV Y entry."""
        try:
            val = int(self.fov_y_entry.get().strip())
        except Exception:
            self._set_entry_text(self.fov_y_entry, str(getattr(config, "fov_y_size", config.region_size)))
            return
        self._apply_fov_y(val, source="entry")

    def _apply_fov_y(self, value, source="code"):
        MIN_FOV, MAX_FOV = 20, 500
        value = max(MIN_FOV, min(MAX_FOV, int(value)))
        self._updating_fov_y = True
        try:
            config.fov_y_size = value
            config.region_size = max(getattr(config, "fov_x_size", config.region_size), config.fov_y_size)
            if source != "slider":
                self.fov_y_slider.set(value)
            if source != "entry":
                self._set_entry_text(self.fov_y_entry, str(value))
            
            # Handle sync - if FOV sync is enabled, sync X to Y
            if getattr(config, "fov_sync_enabled", False):
                self._sync_fov_x_to_y(value)
        finally:
            self._updating_fov_y = False

    def update_target_height(self, val):
        """Update target height value (0.100=bottom, 1.000=top)"""
        value = round(float(val), 3)
        config.target_height = value
        self._set_entry_text(self.target_height_entry, f"{value:.3f}")
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save target_height: {e}")
    
    def on_target_height_entry_commit(self, event=None):
        """Handle target height entry input"""
        try:
            value = float(self.target_height_entry.get().strip())
            value = max(0.100, min(1.000, round(value, 3)))
            config.target_height = value
            self.target_height_slider.set(value)
            self._set_entry_text(self.target_height_entry, f"{value:.3f}")
        except Exception:
            self._set_entry_text(self.target_height_entry, f"{config.target_height:.3f}")
    
    def on_height_deadzone_toggle(self):
        """Toggle height deadzone functionality"""
        config.height_deadzone_enabled = bool(self.height_deadzone_var.get())
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save height_deadzone_enabled: {e}")

    def update_height_deadzone_min(self, val):
        """Update height deadzone minimum value"""
        value = round(float(val), 3)
        # Ensure min is less than max
        if value >= config.height_deadzone_max:
            value = config.height_deadzone_max - 0.001
        config.height_deadzone_min = value
        self._set_entry_text(self.height_deadzone_min_entry, f"{value:.3f}")
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save height_deadzone_min: {e}")
    
    def on_height_deadzone_min_entry_commit(self, event=None):
        """Handle height deadzone min entry input"""
        try:
            value = float(self.height_deadzone_min_entry.get().strip())
            value = max(0.100, min(0.999, round(value, 3)))
            # Ensure min is less than max
            if value >= config.height_deadzone_max:
                value = config.height_deadzone_max - 0.001
            config.height_deadzone_min = value
            self.height_deadzone_min_slider.set(value)
            self._set_entry_text(self.height_deadzone_min_entry, f"{value:.3f}")
        except Exception:
            self._set_entry_text(self.height_deadzone_min_entry, f"{config.height_deadzone_min:.3f}")

    def update_height_deadzone_max(self, val):
        """Update height deadzone maximum value"""
        value = round(float(val), 3)
        # Ensure max is greater than min
        if value <= config.height_deadzone_min:
            value = config.height_deadzone_min + 0.001
        config.height_deadzone_max = value
        self._set_entry_text(self.height_deadzone_max_entry, f"{value:.3f}")
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save height_deadzone_max: {e}")
    
    def on_height_deadzone_max_entry_commit(self, event=None):
        """Handle height deadzone max entry input"""
        try:
            value = float(self.height_deadzone_max_entry.get().strip())
            value = max(0.101, min(1.000, round(value, 3)))
            # Ensure max is greater than min
            if value <= config.height_deadzone_min:
                value = config.height_deadzone_min + 0.001
            config.height_deadzone_max = value
            self.height_deadzone_max_slider.set(value)
            self._set_entry_text(self.height_deadzone_max_entry, f"{value:.3f}")
        except Exception:
            self._set_entry_text(self.height_deadzone_max_entry, f"{config.height_deadzone_max:.3f}")

    def update_height_deadzone_tolerance(self, val):
        """Update height deadzone tolerance value"""
        value = round(float(val), 3)
        config.height_deadzone_tolerance = value
        self._set_entry_text(self.height_deadzone_tolerance_entry, f"{value:.3f}")
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save height_deadzone_tolerance: {e}")
    
    def on_height_deadzone_tolerance_entry_commit(self, event=None):
        """Handle height deadzone tolerance entry input"""
        try:
            value = float(self.height_deadzone_tolerance_entry.get().strip())
            value = max(0.000, min(20.000, round(value, 3)))
            config.height_deadzone_tolerance = value
            self.height_deadzone_tolerance_slider.set(value)
            self._set_entry_text(self.height_deadzone_tolerance_entry, f"{value:.3f}")
        except Exception:
            self._set_entry_text(self.height_deadzone_tolerance_entry, f"{config.height_deadzone_tolerance:.3f}")
    
    def on_x_center_targeting_toggle(self):
        """Toggle X-axis center targeting functionality"""
        config.x_center_targeting_enabled = bool(self.x_center_targeting_var.get())
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save x_center_targeting_enabled: {e}")
    
    def update_x_center_tolerance(self, val):
        """Update X-center tolerance percentage value"""
        value = round(float(val), 1)
        config.x_center_tolerance_percent = value
        self._set_entry_text(self.x_center_tolerance_entry, f"{value:.1f}")
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save x_center_tolerance_percent: {e}")
    
    def on_x_center_tolerance_entry_commit(self, event=None):
        """Handle X-center tolerance entry input"""
        try:
            value = float(self.x_center_tolerance_entry.get().strip())
            value = max(0.0, min(50.0, round(value, 1)))
            config.x_center_tolerance_percent = value
            self.x_center_tolerance_slider.set(value)
            self._set_entry_text(self.x_center_tolerance_entry, f"{value:.1f}")
        except Exception:
            self._set_entry_text(self.x_center_tolerance_entry, f"{config.x_center_tolerance_percent:.1f}")

    def update_mouse_multiplier_x(self, val):
        """Update X-axis mouse movement multiplier value"""
        if getattr(self, '_updating_mouse_multiplier_x', False):
            return
        value = round(float(val), 2)
        config.mouse_movement_multiplier_x = value
        self._set_entry_text(self.mouse_multiplier_x_entry, f"{value:.2f}")
        
        # Sync Y if enabled
        if getattr(config, "mouse_movement_sync_enabled", False):
            config.mouse_movement_multiplier_y = value
            if not getattr(self, '_updating_mouse_multiplier_y', False):
                self.mouse_multiplier_y_slider.set(value)
                self._set_entry_text(self.mouse_multiplier_y_entry, f"{value:.2f}")
        
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save mouse_movement_multiplier_x: {e}")

    def update_mouse_multiplier_y(self, val):
        """Update Y-axis mouse movement multiplier value"""
        if getattr(self, '_updating_mouse_multiplier_y', False):
            return
        value = round(float(val), 2)
        config.mouse_movement_multiplier_y = value
        self._set_entry_text(self.mouse_multiplier_y_entry, f"{value:.2f}")
        
        # Sync X if enabled
        if getattr(config, "mouse_movement_sync_enabled", False):
            config.mouse_movement_multiplier_x = value
            if not getattr(self, '_updating_mouse_multiplier_x', False):
                self.mouse_multiplier_x_slider.set(value)
                self._set_entry_text(self.mouse_multiplier_x_entry, f"{value:.2f}")
        
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save mouse_movement_multiplier_y: {e}")
    
    def on_mouse_multiplier_x_entry_commit(self, event=None):
        """Handle X-axis mouse movement multiplier entry input"""
        try:
            value = float(self.mouse_multiplier_x_entry.get().strip())
            value = max(0.0, min(5.0, round(value, 2)))
            self._updating_mouse_multiplier_x = True
            config.mouse_movement_multiplier_x = value
            self.mouse_multiplier_x_slider.set(value)
            self._set_entry_text(self.mouse_multiplier_x_entry, f"{value:.2f}")
        except Exception:
            self._set_entry_text(self.mouse_multiplier_x_entry, f"{getattr(config, 'mouse_movement_multiplier_x', 1.0):.2f}")
        finally:
            self._updating_mouse_multiplier_x = False

    def on_mouse_multiplier_y_entry_commit(self, event=None):
        """Handle Y-axis mouse movement multiplier entry input"""
        try:
            value = float(self.mouse_multiplier_y_entry.get().strip())
            value = max(0.0, min(5.0, round(value, 2)))
            self._updating_mouse_multiplier_y = True
            config.mouse_movement_multiplier_y = value
            self.mouse_multiplier_y_slider.set(value)
            self._set_entry_text(self.mouse_multiplier_y_entry, f"{value:.2f}")
        except Exception:
            self._set_entry_text(self.mouse_multiplier_y_entry, f"{getattr(config, 'mouse_movement_multiplier_y', 1.0):.2f}")
        finally:
            self._updating_mouse_multiplier_y = False

    def on_mouse_movement_sync_toggle(self):
        """Toggle mouse movement X/Y sync"""
        sync_enabled = bool(self.mouse_movement_sync_var.get())
        config.mouse_movement_sync_enabled = sync_enabled
        
        # If sync is enabled, sync Y to X value
        if sync_enabled:
            config.mouse_movement_multiplier_y = config.mouse_movement_multiplier_x
            self.mouse_multiplier_y_slider.set(config.mouse_movement_multiplier_y)
            self._set_entry_text(self.mouse_multiplier_y_entry, f"{config.mouse_movement_multiplier_y:.2f}")
            print(f"[INFO] 🔗 MOUSE MOVEMENT SYNC ENABLED - Y synced to X ({config.mouse_movement_multiplier_x:.2f})")
        else:
            print("[INFO] 🔓 MOUSE MOVEMENT INDEPENDENT MODE - X/Y can be controlled separately")

    def on_mouse_movement_x_enabled_toggle(self):
        """Toggle X-axis movement enable/disable"""
        enabled = bool(self.mouse_movement_x_enabled_var.get())
        config.mouse_movement_enabled_x = enabled
        print(f"[INFO] {'✅' if enabled else '❌'} X-axis movement {'enabled' if enabled else 'disabled'}")

    def on_mouse_movement_y_enabled_toggle(self):
        """Toggle Y-axis movement enable/disable"""
        enabled = bool(self.mouse_movement_y_enabled_var.get())
        config.mouse_movement_enabled_y = enabled
        print(f"[INFO] {'✅' if enabled else '❌'} Y-axis movement {'enabled' if enabled else 'disabled'}")

    # Height Targeting Controls
    def on_height_targeting_toggle(self):
        """Toggle height targeting functionality"""
        enabled = bool(self.height_targeting_var.get())
        config.height_targeting_enabled = enabled
        
        # Enable/disable all height targeting controls based on toggle
        state = "normal" if enabled else "disabled"
        try:
            self.target_height_slider.configure(state=state)
            self.target_height_entry.configure(state=state)
            self.height_deadzone_switch.configure(state=state)
            
            # Update deadzone controls based on both height targeting and deadzone toggles
            deadzone_state = "normal" if (enabled and config.height_deadzone_enabled) else "disabled"
            self.deadzone_min_slider.configure(state=deadzone_state)
            self.deadzone_max_slider.configure(state=deadzone_state)
            self.deadzone_tolerance_slider.configure(state=deadzone_state)
            self.deadzone_min_entry.configure(state=deadzone_state)
            self.deadzone_max_entry.configure(state=deadzone_state)
            self.deadzone_tolerance_entry.configure(state=deadzone_state)
        except Exception:
            pass
        
        print(f"[INFO] {'🎯' if enabled else '❌'} Height targeting {'enabled' if enabled else 'disabled'}")
        
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save height_targeting_enabled: {e}")
    
    def on_height_deadzone_toggle(self):
        """Toggle height deadzone functionality"""
        enabled = bool(self.height_deadzone_var.get())
        config.height_deadzone_enabled = enabled
        
        # Enable/disable deadzone controls (only if height targeting is also enabled)
        deadzone_state = "normal" if (config.height_targeting_enabled and enabled) else "disabled"
        try:
            self.deadzone_min_slider.configure(state=deadzone_state)
            self.deadzone_max_slider.configure(state=deadzone_state)
            self.deadzone_tolerance_slider.configure(state=deadzone_state)
            self.deadzone_min_entry.configure(state=deadzone_state)
            self.deadzone_max_entry.configure(state=deadzone_state)
            self.deadzone_tolerance_entry.configure(state=deadzone_state)
        except Exception:
            pass
        
        print(f"[INFO] {'🎯' if enabled else '❌'} Height deadzone {'enabled' if enabled else 'disabled'}")
        
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save height_deadzone_enabled: {e}")
    
    def update_target_height(self, val):
        """Update target height value"""
        value = round(float(val), 3)
        config.target_height = value
        self._set_entry_text(self.target_height_entry, f"{value:.3f}")
        
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save target_height: {e}")
    
    def on_target_height_entry_commit(self, event=None):
        """Handle target height entry input"""
        try:
            value = float(self.target_height_entry.get().strip())
            value = max(0.0, min(1.0, round(value, 3)))
            config.target_height = value
            self.target_height_slider.set(value)
            self._set_entry_text(self.target_height_entry, f"{value:.3f}")
        except Exception:
            self._set_entry_text(self.target_height_entry, f"{config.target_height:.3f}")
    
    def update_deadzone_min(self, val):
        """Update deadzone minimum value"""
        value = round(float(val), 3)
        # Ensure min doesn't exceed max
        if value >= config.height_deadzone_max:
            value = config.height_deadzone_max - 0.001
        config.height_deadzone_min = value
        self._set_entry_text(self.deadzone_min_entry, f"{value:.3f}")
        
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save height_deadzone_min: {e}")
    
    def on_deadzone_min_entry_commit(self, event=None):
        """Handle deadzone min entry input"""
        try:
            value = float(self.deadzone_min_entry.get().strip())
            value = max(0.0, min(0.999, round(value, 3)))
            # Ensure min doesn't exceed max
            if value >= config.height_deadzone_max:
                value = config.height_deadzone_max - 0.001
            config.height_deadzone_min = value
            self.deadzone_min_slider.set(value)
            self._set_entry_text(self.deadzone_min_entry, f"{value:.3f}")
        except Exception:
            self._set_entry_text(self.deadzone_min_entry, f"{config.height_deadzone_min:.3f}")
    
    def update_deadzone_max(self, val):
        """Update deadzone maximum value"""
        value = round(float(val), 3)
        # Ensure max doesn't go below min
        if value <= config.height_deadzone_min:
            value = config.height_deadzone_min + 0.001
        config.height_deadzone_max = value
        self._set_entry_text(self.deadzone_max_entry, f"{value:.3f}")
        
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save height_deadzone_max: {e}")
    
    def on_deadzone_max_entry_commit(self, event=None):
        """Handle deadzone max entry input"""
        try:
            value = float(self.deadzone_max_entry.get().strip())
            value = max(0.001, min(1.0, round(value, 3)))
            # Ensure max doesn't go below min
            if value <= config.height_deadzone_min:
                value = config.height_deadzone_min + 0.001
            config.height_deadzone_max = value
            self.deadzone_max_slider.set(value)
            self._set_entry_text(self.deadzone_max_entry, f"{value:.3f}")
        except Exception:
            self._set_entry_text(self.deadzone_max_entry, f"{config.height_deadzone_max:.3f}")
    
    def update_deadzone_tolerance(self, val):
        """Update deadzone tolerance value"""
        value = round(float(val), 1)
        config.height_deadzone_tolerance = value
        self._set_entry_text(self.deadzone_tolerance_entry, f"{value:.1f}")
        
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save height_deadzone_tolerance: {e}")
    
    def on_deadzone_tolerance_entry_commit(self, event=None):
        """Handle deadzone tolerance entry input"""
        try:
            value = float(self.deadzone_tolerance_entry.get().strip())
            value = max(0.0, min(20.0, round(value, 1)))
            config.height_deadzone_tolerance = value
            self.deadzone_tolerance_slider.set(value)
            self._set_entry_text(self.deadzone_tolerance_entry, f"{value:.1f}")
        except Exception:
            self._set_entry_text(self.deadzone_tolerance_entry, f"{config.height_deadzone_tolerance:.1f}")

    def update_silent_strength(self, val):
        """Update silent strength value"""
        value = round(float(val), 3)
        config.silent_strength = value
        self._set_entry_text(self.silent_strength_entry, f"{value:.3f}")
    
    def on_silent_strength_entry_commit(self, event=None):
        """Handle silent strength entry input"""
        try:
            value = float(self.silent_strength_entry.get().strip())
            value = max(0.100, min(3.000, round(value, 3)))
            config.silent_strength = value
            self.silent_strength_slider.set(value)
            self._set_entry_text(self.silent_strength_entry, f"{value:.3f}")
        except Exception:
            self._set_entry_text(self.silent_strength_entry, f"{config.silent_strength:.3f}")
    
    def on_silent_auto_fire_toggle(self):
        """Toggle silent auto fire functionality"""
        config.silent_auto_fire = bool(self.silent_auto_fire_var.get())
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save silent_auto_fire: {e}")
    
    def on_silent_speed_mode_toggle(self):
        """Toggle silent speed mode for ultra-fast execution"""
        config.silent_speed_mode = bool(self.silent_speed_mode_var.get())
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save silent_speed_mode: {e}")
    
    def update_silent_fire_delay(self, val):
        """Update silent fire delay value"""
        value = round(float(val), 3)
        config.silent_fire_delay = value
        self._set_entry_text(self.silent_fire_delay_entry, f"{value:.3f}")
    
    def on_silent_fire_delay_entry_commit(self, event=None):
        """Handle silent fire delay entry input"""
        try:
            value = float(self.silent_fire_delay_entry.get().strip())
            value = max(0.000, min(0.200, round(value, 3)))
            config.silent_fire_delay = value
            self.silent_fire_delay_slider.set(value)
            self._set_entry_text(self.silent_fire_delay_entry, f"{value:.3f}")
        except Exception:
            self._set_entry_text(self.silent_fire_delay_entry, f"{config.silent_fire_delay:.3f}")
    
    def update_silent_return_delay(self, val):
        """Update silent return delay value"""
        value = round(float(val), 3)
        config.silent_return_delay = value
        self._set_entry_text(self.silent_return_delay_entry, f"{value:.3f}")
    
    def on_silent_return_delay_entry_commit(self, event=None):
        """Handle silent return delay entry input"""
        try:
            value = float(self.silent_return_delay_entry.get().strip())
            value = max(0.000, min(0.500, round(value, 3)))
            config.silent_return_delay = value
            self.silent_return_delay_slider.set(value)
            self._set_entry_text(self.silent_return_delay_entry, f"{value:.3f}")
        except Exception:
            self._set_entry_text(self.silent_return_delay_entry, f"{config.silent_return_delay:.3f}")
    
    def on_silent_bezier_toggle(self):
        """Toggle silent bezier curve movement"""
        config.silent_use_bezier = bool(self.silent_use_bezier_var.get())
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save silent_use_bezier: {e}")

    def poll_fps(self):
        # Simple FPS display (safe and stable)
        self.fps_var.set(f"FPS: {main.fps:.1f}")
        self.aimbot_status.set("Running" if is_aimbot_running() else "Stopped")
        self.after(100, self.poll_fps)  # Update every 100ms for stability

    def get_model_list(self):
        model_files = []
        for ext in ("pt", "onnx", "engine"):
            model_files.extend(glob.glob(f"models/*.{ext}"))
        return [os.path.basename(p) for p in model_files]

    def select_model(self, val):
        path = os.path.join("models", val)
        if os.path.isfile(path):
            config.model_path = path
            self.model_name.set(os.path.basename(path))
            self.model_size.set(get_model_size(path))
            try:
                reload_model(path)
                self.load_class_list()
                self.error_text.set(f"✅ Model '{val}' loaded successfully")
            except Exception as e:
                self.error_text.set(f"❌ Failed to load model: {e}")
        else:
            self.error_text.set(f"❌ Model file not found: {path}")

    def reload_model(self):
        try:
            reload_model(config.model_path)
            self.load_class_list()
            self.error_text.set("✅ Model reloaded successfully")
        except Exception as e:
            self.error_text.set(f"❌ Failed to reload model: {e}")

    def load_class_list(self):
        try:
            classes = get_model_classes(config.model_path)
            self.available_classes = classes
            self.class_listbox.delete("0.0", "end")
            
            for i, c in enumerate(classes):
                display_text = f"Class {i}: {c}\n"
                self.class_listbox.insert("end", display_text)
            
            class_options = [str(c) for c in classes]
            self.head_class_menu.configure(values=["None"] + class_options)
            self.player_class_menu.configure(values=class_options)
            
            current_head = config.custom_head_label
            current_player = config.custom_player_label
            
            self.head_class_var.set(str(current_head) if current_head is not None else "None")
            self.player_class_var.set(str(current_player) if current_player is not None else "0")
            
        except Exception as e:
            self.error_text.set(f"❌ Failed to load classes: {e}")

    def get_available_classes(self):
        classes = getattr(self, "available_classes", ["0", "1"])
        return [str(c) for c in classes]

    def set_head_class(self, val):
        if val == "None":
            config.custom_head_label = None
        else:
            config.custom_head_label = val
        # Debug: Head class set (removed for cleaner output)

    def set_player_class(self, val):
        config.custom_player_label = val
        # Debug: Player class set (removed for cleaner output)

    def update_dynamic_frame(self):
        for w in self.dynamic_frame.winfo_children():
            w.destroy()
        mode = config.mode
        # Debug: Updating dynamic frame (removed for cleaner output)
        
        if mode == "normal":
            self.add_speed_section("Normal", "normal_x_speed", "normal_y_speed")
        elif mode == "bezier":
            self.add_bezier_section("bezier_segments", "bezier_ctrl_x", "bezier_ctrl_y")
        elif mode == "silent":
            self.add_bezier_section("silent_segments", "silent_ctrl_x", "silent_ctrl_y")
            self.add_silent_section()
        elif mode == "smooth":
            self.add_smooth_section()
        elif mode == "pid":
            try:
                # Lazy import already done at top; instantiate and render section
                pid_section = PIDAimSection(self.dynamic_frame, config, gui_instance=self)
                pid_section.create_section()
            except Exception as e:
                print(f"[ERROR] Failed to build PID section: {e}")
        elif mode == "gan":
            # Debug: Adding GAN section (removed for cleaner output)
            try:
                self.add_gan_section()
                # Debug: GAN section added successfully (removed for cleaner output)
            except Exception as e:
                print(f"[ERROR] 🧠 REAL GAN section failed: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"[WARN] REAL Unknown aimbot mode: {mode}")

    def add_speed_section(self, label, min_key, max_key):
        f = ctk.CTkFrame(self.dynamic_frame, fg_color="#1a1a1a")
        f.pack(fill="x", pady=5)
        f.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(f, text=f"⚙️ {label} Aim Settings", font=("Segoe UI", 14, "bold"), text_color="#00e676").grid(row=0, column=0, columnspan=3, pady=(10, 5), padx=10, sticky="w")
        
        ctk.CTkLabel(f, text="X Speed:", text_color="#fff").grid(row=1, column=0, sticky="w", padx=10, pady=2)
        x_slider = ctk.CTkSlider(f, from_=0.1, to=1, number_of_steps=9)
        x_slider.set(getattr(config, min_key))
        x_slider.grid(row=1, column=1, sticky="ew", padx=(5, 5), pady=2)
        x_value_label = ctk.CTkLabel(f, text=f"{getattr(config, min_key):.2f}", text_color=NEON, width=50)
        x_value_label.grid(row=1, column=2, padx=10, pady=2)
        
        def update_x(val):
            val = float(val)
            setattr(config, min_key, val)
            x_value_label.configure(text=f"{val:.2f}")
        x_slider.configure(command=update_x)
        
        ctk.CTkLabel(f, text="Y Speed:", text_color="#fff").grid(row=2, column=0, sticky="w", padx=10, pady=(2, 10))
        y_slider = ctk.CTkSlider(f, from_=0.1, to=1, number_of_steps=9)
        y_slider.set(getattr(config, max_key))
        y_slider.grid(row=2, column=1, sticky="ew", padx=(5, 5), pady=(2, 10))
        y_value_label = ctk.CTkLabel(f, text=f"{getattr(config, max_key):.2f}", text_color=NEON, width=50)
        y_value_label.grid(row=2, column=2, padx=10, pady=(2, 10))
        
        def update_y(val):
            val = float(val)
            setattr(config, max_key, val)
            y_value_label.configure(text=f"{val:.2f}")
        y_slider.configure(command=update_y)

        # X/Y movement toggles
        xy_frame = ctk.CTkFrame(f, fg_color="transparent")
        xy_frame.grid(row=3, column=0, columnspan=3, sticky="ew", padx=10, pady=(5, 10))

        def create_toggle(parent, text, config_key, var):
            def on_toggle():
                setattr(config, config_key, var.get())
                config.save() # Save changes immediately
            ctk.CTkSwitch(parent, text=text, variable=var, command=on_toggle, text_color="#fff")\
                .pack(side="left", padx=10)

        create_toggle(xy_frame, "Enable X", f"{label.lower()}_enable_x", getattr(self, f"{label.lower()}_enable_x_var"))
        create_toggle(xy_frame, "Enable Y", f"{label.lower()}_enable_y", getattr(self, f"{label.lower()}_enable_y_var"))

    def add_bezier_section(self, seg_key, cx_key, cy_key):
        f = ctk.CTkFrame(self.dynamic_frame, fg_color="#1a1a1a")
        f.pack(fill="x", pady=5)
        f.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(f, text="🌀 Bezier Curve Settings", font=("Segoe UI", 14, "bold"), text_color="#00e676").grid(row=0, column=0, columnspan=3, pady=(10, 5), padx=10, sticky="w")
        
        ctk.CTkLabel(f, text="Segments:", text_color="#fff").grid(row=1, column=0, sticky="w", padx=10, pady=2)
        seg_slider = ctk.CTkSlider(f, from_=0, to=20, number_of_steps=20, command=lambda v: setattr(config, seg_key, int(float(v))))
        seg_slider.set(getattr(config, seg_key))
        seg_slider.grid(row=1, column=1, sticky="ew", padx=(5, 5), pady=2)
        
        ctk.CTkLabel(f, text="Control X:", text_color="#fff").grid(row=2, column=0, sticky="w", padx=10, pady=2)
        cx_slider = ctk.CTkSlider(f, from_=0, to=60, number_of_steps=60, command=lambda v: setattr(config, cx_key, int(float(v))))
        cx_slider.set(getattr(config, cx_key))
        cx_slider.grid(row=2, column=1, sticky="ew", padx=(5, 5), pady=2)
        
        ctk.CTkLabel(f, text="Control Y:", text_color="#fff").grid(row=3, column=0, sticky="w", padx=10, pady=(2, 10))
        cy_slider = ctk.CTkSlider(f, from_=0, to=60, number_of_steps=60, command=lambda v: setattr(config, cy_key, int(float(v))))
        cy_slider.set(getattr(config, cy_key))
        cy_slider.grid(row=3, column=1, sticky="ew", padx=(5, 5), pady=(2, 10))

        # X/Y movement toggles
        xy_frame = ctk.CTkFrame(f, fg_color="transparent")
        xy_frame.grid(row=4, column=0, columnspan=3, sticky="ew", padx=10, pady=(5, 10))

        def create_toggle(parent, text, config_key, var):
            def on_toggle():
                setattr(config, config_key, var.get())
                config.save() # Save changes immediately
            ctk.CTkSwitch(parent, text=text, variable=var, command=on_toggle, text_color="#fff")\
                .pack(side="left", padx=10)

        create_toggle(xy_frame, "Enable X", "bezier_enable_x", self.bezier_enable_x_var)
        create_toggle(xy_frame, "Enable Y", "bezier_enable_y", self.bezier_enable_y_var)

    def add_silent_section(self):
        f = ctk.CTkFrame(self.dynamic_frame, fg_color="#2a2a2a")
        f.pack(fill="x", pady=5)
        f.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(f, text="🤫 Silent Aim Settings", font=("Segoe UI", 14, "bold"), text_color="#00e676").grid(row=0, column=0, columnspan=3, pady=(10, 5), padx=10, sticky="w")
        
        # Traditional settings
        ctk.CTkLabel(f, text="Speed:", text_color="#fff").grid(row=1, column=0, sticky="w", padx=10, pady=2)
        speed_slider = ctk.CTkSlider(f, from_=1, to=6, number_of_steps=5, command=lambda v: setattr(config, "silent_speed", int(float(v))))
        speed_slider.set(config.silent_speed)
        speed_slider.grid(row=1, column=1, sticky="ew", padx=(5, 5), pady=2)
        
        ctk.CTkLabel(f, text="Cooldown:", text_color="#fff").grid(row=2, column=0, sticky="w", padx=10, pady=2)
        cooldown_slider = ctk.CTkSlider(f, from_=0.00, to=0.5, number_of_steps=50, command=lambda v: setattr(config, "silent_cooldown", float(v)))
        cooldown_slider.set(config.silent_cooldown)
        cooldown_slider.grid(row=2, column=1, sticky="ew", padx=(5, 5), pady=2)
        
        # Enhanced Silent Mode
        ctk.CTkLabel(f, text="⚡ Enhanced Silent Mode", font=("Segoe UI", 12, "bold"), text_color="#ff073a").grid(row=3, column=0, columnspan=3, pady=(15, 5), padx=10, sticky="w")
        
        # Silent Strength
        ctk.CTkLabel(f, text="Silent Strength:", text_color="#fff").grid(row=4, column=0, sticky="w", padx=10, pady=2)
        self.silent_strength_slider = ctk.CTkSlider(f, from_=0.100, to=3.000, number_of_steps=2900, command=self.update_silent_strength)
        self.silent_strength_slider.set(config.silent_strength)
        self.silent_strength_slider.grid(row=4, column=1, sticky="ew", padx=(5, 5), pady=2)
        self.silent_strength_entry = ctk.CTkEntry(f, width=60, justify="center", font=("Segoe UI", 11, "bold"), text_color=NEON)
        self.silent_strength_entry.grid(row=4, column=2, padx=10, pady=2)
        self.silent_strength_entry.insert(0, f"{config.silent_strength:.3f}")
        self.silent_strength_entry.bind("<Return>", self.on_silent_strength_entry_commit)
        self.silent_strength_entry.bind("<FocusOut>", self.on_silent_strength_entry_commit)
        
        # Auto Fire Toggle
        self.silent_auto_fire_var = ctk.BooleanVar(value=config.silent_auto_fire)
        self.silent_auto_fire_switch = ctk.CTkSwitch(
            f,
            text="Auto Fire",
            variable=self.silent_auto_fire_var,
            command=self.on_silent_auto_fire_toggle,
            text_color="#fff"
        )
        self.silent_auto_fire_switch.grid(row=5, column=0, sticky="w", padx=10, pady=(5, 2))
        
        # Speed Mode Toggle
        self.silent_speed_mode_var = ctk.BooleanVar(value=config.silent_speed_mode)
        self.silent_speed_mode_switch = ctk.CTkSwitch(
            f,
            text="⚡ Speed Mode",
            variable=self.silent_speed_mode_var,
            command=self.on_silent_speed_mode_toggle,
            text_color="#00ff00"
        )
        self.silent_speed_mode_switch.grid(row=5, column=1, columnspan=2, sticky="w", padx=10, pady=(5, 2))
        
        # Fire Delay
        ctk.CTkLabel(f, text="Fire Delay:", text_color="#fff").grid(row=6, column=0, sticky="w", padx=10, pady=2)
        self.silent_fire_delay_slider = ctk.CTkSlider(f, from_=0.000, to=0.200, number_of_steps=200, command=self.update_silent_fire_delay)
        self.silent_fire_delay_slider.set(config.silent_fire_delay)
        self.silent_fire_delay_slider.grid(row=6, column=1, sticky="ew", padx=(5, 5), pady=2)
        self.silent_fire_delay_entry = ctk.CTkEntry(f, width=60, justify="center", font=("Segoe UI", 11, "bold"), text_color=NEON)
        self.silent_fire_delay_entry.grid(row=6, column=2, padx=10, pady=2)
        self.silent_fire_delay_entry.insert(0, f"{config.silent_fire_delay:.3f}")
        self.silent_fire_delay_entry.bind("<Return>", self.on_silent_fire_delay_entry_commit)
        self.silent_fire_delay_entry.bind("<FocusOut>", self.on_silent_fire_delay_entry_commit)
        
        # Return Delay
        ctk.CTkLabel(f, text="Return Delay:", text_color="#fff").grid(row=7, column=0, sticky="w", padx=10, pady=2)
        self.silent_return_delay_slider = ctk.CTkSlider(f, from_=0.000, to=0.500, number_of_steps=500, command=self.update_silent_return_delay)
        self.silent_return_delay_slider.set(config.silent_return_delay)
        self.silent_return_delay_slider.grid(row=7, column=1, sticky="ew", padx=(5, 5), pady=2)
        self.silent_return_delay_entry = ctk.CTkEntry(f, width=60, justify="center", font=("Segoe UI", 11, "bold"), text_color=NEON)
        self.silent_return_delay_entry.grid(row=7, column=2, padx=10, pady=2)
        self.silent_return_delay_entry.insert(0, f"{config.silent_return_delay:.3f}")
        self.silent_return_delay_entry.bind("<Return>", self.on_silent_return_delay_entry_commit)
        self.silent_return_delay_entry.bind("<FocusOut>", self.on_silent_return_delay_entry_commit)
        
        # Bezier Curve Toggle
        self.silent_use_bezier_var = ctk.BooleanVar(value=config.silent_use_bezier)
        self.silent_use_bezier_switch = ctk.CTkSwitch(
            f,
            text="🌀 Use Bezier Curve",
            variable=self.silent_use_bezier_var,
            command=self.on_silent_bezier_toggle,
            text_color="#fff"
        )
        self.silent_use_bezier_switch.grid(row=8, column=0, columnspan=3, sticky="w", padx=10, pady=(5, 5))

        # X/Y movement toggles
        xy_frame = ctk.CTkFrame(f, fg_color="transparent")
        xy_frame.grid(row=9, column=0, columnspan=3, sticky="ew", padx=10, pady=(5, 10))

        def create_toggle(parent, text, config_key, var):
            def on_toggle():
                setattr(config, config_key, var.get())
                config.save() # Save changes immediately
            ctk.CTkSwitch(parent, text=text, variable=var, command=on_toggle, text_color="#fff")\
                .pack(side="left", padx=10)

        create_toggle(xy_frame, "Enable X", "silent_enable_x", self.silent_enable_x_var)
        create_toggle(xy_frame, "Enable Y", "silent_enable_y", self.silent_enable_y_var)

    def add_smooth_section(self):
        f = ctk.CTkFrame(self.dynamic_frame, fg_color="#0a0a0a")
        f.pack(fill="x", pady=5)
        f.grid_columnconfigure(1, weight=1)
        
        # Title
        ctk.CTkLabel(f, text="🌪️ WindMouse Smooth Aim", font=("Segoe UI", 14, "bold"), text_color="#00e676").grid(row=0, column=0, columnspan=3, pady=(10, 10), padx=10, sticky="w")
        
        # Core parameters
        params = [
            ("Gravity:", "smooth_gravity", 1, 20, 19),
            ("Wind:", "smooth_wind", 1, 20, 19),
            ("Close Speed:", "smooth_close_speed", 0.1, 1.0, 18),
            ("Far Speed:", "smooth_far_speed", 0.1, 1.0, 18),
            ("Reaction Time:", "smooth_reaction_max", 0.01, 0.3, 29),
            ("Max Step:", "smooth_max_step", 5, 50, 45)
        ]
        
        for i, (label, key, min_val, max_val, steps) in enumerate(params):
            ctk.CTkLabel(f, text=label, text_color="#fff", font=("Segoe UI", 11, "bold")).grid(row=i+1, column=0, sticky="w", padx=10, pady=2)
            
            slider = ctk.CTkSlider(f, from_=min_val, to=max_val, number_of_steps=steps)
            slider.set(getattr(config, key))
            slider.grid(row=i+1, column=1, sticky="ew", padx=(5, 5), pady=2)
            
            if "time" in key.lower():
                value_text = f"{getattr(config, key):.3f}s"
            elif "step" in key.lower():
                value_text = f"{getattr(config, key):.0f}px"
            else:
                value_text = f"{getattr(config, key):.2f}"
                
            value_label = ctk.CTkLabel(f, text=value_text, text_color=NEON, width=60, font=("Segoe UI", 11, "bold"))
            value_label.grid(row=i+1, column=2, padx=10, pady=2)
            
            def make_update_func(param_key, label_widget):
                def update_func(val):
                    setattr(config, param_key, float(val))
                    if "time" in param_key.lower():
                        text = f"{float(val):.3f}s"
                        if param_key == "smooth_reaction_max":
                            config.smooth_reaction_min = float(val) * 0.7
                    elif "step" in param_key.lower():
                        text = f"{float(val):.0f}px"
                    else:
                        text = f"{float(val):.2f}"
                    label_widget.configure(text=text)
                return update_func
            
            slider.configure(command=make_update_func(key, value_label))
        
        # X/Y movement toggles
        xy_frame = ctk.CTkFrame(f, fg_color="transparent")
        xy_frame.grid(row=len(params)+2, column=0, columnspan=3, sticky="ew", padx=10, pady=(5, 10))

        def create_toggle(parent, text, config_key, var):
            def on_toggle():
                setattr(config, config_key, var.get())
                config.save() # Save changes immediately
            ctk.CTkSwitch(parent, text=text, variable=var, command=on_toggle, text_color="#fff")\
                .pack(side="left", padx=10)

        create_toggle(xy_frame, "Enable X", "smooth_enable_x", self.smooth_enable_x_var)
        create_toggle(xy_frame, "Enable Y", "smooth_enable_y", self.smooth_enable_y_var)

    def add_gan_section(self):
        """GAN-Aimbot Research Based Settings (Dynamic Section)"""
        # Debug: Creating GAN dynamic section (removed for cleaner output)
        f = ctk.CTkFrame(self.dynamic_frame, fg_color="#0d1117", corner_radius=15, border_width=2, border_color="#ff6b35")
        f.pack(fill="x", pady=5)
        f.grid_columnconfigure((1,3), weight=1)
        
        # Research-inspired header
        header_frame = ctk.CTkFrame(f, fg_color="#ff6b35", corner_radius=10)
        header_frame.grid(row=0, column=0, columnspan=4, sticky="ew", padx=10, pady=(10, 10))
        
        ctk.CTkLabel(header_frame, text="🧠 GAN-Aimbot: Human-like Movement", 
                    font=("Segoe UI", 14, "bold"), text_color="#000").pack(pady=8)
        
        # Human Behavior Simulation
        behavior_frame = ctk.CTkFrame(f, fg_color="#1c2128", corner_radius=8)
        behavior_frame.grid(row=1, column=0, columnspan=4, sticky="ew", padx=10, pady=(0, 10))
        behavior_frame.grid_columnconfigure((1,3), weight=1)
        
        ctk.CTkLabel(behavior_frame, text="🎯 Human Behavior Simulation", font=("Segoe UI", 12, "bold"),
                    text_color="#58a6ff").grid(row=0, column=0, columnspan=4, padx=10, pady=(10, 5), sticky="w")
        
        # Movement Variability
        ctk.CTkLabel(behavior_frame, text="🌊 Variability:", font=("Segoe UI", 11, "bold"), 
                    text_color="#f85149").grid(row=1, column=0, padx=(15,5), pady=5, sticky="w")
        self.gan_variability_slider = ctk.CTkSlider(behavior_frame, from_=0.0, to=2.0, number_of_steps=200,
                                                   command=self.update_movement_variability, button_color="#f85149", progress_color="#f85149")
        self.gan_variability_slider.set(getattr(config, "movement_variability", 0.3))
        self.gan_variability_slider.grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        self.gan_variability_value = ctk.CTkLabel(behavior_frame, text="0.30", text_color="#f85149", width=40)
        self.gan_variability_value.grid(row=1, column=2, padx=5, pady=5)
        
        # Reaction Delay
        ctk.CTkLabel(behavior_frame, text="⏱️ Reaction (ms):", font=("Segoe UI", 11, "bold"), 
                    text_color="#a5a5a5").grid(row=1, column=3, padx=(15,5), pady=5, sticky="w")
        self.gan_reaction_slider = ctk.CTkSlider(behavior_frame, from_=0, to=200, number_of_steps=200,
                                                command=self.update_reaction_delay, button_color="#a5a5a5", progress_color="#a5a5a5")
        self.gan_reaction_slider.set(getattr(config, "human_reaction_delay_ms", 50))
        self.gan_reaction_slider.grid(row=1, column=4, sticky="ew", padx=5, pady=5)
        self.gan_reaction_value = ctk.CTkLabel(behavior_frame, text="50", text_color="#a5a5a5", width=40)
        self.gan_reaction_value.grid(row=1, column=5, padx=5, pady=5)
        
        # Overshoot and Performance
        ctk.CTkLabel(behavior_frame, text="🎯 Overshoot (%):", font=("Segoe UI", 11, "bold"), 
                    text_color="#7ee787").grid(row=2, column=0, padx=(15,5), pady=5, sticky="w")
        self.gan_overshoot_slider = ctk.CTkSlider(behavior_frame, from_=0, to=50, number_of_steps=50,
                                                 command=self.update_overshoot_chance, button_color="#7ee787", progress_color="#7ee787")
        self.gan_overshoot_slider.set(getattr(config, "overshoot_chance_percent", 15))
        self.gan_overshoot_slider.grid(row=2, column=1, sticky="ew", padx=5, pady=5)
        self.gan_overshoot_value = ctk.CTkLabel(behavior_frame, text="15", text_color="#7ee787", width=40)
        self.gan_overshoot_value.grid(row=2, column=2, padx=5, pady=5)
        
        # Performance Variation
        ctk.CTkLabel(behavior_frame, text="📊 Perf. Variation:", font=("Segoe UI", 11, "bold"), 
                    text_color="#ff7b72").grid(row=2, column=3, padx=(15,5), pady=5, sticky="w")
        self.gan_performance_slider = ctk.CTkSlider(behavior_frame, from_=0.0, to=0.5, number_of_steps=50,
                                                   command=self.update_performance_variation, button_color="#ff7b72", progress_color="#ff7b72")
        self.gan_performance_slider.set(getattr(config, "performance_variation", 0.15))
        self.gan_performance_slider.grid(row=2, column=4, sticky="ew", padx=5, pady=5)
        self.gan_performance_value = ctk.CTkLabel(behavior_frame, text="0.15", text_color="#ff7b72", width=40)
        self.gan_performance_value.grid(row=2, column=5, padx=5, pady=5)
        
        # Micro-corrections and Miss Rate
        ctk.CTkLabel(behavior_frame, text="🔧 Micro-corrections:", font=("Segoe UI", 11, "bold"), 
                    text_color="#ffa657").grid(row=3, column=0, padx=(15,5), pady=5, sticky="w")
        self.gan_micro_slider = ctk.CTkSlider(behavior_frame, from_=0.0, to=1.0, number_of_steps=100,
                                             command=self.update_micro_corrections, button_color="#ffa657", progress_color="#ffa657")
        self.gan_micro_slider.set(getattr(config, "micro_corrections_intensity", 0.4))
        self.gan_micro_slider.grid(row=3, column=1, sticky="ew", padx=5, pady=5)
        self.gan_micro_value = ctk.CTkLabel(behavior_frame, text="0.40", text_color="#ffa657", width=40)
        self.gan_micro_value.grid(row=3, column=2, padx=5, pady=5)
        
        # Intentional Miss
        ctk.CTkLabel(behavior_frame, text="🎯 Miss Rate (%):", font=("Segoe UI", 11, "bold"), 
                    text_color="#f0883e").grid(row=3, column=3, padx=(15,5), pady=(5,15), sticky="w")
        self.gan_miss_slider = ctk.CTkSlider(behavior_frame, from_=0, to=20, number_of_steps=20,
                                            command=self.update_intentional_miss, button_color="#f0883e", progress_color="#f0883e")
        self.gan_miss_slider.set(getattr(config, "intentional_miss_percent", 5))
        self.gan_miss_slider.grid(row=3, column=4, sticky="ew", padx=5, pady=(5,15))
        self.gan_miss_value = ctk.CTkLabel(behavior_frame, text="5", text_color="#f0883e", width=40)
        self.gan_miss_value.grid(row=3, column=5, padx=5, pady=(5,15))
        
        # GAN Presets
        preset_frame = ctk.CTkFrame(f, fg_color="#1a1a1a", corner_radius=8)
        preset_frame.grid(row=2, column=0, columnspan=4, sticky="ew", padx=10, pady=(0, 10))
        
        ctk.CTkLabel(preset_frame, text="🎮 GAN Presets:", font=("Segoe UI", 11, "bold"),
                    text_color="#fff").pack(side="left", padx=10, pady=8)
        
        # Preset buttons
        preset_btns = ctk.CTkFrame(preset_frame, fg_color="transparent")
        preset_btns.pack(side="left", padx=10, pady=5)
        
        ctk.CTkButton(preset_btns, text="🎯 Legit", width=60, height=25, 
                     command=self.set_gan_legit_preset, font=("Segoe UI", 10)).pack(side="left", padx=2)
        ctk.CTkButton(preset_btns, text="⚡ Rage", width=60, height=25,
                     command=self.set_gan_rage_preset, font=("Segoe UI", 10)).pack(side="left", padx=2)
        ctk.CTkButton(preset_btns, text="👤 Human", width=60, height=25,
                     command=self.set_gan_human_preset, font=("Segoe UI", 10)).pack(side="left", padx=2)
        ctk.CTkButton(preset_btns, text="🧠 Ultra-Human", width=80, height=25,
                     command=self.set_gan_ultra_human_preset, font=("Segoe UI", 10)).pack(side="left", padx=2)

    def get_profile_list(self):
        """Get list of available profiles"""
        profiles = self.config_manager.get_config_files()
        return profiles if profiles else ["config_profile"]
    
    def on_profile_select(self, profile_name):
        """Handle profile selection from dropdown"""
        if profile_name and profile_name != self.current_config_name.get():
            self.current_config_name.set(profile_name)
            self.profile_var.set(profile_name)
    
    def create_profile_dialog(self):
        """Show dialog to create a new profile"""
        dialog = ctk.CTkInputDialog(text="Enter new profile name:", title="Create Profile")
        profile_name = dialog.get_input()
        
        if profile_name and profile_name.strip():
            profile_name = profile_name.strip()
            
            # Check if profile already exists
            if self.config_manager.config_exists(profile_name):
                messagebox.showerror("Error", f"Profile '{profile_name}' already exists!")
                return
            
            # Create new profile with current config data
            config_data = self.get_current_config_data()
            if self.config_manager.create_config(profile_name, config_data):
                self.refresh_profile_list()
                self.current_config_name.set(profile_name)
                self.profile_var.set(profile_name)
                self.profile_menu.set(profile_name)
                self.error_text.set(f"✅ Profile '{profile_name}' created successfully!")
            else:
                self.error_text.set(f"❌ Failed to create profile '{profile_name}'")
    
    def rename_profile_dialog(self):
        """Show dialog to rename current profile"""
        current_profile = self.current_config_name.get()
        if not current_profile or current_profile == "config_profile":
            messagebox.showwarning("Warning", "Cannot rename the default profile. Create a new profile first.")
            return
        
        dialog = ctk.CTkInputDialog(text=f"Rename '{current_profile}' to:", title="Rename Profile")
        new_name = dialog.get_input()
        
        if new_name and new_name.strip():
            new_name = new_name.strip()
            
            if new_name == current_profile:
                return  # Same name, nothing to do
            
            # Check if new name already exists
            if self.config_manager.config_exists(new_name):
                messagebox.showerror("Error", f"Profile '{new_name}' already exists!")
                return
            
            # Rename the profile
            if self.config_manager.rename_config(current_profile, new_name):
                self.refresh_profile_list()
                self.current_config_name.set(new_name)
                self.profile_var.set(new_name)
                self.profile_menu.set(new_name)
                self.error_text.set(f"✅ Profile renamed to '{new_name}' successfully!")
            else:
                self.error_text.set(f"❌ Failed to rename profile to '{new_name}'")
    
    def delete_profile_dialog(self):
        """Show dialog to delete current profile"""
        current_profile = self.current_config_name.get()
        if not current_profile or current_profile == "config_profile":
            messagebox.showwarning("Warning", "Cannot delete the default profile.")
            return
        
        # Confirm deletion
        result = messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete profile '{current_profile}'?\n\nThis action cannot be undone.")
        
        if result:
            if self.config_manager.delete_config(current_profile):
                self.refresh_profile_list()
                # Switch to default profile
                self.current_config_name.set("config_profile")
                self.profile_var.set("config_profile")
                self.profile_menu.set("config_profile")
                self.error_text.set(f"✅ Profile '{current_profile}' deleted successfully!")
            else:
                self.error_text.set(f"❌ Failed to delete profile '{current_profile}'")
    
    def save_current_profile(self):
        """Save current settings to the selected profile"""
        profile_name = self.current_config_name.get()
        config_data = self.get_current_config_data()
        
        if self.config_manager.save_config(profile_name, config_data):
            self.error_text.set(f"✅ Profile '{profile_name}' saved successfully!")
        else:
            self.error_text.set(f"❌ Failed to save profile '{profile_name}'")
    
    def load_selected_profile(self):
        """Load the selected profile"""
        profile_name = self.profile_var.get()
        if not profile_name:
            return
        
        config_data = self.config_manager.load_config(profile_name)
        if config_data:
            self.apply_config_data(config_data)
            self.current_config_name.set(profile_name)
            self.refresh_all()
            self.error_text.set(f"✅ Profile '{profile_name}' loaded successfully!")
        else:
            self.error_text.set(f"❌ Failed to load profile '{profile_name}'")
    
    def get_current_config_data(self):
        """Get current configuration as dictionary"""
        return config.__dict__.copy()
    
    def apply_config_data(self, config_data):
        """Apply configuration data to current config"""
        # Remove metadata if present
        if '_metadata' in config_data:
            del config_data['_metadata']
        
        # Update config object
        for key, value in config_data.items():
            if hasattr(config, key):
                setattr(config, key, value)
        
        # Ensure button masking values are properly set
        if 'aim_button_mask' in config_data:
            config.aim_button_mask = bool(config_data['aim_button_mask'])
        if 'trigger_button_mask' in config_data:
            config.trigger_button_mask = bool(config_data['trigger_button_mask'])
        
        # Debug: Print button masking values after loading
        # Debug: After loading profile status (removed for cleaner output)
    
    def refresh_profile_list(self):
        """Refresh the profile dropdown list"""
        try:
            profiles = self.get_profile_list()
            self.profile_menu.configure(values=profiles)
            
            # Ensure current selection is valid
            current = self.current_config_name.get()
            if current not in profiles:
                self.current_config_name.set("config_profile")
                self.profile_var.set("config_profile")
                self.profile_menu.set("config_profile")
        except Exception as e:
            print(f"[WARN] Failed to refresh profile list: {e}")

    def reset_defaults(self):
        config.reset_to_defaults()
        self.refresh_all()
        self.error_text.set("✅ Settings reset to defaults!")

    def start_aimbot(self):
        start_aimbot()
        
        # Automatically enable debug window when aimbot starts
        config.show_debug_window = True
        self.debug_checkbox_var.set(True)
        print("[INFO] Debug window enabled automatically")
        
        button_names = ["Left", "Right", "Middle", "Side 4", "Side 5"]
        button_name = button_names[config.selected_mouse_button] if config.selected_mouse_button < len(button_names) else f"Button {config.selected_mouse_button}"
        self.error_text.set(f"🎯 Aimbot started with debug window! Hold {button_name} to aim.")

    def stop_aimbot(self):
        stop_aimbot()
        self.aimbot_status.set("Stopped")
        self.error_text.set("⏹ Aimbot stopped.")

    def on_close(self):
        stop_aimbot()
        self.destroy()

    def on_debug_toggle(self):
        config.show_debug_window = self.debug_checkbox_var.get()
        if not config.show_debug_window:
            # Just set the flag, let the detection thread handle window cleanup
            # to avoid thread synchronization issues with OpenCV
            print("[INFO] Debug window closing requested via GUI")
        else:
            # Start monitoring debug window status
            self.after(1000, self._check_debug_window_status)
        
        # Update text info checkbox visibility
        self._update_debug_text_info_visibility()
        
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save debug window setting: {e}")
    
    def on_debug_text_info_toggle(self):
        """Toggle text information display in debug window"""
        config.show_debug_text_info = bool(self.debug_text_info_var.get())
        status = "enabled" if config.show_debug_text_info else "disabled"
        print(f"[INFO] Debug text info {status}")
        
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save debug_text_info: {e}")
    
    def on_debug_always_on_top_toggle(self):
        """Toggle debug window always on top functionality"""
        config.debug_always_on_top = bool(self.debug_always_on_top_var.get())
        status = "enabled" if config.debug_always_on_top else "disabled"
        print(f"[INFO] Debug window always on top {status}")
        
        # If debug window is currently open, apply the setting immediately
        if config.show_debug_window and WIN32_AVAILABLE:
            try:
                hwnd = win32gui.FindWindow(None, "AI Debug")
                if hwnd:
                    if config.debug_always_on_top:
                        win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, 
                                            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
                        print("[INFO] Debug window set to always on top")
                    else:
                        win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0, 
                                            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
                        print("[INFO] Debug window removed from always on top")
            except Exception as e:
                print(f"[WARN] Could not apply always on top setting: {e}")
        
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save debug_always_on_top: {e}")
    
    def _update_debug_text_info_visibility(self):
        """Show/hide debug sub-options based on debug window state"""
        try:
            if self.debug_checkbox_var.get():
                # Show debug sub-options when debug window is enabled
                self.debug_text_info_checkbox.grid()
                self.debug_always_on_top_checkbox.grid()
            else:
                # Hide debug sub-options when debug window is disabled
                self.debug_text_info_checkbox.grid_remove()
                self.debug_always_on_top_checkbox.grid_remove()
        except Exception:
            pass
    
    def _check_debug_window_status(self):
        """Periodically check if debug window was closed externally"""
        try:
            if self.debug_checkbox_var.get() and not config.show_debug_window:
                # Debug window was closed externally, update GUI
                self.debug_checkbox_var.set(False)
                self._update_debug_text_info_visibility()
                print("[INFO] Debug window was closed externally")
            elif self.debug_checkbox_var.get():
                # Continue monitoring if debug window is still supposed to be open
                self.after(1000, self._check_debug_window_status)
        except Exception:
            pass

    def on_input_check_toggle(self):
        if self.input_check_var.get():
            self.show_input_check_window()
        else:
            self.hide_input_check_window()
    def on_aim_button_mask_toggle(self):
        value = bool(self.aim_button_mask_var.get())
        config.aim_button_mask = value
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save config.aim_button_mask: {e}")

    def on_trigger_button_mask_toggle(self):
        value = bool(self.trigger_button_mask_var.get())
        config.trigger_button_mask = value
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save config.trigger_button_mask: {e}")

    def show_input_check_window(self):
        if hasattr(self, 'input_check_window') and self.input_check_window is not None:
            return
        self.input_check_window = ctk.CTkToplevel(self)
        self.input_check_window.title("Button States Monitor")
        self.input_check_window.geometry("320x240")
        self.input_check_window.resizable(False, False)
        self.input_check_window.configure(fg_color="#181818")
        
        ctk.CTkLabel(self.input_check_window, text="🎮 Input Monitor", font=("Segoe UI", 16, "bold"), text_color="#00e676").pack(pady=(15, 10))
        
        self.input_check_labels = []
        for i in range(5):
            frame = ctk.CTkFrame(self.input_check_window, fg_color="transparent")
            frame.pack(pady=3, padx=20, fill="x")
            
            ctk.CTkLabel(frame, text=f"Button {i}:", font=("Segoe UI", 12, "bold"), text_color="#fff").pack(side="left")
            
            lbl = ctk.CTkLabel(frame, text="Released", font=("Segoe UI", 12, "bold"), text_color="#FF5555")
            lbl.pack(side="right")
            
            self.input_check_labels.append(lbl)
        
        self.update_input_check_window()
        self.input_check_window.protocol("WM_DELETE_WINDOW", self._on_input_check_close)

    def update_input_check_window(self):
        if not hasattr(self, 'input_check_window') or self.input_check_window is None:
            return
        
        from mouse import button_states, button_states_lock
        
        with button_states_lock:
            for i, lbl in enumerate(self.input_check_labels):
                state = button_states.get(i, False)
                color = "#00FF00" if state else "#FF5555"
                text = "PRESSED" if state else "Released"
                lbl.configure(text=text, text_color=color)
        
        self.after(50, self.update_input_check_window)

    def hide_input_check_window(self):
        if hasattr(self, 'input_check_window') and self.input_check_window:
            self.input_check_window.destroy()
            self.input_check_window = None

    def _on_input_check_close(self):
        self.input_check_var.set(False)
        self.hide_input_check_window()

    # --- Sync Functions for X/Y Settings ---
    def on_fov_sync_toggle(self):
        """Toggle FOV sync mode."""
        config.fov_sync_enabled = self.fov_sync_var.get()
        config.save()
        if self.fov_sync_var.get():
            # Enable sync - sync Y to X
            self._sync_fov_y_to_x()
        else:
            print("[SYNC] FOV sync disabled")

    def on_smoothing_sync_toggle(self):
        """Toggle smoothing sync mode."""
        config.smoothing_sync_enabled = self.smoothing_sync_var.get()
        config.save()
        if self.smoothing_sync_var.get():
            # Enable sync - sync Y to X
            self._sync_smoothing_y_to_x()
        else:
            print("[SYNC] Smoothing sync disabled")

    def on_rcs_strength_sync_toggle(self):
        """Toggle RCS strength sync mode."""
        config.rcs_strength_sync_enabled = self.rcs_strength_sync_var.get()
        config.save()
        if self.rcs_strength_sync_var.get():
            # Enable sync - sync Y to X
            self._sync_rcs_strength_y_to_x()
        else:
            print("[SYNC] RCS strength sync disabled")

    def on_rcs_delay_sync_toggle(self):
        """Toggle RCS delay sync mode."""
        config.rcs_delay_sync_enabled = self.rcs_delay_sync_var.get()
        config.save()
        if self.rcs_delay_sync_var.get():
            # Enable sync - sync Y to X
            self._sync_rcs_delay_y_to_x()
        else:
            print("[SYNC] RCS delay sync disabled")

    def _sync_fov_y_to_x(self):
        """Sync FOV Y to match FOV X value."""
        try:
            x_value = self.fov_x_slider.get()
            self.fov_y_slider.set(x_value)
            self._set_entry_text(self.fov_y_entry, str(int(x_value)))
            config.fov_y_size = int(x_value)
            config.save()
            print(f"[SYNC] FOV Y synced to X value: {int(x_value)}")
        except Exception as e:
            print(f"[WARN] Failed to sync FOV values: {e}")

    def _sync_fov_x_to_y(self, y_value):
        """Sync FOV X to match FOV Y value."""
        try:
            self.fov_x_slider.set(y_value)
            self._set_entry_text(self.fov_x_entry, str(int(y_value)))
            config.fov_x_size = int(y_value)
            config.save()
            print(f"[SYNC] FOV X synced to Y value: {int(y_value)}")
        except Exception as e:
            print(f"[WARN] Failed to sync FOV X to Y: {e}")

    def _sync_smoothing_y_to_x(self):
        """Sync Y smoothing to match X smoothing value."""
        try:
            x_value = self.in_game_sens_x_slider.get()
            self.in_game_sens_y_slider.set(x_value)
            self.in_game_sens_y_value.configure(text=f"{x_value:.2f}")
            config.in_game_sens_y = x_value
            config.save()
            print(f"[SYNC] Y smoothing synced to X value: {x_value:.2f}")
        except Exception as e:
            print(f"[WARN] Failed to sync smoothing values: {e}")

    def _sync_smoothing_x_to_y(self, y_value):
        """Sync X smoothing to match Y smoothing value."""
        try:
            self.in_game_sens_x_slider.set(y_value)
            self.in_game_sens_x_value.configure(text=f"{y_value:.2f}")
            config.in_game_sens_x = y_value
            config.save()
            print(f"[SYNC] X smoothing synced to Y value: {y_value:.2f}")
        except Exception as e:
            print(f"[WARN] Failed to sync X smoothing to Y: {e}")

    def _sync_rcs_strength_y_to_x(self):
        """Sync RCS Y strength to match X strength value."""
        try:
            x_value = self.rcs_x_strength_slider.get()
            self.rcs_y_strength_slider.set(x_value)
            self.rcs_y_strength_entry.delete(0, "end")
            self.rcs_y_strength_entry.insert(0, f"{x_value:.2f}")
            config.rcs_y_random_strength = x_value
            config.save()
            print(f"[SYNC] RCS Y strength synced to X value: {x_value:.2f}")
        except Exception as e:
            print(f"[WARN] Failed to sync RCS strength values: {e}")

    def _sync_rcs_strength_x_to_y(self, y_value):
        """Sync RCS X strength to match Y strength value."""
        try:
            self.rcs_x_strength_slider.set(y_value)
            self.rcs_x_strength_entry.delete(0, "end")
            self.rcs_x_strength_entry.insert(0, f"{y_value:.2f}")
            config.rcs_x_strength = y_value
            config.save()
            print(f"[SYNC] RCS X strength synced to Y value: {y_value:.2f}")
        except Exception as e:
            print(f"[WARN] Failed to sync RCS X strength to Y: {e}")

    def _sync_rcs_delay_y_to_x(self):
        """Sync RCS Y delay to match X delay value."""
        try:
            x_value = self.rcs_x_delay_slider.get()
            self.rcs_y_delay_slider.set(x_value)
            self.rcs_y_delay_entry.delete(0, "end")
            self.rcs_y_delay_entry.insert(0, f"{int(x_value)}")
            config.rcs_y_random_delay = x_value / 1000.0  # Convert back to seconds
            config.save()
            print(f"[SYNC] RCS Y delay synced to X value: {int(x_value)}ms")
        except Exception as e:
            print(f"[WARN] Failed to sync RCS delay values: {e}")

    def _sync_rcs_delay_x_to_y(self, y_value):
        """Sync RCS X delay to match Y delay value."""
        try:
            self.rcs_x_delay_slider.set(y_value)
            self.rcs_x_delay_entry.delete(0, "end")
            self.rcs_x_delay_entry.insert(0, f"{int(y_value)}")
            config.rcs_x_delay = y_value / 1000.0  # Convert back to seconds
            config.save()
            print(f"[SYNC] RCS X delay synced to Y value: {int(y_value)}ms")
        except Exception as e:
            print(f"[WARN] Failed to sync RCS X delay to Y: {e}")

    # --- Secondary Aim Keybind Functions ---
    def on_secondary_aim_enabled_toggle(self):
        """Toggle secondary aim keybind."""
        config.secondary_aim_enabled = self.secondary_aim_enabled_var.get()
        config.save()
        if self.secondary_aim_enabled_var.get():
            print("[SECONDARY AIM] Secondary aim keybind enabled")
        else:
            print("[SECONDARY AIM] Secondary aim keybind disabled")

    def update_secondary_aim_button(self):
        """Update secondary aim button selection."""
        config.secondary_aim_button = int(self.secondary_aim_button_var.get())
        config.save()
        print(f"[SECONDARY AIM] Secondary aim button set to: {config.secondary_aim_button}")


if __name__ == "__main__":
    app = EventuriGUI()
    app.mainloop()