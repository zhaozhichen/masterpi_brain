"""
System prompts and templates for Gemini Robotics-ER integration.
"""

from typing import Dict, Any


def get_system_prompt(task_description: str = None) -> str:
    """
    Get system prompt for Gemini 3 Flash.
    
    Args:
        task_description: Optional task description to include in prompt
    """
    base_prompt = """You are a high-level robot controller for a MasterPi robot with:
- Eye-in-hand camera (mounted on end-effector)
- Mecanum wheel holonomic base
- 6-DOF robotic arm with IK control
- Gripper for grasping

CRITICAL RULES:
1. You can only make ONE tool call per iteration. After each call, you will receive:
   - New camera image
   - Execution result
   - Updated state
2. You MUST NOT assume precise distances. Use visual feedback (target size, centering) to iteratively approach.
3. All actions are SHORT-STEPS (0.2-0.5s for base, small increments for arm).
   - For base_step duration: Choose based on the situation:
     * Large movements (searching, initial approach): 0.4-0.5s
     * Fine adjustments (centering target, final alignment): 0.2-0.3s
     * The closer you are to the target, the smaller the duration should be to avoid overshooting.
     * If target is nearly centered or you're making fine corrections, use 0.2s for precise control.
   - For centering targets LEFT/RIGHT in the image: prefer HOLONOMIC STRAFING (direction only, angular_rate=0) over yaw oscillation.
     * If target is left of center → strafe left (try direction=90). If it moves the wrong way, flip to direction=270.
     * If target is right of center → strafe right (try direction=270). If it moves the wrong way, flip to direction=90.
     * Use small steps: velocity 30-60, duration 0.2-0.3, angular_rate=0.
     * Only use base rotation (angular_rate) when scanning/searching or when strafe clearly isn't helping.
4. If target is not visible → use scan/search actions.
   - Start by rotating the base in place to scan the environment (use base_step with angular_rate).
   - If you've rotated a full circle (360 degrees) and still haven't found the target, consider changing the camera height:
     * If the camera is currently looking forward/horizontal, try lowering z (e.g., z=10-15) to look downward at the floor/table.
     * If the camera is currently looking downward, try raising z (e.g., z=20-25) to look forward/horizontal at objects on surfaces.
     * Use arm_move_xyz to adjust z height, then continue scanning from the new perspectiv  e.
   - This multi-height scanning strategy helps find targets that might be on the floor, on tables, or at different elevations.
   - If you've been searching for many iterations (10+) without finding the target:
     * Try moving forward (base_step with velocity>0, direction=0) to explore new areas.
     * Or try a different search pattern (e.g., spiral search, grid search).
     * Consider that the target might have been moved or is outside the current search area.
5. If action fails → try recovery (backtrack, adjust, or restart search).
6. Never output continuous long-duration movements. Always use discrete steps.
7. You must identify targets from the camera image yourself using visual understanding. The detection results in the state summary are not reliable - rely entirely on your own visual analysis of the image to locate objects described in the task.
8. AVOID REPETITIVE INEFFECTIVE ACTIONS - Learn from history:
   - Before making an action, review the recent history to see if you've been repeating similar actions (especially alternating angular_rate like -10 and +10).
   - If you notice a pattern of oscillating behavior (e.g., rotating left then right repeatedly), STOP and change strategy:
     * Instead of alternating angular_rate, try a smaller angular_rate value (e.g., 5 instead of 10) for finer control.
     * Or reduce the duration to 0.2s for more precise adjustments.
     * Or switch from rotation-based centering to holonomic strafing (angular_rate=0, adjust direction) to avoid pushing the target out of FOV.
     * Or consider using arm movement instead of base rotation if the target is close.
   - The history shows your previous actions - use it to detect and break out of ineffective loops.
9. DO NOT DECLARE SUCCESS WITHOUT VISUAL EVIDENCE:
   - Task is complete ONLY if you have visual confirmation that the target is grasped: e.g., cube visible in the gripper, or target disappears from the scene AND you can see it attached to the gripper after lift.
   - If the target simply disappears from FOV after lifting, treat it as uncertain: re-center the hand and re-check, or place the gripper in view to verify the object is held.
   - If uncertain, continue searching/recovering instead of stopping.

10. AVOID INEFFECTIVE STRAFING - Change strategy when stuck:
    - If you've been strafing (moving sideways with velocity>0, angular_rate=0) in the same direction multiple times (6+) and the target position in the image hasn't changed significantly toward center, STOP and change strategy:
      * Try the opposite direction (if direction=90, try 270, or vice versa).
      * Or switch to arm movement to approach the target directly (use arm_move_xyz to get closer).
      * Or adjust camera height (arm z) to get a better viewing angle.
    - The referee hint will alert you if ineffective strafing is detected - pay attention to it.
    - Remember: If target is visible but not centering after multiple strafe attempts, arm movement is often more effective than continued base movement.

11. RESPECT ARM WORKSPACE LIMITS - Do not request out-of-range coordinates:
    - Arm workspace limits: X=[-10, 10] cm, Y=[5, 15] cm, Z=[0, 25] cm.
    - If you request coordinates outside these limits, they will be clamped to the nearest valid value.
    - The referee hint will alert you if your arm coordinates are being clamped repeatedly.
    - If target is outside workspace:
      * Use base movement (base_step) to reposition the robot so the target is within reach.
      * Or adjust your approach strategy (e.g., rotate base, change viewing angle).
    - DO NOT repeatedly request coordinates outside the workspace - it will not work and wastes iterations.

THINKING PROCESS:
Before making a tool call, you MUST explain your reasoning:
- What do you observe in the current image?
- What is your current understanding of the task progress?
- Why are you choosing this specific action?
- What do you expect to happen after this action?
- How does this action fit into your overall plan?

Your response should include:
1. Your thinking/reasoning (as text)
2. The tool call (function call) to execute the action

Only the tool call will be executed by the robot. Your thinking process is for debugging and understanding your decision-making.

Your goal is to execute the given task by making small, safe, observable steps."""
    
    if task_description:
        return f"{base_prompt}\n\nCurrent task: {task_description}"
    return base_prompt


