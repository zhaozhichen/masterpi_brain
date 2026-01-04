"""
Main execution loop: observe → plan → act → log → repeat.

Enforces single skill call per iteration, parameter validation, and safety.
"""

import time
import os
from typing import Dict, Any, Optional
import yaml
from dotenv import load_dotenv

from masterpi_rpc.rpc_client import RPCClient
from masterpi_rpc.skills import RobotSkills
from perception.camera import Camera
from perception.task_detector import TaskDetector
from planner.gemini_policy import GeminiPolicy
from runtime.logger import Logger

# Load environment variables
load_dotenv()


class Executor:
    """Main execution loop for robot control."""
    
    def __init__(self, 
                 robot_ip: str = None,
                 rpc_port: int = None,
                 camera_port: int = None,
                 thresholds_path: str = "config/thresholds.yaml"):
        """
        Initialize executor.
        
        Args:
            robot_ip: Robot IP address (default: from .env ROBOT_IP)
            rpc_port: RPC server port (default: from .env RPC_PORT)
            camera_port: Camera stream port (default: from .env CAMERA_PORT)
            thresholds_path: Path to thresholds config
        """
        # Get defaults from environment variables
        if robot_ip is None:
            robot_ip = os.getenv("ROBOT_IP")
            if robot_ip is None:
                raise ValueError("ROBOT_IP must be set in .env file or provided as argument")
        if rpc_port is None:
            rpc_port = int(os.getenv("RPC_PORT", "9030"))
        if camera_port is None:
            camera_port = int(os.getenv("CAMERA_PORT", "8080"))
        
        # Initialize components
        self.rpc_client = RPCClient(robot_ip, rpc_port)
        self.skills = RobotSkills(self.rpc_client)
        self.camera = Camera(robot_ip, camera_port)
        # Task completion detector (uses gemini-3-flash-preview)
        self.task_detector = TaskDetector()
        
        # Load thresholds
        with open(thresholds_path, 'r') as f:
            self.thresholds = yaml.safe_load(f)['thresholds']
        
        # Initialize Gemini policy
        self.policy = GeminiPolicy(thresholds_path)
        
        # Logger
        self.logger = Logger()
        
        # State tracking
        self.iteration = 0
        self.last_action = None
        self.last_action_result = None
        self.current_task = None  # Will be set in run()
    
    def observe(self) -> tuple[bool, Optional[Any], Dict[str, Any]]:
        """
        Observe current state: capture image and detect target.
        
        Returns:
            (success: bool, image: np.ndarray or None, detection: dict)
        """
        # Capture frame
        success, image, timestamp = self.camera.get_frame()
        if not success or image is None:
            return (False, None, {
                "found": False,
                "bbox": None,
                "center": None,
                "area_ratio": 0.0,
                "confidence": 0.0,
                "error": "Failed to capture frame"
            })
        
        # No local detection needed - Gemini will use visual understanding
        detection = {
            "found": False,  # Unknown - let Gemini decide
            "bbox": None,
            "center": None,
            "area_ratio": 0.0,
            "confidence": 0.0,
            "note": "No local detection - using Gemini visual understanding"
        }
        
        return (True, image, detection)
    
    def plan(self, image, detection: Dict[str, Any]) -> Dict[str, Any]:
        """
        Plan next action.
        
        Args:
            image: Current camera frame (for Gemini policy)
            detection: Current detection result
        
        Returns:
            Action plan dict with "action", "params", "phase", "why"
        """
        # Build state summary for Gemini
        state_summary = {
            "task": self.current_task,
            "phase": "unknown",
            "iteration": self.iteration,
            "detection": detection,  # Included for logging, but Gemini ignores it
            "last_action": self.last_action.get("action") if self.last_action else None,
            "last_action_success": self.last_action_result is not None and self.last_action_result.get("success", False) if self.last_action_result else None
        }
        return self.policy.plan(image, detection, state_summary, self.last_action_result)
    
    def act(self, action_plan: Dict[str, Any]) -> tuple[bool, Dict[str, Any], str]:
        """
        Execute planned action.
        
        Args:
            action_plan: Action plan from policy
        
        Returns:
            (success: bool, result: dict, error: str)
        """
        action_name = action_plan.get("action")
        params = action_plan.get("params", {})
        
        # Execute action via skills
        if action_name == "base_step":
            return self.skills.base_step(
                params.get("velocity", 0.0),
                params.get("direction", 0.0),
                params.get("angular_rate", 0.0),
                params.get("duration", 0.3)
            )
        elif action_name == "base_stop":
            return self.skills.base_stop()
        elif action_name == "arm_move_xyz":
            return self.skills.arm_move_xyz(
                params.get("x", 0.0),
                params.get("y", 6.0),
                params.get("z", 18.0),
                params.get("pitch", 0.0),
                params.get("roll", -90.0),
                params.get("yaw", 90.0),
                params.get("speed", 1500)
            )
        elif action_name == "arm_to_safe_pose":
            return self.skills.arm_to_safe_pose()
        elif action_name == "gripper_open":
            return self.skills.gripper_open()
        elif action_name == "gripper_close":
            return self.skills.gripper_close()
        else:
            return (False, {}, f"Unknown action: {action_name}")
    
    def run(self, task: str, max_iterations: int = 500):
        """
        Run main execution loop.
        
        Args:
            task: Task description
            max_iterations: Maximum iterations before timeout
        """
        print(f"Starting execution: {task}")
        print(f"Policy: {type(self.policy).__name__}")
        
        # Store current task
        self.current_task = task
        
        # Start logging session
        self.logger.start_session(task)
        
        # Reset policy
        self.policy.reset()
        
        # Set log directory for Gemini policy (after reset to avoid being cleared)
        session_dir = self.logger.get_session_dir()
        if session_dir:
            self.policy.set_log_dir(session_dir)
        
        # Reset arm to safe pose before starting new task
        print("Resetting arm to safe pose...")
        print(f"  → Target position: x=0.0, y=5.0, z=20.0, pitch=0.0, roll=-90.0, yaw=90.0, speed=1500")
        success, result, error = self.skills.arm_to_safe_pose()
        if success:
            print(f"✓ Arm reset command sent successfully")
            if result:
                if "ik_success" in result:
                    print(f"  → IK calculation: {'success' if result['ik_success'] else 'failed'}")
                if "wait_time" in result:
                    print(f"  → Waited {result['wait_time']:.1f}s for movement to complete")
                # Show actual parameters used (after clamping)
                if "x" in result and "y" in result and "z" in result:
                    print(f"  → Actual position: x={result['x']}, y={result['y']}, z={result['z']}")
        else:
            print(f"⚠️  Warning: Arm reset failed: {error}")
            if result:
                print(f"  → RPC result: {result}")
            # Continue anyway - arm might already be in a safe position
        
        try:
            while self.iteration < max_iterations:
                self.iteration += 1
                print(f"\n--- Iteration {self.iteration} ---")
                
                # Observe
                obs_success, image, detection = self.observe()
                if not obs_success:
                    error_msg = detection.get("error", "Unknown error")
                    print(f"Warning: Observation failed - {error_msg}")
                    # Use latest cached frame if available
                    if self.camera.latest_frame is not None:
                        print("  → Using cached frame from previous observation")
                        image = self.camera.latest_frame.copy()
                        obs_success = True
                        # Update detection to indicate we're using cached frame
                        detection["using_cached_frame"] = True
                    else:
                        # If no cached frame, try to get one more time with fresh connection
                        print("  → No cached frame, retrying with fresh connection...")
                        try:
                            retry_success, retry_image, _ = self.camera.get_frame()
                            if retry_success and retry_image is not None:
                                print("  → Retry successful, using fresh frame")
                                image = retry_image
                                obs_success = True
                            else:
                                print("  → Retry also failed, will log without image")
                        except Exception as e:
                            print(f"  → Retry exception: {e}, will log without image")
                
                # Get phase string
                phase_str = str(self.policy.phase)
                print(f"Detection: found={detection.get('found')}, "
                      f"area_ratio={detection.get('area_ratio', 0):.4f}, "
                      f"phase={phase_str}")
                
                # Check task completion using fast detector (gemini-3-flash-preview)
                # This happens BEFORE planning to avoid unnecessary planning if task is done
                if image is not None:
                    try:
                        completion_check = self.task_detector.check_completion(
                            image=image,
                            task_description=task,
                            last_action=self.last_action.get("action") if self.last_action else None
                        )
                        
                        if completion_check.get("completed", False):
                            confidence = completion_check.get("confidence", 0.0)
                            reason = completion_check.get("reason", "")
                            evidence = completion_check.get("evidence", "")
                            print(f"\n✓ Task completed! (confidence: {confidence:.2f})")
                            print(f"  Reason: {reason}")
                            print(f"  Evidence: {evidence}")
                            break
                    except Exception as e:
                        # If detection fails, continue with planning
                        print(f"Warning: Task completion check failed: {e}")
                
                # Plan (using gemini-robotics-er-1.5-preview)
                action_plan = self.plan(image, detection)
                
                # Print action with full thinking process
                action_name = action_plan.get('action', 'unknown')
                thinking_process = action_plan.get('thinking_process') or action_plan.get('why', '')
                
                print(f"Action: {action_name}")
                if thinking_process:
                    # Print thinking process in a readable format
                    print(f"Thinking: {thinking_process}")
                else:
                    why = action_plan.get('why', '')
                    if why:
                        print(f"Why: {why}")
                
                # Act
                act_success, action_result, error = self.act(action_plan)
                self.last_action = action_plan
                self.last_action_result = action_result
                
                if not act_success:
                    print(f"Action failed: {error}")
                    # If it's a connection error, provide additional help
                    if "Cannot connect to robot" in error or "No route to host" in error:
                        print("\n⚠️  Robot connection issue detected!")
                        print("   Please check:")
                        print(f"   1. Robot is powered on and connected to network")
                        print(f"   2. Robot IP is correct: {self.rpc_client.ip_address}")
                        print(f"   3. RPC server is running on port {self.rpc_client.port}")
                        print(f"   4. Network connectivity: try 'ping {self.rpc_client.ip_address}'")
                        print("   The system will continue trying, but actions will fail until connection is restored.")
                
                # Create state summary
                phase_str = str(self.policy.phase)  # Gemini uses string phase
                state_summary = {
                    "task": task,
                    "phase": phase_str,
                    "iteration": self.iteration,
                    "detection": detection,
                    "last_action": action_plan.get("action"),
                    "last_action_success": act_success
                }
                
                # Log (includes thinking process from action_plan)
                self.logger.log_iteration(
                    image=image,
                    detection=detection,
                    state_summary=state_summary,
                    action_plan=action_plan,  # Contains "thinking_process" field
                    action_result=action_result
                )
                
                # Small delay for observation
                time.sleep(self.thresholds['general']['observation_delay_s'])
            
            if self.iteration >= max_iterations:
                print(f"Reached maximum iterations ({max_iterations})")
        
        except KeyboardInterrupt:
            print("\nExecution interrupted by user")
        except Exception as e:
            print(f"Execution error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Stop all movement
            self.skills.base_stop()
            self.camera.close()
            
            # Save log summary
            self.logger.save_summary()
            print(f"\nExecution complete. Logs saved to: {self.logger.get_session_dir()}")

