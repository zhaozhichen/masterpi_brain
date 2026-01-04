"""
Task completion detector using Gemini 3 Flash Preview.

Uses a lightweight model to quickly determine if the current task has been completed.
"""

import os
from typing import Dict, Any, Optional
from google import genai
from PIL import Image
import io
import numpy as np
import cv2
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class TaskDetector:
    """Detects task completion using Gemini 3 Flash Preview."""
    
    def __init__(self):
        """Initialize task detector with Gemini 3 Flash."""
        # Get API key
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")
        
        # Initialize GenAI client
        from google.genai import types as genai_types
        self.client = genai.Client(
            api_key=api_key,
            http_options=genai_types.HttpOptions(timeout=120000)  # 120 seconds = 120000 milliseconds
        )
        
        # Model: Gemini 3 Flash Preview (fast and cheap for detection)
        self.model_name = "gemini-3-flash-preview"
    
    def _image_to_bytes(self, image: np.ndarray) -> bytes:
        """Convert numpy image to JPEG bytes."""
        # Convert BGR to RGB
        if len(image.shape) == 3 and image.shape[2] == 3:
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        else:
            image_rgb = image
        
        # Convert to PIL Image
        pil_image = Image.fromarray(image_rgb)
        
        # Convert to JPEG bytes
        buffer = io.BytesIO()
        pil_image.save(buffer, format="JPEG", quality=85)
        return buffer.getvalue()
    
    def check_completion(self, 
                        image: np.ndarray,
                        task_description: str,
                        last_action: Optional[str] = None) -> Dict[str, Any]:
        """
        Check if the current task has been completed.
        
        Args:
            image: Current camera frame
            task_description: The task to check (e.g., "pick up red block")
            last_action: Last action taken (optional, for context)
        
        Returns:
            {
                "completed": bool,
                "confidence": float (0.0-1.0),
                "reason": str,
                "evidence": str
            }
        """
        try:
            from google.genai import types
            
            # Build prompt for task completion check
            prompt = f"""You are a task completion checker for a robot.

Current task: {task_description}

Last action: {last_action if last_action else "None"}

Look at the image and determine if the task has been completed. 

Return your answer in this exact JSON format:
{{
    "completed": true or false,
    "confidence": 0.0 to 1.0,
    "reason": "brief explanation",
    "evidence": "what you see in the image that supports your conclusion"
}}

Be strict - the task is only completed if it is clearly and fully done. If uncertain, return completed=false."""
            
            # Prepare contents
            parts = [types.Part.from_text(text=prompt)]
            
            # Add image
            try:
                image_bytes = self._image_to_bytes(image)
                parts.append(types.Part.from_bytes(
                    data=image_bytes,
                    mime_type="image/jpeg"
                ))
            except Exception as e:
                return {
                    "completed": False,
                    "confidence": 0.0,
                    "reason": f"Failed to encode image: {e}",
                    "evidence": ""
                }
            
            contents = [types.Content(parts=parts)]
            
            # Build config
            config = types.GenerateContentConfig(
                temperature=0.1,  # Low temperature for consistent detection
                responseMimeType="application/json",  # Request JSON response
                httpOptions=genai_types.HttpOptions(timeout=120000)  # 120 seconds = 120000 milliseconds
            )
            
            # Call API
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config
            )
            
            # Parse response
            response_text = ""
            if hasattr(response, 'text'):
                response_text = response.text
            elif hasattr(response, 'candidates') and len(response.candidates) > 0:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and candidate.content:
                    parts = candidate.content.parts
                    for part in parts:
                        if hasattr(part, 'text') and part.text:
                            response_text += part.text
            
            # Parse JSON response
            import json
            try:
                # Extract JSON from response (might have markdown code blocks)
                response_text = response_text.strip()
                if response_text.startswith("```json"):
                    response_text = response_text[7:]
                if response_text.startswith("```"):
                    response_text = response_text[3:]
                if response_text.endswith("```"):
                    response_text = response_text[:-3]
                response_text = response_text.strip()
                
                result = json.loads(response_text)
                
                return {
                    "completed": result.get("completed", False),
                    "confidence": float(result.get("confidence", 0.0)),
                    "reason": result.get("reason", ""),
                    "evidence": result.get("evidence", "")
                }
            except json.JSONDecodeError as e:
                # Fallback: try to extract completion status from text
                completed = "completed" in response_text.lower() and "true" in response_text.lower()
                return {
                    "completed": completed,
                    "confidence": 0.5,
                    "reason": f"Failed to parse JSON: {e}",
                    "evidence": response_text[:200]
                }
        
        except Exception as e:
            # On error, assume not completed
            return {
                "completed": False,
                "confidence": 0.0,
                "reason": f"Detection error: {e}",
                "evidence": ""
            }

