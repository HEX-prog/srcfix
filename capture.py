import time
import numpy as np
import mss
import cv2
import dxcam
from config import config

# NDI imports
from cyndilib.wrapper.ndi_recv import RecvColorFormat, RecvBandwidth
from cyndilib.finder import Finder
from cyndilib.receiver import Receiver
from cyndilib.video_frame import VideoFrameSync
from cyndilib.audio_frame import AudioFrameSync

# UDP imports
from OBS_UDP import OBS_UDP_Receiver


def get_region():
    """Center capture region based on current capture source dimensions.

    Uses FOV X/Y sizes and centers within the active capture backend size if known,
    otherwise falls back to screen dimensions. This improves centering consistency
    across MSS, CaptureCard, DXGI, UDP, and NDI.
    """
    fov_x = int(getattr(config, "fov_x_size", getattr(config, "region_size", 200)))
    fov_y = int(getattr(config, "fov_y_size", getattr(config, "region_size", 200)))

    mode = str(getattr(config, "capturer_mode", "mss")).lower()

    if mode in ("capturecard", "capture_card"):
        base_w = int(getattr(config, "capture_width", getattr(config, "screen_width", 1920)))
        base_h = int(getattr(config, "capture_height", getattr(config, "screen_height", 1080)))
    elif mode == "ndi":
        # NDI can change size dynamically; use last known values when available
        base_w = int(getattr(config, "ndi_width", getattr(config, "screen_width", 1920)))
        base_h = int(getattr(config, "ndi_height", getattr(config, "screen_height", 1080)))
    elif mode == "udp":
        base_w = int(getattr(config, "udp_width", getattr(config, "screen_width", 1920)))
        base_h = int(getattr(config, "udp_height", getattr(config, "screen_height", 1080)))
    elif mode == "dxgi":
        base_w = int(getattr(config, "screen_width", 1920))
        base_h = int(getattr(config, "screen_height", 1080))
    else:  # mss and any unknown
        base_w = int(getattr(config, "screen_width", 1920))
        base_h = int(getattr(config, "screen_height", 1080))

    # Clamp FOV to base dimensions
    fov_x = max(1, min(fov_x, base_w))
    fov_y = max(1, min(fov_y, base_h))

    left = max(0, (base_w - fov_x) // 2)
    top = max(0, (base_h - fov_y) // 2)
    right = min(base_w, left + fov_x)
    bottom = min(base_h, top + fov_y)
    return left, top, right, bottom


class MSSCamera:
    def __init__(self, region):
        # Original MSS screen capture implementation
        self.region = region
        self.mss = mss.mss()
        
    def get_latest_frame(self):
        try:
            # Capture screen region using MSS
            screenshot = self.mss.grab(self.region)
            frame = np.array(screenshot)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            return frame
        except Exception as e:
            print(f"[MSS] Capture error: {e}")
            return None
    
    def stop(self):
        try:
            self.mss.close()
        except Exception:
            pass

class CaptureCardCamera:
    def __init__(self, region=None):
        # Get capture card parameters from config
        self.frame_width = int(getattr(config, "capture_width", 1920))
        self.frame_height = int(getattr(config, "capture_height", 1080))
        self.target_fps = float(getattr(config, "capture_fps", 240))
        self.device_index = int(getattr(config, "capture_device_index", 0))
        self.fourcc_pref = list(getattr(config, "capture_fourcc_preference", ["NV12", "YUY2", "MJPG"]))
        self.region = region
        self.cap = None
        self.running = True
        
        # Try different backends in order of preference
        preferred_backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
        for backend in preferred_backends:
            self.cap = cv2.VideoCapture(self.device_index, backend)
            if self.cap.isOpened():
                # Set resolution and frame rate
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(self.frame_width))
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(self.frame_height))
                self.cap.set(cv2.CAP_PROP_FPS, float(self.target_fps))
                
                # Try to set preferred fourcc format
                for fourcc in self.fourcc_pref:
                    try:
                        fourcc_code = cv2.VideoWriter_fourcc(*fourcc)
                        self.cap.set(cv2.CAP_PROP_FOURCC, fourcc_code)
                        print(f"[CaptureCard] Set fourcc to {fourcc}")
                        break
                    except Exception as e:
                        print(f"[CaptureCard] Failed to set fourcc {fourcc}: {e}")
                        continue
                
                print(f"[CaptureCard] Successfully opened camera {self.device_index} with backend {backend}")
                print(f"[CaptureCard] Resolution: {self.frame_width}x{self.frame_height}, FPS: {self.target_fps}")
                break
            else:
                self.cap.release()
                self.cap = None
        
        if self.cap is None or not self.cap.isOpened():
            raise RuntimeError(f"Failed to open capture card at device index {self.device_index}")

    def get_latest_frame(self):
        if not self.cap or not self.cap.isOpened():
            return None
        
        ret, frame = self.cap.read()
        if not ret or frame is None:
            return None
        
        # Apply region cropping if specified
        if self.region:
            x1, y1, x2, y2 = self.region
            frame = frame[y1:y2, x1:x2]
        
        return frame

    def stop(self):
        self.running = False
        if self.cap:
            self.cap.release()
            self.cap = None


