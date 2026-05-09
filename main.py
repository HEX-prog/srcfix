import numpy as np
import time
import threading
import math
from mouse import Mouse, is_button_pressed  # Use the thread-safe function
from capture import get_camera, get_region
from capture import get_camera
from detection import load_model, perform_detection
from config import config
from windmouse_smooth import smooth_aimer
import os
import math
import cv2
import queue
import random
from mouse import Mouse  # ensure we can call mask_manager_tick_multi
from safety_monitor import start_safety_monitoring, stop_safety_monitoring, update_frame_time
from human_gan_enhanced import apply_enhanced_human_movement, add_human_aiming_patterns, simulate_human_timing_delays

# Windows-specific imports for debug window always-on-top functionality
try:
    import win32gui
    import win32con
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False
    print("[INFO] win32gui not available - debug window always-on-top not supported")

# --- Global state for aimbot control ---
_aimbot_running = False
_aimbot_thread = None
_capture_thread = None
_smooth_thread = None
fps = 0
true_fps = 0  # True FPS counter that bypasses capture card limits
processing_fps = 0  # Actual processing FPS (uncapped by capture card)
frame_queue = queue.Queue(maxsize=1)
smooth_move_queue = queue.Queue(maxsize=10)  # Queue for smooth movements
makcu = None  # <-- Declare Mouse instance globally, will be initialized once
_last_trigger_time_ms = 0.0
_in_zone_since_ms = 0.0

# --- Global state for triggerbot modes ---
_last_shot_time_ms = 0.0
_burst_shots_fired = 0
_is_spraying = False # Track if spray mode is currently holding click
_is_burst_holding = False # Track if burst mode is currently holding click
_burst_hold_start_time = 0.0 # When burst hold started

# --- Target switching state ---
_last_target_id = None # Track last targeted enemy ID
_target_switch_time = 0.0 # When we last switched targets

# --- Enhanced Silent Mode state ---
_silent_original_pos = None  # Store original mouse position
_silent_in_progress = False  # Flag to indicate silent mode operation in progress
_silent_last_activation = 0.0  # Timestamp of last silent activation

# --- Magnet trigger state ---
_magnet_firing = False
_magnet_status = "INACTIVE"

# --- RCS (Recoil Control System) state ---
_rcs_running = False
_rcs_thread = None
_last_left_click_state = False
_rcs_active = False
_rcs_start_time = 0
_last_rcs_x_time = 0  # Last time X compensation was applied
_last_rcs_y_time = 0  # Last time Y jitter was applied
_rcs_accumulated_x = 0.0  # Accumulated fractional X movement
_rcs_accumulated_y = 0.0  # Accumulated fractional Y movement

def smooth_movement_loop():
    """
    Dedicated thread for executing smooth movements.
    This ensures movements are executed with precise timing.
    """
    global _aimbot_running, makcu
    print("[INFO] Smooth movement thread started")
    while _aimbot_running:
        try:
            # Get next movement from queue (blocking with timeout)
            move_data = smooth_move_queue.get(timeout=0.1)
            dx, dy, delay = move_data


            # Execute the movement
            makcu.move(dx, dy)

            # Wait for the specified delay
            if delay > 0:
                time.sleep(delay)

        except queue.Empty:
            # No movements in queue, continue
            continue
        except Exception as e:
            print(f"[ERROR] Smooth movement failed: {e}")
            time.sleep(0.01)

    print("[INFO] Smooth movement thread stopped")

def _now_ms():
    return time.perf_counter() * 1000.0

def apply_gan_enhancements(dx, dy):
    """
    Enhanced Human-like GAN Movement System
    Uses realistic human behaviors for indistinguishable movement
    """
    # Calculate movement characteristics
    movement_distance = math.sqrt(dx*dx + dy*dy)
    
    # Determine movement urgency based on distance and context
    if movement_distance > 200:
        urgency = 1.0  # High urgency for long flicks
    elif movement_distance > 100:
        urgency = 0.8  # Medium urgency
    elif movement_distance > 50:
        urgency = 0.6  # Low-medium urgency
    else:
        urgency = 0.4  # Low urgency for small adjustments
    
    # Apply enhanced human movement
    enhanced_dx, enhanced_dy = apply_enhanced_human_movement(dx, dy, movement_distance, urgency)
    
    # Add human aiming patterns
    enhanced_dx, enhanced_dy = add_human_aiming_patterns(enhanced_dx, enhanced_dy, 
                                                        target_size=movement_distance/4, 
                                                        is_tracking=movement_distance < 30)
    
    return enhanced_dx, enhanced_dy
    original_dx, original_dy = dx, dy
    movement_distance = math.sqrt(dx*dx + dy*dy)
    
    # Initialize movement tracking
    if not hasattr(config, 'movement_phase'):
        config.movement_phase = 0.0
    if not hasattr(config, 'path_phases'):
        config.path_phases = [0.0, 0.0, 0.0, 0.0, 0.0]  # 5 different path phases
    if not hasattr(config, 'path_weights'):
        config.path_weights = [0.3, 0.25, 0.2, 0.15, 0.1]  # Weights for each path
    if not hasattr(config, 'path_frequencies'):
        config.path_frequencies = [1.0, 2.3, 4.7, 8.1, 13.2]  # Different frequencies for each path
    
    # Update main movement phase
    config.movement_phase += random.uniform(0.05, 0.15)
    
    # Always apply complex path generation for any movement
    if movement_distance > 0:
        # Calculate movement direction and perpendicular
        dir_x = dx / movement_distance
        dir_y = dy / movement_distance
        
        # Perpendicular direction for natural curves
        perp_x = -dir_y
        perp_y = dir_x
        
        # Determine number of path segments based on distance
        # Minimum 3 segments, more for longer distances
        min_segments = 3
        max_segments = max(min_segments, int(movement_distance / 20) + 2)  # 1 segment per 20 pixels
        num_segments = min(max_segments, 8)  # Cap at 8 segments max
        
        # Debug output for path generation
        if random.random() < 0.1:  # 10% chance to show debug info
            # Debug: GAN Path calculation (removed for cleaner output)
            pass
        
        # Initialize path components
        total_dx = 0.0
        total_dy = 0.0
        
        # Generate multiple path segments along the movement trajectory
        for segment in range(num_segments):
            # Calculate segment position along the movement (0.0 to 1.0)
            segment_progress = segment / max(1, num_segments - 1)
            
            # Update individual path phase for this segment
            segment_phase = config.movement_phase + segment_progress * math.pi * 2
            
            # Randomize path characteristics for this segment
            base_amplitude = movement_distance * random.uniform(0.15, 0.6)  # Increased amplitude range
            # Amplitude varies along the path (stronger in middle, weaker at ends)
            amplitude_modifier = math.sin(segment_progress * math.pi) * 0.7 + 0.3  # Increased variation
            path_amplitude = base_amplitude * amplitude_modifier
            
            # Add extra randomization for more dramatic curves
            if random.random() < 0.3:  # 30% chance for extra dramatic curves
                path_amplitude *= random.uniform(1.5, 2.5)
            
            path_curve_type = random.choice(['sine', 'cosine', 'sawtooth', 'triangle', 'complex'])
            path_direction = random.choice([1, -1])  # Clockwise or counter-clockwise
            
            # Generate curve based on type
            if path_curve_type == 'sine':
                curve_value = math.sin(segment_phase) * path_amplitude
            elif path_curve_type == 'cosine':
                curve_value = math.cos(segment_phase) * path_amplitude
            elif path_curve_type == 'sawtooth':
                # Sawtooth wave
                phase = segment_phase % (2 * math.pi)
                curve_value = (phase / (2 * math.pi)) * path_amplitude * 2 - path_amplitude
            elif path_curve_type == 'triangle':
                # Triangle wave
                phase = segment_phase % (2 * math.pi)
                if phase < math.pi:
                    curve_value = (phase / math.pi) * path_amplitude * 2 - path_amplitude
                else:
                    curve_value = path_amplitude - ((phase - math.pi) / math.pi) * path_amplitude * 2
            else:  # complex
                # Complex wave combining multiple frequencies
                curve1 = math.sin(segment_phase) * path_amplitude * 0.6
                curve2 = math.cos(segment_phase * 2.3) * path_amplitude * 0.3
                curve3 = math.sin(segment_phase * 4.7) * path_amplitude * 0.1
                curve_value = curve1 + curve2 + curve3
            
            # Apply direction and add some randomness
            curve_value *= path_direction * random.uniform(0.4, 1.8)  # Increased randomness range
            
            # Add micro-variations specific to this segment
            micro_variation = random.gauss(0, path_amplitude * 0.25)  # Increased micro-variation
            curve_value += micro_variation
            
            # Add segment-specific noise
            segment_noise = random.gauss(0, movement_distance * 0.03)  # Increased segment noise
            curve_value += segment_noise
            
            # Add occasional dramatic curve changes
            if random.random() < 0.2:  # 20% chance for dramatic changes
                curve_value *= random.uniform(-2.0, 2.0)  # Can reverse direction dramatically
            
            # Calculate path offset for this segment
            path_dx = perp_x * curve_value
            path_dy = perp_y * curve_value
            
            # Weight segments (middle segments have more influence)
            segment_weight = 1.0
            if num_segments > 1:
                # Middle segments get higher weight
                distance_from_center = abs(segment_progress - 0.5) * 2  # 0 to 1
                segment_weight = 1.0 - (distance_from_center * 0.3)  # 0.7 to 1.0
            
            # Add to total with weight
            total_dx += path_dx * segment_weight
            total_dy += path_dy * segment_weight
        
        # Add some direct movement variation
        direct_variation_x = random.gauss(0, movement_distance * 0.08)  # Increased direct variation
        direct_variation_y = random.gauss(0, movement_distance * 0.08)
        
        # Add trajectory-based variation
        trajectory_variation_x = random.gauss(0, movement_distance * 0.05)  # Increased trajectory variation
        trajectory_variation_y = random.gauss(0, movement_distance * 0.05)
        
        # Add cross-axis movement for more complex paths
        cross_axis_strength = random.uniform(0.1, 0.4)
        cross_dx = random.gauss(0, movement_distance * cross_axis_strength)
        cross_dy = random.gauss(0, movement_distance * cross_axis_strength)
        
        # Combine all paths
        dx += total_dx + direct_variation_x + trajectory_variation_x + cross_dx
        dy += total_dy + direct_variation_y + trajectory_variation_y + cross_dy
    
    # Add realistic hand tremor
    tremor_intensity = getattr(config, "hand_tremor_intensity", 0.008)
    if tremor_intensity > 0 and movement_distance > 0:
        # Multi-frequency tremor
        tremor_1 = random.gauss(0, tremor_intensity * movement_distance)
        tremor_2 = random.gauss(0, tremor_intensity * movement_distance * 0.5)
        tremor_3 = random.gauss(0, tremor_intensity * movement_distance * 0.2)
        
        dx += tremor_1 + tremor_2 + tremor_3
        dy += tremor_1 + tremor_2 + tremor_3
    
    # Add breathing effect
    breathing_amplitude = getattr(config, "breathing_amplitude", 0.006)
    if breathing_amplitude > 0:
        config.breathing_cycle = getattr(config, "breathing_cycle", 0) + random.uniform(0.03, 0.07)
        breathing_effect = math.sin(config.breathing_cycle) * breathing_amplitude * movement_distance
        dx += breathing_effect * random.uniform(-0.3, 0.3)
        dy += breathing_effect * random.uniform(-0.3, 0.3)
    
    # Add muscle memory effect
    muscle_memory = getattr(config, "muscle_memory_strength", 0.25)
    if muscle_memory > 0:
        if not hasattr(config, 'previous_movements'):
            config.previous_movements = []
        
        if len(config.previous_movements) > 0:
            # Use recent movements for muscle memory
            recent_movements = config.previous_movements[-3:]
            if recent_movements:
                weights = [0.5, 0.3, 0.2]
                weights = weights[:len(recent_movements)]
                
                avg_dx = sum(m[0] * w for m, w in zip(recent_movements, weights))
                avg_dy = sum(m[1] * w for m, w in zip(recent_movements, weights))
                
                # Blend with muscle memory
                dx = dx * (1 - muscle_memory) + avg_dx * muscle_memory
                dy = dy * (1 - muscle_memory) + avg_dy * muscle_memory
        
        # Store current movement
        config.previous_movements.append((dx, dy))
        if len(config.previous_movements) > 6:
            config.previous_movements.pop(0)
    
    # Add skill-based variation
    skill_level = getattr(config, "skill_level", 0.6)
    if movement_distance > 5:
        # Skill affects precision
        skill_factor = 0.9 + (skill_level * 0.2)  # 0.9 to 1.1 range
        variation = random.uniform(0.95, 1.05) * skill_factor
        
        dx *= variation
        dy *= variation
    
    # Add occasional overshoot
    overshoot_chance = getattr(config, "overshoot_chance", 0.15)
    if movement_distance > 15 and random.random() < overshoot_chance:
        overshoot_factor = random.uniform(1.02, 1.08)
        dx *= overshoot_factor
        dy *= overshoot_factor
    
    # Final smoothing
    movement_smoothness = getattr(config, "movement_smoothness", 0.85)
    if movement_smoothness > 0:
        dx = dx * movement_smoothness + original_dx * (1 - movement_smoothness)
        dy = dy * movement_smoothness + original_dy * (1 - movement_smoothness)
    
    return dx, dy

