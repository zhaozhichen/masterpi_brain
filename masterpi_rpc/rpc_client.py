"""
JSON-RPC 2.0 client for MasterPi RPCServer.

Wraps all Level 1 functions from the RPC function list document.
All methods return (success: bool, result: Any, error: str).
"""

import requests
import os
from typing import Tuple, Any, Optional, List
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class RPCClient:
    """JSON-RPC 2.0 client for MasterPi robot."""
    
    def __init__(self, ip_address: str = None, port: int = None, timeout: int = 10):
        """
        Initialize RPC client.
        
        Args:
            ip_address: Robot IP address (default: from .env ROBOT_IP)
            port: RPC server port (default: from .env RPC_PORT)
            timeout: Request timeout in seconds
        """
        if ip_address is None:
            ip_address = os.getenv("ROBOT_IP")
            if ip_address is None:
                raise ValueError("ROBOT_IP must be set in .env file or provided as argument")
        if port is None:
            port = int(os.getenv("RPC_PORT", "9030"))
        
        self.ip_address = ip_address
        self.port = port
        self.timeout = timeout
        self.rpc_url = f"http://{ip_address}:{port}/"
    
    def _call(self, method: str, params: List[Any] = None) -> Tuple[bool, Any, str]:
        """
        Internal method to make JSON-RPC 2.0 call.
        
        Args:
            method: RPC method name
            params: Method parameters (list)
        
        Returns:
            (success: bool, result: Any, error: str)
        """
        if params is None:
            params = []
        
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": int(time.time() * 1000)  # Use timestamp as ID
        }
        
        try:
            response = requests.post(
                self.rpc_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                if "result" in result:
                    # RPC methods return (True, data, 'MethodName') or (False, error_msg, 'MethodName')
                    rpc_result = result["result"]
                    if isinstance(rpc_result, tuple) and len(rpc_result) == 3:
                        success, data, method_name = rpc_result
                        return (success, data, "" if success else str(data))
                    else:
                        return (True, rpc_result, "")
                elif "error" in result:
                    error_info = result["error"]
                    error_msg = error_info.get("message", str(error_info))
                    return (False, None, error_msg)
                else:
                    return (False, None, "Invalid RPC response format")
            else:
                return (False, None, f"HTTP {response.status_code}: {response.text}")
        
        except requests.exceptions.Timeout:
            return (False, None, f"Request timeout after {self.timeout}s")
        except requests.exceptions.ConnectionError as e:
            return (False, None, f"Connection error: {e}")
        except Exception as e:
            return (False, None, f"Unexpected error: {e}")
    
    # ========== Mechanical Arm Operations ==========
    
    def arm_move_ik(self, x: float, y: float, z: float, pitch: float = 0.0, 
                    roll: float = -90.0, yaw: float = 90.0, speed: int = 1500) -> Tuple[bool, Any, str]:
        """
        Move arm end-effector to target position using IK.
        
        Args:
            x: X coordinate (cm), range -15.0 to 15.0
            y: Y coordinate (cm), range 0.0 to 20.0
            z: Z coordinate (cm), range -5.0 to 30.0
            pitch: Pitch angle (degrees), range -90.0 to 90.0
            roll: Roll angle (degrees), range -90.0 to 90.0
            yaw: Yaw angle (degrees), range -180.0 to 180.0
            speed: Movement speed (ms), range 100 to 5000
        
        Returns:
            (success: bool, result: Any, error: str)
        """
        return self._call("ArmMoveIk", [x, y, z, pitch, roll, yaw, speed])
    
    def run_action(self, args) -> Tuple[bool, Any, str]:
        """
        Execute action group file.
        
        Args:
            args: Action group name (str) or list of names
        
        Returns:
            (success: bool, result: Any, error: str)
        """
        if isinstance(args, list):
            return self._call("RunAction", [args])
        else:
            return self._call("RunAction", [args])
    
    def stop_bus_servo(self, args: str = "stopAction") -> Tuple[bool, Any, str]:
        """
        Stop current action group.
        
        Args:
            args: Must be "stopAction"
        
        Returns:
            (success: bool, result: Any, error: str)
        """
        return self._call("StopBusServo", [args])
    
    # ========== Gripper Operations ==========
    
    def set_gripper_open(self) -> Tuple[bool, Any, str]:
        """
        Open gripper.
        
        Returns:
            (success: bool, result: Any, error: str)
        """
        return self._call("SetGripperOpen", [])
    
    def set_gripper_close(self) -> Tuple[bool, Any, str]:
        """
        Close gripper.
        
        Returns:
            (success: bool, result: Any, error: str)
        """
        return self._call("SetGripperClose", [])
    
    def set_gripper_position(self, position: int, use_time: int = 500) -> Tuple[bool, Any, str]:
        """
        Set gripper position by percentage.
        
        Args:
            position: Position percentage (0-100)
            use_time: Movement time (ms), default 500
        
        Returns:
            (success: bool, result: Any, error: str)
        """
        return self._call("SetGripperPosition", [position, use_time])
    
    def get_gripper_position(self) -> Tuple[bool, int, str]:
        """
        Get current gripper position.
        
        Returns:
            (success: bool, position: int (0-100), error: str)
        """
        return self._call("GetGripperPosition", [])
    
    # ========== Mecanum Base Operations ==========
    
    def set_mecanum_velocity(self, velocity: float, direction: float, 
                             angular_rate: float) -> Tuple[bool, Any, str]:
        """
        Set base velocity using polar coordinates.
        
        Args:
            velocity: Velocity (mm/s), range 0.0 to 200.0
            direction: Direction angle (degrees), range 0.0 to 360.0
            angular_rate: Angular velocity (deg/s), range -100.0 to 100.0
        
        Returns:
            (success: bool, result: Any, error: str)
        """
        return self._call("SetMecanumVelocity", [velocity, direction, angular_rate])
    
    def set_mecanum_translation(self, velocity_x: float, velocity_y: float) -> Tuple[bool, Any, str]:
        """
        Set base translation velocity in Cartesian coordinates.
        
        Args:
            velocity_x: X velocity (mm/s), positive = right
            velocity_y: Y velocity (mm/s), positive = forward
        
        Returns:
            (success: bool, result: Any, error: str)
        """
        return self._call("SetMecanumTranslation", [velocity_x, velocity_y])
    
    def set_movement_angle(self, angle: float) -> Tuple[bool, Any, str]:
        """
        Set base movement direction (fixed speed 70mm/s).
        
        Args:
            angle: Direction angle (degrees), 0-360, or -1 to stop
        
        Returns:
            (success: bool, result: Any, error: str)
        """
        return self._call("SetMovementAngle", [angle])
    
    def get_mecanum_status(self) -> Tuple[bool, dict, str]:
        """
        Get current base status.
        
        Returns:
            (success: bool, status: dict with velocity/direction/angular_rate, error: str)
        """
        return self._call("GetMecanumStatus", [])
    
    def reset_mecanum_motors(self) -> Tuple[bool, Any, str]:
        """
        Stop all motors and reset base state.
        
        Returns:
            (success: bool, result: Any, error: str)
        """
        return self._call("ResetMecanumMotors", [])
    
    # ========== Sensor Operations ==========
    
    def get_sonar_distance(self) -> Tuple[bool, float, str]:
        """
        Get ultrasonic sensor distance.
        
        Returns:
            (success: bool, distance: float (cm), error: str)
        """
        return self._call("GetSonarDistance", [])
    
    def get_battery_voltage(self) -> Tuple[bool, int, str]:
        """
        Get battery voltage.
        
        Returns:
            (success: bool, voltage: int (mV), error: str)
        """
        return self._call("GetBatteryVoltage", [])
    
    # ========== Emergency Stop ==========
    
    def stop_all_motors(self) -> Tuple[bool, Any, str]:
        """
        Emergency stop all motors.
        
        Returns:
            (success: bool, result: Any, error: str)
        """
        return self._call("StopAllMotors", [])

