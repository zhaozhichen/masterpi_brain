"""
Safety layer for parameter validation and clamping.

Enforces limits on all robot actions to prevent unsafe operations.
"""

from typing import Tuple, Optional
import time


class SafetyLimits:
    """Safety limits and validation for robot actions."""
    
    # Base limits
    BASE_VELOCITY_MIN = 0.0
    BASE_VELOCITY_MAX = 200.0  # mm/s
    BASE_ANGULAR_RATE_MIN = -50.0
    BASE_ANGULAR_RATE_MAX = 50.0  # deg/s
    BASE_STEP_DURATION_MIN = 0.2  # seconds
    BASE_STEP_DURATION_MAX = 0.5  # seconds
    
    # Arm limits (from RPC document)
    ARM_X_MIN = -10.0  # cm
    ARM_X_MAX = 10.0
    ARM_Y_MIN = 5.0
    ARM_Y_MAX = 15.0
    ARM_Z_MIN = 0.0
    ARM_Z_MAX = 25.0
    ARM_SPEED_MIN = 500  # ms
    ARM_SPEED_MAX = 3000
    
    # Action timeout
    ACTION_TIMEOUT_DEFAULT = 2.0  # seconds
    
    @staticmethod
    def clamp_base_velocity(velocity: float) -> float:
        """Clamp base velocity to safe range."""
        return max(SafetyLimits.BASE_VELOCITY_MIN, 
                  min(SafetyLimits.BASE_VELOCITY_MAX, velocity))
    
    @staticmethod
    def clamp_angular_rate(angular_rate: float) -> float:
        """Clamp angular rate to safe range."""
        return max(SafetyLimits.BASE_ANGULAR_RATE_MIN,
                  min(SafetyLimits.BASE_ANGULAR_RATE_MAX, angular_rate))
    
    @staticmethod
    def clamp_step_duration(duration: float) -> float:
        """Clamp step duration to safe range."""
        return max(SafetyLimits.BASE_STEP_DURATION_MIN,
                  min(SafetyLimits.BASE_STEP_DURATION_MAX, duration))
    
    @staticmethod
    def clamp_arm_x(x: float) -> float:
        """Clamp arm X coordinate."""
        return max(SafetyLimits.ARM_X_MIN, min(SafetyLimits.ARM_X_MAX, x))
    
    @staticmethod
    def clamp_arm_y(y: float) -> float:
        """Clamp arm Y coordinate."""
        return max(SafetyLimits.ARM_Y_MIN, min(SafetyLimits.ARM_Y_MAX, y))
    
    @staticmethod
    def clamp_arm_z(z: float) -> float:
        """Clamp arm Z coordinate."""
        return max(SafetyLimits.ARM_Z_MIN, min(SafetyLimits.ARM_Z_MAX, z))
    
    @staticmethod
    def clamp_arm_speed(speed: int) -> int:
        """Clamp arm movement speed."""
        return max(SafetyLimits.ARM_SPEED_MIN, 
                  min(SafetyLimits.ARM_SPEED_MAX, speed))
    
    @staticmethod
    def validate_base_params(velocity: float, direction: float, 
                             angular_rate: float, duration: float) -> Tuple[bool, str]:
        """
        Validate base movement parameters.
        
        Returns:
            (is_valid: bool, error_message: str)
        """
        if velocity < 0 or velocity > SafetyLimits.BASE_VELOCITY_MAX:
            return (False, f"Velocity {velocity} out of range [0, {SafetyLimits.BASE_VELOCITY_MAX}]")
        
        if not (0 <= direction <= 360):
            return (False, f"Direction {direction} out of range [0, 360]")
        
        if angular_rate < SafetyLimits.BASE_ANGULAR_RATE_MIN or \
           angular_rate > SafetyLimits.BASE_ANGULAR_RATE_MAX:
            return (False, f"Angular rate {angular_rate} out of range "
                   f"[{SafetyLimits.BASE_ANGULAR_RATE_MIN}, {SafetyLimits.BASE_ANGULAR_RATE_MAX}]")
        
        if duration < SafetyLimits.BASE_STEP_DURATION_MIN or \
           duration > SafetyLimits.BASE_STEP_DURATION_MAX:
            return (False, f"Duration {duration} out of range "
                   f"[{SafetyLimits.BASE_STEP_DURATION_MIN}, {SafetyLimits.BASE_STEP_DURATION_MAX}]")
        
        return (True, "")
    
    @staticmethod
    def validate_arm_params(x: float, y: float, z: float, speed: int) -> Tuple[bool, str]:
        """
        Validate arm movement parameters.
        
        Returns:
            (is_valid: bool, error_message: str)
        """
        if x < SafetyLimits.ARM_X_MIN or x > SafetyLimits.ARM_X_MAX:
            return (False, f"X {x} out of range [{SafetyLimits.ARM_X_MIN}, {SafetyLimits.ARM_X_MAX}]")
        
        if y < SafetyLimits.ARM_Y_MIN or y > SafetyLimits.ARM_Y_MAX:
            return (False, f"Y {y} out of range [{SafetyLimits.ARM_Y_MIN}, {SafetyLimits.ARM_Y_MAX}]")
        
        if z < SafetyLimits.ARM_Z_MIN or z > SafetyLimits.ARM_Z_MAX:
            return (False, f"Z {z} out of range [{SafetyLimits.ARM_Z_MIN}, {SafetyLimits.ARM_Z_MAX}]")
        
        if speed < SafetyLimits.ARM_SPEED_MIN or speed > SafetyLimits.ARM_SPEED_MAX:
            return (False, f"Speed {speed} out of range "
                   f"[{SafetyLimits.ARM_SPEED_MIN}, {SafetyLimits.ARM_SPEED_MAX}]")
        
        return (True, "")


class ActionTimeout:
    """Monitor action execution time and enforce timeouts."""
    
    def __init__(self, timeout: float = SafetyLimits.ACTION_TIMEOUT_DEFAULT):
        """
        Initialize timeout monitor.
        
        Args:
            timeout: Maximum allowed duration in seconds
        """
        self.timeout = timeout
        self.start_time: Optional[float] = None
    
    def start(self):
        """Start timing."""
        self.start_time = time.time()
    
    def check(self) -> Tuple[bool, float]:
        """
        Check if timeout exceeded.
        
        Returns:
            (has_exceeded: bool, elapsed_time: float)
        """
        if self.start_time is None:
            return (False, 0.0)
        
        elapsed = time.time() - self.start_time
        exceeded = elapsed > self.timeout
        return (exceeded, elapsed)
    
    def reset(self):
        """Reset timer."""
        self.start_time = None