class NDICamera:
    def __init__(self):
        self.finder = Finder()
        self.finder.set_change_callback(self.on_finder_change)
        self.finder.open()

        self.receiver = Receiver(
            color_format=RecvColorFormat.RGBX_RGBA,
            bandwidth=RecvBandwidth.highest,
        )
        self.video_frame = VideoFrameSync()
        self.audio_frame = AudioFrameSync()
        self.receiver.frame_sync.set_video_frame(self.video_frame)
        self.receiver.frame_sync.set_audio_frame(self.audio_frame)

        # --------------------------------------------------------------

        self.available_sources = []     
        self.desired_source_name = None
        self._pending_index = None
        self._pending_connect = False
        self._last_connect_try = 0.0
        self._retry_interval = 0.5
        # ---------------------------------------------------------------

        self.connected = False
        self._source_name = None
        self._size_checked = False
        self._allowed_sizes = {128,160,192,224,256,288,320,352,384,416,448,480,512,544,576,608,640}

        # prime the initial list so select_source(0) works immediately
        try:
            self.available_sources = self.finder.get_source_names() or []
        except Exception:
            self.available_sources = []

    def select_source(self, name_or_index):
        # guard against early calls
        if self.available_sources is None:
            self.available_sources = []

        self._pending_connect = True
        if isinstance(name_or_index, int):
            self._pending_index = name_or_index
            if 0 <= name_or_index < len(self.available_sources):
                self.desired_source_name = self.available_sources[name_or_index]
            else:
                print(f"[NDI] Will connect to index {name_or_index} when sources are ready.")
                return
        else:
            self.desired_source_name = str(name_or_index)

        if self.desired_source_name in self.available_sources:
            self._try_connect_throttled()

    def on_finder_change(self):
        self.available_sources = self.finder.get_source_names() or []
        print("[NDI] Found sources:", self.available_sources)

        if self._pending_index is not None and 0 <= self._pending_index < len(self.available_sources):
            self.desired_source_name = self.available_sources[self._pending_index]

        if self._pending_connect and not self.connected and self.desired_source_name in self.available_sources:
            self._try_connect_throttled()

    def _try_connect_throttled(self):
        now = time.time()
        if now - self._last_connect_try < self._retry_interval:
            return
        self._last_connect_try = now
        if self.desired_source_name:
            self.connect_to_source(self.desired_source_name)

    def connect_to_source(self, source_name):
        source = self.finder.get_source(source_name)
        if not source:
            print(f"[NDI] Source '{source_name}' not available (get_source returned None).")
            return
        self.receiver.set_source(source)
        self._source_name = source.name
        print(f"[NDI] set_source -> {self._source_name}")
        for _ in range(200):
            if self.receiver.is_connected():
                self.connected = True
                self._pending_connect = False
                print("[NDI] Receiver reports CONNECTED.")
                break
            time.sleep(0.01)
        else:
            print("[NDI] Timeout: receiver never reported connected.")
            self.connected = False
        self._size_checked = False

    def maintain_connection(self):
        if self.connected and not self.receiver.is_connected():
            self.connected = False
            self._pending_connect = True
        # try reconnect if source is present
        if self._pending_connect and self.desired_source_name in self.available_sources:
            self._try_connect_throttled()

    def _log_size_verdict_once(self, w, h):
        if self._size_checked:
            return
        self._size_checked = True

        name = self._source_name or "NDI Source"
        if w == h and w in self._allowed_sizes:
            print(f"[NDI] Source {name}: {w}x{h} ✔ allowed (no resize).")
            return

        target = min(w, h)
        allowed = sorted(self._allowed_sizes)
        down = max((s for s in allowed if s <= target), default=None)
        up   = min((s for s in allowed if s >= target), default=None)
        if down is None and up is None:
            suggest = 640
        elif down is None:
            suggest = up
        elif up is None:
            suggest = down
        else:
            suggest = down if (target - down) <= (up - target) else up

        if w != h:
            print(
                f"[NDI][FOV WARNING] Source {name}: input {w}x{h} is not square. "
                f"Nearest allowed square: {suggest}x{suggest}. "
                f"Consider a center crop to {suggest}x{suggest} for stable colors & model sizing."
            )
        else:
            print(
                f"[NDI][FOV WARNING] Source {name}: {w}x{h} not in allowed set. "
                f"Nearest allowed: {suggest}x{suggest}. "
                f"Consider a center ROI of {suggest}x{suggest} to avoid interpolation artifacts."
            )

    def get_latest_frame(self):
        if not self.receiver.is_connected():
            time.sleep(0.002)
            return None

        self.receiver.frame_sync.capture_video()
        if min(self.video_frame.xres, self.video_frame.yres) == 0:
            time.sleep(0.002)
            return None
        config.ndi_width, config.ndi_height = self.video_frame.xres, self.video_frame.yres

        # one-time verdict/log about resolution
        self._log_size_verdict_once(config.ndi_width, config.ndi_height)

        # Copy frame to own memory to avoid "cannot write with view active"
        frame = np.frombuffer(self.video_frame, dtype=np.uint8).copy()
        frame = frame.reshape((self.video_frame.yres, self.video_frame.xres, 4))
        frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)

        return frame

    def list_sources(self, refresh=True):
        """
        Return a list of NDI source names. If refresh=True, query the Finder.
        Never raises; always returns a list.
        """
        if refresh:
            try:
                self.available_sources = self.finder.get_source_names() or []
            except Exception:
                # keep whatever we had, but make sure it's a list
                self.available_sources = self.available_sources or []
        return list(self.available_sources)

    def switch_source(self, name_or_index):
        """Convenience wrapper to switch sources."""
        self.select_source(name_or_index)
        self._try_connect_throttled()

    def stop(self):
        # Detach source to help sender release quickly
        try:
            if self.receiver:
                self.receiver.set_source(None)
        except Exception:
            pass

        try:
            if self.video_sync:
                self.video_sync.close()
        except Exception:
            pass

        try:
            if self.audio_sync:
                self.audio_sync.close()
        except Exception:
            pass

        try:
            if self.receiver:
                self.receiver.close()
        except Exception:
            pass

        try:
            if self.finder:
                self.finder.stop()
                self.finder.close()
        except Exception:
            pass