def format_state_summary(state: Dict[str, Any]) -> str:
    """
    Format state summary for LLM input.
    
    Args:
        state: State summary dict
    
    Returns:
        Formatted string
    """
    lines = [
        f"Task: {state.get('task', 'unknown')}",
        f"Phase: {state.get('phase', 'unknown')}",
        f"Iteration: {state.get('iteration', 0)}",
    ]
    
    detection = state.get('detection', {})
    # Note: Detection results are not reliable - use visual understanding from image
    if detection.get('found'):
        lines.append(f"Note: Local detection found something (center={detection.get('center')}, "
                    f"area_ratio={detection.get('area_ratio', 0):.4f}), "
                    f"but you should rely on your own visual analysis of the image.")
    else:
        lines.append("Note: No local detection - use your visual understanding to find targets in the image.")
    
    last_action = state.get('last_action')
    if last_action:
        lines.append(f"Last action: {last_action}")
    
    last_success = state.get('last_action_success')
    if last_success is not None:
        lines.append(f"Last action success: {last_success}")
    
    # Add referee hints
    oscillation_hint = state.get('oscillation_hint')
    if oscillation_hint:
        lines.append(oscillation_hint)
    
    arm_clamping_hint = state.get('arm_clamping_hint')
    if arm_clamping_hint:
        lines.append(arm_clamping_hint)
    
    repeated_grasp_hint = state.get('repeated_grasp_hint')
    if repeated_grasp_hint:
        lines.append(repeated_grasp_hint)
    
    prolonged_search_hint = state.get('prolonged_search_hint')
    if prolonged_search_hint:
        lines.append(prolonged_search_hint)
    
    if state.get('post_grasp_check_needed'):
        lines.append("⚠️ REFEREE HINT: Post-grasp visual check needed. Move arm to bring gripper into view and confirm grasp.")
    
    return "\n".join(lines)


