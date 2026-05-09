import os
import json
import ctypes
import numpy as np
from ctypes import wintypes

# Structures
class RECT(ctypes.Structure):
    _fields_ = [
        ("left",   ctypes.c_long),
        ("top",    ctypes.c_long),
        ("right",  ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]

class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize",   ctypes.c_ulong),
        ("rcMonitor", RECT),
        ("rcWork",    RECT),
        ("dwFlags",   ctypes.c_ulong),
    ]

def get_foreground_monitor_resolution():
    # DPI awareness so we get actual pixels
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    user32 = ctypes.windll.user32
    monitor = user32.MonitorFromWindow(user32.GetForegroundWindow(), 2)  # MONITOR_DEFAULTTONEAREST = 2
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)

    if ctypes.windll.user32.GetMonitorInfoW(monitor, ctypes.byref(mi)):
        w = mi.rcMonitor.right - mi.rcMonitor.left
        h = mi.rcMonitor.bottom - mi.rcMonitor.top
        return w, h
    else:
        # fallback to primary if anything fails
        return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)

w, h = get_foreground_monitor_resolution()

class Config:
    def __init__(self):
        # --- General Settings ---
        self.region_size = 200
        self.scan_size   = 256
        w, h = get_foreground_monitor_resolution()
        self.screen_width = w # Revert to original
        self.screen_height = h  # Revert to original
        self.player_y_offset = 5 # Offset for player detection
        self.capturer_mode = "capturecard"  # Default to CaptureCard mode
        self.always_on_aim = False
        self.main_pc_width = 1920  # Default width for main PC
        self.main_pc_height = 1080  # Default height for main PC
        
        # New additions from provided SRC
        self.fov_x_size = 200   # FOV X-axis size
        self.fov_y_size = 200   # FOV Y-axis size

        # --- Height Targeting System ---
        self.height_targeting_enabled = True  # Enable height targeting system
        self.target_height = 0.700  # Target height on player (0.100=bottom, 1.000=top)
        self.height_deadzone_enabled = False  # Disable height deadzone for GAN mode testing
        self.height_deadzone_min = 0.600  # Lower bound of deadzone
        self.height_deadzone_max = 0.800  # Upper bound of deadzone
        self.height_deadzone_x_only = True  # Only move X-axis in deadzone
        self.height_deadzone_tolerance = 5.000  # Pixels of tolerance for full entry (higher = need to be deeper inside)
        
        # --- X-Axis Center Targeting ---
        self.x_center_targeting_enabled = False  # Enable X-axis center targeting
        self.x_center_tolerance_percent = 10.0   # Tolerance percentage for X-center targeting (0-50%)
        
        # --- Mouse Movement Multiplier ---
        self.mouse_movement_multiplier = 1.0     # Mouse movement speed multiplier (0.1-5.0) - kept for backward compatibility
        self.mouse_movement_multiplier_x = 1.0   # Mouse movement speed multiplier for X-axis (0.0-5.0)
        self.mouse_movement_multiplier_y = 1.0   # Mouse movement speed multiplier for Y-axis (0.0-5.0)
        self.mouse_movement_enabled_x = True     # Enable/disable X-axis movement (True/False)
        self.mouse_movement_enabled_y = True     # Enable/disable Y-axis movement (True/False)
        self.mouse_movement_sync_enabled = False # Sync X/Y multipliers together
        
        # --- RCS (Recoil Control System) ---
        self.rcs_enabled = False                 # Enable RCS functionality
        self.rcs_ads_only = False               # Enable RCS only when ADS (right mouse button held)
        self.rcs_x_strength = 1.0               # X-axis recoil compensation strength (0.1-5.0)
        self.rcs_x_delay = 0.010                # X-axis recoil compensation delay in seconds (0.001-0.100)
        self.rcs_y_random_enabled = False       # Enable Y-axis random jitter
        self.rcs_y_random_strength = 0.5        # Y-axis random jitter strength (0.1-3.0)
        self.rcs_y_random_delay = 0.020         # Y-axis random jitter delay in seconds (0.001-0.100)

        # --- Capture card settings ---
        # Camera/device index to open with OpenCV (0 is typical)
        self.capture_device_index = 0
        # Desired input mode for the capture card
        self.capture_width  = 1920
        self.capture_height = 1080
        self.capture_fps    = 240  # Capture card FPS limit (doesn't affect true performance)
        self.show_true_fps  = True  # Show true FPS instead of capture-limited FPS
        # Preferred pixel formats to try in order (drivers may ignore)
        self.capture_fourcc_preference = ["NV12", "YUY2", "MJPG"]

        # --- Model and Detection ---
        self.models_dir = "models"
        self.model_path = os.path.join(self.models_dir, "Click here to Load a model")
        self.custom_player_label = "Select a Player Class"  
        self.custom_head_label = "Select a Head Class"  
        self.model_file_size = 0
        self.model_load_error = ""
        self.conf = 0.2
        self.imgsz = 640
        self.max_detect = 50
        
        # --- Mouse / MAKCU ---
        self.selected_mouse_button = 3   # Default to middle mouse button
        self.makcu_connected = False # Updated to reflect device type
        self.makcu_status_msg = "Disconnected"  # Updated to reflect device type
        self.aim_humanization = 0 # Default to no humanization
        self.in_game_sens = 1.3 # Default smoothing
        self.in_game_sens_x = 1.3 # X-axis specific smoothing
        self.in_game_sens_y = 1.3 # Y-axis specific smoothing
        self.aim_button_mask = False
        self.trigger_button_mask = False

        # --- Trigger Settings ---
        self.trigger_enabled         = getattr(self, "trigger_enabled", False)   # master on/off
        self.trigger_always_on       = getattr(self, "trigger_always_on", False) # fire even without holding key
        self.trigger_button          = getattr(self, "trigger_button", 1)        # 0..4 -> Left, Right, Middle, Side4, Side5

        self.trigger_radius_px       = getattr(self, "trigger_radius_px", 8)     # how close to crosshair (px)
        self.trigger_delay_ms        = getattr(self, "trigger_delay_ms", 30)     # delay before click
        self.trigger_cooldown_ms     = getattr(self, "trigger_cooldown_ms", 120) # time between clicks
        self.trigger_min_conf        = getattr(self, "trigger_min_conf", 0.35)   # min conf to shoot
        self.trigger_burst_count     = getattr(self, "trigger_burst_count", 3)   # shots before cooldown (Mode 2)

        # --- Triggerbot Modes (Enhanced with CH341PAR improvements) ---
        self.trigger_mode = getattr(self, "trigger_mode", "normal")   # Firing modes: spray, burst, normal
        self.trigger_detection_method = getattr(self, "trigger_detection_method", "ai")  # "ai" or "color" - detection method

        # --- Color Outline Filter (AI Enhancement) ---
        self.color_outline_filter_enabled = getattr(self, "color_outline_filter_enabled", False)  # Enable color outline filtering
        print(f"[DEBUG] Config: color_outline_filter_enabled = {self.color_outline_filter_enabled}")  # Debug output
        print(f"[DEBUG] Config: getattr result = {getattr(self, 'color_outline_filter_enabled', 'NOT_FOUND')}")  # Debug output
        self.outline_detection_radius = getattr(self, "outline_detection_radius", 3)  # Radius around target to check for outline (pixels)
        self.outline_min_pixels = getattr(self, "outline_min_pixels", 10)   # Minimum pixels that must match outline color (increased for stricter filtering)
        

        
        # Spray mode parameters
        self.spray_initial_delay_ms = 50
        self.spray_cooldown_ms = 80
        
        # Burst mode parameters
        self.burst_shots = 3
        self.burst_delay_ms = 40
        self.burst_cooldown_ms = 200
        self.burst_hold_duration_ms = 500  # How long to hold the button down in burst mode
        
        # Normal mode parameters
        self.normal_shot_delay_ms = 50  # Time between shots in normal mode
        
        # Target switching parameters
        self.target_switch_delay_ms = 100  # Delay when switching between targets
        
        # --- Mode 3 (Color) HSV Settings (CH341PAR improvements) ---
        self.trigger_hsv_h_min       = getattr(self, "trigger_hsv_h_min", 0)     # HSV H minimum value
        self.trigger_hsv_h_max       = getattr(self, "trigger_hsv_h_max", 179)   # HSV H maximum value
        self.trigger_hsv_s_min       = getattr(self, "trigger_hsv_s_min", 0)     # HSV S minimum value
        self.trigger_hsv_s_max       = getattr(self, "trigger_hsv_s_max", 255)   # HSV S maximum value
        self.trigger_hsv_v_min       = getattr(self, "trigger_hsv_v_min", 0)     # HSV V minimum value
        self.trigger_hsv_v_max       = getattr(self, "trigger_hsv_v_max", 255)   # HSV V maximum value
        self.trigger_color_radius_px = getattr(self, "trigger_color_radius_px", 20) # color detection radius
        self.trigger_color_delay_ms  = getattr(self, "trigger_color_delay_ms", 50)  # color trigger delay
        self.trigger_color_cooldown_ms = getattr(self, "trigger_color_cooldown_ms", 200) # color trigger cooldown
        
        # RGB color picker values (converted to HSV)
        self.target_color_r = 255       # Red component (0-255)
        self.target_color_g = 0         # Green component (0-255)
        self.target_color_b = 0         # Blue component (0-255)
        self.color_tolerance = 20       # HSV tolerance for color matching
        
        # --- GAN-Aimbot Research Based Settings ---
        self.gan_enable_x = getattr(self, "gan_enable_x", True)
        self.gan_enable_y = getattr(self, "gan_enable_y", True)
        
        # Human Behavior Simulation (Research findings)
        self.movement_variability = getattr(self, "movement_variability", 0.3)       # Gaussian noise injection (0.0-2.0)
        self.human_reaction_delay_ms = getattr(self, "human_reaction_delay_ms", 50)  # Natural human reaction delay (0-200ms)
        self.overshoot_chance_percent = getattr(self, "overshoot_chance_percent", 15) # Probability of overshooting target (0-50%)
        self.micro_corrections_intensity = getattr(self, "micro_corrections_intensity", 0.4) # Small adjustment intensity (0.0-1.0)
        
        # Advanced Movement Patterns (Research insights)
        self.trajectory_smoothness = getattr(self, "trajectory_smoothness", 0.8)     # Natural curve smoothness (0.1-2.0)
        self.fatigue_simulation = getattr(self, "fatigue_simulation", 0.2)           # Performance degradation over time (0.0-1.0)
        self.context_memory_frames = getattr(self, "context_memory_frames", 20)      # Frames to consider for movement context (5-50)
        
        # Anti-Detection Features (Research proven)
        self.performance_variation = getattr(self, "performance_variation", 0.15)    # Inconsistent performance simulation (0.0-0.5)
        self.intentional_miss_percent = getattr(self, "intentional_miss_percent", 5) # Intentional miss rate (0-20%)
        self.axis_independence = getattr(self, "axis_independence", 0.7)             # X/Y axis movement correlation (0.0-1.0)
        
        # Natural Movement Enhancement Parameters
        self.movement_smoothness = getattr(self, "movement_smoothness", 0.8)         # Smooth interpolation factor (0.0-1.0)
        self.hand_tremor_intensity = getattr(self, "hand_tremor_intensity", 0.02)    # Subtle hand tremor effect (0.0-0.1)
        self.natural_acceleration = getattr(self, "natural_acceleration", 0.3)       # Natural speed variation (0.0-1.0)
        
        # Advanced Humanization Parameters (Ultra-Human Preset)
        self.muscle_memory_strength = getattr(self, "muscle_memory_strength", 0.25)  # How much previous movements affect current (0.0-1.0)
        self.fatigue_simulation = getattr(self, "fatigue_simulation", 0.15)         # Performance degradation over time (0.0-1.0)
        self.context_awareness = getattr(self, "context_awareness", True)           # Movement depends on context (True/False)
        self.breathing_amplitude = getattr(self, "breathing_amplitude", 0.01)       # Subtle breathing effect (0.0-0.1)
        self.skill_level = getattr(self, "skill_level", 0.6)                       # Moderate skill level (0.0-1.0)
        self.consistency = getattr(self, "consistency", 0.75)                      # How consistent the player is (0.0-1.0)
        
        # Movement Context Tracking (Runtime variables)
        self.movement_context = getattr(self, "movement_context", "idle")          # Current movement type
        self.previous_movements = getattr(self, "previous_movements", [])          # Track recent movements for muscle memory
        self.session_duration = getattr(self, "session_duration", 0.0)             # Time since start
        self.fatigue_level = getattr(self, "fatigue_level", 0.0)                   # Current fatigue level
        self.breathing_cycle = getattr(self, "breathing_cycle", 0.0)               # Breathing cycle for natural variation
        self.heart_rate = getattr(self, "heart_rate", 70)                          # BPM for subtle effects


        # --- Aimbot Mode ---
        self.mode = "normal"    
        self.aimbot_running = False
        self.aimbot_status_msg = "Stopped"
        
        # --- Sync States ---
        self.fov_sync_enabled = getattr(self, "fov_sync_enabled", False)
        self.smoothing_sync_enabled = getattr(self, "smoothing_sync_enabled", False)
        self.rcs_strength_sync_enabled = getattr(self, "rcs_strength_sync_enabled", False)
        self.rcs_delay_sync_enabled = getattr(self, "rcs_delay_sync_enabled", False)
        
        # --- Secondary Aim Keybind ---
        self.secondary_aim_enabled = getattr(self, "secondary_aim_enabled", False)
        self.secondary_aim_button = getattr(self, "secondary_aim_button", 2)  # Default to Middle mouse

        # --- Normal Aim ---
        self.normal_x_speed = 0.5
        self.normal_y_speed = 0.5
        self.normal_enable_x = True
        self.normal_enable_y = True

        # --- Bezier Aim ---
        self.bezier_segments = 8
        self.bezier_ctrl_x = 16
        self.bezier_ctrl_y = 16
        self.bezier_enable_x = True
        self.bezier_enable_y = True

        # --- PID Aim (new) ---
        self.pid_p_min = getattr(self, "pid_p_min", 0.155)
        self.pid_p_max = getattr(self, "pid_p_max", 0.601)
        self.pid_p_slope = getattr(self, "pid_p_slope", 0.100)
        self.pid_i_max = getattr(self, "pid_i_max", 2.000)
        self.pid_d = getattr(self, "pid_d", 0.004)
        self.pid_max_pixel = getattr(self, "pid_max_pixel", 10)
        self.pid_segments_x = getattr(self, "pid_segments_x", 1)
        self.pid_segments_y = getattr(self, "pid_segments_y", 1)
        self.pid_x_speed = getattr(self, "pid_x_speed", 0.789)
        self.pid_y_speed = getattr(self, "pid_y_speed", 0.666)
        self.pid_max_pixels = getattr(self, "pid_max_pixels", 50)
        # PID runtime state
        self.pid_last_update_time = getattr(self, "pid_last_update_time", 0.0)
        self.pid_integral_x = getattr(self, "pid_integral_x", 0.0)
        self.pid_integral_y = getattr(self, "pid_integral_y", 0.0)
        self.pid_previous_error_x = getattr(self, "pid_previous_error_x", 0.0)
        self.pid_previous_error_y = getattr(self, "pid_previous_error_y", 0.0)

        # --- Silent Aim ---
        self.silent_segments = 7
        self.silent_ctrl_x = 18
        self.silent_ctrl_y = 18
        self.silent_speed = 3
        self.silent_cooldown = 0.18
        self.silent_enable_x = True
        self.silent_enable_y = True

        # --- Enhanced Silent Mode ---
        self.silent_strength = 1.000  # Silent mode strength (0.100 = weak, 3.000 = over-reach)
        self.silent_auto_fire = False  # Auto fire when reaching target
        self.silent_fire_delay = 0.010  # Delay before firing (seconds) - Optimized for speed
        self.silent_return_delay = 0.020  # Delay before returning to origin (seconds) - Optimized for speed
        self.silent_speed_mode = True  # Enable ultra-fast speed optimizations
        self.silent_use_bezier = False  # Use bezier curve movement instead of direct movement

        # --- Smooth Aim (WindMouse) ---
        self.smooth_gravity = 9.0          # Gravitational pull towards target (1-20)
        self.smooth_wind = 3.0             # Wind randomness effect (1-20)  
        self.smooth_min_delay = 0.0      # Minimum delay between steps (seconds)
        self.smooth_max_delay = 0.002     # Maximum delay between steps (seconds)
        self.smooth_max_step = 40.0        # Maximum pixels per step
        self.smooth_min_step = 2.0         # Minimum pixels per step
        self.smooth_max_step_ratio = 0.20   # Max step as ratio of total distance
        self.smooth_target_area_ratio = 0.06  # Stop when within this ratio of distance
        self.smooth_enable_x = True
        self.smooth_enable_y = True
        
        # Human-like behavior settings
        self.smooth_reaction_min = 0.05    # Min reaction time to new targets (seconds)
        self.smooth_reaction_max = 0.21    # Max reaction time to new targets (seconds)
        self.smooth_close_range = 35       # Distance considered "close" (pixels)
        self.smooth_far_range = 250        # Distance considered "far" (pixels) 
        self.smooth_close_speed = 0.8      # Speed multiplier when close to target
        self.smooth_far_speed = 1.00        # Speed multiplier when far from target
        self.smooth_acceleration = 1.15     # Acceleration curve strength
        self.smooth_deceleration = 1.05     # Deceleration curve strength
        self.smooth_fatigue_effect = 1.2   # How much fatigue affects shakiness
        self.smooth_micro_corrections = 0  # Small random corrections (pixels)

        # (Magnet Trigger removed)

        # --- Last error/status for GUI display
        self.last_error = ""
        self.last_info = ""

        # --- Debug window toggle ---
        self.show_debug_window = False
        self.show_debug_text_info = True  # Show text information in debug window
        self.debug_always_on_top = False  # Keep debug window always on top
        
        # --- GUI window settings ---
        self.always_on_top = False  # Keep main GUI window always on top

        # --- Ndi Settings ---
        self.ndi_width = 0
        self.ndi_height = 0
        self.ndi_sources = []
        self.ndi_selected_source = None
        
        # --- UDP Settings ---
        self.udp_ip = getattr(self, "udp_ip", "192.168.0.01")
        self.udp_port = getattr(self, "udp_port", 1234)
        self.udp_width = getattr(self, "udp_width", 1920)
        self.udp_height = getattr(self, "udp_height", 1080)
        self.udp_target_fps = getattr(self, "udp_target_fps", 60)

    # -- Profile functions --
    def save(self, path="config_profile.json"):
        data = self.__dict__.copy()
        
        # Convert numpy types to Python native types for JSON serialization
        for key, value in data.items():
            if hasattr(value, 'item'):  # numpy scalar
                data[key] = value.item()
            elif isinstance(value, (np.integer, np.floating)):
                data[key] = value.item()
            elif isinstance(value, np.ndarray):
                data[key] = value.tolist()
        
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    def load(self, path="config_profile.json"):
        if os.path.exists(path):
            with open(path, "r") as f:
                self.__dict__.update(json.load(f))
    def reset_to_defaults(self):
        self.__init__()

    # --- Utility ---
    def list_models(self):
        return [f for f in os.listdir(self.models_dir)
                if f.endswith(".engine")]

config = Config()