class DXGICamera:
    def __init__(self, region=None, target_fps=None):
        self.region = region
        self.camera = dxcam.create(output_idx=0, output_color="BGRA")  # stable default
        # Use config.capture_fps if available, else fallback
        fps = int(getattr(config, "capture_fps", 240) if target_fps is None else target_fps)
        self.camera.start(target_fps=fps)  # <-- start the capture thread here
        self.running = True

    def get_latest_frame(self):
        frame = self.camera.get_latest_frame()
        if frame is None:
            return None
        # Convert BGRA -> BGR once
        if frame.shape[2] == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

        if self.region:
            x1, y1, x2, y2 = self.region
            frame = frame[y1:y2, x1:x2]
        return frame

    def stop(self):
        self.running = False
        try:
            self.camera.stop()
        except Exception:
            pass


def get_camera():
    """Factory function to return the right camera based on config."""
    if config.capturer_mode.lower() == "mss":
        region = get_region()
        cam = MSSCamera(region)
        return cam, region
    elif config.capturer_mode.lower() == "ndi":
        cam = NDICamera()
        return cam, None
    elif config.capturer_mode.lower() == "dxgi":
        region = get_region()
        cam = DXGICamera(region)
        return cam, region
    elif config.capturer_mode.lower() in ["capturecard", "capture_card"]:
        region = get_region()
        cam = CaptureCardCamera(region)
        return cam, region
    elif config.capturer_mode.lower() == "udp":
        region = get_region()
        cam = UDPCamera(region)
        return cam, region
    else:
        # Default to MSS if unknown mode
        print(f"[WARN] Unknown capturer_mode: {config.capturer_mode}, defaulting to MSS")
        region = get_region()
        cam = MSSCamera(region)
        return cam, region


