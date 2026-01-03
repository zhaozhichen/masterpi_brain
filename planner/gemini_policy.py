"""
Gemini Robotics-ER 1.5 policy for high-level planning.

Uses Google GenAI API for task planning and tool selection.
"""

import os
from typing import Dict, Any, Optional
from google import genai
from PIL import Image
import io
import numpy as np
import cv2
from dotenv import load_dotenv

from planner.prompts import get_system_prompt, format_state_summary, get_tool_descriptions

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
        
        # Model name (Robotics-ER 1.5 when available)
        # Check: https://ai.google.dev/gemini-api/docs/models/gemini-robotics-er-1.5
        # For now, using a standard Gemini model
        self.model_name = "gemini-3-pro-preview"
        # self.model_name = "gemini-3-flash-preview"
        
        # System prompt
        self.system_prompt = get_system_prompt()
        
        # Conversation history
        self.messages = []
        
        # Image size (for compatibility with executor)
        self.image_center = None
        
        # Phase (for compatibility with executor)
        # Gemini policy doesn't use explicit phases, but we track it for logging
        self.phase = "PLANNING"  # Simple string for compatibility
    
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
        # Format state summary
        state_text = format_state_summary(state_summary)
        
        # Add last action result if available
        if last_action_result:
            state_text += f"\nLast action result: {last_action_result}"
        
        # Build prompt with system instruction
        prompt = f"{self.system_prompt}\n\n{state_text}"
        
        # Prepare contents - start with text
        contents = [prompt]
        
        # Add image if available
        if image is not None:
            try:
                image_bytes = self._image_to_bytes(image)
                # Add image as Part using types
                from google.genai import types
                contents.append(types.Part.from_bytes(
                    data=image_bytes,
                    mime_type="image/jpeg"
                ))
            except Exception as e:
                print(f"Warning: Failed to encode image: {e}")
        
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
            
            # Build config - try without tools first to test
            config = types.GenerateContentConfig(
                temperature=0.3,
                tools=tools if function_declarations else None
            )
            
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
                
                return {
                    "action": action_name,
                    "params": params,
                    "phase": state_summary.get("phase", "unknown"),
                    "why": response_text or f"Gemini selected {action_name}"
                }
            
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
