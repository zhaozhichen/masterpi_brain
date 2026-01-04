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
        
        # Referee: Track recent base_step actions to detect oscillation and ineffective strafing
        self.recent_base_steps = []  # List of (angular_rate, velocity, direction) tuples
        self.max_recent_steps = 8  # Track last 8 base_step actions
        # Post-grasp visual verification flag
        self.need_post_grasp_check = False
        
        # Referee: Track arm movements to detect clamping (coordinates out of workspace)
        self.recent_arm_moves = []  # List of (requested_x, requested_y, actual_x, actual_y) tuples
        self.max_recent_arm_moves = 6  # Track last 6 arm movements
        
        # Referee: Track grasping attempts to detect repeated failed grasps
        self.recent_grasp_attempts = []  # List of action names in grasping sequence
        self.max_grasp_attempts = 20  # Track last 20 actions to detect patterns
        self.grasp_sequence_pattern = ['arm_move_xyz', 'gripper_open', 'gripper_close', 'arm_to_safe_pose']
        
        # Referee: Track target visibility to detect prolonged search
        self.target_not_visible_count = 0  # Count consecutive iterations where target is not visible
    
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
        # Detect oscillation pattern in recent base_step actions
        oscillation_hint = self._detect_oscillation()
        arm_clamping_hint = self._detect_arm_clamping()
        repeated_grasp_hint = self._detect_repeated_grasp_attempts()
        prolonged_search_hint = self._detect_prolonged_search()
        
        # Build state summary for Gemini
        state_summary = {
            "task": self.current_task,
            "phase": "unknown",
            "iteration": self.iteration,
            "detection": detection,  # Included for logging, but Gemini ignores it
            "last_action": self.last_action.get("action") if self.last_action else None,
            "last_action_success": self.last_action_result is not None and self.last_action_result.get("success", False) if self.last_action_result else None,
            "oscillation_hint": oscillation_hint,  # Referee hint for Gemini
            "arm_clamping_hint": arm_clamping_hint,  # Referee hint for Gemini
            "repeated_grasp_hint": repeated_grasp_hint,  # Referee hint for Gemini
            "prolonged_search_hint": prolonged_search_hint,  # Referee hint for Gemini
            "post_grasp_check_needed": self.need_post_grasp_check  # Referee hint for Gemini
        }
        return self.policy.plan(image, detection, state_summary, self.last_action_result)
    
    def _detect_arm_clamping(self) -> Optional[str]:
        """
        Detect if arm movements are being clamped to workspace limits repeatedly.
        
        Returns:
            Hint string if clamping detected, None otherwise
        """
        if len(self.recent_arm_moves) < 4:
            return None
        
        # Check if recent arm moves show clamping pattern
        clamping_count = 0
        for req_x, req_y, act_x, act_y in self.recent_arm_moves:
            # Check if requested coordinates were clamped
            x_clamped = abs(req_x - act_x) > 0.5  # More than 0.5cm difference
            y_clamped = abs(req_y - act_y) > 0.5
            if x_clamped or y_clamped:
                clamping_count += 1
        
        # If most recent moves were clamped, it's a problem
        if clamping_count >= 3:
            # Get the most recent clamped move to show limits
            req_x, req_y, act_x, act_y = self.recent_arm_moves[-1]
            return (f"⚠️ REFEREE HINT: Arm coordinates are being clamped to workspace limits. "
                   f"Requested ({req_x:.1f}, {req_y:.1f}) was clamped to ({act_x:.1f}, {act_y:.1f}). "
                   f"Workspace limits: X=[-10, 10] cm, Y=[5, 15] cm. "
                   f"If target is outside workspace, use base movement to reposition robot, "
                   f"or adjust approach strategy (e.g., rotate base, change camera angle).")
        
        return None
    
    def _detect_oscillation(self) -> Optional[str]:
        """
        Detect oscillation pattern or ineffective strafing in recent base_step actions.
        
        Returns:
            Hint string if problem detected, None otherwise
        """
        if len(self.recent_base_steps) < 6:
            return None
        
        # Extract data
        angular_rates = [ar for ar, v, d in self.recent_base_steps]
        velocities = [v for ar, v, d in self.recent_base_steps]
        directions = [d for ar, v, d in self.recent_base_steps]
        
        # Check 1: Rotation oscillation (velocity ≈ 0, angular_rate alternates)
        rotation_only = all(abs(v) < 1e-6 for v in velocities)
        if rotation_only:
            sign_changes = 0
            for i in range(1, len(angular_rates)):
                if angular_rates[i] != 0 and angular_rates[i-1] != 0:
                    if (angular_rates[i] > 0) != (angular_rates[i-1] > 0):
                        sign_changes += 1
            
            if sign_changes >= 4:
                return ("⚠️ REFEREE HINT: Detected oscillation pattern in recent base_step rotations "
                       f"(alternating angular_rate: {angular_rates[-6:]}). "
                       "Consider switching to strafe-based centering (velocity=30-60, direction=90/270, angular_rate=0) "
                       "or using arm movement if target is close.")
        
        # Check 2: Ineffective same-direction strafing (velocity > 0, same direction, no rotation)
        strafing = all(abs(v) > 1e-6 and abs(ar) < 1e-6 for ar, v, d in self.recent_base_steps)
        if strafing and len(self.recent_base_steps) >= 6:
            # Check if all recent steps are in the same direction (within 10 degrees)
            if len(set(directions)) <= 2:  # Same or very similar direction
                return ("⚠️ REFEREE HINT: Detected ineffective strafing pattern - "
                       f"repeated {len(self.recent_base_steps)} base_step actions in same direction "
                       f"(direction={directions[-1]:.0f}°, velocity={velocities[-1]:.0f} mm/s) without progress. "
                       "If target is visible but not centering, try: "
                       "1) Reverse direction (direction=270 if currently 90, or vice versa), "
                       "2) Use arm movement to approach target directly, "
                       "3) Adjust camera height (arm z) for better view.")
        
        return None
    
    def _detect_repeated_grasp_attempts(self) -> Optional[str]:
        """
        Detect repeated grasping attempts that may indicate failed grasps.
        
        Returns:
            Hint string if repeated grasp pattern detected, None otherwise
        """
        if len(self.recent_grasp_attempts) < 6:
            return None
        
        # Check for repeated grasp sequences with flexible pattern matching
        # Pattern: (arm_move_xyz)* → gripper_open → (arm_move_xyz)* → gripper_close → arm_to_safe_pose
        # This allows multiple arm movements before/after gripper_open
        
        pattern_count = 0
        i = 0
        while i < len(self.recent_grasp_attempts) - 2:
            # Look for gripper_open
            if self.recent_grasp_attempts[i] == 'gripper_open':
                # After gripper_open, look for gripper_close (allowing arm_move_xyz in between)
                j = i + 1
                while j < len(self.recent_grasp_attempts) and self.recent_grasp_attempts[j] == 'arm_move_xyz':
                    j += 1
                
                # Check if we have gripper_close followed by arm_to_safe_pose
                if (j < len(self.recent_grasp_attempts) and
                    self.recent_grasp_attempts[j] == 'gripper_close'):
                    k = j + 1
                    while k < len(self.recent_grasp_attempts) and self.recent_grasp_attempts[k] == 'arm_move_xyz':
                        k += 1
                    
                    if (k < len(self.recent_grasp_attempts) and
                        self.recent_grasp_attempts[k] == 'arm_to_safe_pose'):
                        pattern_count += 1
                        i = k + 1  # Skip past this pattern
                        continue
            i += 1
        
        # If we've seen the pattern 2+ times, it's likely failing
        if pattern_count >= 2:
            return (f"⚠️ REFEREE HINT: Detected {pattern_count} repeated grasp attempts "
                   f"(gripper_open → gripper_close → arm_to_safe_pose sequence). "
                   f"This suggests the grasp is failing. Consider: "
                   f"1) Adjusting approach angle or position, "
                   f"2) Verifying target is actually in gripper after close, "
                   f"3) Trying a different grasping strategy (e.g., different z height, different approach), "
                   f"4) If target keeps disappearing after grasp, it may have been successfully grasped - verify visually.")
        
        return None
    
    def _detect_prolonged_search(self) -> Optional[str]:
        """
        Detect prolonged search when target is not visible for many iterations.
        
        Returns:
            Hint string if prolonged search detected, None otherwise
        """
        # Check if we've been searching for 10+ iterations without finding target
        # This is a simple heuristic - if iteration > 10 and last few actions were base_step rotations
        if self.iteration < 10:
            return None
        
        # Check if recent actions are mostly base_step rotations (searching)
        if len(self.recent_base_steps) >= 6:
            rotation_only = all(abs(v) < 1e-6 and abs(ar) > 1e-6 for ar, v, d in self.recent_base_steps)
            if rotation_only:
                return ("⚠️ REFEREE HINT: Prolonged search detected - target not visible for many iterations. "
                       "Consider: 1) Moving forward (base_step with velocity>0, direction=0) to explore new areas, "
                       "2) Changing camera height (arm z) for different perspective, "
                       "3) Target may have been moved or is outside current search area.")
        
        return None
    
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
            velocity = params.get("velocity", 0.0)
            angular_rate = params.get("angular_rate", 0.0)
            direction = params.get("direction", 0.0)
            
            # Record base_step for oscillation and ineffective strafing detection
            self.recent_base_steps.append((angular_rate, velocity, direction))
            if len(self.recent_base_steps) > self.max_recent_steps:
                self.recent_base_steps.pop(0)
            
            return self.skills.base_step(
                velocity,
                direction,
                angular_rate,
                params.get("duration", 0.3)
            )
        elif action_name == "base_stop":
            return self.skills.base_stop()
        elif action_name == "task_complete":
            # Special action: Gemini declared task completion
            # Return success but don't execute any robot action
            return (True, {
                "action": "task_complete",
                "message": "Task completion declared by Gemini"
            }, "")
        elif action_name == "arm_move_xyz":
            # Clear base_step history when switching to arm movement
            self.recent_base_steps.clear()
            
            # Record requested coordinates before clamping
            requested_x = params.get("x", 0.0)
            requested_y = params.get("y", 6.0)
            
            # Execute arm movement
            success, result, error = self.skills.arm_move_xyz(
                requested_x,
                requested_y,
                params.get("z", 18.0),
                params.get("pitch", 0.0),
                params.get("roll", -90.0),
                params.get("yaw", 90.0),
                params.get("speed", 1500)
            )
            
            # Record arm movement for clamping detection
            if success and result:
                actual_x = result.get("x", requested_x)
                actual_y = result.get("y", requested_y)
                self.recent_arm_moves.append((requested_x, requested_y, actual_x, actual_y))
                if len(self.recent_arm_moves) > self.max_recent_arm_moves:
                    self.recent_arm_moves.pop(0)
            
            return success, result, error
        elif action_name == "arm_to_safe_pose":
            # Clear base_step history when switching to arm movement
            self.recent_base_steps.clear()
            return self.skills.arm_to_safe_pose()
        elif action_name == "gripper_open":
            return self.skills.gripper_open()
        elif action_name == "gripper_close":
            success, result, error = self.skills.gripper_close()
            # If gripper close succeeded, schedule a post-grasp visual check
            if success:
                self.need_post_grasp_check = True
            # Record action for grasp pattern detection
            self.recent_grasp_attempts.append(action_name)
            if len(self.recent_grasp_attempts) > self.max_grasp_attempts:
                self.recent_grasp_attempts.pop(0)
            return success, result, error
        elif action_name in ["arm_move_xyz", "gripper_open", "arm_to_safe_pose"]:
            # Record action for grasp pattern detection
            self.recent_grasp_attempts.append(action_name)
            if len(self.recent_grasp_attempts) > self.max_grasp_attempts:
                self.recent_grasp_attempts.pop(0)
            # Continue with existing logic for these actions
            if action_name == "arm_move_xyz":
                # Clear base_step history when switching to arm movement
                self.recent_base_steps.clear()
                
                # Record requested coordinates before clamping
                requested_x = params.get("x", 0.0)
                requested_y = params.get("y", 6.0)
                
                # Execute arm movement
                success, result, error = self.skills.arm_move_xyz(
                    requested_x,
                    requested_y,
                    params.get("z", 18.0),
                    params.get("pitch", 0.0),
                    params.get("roll", -90.0),
                    params.get("yaw", 90.0),
                    params.get("speed", 1500)
                )
                
                # Record arm movement for clamping detection
                if success and result:
                    actual_x = result.get("x", requested_x)
                    actual_y = result.get("y", requested_y)
                    self.recent_arm_moves.append((requested_x, requested_y, actual_x, actual_y))
                    if len(self.recent_arm_moves) > self.max_recent_arm_moves:
                        self.recent_arm_moves.pop(0)
                
                return success, result, error
            elif action_name == "arm_to_safe_pose":
                # Clear base_step history when switching to arm movement
                self.recent_base_steps.clear()
                return self.skills.arm_to_safe_pose()
            elif action_name == "gripper_open":
                return self.skills.gripper_open()
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
        
        # Track consecutive base_stop actions (may indicate task completion)
        consecutive_base_stop = 0
        max_consecutive_base_stop = 3  # If 3+ consecutive base_stop with completion keywords, stop
        
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
                
                # If post-grasp visual verification is pending, force a check action
                if self.need_post_grasp_check:
                    action_plan = {
                        "action": "arm_to_safe_pose",
                        "params": {},
                        "phase": "VERIFY",
                        "why": "Post-grasp visual check: bring gripper into view to verify object is held"
                    }
                    # Clear flag after scheduling the forced action
                    self.need_post_grasp_check = False
                else:
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
                
                # Check for task completion
                if action_plan.get("action") == "task_complete":
                    print("\n✓ Task completion declared by Gemini")
                    print(f"Reason: {action_plan.get('why', 'N/A')[:200]}")
                    break
                
                # Track consecutive base_stop actions (may indicate completion)
                if action_plan.get("action") == "base_stop":
                    why = action_plan.get("why", "").lower()
                    completion_keywords = ["complete", "successfully", "finished", "accomplished", "task"]
                    if any(kw in why for kw in completion_keywords):
                        consecutive_base_stop += 1
                        if consecutive_base_stop >= max_consecutive_base_stop:
                            print(f"\n✓ Detected {consecutive_base_stop} consecutive base_stop actions with completion keywords")
                            print("Stopping execution - task may be complete")
                            break
                    else:
                        consecutive_base_stop = 0  # Reset if no completion keywords
                else:
                    consecutive_base_stop = 0  # Reset if not base_stop
                
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

