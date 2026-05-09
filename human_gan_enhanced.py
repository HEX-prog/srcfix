"""
Enhanced Human-like GAN Movement System
Makes mouse movements indistinguishable from real human players
"""

import random
import math
import time
import numpy as np
from collections import deque

class HumanMovementGAN:
    def __init__(self):
        # Human behavior parameters
        self.fatigue_level = 0.0  # Accumulates over time
        self.stress_level = 0.0   # Increases with fast movements
        self.focus_level = 1.0    # Decreases over time, resets with breaks
        
        # Movement history for learning
        self.movement_history = deque(maxlen=100)
        self.reaction_times = deque(maxlen=20)
        self.accuracy_history = deque(maxlen=50)
        
        # Human timing patterns
        self.last_movement_time = 0
        self.movement_rhythm = random.uniform(0.8, 1.2)  # Personal rhythm
        
        # Muscle memory simulation
        self.muscle_memory = {}  # Store common movement patterns
        self.hand_dominance = random.choice(['right', 'left'])  # Affects movement bias
        
        # Micro-movement patterns
        self.micro_tremor_phase = 0.0
        self.breathing_phase = 0.0
        self.heartbeat_phase = 0.0
        
        print(f"[GAN] Human movement system initialized - Hand: {self.hand_dominance}")
    
    def apply_human_enhancements(self, dx, dy, target_distance=None, movement_urgency=1.0):
        """
        Apply comprehensive human-like enhancements to mouse movement
        
        Args:
            dx, dy: Target movement
            target_distance: Distance to target (affects behavior)
            movement_urgency: How urgent the movement is (0.0 to 1.0)
        """
        original_dx, original_dy = dx, dy
        movement_distance = math.sqrt(dx*dx + dy*dy)
        
        if movement_distance < 1:
            return dx, dy
        
        # Update human state
        self._update_human_state(movement_distance, movement_urgency)
        
        # Apply human behaviors in order of importance
        dx, dy = self._apply_reaction_time_variation(dx, dy, movement_urgency)
        dx, dy = self._apply_fatigue_effects(dx, dy)
        dx, dy = self._apply_stress_effects(dx, dy, movement_urgency)
        dx, dy = self._apply_micro_movements(dx, dy)
        dx, dy = self._apply_hand_dominance_bias(dx, dy)
        dx, dy = self._apply_muscle_memory(dx, dy)
        dx, dy = self._apply_natural_acceleration(dx, dy, movement_distance)
        dx, dy = self._apply_human_imperfections(dx, dy, movement_distance)
        dx, dy = self._apply_breathing_heartbeat(dx, dy)
        
        # Store movement for learning
        self.movement_history.append((original_dx, original_dy, dx, dy, time.time()))
        
        return dx, dy
    
    def _update_human_state(self, movement_distance, urgency):
        """Update human state variables"""
        current_time = time.time()
        time_since_last = current_time - self.last_movement_time
        
        # Update fatigue (accumulates with large movements)
        if movement_distance > 50:
            self.fatigue_level = min(1.0, self.fatigue_level + 0.02)
        else:
            self.fatigue_level = max(0.0, self.fatigue_level - 0.001)  # Slow recovery
        
        # Update stress (increases with urgent movements)
        stress_increase = urgency * 0.05
        self.stress_level = min(1.0, self.stress_level + stress_increase)
        self.stress_level = max(0.0, self.stress_level - 0.01)  # Stress decreases over time
        
        # Update focus (decreases over time, affected by breaks)
        if time_since_last > 2.0:  # Break longer than 2 seconds
            self.focus_level = min(1.0, self.focus_level + 0.1)  # Focus recovers
        else:
            self.focus_level = max(0.3, self.focus_level - 0.002)  # Focus decreases
        
        self.last_movement_time = current_time
    
    def _apply_reaction_time_variation(self, dx, dy, urgency):
        """Simulate human reaction time variations"""
        # Base reaction time: 150-250ms for gaming
        base_reaction = random.uniform(0.15, 0.25)
        
        # Factors affecting reaction time
        fatigue_factor = 1.0 + (self.fatigue_level * 0.3)  # Fatigue slows reactions
        stress_factor = 0.9 + (self.stress_level * 0.2)    # Stress can speed up reactions
        focus_factor = 0.8 + (self.focus_level * 0.4)      # Focus improves reactions
        
        reaction_time = base_reaction * fatigue_factor * stress_factor * focus_factor
        
        # Store reaction time
        self.reaction_times.append(reaction_time)
        
        # Apply reaction time delay effect to movement
        # Humans don't move instantly - there's always a slight delay
        delay_factor = 1.0 - (reaction_time * urgency * 0.1)
        
        return dx * delay_factor, dy * delay_factor
    
    def _apply_fatigue_effects(self, dx, dy):
        """Apply fatigue effects to movement"""
        if self.fatigue_level > 0.1:
            # Fatigue causes:
            # 1. Reduced precision
            precision_loss = self.fatigue_level * 0.15
            dx *= (1.0 - precision_loss + random.uniform(-0.05, 0.05))
            dy *= (1.0 - precision_loss + random.uniform(-0.05, 0.05))
            
            # 2. Slight tremor
            tremor_strength = self.fatigue_level * 2.0
            dx += random.uniform(-tremor_strength, tremor_strength)
            dy += random.uniform(-tremor_strength, tremor_strength)
        
        return dx, dy
    
    def _apply_stress_effects(self, dx, dy, urgency):
        """Apply stress effects to movement"""
        if self.stress_level > 0.2:
            # Stress causes:
            # 1. Overcorrection
            if urgency > 0.7:  # High urgency movements
                overcorrect_factor = 1.0 + (self.stress_level * 0.1)
                dx *= overcorrect_factor
                dy *= overcorrect_factor
            
            # 2. Jittery movements
            jitter_strength = self.stress_level * 1.5
            dx += random.uniform(-jitter_strength, jitter_strength)
            dy += random.uniform(-jitter_strength, jitter_strength)
        
        return dx, dy
    
    def _apply_micro_movements(self, dx, dy):
        """Add realistic micro-movements"""
        # Micro-tremor (always present in humans)
        self.micro_tremor_phase += random.uniform(0.1, 0.3)
        tremor_x = math.sin(self.micro_tremor_phase * 2.1) * 0.3
        tremor_y = math.cos(self.micro_tremor_phase * 1.7) * 0.3
        
        # Hand steadiness varies with focus
        steadiness = self.focus_level * 0.7 + 0.3  # 0.3 to 1.0
        tremor_x *= (1.0 - steadiness)
        tremor_y *= (1.0 - steadiness)
        
        return dx + tremor_x, dy + tremor_y
    
    def _apply_hand_dominance_bias(self, dx, dy):
        """Apply hand dominance bias to movements"""
        if self.hand_dominance == 'right':
            # Right-handed people tend to move slightly right and down
            dx += random.uniform(0, 0.5)
            dy += random.uniform(0, 0.3)
        else:
            # Left-handed people tend to move slightly left and down
            dx += random.uniform(-0.5, 0)
            dy += random.uniform(0, 0.3)
        
        return dx, dy
    
    def _apply_muscle_memory(self, dx, dy):
        """Simulate muscle memory for common movements"""
        movement_distance = math.sqrt(dx*dx + dy*dy)
        
        # Create movement signature
        if movement_distance > 10:
            angle = math.atan2(dy, dx)
            distance_bucket = int(movement_distance / 20) * 20  # Group by 20-pixel buckets
            signature = f"{angle:.1f}_{distance_bucket}"
            
            # Check if we've done this movement before
            if signature in self.muscle_memory:
                stored_dx, stored_dy, confidence = self.muscle_memory[signature]
                
                # Blend with stored movement (muscle memory effect)
                memory_strength = min(confidence * 0.3, 0.5)  # Max 50% influence
                dx = dx * (1 - memory_strength) + stored_dx * memory_strength
                dy = dy * (1 - memory_strength) + stored_dy * memory_strength
                
                # Increase confidence
                self.muscle_memory[signature] = (stored_dx, stored_dy, min(confidence + 0.1, 1.0))
            else:
                # Store new movement pattern
                self.muscle_memory[signature] = (dx, dy, 0.1)
                
                # Limit muscle memory size
                if len(self.muscle_memory) > 50:
                    # Remove oldest entry
                    oldest_key = min(self.muscle_memory.keys())
                    del self.muscle_memory[oldest_key]
        
        return dx, dy
    
    def _apply_natural_acceleration(self, dx, dy, distance):
        """Apply natural acceleration/deceleration curves"""
        if distance < 5:
            return dx, dy
        
        # Human acceleration profile (starts slow, peaks in middle, slows at end)
        # This simulates how humans naturally move their hand
        
        # Calculate movement phase (0.0 to 1.0)
        movement_phase = random.uniform(0.3, 0.7)  # Simulate where we are in the movement
        
        # Natural acceleration curve (bell curve-like)
        acceleration = math.sin(movement_phase * math.pi) * 1.2 + 0.8
        
        # Apply distance-based scaling
        if distance > 100:  # Long movements
            # Start slower, accelerate, then decelerate
            if movement_phase < 0.3:
                acceleration *= 0.7  # Slow start
            elif movement_phase > 0.7:
                acceleration *= 0.8  # Slow end
        elif distance < 20:  # Short movements
            # More consistent speed for precision
            acceleration = random.uniform(0.9, 1.1)
        
        return dx * acceleration, dy * acceleration
    
    def _apply_human_imperfections(self, dx, dy, distance):
        """Add realistic human imperfections"""
        # Humans are never perfectly accurate
        if distance > 5:
            # Add slight inaccuracy that scales with distance and fatigue
            inaccuracy = (distance * 0.002) + (self.fatigue_level * 0.01)
            
            # Random direction for inaccuracy
            error_angle = random.uniform(0, 2 * math.pi)
            error_magnitude = random.uniform(0, inaccuracy)
            
            error_x = math.cos(error_angle) * error_magnitude
            error_y = math.sin(error_angle) * error_magnitude
            
            dx += error_x
            dy += error_y
        
        # Add occasional "hiccups" (small random corrections)
        if random.random() < 0.05:  # 5% chance
            hiccup_x = random.uniform(-1, 1)
            hiccup_y = random.uniform(-1, 1)
            dx += hiccup_x
            dy += hiccup_y
        
        return dx, dy
    
    def _apply_breathing_heartbeat(self, dx, dy):
        """Simulate breathing and heartbeat micro-movements"""
        # Breathing (slow, large influence)
        self.breathing_phase += 0.02  # ~0.2 Hz (breathing rate)
        breathing_influence = math.sin(self.breathing_phase) * 0.2
        
        # Heartbeat (faster, smaller influence)  
        self.heartbeat_phase += 0.15  # ~1.5 Hz (heart rate)
        heartbeat_influence = math.sin(self.heartbeat_phase) * 0.1
        
        # Apply to movement
        dx += breathing_influence + heartbeat_influence
        dy += (breathing_influence + heartbeat_influence) * 0.7  # Less Y influence
        
        return dx, dy
    
    def get_human_stats(self):
        """Get current human state for debugging"""
        return {
            'fatigue': self.fatigue_level,
            'stress': self.stress_level,
            'focus': self.focus_level,
            'muscle_memory_patterns': len(self.muscle_memory),
            'avg_reaction_time': sum(self.reaction_times) / len(self.reaction_times) if self.reaction_times else 0
        }