def get_tool_descriptions() -> list:
    """Get tool descriptions for Gemini function calling."""
    return [
        {
            "name": "base_step",
            "description": "Move base for a short duration (0.2-0.5s), then automatically stop. IMPORTANT: Choose duration based on situation - use shorter durations (0.2-0.3s) for fine adjustments when target is close/centered, longer durations (0.4-0.5s) for searching or initial approach. Always rely on camera feedback after each step.",
            "parameters": {
                "type": "object",
                "properties": {
                    "velocity": {
                        "type": "number",
                        "description": "Velocity in mm/s (0-200)",
                        "minimum": 0,
                        "maximum": 200
                    },
                    "direction": {
                        "type": "number",
                        "description": "Direction angle in degrees (0-360), 0=forward, 90=right, 180=backward, 270=left. CRITICAL: If you've been strafing in the same direction (e.g., direction=90) multiple times without the target moving toward center, try the opposite direction (270) or switch to arm movement.",
                        "minimum": 0,
                        "maximum": 360
                    },
                    "angular_rate": {
                        "type": "number",
                        "description": "Angular velocity in deg/s (-50 to 50), positive=CCW. CRITICAL: If you've been alternating between positive and negative values (oscillating), reduce the magnitude (e.g., use 5 instead of 10) for finer control. For fine centering adjustments, use small values (5-10 deg/s) with short duration (0.2s).",
                        "minimum": -50,
                        "maximum": 50
                    },
                    "duration": {
                        "type": "number",
                        "description": "Movement duration in seconds (0.2-0.5). CRITICAL: Choose duration based on precision needed: 0.2-0.3s for fine adjustments (target close/centered, small corrections), 0.4-0.5s for larger movements (searching, initial approach). Smaller duration = more precise control, prevents overshooting.",
                        "minimum": 0.2,
                        "maximum": 0.5
                    }
                },
                "required": ["velocity", "direction", "angular_rate", "duration"]
            }
        },
        {
            "name": "arm_move_xyz",
            "description": "Move end effector to target XYZ using IK. Returns reachability. Use small increments for visual servoing. CRITICAL: Workspace limits are X=[-10, 10] cm, Y=[5, 15] cm, Z=[0, 25] cm. Coordinates outside these limits will be clamped. If you repeatedly request out-of-range coordinates, the referee will warn you - use base movement to reposition the robot instead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {
                        "type": "number",
                        "description": "X coordinate in cm (-10 to 10)",
                        "minimum": -10,
                        "maximum": 10
                    },
                    "y": {
                        "type": "number",
                        "description": "Y coordinate in cm (5 to 15)",
                        "minimum": 5,
                        "maximum": 15
                    },
                    "z": {
                        "type": "number",
                        "description": "Z coordinate in cm (0 to 25)",
                        "minimum": 0,
                        "maximum": 25
                    },
                    "pitch": {
                        "type": "number",
                        "description": "Pitch angle in degrees (default: 0)",
                        "default": 0
                    },
                    "roll": {
                        "type": "number",
                        "description": "Roll angle in degrees (default: -90)",
                        "default": -90
                    },
                    "yaw": {
                        "type": "number",
                        "description": "Yaw angle in degrees (default: 90)",
                        "default": 90
                    },
                    "speed": {
                        "type": "integer",
                        "description": "Movement speed in ms (500-3000, default: 1500)",
                        "minimum": 500,
                        "maximum": 3000,
                        "default": 1500
                    }
                },
                "required": ["x", "y", "z"]
            }
        },
        {
            "name": "arm_to_safe_pose",
            "description": "Move arm to safe pre-grasp position (above workspace).",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        },
        {
            "name": "gripper_open",
            "description": "Open gripper.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        },
        {
            "name": "gripper_close",
            "description": "Close gripper.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    ]