def is_target_touching_boundary_mode2(x1, y1, x2, y2):
    """
    Mode 2: Check if target bounding box touches the trigger boundary area.
    This is a simplified boundary contact detection for Mode 2.
    
    Args:
        x1, y1, x2, y2: Target bounding box coordinates
        
    Returns:
        bool: True if target touches the boundary area
    """
    # Get trigger radius from config
    radius_px = getattr(config, "trigger_radius_px", 8)
    
    # Get crosshair center based on capture mode
    if config.capturer_mode.lower() in ["mss", "capturecard"]:
        crosshair_center_x = config.fov_x_size / 2
        crosshair_center_y = config.fov_y_size / 2
    elif config.capturer_mode.lower() == "udp":
        crosshair_center_x = config.udp_width / 2
        crosshair_center_y = config.udp_height / 2
    else:
        crosshair_center_x = config.ndi_width / 2
        crosshair_center_y = config.ndi_height / 2
    
    # Calculate boundary area (circle around crosshair)
    boundary_x1 = crosshair_center_x - radius_px
    boundary_y1 = crosshair_center_y - radius_px
    boundary_x2 = crosshair_center_x + radius_px
    boundary_y2 = crosshair_center_y + radius_px
    
    # Check if target bounding box intersects with boundary area
    # This is a simple rectangular intersection check for the circular boundary
    x_overlap = max(0, min(x2, boundary_x2) - max(x1, boundary_x1))
    y_overlap = max(0, min(y2, boundary_y2) - max(y1, boundary_y1))
    
    # If both overlaps are positive, the target touches the boundary
    return x_overlap > 0 and y_overlap > 0

def process_mode2_trigger_logic(all_targets, delay_ms, cooldown_ms):
    """
    Independent Mode 2 trigger logic: boundary contact -> delay -> fire -> cooldown
    
    Args:
        all_targets: List of detected targets
        delay_ms: Delay before firing (ms)
        cooldown_ms: Cooldown after firing (ms)
        
    Returns:
        tuple: (should_fire, status_message, best_target)
    """
    global _in_zone_since_ms, _last_trigger_time_ms
    
    now = _now_ms()
    
    # Find targets that touch the boundary
    boundary_targets = []
    for target in all_targets:
        if is_target_touching_boundary_mode2(target['x1'], target['y1'], target['x2'], target['y2']):
            boundary_targets.append(target)
    
    # If no targets touching boundary, reset timing
    if not boundary_targets:
        _in_zone_since_ms = 0.0
        return False, "NO_TARGETS", None
    
    # Select best target (closest to crosshair center)
    best_target = min(boundary_targets, key=lambda t: t['dist'])
    
    # Check if in cooldown phase
    cooldown_ok = (now - _last_trigger_time_ms) >= cooldown_ms
    
    if not cooldown_ok:
        # In cooldown phase
        cooldown_remaining = cooldown_ms - (now - _last_trigger_time_ms)
        return False, f"COOLDOWN ({cooldown_remaining:.0f}ms)", best_target
    
    # Not in cooldown - start delay phase
    if _in_zone_since_ms == 0.0:
        _in_zone_since_ms = now
        return False, "WAITING", best_target
    
    time_in_zone = now - _in_zone_since_ms
    linger_ok = time_in_zone >= delay_ms
    
    if linger_ok:
        # Ready to fire
        return True, "FIRING", best_target
    else:
        # Still waiting
        return False, f"WAITING ({time_in_zone:.0f}/{delay_ms}ms)", best_target

def detect_color_in_region(frame, center_x, center_y, radius, h_min, h_max, s_min, s_max, v_min, v_max):
    """
    Detect if specified HSV color range exists in circular region around center point
    
    Args:
        frame: Input image frame (BGR format)
        center_x, center_y: Center point for detection
        radius: Detection radius in pixels
        h_min, h_max: Hue range (0-179)
        s_min, s_max: Saturation range (0-255)
        v_min, v_max: Value range (0-255)
        
    Returns:
        bool: True if color is detected in region
    """
    try:
        if frame is None:
            return False
        
        # Convert BGR to HSV
        hsv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        
        # Define circular region
        mask = np.zeros(hsv_frame.shape[:2], dtype=np.uint8)
        cv2.circle(mask, (int(center_x), int(center_y)), radius, 255, -1)
        
        # Create HSV range mask
        lower_hsv = np.array([h_min, s_min, v_min])
        upper_hsv = np.array([h_max, s_max, v_max])
        hsv_mask = cv2.inRange(hsv_frame, lower_hsv, upper_hsv)
        
        # Combine circular region with HSV range
        combined_mask = cv2.bitwise_and(mask, hsv_mask)
        
        # Count pixels that match the color criteria
        matching_pixels = cv2.countNonZero(combined_mask)
        total_pixels = cv2.countNonZero(mask)
        
        # Return True if at least 10% of the region matches the color
        if total_pixels > 0:
            color_ratio = matching_pixels / total_pixels
            return color_ratio >= 0.1  # 10% threshold for color detection
        
        return False
    except Exception as e:
        print(f"[ERROR] Color detection failed: {e}")
        return False

def detect_color_outline(frame, target_x, target_y, target_width, target_height, detection_radius=3, min_pixels=5):
    """
    Enhanced outline detection for enemy vs teammate identification
    Enemies have colored outlines, teammates don't
    """
    try:
        if frame is None or frame.size == 0:
            return False

        # Safety checks to prevent crashes
        height, width = frame.shape[:2]
        if height < 50 or width < 50:
            return False

        # Convert BGR to HSV for better color detection
        hsv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Calculate target bounds with safety checks
        target_left = max(detection_radius, int(target_x - target_width / 2))
        target_right = min(width - detection_radius, int(target_x + target_width / 2))
        target_top = max(detection_radius, int(target_y - target_height / 2))
        target_bottom = min(height - detection_radius, int(target_y + target_height / 2))

        # Safety check for valid bounds
        if target_left >= target_right or target_top >= target_bottom:
            return False

        # Create improved outline detection mask
        mask = np.zeros(hsv_frame.shape[:2], dtype=np.uint8)

        # Create multiple detection rings for better accuracy
        for radius in range(1, detection_radius + 1):
            # Outer ring
            cv2.rectangle(mask, 
                         (target_left - radius, target_top - radius),
                         (target_right + radius, target_bottom + radius), 255, 1)

        # Remove inner target area to focus on outline
        cv2.rectangle(mask, (target_left, target_top), (target_right, target_bottom), 0, -1)

        # Enhanced color detection for enemy outlines
        # More precise color ranges for better enemy/teammate distinction
        
        # Red outlines (enemies) - Expanded range for better detection
        red_lower1 = np.array([0, 100, 100])   # Lower saturation threshold
        red_upper1 = np.array([15, 255, 255])  # Wider hue range
        red_lower2 = np.array([165, 100, 100]) # Lower saturation threshold
        red_upper2 = np.array([179, 255, 255])
        red_mask1 = cv2.inRange(hsv_frame, red_lower1, red_upper1)
        red_mask2 = cv2.inRange(hsv_frame, red_lower2, red_upper2)
        red_mask = cv2.bitwise_or(red_mask1, red_mask2)
        
        # Yellow/Orange outlines (enemies) - Expanded range
        yellow_lower = np.array([15, 100, 100])  # Lower saturation threshold
        yellow_upper = np.array([45, 255, 255])  # Wider range to include orange
        yellow_mask = cv2.inRange(hsv_frame, yellow_lower, yellow_upper)
        
        # Purple/Magenta outlines (enemies) - Expanded range
        purple_lower = np.array([125, 100, 100]) # Lower saturation threshold
        purple_upper = np.array([165, 255, 255]) # Wider range
        purple_mask = cv2.inRange(hsv_frame, purple_lower, purple_upper)
        
        # Blue outlines (some games use blue for enemies)
        blue_lower = np.array([100, 100, 100])
        blue_upper = np.array([125, 255, 255])
        blue_mask = cv2.inRange(hsv_frame, blue_lower, blue_upper)
        
        # Green outlines (some games use green for enemies)
        green_lower = np.array([45, 100, 100])
        green_upper = np.array([80, 255, 255])
        green_mask = cv2.inRange(hsv_frame, green_lower, green_upper)

        # Combine all enemy outline colors
        enemy_colors_mask = cv2.bitwise_or(red_mask, yellow_mask)
        enemy_colors_mask = cv2.bitwise_or(enemy_colors_mask, purple_mask)
        enemy_colors_mask = cv2.bitwise_or(enemy_colors_mask, blue_mask)
        enemy_colors_mask = cv2.bitwise_or(enemy_colors_mask, green_mask)

        # Apply morphological operations to reduce noise
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        enemy_colors_mask = cv2.morphologyEx(enemy_colors_mask, cv2.MORPH_CLOSE, kernel)

        # Combine outline area with color mask
        outline_mask = cv2.bitwise_and(mask, enemy_colors_mask)

        # Count pixels that match colored outline
        matching_pixels = cv2.countNonZero(outline_mask)
        
        # Enhanced detection criteria
        # Check both absolute pixel count and relative density
        total_outline_pixels = cv2.countNonZero(mask)
        
        if total_outline_pixels > 0:
            outline_density = matching_pixels / total_outline_pixels
            # Enemy detected if either enough pixels OR high density
            has_outline = (matching_pixels >= min_pixels) or (outline_density >= 0.15)
        else:
            has_outline = matching_pixels >= min_pixels
        
        return has_outline

    except Exception as e:
        print(f"[ERROR] Color outline detection failed: {e}")
        return False

