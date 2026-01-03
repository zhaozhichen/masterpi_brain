"""
OpenCV-based red block detection.

Uses HSV color space with adaptive thresholding and morphological operations.
"""

import cv2
import numpy as np
from typing import Dict, Any, Optional, Tuple


class RedBlockDetector:
    """Detect red blocks in images using OpenCV."""
    
    def __init__(self):
        """Initialize detector with default HSV ranges for red."""
        # Red color in HSV (handles both red ranges due to hue wrap-around)
        # Lower red range
        self.lower_red1 = np.array([0, 50, 50])
        self.upper_red1 = np.array([10, 255, 255])
        # Upper red range
        self.lower_red2 = np.array([170, 50, 50])
        self.upper_red2 = np.array([180, 255, 255])
        
        # Minimum contour area (to filter noise)
        self.min_contour_area = 100
    
    def detect(self, image: np.ndarray) -> Dict[str, Any]:
        """
        Detect red block in image.
        
        Args:
            image: BGR image from camera
        
        Returns:
            {
                "found": bool,
                "bbox": (x1, y1, x2, y2) or None,
                "center": (cx, cy) or None,
                "area_ratio": float,  # bbox_area / image_area
                "confidence": float  # 0.0 to 1.0
            }
        """
        if image is None or image.size == 0:
            return {
                "found": False,
                "bbox": None,
                "center": None,
                "area_ratio": 0.0,
                "confidence": 0.0
            }
        
        # Convert BGR to HSV
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        
        # Create mask for red color (both ranges)
        mask1 = cv2.inRange(hsv, self.lower_red1, self.upper_red1)
        mask2 = cv2.inRange(hsv, self.lower_red2, self.upper_red2)
        mask = cv2.bitwise_or(mask1, mask2)
        
        # Apply morphological operations to reduce noise
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        
        # Find contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return {
                "found": False,
                "bbox": None,
                "center": None,
                "area_ratio": 0.0,
                "confidence": 0.0
            }
        
        # Find largest contour
        largest_contour = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest_contour)
        
        if area < self.min_contour_area:
            return {
                "found": False,
                "bbox": None,
                "center": None,
                "area_ratio": 0.0,
                "confidence": 0.0
            }
        
        # Get bounding box
        x, y, w, h = cv2.boundingRect(largest_contour)
        bbox = (x, y, x + w, y + h)
        
        # Calculate center
        center = (x + w // 2, y + h // 2)
        
        # Calculate area ratio
        image_area = image.shape[0] * image.shape[1]
        area_ratio = area / image_area
        
        # Calculate confidence (based on area and aspect ratio)
        # Prefer more square-like shapes
        aspect_ratio = w / h if h > 0 else 0
        aspect_score = 1.0 - abs(1.0 - aspect_ratio)  # Closer to 1.0 is better
        area_score = min(area_ratio * 20, 1.0)  # Normalize area
        confidence = (aspect_score * 0.3 + area_score * 0.7)
        
        return {
            "found": True,
            "bbox": bbox,
            "center": center,
            "area_ratio": area_ratio,
            "confidence": confidence
        }
    
    def set_hsv_ranges(self, lower1: Tuple[int, int, int], upper1: Tuple[int, int, int],
                       lower2: Optional[Tuple[int, int, int]] = None,
                       upper2: Optional[Tuple[int, int, int]] = None):
        """
        Set custom HSV ranges for red detection.
        
        Args:
            lower1: Lower bound for first red range
            upper1: Upper bound for first red range
            lower2: Lower bound for second red range (optional)
            upper2: Upper bound for second red range (optional)
        """
        self.lower_red1 = np.array(lower1)
        self.upper_red1 = np.array(upper1)
        if lower2 is not None and upper2 is not None:
            self.lower_red2 = np.array(lower2)
            self.upper_red2 = np.array(upper2)
    
    def set_min_contour_area(self, area: int):
        """Set minimum contour area threshold."""
        self.min_contour_area = area

