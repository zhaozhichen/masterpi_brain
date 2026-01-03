"""
Gemini Robotics-ER 1.5 policy for high-level planning.

Uses Google GenAI API for task planning and tool selection.
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from google import genai
from PIL import Image
import io
import numpy as np
import cv2
from dotenv import load_dotenv

from planner.prompts import get_system_prompt, format_state_summary, get_tool_descriptions

# Set up logger for Gemini API calls
gemini_logger = logging.getLogger("gemini_api")
gemini_logger.setLevel(logging.DEBUG)

# Load environment variables from .env file
load_dotenv()


class GeminiPolicy:
    """Gemini Robotics-ER 1.5 policy for robot control."""
    
    def __init__(self, thresholds_path: str = "config/thresholds.yaml"):
        """
        Initialize Gemini policy.
        
        Args:
            thresholds_path: Path to thresholds configuration
        """
        # Get API key
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")
        
        # Initialize GenAI client with increased timeout
        from google.genai import types as genai_types
        self.client = genai.Client(
            api_key=api_key,
            http_options=genai_types.HttpOptions(timeout=60.0)  # 60 second timeout
        )
        
        # Model name: Gemini Robotics-ER 1.5
        # Check: https://ai.google.dev/gemini-api/docs/models/gemini-robotics-er-1.5
        # self.model_name = "gemini-3-pro-preview"
        # self.model_name = "gemini-3-flash-preview"
        self.model_name = "gemini-robotics-er-1.5"
        
        # System prompt (will be updated with task description in plan method)
        self.base_system_prompt = get_system_prompt()
        self.system_prompt = self.base_system_prompt
        self.current_task = None
        
        # Conversation history
        self.messages = []
        
        # Image size (for compatibility with executor)
        self.image_center = None
        
        # Phase (for compatibility with executor)
        # Gemini policy doesn't use explicit phases, but we track it for logging
        self.phase = "PLANNING"  # Simple string for compatibility
        
        # Log directory for detailed prompts
        self.log_dir = Path("logs")
        self.current_log_dir = None
    
    def set_image_size(self, width: int, height: int):
        """Set image dimensions (for compatibility with executor)."""
        self.image_center = (width // 2, height // 2)
    
    def _image_to_bytes(self, image: np.ndarray) -> bytes:
        """Convert numpy image to bytes."""
        # Convert BGR to RGB if needed
        if len(image.shape) == 3 and image.shape[2] == 3:
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        else:
            image_rgb = image
        
        # Convert to PIL Image
        pil_image = Image.fromarray(image_rgb)
        
        # Convert to bytes
        buffer = io.BytesIO()
        pil_image.save(buffer, format="JPEG")
        return buffer.getvalue()
    
    def plan(self, 
             image: Optional[np.ndarray],
             detection: Dict[str, Any],
             state_summary: Dict[str, Any],
             last_action_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Plan next action using Gemini.
        
        Args:
            image: Current camera frame
            detection: Detection results
            state_summary: Current state summary
            last_action_result: Result from last action
        
        Returns:
            Action plan dict with "action", "params", "phase", "why"
        """
        # Update current task if provided
        task_desc = state_summary.get('task', '')
        if task_desc and task_desc != self.current_task:
            self.current_task = task_desc
            # Update system prompt with task description
            self.system_prompt = get_system_prompt(task_description=task_desc)
        
        # Format state summary
        state_text = format_state_summary(state_summary)
        
        # Add last action result if available
        if last_action_result:
            state_text += f"\nLast action result: {last_action_result}"
        
        # Build prompt with system instruction (includes task description)
        prompt = f"{self.system_prompt}\n\n{state_text}"
        
        # Prepare contents - start with text
        contents = [prompt]
        
        # Track image info for logging
        image_info = None
        if image is not None:
            try:
                image_bytes = self._image_to_bytes(image)
                image_info = {
                    "has_image": True,
                    "image_size_bytes": len(image_bytes),
                    "image_shape": list(image.shape) if hasattr(image, 'shape') else None
                }
                # Add image as Part using types
                from google.genai import types
                contents.append(types.Part.from_bytes(
                    data=image_bytes,
                    mime_type="image/jpeg"
                ))
            except Exception as e:
                print(f"Warning: Failed to encode image: {e}")
                image_info = {"has_image": False, "error": str(e)}
        else:
            image_info = {"has_image": False}
        
        try:
            # Generate response using new API
            from google.genai import types
            
            # Convert tool descriptions to FunctionDeclarations
            tool_descs = get_tool_descriptions()
            function_declarations = []
            for tool_desc in tool_descs:
                # Convert parameters dict to Schema using parametersJsonSchema
                params_dict = tool_desc["parameters"]
                func_decl = types.FunctionDeclaration(
                    name=tool_desc["name"],
                    description=tool_desc["description"],
                    parametersJsonSchema=params_dict
                )
                function_declarations.append(func_decl)
            
            # Create Tool with functionDeclarations
            tools = [types.Tool(functionDeclarations=function_declarations)]
            
            # Build config
            config = types.GenerateContentConfig(
                temperature=0.3,
                tools=tools if function_declarations else None
            )
            
            # Prepare detailed prompt log
            prompt_log = {
                "model": self.model_name,
                "system_prompt": self.system_prompt,
                "state_summary": state_text,
                "full_prompt": prompt,
                "image_info": image_info,
                "tools": [
                    {
                        "name": tool_desc["name"],
                        "description": tool_desc["description"],
                        "parameters": tool_desc["parameters"]
                    }
                    for tool_desc in tool_descs
                ],
                "config": {
                    "temperature": 0.3,
                    "has_tools": len(function_declarations) > 0,
                    "num_tools": len(function_declarations)
                },
                "iteration": state_summary.get("iteration", 0),
                "task": state_summary.get("task", "unknown")
            }
            
            # Log prompt to file
            self._log_prompt(prompt_log)
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config
            )
            
            # Extract response text and function calls
            response_text = ""
            function_call = None
            
            # Check for function calls directly in response
            if hasattr(response, 'function_calls') and response.function_calls:
                function_call = response.function_calls[0]
            
            # Also check in candidates (fallback)
            if not function_call and hasattr(response, 'candidates') and len(response.candidates) > 0:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and candidate.content:
                    parts = candidate.content.parts
                    for part in parts:
                        # Extract text
                        if hasattr(part, 'text') and part.text:
                            response_text += part.text
                        # Extract function call
                        if hasattr(part, 'function_call') and part.function_call:
                            function_call = part.function_call
            
            # Log response
            response_log = {
                "has_function_call": function_call is not None,
                "response_text": response_text,
                "function_call": None
            }
            
            # If we have a function call, use it
            if function_call:
                action_name = function_call.name
                # Extract parameters
                params = {}
                if hasattr(function_call, 'args') and function_call.args:
                    # Convert args to dict
                    if isinstance(function_call.args, dict):
                        params = function_call.args
                    elif hasattr(function_call.args, '__dict__'):
                        params = dict(function_call.args)
                    else:
                        # Try to convert protobuf message to dict
                        try:
                            params = {k: v for k, v in function_call.args.items()}
                        except:
                            params = {}
                
                response_log["function_call"] = {
                    "name": action_name,
                    "params": params
                }
                
                # Log response
                self._log_response(response_log, state_summary.get("iteration", 0))
                
                return {
                    "action": action_name,
                    "params": params,
                    "phase": state_summary.get("phase", "unknown"),
                    "why": response_text or f"Gemini selected {action_name}"
                }
            
            # Log response even if no function call
            self._log_response(response_log, state_summary.get("iteration", 0))
            
            # No function call found, return safe action with response text
            return {
                "action": "base_stop",
                "params": {},
                "phase": state_summary.get("phase", "unknown"),
                "why": f"Gemini response: {response_text[:200] if response_text else 'No response'}"
            }
        
        except Exception as e:
            error_msg = str(e)
            # Don't print full traceback for timeout errors (too verbose)
            if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                print(f"GenAI API timeout (this may be due to network issues)")
            else:
                print(f"GenAI API error: {e}")
                import traceback
                traceback.print_exc()
            
            # Fallback: use simple heuristic based on detection
            # If target found but small, approach; if large, use arm; if not found, search
            if detection.get('found'):
                area_ratio = detection.get('area_ratio', 0.0)
                if area_ratio < 0.05:
                    # Target far, approach
                    return {
                        "action": "base_step",
                        "params": {
                            "velocity": 50.0,
                            "direction": 0.0,
                            "angular_rate": 0.0,
                            "duration": 0.3
                        },
                        "phase": state_summary.get("phase", "unknown"),
                        "why": f"API timeout fallback: approaching target (area={area_ratio:.4f})"
                    }
                else:
                    # Target close, use arm
                    return {
                        "action": "arm_to_safe_pose",
                        "params": {},
                        "phase": state_summary.get("phase", "unknown"),
                        "why": f"API timeout fallback: target close (area={area_ratio:.4f}), moving arm"
                    }
            else:
                # Target not found, search
                return {
                    "action": "base_step",
                    "params": {
                        "velocity": 0.0,
                        "direction": 0.0,
                        "angular_rate": 15.0,  # Rotate
                        "duration": 0.3
                    },
                    "phase": state_summary.get("phase", "unknown"),
                    "why": "API timeout fallback: target not found, searching"
                }
    
    def reset(self):
        """Reset conversation history."""
        self.messages = []
        self.current_task = None
        self.system_prompt = self.base_system_prompt
        self.current_log_dir = None
    
    def set_log_dir(self, log_dir: Path):
        """Set log directory for prompt logging."""
        self.current_log_dir = log_dir
        if log_dir:
            (log_dir / "gemini_prompts").mkdir(parents=True, exist_ok=True)
    
    def _log_prompt(self, prompt_log: Dict[str, Any]):
        """Log detailed prompt to file."""
        if not self.current_log_dir:
            return
        
        prompt_dir = self.current_log_dir / "gemini_prompts"
        prompt_dir.mkdir(exist_ok=True)
        
        iteration = prompt_log.get("iteration", 0)
        prompt_file = prompt_dir / f"prompt_{iteration:05d}.json"
        
        try:
            with open(prompt_file, 'w', encoding='utf-8') as f:
                json.dump(prompt_log, f, indent=2, ensure_ascii=False, default=str)
            print(f"Gemini prompt logged: {prompt_file}")
        except Exception as e:
            print(f"Warning: Failed to log prompt: {e}")
    
    def _log_response(self, response_log: Dict[str, Any], iteration: int):
        """Log response to file."""
        if not self.current_log_dir:
            return
        
        prompt_dir = self.current_log_dir / "gemini_prompts"
        prompt_dir.mkdir(exist_ok=True)
        
        response_file = prompt_dir / f"response_{iteration:05d}.json"
        
        try:
            with open(response_file, 'w', encoding='utf-8') as f:
                json.dump(response_log, f, indent=2, ensure_ascii=False, default=str)
            print(f"Gemini response logged: {response_file}")
        except Exception as e:
            print(f"Warning: Failed to log response: {e}")
