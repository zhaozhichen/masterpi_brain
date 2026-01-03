"""
Deterministic FSM policy for MVP task execution.

Implements state machine: SEARCH → ALIGN_BASE → APPROACH → PREGRASP → 
ALIGN_ARM → GRASP → VERIFY → RECOVER
"""

from enum import Enum
from typing import Dict, Any, Optional, Tuple
import yaml
import os


class Phase(Enum):
    """Task execution phases."""
    SEARCH = "SEARCH"
    ALIGN_BASE = "ALIGN_BASE"
    APPROACH = "APPROACH"
    PREGRASP = "PREGRASP"
    ALIGN_ARM = "ALIGN_ARM"
    GRASP = "GRASP"
    VERIFY = "VERIFY"
    RECOVER = "RECOVER"
    DONE = "DONE"
    FAILED = "FAILED"


class FSMPolicy:
    """Finite State Machine policy for deterministic task execution."""
    
    def __init__(self, thresholds_path: str = "config/thresholds.yaml"):
        """
        Initialize FSM policy.
        
        Args:
            thresholds_path: Path to thresholds configuration file
        """
        # Load thresholds
        with open(thresholds_path, 'r') as f:
            self.thresholds = yaml.safe_load(f)['thresholds']
        
        # State variables
        self.phase = Phase.SEARCH
        self.search_rotation_count = 0
        self.grasp_attempts = 0
        self.last_detection: Optional[Dict[str, Any]] = None
        self.image_center: Optional[Tuple[int, int]] = None
        self.grasp_target_px: Optional[Tuple[int, int]] = None
        self.pre_grasp_xyz: Optional[Tuple[float, float, float]] = None
        
    def set_image_size(self, width: int, height: int):
        """Set image dimensions for centering calculations."""
        self.image_center = (width // 2, height // 2)
        # Grasp target is center X, center Y + offset
        offset_y = self.thresholds['arm']['grasp_pixel_offset_y']
        self.grasp_target_px = (self.image_center[0], self.image_center[1] + offset_y)
    
    def plan(self, detection: Dict[str, Any], last_action_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Plan next action based on current phase and detection.
        
        Args:
            detection: Detection result from perception layer
            last_action_result: Result from last executed action
        
        Returns:
            {
                "action": str,  # Skill name
                "params": dict,  # Skill parameters
                "phase": str,    # Current phase
                "why": str       # Reason for action
            }
        """
        self.last_detection = detection
        
        if self.image_center is None and detection.get("found"):
            # Initialize image size from detection bbox
            if detection.get("bbox"):
                x1, y1, x2, y2 = detection["bbox"]
                self.set_image_size(x2, y2)  # Approximate
        
        # State machine logic
        if self.phase == Phase.SEARCH:
            return self._plan_search(detection)
        elif self.phase == Phase.ALIGN_BASE:
            return self._plan_align_base(detection)
        elif self.phase == Phase.APPROACH:
            return self._plan_approach(detection)
        elif self.phase == Phase.PREGRASP:
            return self._plan_pregrasp(detection)
        elif self.phase == Phase.ALIGN_ARM:
            return self._plan_align_arm(detection)
        elif self.phase == Phase.GRASP:
            return self._plan_grasp(detection, last_action_result)
        elif self.phase == Phase.VERIFY:
            return self._plan_verify(detection)
        elif self.phase == Phase.RECOVER:
            return self._plan_recover(detection)
        else:
            return {
                "action": "base_stop",
                "params": {},
                "phase": self.phase.value,
                "why": "Task completed or failed"
            }
    
    def _plan_search(self, detection: Dict[str, Any]) -> Dict[str, Any]:
        """Plan SEARCH phase: rotate base to find target."""
        if detection.get("found"):
            # Target found, switch to ALIGN_BASE
            self.phase = Phase.ALIGN_BASE
            self.search_rotation_count = 0
            return self._plan_align_base(detection)
        
        # Target not found, continue searching
        if self.search_rotation_count >= self.thresholds['base']['max_search_rotations']:
            # Expand search: move forward a bit, then continue
            self.search_rotation_count = 0
            return {
                "action": "base_step",
                "params": {
                    "velocity": 30.0,  # Slow forward
                    "direction": 0.0,
                    "angular_rate": 0.0,
                    "duration": 0.3
                },
                "phase": Phase.SEARCH.value,
                "why": "Expanding search area"
            }
        
        # Rotate in place
        self.search_rotation_count += 1
        step_deg = self.thresholds['base']['search_rotation_step_deg']
        duration = self.thresholds['base']['search_rotation_duration_s']
        
        return {
            "action": "base_step",
            "params": {
                "velocity": 0.0,
                "direction": 0.0,
                "angular_rate": step_deg / duration,  # deg/s
                "duration": duration
            },
            "phase": Phase.SEARCH.value,
            "why": f"Searching for target (rotation {self.search_rotation_count})"
        }
    
    def _plan_align_base(self, detection: Dict[str, Any]) -> Dict[str, Any]:
        """Plan ALIGN_BASE phase: center target horizontally."""
        if not detection.get("found"):
            # Target lost, go back to search
            self.phase = Phase.SEARCH
            return self._plan_search(detection)
        
        if self.image_center is None:
            return {
                "action": "base_stop",
                "params": {},
                "phase": Phase.ALIGN_BASE.value,
                "why": "Waiting for image size"
            }
        
        center_x, _ = detection["center"]
        img_center_x, _ = self.image_center
        dx = center_x - img_center_x
        tol = self.thresholds['base']['center_tol_px']
        
        if abs(dx) <= tol:
            # Centered, switch to APPROACH
            self.phase = Phase.APPROACH
            return self._plan_approach(detection)
        
        # Need to rotate to center
        # Positive dx means target is right, need to rotate right (positive angular_rate)
        angular_rate = 20.0 if dx > 0 else -20.0  # deg/s
        duration = self.thresholds['base']['search_rotation_duration_s']
        
        return {
            "action": "base_step",
            "params": {
                "velocity": 0.0,
                "direction": 0.0,
                "angular_rate": angular_rate,
                "duration": duration
            },
            "phase": Phase.ALIGN_BASE.value,
            "why": f"Centering target (dx={dx:.1f}px)"
        }
    
    def _plan_approach(self, detection: Dict[str, Any]) -> Dict[str, Any]:
        """Plan APPROACH phase: move base forward until target is large enough."""
        if not detection.get("found"):
            # Target lost, go back to search
            self.phase = Phase.SEARCH
            return self._plan_search(detection)
        
        area_ratio = detection.get("area_ratio", 0.0)
        near_threshold = self.thresholds['approach']['near_threshold']
        
        if area_ratio >= near_threshold:
            # Close enough, switch to PREGRASP
            self.phase = Phase.PREGRASP
            return self._plan_pregrasp(detection)
        
        # Check if we need to re-align
        if self.image_center:
            center_x, _ = detection["center"]
            img_center_x, _ = self.image_center
            dx = abs(center_x - img_center_x)
            if dx > self.thresholds['base']['center_tol_px']:
                # Re-align first
                self.phase = Phase.ALIGN_BASE
                return self._plan_align_base(detection)
        
        # Move forward
        velocity = self.thresholds['base']['approach_velocity_mm_s']
        duration = self.thresholds['base']['approach_duration_s']
        
        return {
            "action": "base_step",
            "params": {
                "velocity": velocity,
                "direction": 0.0,  # Forward
                "angular_rate": 0.0,
                "duration": duration
            },
            "phase": Phase.APPROACH.value,
            "why": f"Approaching target (area_ratio={area_ratio:.4f} < {near_threshold:.4f})"
        }
    
    def _plan_pregrasp(self, detection: Dict[str, Any]) -> Dict[str, Any]:
        """Plan PREGRASP phase: move arm to safe pre-grasp position."""
        if not detection.get("found"):
            # Target lost, go back to search
            self.phase = Phase.SEARCH
            return self._plan_search(detection)
        
        # Move arm to safe pose (from robot_card.yaml)
        # This is a one-time action, so we track if we've done it
        if self.pre_grasp_xyz is None:
            # Store current target position estimate for later alignment
            # We'll use a conservative pre-grasp position
            self.pre_grasp_xyz = (0.0, 6.0, 18.0)  # Safe pose from config
        
        # Move to pre-grasp pose
        self.phase = Phase.ALIGN_ARM
        return {
            "action": "arm_to_safe_pose",
            "params": {},
            "phase": Phase.PREGRASP.value,
            "why": "Moving arm to pre-grasp position"
        }
    
    def _plan_align_arm(self, detection: Dict[str, Any]) -> Dict[str, Any]:
        """Plan ALIGN_ARM phase: visual servoing to center target under end-effector."""
        if not detection.get("found"):
            # Target lost, go back to search
            self.phase = Phase.SEARCH
            return self._plan_search(detection)
        
        if self.grasp_target_px is None or self.image_center is None:
            return {
                "action": "base_stop",
                "params": {},
                "phase": Phase.ALIGN_ARM.value,
                "why": "Waiting for image size"
            }
        
        # Calculate pixel error
        target_cx, target_cy = detection["center"]
        grasp_x, grasp_y = self.grasp_target_px
        ex = target_cx - grasp_x
        ey = target_cy - grasp_y
        
        tol = self.thresholds['arm']['visual_servo_tolerance_px']
        
        if abs(ex) <= tol and abs(ey) <= tol:
            # Aligned, switch to GRASP
            self.phase = Phase.GRASP
            self.grasp_attempts = 0
            return self._plan_grasp(detection, None)
        
        # Need to adjust arm position
        # Convert pixel error to arm movement (rough approximation)
        # This is a simplified mapping - in practice, you'd calibrate this
        max_step_cm = self.thresholds['arm']['align_step_max_cm']
        
        # Scale pixel error to arm movement (rough: 1px ≈ 0.1cm at this distance)
        dx_cm = max(-max_step_cm, min(max_step_cm, ex * 0.1))
        dy_cm = max(-max_step_cm, min(max_step_cm, ey * 0.1))
        
        # Get current arm position (we'll estimate from pre_grasp_xyz)
        if self.pre_grasp_xyz:
            x, y, z = self.pre_grasp_xyz
            new_x = x + dx_cm
            new_y = y + dy_cm
            # Keep Z the same for now
            new_z = z
            
            self.pre_grasp_xyz = (new_x, new_y, new_z)
        
        return {
            "action": "arm_move_xyz",
            "params": {
                "x": new_x,
                "y": new_y,
                "z": new_z,
                "pitch": 0.0,
                "roll": -90.0,
                "yaw": 90.0,
                "speed": 1500
            },
            "phase": Phase.ALIGN_ARM.value,
            "why": f"Aligning arm (ex={ex:.1f}px, ey={ey:.1f}px)"
        }
    
    def _plan_grasp(self, detection: Dict[str, Any], last_action_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Plan GRASP phase: open gripper, lower, close, lift."""
        # This is a multi-step sequence
        # We'll use a simple state within GRASP phase
        if not hasattr(self, '_grasp_step'):
            self._grasp_step = 0
        
        if self._grasp_step == 0:
            # Open gripper
            self._grasp_step = 1
            return {
                "action": "gripper_open",
                "params": {},
                "phase": Phase.GRASP.value,
                "why": "Opening gripper"
            }
        elif self._grasp_step == 1:
            # Lower arm
            if self.pre_grasp_xyz:
                x, y, z = self.pre_grasp_xyz
                z_offset = self.thresholds['grasp']['approach_z_offset_cm']
                new_z = z + z_offset
                self._grasp_step = 2
                return {
                    "action": "arm_move_xyz",
                    "params": {
                        "x": x,
                        "y": y,
                        "z": new_z,
                        "pitch": 0.0,
                        "roll": -90.0,
                        "yaw": 90.0,
                        "speed": 1500
                    },
                    "phase": Phase.GRASP.value,
                    "why": "Lowering arm to grasp"
                }
        elif self._grasp_step == 2:
            # Close gripper
            self._grasp_step = 3
            return {
                "action": "gripper_close",
                "params": {},
                "phase": Phase.GRASP.value,
                "why": "Closing gripper"
            }
        elif self._grasp_step == 3:
            # Lift arm
            if self.pre_grasp_xyz:
                x, y, z = self.pre_grasp_xyz
                z_offset = self.thresholds['grasp']['lift_z_offset_cm']
                new_z = z + z_offset
                self._grasp_step = 0  # Reset for next attempt
                self.phase = Phase.VERIFY
                return {
                    "action": "arm_move_xyz",
                    "params": {
                        "x": x,
                        "y": y,
                        "z": new_z,
                        "pitch": 0.0,
                        "roll": -90.0,
                        "yaw": 90.0,
                        "speed": 1500
                    },
                    "phase": Phase.GRASP.value,
                    "why": "Lifting arm after grasp"
                }
        
        return {
            "action": "base_stop",
            "params": {},
            "phase": Phase.GRASP.value,
            "why": "Grasp sequence complete"
        }
    
    def _plan_verify(self, detection: Dict[str, Any]) -> Dict[str, Any]:
        """Plan VERIFY phase: check if grasp succeeded."""
        # If target disappeared or area dropped significantly, likely grasped
        if not detection.get("found"):
            # Target not visible - likely grasped
            self.phase = Phase.DONE
            return {
                "action": "base_stop",
                "params": {},
                "phase": Phase.VERIFY.value,
                "why": "Grasp verified: target disappeared"
            }
        
        # Check if area dropped significantly
        area_ratio = detection.get("area_ratio", 1.0)
        # Compare with area before grasp (we'd need to store this)
        # For now, if area is very small, assume grasped
        if area_ratio < 0.01:
            self.phase = Phase.DONE
            return {
                "action": "base_stop",
                "params": {},
                "phase": Phase.VERIFY.value,
                "why": "Grasp verified: target area dropped"
            }
        
        # Grasp may have failed, retry
        self.grasp_attempts += 1
        if self.grasp_attempts >= self.thresholds['grasp']['max_attempts']:
            self.phase = Phase.RECOVER
            return self._plan_recover(detection)
        
        # Retry grasp
        self.phase = Phase.ALIGN_ARM
        return self._plan_align_arm(detection)
    
    def _plan_recover(self, detection: Dict[str, Any]) -> Dict[str, Any]:
        """Plan RECOVER phase: handle failures."""
        # Simple recovery: go back to search
        self.phase = Phase.SEARCH
        self.search_rotation_count = 0
        self.grasp_attempts = 0
        self._grasp_step = 0
        self.pre_grasp_xyz = None
        
        return {
            "action": "arm_to_safe_pose",
            "params": {},
            "phase": Phase.RECOVER.value,
            "why": "Recovering: returning to safe pose and restarting search"
        }
    
    def reset(self):
        """Reset FSM to initial state."""
        self.phase = Phase.SEARCH
        self.search_rotation_count = 0
        self.grasp_attempts = 0
        self.last_detection = None
        self.pre_grasp_xyz = None
        if hasattr(self, '_grasp_step'):
            self._grasp_step = 0