# Global GAN instance
_human_gan = None

def get_human_gan():
    """Get the global human GAN instance"""
    global _human_gan
    if _human_gan is None:
        _human_gan = HumanMovementGAN()
    return _human_gan

def apply_enhanced_human_movement(dx, dy, target_distance=None, urgency=1.0):
    """
    Apply enhanced human-like movement with realistic behaviors
    
    Args:
        dx, dy: Target movement
        target_distance: Distance to target
        urgency: How urgent the movement is (0.0 = casual, 1.0 = critical)
    
    Returns:
        Enhanced dx, dy that mimics human movement patterns
    """
    gan = get_human_gan()
    return gan.apply_human_enhancements(dx, dy, target_distance, urgency)

def add_human_aiming_patterns(dx, dy, target_size=None, is_tracking=False):
    """
    Add human aiming patterns based on target characteristics
    
    Args:
        dx, dy: Movement to target
        target_size: Size of target (affects aiming style)
        is_tracking: Whether this is tracking an existing target
    """
    movement_distance = math.sqrt(dx*dx + dy*dy)
    
    # Human aiming behaviors
    if is_tracking:
        # Tracking movements are smoother and more predictive
        tracking_smoothness = 0.85
        dx *= tracking_smoothness
        dy *= tracking_smoothness
        
        # Add predictive movement (humans anticipate target movement)
        prediction_factor = random.uniform(0.02, 0.08)
        dx += random.uniform(-prediction_factor, prediction_factor) * movement_distance
        dy += random.uniform(-prediction_factor, prediction_factor) * movement_distance
    
    else:
        # Initial target acquisition is more aggressive
        if movement_distance > 100:
            # Long-range flicks have overshoot tendency
            overshoot_chance = 0.3
            if random.random() < overshoot_chance:
                overshoot = random.uniform(1.05, 1.15)
                dx *= overshoot
                dy *= overshoot
        
        # Add flick accuracy variation based on target size
        if target_size:
            # Smaller targets = more careful movement
            if target_size < 50:  # Small target
                precision_factor = random.uniform(0.95, 1.02)
            else:  # Large target
                precision_factor = random.uniform(0.92, 1.08)
            
            dx *= precision_factor
            dy *= precision_factor
    
    # Add crosshair placement preference (humans aim for different parts)
    if target_size and target_size > 30:
        # Aim for different parts of the target (head, center, etc.)
        aim_preference = random.choice(['head', 'center', 'body'])
        
        if aim_preference == 'head':
            dy -= target_size * 0.2  # Aim higher
        elif aim_preference == 'body':
            dy += target_size * 0.1   # Aim lower
        # 'center' keeps original position
    
    return dx, dy

