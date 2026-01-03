"""
Camera module for MJPEG stream capture.

Captures frames from the MasterPi camera feed running on port 8080.
"""

import cv2
import urllib.request
import numpy as np
import time
import os
from typing import Tuple, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Camera:
    """MJPEG stream camera capture."""
    
    def __init__(self, ip_address: str = None, port: int = None, timeout: int = 10):
        """
        Initialize camera.
        
        Args:
            ip_address: Robot IP address (default: from .env ROBOT_IP)
            port: Camera stream port (default: from .env CAMERA_PORT)
            timeout: Connection timeout in seconds
        """
        if ip_address is None:
            ip_address = os.getenv("ROBOT_IP")
            if ip_address is None:
                raise ValueError("ROBOT_IP must be set in .env file or provided as argument")
        if port is None:
            port = int(os.getenv("CAMERA_PORT", "8080"))
        
        self.ip_address = ip_address
        self.port = port
        self.timeout = timeout
        self.camera_url = f"http://{ip_address}:{port}/"
        self.stream: Optional[urllib.request.URLopener] = None
        self.latest_frame: Optional[np.ndarray] = None
        self.latest_timestamp: float = 0.0
    
    def _open_stream(self) -> bool:
        """Open MJPEG stream connection."""
        try:
            self.stream = urllib.request.urlopen(self.camera_url, timeout=self.timeout)
            return True
        except Exception as e:
            print(f"Failed to open camera stream: {e}")
            return False
    
    def get_frame(self) -> Tuple[bool, Optional[np.ndarray], float]:
        """
        Capture a single frame from the MJPEG stream.
        
        Returns:
            (success: bool, frame: np.ndarray or None, timestamp: float)
        """
        timestamp = time.time()
        
        try:
            # Open stream if not already open
            if self.stream is None:
                if not self._open_stream():
                    return (False, None, timestamp)
            
            bytes_data = bytes()
            max_iterations = 100  # Prevent infinite loop
            iteration = 0
            
            # Read stream until we find a complete JPEG frame
            while iteration < max_iterations:
                chunk = self.stream.read(1024)
                if not chunk:
                    # Stream ended, try to reopen
                    if not self._open_stream():
                        return (False, None, timestamp)
                    continue
                
                bytes_data += chunk
                
                # Look for JPEG start marker (0xFF 0xD8)
                start_marker = bytes_data.find(b'\xff\xd8')
                # Look for JPEG end marker (0xFF 0xD9)
                end_marker = bytes_data.find(b'\xff\xd9')
                
                if start_marker != -1 and end_marker != -1 and end_marker > start_marker:
                    # Extract the complete JPEG frame
                    jpg_data = bytes_data[start_marker:end_marker + 2]
                    
                    # Decode the JPEG image
                    image_array = np.frombuffer(jpg_data, dtype=np.uint8)
                    image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
                    
                    if image is not None:
                        self.latest_frame = image
                        self.latest_timestamp = timestamp
                        return (True, image, timestamp)
                    else:
                        # Failed to decode, continue reading
                        bytes_data = bytes_data[end_marker + 2:]
                        continue
                
                # If we have too much data without finding markers, reset
                if len(bytes_data) > 100000:  # ~100KB
                    bytes_data = bytes_data[-50000:]  # Keep last 50KB
                
                iteration += 1
            
            return (False, None, timestamp)
        
        except urllib.error.URLError as e:
            print(f"Camera stream error: {e}")
            self.stream = None
            return (False, None, timestamp)
        except Exception as e:
            print(f"Unexpected camera error: {e}")
            self.stream = None
            return (False, None, timestamp)
    
    def get_latest_frame(self) -> Tuple[bool, Optional[np.ndarray], float]:
        """
        Get the latest cached frame.
        
        Returns:
            (success: bool, frame: np.ndarray or None, timestamp: float)
        """
        if self.latest_frame is not None:
            return (True, self.latest_frame.copy(), self.latest_timestamp)
        else:
            return self.get_frame()
    
    def close(self):
        """Close camera stream."""
        if self.stream is not None:
            try:
                self.stream.close()
            except:
                pass
            self.stream = None

