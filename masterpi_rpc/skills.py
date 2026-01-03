"""
Short-step skill wrappers for robot control.

All skills enforce maximum duration, validate parameters, and return
(success: bool, result: dict, error: str).
"""

import time
from typing import Tuple, Dict, Any
from .rpc_client import RPCClient
from .safety import SafetyLimits, ActionTimeout


class RobotSkills:
    """Short-step skill wrappers for safe robot control."""
    
    def __init__(self, rpc_client: RPCClient):
        """
        Initialize skills with RPC client.
        
        Args:
            rpc_client: RPCClient instance
        """
        self.rpc = rpc_client
        self.timeout = ActionTimeout()
    
    def base_step(self, velocity: float, direction: float, angular_rate: float, 
                  duration: float) -> Tuple[bool, Dict[str, Any], str]:
        """
        Move base for a short duration, then automatically stop.
        
        Args:
            velocity: Velocity (mm/s), will be clamped
            direction: Direction angle (degrees), 0-360
            angular_rate: Angular velocity (deg/s), will be clamped
            duration: Movement duration (seconds), will be clamped to 0.2-0.5s
        
        Returns:
            (success: bool, result: dict, error: str)
        """
        # Clamp parameters
        velocity = SafetyLimits.clamp_base_velocity(velocity)
        angular_rate = SafetyLimits.clamp_angular_rate(angular_rate)
        duration = SafetyLimits.clamp_step_duration(duration)
        
        # Validate
        is_valid, error_msg = SafetyLimits.validate_base_params(
            velocity, direction, angular_rate, duration
        )
        if not is_valid:
            return (False, {}, error_msg)
        
        # Start movement
        self.timeout.start()
        success, result, error = self.rpc.set_mecanum_velocity(velocity, direction, angular_rate)
        
        if not success:
            return (False, {}, f"Failed to start base movement: {error}")
        
        # Wait for duration
        time.sleep(duration)
        
        # Stop
        stop_success, _, stop_error = self.rpc.reset_mecanum_motors()
        if not stop_success:
            return (False, {}, f"Failed to stop base: {stop_error}")
        
        elapsed = time.time() - self.timeout.start_time if self.timeout.start_time else duration
        
        return (True, {
            "action": "base_step",
            "velocity": velocity,
            "direction": direction,
            "angular_rate": angular_rate,
            "duration": duration,
            "elapsed": elapsed
        }, "")
    
    def base_stop(self) -> Tuple[bool, Dict[str, Any], str]:
        """
        Explicitly stop base movement.
        
        Returns:
            (success: bool, result: dict, error: str)
        """
        success, result, error = self.rpc.reset_mecanum_motors()
        return (success, {"action": "base_stop"}, error)
    
    def arm_move_xyz(self, x: float, y: float, z: float, pitch: float = 0.0,
                     roll: float = -90.0, yaw: float = 90.0, 
                     speed: int = 1500) -> Tuple[bool, Dict[str, Any], str]:
        """
        Move arm end-effector to target XYZ using IK.
        
        Args:
            x: X coordinate (cm), will be clamped
            y: Y coordinate (cm), will be clamped
            z: Z coordinate (cm), will be clamped
            pitch: Pitch angle (degrees), default 0.0
            roll: Roll angle (degrees), default -90.0
            yaw: Yaw angle (degrees), default 90.0
            speed: Movement speed (ms), will be clamped, default 1500
        
        Returns:
            (success: bool, result: dict with ik_success, error: str)
        """
        # Clamp parameters
        x = SafetyLimits.clamp_arm_x(x)
        y = SafetyLimits.clamp_arm_y(y)
        z = SafetyLimits.clamp_arm_z(z)
        speed = SafetyLimits.clamp_arm_speed(speed)
        
        # Validate
        is_valid, error_msg = SafetyLimits.validate_arm_params(x, y, z, speed)
        if not is_valid:
            return (False, {}, error_msg)
        
        # Execute IK movement
        self.timeout.start()
        success, result, error = self.rpc.arm_move_ik(x, y, z, pitch, roll, yaw, speed)
        
        elapsed = time.time() - self.timeout.start_time if self.timeout.start_time else 0.0
        
        if success:
            return (True, {
                "action": "arm_move_xyz",
                "x": x,
                "y": y,
                "z": z,
                "pitch": pitch,
                "roll": roll,
                "yaw": yaw,
                "speed": speed,
                "ik_success": True,
                "elapsed": elapsed
            }, "")
        else:
            return (False, {
                "action": "arm_move_xyz",
                "ik_success": False,
                "ik_error": error
            }, error)
    
    def arm_to_safe_pose(self) -> Tuple[bool, Dict[str, Any], str]:
        """
        Move arm to safe pre-grasp position.
        
        Default safe pose: (0, 6, 18, 0, -90, 90, 1500)
        This is a conservative position above the workspace.
        
        Returns:
            (success: bool, result: dict, error: str)
        """
        return self.arm_move_xyz(
            x=0.0,
            y=6.0,
            z=18.0,
            pitch=0.0,
            roll=-90.0,
            yaw=90.0,
            speed=1500
        )
    
    def gripper_open(self) -> Tuple[bool, Dict[str, Any], str]:
        """
        Open gripper.
        
        Returns:
            (success: bool, result: dict, error: str)
        """
        self.timeout.start()
        success, result, error = self.rpc.set_gripper_open()
        
        elapsed = time.time() - self.timeout.start_time if self.timeout.start_time else 0.0
        
        return (success, {
            "action": "gripper_open",
            "elapsed": elapsed
        }, error)
    
    def gripper_close(self) -> Tuple[bool, Dict[str, Any], str]:
        """
        Close gripper.
        
        Returns:
            (success: bool, result: dict, error: str)
        """
        self.timeout.start()
        success, result, error = self.rpc.set_gripper_close()
        
        elapsed = time.time() - self.timeout.start_time if self.timeout.start_time else 0.0
        
        return (success, {
            "action": "gripper_close",
            "elapsed": elapsed
        }, error)
    
    def gripper_position(self, position: int, use_time: int = 500) -> Tuple[bool, Dict[str, Any], str]:
        """
        Set gripper position by percentage.
        
        Args:
            position: Position percentage (0-100), 0=closed, 100=open
            use_time: Movement time (ms), default 500
        
        Returns:
            (success: bool, result: dict, error: str)
        """
        # Clamp position
        position = max(0, min(100, position))
        
        self.timeout.start()
        success, result, error = self.rpc.set_gripper_position(position, use_time)
        
        elapsed = time.time() - self.timeout.start_time if self.timeout.start_time else 0.0
        
        return (success, {
            "action": "gripper_position",
            "position": position,
            "use_time": use_time,
            "elapsed": elapsed
        }, error)
    
    def get_sonar_distance(self) -> Tuple[bool, float, str]:
        """
        Get ultrasonic sensor distance.
        
        Returns:
            (success: bool, distance: float (cm), error: str)
        """
        return self.rpc.get_sonar_distance()