def simulate_human_timing_delays():
    """
    Simulate realistic human timing delays
    Returns delay in seconds
    """
    gan = get_human_gan()
    
    # Base human reaction time varies
    base_delay = random.uniform(0.08, 0.18)  # 80-180ms
    
    # Factors affecting timing
    fatigue_delay = gan.fatigue_level * 0.05      # Fatigue slows reactions
    stress_delay = gan.stress_level * -0.02       # Stress can speed up reactions
    focus_bonus = (gan.focus_level - 0.5) * -0.03 # Focus improves timing
    
    total_delay = max(0.05, base_delay + fatigue_delay + stress_delay + focus_bonus)
    
    return total_delay

def add_human_click_patterns():
    """
    Add human-like clicking patterns
    Returns click timing and pattern info
    """
    # Human click duration varies
    click_duration = random.uniform(0.05, 0.12)  # 50-120ms
    
    # Humans sometimes double-click accidentally under stress
    gan = get_human_gan()
    if gan.stress_level > 0.7 and random.random() < 0.05:  # 5% chance when stressed
        return {
            'duration': click_duration,
            'double_click': True,
            'double_click_delay': random.uniform(0.08, 0.15)
        }
    
    return {
        'duration': click_duration,
        'double_click': False
    }

def get_human_performance_stats():
    """Get human performance statistics for analysis"""
    gan = get_human_gan()
    return gan.get_human_stats()
