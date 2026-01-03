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
from perception.detect_red import RedBlockDetector
from planner.fsm_policy import FSMPolicy, Phase
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
                 policy_type: str = "fsm",
                 thresholds_path: str = "config/thresholds.yaml"):
        """
        Initialize executor.
        
        Args:
            robot_ip: Robot IP address (default: from .env ROBOT_IP)
            rpc_port: RPC server port (default: from .env RPC_PORT)
            camera_port: Camera stream port (default: from .env CAMERA_PORT)
            policy_type: Policy type ("fsm" or "gemini")
            thresholds_path: Path to thresholds config
        """
        # Get defaults from environment variables
        if robot_ip is None:
            robot_ip = os.getenv("ROBOT_IP", "192.168.86.60")
        if rpc_port is None:
            rpc_port = int(os.getenv("RPC_PORT", "9030"))
        if camera_port is None:
            camera_port = int(os.getenv("CAMERA_PORT", "8080"))
        
        # Initialize components
        self.rpc_client = RPCClient(robot_ip, rpc_port)
        self.skills = RobotSkills(self.rpc_client)
        self.camera = Camera(robot_ip, camera_port)
        self.detector = RedBlockDetector()
        
        # Load thresholds
        with open(thresholds_path, 'r') as f:
            self.thresholds = yaml.safe_load(f)['thresholds']
        
        # Initialize policy
        if policy_type == "fsm":
            self.policy = FSMPolicy(thresholds_path)
        elif policy_type == "gemini":
            self.policy = GeminiPolicy(thresholds_path)
        else:
            raise ValueError(f"Unknown policy type: {policy_type}")
        
        # Logger
        self.logger = Logger()
        
        # State tracking
        self.iteration = 0
        self.last_action = None
        self.last_action_result = None
        self.stuck_counter = 0
        self.last_action_name = None
        self.current_task = "pick up red block"
    
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
        
        # Detect target
        detection = self.detector.detect(image)
        
        # Set image size in policy if needed (only for FSM policy)
        if image is not None and isinstance(self.policy, FSMPolicy):
            h, w = image.shape[:2]
            self.policy.set_image_size(w, h)
        
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
        if isinstance(self.policy, GeminiPolicy):
            # Gemini policy needs image and state summary
            state_summary = {
                "task": self.current_task,
                "phase": "unknown",
                "iteration": self.iteration,
                "detection": detection,
                "last_action": self.last_action.get("action") if self.last_action else None,
                "last_action_success": self.last_action_result is not None and self.last_action_result.get("success", False) if self.last_action_result else None
            }
            return self.policy.plan(image, detection, state_summary, self.last_action_result)
        else:
            # FSM policy
            return self.policy.plan(detection, self.last_action_result)
    
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
        
        # Check for stuck condition (same action repeated)
        if action_name == self.last_action_name:
            self.stuck_counter += 1
            if self.stuck_counter >= self.thresholds['general']['stuck_threshold']:
                # Force recovery (only for FSM policy)
                if isinstance(self.policy, FSMPolicy):
                    self.policy.phase = Phase.RECOVER
                return (False, {}, "Stuck: same action repeated too many times")
        else:
            self.stuck_counter = 0
        
        self.last_action_name = action_name
        
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
    
    def run(self, task: str = "pick up red block", max_iterations: int = 500):
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
        
        try:
            while self.iteration < max_iterations:
                self.iteration += 1
                print(f"\n--- Iteration {self.iteration} ---")
                
                # Observe
                obs_success, image, detection = self.observe()
                if not obs_success:
                    print("Warning: Observation failed")
                
                # Get phase string (handle both FSM Phase enum and Gemini string)
                phase_str = self.policy.phase.value if hasattr(self.policy.phase, 'value') else str(self.policy.phase)
                print(f"Detection: found={detection.get('found')}, "
                      f"area_ratio={detection.get('area_ratio', 0):.4f}, "
                      f"phase={phase_str}")
                
                # Check if done (only for FSM policy)
                if isinstance(self.policy, FSMPolicy):
                    if self.policy.phase == Phase.DONE:
                        print("Task completed!")
                        break
                    elif self.policy.phase == Phase.FAILED:
                        print("Task failed!")
                        break
                
                # Plan
                action_plan = self.plan(image, detection)
                print(f"Action: {action_plan.get('action')} - {action_plan.get('why')}")
                
                # Act
                act_success, action_result, error = self.act(action_plan)
                self.last_action = action_plan
                self.last_action_result = action_result
                
                if not act_success:
                    print(f"Action failed: {error}")
                
                # Create state summary
                # Get phase string (handle both FSM Phase enum and Gemini string)
                phase_str = self.policy.phase.value if hasattr(self.policy.phase, 'value') else str(self.policy.phase)
                state_summary = {
                    "task": task,
                    "phase": phase_str,
                    "iteration": self.iteration,
                    "detection": detection,
                    "last_action": action_plan.get("action"),
                    "last_action_success": act_success
                }
                
                # Log
                self.logger.log_iteration(
                    image=image,
                    detection=detection,
                    state_summary=state_summary,
                    action_plan=action_plan,
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

