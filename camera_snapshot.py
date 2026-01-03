#!/usr/bin/env python3
"""
Camera Snapshot Script for MasterPi Robot
Captures a snapshot from the MJPEG camera feed running on port 8080.
"""

import cv2
import urllib.request
import numpy as np
import sys
import argparse
from pathlib import Path


def capture_snapshot(ip_address="192.168.86.60", port=8080, output_file="snapshot.jpg", timeout=10):
    """
    Capture a snapshot from the MJPEG camera feed.
    
    Args:
        ip_address: IP address of the robot (default: 192.168.86.60)
        port: Port number for camera feed (default: 8080)
        output_file: Output filename for the snapshot (default: snapshot.jpg)
        timeout: Connection timeout in seconds (default: 10)
    
    Returns:
        bool: True if successful, False otherwise
    """
    # Construct camera feed URL
    camera_url = f"http://{ip_address}:{port}/"
    
    print(f"Connecting to camera feed at {camera_url}...")
    
    try:
        # Open the MJPEG stream
        stream = urllib.request.urlopen(camera_url, timeout=timeout)
        bytes_data = bytes()
        
        print("Reading stream data...")
        
        # Read stream until we find a complete JPEG frame
        while True:
            chunk = stream.read(1024)
            if not chunk:
                print("Error: Stream ended without finding a frame")
                return False
            
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
                    # Save the image
                    cv2.imwrite(output_file, image)
                    print(f"Snapshot saved successfully: {output_file}")
                    print(f"Image size: {image.shape[1]}x{image.shape[0]} pixels")
                    return True
                else:
                    print("Error: Failed to decode image")
                    return False
        
    except urllib.error.URLError as e:
        print(f"Error: Could not connect to camera feed: {e}")
        return False
    except Exception as e:
        print(f"Error: Unexpected error occurred: {e}")
        return False


def main():
    """Main function with command-line argument parsing."""
    parser = argparse.ArgumentParser(
        description="Capture a snapshot from MasterPi robot camera feed"
    )
    parser.add_argument(
        "--ip",
        default="192.168.86.60",
        help="IP address of the robot (default: 192.168.86.60)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port number for camera feed (default: 8080)"
    )
    parser.add_argument(
        "-o", "--output",
        default="snapshot.jpg",
        help="Output filename (default: snapshot.jpg)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="Connection timeout in seconds (default: 10)"
    )
    
    args = parser.parse_args()
    
    success = capture_snapshot(
        ip_address=args.ip,
        port=args.port,
        output_file=args.output,
        timeout=args.timeout
    )
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

