from config import config
import customtkinter as ctk
from tkinter import messagebox
import main
from main import start_aimbot, stop_aimbot, is_aimbot_running, reload_model, get_model_classes, get_model_size
from mouse import connect_to_makcu, button_states, button_states_lock
import os
import glob
import cv2

class GUICallbacks:
    def refresh_all(self):
        self.fov_slider.set(config.region_size)
        self.fov_value.configure(text=str(config.region_size))
        self.offset_slider.set(config.player_y_offset)
        self.offset_value.configure(text=str(config.player_y_offset))
        self.btn_var.set(config.selected_mouse_button)
        self.mode_var.set(config.mode)
        self.model_name.set(os.path.basename(config.model_path))
        self.model_menu.set(os.path.basename(config.model_path))
        self.model_size.set(get_model_size(config.model_path))
        
        # Update aimbot status 
        self.aimbot_status.set("Running" if is_aimbot_running() else "Stopped")
            
        if config.makcu_connected:
            self.connection_status.set(config.makcu_status_msg)
            self.connection_color.set("#00FF00")
        else:
            self.connection_status.set(config.makcu_status_msg)
            self.connection_color.set("#b71c1c")
        self.conn_status_lbl.configure(text_color=self.connection_color.get())
        self.conf_slider.set(config.conf)
        self.conf_value.configure(text=f"{config.conf:.2f}")
        self.in_game_sens_slider.set(config.in_game_sens)
        self.in_game_sens_value.configure(text=f"{config.in_game_sens:.2f}")  # Fixed typo here
        self.imgsz_slider.set(config.imgsz)
        self.imgsz_value.configure(text=str(config.imgsz))
        self.load_class_list()
        self.update_dynamic_frame()
        self.update_idletasks()
        # Removed _autosize() call that was breaking window sizing
        self.toggle_humanize()
        self.debug_checkbox_var.set(config.show_debug_window)
        self.input_check_var.set(False)
        
        # Update always on top checkbox
        if hasattr(self, 'always_on_top_var'):
            self.always_on_top_var.set(getattr(config, "always_on_top", False))
            
        # Update triggerbot detection method and color frame visibility
        if hasattr(self, 'trigger_detection_method_var'):
            self.trigger_detection_method_var.set(getattr(config, "trigger_detection_method", "ai").title())
            # Force update color frame visibility
            self.after(100, self._update_color_frame_visibility)  # Delay to ensure GUI is ready

        # Update color outline filter
        if hasattr(self, 'outline_filter_var'):
            self.outline_filter_var.set(config.color_outline_filter_enabled)
            # Update outline color frame visibility
            if config.color_outline_filter_enabled:
                if hasattr(self, 'outline_color_frame') and self.outline_color_frame is not None:
                    self.outline_color_frame.grid(row=7, column=0, columnspan=3, sticky="ew", padx=6, pady=(8, 15))
            else:
                if hasattr(self, 'outline_color_frame') and self.outline_color_frame is not None:
                    self.outline_color_frame.grid_remove()

        self.error_text.set("")

    def on_connect(self):
        if connect_to_makcu():
            self.error_text.set("")
        else:
            self.error_text.set("Failed to connect! " + config.makcu_status_msg)
        self.refresh_all()

    def update_fov(self, val):
        config.region_size = int(round(val))
        self.fov_value.configure(text=str(config.region_size))

    def update_offset(self, val):
        config.player_y_offset = int(round(val))
        self.offset_value.configure(text=str(config.player_y_offset))

    def update_mouse_btn(self):
        config.selected_mouse_button = self.btn_var.get()

    def update_mode(self):
        old_mode = config.mode
        config.mode = self.mode_var.get()
        # Debug: Mode changed (removed for cleaner output)
        self.update_dynamic_frame()
        self.update_idletasks()
        # Removed _autosize() call that was breaking window sizing

    def update_conf(self, val):
        config.conf = round(float(val), 2)
        self.conf_value.configure(text=f"{config.conf:.2f}")

    def update_imgsz(self, val):
        config.imgsz = int(round(val))
        self.imgsz_value.configure(text=str(config.imgsz))

    def update_max_detect(self, val):
        val = int(round(float(val)))
        config.max_detect = val
        self.max_detect_label.configure(text=str(val))

    def update_in_game_sens(self, val):
        config.in_game_sens = round(float(val), 2)
        self.in_game_sens_value.configure(text=f"{config.in_game_sens:.2f}")

    def toggle_humanize(self):
        if self.aim_humanize_var.get():
            self.humanize_slider.grid(row=2, column=1, padx=(2, 12))
            self.humanize_slider_label.grid(row=2, column=2, padx=(2, 8))
            config.aim_humanization = int(self.humanize_slider.get())
        else:
            self.humanize_slider.grid_remove()
            self.humanize_slider_label.grid_remove()
            config.aim_humanization = 0

    def update_humanization(self, val):
        val = int(round(float(val)))
        self.humanize_slider_label.configure(text=str(val))
        config.aim_humanization = val

    def poll_fps(self):
        # Simple FPS display (safe and stable)
        self.fps_var.set(f"FPS: {main.fps:.1f}")
        
        # Update aimbot status
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
            except Exception as e:
                self.error_text.set(str(e))
        else:
            self.error_text.set(f"File not found: {path}")

    def reload_model(self):
        try:
            reload_model(config.model_path)
            self.load_class_list()
            self.error_text.set("")
        except Exception as e:
            self.error_text.set(str(e))

    def load_class_list(self):
        try:
            classes = get_model_classes(config.model_path)
            self.available_classes = classes
            self.class_listbox.delete("0.0", "end")
            
            # Handle both numeric and text classes
            for i, c in enumerate(classes):
                # Show both class ID and name for clarity
                display_text = f"Class {i}: {c}\n"
                self.class_listbox.insert("end", display_text)
            
            # Create dropdown options with both ID and name
            class_options = []
            for i, c in enumerate(classes):
                if str(c).isdigit():
                    # For numeric classes, show "ID: name" format
                    class_options.append(f"{c}")
                else:
                    # For text classes, show as-is
                    class_options.append(c)
            
            self.head_class_menu.configure(values=["None"] + class_options)
            self.player_class_menu.configure(values=class_options)
            
            # Set current values - handle numeric classes
            current_head = config.custom_head_label
            current_player = config.custom_player_label
            
            self.head_class_var.set(str(current_head) if current_head is not None else "None")
            self.player_class_var.set(str(current_player) if current_player is not None else "0")
            
        except Exception as e:
            self.error_text.set(f"Failed to load classes: {e}")

    def get_available_classes(self):
        classes = getattr(self, "available_classes", ["0", "1"])
        # Return string versions of classes for dropdown
        return [str(c) for c in classes]

    def set_head_class(self, val):
        if val == "None":
            config.custom_head_label = None
        else:
            # Handle numeric classes
            if val.isdigit():
                config.custom_head_label = val  # Keep as string for consistent comparison
            else:
                config.custom_head_label = val
        # Debug: Head class set (removed for cleaner output)

    def set_player_class(self, val):
        # Handle numeric classes
        if val.isdigit():
            config.custom_player_label = val  # Keep as string for consistent comparison
        else:
            config.custom_player_label = val
        # Debug: Player class set (removed for cleaner output)

    def update_trigger_mode(self):
        """Update original trigger mode (spray, burst, normal)"""
        config.trigger_mode = self.trigger_mode_var.get()
        print(f"[INFO] Firing mode set to: {config.trigger_mode}")
        
        # Save config
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save trigger mode: {e}")


    def on_trigger_detection_method_change(self, selected_value):
        """Handle trigger detection method change (AI/Color switch)"""
        # Debug: Callback started (removed for cleaner output)
        
        try:
            method = selected_value.lower()
            config.trigger_detection_method = method
            print(f"[INFO] 🔄 Trigger detection method changed to: {method.upper()}")
            
            # Debug: Color frame checks (removed for cleaner output)
            
            if hasattr(self, 'color_frame'):
                if self.color_frame is not None:
                    
                    if method == "color":
                        # Debug: Showing color frame (removed for cleaner output)
                        self.color_frame.grid(row=4, column=0, columnspan=2, sticky="ew", padx=15, pady=(5, 15))
                        print("[INFO] ✅ HSV color settings SHOWN (DIRECT)")
                    else:
                        # Debug: Hiding color frame (removed for cleaner output)
                        self.color_frame.grid_remove()
                        print("[INFO] ❌ HSV color settings HIDDEN (DIRECT)")
                    
                    # Force immediate GUI update
                    self.update_idletasks()
                    # Debug: GUI update completed (removed for cleaner output)
                else:
                    print("[ERROR] 🚨 color_frame is None!")
            else:
                print("[ERROR] 🚨 No color_frame attribute!")
                
        except Exception as callback_error:
            print(f"[ERROR] 🚨 CALLBACK FAILED: {callback_error}")
            import traceback
            traceback.print_exc()
        
        # Debug: Callback completed (removed for cleaner output)
        
        # Save config
        try:
            if hasattr(config, "save") and callable(config.save):
                config.save()
        except Exception as e:
            print(f"[WARN] Failed to save trigger detection method: {e}")

    def _update_color_frame_visibility(self):
        """Show/hide color detection HSV settings based on detection method"""
        try:
            # Check both config and GUI dropdown for current method
            config_method = getattr(config, "trigger_detection_method", "ai").lower()
            gui_method = "ai"
            
            if hasattr(self, 'trigger_detection_method_var'):
                gui_raw = self.trigger_detection_method_var.get()
                gui_method = gui_raw.lower()
                # Debug: GUI dropdown value (removed for cleaner output)
            
            # Use GUI method if available, otherwise use config
            current_method = gui_method if hasattr(self, 'trigger_detection_method_var') else config_method
            
            # Debug: Color frame check (removed for cleaner output)
            
            if hasattr(self, 'color_frame') and self.color_frame is not None:
                try:
                    # Check if frame is still valid
                    self.color_frame.winfo_exists()
                    
                    if current_method == "color":
                        # Show HSV settings
                        self.color_frame.grid(row=4, column=0, columnspan=2, sticky="ew", padx=15, pady=(5, 15))
                        print("[INFO] ✅ HSV color settings SHOWN")
                    else:
                        # Hide HSV settings
                        self.color_frame.grid_remove()
                        print("[INFO] ❌ HSV color settings HIDDEN")
                        
                    # Force GUI update
                    self.update_idletasks()
                    
                except Exception as widget_error:
                    print(f"[ERROR] Color frame widget error: {widget_error}")
                    # Debug: Color frame invalid (removed for cleaner output)
                    self.after(500, self._update_color_frame_visibility)
            else:
                print("[DEBUG] ⚠️ Color frame not found - will retry in 500ms")
                # Retry after a delay if frame not ready yet
                self.after(500, self._update_color_frame_visibility)
        except Exception as e:
            print(f"[ERROR] Failed to update color frame visibility: {e}")
            import traceback
            traceback.print_exc()
            
    def force_show_color_settings(self):
        """Force show color settings for debugging"""
        try:
            print("[DEBUG] 🔧 FORCE SHOW ATTEMPT:")
            print(f"[DEBUG] - Has color_frame: {hasattr(self, 'color_frame')}")
            
            if hasattr(self, 'color_frame') and self.color_frame is not None:
                print(f"[DEBUG] - Color frame widget: {self.color_frame}")
                print(f"[DEBUG] - Color frame master: {self.color_frame.master}")
                
                # Force show with explicit parameters
                self.color_frame.grid(row=4, column=0, columnspan=2, sticky="ew", padx=15, pady=(5, 15))
                print("[DEBUG] ✅ FORCE SHOWED color settings")
                
                # Also force update the config and dropdown
                config.trigger_detection_method = "color"
                if hasattr(self, 'trigger_detection_method_var'):
                    self.trigger_detection_method_var.set("Color")
                if hasattr(self, 'trigger_detection_method_menu'):
                    self.trigger_detection_method_menu.set("Color")
                    
                self.update_idletasks()
            else:
                print("[DEBUG] ❌ Color frame not available")
        except Exception as e:
            print(f"[ERROR] Force show failed: {e}")
            import traceback
            traceback.print_exc()
            
    def debug_color_frame_info(self):
        """Debug function to check color frame status"""
        print("\n[DEBUG] 🔍 COLOR FRAME DEBUG INFO:")
        print(f"- Has color_frame attribute: {hasattr(self, 'color_frame')}")
        if hasattr(self, 'color_frame'):
            print(f"- Color frame is not None: {self.color_frame is not None}")
            if self.color_frame is not None:
                print(f"- Color frame widget info: {self.color_frame}")
                try:
                    grid_info = self.color_frame.grid_info()
                    print(f"- Grid info: {grid_info}")
                except Exception as e:
                    print(f"- Grid info error: {e}")
        
        print(f"- Config detection method: {getattr(config, 'trigger_detection_method', 'unknown')}")
        if hasattr(self, 'trigger_detection_method_var'):
            print(f"- GUI detection method: {self.trigger_detection_method_var.get()}")
        print("🔍 END DEBUG INFO\n")

    def update_hsv_preview(self, val=None):
        """Update HSV sliders and color preview"""
        try:
            # Get current slider values
            h_min = int(self.hsv_h_min_slider.get())
            h_max = int(self.hsv_h_max_slider.get())
            s_min = int(self.hsv_s_min_slider.get())
            s_max = int(self.hsv_s_max_slider.get())
            v_min = int(self.hsv_v_min_slider.get())
            v_max = int(self.hsv_v_max_slider.get())
            
            # Update value labels
            self.hsv_h_min_value.configure(text=str(h_min))
            self.hsv_h_max_value.configure(text=str(h_max))
            self.hsv_s_min_value.configure(text=str(s_min))
            self.hsv_s_max_value.configure(text=str(s_max))
            self.hsv_v_min_value.configure(text=str(v_min))
            self.hsv_v_max_value.configure(text=str(v_max))
            
            # Calculate preview color (use middle of ranges)
            h_mid = (h_min + h_max) // 2
            s_mid = (s_min + s_max) // 2
            v_mid = (v_min + v_max) // 2
            
            # Convert HSV to RGB for preview
            import colorsys
            r, g, b = colorsys.hsv_to_rgb(h_mid/179, s_mid/255, v_mid/255)
            hex_color = f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
            
            # Update preview color
            self.color_preview.configure(fg_color=hex_color)
            
            # Update config
            config.trigger_hsv_h_min = h_min
            config.trigger_hsv_h_max = h_max
            config.trigger_hsv_s_min = s_min
            config.trigger_hsv_s_max = s_max
            config.trigger_hsv_v_min = v_min
            config.trigger_hsv_v_max = v_max
            
            # Debounced save
            self._schedule_config_save()
            
        except Exception as e:
            print(f"[WARN] HSV preview update failed: {e}")

    def update_color_radius(self, val):
        """Update color detection radius"""
        val = int(round(float(val)))
        config.trigger_color_radius_px = val
        self.color_radius_value.configure(text=str(val))
        self._schedule_config_save()

    def update_color_delay(self, val):
        """Update color detection delay"""
        val = int(round(float(val)))
        config.trigger_color_delay_ms = val
        self.color_delay_value.configure(text=str(val))
        self._schedule_config_save()

    def update_color_cooldown(self, val):
        """Update color detection cooldown"""
        val = int(round(float(val)))
        config.trigger_color_cooldown_ms = val
        self.color_cooldown_value.configure(text=str(val))
        self._schedule_config_save()

    # GAN-Aimbot Research Based Functions
    def on_gan_smoothing_toggle(self):
        """Toggle GAN-based human-like movement"""
        config.gan_smoothing_enabled = bool(self.gan_smoothing_enabled_var.get())
        status = "enabled" if config.gan_smoothing_enabled else "disabled"
        print(f"[INFO] 🧠 GAN-based human-like movement {status}")
        self._schedule_config_save()

    def update_movement_variability(self, val):
        """Update movement variability (Gaussian noise injection)"""
        val = round(float(val), 2)
        config.movement_variability = val
        
        # Update both static and dynamic slider labels
        if hasattr(self, 'movement_variability_value'):
            self.movement_variability_value.configure(text=f"{val:.2f}")
        if hasattr(self, 'gan_variability_value'):
            self.gan_variability_value.configure(text=f"{val:.2f}")
        self._schedule_config_save()

    def update_reaction_delay(self, val):
        """Update human reaction delay simulation"""
        val = int(round(float(val)))
        config.human_reaction_delay_ms = val
        
        # Update both static and dynamic slider labels
        if hasattr(self, 'reaction_delay_value'):
            self.reaction_delay_value.configure(text=str(val))
        if hasattr(self, 'gan_reaction_value'):
            self.gan_reaction_value.configure(text=str(val))
        self._schedule_config_save()

    def update_overshoot_chance(self, val):
        """Update overshoot probability (humans overshoot and correct)"""
        val = int(round(float(val)))
        config.overshoot_chance_percent = val
        
        # Update both static and dynamic slider labels
        if hasattr(self, 'overshoot_chance_value'):
            self.overshoot_chance_value.configure(text=str(val))
        if hasattr(self, 'gan_overshoot_value'):
            self.gan_overshoot_value.configure(text=str(val))
        self._schedule_config_save()

    def update_micro_corrections(self, val):
        """Update micro-corrections intensity"""
        val = round(float(val), 2)
        config.micro_corrections_intensity = val
        
        # Update both static and dynamic slider labels
        if hasattr(self, 'micro_corrections_value'):
            self.micro_corrections_value.configure(text=f"{val:.2f}")
        if hasattr(self, 'gan_micro_value'):
            self.gan_micro_value.configure(text=f"{val:.2f}")
        self._schedule_config_save()

    def update_trajectory_smoothness(self, val):
        """Update trajectory smoothness (natural curve generation)"""
        val = round(float(val), 2)
        config.trajectory_smoothness = val
        if hasattr(self, 'trajectory_smoothness_value'):
            self.trajectory_smoothness_value.configure(text=f"{val:.2f}")
        self._schedule_config_save()

    def update_fatigue_simulation(self, val):
        """Update fatigue simulation (performance degradation over time)"""
        val = round(float(val), 2)
        config.fatigue_simulation = val
        if hasattr(self, 'fatigue_simulation_value'):
            self.fatigue_simulation_value.configure(text=f"{val:.2f}")
        self._schedule_config_save()

    def update_context_memory(self, val):
        """Update context memory frames (movement depends on previous actions)"""
        val = int(round(float(val)))
        config.context_memory_frames = val
        if hasattr(self, 'context_memory_value'):
            self.context_memory_value.configure(text=str(val))
        self._schedule_config_save()

    def update_performance_variation(self, val):
        """Update performance variation (humans don't perform consistently)"""
        val = round(float(val), 2)
        config.performance_variation = val
        
        # Update both static and dynamic slider labels
        if hasattr(self, 'performance_variation_value'):
            self.performance_variation_value.configure(text=f"{val:.2f}")
        if hasattr(self, 'gan_performance_value'):
            self.gan_performance_value.configure(text=f"{val:.2f}")
        self._schedule_config_save()

    def update_intentional_miss(self, val):
        """Update intentional miss rate (humans occasionally miss)"""
        val = int(round(float(val)))
        config.intentional_miss_percent = val
        
        # Update both static and dynamic slider labels
        if hasattr(self, 'intentional_miss_value'):
            self.intentional_miss_value.configure(text=str(val))
        if hasattr(self, 'gan_miss_value'):
            self.gan_miss_value.configure(text=str(val))
        self._schedule_config_save()

    def update_axis_independence(self, val):
        """Update axis independence (humans move X and Y differently)"""
        val = round(float(val), 2)
        config.axis_independence = val
        if hasattr(self, 'axis_independence_value'):
            self.axis_independence_value.configure(text=f"{val:.2f}")
        self._schedule_config_save()

    def set_gan_legit_preset(self):
        """Set GAN settings to legit/undetectable preset - ULTRA STEALTH"""
        # Core humanization (very conservative for maximum stealth)
        config.movement_variability = 0.08   # Low jitter but not too perfect
        config.human_reaction_delay_ms = 90  # Natural reaction time
        config.overshoot_chance_percent = 6   # Minimal overshooting
        config.micro_corrections_intensity = 0.06  # Very subtle micro-corrections
        config.performance_variation = 0.12  # Low inconsistency
        config.intentional_miss_percent = 2   # Very few misses
        config.axis_independence = 0.85      # Good axis independence
        
        # Natural movement enhancements
        config.movement_smoothness = 0.88    # Smooth interpolation
        config.hand_tremor_intensity = 0.012 # Subtle hand tremor
        config.natural_acceleration = 0.35   # Natural speed variation
        
        # Advanced humanization (conservative)
        config.muscle_memory_strength = 0.15  # Light muscle memory
        config.fatigue_simulation = 0.08     # Minimal fatigue
        config.context_awareness = True      # Context awareness
        config.breathing_amplitude = 0.008   # Very subtle breathing
        config.skill_level = 0.7            # Higher skill level
        config.consistency = 0.85           # High consistency
        
        # Movement context tracking
        config.movement_context = "idle"
        config.previous_movements = []
        config.session_duration = 0.0
        config.fatigue_level = 0.0
        config.breathing_cycle = 0.0
        config.heart_rate = 65              # Calm heart rate
        
        print("[INFO] 🎯 Applied GAN Legit preset (Ultra Stealth - Undetectable)")
        self._schedule_config_save()
        self._refresh_gan_sliders()

    def set_gan_rage_preset(self):
        """Set GAN settings to rage/aggressive preset - FAST & AGGRESSIVE"""
        # Core humanization (aggressive but still human-like)
        config.movement_variability = 0.15   # Higher jitter for aggressive feel
        config.human_reaction_delay_ms = 60  # Fast reaction time
        config.overshoot_chance_percent = 15  # More overshooting for aggressive style
        config.micro_corrections_intensity = 0.12  # Moderate micro-corrections
        config.performance_variation = 0.20  # Higher inconsistency
        config.intentional_miss_percent = 3   # Few misses but some
        config.axis_independence = 0.75      # Lower axis independence for speed
        
        # Natural movement enhancements
        config.movement_smoothness = 0.80    # Less smooth for aggressive feel
        config.hand_tremor_intensity = 0.025 # More tremor for aggressive style
        config.natural_acceleration = 0.6    # High speed variation
        
        # Advanced humanization (aggressive)
        config.muscle_memory_strength = 0.20  # Moderate muscle memory
        config.fatigue_simulation = 0.25     # Higher fatigue for aggressive play
        config.context_awareness = True      # Context awareness
        config.breathing_amplitude = 0.015   # More noticeable breathing
        config.skill_level = 0.5            # Moderate skill level
        config.consistency = 0.65           # Lower consistency for aggressive play
        
        # Movement context tracking
        config.movement_context = "idle"
        config.previous_movements = []
        config.session_duration = 0.0
        config.fatigue_level = 0.0
        config.breathing_cycle = 0.0
        config.heart_rate = 85              # Elevated heart rate
        
        print("[INFO] ⚡ Applied GAN Rage preset (Fast & Aggressive - High Performance)")
        self._schedule_config_save()
        self._refresh_gan_sliders()

    def set_gan_human_preset(self):
        """Set GAN settings to balanced human-like preset - NATURAL & SMOOTH"""
        # Core humanization (balanced for natural feel)
        config.movement_variability = 0.10   # Moderate jitter for natural feel
        config.human_reaction_delay_ms = 100 # Natural reaction time
        config.overshoot_chance_percent = 8   # Moderate overshooting
        config.micro_corrections_intensity = 0.07  # Subtle micro-corrections
        config.performance_variation = 0.16  # Moderate inconsistency
        config.intentional_miss_percent = 4   # Some intentional misses
        config.axis_independence = 0.90      # High axis independence
        
        # Natural movement enhancements
        config.movement_smoothness = 0.90    # Very smooth interpolation
        config.hand_tremor_intensity = 0.018 # Subtle hand tremor
        config.natural_acceleration = 0.45   # Natural speed variation
        
        # Advanced humanization (balanced)
        config.muscle_memory_strength = 0.30  # Strong muscle memory
        config.fatigue_simulation = 0.12     # Moderate fatigue
        config.context_awareness = True      # Context awareness
        config.breathing_amplitude = 0.012   # Subtle breathing effect
        config.skill_level = 0.65           # Good skill level
        config.consistency = 0.80           # High consistency
        
        # Movement context tracking
        config.movement_context = "idle"
        config.previous_movements = []
        config.session_duration = 0.0
        config.fatigue_level = 0.0
        config.breathing_cycle = 0.0
        config.heart_rate = 72              # Normal heart rate
        
        print("[INFO] 👤 Applied GAN Human preset (Natural & Smooth - Balanced Human-like)")
        self._schedule_config_save()
        self._refresh_gan_sliders()

    def set_gan_ultra_human_preset(self):
        """Set GAN settings to practically indistinguishable preset - MAXIMUM HUMAN-LIKE"""
        # Core humanization parameters (optimized for maximum realism)
        config.movement_variability = 0.12   # Moderate jitter (more natural than current 0.01)
        config.human_reaction_delay_ms = 80  # Natural reaction time (faster than current 120)
        config.overshoot_chance_percent = 12  # Realistic overshooting (more than current 10)
        config.micro_corrections_intensity = 0.08  # Subtle corrections (more than current 0.05)
        config.performance_variation = 0.18  # Human inconsistency (more than current 0.15)
        config.intentional_miss_percent = 4   # Fewer misses (less than current 6)
        config.axis_independence = 0.88      # Good axis independence (less than current 0.95)
        
        # Natural movement enhancements (optimized for realism)
        config.movement_smoothness = 0.92    # Very smooth (less than current 0.95)
        config.hand_tremor_intensity = 0.015 # Subtle tremor (more than current 0.01)
        config.natural_acceleration = 0.4    # Natural speed variation (more than current 0.3)
        
        # Advanced humanization parameters (new)
        config.muscle_memory_strength = 0.25  # How much previous movements affect current
        config.fatigue_simulation = 0.15     # Performance degradation over time
        config.context_awareness = True      # Movement depends on context
        config.breathing_amplitude = 0.01    # Subtle breathing effect
        config.skill_level = 0.6            # Moderate skill level (0.0-1.0)
        config.consistency = 0.75           # How consistent the player is
        
        # Movement context tracking
        config.movement_context = "idle"     # Current movement type
        config.previous_movements = []       # Track recent movements for muscle memory
        config.session_duration = 0.0        # Time since start
        config.fatigue_level = 0.0          # Current fatigue level
        config.breathing_cycle = 0.0         # Breathing cycle for natural variation
        config.heart_rate = 70              # BPM for subtle effects
        
        print("[INFO] 🧠 Applied GAN Ultra-Human preset (Practically Indistinguishable)")
        print("[INFO] 🎯 Features: Dynamic variability, muscle memory, fatigue, context awareness")
        self._schedule_config_save()
        self._refresh_gan_sliders()

    def _refresh_gan_sliders(self):
        """Refresh GAN slider values after preset change"""
        try:
            if hasattr(self, 'gan_variability_slider'):
                self.gan_variability_slider.set(config.movement_variability)
                self.gan_variability_value.configure(text=f"{config.movement_variability:.2f}")
            if hasattr(self, 'gan_reaction_slider'):
                self.gan_reaction_slider.set(config.human_reaction_delay_ms)
                self.gan_reaction_value.configure(text=str(config.human_reaction_delay_ms))
            if hasattr(self, 'gan_overshoot_slider'):
                self.gan_overshoot_slider.set(config.overshoot_chance_percent)
                self.gan_overshoot_value.configure(text=str(config.overshoot_chance_percent))
            if hasattr(self, 'gan_performance_slider'):
                self.gan_performance_slider.set(config.performance_variation)
                self.gan_performance_value.configure(text=f"{config.performance_variation:.2f}")
            if hasattr(self, 'gan_micro_slider'):
                self.gan_micro_slider.set(config.micro_corrections_intensity)
                self.gan_micro_value.configure(text=f"{config.micro_corrections_intensity:.2f}")
            if hasattr(self, 'gan_miss_slider'):
                self.gan_miss_slider.set(config.intentional_miss_percent)
                self.gan_miss_value.configure(text=str(config.intentional_miss_percent))
        except Exception as e:
            print(f"[WARN] Failed to refresh GAN sliders: {e}")

    def update_dynamic_frame(self):
        for w in self.dynamic_frame.winfo_children():
            w.destroy()
        mode = config.mode
        print(f"[DEBUG] 🔄 Updating dynamic frame for mode: {mode}")
        
        if mode == "normal":
            self.add_speed_section("Normal", "normal_x_speed", "normal_y_speed")
        elif mode == "bezier":
            self.add_bezier_section("bezier_segments", "bezier_ctrl_x", "bezier_ctrl_y")
        elif mode == "silent":
            self.add_bezier_section("silent_segments", "silent_ctrl_x", "silent_ctrl_y")
            self.add_silent_section()
        elif mode == "smooth":
            self.add_smooth_section()
        elif mode == "gan":
            print("[DEBUG] 🧠 Adding GAN section...")
            try:
                print(f"[DEBUG] 🧠 Has add_gan_section: {hasattr(self, 'add_gan_section')}")
                if hasattr(self, 'add_gan_section'):
                    self.add_gan_section()
                    print("[DEBUG] ✅ GAN section added successfully")
                else:
                    print("[ERROR] ❌ add_gan_section method not found!")
            except Exception as e:
                print(f"[ERROR] 🧠 GAN section failed: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"[WARN] Unknown aimbot mode: {mode}")

    def _autosize(self):
        self.update_idletasks()
        req_width = self.winfo_reqwidth()
        req_height = self.winfo_reqheight()
        self.geometry(f"{req_width}x{req_height}")

    def save_profile(self):
        config.save()
        messagebox.showinfo("Profile Saved", "Config saved!")

    def load_profile(self):
        config.load()
        self.refresh_all()
        
        # Force update detection method dropdown and color frame visibility after profile load
        if hasattr(self, 'trigger_detection_method_var') and hasattr(self, 'trigger_detection_method_menu'):
            # Fix the case sensitivity issue - ensure proper capitalization
            raw_method = getattr(config, "trigger_detection_method", "ai").lower()
            if raw_method == "ai":
                proper_method = "AI"
            elif raw_method == "color":
                proper_method = "Color"
            else:
                proper_method = "AI"  # Default fallback
                
            print(f"[DEBUG] 🔄 Profile loaded - raw: '{raw_method}' → proper: '{proper_method}'")
            
            # Update both the variable and the menu display
            self.trigger_detection_method_var.set(proper_method)
            self.trigger_detection_method_menu.set(proper_method)
            
            # Also ensure config is properly set
            config.trigger_detection_method = raw_method
            
            # Force update color frame visibility with multiple attempts
            self.after(50, self._update_color_frame_visibility)   # First attempt
            self.after(200, self._update_color_frame_visibility)  # Second attempt
            self.after(500, self._update_color_frame_visibility)  # Third attempt (fallback)
            print("[DEBUG] 📅 Scheduled color frame visibility updates after profile load")

    def reset_defaults(self):
        config.reset_to_defaults()
        self.refresh_all()

    def start_aimbot(self):
        start_aimbot()
        button_names = ["Left", "Right", "Middle", "Side 4", "Side 5"]
        button_name = button_names[config.selected_mouse_button] if config.selected_mouse_button < len(button_names) else f"Button {config.selected_mouse_button}"
        self.error_text.set(f"Aimbot started. Hold {button_name} to aim.")

    def stop_aimbot(self):
        stop_aimbot()
        self.aimbot_status.set("Stopped")
        self.error_text.set("")

    def on_close(self):
        stop_aimbot()
        self.destroy()

    def on_debug_toggle(self):
        config.show_debug_window = self.debug_checkbox_var.get()
        if not config.show_debug_window:
            try:
                cv2.destroyWindow("AI Debug")
            except Exception:
                pass

    def on_input_check_toggle(self):
        if self.input_check_var.get():
            self.show_input_check_window()
        else:
            self.hide_input_check_window()

    def show_input_check_window(self):
        if hasattr(self, 'input_check_window') and self.input_check_window is not None:
            return
        self.input_check_window = ctk.CTkToplevel(self)
        self.input_check_window.title("Button States")
        self.input_check_window.geometry("220x160")
        self.input_check_window.resizable(False, False)
        self.input_check_window.configure(bg="#181818")
        self.input_check_labels = []
        for i in range(5):
            lbl = ctk.CTkLabel(self.input_check_window, text=f"Button {i}:", text_color="#fff", font=("Segoe UI", 16, "bold"))
            lbl.pack(anchor="w", padx=18, pady=6)
            self.input_check_labels.append(lbl)
        self.update_input_check_window()
        self.input_check_window.protocol("WM_DELETE_WINDOW", self._on_input_check_close)

    def update_input_check_window(self):
        if not hasattr(self, 'input_check_window') or self.input_check_window is None:
            return
        with button_states_lock:
            for i, lbl in enumerate(self.input_check_labels):
                state = button_states.get(i, False)
                color = "#00FF00" if state else "#FF5555"
                lbl.configure(text=f"Button {i}: {state}", text_color=color)
        self.after(50, self.update_input_check_window)

    def hide_input_check_window(self):
        if hasattr(self, 'input_check_window') and self.input_check_window:
            self.input_check_window.destroy()
            self.input_check_window = None

    def _on_input_check_close(self):
        self.input_check_var.set(False)
        self.hide_input_check_window()

    def toggle_outline_filter(self):
        """Toggle color outline filter on/off"""
        config.color_outline_filter_enabled = self.outline_filter_var.get()
        print(f"[DEBUG] 🎨 Color outline filter checkbox clicked! Current value: {config.color_outline_filter_enabled}")
        print(f"[INFO] 🎨 Color outline filter {'ENABLED' if config.color_outline_filter_enabled else 'DISABLED'}")
        print(f"[DEBUG] 🎨 Config object color_outline_filter_enabled: {getattr(config, 'color_outline_filter_enabled', 'NOT_FOUND')}")

        self._schedule_config_save()
        print(f"[DEBUG] 🎨 Config save scheduled")