def enhanced_silent_aim(target_x, target_y, screen_center_x, screen_center_y):
    """
    Enhanced Silent Mode: High-speed calculate distance to target, move to target, optionally fire, return to origin
    
    Args:
        target_x, target_y: Target position in screen coordinates
        screen_center_x, screen_center_y: Current screen center position
    """
    global _silent_original_pos, _silent_in_progress, _silent_last_activation
    
    # Fast cooldown check using perf_counter for better precision
    current_time = time.perf_counter()
    if current_time - _silent_last_activation < config.silent_cooldown:
        return False
    
    # Prevent multiple silent operations
    if _silent_in_progress:
        return False
    
    try:
        _silent_in_progress = True
        _silent_last_activation = current_time
        
        # Pre-calculate all movements for speed
        raw_dx = target_x - screen_center_x
        raw_dy = target_y - screen_center_y
        
        # Apply silent strength - use direct multiplication for speed
        dx = int(raw_dx * config.silent_strength)
        dy = int(raw_dy * config.silent_strength)
        
        # Apply separate X/Y mouse movement multipliers for speed control
        if getattr(config, 'mouse_movement_enabled_x', True):
            dx = int(dx * getattr(config, 'mouse_movement_multiplier_x', config.mouse_movement_multiplier))
        else:
            dx = 0  # Disable X-axis movement
            
        if getattr(config, 'mouse_movement_enabled_y', True):
            dy = int(dy * getattr(config, 'mouse_movement_multiplier_y', config.mouse_movement_multiplier))
        else:
            dy = 0  # Disable Y-axis movement
        
        # Speed mode optimizations
        if config.silent_speed_mode:
            # ULTRA-FAST MODE: Skip all debug output and use optimized execution
            # Phase 1: Instant movement to target
            if dx | dy:  # Bitwise OR is faster than != 0 checks
                # Apply GAN enhancements to silent movement
                enhanced_dx, enhanced_dy = apply_gan_enhancements(dx, dy)
                
                if config.silent_use_bezier:
                    # Ultra-fast bezier movement with GAN enhancements
                    makcu.move_bezier(enhanced_dx, enhanced_dy, config.silent_segments, config.silent_ctrl_x, config.silent_ctrl_y)
                else:
                    # Direct movement for maximum speed with GAN enhancements
                    makcu.move(enhanced_dx, enhanced_dy)
            
            # Phase 2: Lightning-fast auto fire sequence
            if config.silent_auto_fire:
                # Micro-sleep only if delay > 0
                config.silent_fire_delay > 0 and time.sleep(config.silent_fire_delay)
                makcu.click()
                config.silent_return_delay > 0 and time.sleep(config.silent_return_delay)
            else:
                # Instant return delay
                config.silent_return_delay > 0 and time.sleep(config.silent_return_delay)
            
            # Phase 3: Instant return to origin
            if dx | dy:
                # Apply GAN enhancements to return movement
                enhanced_return_dx, enhanced_return_dy = apply_gan_enhancements(-dx, -dy)
                
                if config.silent_use_bezier:
                    # Ultra-fast bezier return with GAN enhancements
                    makcu.move_bezier(enhanced_return_dx, enhanced_return_dy, config.silent_segments, config.silent_ctrl_x, config.silent_ctrl_y)
                else:
                    # Direct return for maximum speed with GAN enhancements
                    makcu.move(enhanced_return_dx, enhanced_return_dy)
        else:
            # STANDARD MODE: With debug output and normal execution
            distance = (dx*dx + dy*dy) ** 0.5  # Faster than math.sqrt
            # Debug: Enhanced Silent movement (removed for cleaner output)
            
            # Phase 1: Movement to target
            if dx != 0 or dy != 0:
                # Apply GAN enhancements to silent movement
                enhanced_dx, enhanced_dy = apply_gan_enhancements(dx, dy)
                
                if config.silent_use_bezier:
                    makcu.move_bezier(enhanced_dx, enhanced_dy, config.silent_segments, config.silent_ctrl_x, config.silent_ctrl_y)
                    # Debug: Silent movement with bezier (removed for cleaner output)
                else:
                    makcu.move(enhanced_dx, enhanced_dy)
                    # Debug: Silent movement with direct (removed for cleaner output)
            
            # Phase 2: Auto fire sequence
            if config.silent_auto_fire:
                if config.silent_fire_delay > 0:
                    time.sleep(config.silent_fire_delay)
                
                makcu.click()
                # Debug: Silent auto fire (removed for cleaner output)
                
                if config.silent_return_delay > 0:
                    time.sleep(config.silent_return_delay)
            else:
                if config.silent_return_delay > 0:
                    time.sleep(config.silent_return_delay)
            
            # Phase 3: Return to origin
            if dx != 0 or dy != 0:
                # Apply GAN enhancements to return movement
                enhanced_return_dx, enhanced_return_dy = apply_gan_enhancements(-dx, -dy)
                
                if config.silent_use_bezier:
                    makcu.move_bezier(enhanced_return_dx, enhanced_return_dy, config.silent_segments, config.silent_ctrl_x, config.silent_ctrl_y)
                    # Debug: Silent return with bezier (removed for cleaner output)
                else:
                    makcu.move(enhanced_return_dx, enhanced_return_dy)
                    # Debug: Silent return with direct (removed for cleaner output)
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Enhanced silent aim error: {e}")
        return False
    finally:
        _silent_in_progress = False

def is_target_in_fov(x1, y1, x2, y2):
    """Check if target bounding box intersects with FOV (Field of View) area"""
    if config.capturer_mode.lower() in ("capturecard", "mss"):
        # For CaptureCard mode, FOV is centered on the captured region
        fov_center_x = config.fov_x_size / 2
        fov_center_y = config.fov_y_size / 2
        fov_half_x = config.fov_x_size / 2
        fov_half_y = config.fov_y_size / 2
    else:
        # For NDI mode, FOV is centered on the NDI capture area
        fov_center_x = config.ndi_width / 2
        fov_center_y = config.ndi_height / 2
        fov_half_x = config.fov_x_size / 2
        fov_half_y = config.fov_y_size / 2
    
    # Calculate FOV rectangle bounds using separate X and Y dimensions
    fov_x1 = fov_center_x - fov_half_x
    fov_y1 = fov_center_y - fov_half_y
    fov_x2 = fov_center_x + fov_half_x
    fov_y2 = fov_center_y + fov_half_y
    
    # Check if target bounding box intersects with FOV rectangle
    # Two rectangles intersect if they overlap in both X and Y dimensions
    x_overlap = max(0, min(x2, fov_x2) - max(x1, fov_x1))
    y_overlap = max(0, min(y2, fov_y2) - max(y1, fov_y1))
    
    # If both overlaps are positive, the rectangles intersect
    return x_overlap > 0 and y_overlap > 0

def calculate_height_target_position(x1, y1, x2, y2):
    """
    Calculate the target position based on height targeting settings.
    
    Args:
        x1, y1, x2, y2: Target bounding box coordinates
        
    Returns:
        tuple: (target_x, target_y) - calculated target position
    """
    # Calculate center X (always use center for X)
    target_x = (x1 + x2) / 2
    
    # Check if height targeting is enabled
    if not getattr(config, 'height_targeting_enabled', True):
        # If height targeting is disabled, use center Y position
        target_y = (y1 + y2) / 2
        return target_x, target_y
    
    # Calculate target Y based on height setting
    target_height = config.target_height  # 0.1 = bottom, 1.0 = top
    
    # Linear interpolation between bottom and top of bounding box
    # y1 is top of box, y2 is bottom of box (screen coordinates)
    target_y = y1 + (y2 - y1) * (1.0 - target_height)
    
    return target_x, target_y

def calculate_x_center_target_position(x1, y1, x2, y2, crosshair_x):
    """
    Calculate the target position with X-axis center targeting and tolerance.
    
    Args:
        x1, y1, x2, y2: Target bounding box coordinates
        crosshair_x: Current crosshair X position
        
    Returns:
        tuple: (target_x, target_y) - calculated target position
    """
    # Start with standard height-based targeting
    target_x, target_y = calculate_height_target_position(x1, y1, x2, y2)
    
    # Apply X-center targeting if enabled
    if config.x_center_targeting_enabled:
        # Calculate ultra-precise center X of the player using float precision
        player_center_x = (float(x1) + float(x2)) / 2.0
        
        # If tolerance is 0%, always aim at exact center with maximum precision
        if config.x_center_tolerance_percent <= 0.1:  # Treat very small values as zero for precision
            target_x = player_center_x
        else:
            # Calculate player bounding box width with precision
            player_width = float(x2) - float(x1)
            
            # Calculate tolerance zone as percentage of player width
            tolerance_pixels = (config.x_center_tolerance_percent / 100.0) * player_width
            
            # Check if crosshair is within tolerance zone of player center
            distance_from_center = abs(float(crosshair_x) - player_center_x)
            
            if distance_from_center <= tolerance_pixels:
                # Within tolerance zone - aim at player X center with precision
                target_x = player_center_x
            else:
                # Outside tolerance zone - use precise calculation toward center
                if float(crosshair_x) < player_center_x:
                    # Crosshair is left of center, aim toward left edge of tolerance zone
                    target_x = player_center_x - tolerance_pixels
                else:
                    # Crosshair is right of center, aim toward right edge of tolerance zone
                    target_x = player_center_x + tolerance_pixels
    
    return target_x, target_y

def should_apply_target_switch_delay(best_target, target_switch_delay_ms):
    """
    Check if target switch delay should be applied for aiming.
    
    Args:
        best_target: Current best target dictionary
        target_switch_delay_ms: Target switch delay in milliseconds
        
    Returns:
        bool: True if aiming should be delayed, False if aiming is allowed
    """
    global _last_target_id, _target_switch_time
    
    if target_switch_delay_ms <= 0:
        return False  # No delay configured
    
    if _last_target_id is None:
        return False  # No previous target to compare against
    
    # Use a more stable target ID based on center position with tolerance
    center_x = (best_target['x1'] + best_target['x2']) / 2
    center_y = (best_target['y1'] + best_target['y2']) / 2
    # Round to 10-pixel tolerance to reduce false switches from minor detection variations
    current_target_id = f"{int(center_x/10)*10}_{int(center_y/10)*10}"
    
    # Check if we switched to a different target
    if _last_target_id != current_target_id:
        time_since_switch = _now_ms() - _target_switch_time
        if time_since_switch < target_switch_delay_ms:
            return True  # Apply delay
    
    return False  # No delay needed

def is_in_height_deadzone(current_y, target_y, box_height):
    """
    Check if the current crosshair Y position is FULLY within the height deadzone.
    Uses tolerance to ensure complete entry rather than just touching the boundary.
    
    Args:
        current_y: Current crosshair Y position
        target_y: Target Y position
        box_height: Height of the target bounding box
        
    Returns:
        bool: True if fully in deadzone (should only move X-axis)
    """
    if not config.height_deadzone_enabled:
        return False
    
    # Calculate deadzone bounds relative to target bounding box
    # The deadzone percentages (0.6-0.8) should be applied to the actual box height
    deadzone_range = config.height_deadzone_max - config.height_deadzone_min  # e.g., 0.8 - 0.6 = 0.2
    deadzone_center_ratio = (config.height_deadzone_min + config.height_deadzone_max) / 2  # e.g., (0.6 + 0.8) / 2 = 0.7
    
    # Calculate deadzone bounds in actual pixel coordinates
    deadzone_height_pixels = deadzone_range * box_height  # e.g., 0.2 * box_height
    deadzone_center_pixels = target_y  # Use the calculated target Y position
    deadzone_half_pixels = deadzone_height_pixels / 2
    
    deadzone_min_y = deadzone_center_pixels - deadzone_half_pixels
    deadzone_max_y = deadzone_center_pixels + deadzone_half_pixels
    
    # Apply tolerance for "full entry" - crosshair must be this many pixels inside the deadzone
    tolerance = config.height_deadzone_tolerance
    deadzone_inner_min = deadzone_min_y + tolerance
    deadzone_inner_max = deadzone_max_y - tolerance
    
    # Check if current Y is FULLY within deadzone (with tolerance)
    is_fully_inside = deadzone_inner_min <= current_y <= deadzone_inner_max
    
    return is_fully_inside

def capture_loop():
    """PRODUCER: This loop runs on a dedicated CPU thread."""
    camera, _ = get_camera()
    last_selected = None

    while _aimbot_running:
        try:
            if config.capturer_mode.lower() in ("capturecard", "mss", "dxgi"):
                try:
                    camera.region = get_region()
                except Exception:
                    pass
            try:
                config.ndi_sources = camera.list_sources()
            except Exception:
                config.ndi_sources = []

            if config.capturer_mode.lower() == "ndi":
                desired = config.ndi_selected_source

                if isinstance(desired, str) and desired in config.ndi_sources:
                    if (desired != last_selected) or not camera.connected:
                        camera.select_source(desired)
                        last_selected = desired

            image = camera.get_latest_frame()
            if image is not None:
                try:
                    frame_queue.put(image, block=False)
                except queue.Full:
                    try: frame_queue.get_nowait()
                    except queue.Empty: pass
                    try: frame_queue.put(image, block=False)
                    except queue.Full: pass

        except Exception as e:
            print(f"[ERROR] Capture loop failed: {e}")
            time.sleep(1)

    try:
        camera.stop()
    except Exception as e:
        print(f"[ERROR] Camera stop failed: {e}")
    print("[INFO] Capture loop stopped.")

def calculate_overlap(box1, box2):
    """Calculate overlap ratio between two bounding boxes"""
    x1_1, y1_1, x2_1, y2_1 = box1
    x1_2, y1_2, x2_2, y2_2 = box2
    
    # Calculate intersection
    x1_i = max(x1_1, x1_2)
    y1_i = max(y1_1, y1_2)
    x2_i = min(x2_1, x2_2)
    y2_i = min(y2_1, y2_2)
    
    if x2_i <= x1_i or y2_i <= y1_i:
        return 0.0
    
    intersection = (x2_i - x1_i) * (y2_i - y1_i)
    area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
    area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
    union = area1 + area2 - intersection
    
    return intersection / union if union > 0 else 0.0

