"""
Gemini Robotics-ER 1.5 policy for high-level planning.

Uses Google Gemini Robotics-ER API for task planning and tool selection.
"""

import os
import base64
from typing import Dict, Any, Optional
import google.generativeai as genai
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
        
        # Configure Gemini
        genai.configure(api_key=api_key)
        
        # Initialize model (Robotics-ER 1.5)
        # Note: Update model name when Robotics-ER 1.5 is available
        # For now, using a standard Gemini model with function calling
        # Check: https://ai.google.dev/gemini-api/docs/models/gemini-robotics-er-1.5
        try:
            # Try Robotics-ER model first
            self.model = genai.GenerativeModel(
                model_name="gemini-robotics-er-1.5",  # Update when available
                tools=get_tool_descriptions()
            )
        except:
            # Fallback to standard model with function calling
            self.model = genai.GenerativeModel(
                model_name="gemini-2.0-flash-exp",
                tools=get_tool_descriptions()
            )
        
        # Conversation history
        self.conversation_history = []
        
        # Initialize with system prompt
        self.conversation_history.append({
            "role": "user",
            "parts": [get_system_prompt()]
        })
    
    def _image_to_base64(self, image: np.ndarray) -> str:
        """Convert numpy image to base64 string."""
        # Convert BGR to RGB if needed
        if len(image.shape) == 3 and image.shape[2] == 3:
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        else:
            image_rgb = image
        
        # Convert to PIL Image
        pil_image = Image.fromarray(image_rgb)
        
        # Convert to base64
        buffer = io.BytesIO()
        pil_image.save(buffer, format="JPEG")
        image_bytes = buffer.getvalue()
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        
        return image_base64
    
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
        
        # Prepare user message
        user_parts = [state_text]
        
        # Add image if available
        if image is not None:
            try:
                image_base64 = self._image_to_base64(image)
                user_parts.append({
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": image_base64
                    }
                })
            except Exception as e:
                print(f"Warning: Failed to encode image: {e}")
        
        # Add to conversation
        self.conversation_history.append({
            "role": "user",
            "parts": user_parts
        })
        
        try:
            # Generate response
            response = self.model.generate_content(
                self.conversation_history,
                generation_config={
                    "temperature": 0.3,  # Lower temperature for more deterministic behavior
                }
            )
            
            # Add response to history
            self.conversation_history.append({
                "role": "model",
                "parts": [response.text]
            })
            
            # Parse function call from response
            # Gemini may return function calls in the response
            if hasattr(response, 'function_calls') and response.function_calls:
                func_call = response.function_calls[0]
                action_name = func_call.name
                params = func_call.args if hasattr(func_call, 'args') else {}
                
                return {
                    "action": action_name,
                    "params": params,
                    "phase": state_summary.get("phase", "unknown"),
                    "why": response.text or f"Gemini selected {action_name}"
                }
            else:
                # Try to parse action from text response
                # Fallback: return a safe action
                return {
                    "action": "base_stop",
                    "params": {},
                    "phase": state_summary.get("phase", "unknown"),
                    "why": f"Gemini response: {response.text[:100]}"
                }
        
        except Exception as e:
            print(f"Gemini API error: {e}")
            # Fallback to safe action
            return {
                "action": "base_stop",
                "params": {},
                "phase": state_summary.get("phase", "unknown"),
                "why": f"Error: {str(e)}"
            }
    
    def reset(self):
        """Reset conversation history."""
        self.conversation_history = [{
            "role": "user",
            "parts": [get_system_prompt()]
        }]

