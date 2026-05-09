import cv2
import socket
import threading
import time
import numpy as np
from typing import Optional, Callable, Tuple
import logging

logger = logging.getLogger(__name__)


class OBS_UDP_Receiver:
    """
    OBS UDP receiver for MJPEG stream from OBS Studio
    Supports receiving Motion JPEG stream over UDP protocol
    """
    
    def __init__(self, ip: str = "192.168.0.01", port: int = 1234, target_fps: int = 60):
        """
        Initialize OBS UDP receiver
        
        Args:
            ip: IP address to receive UDP stream from
            port: Port number to receive UDP stream on
            target_fps: Target FPS for processing
        """
        self.ip = ip
        self.port = port
        self.target_fps = target_fps
        self.frame_interval = 1.0 / target_fps
        
        # Connection state
        self.socket = None
        self.is_connected = False
        self.is_receiving = False
        
        # Threading
        self.receive_thread = None
        self.stop_event = threading.Event()
        
        # Frame processing
        self.current_frame = None
        self.frame_lock = threading.Lock()
        self.frame_callback = None
        
        # Performance monitoring
        self.fps_counter = 0
        self.last_fps_time = time.time()
        self.current_fps = 0.0
        self.processing_fps = 0.0
        self.last_processing_time = time.time()
        self.processing_counter = 0
        self.receive_delay = 0.0
        self.processing_delay = 0.0
        
        # MJPEG buffer
        self.mjpeg_buffer = b""
        self.mjpeg_start_marker = b'\xff\xd8'  # JPEG start marker
        self.mjpeg_end_marker = b'\xff\xd9'    # JPEG end marker
        
        logger.info(f"OBS_UDP_Receiver initialized: {ip}:{port}, target_fps={target_fps}")
    
    def set_frame_callback(self, callback: Callable[[np.ndarray], None]):
        """
        Set callback function for frame processing
        
        Args:
            callback: Function to call with each received frame
        """
        self.frame_callback = callback
    
    def connect(self) -> bool:
        """
        Connect to UDP stream
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            if self.is_connected:
                self.disconnect()
            
            # Create UDP socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.settimeout(5.0)  # 5 second timeout
            
            # Bind to receive UDP packets
            self.socket.bind((self.ip, self.port))
            
            self.is_connected = True
            self.stop_event.clear()
            
            # Start receiving thread
            self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self.receive_thread.start()
            
            logger.info(f"Connected to UDP stream at {self.ip}:{self.port}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to UDP stream: {e}")
            self.is_connected = False
            return False
    
    def disconnect(self):
        """Disconnect from UDP stream"""
        try:
            self.is_connected = False
            self.is_receiving = False
            self.stop_event.set()
            
            if self.receive_thread and self.receive_thread.is_alive():
                self.receive_thread.join(timeout=2.0)
            
            if self.socket:
                self.socket.close()
                self.socket = None
            
            logger.info("Disconnected from UDP stream")
            
        except Exception as e:
            logger.error(f"Error during disconnect: {e}")
    
    def _receive_loop(self):
        """Main receiving loop for UDP packets"""
        self.is_receiving = True
        logger.info("Started UDP receive loop")
        
        while not self.stop_event.is_set() and self.is_connected:
            try:
                # Receive UDP packet
                data, addr = self.socket.recvfrom(65536)  # Max UDP packet size
                receive_time = time.time()
                
                # Process MJPEG data
                self._process_mjpeg_data(data, receive_time)
                
            except socket.timeout:
                continue
            except Exception as e:
                if self.is_connected:
                    logger.error(f"Error in receive loop: {e}")
                break
        
        self.is_receiving = False
        logger.info("UDP receive loop ended")
    
    def _process_mjpeg_data(self, data: bytes, receive_time: float):
        """
        Process incoming MJPEG data and extract frames with improved error handling
        
        Args:
            data: Raw UDP packet data
            receive_time: Timestamp when data was received
        """
        try:
            # Add data to buffer
            self.mjpeg_buffer += data
            
            # Prevent buffer from growing too large
            if len(self.mjpeg_buffer) > 2 * 1024 * 1024:  # 2MB limit (increased for high-res streams)
                logger.warning("MJPEG buffer too large, clearing")
                self.mjpeg_buffer = b""
                return
            
            # Look for complete JPEG frames
            frames_processed = 0
            max_frames_per_packet = 5  # Prevent infinite loops
            
            while frames_processed < max_frames_per_packet:
                start_pos = self.mjpeg_buffer.find(self.mjpeg_start_marker)
                if start_pos == -1:
                    # No start marker found, keep only last part of buffer
                    if len(self.mjpeg_buffer) > 2048:  # Keep more buffer for high-res streams
                        self.mjpeg_buffer = self.mjpeg_buffer[-1024:]
                    break
                
                # Remove data before start marker
                self.mjpeg_buffer = self.mjpeg_buffer[start_pos:]
                
                # Find end marker
                end_pos = self.mjpeg_buffer.find(self.mjpeg_end_marker, 2)
                if end_pos == -1:
                    # No complete frame yet, wait for more data
                    break
                
                # Extract complete JPEG frame
                jpeg_data = self.mjpeg_buffer[:end_pos + 2]
                self.mjpeg_buffer = self.mjpeg_buffer[end_pos + 2:]
                
                # Validate JPEG data size and content
                if len(jpeg_data) < 100:  # Skip very small frames
                    continue
                
                # Additional validation: check for reasonable JPEG size
                if len(jpeg_data) > 10 * 1024 * 1024:  # 10MB limit per frame
                    logger.warning(f"JPEG frame too large: {len(jpeg_data)} bytes, skipping")
                    continue
                
                # Decode JPEG to OpenCV frame
                frame = self._decode_jpeg_frame(jpeg_data, receive_time)
                if frame is not None:
                    self._update_frame(frame, receive_time)
                    frames_processed += 1
                else:
                    # If decode failed, continue to next frame
                    continue
                
        except Exception as e:
            logger.error(f"Error processing MJPEG data: {e}")
            # Clear buffer on error to prevent corruption
            self.mjpeg_buffer = b""
    
    def _decode_jpeg_frame(self, jpeg_data: bytes, receive_time: float) -> Optional[np.ndarray]:
        """
        Decode JPEG data to OpenCV frame with robust error handling
        
        Args:
            jpeg_data: Raw JPEG data
            receive_time: Timestamp when data was received
            
        Returns:
            Decoded frame as numpy array or None if failed
        """
        try:
            # Validate JPEG data length
            if len(jpeg_data) < 100:  # Minimum reasonable JPEG size
                logger.warning(f"JPEG data too small: {len(jpeg_data)} bytes")
                return None
            
            # Check for valid JPEG markers
            if not (jpeg_data.startswith(b'\xff\xd8') and jpeg_data.endswith(b'\xff\xd9')):
                logger.warning("Invalid JPEG markers")
                return None
            
            # Convert bytes to numpy array
            nparr = np.frombuffer(jpeg_data, np.uint8)
            
            # Decode JPEG with error handling and multiple fallback strategies
            frame = None
            
            # Try standard decoding first
            try:
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            except cv2.error as e:
                logger.warning(f"Standard JPEG decode failed: {e}")
                
                # Try with different flags as fallback
                try:
                    frame = cv2.imdecode(nparr, cv2.IMREAD_ANYCOLOR)
                except cv2.error as e2:
                    logger.warning(f"Fallback JPEG decode failed: {e2}")
                    
                    # Try with ignore orientation flag
                    try:
                        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
                    except cv2.error as e3:
                        logger.error(f"All JPEG decode attempts failed: {e3}")
                        return None
            
            if frame is not None and frame.size > 0:
                # Validate frame dimensions
                if len(frame.shape) >= 2 and frame.shape[0] > 0 and frame.shape[1] > 0:
                    # Additional validation for reasonable dimensions
                    height, width = frame.shape[:2]
                    if height < 10 or width < 10 or height > 10000 or width > 10000:
                        logger.warning(f"Frame dimensions out of reasonable range: {width}x{height}")
                        return None
                    
                    # Check for corrupted frames (all zeros or all same value)
                    if np.all(frame == 0) or np.all(frame == frame.flat[0]):
                        logger.warning("Frame appears to be corrupted (all zeros or same value)")
                        return None
                    
                    # Calculate receive delay
                    self.receive_delay = (time.time() - receive_time) * 1000  # Convert to ms
                    return frame
                else:
                    logger.warning(f"Invalid frame dimensions: {frame.shape}")
                    return None
            else:
                logger.warning("Failed to decode JPEG frame - returned None or empty")
                return None
            
        except cv2.error as e:
            logger.error(f"OpenCV error decoding JPEG frame: {e}")
        except Exception as e:
            logger.error(f"Unexpected error decoding JPEG frame: {e}")
        
        return None
    
    def _update_frame(self, frame: np.ndarray, receive_time: float):
        """
        Update current frame and trigger processing
        
        Args:
            frame: New frame
            receive_time: Timestamp when frame was received
        """
        try:
            with self.frame_lock:
                self.current_frame = frame.copy()
            
            # Update FPS counter
            self._update_fps_counters()
            
            # Trigger frame callback if set
            if self.frame_callback:
                processing_start = time.time()
                self.frame_callback(frame)
                processing_end = time.time()
                
                # Calculate processing delay
                self.processing_delay = (processing_end - processing_start) * 1000  # Convert to ms
                
                # Update processing FPS
                self.processing_counter += 1
                if processing_end - self.last_processing_time >= 1.0:
                    self.processing_fps = self.processing_counter / (processing_end - self.last_processing_time)
                    self.processing_counter = 0
                    self.last_processing_time = processing_end
            
        except Exception as e:
            logger.error(f"Error updating frame: {e}")
    
    def _update_fps_counters(self):
        """Update FPS counters for monitoring"""
        current_time = time.time()
        self.fps_counter += 1
        
        if current_time - self.last_fps_time >= 1.0:
            self.current_fps = self.fps_counter / (current_time - self.last_fps_time)
            self.fps_counter = 0
            self.last_fps_time = current_time
    
    def get_current_frame(self) -> Optional[np.ndarray]:
        """
        Get current frame
        
        Returns:
            Current frame or None if no frame available
        """
        with self.frame_lock:
            return self.current_frame.copy() if self.current_frame is not None else None
    
    def get_performance_stats(self) -> dict:
        """
        Get performance statistics
        
        Returns:
            Dictionary with performance metrics
        """
        return {
            'current_fps': self.current_fps,
            'processing_fps': self.processing_fps,
            'target_fps': self.target_fps,
            'receive_delay_ms': self.receive_delay,
            'processing_delay_ms': self.processing_delay,
            'is_connected': self.is_connected,
            'is_receiving': self.is_receiving
        }
    
    def set_target_fps(self, fps: int):
        """
        Set target FPS
        
        Args:
            fps: Target FPS value
        """
        self.target_fps = max(1, min(240, fps))  # Clamp between 1-240
        self.frame_interval = 1.0 / self.target_fps
        logger.info(f"Target FPS set to {self.target_fps}")
    
    def update_connection_params(self, ip: str, port: int):
        """
        Update connection parameters
        
        Args:
            ip: New IP address
            port: New port number
        """
        self.ip = ip
        self.port = port
        logger.info(f"Connection parameters updated: {ip}:{port}")


class OBS_UDP_Manager:
    """
    Manager class for OBS UDP connections
    Provides high-level interface for UDP stream management
    """
    
    def __init__(self):
        self.receiver = None
        self.is_connected = False
        
    def create_receiver(self, ip: str, port: int, target_fps: int = 60) -> OBS_UDP_Receiver:
        """
        Create new UDP receiver
        
        Args:
            ip: IP address
            port: Port number
            target_fps: Target FPS
            
        Returns:
            OBS_UDP_Receiver instance
        """
        self.receiver = OBS_UDP_Receiver(ip, port, target_fps)
        return self.receiver
    
    def connect(self, ip: str, port: int, target_fps: int = 60) -> bool:
        """
        Connect to UDP stream
        
        Args:
            ip: IP address
            port: Port number
            target_fps: Target FPS
            
        Returns:
            True if connection successful
        """
        if self.receiver:
            self.receiver.disconnect()
        
        self.receiver = OBS_UDP_Receiver(ip, port, target_fps)
        success = self.receiver.connect()
        self.is_connected = success
        return success
    
    def disconnect(self):
        """Disconnect from UDP stream"""
        if self.receiver:
            self.receiver.disconnect()
            self.receiver = None
        self.is_connected = False
    
    def get_receiver(self) -> Optional[OBS_UDP_Receiver]:
        """Get current receiver instance"""
        return self.receiver
    
    def is_stream_active(self) -> bool:
        """Check if stream is active"""
        return self.is_connected and self.receiver and self.receiver.is_receiving
