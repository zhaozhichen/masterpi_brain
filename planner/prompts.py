"""
System prompts and templates for Gemini Robotics-ER integration.
"""

from typing import Dict, Any


def get_system_prompt(task_description: str = None) -> str:
    """
    Get system prompt for Gemini Robotics-ER.
    
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
4. If target is not visible → use scan/search actions.
5. If action fails → try recovery (backtrack, adjust, or restart search).
6. Never output continuous long-duration movements. Always use discrete steps.
7. You must identify targets from the camera image yourself - use visual understanding to locate objects described in the task. The detection results provided are optional hints, but you should rely primarily on your own visual analysis of the image.

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
    if detection.get('found'):
        lines.append(f"Target detected: center={detection.get('center')}, "
                    f"area_ratio={detection.get('area_ratio', 0):.4f}, "
                    f"confidence={detection.get('confidence', 0):.2f}")
    else:
        lines.append("Target not detected")
    
    last_action = state.get('last_action')
    if last_action:
        lines.append(f"Last action: {last_action}")
    
    last_success = state.get('last_action_success')
    if last_success is not None:
        lines.append(f"Last action success: {last_success}")
    
    return "\n".join(lines)


def get_tool_descriptions() -> list:
    """Get tool descriptions for Gemini function calling."""
    return [
        {
            "name": "base_step",
            "description": "Move base for a short duration (0.2-0.5s), then automatically stop. Use small durations only; rely on camera feedback after each step.",
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
                        "description": "Direction angle in degrees (0-360), 0=forward",
                        "minimum": 0,
                        "maximum": 360
                    },
                    "angular_rate": {
                        "type": "number",
                        "description": "Angular velocity in deg/s (-50 to 50), positive=CCW",
                        "minimum": -50,
                        "maximum": 50
                    },
                    "duration": {
                        "type": "number",
                        "description": "Movement duration in seconds (0.2-0.5)",
                        "minimum": 0.2,
                        "maximum": 0.5
                    }
                },
                "required": ["velocity", "direction", "angular_rate", "duration"]
            }
        },
        {
            "name": "arm_move_xyz",
            "description": "Move end effector to target XYZ using IK. Returns reachability. Use small increments for visual servoing.",
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