class UDPCamera:
    def __init__(self, region=None):
        """
        Initialize UDP camera for receiving MJPEG stream from OBS Studio
        
        Args:
            region: Optional region tuple (left, top, right, bottom) for cropping
                   Note: For UDP mode, we typically get the full frame like NDI
        """
        self.region = region
        self.udp_receiver = None
        self.running = True
        self.last_valid_frame = None
        self.frame_retry_count = 0
        self.max_retries = 5
        
        # Get UDP parameters from config
        self.udp_ip = getattr(config, "udp_ip", "192.168.0.01")
        self.udp_port = int(getattr(config, "udp_port", 1234))
        
        # Initialize UDP receiver
        try:
            self.udp_receiver = OBS_UDP_Receiver(
                ip=self.udp_ip,
                port=self.udp_port,
                target_fps=60  # Default FPS, can be adjusted if needed
            )
            
            # Connect to UDP stream
            if not self.udp_receiver.connect():
                raise RuntimeError(f"Failed to connect to UDP stream at {self.udp_ip}:{self.udp_port}")
            
            print(f"[UDP] Successfully connected to {self.udp_ip}:{self.udp_port}")
            
        except Exception as e:
            print(f"[UDP] Error initializing UDP camera: {e}")
            raise RuntimeError(f"Failed to initialize UDP camera: {e}")

    def get_latest_frame(self):
        """
        Get the latest frame from UDP stream with robust error handling
        
        Returns:
            numpy.ndarray or None: Latest frame or None if no frame available
        """
        if not self.udp_receiver or not self.udp_receiver.is_connected:
            return self.last_valid_frame  # Return last valid frame if disconnected
        
        try:
            # Get current frame from UDP receiver
            frame = self.udp_receiver.get_current_frame()
            
            if frame is None:
                # If no new frame, return last valid frame to avoid empty frames
                return self.last_valid_frame
            
            # Validate frame dimensions and data
            if not self._validate_frame(frame):
                self.frame_retry_count += 1
                if self.frame_retry_count >= self.max_retries:
                    print(f"[UDP] Too many invalid frames, using last valid frame")
                    self.frame_retry_count = 0
                return self.last_valid_frame
            
            # Reset retry count on successful frame
            self.frame_retry_count = 0
            
            # Apply region cropping if specified
            if self.region:
                x1, y1, x2, y2 = self.region
                # Ensure region is within frame bounds
                height, width = frame.shape[:2]
                x1 = max(0, min(x1, width))
                y1 = max(0, min(y1, height))
                x2 = max(x1, min(x2, width))
                y2 = max(y1, min(y2, height))
                
                if x2 > x1 and y2 > y1:
                    frame = frame[y1:y2, x1:x2]
                else:
                    print(f"[UDP] Invalid region bounds: ({x1},{y1},{x2},{y2})")
                    return self.last_valid_frame
            
            # Store as last valid frame
            self.last_valid_frame = frame.copy()
            
            # Update config with frame dimensions for FOV calculations
            config.udp_width, config.udp_height = frame.shape[1], frame.shape[0]
            
            return frame
            
        except Exception as e:
            print(f"[UDP] Error getting frame: {e}")
            return self.last_valid_frame
    
    def _validate_frame(self, frame):
        """
        Validate frame data and dimensions
        
        Args:
            frame: Frame to validate
            
        Returns:
            bool: True if frame is valid, False otherwise
        """
        if frame is None:
            return False
        
        if frame.size == 0:
            return False
        
        # Check dimensions
        if len(frame.shape) < 2:
            return False
        
        height, width = frame.shape[:2]
        if height < 10 or width < 10:
            return False
        
        if height > 4000 or width > 4000:  # Reasonable upper limit
            return False
        
        return True
    
    def list_sources(self):
        """List available UDP sources (returns connection info)"""
        return [f"UDP Stream ({self.udp_ip}:{self.udp_port})"]
    
    def stop(self):
        """Stop UDP camera and clean up resources"""
        self.running = False
        if self.udp_receiver:
            self.udp_receiver.disconnect()
            self.udp_receiver = None
        print("[UDP] Camera stopped")
    
    def get_performance_stats(self):
        """Get UDP performance statistics"""
        if self.udp_receiver:
            return self.udp_receiver.get_performance_stats()
        return {
            'current_fps': 0,
            'processing_fps': 0,
            'target_fps': 60,
            'is_connected': False,
            'is_receiving': False
        }