def detection_and_aim_loop():
    """CONSUMER: This loop runs on the main aimbot thread, utilizing the GPU."""
    global _aimbot_running, fps, makcu, processing_fps
    model, class_names = load_model()
    # makcu is already initialized in start_aimbot

    # Start safety monitoring to prevent PC freezing
    start_safety_monitoring()
    print("[INFO] Detection and aim loop started with safety monitoring")

    # Performance optimization variables
    frame_count = 0
    start_time = time.perf_counter()  # Use a more precise clock
    debug_window_moved = False  # Track if debug window has been moved
    
    
    # Pre-compute frequently used values
    fov_x = getattr(config, "fov_x_size", config.region_size)
    fov_y = getattr(config, "fov_y_size", config.region_size)
    fov_radius = max(4, max(fov_x, fov_y) // 2)
    
    # Cache configuration values to avoid repeated getattr calls
    conf_threshold = config.conf
    imgsz = config.imgsz
    max_detect = config.max_detect
    player_label = config.custom_player_label
    head_label = config.custom_head_label
    player_y_offset = config.player_y_offset
    always_on_aim = config.always_on_aim
    mode = config.mode
    
    # Simple variables like stable version
    last_targets = []
    last_detection_time = 0
    
    
    # Temporal consistency tracking for better detection (reduced overhead)
    detection_history = []
    max_history_frames = 3  # Reduced from 5 to 3
    temporal_confidence_boost = 0.05  # Reduced from 0.1 to 0.05
    
    # Removed performance configuration (was causing issues)
    
    # Memory optimization variables
    gc_threshold = 1000  # Simple threshold
    frame_since_gc = 0

    # Safety variables to prevent PC freezing
    last_safety_check = time.time()
    safety_check_interval = 5.0  # Check every 5 seconds
    max_loop_time = 0.1  # Maximum time per loop iteration (100ms)

    while _aimbot_running:
        loop_start_time = time.time()
        
        try:
            # Safety check to prevent infinite loops and PC freezing
            current_time = time.time()
            if current_time - last_safety_check > safety_check_interval:
                # Reset counters periodically to prevent overflow
                if frame_count > 1000000:
                    frame_count = 0
                    print("[SAFETY] Frame count reset to prevent overflow")
                
                # Check if loop is taking too long
                loop_duration = current_time - loop_start_time
                if loop_duration > max_loop_time:
                    print(f"[SAFETY] Loop taking too long: {loop_duration:.3f}s")
                    time.sleep(0.01)  # Force a break
                
                last_safety_check = current_time
            
            # Use reasonable timeout to reduce empty queue warnings
            image = frame_queue.get(timeout=0.5)  # Reduced timeout to prevent hanging
        except queue.Empty:
            # Add safety delay to prevent CPU spinning
            time.sleep(0.001)  # 1ms delay to prevent CPU spinning
            # Only print warning occasionally to reduce I/O overhead
            if frame_count % 20000 == 0:
                print("[WARN] Frame queue is empty. Capture thread may have stalled.")
            continue
        except Exception as e:
            print(f"[ERROR] Frame queue error: {e}")
            time.sleep(0.01)  # Safety delay
            continue
            
        # Removed adaptive frame skipping (was adding overhead)
        
        # Removed frame skipping (was adding overhead)
        
        # Optimized memory management
        frame_since_gc += 1
        if frame_since_gc >= gc_threshold * 10:  # Further reduce cleanup frequency
            import gc
            gc.collect()
            frame_since_gc = 0
            if frame_count % 10000 == 0:  # Less frequent logging
                print(f"[PERF] Memory cleanup performed at frame {frame_count}")
            
            # GPU memory optimization (less frequent)
            if frame_count % 10000 == 0:  # Only every 2000 frames
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                        print(f"[PERF] GPU memory cleared at frame {frame_count}")
                except ImportError:
                    pass
            
        img_h, img_w = image.shape[:2]
        if config.capturer_mode.lower() in ("capturecard", "mss"):
            region_left = (config.screen_width  - img_w) // 2
            region_top  = (config.screen_height - img_h) // 2
            screen_cx   = config.screen_width  // 2
            screen_cy   = config.screen_height // 2
        else:
            region_left = (config.main_pc_width  - config.ndi_width)  // 2
            region_top  = (config.main_pc_height - config.ndi_height) // 2
            screen_cx   = config.main_pc_width  // 2
            screen_cy   = config.main_pc_height // 2
        mask_set = set()
        if config.aim_button_mask:
            try:
                aim_idx = int(getattr(config, "selected_mouse_button", 0))
                if aim_idx != 0:  # don't mask Left Click for aiming
                    mask_set.add(aim_idx)
            except Exception:
                pass
        
        if config.trigger_button_mask:
            try:
                trig_idx = int(getattr(config, "trigger_button", 1))
                mask_set.add(trig_idx)
            except Exception:
                pass
        
        Mouse.mask_manager_tick_multi(mask_set, aimbot_running=is_aimbot_running())

        
        all_targets = []
        # Optimized debug image creation - only when needed
        debug_image = None
        if config.show_debug_window and frame_count % 3 == 0:  # Every 3rd frame for performance
            debug_image = image.copy()
        detected_classes = set()  # Track what classes are being detected
        
        # Use cached FOV values
        fov_radius = max(4, max(fov_x, fov_y) // 2)

        # Simple detection like stable version
        results = perform_detection(model, image)

        # --- Optimized Target Processing Logic ---
        all_targets = []
        detected_classes = set()
        
        if results:
            # Pre-compute FOV values for efficiency
            fov_center_x = fov_x / 2
            fov_center_y = fov_y / 2
            
            for result in results:
                if result.boxes is None: 
                    continue
                
                # Process all boxes at once for better performance
                boxes = result.boxes
                coords = boxes.xyxy.cpu().numpy()  # Convert to numpy once
                confs = boxes.conf.cpu().numpy()
                classes = boxes.cls.cpu().numpy()
                
                for i in range(len(coords)):
                    x1, y1, x2, y2 = coords[i].astype(int)
                    conf = float(confs[i])
                    cls = int(classes[i])
                    
                    # Skip low confidence detections early
                    if conf < conf_threshold:
                        continue
                    
                    # Apply temporal consistency boost (optimized)
                    temporal_boost = 0.0
                    if detection_history and len(detection_history) > 0:
                        # Only check the most recent frame for performance
                        recent_frame = detection_history[-1]
                        for hist_target in recent_frame:
                            # Quick distance check first (faster than overlap calculation)
                            hist_x1, hist_y1, hist_x2, hist_y2 = hist_target['coords']
                            hist_center_x = (hist_x1 + hist_x2) // 2
                            hist_center_y = (hist_y1 + hist_y2) // 2
                            current_center_x = (x1 + x2) // 2
                            current_center_y = (y1 + y2) // 2
                            
                            # Quick distance check (much faster than overlap)
                            distance = abs(hist_center_x - current_center_x) + abs(hist_center_y - current_center_y)
                            if distance < 50 and hist_target['class'] == cls:  # 50 pixel threshold
                                temporal_boost = temporal_confidence_boost
                                break
                    
                    # Apply temporal boost to confidence
                    enhanced_conf = conf + temporal_boost
                    
                    class_name = class_names.get(cls, f"class_{cls}")
                    detected_classes.add(class_name)



                    # Quick target classification (optimized)
                    is_target = False
                    target_type = "unknown"
                    
                    # Fast integer comparison first
                    if cls == player_label or (player_label and str(cls) == str(player_label)):
                        is_target = True
                        target_type = "player"
                    elif head_label and (cls == head_label or str(cls) == str(head_label)):
                        is_target = True
                        target_type = "head"
                    # String comparison only if needed
                    elif player_label and class_name == str(player_label):
                        is_target = True
                        target_type = "player"
                    elif head_label and class_name == str(head_label):
                        is_target = True
                        target_type = "head"

                    if is_target:
                        # Calculate center position efficiently
                        center_x = (x1 + x2) / 2
                        if target_type == "player":
                            # Use height targeting for players
                            center_y = y1 + (y2 - y1) * (1.0 - config.target_height)
                        else:
                            # For heads, use traditional center + offset
                            center_y = y1 + player_y_offset

                        # Quick FOV check (inline for speed)
                        inside_fov = (abs(center_x - fov_center_x) <= fov_x/2 and 
                                    abs(center_y - fov_center_y) <= fov_y/2)
                        
                        # Calculate distances efficiently
                        roi_cx, roi_cy = img_w / 2.0, img_h / 2.0
                        dist_roi = math.hypot(center_x - roi_cx, center_y - roi_cy)
                        abs_x = center_x + region_left
                        abs_y = center_y + region_top
                        dist_abs = math.hypot(abs_x - screen_cx, abs_y - screen_cy)

                        all_targets.append({
                            'dist_roi': dist_roi,
                            'dist_abs': dist_abs,
                            'dist': dist_roi,
                            'center_x': center_x,
                            'center_y': center_y,
                            'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2,
                            'bbox': [x1, y1, x2, y2],
                            'coords': (x1, y1, x2, y2),  # For temporal consistency
                            'type': target_type,
                            'class': class_name,
                            'class_name': class_name,
                            'conf': enhanced_conf,  # Use enhanced confidence
                            'original_conf': conf,  # Keep original for reference
                            'is_target': is_target,
                            'target_type': target_type,
                            'inside_fov': inside_fov
                        })

                        

                    # Optimized debug box drawing (only when debug image exists)
                    if debug_image is not None:
                        if is_target:
                            # Green for player, red for head
                            color = (0, 255, 0) if target_type == "player" else (0, 0, 255)
                            thickness = 3
                        else:
                            # Yellow for non-targets
                            color = (0, 255, 255)
                            thickness = 1

                        cv2.rectangle(debug_image, (x1, y1), (x2, y2), color, thickness)

                        # Only draw labels for targets to reduce overhead
                        if is_target:
                            label = f"{class_name} {conf:.2f} [{target_type.upper()}]"
                            cv2.putText(debug_image, label, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        # Update detection history for temporal consistency
        if all_targets:
            detection_history.append(all_targets.copy())
            # Keep only recent history
            if len(detection_history) > max_history_frames:
                detection_history.pop(0)

        # --- Target Switch Delay Logic (Only when user is actively using aimbot) ---
        global _last_target_id, _target_switch_time
        target_switch_delay_ms = getattr(config, "target_switch_delay_ms", 100)
        
        # Check if user is actively using aimbot (target switching only for aiming, not triggerbot)
        primary_button_held = is_button_pressed(config.selected_mouse_button)
        secondary_button_held = (getattr(config, "secondary_aim_enabled", False) and 
                               is_button_pressed(getattr(config, "secondary_aim_button", 2)))
        aim_button_held = primary_button_held or secondary_button_held
        
        # Debug output removed for performance
        
        # Target switching only activates when aiming, not when using triggerbot
        user_active = aim_button_held
        
        # Only track target switching when user is actively using the system
        if user_active and all_targets:
            best_target = min(all_targets, key=lambda t: t['dist_abs'])
            # Use the same stable target ID generation as in the delay check
            center_x = (best_target['x1'] + best_target['x2']) / 2
            center_y = (best_target['y1'] + best_target['y2']) / 2
            current_target_id = f"{int(center_x/10)*10}_{int(center_y/10)*10}"
            
            # Check if we switched targets
            if _last_target_id != current_target_id:
                _last_target_id = current_target_id
                _target_switch_time = _now_ms()
                print(f"[TARGET_SWITCH] Switched to new target, delay: {target_switch_delay_ms}ms")
        else:
            # Reset when user is not active
            if not user_active:
                _last_target_id = None

        # --- Target Selection and Aiming (Only when button is held) ---
        button_held = aim_button_held
        
        inside = [t for t in all_targets if t.get('inside_fov')]
        can_aim = False  # Flag to control aiming independently from triggerbot
        
        # Debug output removed for performance
        
        if inside and button_held:
            best_target = min(inside, key=lambda t: t['dist_abs'])
            # Debug output removed for performance
            
            # Check if target switch delay should be applied
            if should_apply_target_switch_delay(best_target, target_switch_delay_ms):
                remaining_delay = target_switch_delay_ms - (_now_ms() - _target_switch_time)
                if frame_count % 50 == 0:
                    print(f"[TARGET_SWITCH] Aiming delayed - {remaining_delay:.0f}ms remaining")
                can_aim = False
            else:
                can_aim = True

            # Use X-center targeting system for precise target position calculation
            # Crosshair position in image coordinates (center of captured region)
            crosshair_x = img_w // 2
            crosshair_y = img_h // 2
            
            target_x, target_y = calculate_x_center_target_position(
                best_target['x1'], best_target['y1'], 
                best_target['x2'], best_target['y2'],
                crosshair_x
            )
            
            target_screen_x = region_left + target_x
            target_screen_y = region_top + target_y

            dx = target_screen_x - screen_cx
            dy = target_screen_y - screen_cy
            
            # Check if we're in the height deadzone
            box_height = best_target['y2'] - best_target['y1']
            current_y = crosshair_y  # Use crosshair Y in image coordinates
            target_relative_y = target_y  # Target Y in image coordinates
            
            if is_in_height_deadzone(current_y, target_relative_y, box_height):
                # In deadzone: only move X-axis, set Y movement to zero
                dy = 0

            # Apply im-game-sensitivity scaling with separate X/Y values
            sens_x = getattr(config, "in_game_sens_x", config.in_game_sens)
            sens_y = getattr(config, "in_game_sens_y", config.in_game_sens)
            distance_x = 1.07437623 * math.pow(sens_x, -0.9936827126)
            distance_y = 1.07437623 * math.pow(sens_y, -0.9936827126)
            # Apply distance scaling separately for X and Y
            dx *= distance_x
            dy *= distance_y
            
            # Apply mouse movement multiplier for speed control
            # Apply separate X/Y mouse movement multipliers
            if getattr(config, 'mouse_movement_enabled_x', True):
                dx *= getattr(config, 'mouse_movement_multiplier_x', config.mouse_movement_multiplier)
            else:
                dx = 0  # Disable X-axis movement
                
            if getattr(config, 'mouse_movement_enabled_y', True):
                dy *= getattr(config, 'mouse_movement_multiplier_y', config.mouse_movement_multiplier)
            else:
                dy = 0  # Disable Y-axis movement

            # Only perform aiming if target switch delay has passed
            if can_aim:
                if mode == "normal":
                    from aim_system.modes import normal_move
                    normal_move(makcu, dx, dy, config, apply_gan_enhancements, frame_count)
                elif mode == "bezier":
                    from aim_system.modes import bezier_move
                    bezier_move(makcu, dx, dy, config, apply_gan_enhancements)
                elif mode == "silent":
                    from aim_system.modes import silent_move
                    silent_move(enhanced_silent_aim, target_screen_x, target_screen_y, screen_cx, screen_cy)
                elif mode == "smooth":
                    from aim_system.modes import smooth_move
                    smooth_move(smooth_move_queue, dx, dy, config, smooth_aimer)

                    # Only print debug info occasionally (reduced frequency)
                    if movements_added > 0 and frame_count % 200 == 0:
                        # Debug: Movements added to queue (removed for cleaner output)
                        pass

                    # Fallback: if no smooth movements generated, use direct movement
                    if len(path) == 0:
                        # Debug: No smooth path fallback (removed for cleaner output)
                        final_dx = dx if config.smooth_enable_x else 0
                        final_dy = dy if config.smooth_enable_y else 0
                        makcu.move(final_dx, final_dy)

                elif mode == "gan":
                    # GAN handled earlier in flow below for consistency
                    final_dx = dx if getattr(config, "gan_enable_x", True) else 0
                    final_dy = dy if getattr(config, "gan_enable_y", True) else 0
                    enhanced_dx, enhanced_dy = apply_gan_enhancements(final_dx, final_dy)
                    if abs(enhanced_dx) > 0.1 or abs(enhanced_dy) > 0.1:
                        makcu.move(enhanced_dx, enhanced_dy)
                elif mode == "pid":
                    from aim_system.modes import pid_move
                    pid_move(makcu, dx, dy, config)
                    # GAN-based human-like movement (Research implementation)
                    # Debug: GAN mode active (removed for cleaner output)
                    final_dx = dx if getattr(config, "gan_enable_x", True) else 0
                    final_dy = dy if getattr(config, "gan_enable_y", True) else 0

                    # Apply all GAN-based human-like enhancements
                    enhanced_dx, enhanced_dy = apply_gan_enhancements(final_dx, final_dy)
                    # Debug: GAN movement (removed for cleaner output)
                    
                    # Check if movement is significant enough
                    if abs(enhanced_dx) > 0.1 or abs(enhanced_dy) > 0.1:
                        # Debug: GAN move execution (removed for cleaner output)
                        makcu.move(enhanced_dx, enhanced_dy)
                    else:
                        # Debug: GAN move skipped (removed for cleaner output)
                        pass
            else:
                # Target switch delay is active - skip aiming but show debug info
                if config.show_debug_text_info:
                    print(f"[TARGET_SWITCH] Aiming blocked - waiting for target switch delay")

        elif inside and config.always_on_aim:
            best_target = min(inside, key=lambda t: t['dist_abs'])
            
            # Check target switch delay for always-on aim as well
            can_aim_always_on = not should_apply_target_switch_delay(best_target, target_switch_delay_ms)
            # Debug: Always on aim status (removed for cleaner output)

            # Use X-center targeting system for precise target position calculation
            # Crosshair position in image coordinates (center of captured region)
            crosshair_x = img_w // 2
            crosshair_y = img_h // 2
            
            target_x, target_y = calculate_x_center_target_position(
                best_target['x1'], best_target['y1'], 
                best_target['x2'], best_target['y2'],
                crosshair_x
            )
            
            target_screen_x = region_left + target_x
            target_screen_y = region_top + target_y

            dx = target_screen_x - screen_cx
            dy = target_screen_y - screen_cy
            
            # Check if we're in the height deadzone
            box_height = best_target['y2'] - best_target['y1']
            current_y = crosshair_y  # Use crosshair Y in image coordinates
            target_relative_y = target_y  # Target Y in image coordinates
            
            if is_in_height_deadzone(current_y, target_relative_y, box_height):
                # In deadzone: only move X-axis, set Y movement to zero
                dy = 0

            # Apply im-game-sensitivity scaling with separate X/Y values
            sens_x = getattr(config, "in_game_sens_x", config.in_game_sens)
            sens_y = getattr(config, "in_game_sens_y", config.in_game_sens)
            distance_x = 1.07437623 * math.pow(sens_x, -0.9936827126)
            distance_y = 1.07437623 * math.pow(sens_y, -0.9936827126)
            # Apply distance scaling separately for X and Y
            dx *= distance_x
            dy *= distance_y
            
            # Apply mouse movement multiplier for speed control
            # Apply separate X/Y mouse movement multipliers
            if getattr(config, 'mouse_movement_enabled_x', True):
                dx *= getattr(config, 'mouse_movement_multiplier_x', config.mouse_movement_multiplier)
            else:
                dx = 0  # Disable X-axis movement
                
            if getattr(config, 'mouse_movement_enabled_y', True):
                dy *= getattr(config, 'mouse_movement_multiplier_y', config.mouse_movement_multiplier)
            else:
                dy = 0  # Disable Y-axis movement

            # Only perform always-on aiming if target switch delay has passed
            if can_aim_always_on:
                if mode == "normal":
                    # Apply x,y speeds scaling
                    dx *= config.normal_x_speed
                    dy *= config.normal_y_speed
                    
                    final_dx = dx if config.normal_enable_x else 0
                    final_dy = dy if config.normal_enable_y else 0
                    
                    # Normal mode - no GAN enhancements
                    # Debug: Movement execution (reduced frequency)
                    if frame_count % 20000 == 0:
                        print(f"[DEBUG] 🎯 Normal mode movement (no GAN) - dx: {final_dx:.2f}, dy: {final_dy:.2f}")
                    makcu.move(final_dx, final_dy)
                elif mode == "bezier":
                    final_dx = dx if config.bezier_enable_x else 0
                    final_dy = dy if config.bezier_enable_y else 0
                    
                    # Apply GAN enhancements to bezier movement
                    enhanced_dx, enhanced_dy = apply_gan_enhancements(final_dx, final_dy)
                    makcu.move_bezier(enhanced_dx, enhanced_dy, config.bezier_segments, config.bezier_ctrl_x, config.bezier_ctrl_y)
                elif mode == "silent":
                    # Use enhanced silent aim system
                    enhanced_silent_aim(target_screen_x, target_screen_y, screen_cx, screen_cy)
                elif mode == "smooth":
                    # Use smooth aiming with WindMouse algorithm

                    # Apply X/Y enable/disable before calculating path
                    adjusted_dx = dx if config.smooth_enable_x else 0
                    adjusted_dy = dy if config.smooth_enable_y else 0

                    path = smooth_aimer.calculate_smooth_path(adjusted_dx, adjusted_dy, config)

                    # Add all movements to the smooth movement queue
                    movements_added = 0
                    for move_dx, move_dy, delay in path:
                        final_move_dx = move_dx if config.smooth_enable_x else 0
                        final_move_dy = move_dy if config.smooth_enable_y else 0
                        if not smooth_move_queue.full():
                            smooth_move_queue.put((final_move_dx, final_move_dy, delay))
                            movements_added += 1
                        if movements_added <= 5:  # Only print first few to avoid spam
                            # Debug: Movement added (removed for cleaner output)
                            pass
                    else:
                        # If queue is full, clear it and add this movement
                        # Debug: Queue full (removed for cleaner output)
                        pass
                        try:
                            while not smooth_move_queue.empty():
                                smooth_move_queue.get_nowait()
                        except queue.Empty:
                            pass
                        smooth_move_queue.put((final_move_dx, final_move_dy, delay))
                        movements_added += 1
                        break

                    # Debug: Movements added (removed for cleaner output)

                    # Fallback: if no smooth movements generated, use direct movement
                    if len(path) == 0:
                        # Debug: No smooth path fallback (removed for cleaner output)
                        final_dx = dx if config.smooth_enable_x else 0
                        final_dy = dy if config.smooth_enable_y else 0
                        makcu.move(final_dx, final_dy)

                elif mode == "gan":
                    # GAN-based human-like movement (Research implementation)
                    # Debug: GAN mode active (removed for cleaner output)
                    final_dx = dx if getattr(config, "gan_enable_x", True) else 0
                    final_dy = dy if getattr(config, "gan_enable_y", True) else 0

                    # Apply all GAN-based human-like enhancements
                    enhanced_dx, enhanced_dy = apply_gan_enhancements(final_dx, final_dy)
                    # Debug: GAN movement (removed for cleaner output)
                    
                    # Check if movement is significant enough
                    if abs(enhanced_dx) > 0.1 or abs(enhanced_dy) > 0.1:
                        # Debug: GAN move execution (removed for cleaner output)
                        makcu.move(enhanced_dx, enhanced_dy)
                    else:
                        # Debug: GAN move skipped (removed for cleaner output)
                        pass
            else:
                # Always-on aim target switch delay is active
                if config.show_debug_text_info:
                    print(f"[TARGET_SWITCH] Always-on aim blocked - waiting for target switch delay")
        else:
            # Reset fatigue when not aiming
            smooth_aimer.reset_fatigue()
        # (Magnet Trigger removed)

        # --- Enhanced Triggerbot (CH341PAR improvements) ---
        triggerbot_status = "INACTIVE"
        triggerbot_candidates = []
        best_trigger_target = None
        
        try:
            # Declare global variables used in triggerbot
            global _is_spraying, _burst_shots_fired, _last_trigger_time_ms, _in_zone_since_ms

            # Initialize trigger variables
            trigger_active = False
            firing_mode = "normal"
            detection_method = "ai"

            if getattr(config, "trigger_enabled", False):
                # Debug: Trigger enabled (removed for cleaner output)
                
                # Get triggerbot parameters first
                min_conf = float(getattr(config, "trigger_min_conf", 0.35))
                radius_px = int(getattr(config, "trigger_radius_px", 8))
                delay_ms = int(getattr(config, "trigger_delay_ms", 30))
                cooldown_ms = int(getattr(config, "trigger_cooldown_ms", 120))
                
                # Get firing mode
                firing_mode = getattr(config, "trigger_mode", "normal")
                
                # Get detection method (AI or Color)
                detection_method = getattr(config, "trigger_detection_method", "ai").lower()
                
                # Check trigger button state for triggerbot
                trigger_active = bool(getattr(config, "trigger_always_on", False))
                if not trigger_active:
                    trigger_btn_idx = int(getattr(config, "trigger_button", 0))
                    trigger_active = is_button_pressed(trigger_btn_idx)
                # Debug: Trigger status (removed for cleaner output)
                
                if trigger_active:
                    # Handle AI-based detection (enhanced with CH341PAR improvements)
                    if detection_method == "ai" and all_targets:
                        # Filter targets by confidence for AI detection
                        valid_targets = [t for t in all_targets if t['conf'] >= min_conf]
                        
                        # Debug: Check filter state (reduced frequency)
                        filter_enabled = getattr(config, "color_outline_filter_enabled", False)
                        if frame_count % 10000 == 0:
                            print(f"[DEBUG] 🎨 Color outline filter state: {filter_enabled}")

                        # Apply color outline filter if enabled - COMPLETE teammate filtering
                        if filter_enabled:
                            if frame_count % 20000 == 0:
                                print("[INFO] 🎨 Color outline filter ENABLED - COMPLETELY filtering out teammates")
                            filtered_targets = []
                            teammates_filtered = 0
                            
                            for target in valid_targets:
                                # Calculate target center and dimensions from bounding box
                                target_center_x = (target['x1'] + target['x2']) / 2
                                target_center_y = (target['y1'] + target['y2']) / 2
                                target_width = target['x2'] - target['x1']
                                target_height = target['y2'] - target['y1']

                            # Check for color outline around target (automatic detection)
                            try:
                                has_outline = detect_color_outline(
                                    image,
                                    target_center_x, target_center_y,
                                    target_width, target_height,
                                    getattr(config, "outline_detection_radius", 3),
                                    getattr(config, "outline_min_pixels", 10)
                                )
                            except Exception as e:
                                print(f"[ERROR] Outline detection failed: {e}")
                                has_outline = True  # Default to enemy if detection fails

                                if has_outline:
                                    filtered_targets.append(target)
                                    if frame_count % 10000 == 0:  # Very reduced frequency
                                        print(f"[DEBUG] ✅ ENEMY detected - {target['class']} has red/yellow/purple outline - TARGETING")
                                else:
                                    teammates_filtered += 1
                                    if frame_count % 10000 == 0:  # Very reduced frequency
                                        print(f"[DEBUG] 👥 TEAMMATE detected - {target['class']} no outline - COMPLETELY IGNORED")

                            valid_targets = filtered_targets
                            if frame_count % 20000 == 0:
                                print(f"[INFO] 📊 Color outline filter: {len(valid_targets)} enemies, {teammates_filtered} teammates COMPLETELY FILTERED OUT")
                            
                            # If no enemies found, completely skip all targeting
                            if not valid_targets:
                                if frame_count % 20000 == 0:
                                    print("[INFO] 🚫 No enemies detected - all targets filtered as teammates - SKIPPING ALL TARGETING")
                                continue
                        else:
                            if frame_count % 20000 == 0:
                                print("[INFO] 🎨 Color outline filter DISABLED - targeting all detected players")
                        
                        # Enhanced AI detection with better scoring (CH341PAR improvement)
                        for target in valid_targets:
                            crosshair_dist = target.get('dist', target.get('dist_abs', 1e9))
                            if crosshair_dist <= radius_px:
                                # Enhanced scoring system for better target selection
                                target_score = target['conf'] * (1.0 - (crosshair_dist / radius_px))
                                triggerbot_candidates.append({
                                    'target': target,
                                    'distance': crosshair_dist,
                                    'score': target_score
                                })
                    
                    elif detection_method == "color":
                        # Pure color-based detection (CH341PAR enhancement)
                        # Get HSV parameters
                        h_min = int(getattr(config, "trigger_hsv_h_min", 0))
                        h_max = int(getattr(config, "trigger_hsv_h_max", 179))
                        s_min = int(getattr(config, "trigger_hsv_s_min", 0))
                        s_max = int(getattr(config, "trigger_hsv_s_max", 255))
                        v_min = int(getattr(config, "trigger_hsv_v_min", 0))
                        v_max = int(getattr(config, "trigger_hsv_v_max", 255))
                        color_radius = int(getattr(config, "trigger_color_radius_px", 20))
                        
                        # Get crosshair center based on capture mode
                        if config.capturer_mode.lower() in ["mss", "capturecard"]:
                            crosshair_center_x = config.fov_x_size / 2
                            crosshair_center_y = config.fov_y_size / 2
                        elif config.capturer_mode.lower() == "udp":
                            crosshair_center_x = config.udp_width / 2
                            crosshair_center_y = config.udp_height / 2
                        else:
                            crosshair_center_x = config.ndi_width / 2
                            crosshair_center_y = config.ndi_height / 2
                        
                        # Color detection - check for color in crosshair region
                        if detect_color_in_region(image, crosshair_center_x, crosshair_center_y, color_radius, h_min, h_max, s_min, s_max, v_min, v_max):
                            # Create virtual target for color detection
                            virtual_target = {
                                'x1': crosshair_center_x - color_radius,
                                'y1': crosshair_center_y - color_radius,
                                'x2': crosshair_center_x + color_radius,
                                'y2': crosshair_center_y + color_radius,
                                'conf': 1.0,
                                'class_name': 'color_target',
                                'dist': 0,  # At crosshair center
                                'center_x': crosshair_center_x,
                                'center_y': crosshair_center_y
                            }
                            
                            triggerbot_candidates.append({
                                'target': virtual_target,
                                'distance': 0,
                                'score': 1.0
                            })
                    
                    # Process candidates with firing mode logic
                    if triggerbot_candidates:
                        # Debug: Trigger candidates found (removed for cleaner output)
                        # Handle other modes with existing logic
                        best_candidate = max(triggerbot_candidates, key=lambda c: c['score'])
                        best_trigger_target = best_candidate['target']
                        # Debug: Best trigger target (removed for cleaner output)
                        
                        now = _now_ms()
                        
                        # Apply firing mode logic
                        # Debug: Trigger firing mode (removed for cleaner output)
                        if firing_mode.lower() == "spray":
                            # Spray mode: Start spraying when target detected, keep spraying until keybind released
                            if not _is_spraying:
                                makcu.left_press()
                                _is_spraying = True
                                triggerbot_status = "SPRAYING"
                                print(f"[SPRAY] Started spraying at target with {best_trigger_target['conf']:.2f} confidence")
                            else:
                                triggerbot_status = "SPRAYING"
                                # Only print every 30 frames to avoid spam
                                if int(now) % 30 == 0:
                                    print(f"[SPRAY] Continuing to spray... (target: {best_trigger_target['conf']:.2f})")
                                
                        elif firing_mode.lower() == "burst":
                            # Burst mode: Fire multiple shots in sequence
                            burst_shots = getattr(config, "burst_shots", 3)
                            burst_delay_ms = getattr(config, "burst_delay_ms", 40)
                            burst_cooldown_ms = getattr(config, "burst_cooldown_ms", 200)
                            
                            if _burst_shots_fired == 0 and (now - _last_trigger_time_ms >= burst_cooldown_ms):
                                # Start new burst
                                makcu.click()
                                _burst_shots_fired = 1
                                _last_trigger_time_ms = now
                                triggerbot_status = f"BURST 1/{burst_shots}"
                                print(f"[BURST] Started burst - shot 1/{burst_shots}")
                            elif 0 < _burst_shots_fired < burst_shots and (now - _last_trigger_time_ms >= burst_delay_ms):
                                # Continue burst
                                makcu.click()
                                _burst_shots_fired += 1
                                _last_trigger_time_ms = now
                                triggerbot_status = f"BURST {_burst_shots_fired}/{burst_shots}"
                                print(f"[BURST] Continued burst - shot {_burst_shots_fired}/{burst_shots}")
                            elif _burst_shots_fired >= burst_shots:
                                # Burst completed, reset for next burst
                                _burst_shots_fired = 0
                                triggerbot_status = "BURST READY"
                            else:
                                triggerbot_status = f"BURST COOLDOWN"
                                
                        elif firing_mode.lower() == "normal":
                            # Normal mode: Single shots with enhanced timing (CH341PAR improvement)
                            if _in_zone_since_ms == 0.0:
                                _in_zone_since_ms = now
                                triggerbot_status = "TARGETING"
                                print(f"[NORMAL] Started targeting - waiting {delay_ms}ms")

                            time_in_zone = now - _in_zone_since_ms
                            linger_ok = time_in_zone >= delay_ms
                            cooldown_ok = (now - _last_trigger_time_ms) >= cooldown_ms

                            # Debug: Normal mode status (removed for cleaner output)

                            if linger_ok and cooldown_ok:
                                triggerbot_status = "FIRING"
                                try:
                                    # Single click via MAKCU
                                    makcu.click()
                                    print(f"[NORMAL] Fired at target with {best_trigger_target['conf']:.2f} confidence")
                                    _last_trigger_time_ms = now
                                    _in_zone_since_ms = 0.0  # Reset for next cycle
                                except Exception as e:
                                    print(f"[WARN] Trigger click failed: {e}")
                                    _last_trigger_time_ms = now
                                    _in_zone_since_ms = 0.0
                            else:
                                if not linger_ok:
                                    triggerbot_status = f"WAITING ({time_in_zone:.0f}/{delay_ms}ms)"
                                    print(f"[NORMAL] Waiting for linger time: {time_in_zone:.0f}/{delay_ms}ms")
                                elif not cooldown_ok:
                                    cooldown_remaining = cooldown_ms - (now - _last_trigger_time_ms)
                                    triggerbot_status = f"COOLDOWN ({cooldown_remaining:.0f}ms)"
                                    print(f"[NORMAL] In cooldown: {cooldown_remaining:.0f}ms remaining")
                    else:
                        # No targets detected - cleanup based on firing mode
                        if firing_mode.lower() == "spray" and _is_spraying:
                            # Keep spraying even when no targets detected - only stop when keybind released
                            triggerbot_status = "SPRAYING (NO TARGET)"
                            # Only print every 30 frames to avoid spam
                            if int(now) % 30 == 0:
                                print(f"[SPRAY] Continuing to spray... (no targets detected)")
                        elif firing_mode.lower() == "normal" and _is_spraying:
                            # Stop firing when no target detected
                            makcu.left_release()
                            _is_spraying = False
                            print("[NORMAL] Stopped firing - no targets")
                        elif firing_mode.lower() == "burst" and _burst_shots_fired > 0:
                            # Reset burst counter when no targets
                            _burst_shots_fired = 0
                            print("[BURST] Reset burst - no targets")
                        
                        # Reset timing for normal mode
                        _in_zone_since_ms = 0.0
                        if detection_method == "color":
                            triggerbot_status = "NO_COLOR"
                        else:
                            triggerbot_status = "NO_TARGETS"
                else:
                    # Trigger not active - cleanup all firing modes
                    if firing_mode.lower() == "spray" and _is_spraying:
                        makcu.left_release()
                        _is_spraying = False
                        print("[SPRAY] Stopped spraying - trigger not active")
                    elif firing_mode.lower() == "normal" and _is_spraying:
                        makcu.left_release()
                        _is_spraying = False
                        print("[NORMAL] Stopped firing - trigger not active")
                    elif firing_mode.lower() == "burst" and _burst_shots_fired > 0:
                        _burst_shots_fired = 0
                        print("[BURST] Reset burst - trigger not active")
                    
                    _in_zone_since_ms = 0.0
                    if trigger_active:
                        triggerbot_status = "ACTIVE"
                    else:
                        triggerbot_status = "STANDBY"
        except Exception as e:
            print(f"[ERROR] Triggerbot block: {e}")
            triggerbot_status = "ERROR"

            
        # --- Enhanced Debug Window Display ---
        if debug_image is not None:
            # Use the original debug image as base (don't create fixed size window)
            debug_display = debug_image.copy()
            
            # Add enhanced text overlays only if text info is enabled
            if config.show_debug_text_info:
                # Button status with color coding
                primary_button_held = is_button_pressed(config.selected_mouse_button)
                secondary_button_held = (getattr(config, "secondary_aim_enabled", False) and 
                                       is_button_pressed(getattr(config, "secondary_aim_button", 2)))
                button_held = primary_button_held or secondary_button_held
                
                # Primary button status
                primary_text = f"Primary {config.selected_mouse_button}: {'HELD' if primary_button_held else 'released'}"
                primary_color = (0, 255, 0) if primary_button_held else (0, 0, 255)
                cv2.putText(debug_display, primary_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, primary_color, 2)
                
                # Secondary button status (if enabled)
                y_offset = 60
                if getattr(config, "secondary_aim_enabled", False):
                    secondary_text = f"Secondary {getattr(config, 'secondary_aim_button', 2)}: {'HELD' if secondary_button_held else 'released'}"
                    secondary_color = (0, 255, 0) if secondary_button_held else (0, 0, 255)
                    cv2.putText(debug_display, secondary_text, (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.7, secondary_color, 2)
                    y_offset += 30
                
                # Target and detection information
                target_text = f"Targets: {len(all_targets)} | Detected: {len(detected_classes)} classes"
                cv2.putText(debug_display, target_text, (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                y_offset += 30
                
                # Current settings display
                settings_text = f"Looking for: '{config.custom_player_label}', '{config.custom_head_label}'"
                cv2.putText(debug_display, settings_text, (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
                y_offset += 30
                
                # Current mode and FOV information
                mode_text = f"Mode: {mode.upper()}"
                cv2.putText(debug_display, mode_text, (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2)
                y_offset += 30
                
                # FOV Size information
                fov_x = getattr(config, "fov_x_size", config.region_size)
                fov_y = getattr(config, "fov_y_size", config.region_size)
                fov_text = f"FOV Size: {fov_x}x{fov_y}"
                cv2.putText(debug_display, fov_text, (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                y_offset += 30
                
                # Height targeting information
                if getattr(config, 'height_targeting_enabled', True):
                    height_text = f"Height Target: {config.target_height:.2f} | Deadzone: {config.height_deadzone_enabled}"
                    cv2.putText(debug_display, height_text, (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                    y_offset += 25
                
                # Mouse movement multipliers
                mult_x = getattr(config, 'mouse_movement_multiplier_x', 1.0)
                mult_y = getattr(config, 'mouse_movement_multiplier_y', 1.0)
                mult_text = f"Movement: X={mult_x:.2f} Y={mult_y:.2f}"
                cv2.putText(debug_display, mult_text, (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                y_offset += 25
                
                # Target switch delay status
                if getattr(config, "target_switch_delay_ms", 0) > 0:
                    delay_text = f"Target Switch Delay: {config.target_switch_delay_ms}ms"
                    if _last_target_id is not None and _target_switch_time > 0:
                        time_since_switch = _now_ms() - _target_switch_time
                        if time_since_switch < config.target_switch_delay_ms:
                            remaining = config.target_switch_delay_ms - time_since_switch
                            delay_text += f" (Active: {remaining:.0f}ms)"
                            delay_color = (0, 255, 255)  # Yellow when active
                        else:
                            delay_text += " (Ready)"
                            delay_color = (0, 255, 0)  # Green when ready
                    else:
                        delay_text += " (Standby)"
                        delay_color = (128, 128, 128)  # Gray when standby
                    
                    cv2.putText(debug_display, delay_text, (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, delay_color, 2)
                    y_offset += 25
                
                # Show smooth movement queue status
                if mode == "smooth":
                    queue_text = f"Smooth Queue: {smooth_move_queue.qsize()}/10"
                    cv2.putText(debug_display, queue_text, (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
                    y_offset += 25
                
                # Show triggerbot information
                if getattr(config, "trigger_enabled", False):
                    trigger_radius = getattr(config, "trigger_radius_px", 8)
                    trigger_delay = getattr(config, "trigger_delay_ms", 30)
                    trigger_method = getattr(config, "trigger_detection_method", "ai").upper()
                    trigger_status_text = f"Triggerbot: {triggerbot_status} | Radius: {trigger_radius}px | Delay: {trigger_delay}ms | Method: {trigger_method}"
                    trigger_color = (0, 255, 0) if triggerbot_status in ["FIRING", "SPRAYING"] else (255, 255, 0) if triggerbot_status in ["TARGETING", "WAITING"] else (128, 128, 128)
                    cv2.putText(debug_display, trigger_status_text, (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, trigger_color, 2)
                    y_offset += 25
                
                # Show detected classes at bottom
                if detected_classes:
                    classes_text = f"Classes: {', '.join(sorted(detected_classes))}"
                    cv2.putText(debug_display, classes_text, (10, debug_display.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
            
            # Draw crosshair and FOV rectangle
            img_height, img_width = debug_display.shape[:2]
            center = (img_width // 2, img_height // 2)
            
            # Draw crosshair at center
            cv2.drawMarker(debug_display, center, (255, 255, 255), cv2.MARKER_CROSS, 20, 2)
            
            # Draw triggerbot radius circle if enabled
            if getattr(config, "trigger_enabled", False):
                trigger_radius = getattr(config, "trigger_radius_px", 8)
                # Draw triggerbot radius circle around crosshair
                cv2.circle(debug_display, center, trigger_radius, (255, 0, 255), 2)  # Magenta circle
                # Add radius label
                if config.show_debug_text_info:
                    cv2.putText(debug_display, f"R: {trigger_radius}px", 
                               (center[0] + trigger_radius + 5, center[1] - 5), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 255), 1)
            
            # Draw FOV rectangle outline 
            fov_x = getattr(config, "fov_x_size", config.region_size)
            fov_y = getattr(config, "fov_y_size", config.region_size)
            fov_half_x = fov_x // 2
            fov_half_y = fov_y // 2
            
            fov_x1 = max(0, center[0] - fov_half_x)
            fov_y1 = max(0, center[1] - fov_half_y)
            fov_x2 = min(img_width, center[0] + fov_half_x)
            fov_y2 = min(img_height, center[1] + fov_half_y)
            
            # Draw FOV rectangle outline (the actual area being processed by AI)
            cv2.rectangle(debug_display, (fov_x1, fov_y1), (fov_x2, fov_y2), (0, 255, 255), 2)
            
            # Draw corner indicators for better visibility
            corner_size = 10
            # Top-left corner
            cv2.line(debug_display, (fov_x1, fov_y1), (fov_x1 + corner_size, fov_y1), (0, 255, 255), 3)
            cv2.line(debug_display, (fov_x1, fov_y1), (fov_x1, fov_y1 + corner_size), (0, 255, 255), 3)
            # Top-right corner
            cv2.line(debug_display, (fov_x2, fov_y1), (fov_x2 - corner_size, fov_y1), (0, 255, 255), 3)
            cv2.line(debug_display, (fov_x2, fov_y1), (fov_x2, fov_y1 + corner_size), (0, 255, 255), 3)
            # Bottom-left corner
            cv2.line(debug_display, (fov_x1, fov_y2), (fov_x1 + corner_size, fov_y2), (0, 255, 255), 3)
            cv2.line(debug_display, (fov_x1, fov_y2), (fov_x1, fov_y2 - corner_size), (0, 255, 255), 3)
            # Bottom-right corner
            cv2.line(debug_display, (fov_x2, fov_y2), (fov_x2 - corner_size, fov_y2), (0, 255, 255), 3)
            cv2.line(debug_display, (fov_x2, fov_y2), (fov_x2, fov_y2 - corner_size), (0, 255, 255), 3)
            
            # Add FOV label
            if config.show_debug_text_info:
                cv2.putText(debug_display, f"FOV: {fov_x}x{fov_y}", 
                           (fov_x1 + 5, fov_y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

            # Draw enhanced bounding boxes with height targeting visualization
            for target in all_targets:
                try:
                    # Check if target has required keys
                    if 'bbox' not in target or 'class_name' not in target or 'conf' not in target:
                        print(f"[WARN] Skipping invalid target: {target}")
                        continue
                    
                    x1, y1, x2, y2 = target['bbox']
                    class_name = target['class_name']
                    conf = target['conf']
                    is_target = target.get('is_target', False)
                    target_type = target.get('target_type', 'unknown')
                    inside_fov = target.get('inside_fov', False)
                    
                    # Draw bounding box with enhanced color coding
                    if is_target:
                        if target_type == "player":
                            color = (0, 255, 0)  # Green for players
                        else:
                            color = (0, 0, 255)  # Red for heads
                        thickness = 3
                        
                        # Dim boxes outside FOV
                        if not inside_fov:
                            color = tuple(c // 2 for c in color)  # Dim the color
                    else:
                        # Yellow for non-targets
                        color = (0, 255, 255)
                        thickness = 1
                    
                    cv2.rectangle(debug_display, (x1, y1), (x2, y2), color, thickness)
                    
                    # Label with class name and confidence
                    label = f"{class_name} {conf:.2f}"
                    if is_target:
                        label += f" [{target_type.upper()}]"
                        # Add FOV status to label
                        if inside_fov:
                            label += " [IN-FOV]"
                    
                    cv2.putText(debug_display, label, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                    
                    # Draw height targeting visualization for valid targets
                    if is_target and target_type == "player":
                        # Calculate target position based on height setting
                        target_x, target_y = calculate_height_target_position(x1, y1, x2, y2)
                        
                        # Draw target point (red circle)
                        cv2.circle(debug_display, (int(target_x), int(target_y)), 4, (0, 0, 255), -1)
                        
                        # Draw height deadzone if enabled
                        if getattr(config, 'height_targeting_enabled', True) and config.height_deadzone_enabled:
                            box_height = y2 - y1
                            
                            # Calculate deadzone bounds
                            deadzone_range = config.height_deadzone_max - config.height_deadzone_min
                            deadzone_center_ratio = (config.height_deadzone_min + config.height_deadzone_max) / 2
                            
                            deadzone_height_pixels = deadzone_range * box_height
                            deadzone_half_pixels = deadzone_height_pixels / 2
                            
                            deadzone_min_y = target_y - deadzone_half_pixels
                            deadzone_max_y = target_y + deadzone_half_pixels
                            
                            # Apply tolerance for "full entry"
                            tolerance = config.height_deadzone_tolerance
                            deadzone_inner_min = deadzone_min_y + tolerance
                            deadzone_inner_max = deadzone_max_y - tolerance
                            
                            # Draw outer deadzone (touching range) - light yellow overlay
                            overlay1 = debug_display.copy()
                            cv2.rectangle(overlay1, (x1, int(deadzone_min_y)), (x2, int(deadzone_max_y)), (0, 255, 255), -1)
                            cv2.addWeighted(debug_display, 0.85, overlay1, 0.15, 0, debug_display)
                            
                            # Draw inner deadzone (full entry range) - brighter yellow overlay
                            if deadzone_inner_min < deadzone_inner_max:
                                overlay2 = debug_display.copy()
                                cv2.rectangle(overlay2, (x1, int(deadzone_inner_min)), (x2, int(deadzone_inner_max)), (0, 255, 255), -1)
                                cv2.addWeighted(debug_display, 0.7, overlay2, 0.3, 0, debug_display)
                            
                            # Draw deadzone borders
                            cv2.line(debug_display, (x1, int(deadzone_min_y)), (x2, int(deadzone_min_y)), (0, 255, 255), 2)
                            cv2.line(debug_display, (x1, int(deadzone_max_y)), (x2, int(deadzone_max_y)), (0, 255, 255), 2)
                            
                            # Draw inner borders (full entry bounds)
                            if deadzone_inner_min < deadzone_inner_max:
                                cv2.line(debug_display, (x1, int(deadzone_inner_min)), (x2, int(deadzone_inner_min)), (0, 200, 255), 1)
                                cv2.line(debug_display, (x1, int(deadzone_inner_max)), (x2, int(deadzone_inner_max)), (0, 200, 255), 1)
                
                except Exception as e:
                    print(f"[WARN] Error drawing target: {e}, target: {target}")
                    continue

            # Enhanced debug window management
            win_name = "AI Debug"
            
            # Create window if it doesn't exist and make it resizable
            if not debug_window_moved:
                cv2.namedWindow(win_name, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
                cv2.resizeWindow(win_name, debug_display.shape[1], debug_display.shape[0])
                
                # Center the window on screen
                try:
                    screen_w, screen_h = config.screen_width, config.screen_height
                    win_w, win_h = debug_display.shape[1], debug_display.shape[0]
                    x = (screen_w - win_w) // 2
                    y = (screen_h - win_h) // 2
                    cv2.moveWindow(win_name, x, y)
                    debug_window_moved = True
                    print("[INFO] Debug window created and positioned at screen center - you can resize it as needed")
                except Exception as e:
                    # Debug: Could not position debug window (removed for cleaner output)
                    pass
            
            cv2.imshow(win_name, debug_display) 
            
            # Set window to always stay on top if enabled (only apply once per window creation)
            if getattr(config, "debug_always_on_top", False) and WIN32_AVAILABLE and not debug_window_moved:
                try:
                    hwnd = win32gui.FindWindow(None, win_name)
                    if hwnd:
                        # Set window to always stay on top
                        win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, 
                                            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
                        # Debug: Debug window set to always on top (removed for cleaner output)
                        debug_window_moved = True  # Mark as applied
                except Exception as e:
                    # Debug: Could not set debug window on top (removed for cleaner output)
                    debug_window_moved = True  # Mark as attempted to avoid spam
            
            # Handle window events and check if window was closed
            key = cv2.waitKey(1) & 0xFF
            
            # ESC key closes debug window
            if key == 27:  # ESC key
                config.show_debug_window = False
                print("[INFO] Debug window closed via ESC key")
                break
            
            # Check if user closed the window manually
            try:
                # Only check window property, avoid multiple detection methods
                window_property = cv2.getWindowProperty(win_name, cv2.WND_PROP_VISIBLE)
                if window_property < 0:  # Window was closed
                    config.show_debug_window = False
                    print("[INFO] Debug window closed by user")
                    break
            except Exception:
                # If we can't check the window property, assume it's closed
                config.show_debug_window = False
                print("[INFO] Debug window closed (property check failed)")
                break


        # --- FPS Calculation and Performance Monitoring ---
        frame_count += 1
        current_time = time.perf_counter()
        elapsed = current_time - start_time
        
        # Safety check: Ensure loop doesn't take too long
        loop_end_time = time.time()
        loop_duration = loop_end_time - loop_start_time
        if loop_duration > max_loop_time:
            print(f"[SAFETY] Long loop detected: {loop_duration:.3f}s - adding safety delay")
            time.sleep(0.005)  # 5ms safety delay
        
        # Update safety monitor
        update_frame_time()
        
        # Simple processing FPS calculation (safe and lightweight)
        processing_fps = fps  # Use the same FPS as capture for now
        
        # Calculate FPS more frequently for accurate display (every 0.1 seconds)
        if elapsed >= 0.1:  # Update FPS every 100ms for more responsive display
            fps = frame_count / elapsed
            true_fps = fps  # Store true FPS (uncapped by capture card)
            

            
            # Performance monitoring (reduced frequency)
            if frame_count % 500 == 0:  # Log performance every 500 frames to reduce overhead
                print(f"[PERF] Processing FPS: {processing_fps:.1f}, Capture FPS: {true_fps:.1f}")
            start_time = current_time
            frame_count = 0
        else:
            # Keep true_fps in sync with fps even when not updating
            true_fps = fps
        

    
    # Cleanup debug window when detection loop ends
    if config.show_debug_window:
        try:
            cv2.destroyWindow("AI Debug")
            print("[INFO] Debug window cleaned up safely")
        except Exception as e:
            print(f"[WARN] Debug window cleanup warning: {e}")
        finally:
            config.show_debug_window = False
    
    # Stop safety monitoring
    stop_safety_monitoring()
    print("[INFO] Detection loop ended safely")

def rcs_loop():
    """
    RCS (Recoil Control System) loop that monitors mouse button states
    and applies recoil compensation when shooting.
    
    Supports two modes:
    - Normal mode: Triggers on left mouse button only
    - ADS only mode: Triggers when both left and right mouse buttons are held
    """
    global _rcs_running, _last_left_click_state, _rcs_active, _rcs_start_time, makcu
    global _last_rcs_x_time, _last_rcs_y_time, _rcs_accumulated_x, _rcs_accumulated_y
    print("[INFO] RCS thread started")
    
    while _rcs_running:
        try:
            # Check if RCS is enabled in config
            if not config.rcs_enabled:
                time.sleep(0.01)  # Small delay when disabled
                continue
            
            # Monitor left mouse button (button index 0) and right mouse button (button index 1)
            current_left_click_state = is_button_pressed(0)
            current_right_click_state = is_button_pressed(1)
            
            # Determine if RCS should be active based on ADS only setting
            should_activate_rcs = current_left_click_state
            if config.rcs_ads_only:
                # ADS only mode: require both left and right mouse buttons to be held
                should_activate_rcs = current_left_click_state and current_right_click_state
            
            # Detect RCS activation (transition from False to True)
            if should_activate_rcs and not _rcs_active:
                # RCS started - begin recoil compensation
                _rcs_active = True
                current_time = time.time()
                _rcs_start_time = current_time
                _last_rcs_x_time = current_time  # Reset X timer
                _last_rcs_y_time = current_time  # Reset Y timer
                _rcs_accumulated_x = 0.0  # Reset accumulation
                _rcs_accumulated_y = 0.0  # Reset accumulation
                ads_status = " (ADS mode)" if config.rcs_ads_only else ""
                # Debug: RCS activated (removed for cleaner output)
            
            # Detect RCS deactivation (transition from True to False)
            elif not should_activate_rcs and _rcs_active:
                # RCS ended - stop recoil compensation
                _rcs_active = False
                ads_status = " (ADS mode)" if config.rcs_ads_only else ""
                # Debug: RCS deactivated (removed for cleaner output)
            
            # Apply RCS when active and conditions are met
            if _rcs_active and should_activate_rcs:
                current_time = time.time()
                shooting_duration = current_time - _rcs_start_time
                
                # Track what movements to apply this cycle
                x_movement = 0
                y_movement = 0
                
                # Apply X-axis downward compensation after initial delay and at regular intervals
                if shooting_duration >= config.rcs_x_delay:
                    # Check if enough time has passed since last X compensation
                    if current_time - _last_rcs_x_time >= config.rcs_x_delay:
                        # Apply X-axis compensation (downward movement) 
                        y_movement += config.rcs_x_strength  # Downward is positive Y
                        _last_rcs_x_time = current_time
                        # Debug: RCS X-compensation (removed for cleaner output)
                
                # Apply Y-axis random jitter if enabled and at separate intervals
                if config.rcs_y_random_enabled and shooting_duration >= config.rcs_y_random_delay:
                    # Check if enough time has passed since last Y jitter
                    if current_time - _last_rcs_y_time >= config.rcs_y_random_delay:
                        # Generate random horizontal movement (left/right jitter)
                        x_jitter = random.uniform(-config.rcs_y_random_strength, config.rcs_y_random_strength)
                        x_movement += x_jitter
                        _last_rcs_y_time = current_time
                        # Debug: RCS Y-jitter (removed for cleaner output)
                
                # Apply combined movement using accumulation for fractional values
                if x_movement != 0 or y_movement != 0:
                    # Accumulate fractional movements
                    _rcs_accumulated_x += x_movement
                    _rcs_accumulated_y += y_movement
                    
                    # Calculate integer movement to send
                    send_x = int(_rcs_accumulated_x)
                    send_y = int(_rcs_accumulated_y)
                    
                    # Subtract sent movement from accumulation
                    _rcs_accumulated_x -= send_x
                    _rcs_accumulated_y -= send_y
                    
                    # Send movement only if there's integer movement to send
                    if send_x != 0 or send_y != 0:
                        if makcu:
                            makcu.move(send_x, send_y)
                            # Debug: RCS movement sent (removed for cleaner output)
                        else:
                            # Debug: RCS accumulating (removed for cleaner output)
                            pass
            
            # Update the previous state
            _last_left_click_state = current_left_click_state
            
            # Small delay to prevent excessive CPU usage
            time.sleep(0.001)  # 1ms delay for high precision
            
        except Exception as e:
            print(f"[ERROR] RCS loop error: {e}")
            time.sleep(0.01)

def start_aimbot():
    global _aimbot_running, _aimbot_thread, _capture_thread, _smooth_thread, _rcs_running, _rcs_thread, makcu
    global _last_trigger_time_ms, _in_zone_since_ms
    _last_trigger_time_ms = 0.0
    _in_zone_since_ms = 0.0
    if _aimbot_running:
        return
    try:
        if makcu is None:  # <-- Initialize only once
            Mouse.cleanup()
            makcu=Mouse()
    except Exception as e:
        print(f"[ERROR] Failed to cleanup Mouse instance: {e}")

    _aimbot_running = True
    _rcs_running = True
    
    # Start capture thread
    _capture_thread = threading.Thread(target=capture_loop, daemon=True)
    _capture_thread.start()

    # Start smooth movement thread (for smooth mode)
    _smooth_thread = threading.Thread(target=smooth_movement_loop, daemon=True)
    _smooth_thread.start()

    # Start RCS thread
    _rcs_thread = threading.Thread(target=rcs_loop, daemon=True)
    _rcs_thread.start()

    # Start main detection thread
    _aimbot_thread = threading.Thread(target=detection_and_aim_loop, daemon=True)
    _aimbot_thread.start()

    button_names = ["Left", "Right", "Middle", "Side 4", "Side 5"]
    button_name = button_names[config.selected_mouse_button] if config.selected_mouse_button < len(button_names) else f"Button {config.selected_mouse_button}"
    print(f"[INFO] Aimbot started in {config.mode} mode. Hold {button_name} button to aim.")

def stop_aimbot():
    global _aimbot_running, _rcs_running, _last_trigger_time_ms, _in_zone_since_ms
    global _silent_original_pos, _silent_in_progress, _silent_last_activation
    global _last_left_click_state, _rcs_active, _rcs_start_time, _last_rcs_x_time, _last_rcs_y_time
    global _rcs_accumulated_x, _rcs_accumulated_y
    _aimbot_running = False
    _rcs_running = False
    _last_trigger_time_ms = 0.0
    _in_zone_since_ms = 0.0
    
    # Reset Enhanced Silent Mode state
    _silent_original_pos = None
    _silent_in_progress = False
    _silent_last_activation = 0.0
    
    # Reset RCS state
    _last_left_click_state = False
    _rcs_active = False
    _rcs_start_time = 0
    _last_rcs_x_time = 0
    _last_rcs_y_time = 0
    _rcs_accumulated_x = 0.0
    _rcs_accumulated_y = 0.0
    
    Mouse.mask_manager_tick(selected_idx=config.selected_mouse_button, aimbot_running=False)
    Mouse.mask_manager_tick(selected_idx=config.trigger_button, aimbot_running=False)
    try:
        if makcu is None:  # <-- Initialize only once
            Mouse.cleanup()
            makcu=Mouse()
    except Exception as e:
        print(f"[ERROR] Failed to cleanup Mouse instance: {e}")
    # Clear the smooth movement queue
    try:
        while not smooth_move_queue.empty():
            smooth_move_queue.get_nowait()
    except queue.Empty:
        pass

    # ensure spray click is released if it was active
    global _is_spraying
    if _is_spraying:
        try:
            makcu.left_release()
            print("[INFO] Spray mode click released on aimbot stop.")
        except Exception as e:
            print(f"[WARN] Failed to release spray click: {e}")
        _is_spraying = False

    # Set flag to false to let detection thread handle window cleanup
    config.show_debug_window = False
    
    # Small delay to allow detection thread to cleanup windows
    time.sleep(0.1)
    
    # Final cleanup attempt (failsafe)
    try:
        cv2.destroyAllWindows()
    except Exception:
        pass  # Ignore errors if window was already closed
    
    print("[INFO] Aimbot stopped.")

def is_aimbot_running():
    return _aimbot_running

# Rest of the utility functions remain the same
def reload_model(path=None):
    if path is None: path = config.model_path
    return load_model(path)

def get_model_classes(path=None):
    if path is None: path = config.model_path
    _, class_names = load_model(path)
    return [class_names[i] for i in sorted(class_names.keys())]

def get_model_size(path=None):
    if path is None: path = config.model_path
    try:
        return f"{os.path.getsize(path) / (1024*1024):.2f} MB"
    except Exception:
        return "?"

__all__ = [
    'start_aimbot', 'stop_aimbot', 'is_aimbot_running', 'reload_model',
    'get_model_classes', 'get_model_size', 'fps'
]
