"""
Safety Monitor Module
Prevents PC freezing by monitoring application performance and adding safety measures
"""

import threading
import time
import psutil
import os

class SafetyMonitor:
    def __init__(self):
        self.running = False
        self.monitor_thread = None
        self.last_frame_time = time.time()
        self.cpu_usage_history = []
        self.memory_usage_history = []
        
        # Safety thresholds
        self.max_cpu_usage = 90  # Maximum CPU usage before intervention
        self.max_memory_mb = 2000  # Maximum memory usage in MB
        self.max_hang_time = 10  # Maximum seconds without frame processing
        
    def start_monitoring(self):
        """Start safety monitoring in background thread"""
        if self.running:
            return
        
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        print("[SAFETY] Safety monitor started")
    
    def stop_monitoring(self):
        """Stop safety monitoring"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1.0)
        print("[SAFETY] Safety monitor stopped")
    
    def update_frame_time(self):
        """Update last frame processing time"""
        self.last_frame_time = time.time()
    
    def _monitor_loop(self):
        """Main monitoring loop"""
        while self.running:
            try:
                self._check_system_resources()
                self._check_application_hang()
                time.sleep(1.0)  # Check every second
            except Exception as e:
                print(f"[SAFETY] Monitor error: {e}")
                time.sleep(1.0)
    
    def _check_system_resources(self):
        """Check CPU and memory usage"""
        try:
            # Get current process
            process = psutil.Process(os.getpid())
            
            # Check CPU usage
            cpu_percent = process.cpu_percent()
            self.cpu_usage_history.append(cpu_percent)
            if len(self.cpu_usage_history) > 10:
                self.cpu_usage_history.pop(0)
            
            # Check memory usage
            memory_mb = process.memory_info().rss / 1024 / 1024
            self.memory_usage_history.append(memory_mb)
            if len(self.memory_usage_history) > 10:
                self.memory_usage_history.pop(0)
            
            # Check if resources are too high
            if len(self.cpu_usage_history) >= 5:
                avg_cpu = sum(self.cpu_usage_history[-5:]) / 5
                if avg_cpu > self.max_cpu_usage:
                    print(f"[SAFETY] High CPU usage detected: {avg_cpu:.1f}%")
                    time.sleep(0.1)  # Force a break
            
            if memory_mb > self.max_memory_mb:
                print(f"[SAFETY] High memory usage: {memory_mb:.1f}MB")
                # Force garbage collection
                import gc
                gc.collect()
                
        except Exception as e:
            print(f"[SAFETY] Resource check failed: {e}")
    
    def _check_application_hang(self):
        """Check if application is hanging"""
        try:
            current_time = time.time()
            time_since_frame = current_time - self.last_frame_time
            
            if time_since_frame > self.max_hang_time:
                print(f"[SAFETY] Application hang detected: {time_since_frame:.1f}s since last frame")
                print("[SAFETY] Consider restarting the application")
                
        except Exception as e:
            print(f"[SAFETY] Hang check failed: {e}")

# Global safety monitor instance
_safety_monitor = None

def get_safety_monitor():
    """Get the global safety monitor instance"""
    global _safety_monitor
    if _safety_monitor is None:
        _safety_monitor = SafetyMonitor()
    return _safety_monitor

def start_safety_monitoring():
    """Start safety monitoring"""
    monitor = get_safety_monitor()
    monitor.start_monitoring()

def stop_safety_monitoring():
    """Stop safety monitoring"""
    monitor = get_safety_monitor()
    monitor.stop_monitoring()

def update_frame_time():
    """Update frame processing time for hang detection"""
    monitor = get_safety_monitor()
    monitor.update_frame_time()
