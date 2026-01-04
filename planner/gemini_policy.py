"""
Gemini Robotics-ER 1.5 policy for high-level planning.

Uses Google GenAI API (gemini-robotics-er-1.5-preview) for task planning, multi-step reasoning, and tool selection.
Task completion detection uses gemini-3-flash-preview (separate detector).
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
    """Gemini Robotics-ER 1.5 policy for robot control with high-level planning."""
    
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
            http_options=genai_types.HttpOptions(timeout=120000)  # 120 seconds = 120000 milliseconds
        )
        
        # Model name: Gemini Robotics-ER 1.5 Preview
        # Using gemini-robotics-er-1.5-preview for planning (task decomposition, multi-step planning)
        # Task completion detection uses gemini-3-flash-preview (faster, cheaper)
        # Check: https://ai.google.dev/gemini-api/docs/models/gemini-robotics-er-1.5
        self.model_name = "gemini-robotics-er-1.5-preview"
        # self.model_name = "gemini-3-flash-preview"
        # self.model_name = "gemini-3-pro-preview"
        
        # System prompt (will be updated with task description in plan method)
        self.base_system_prompt = get_system_prompt()
        self.system_prompt = self.base_system_prompt
        self.current_task = None
        
        # Conversation history
        self.messages = []
        
        # Maximum number of messages to keep in history (to prevent token quota exhaustion)
        # Each message pair (user + model) = 1 interaction
        # 10 messages = 5 interactions
        self.max_history_messages = 10
        
        # Image compression settings for history (to reduce token usage)
        # Current images use full resolution, history images are compressed
        self.history_image_max_size = (320, 240)  # (width, height) for history images
        self.history_image_quality = 70  # JPEG quality (0-100) for history images
        
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
    
    def _image_to_bytes(self, image: np.ndarray, compress: bool = False) -> bytes:
        """
        Convert numpy image to bytes.
        
        Args:
            image: Input image as numpy array
            compress: If True, compress image for history (lower resolution and quality)
                     If False, use full resolution for current observation
        """
        # Convert BGR to RGB if needed
        if len(image.shape) == 3 and image.shape[2] == 3:
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        else:
            image_rgb = image
        
        # Convert to PIL Image
        pil_image = Image.fromarray(image_rgb)
        
        # Compress if requested (for history)
        if compress:
            # Resize to reduce token usage
            pil_image.thumbnail(self.history_image_max_size, Image.Resampling.LANCZOS)
        
        # Convert to bytes
        buffer = io.BytesIO()
        if compress:
            # Use lower quality for history images
            pil_image.save(buffer, format="JPEG", quality=self.history_image_quality, optimize=True)
        else:
            # Full quality for current images
            pil_image.save(buffer, format="JPEG", quality=95)
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
        
        # Build conversation history context
        # Include previous observations, plans, actions, and results
        history_context = self._build_history_context(state_summary, last_action_result)
        
        # Combine history context with current state
        if history_context:
            user_message = f"{history_context}\n\n--- Current State ---\n{state_text}"
        else:
            user_message = state_text
        
        # Format state summary (system prompt will be in config, not in prompt)
        # Prepare contents using Content object with parts
        from google.genai import types
        
        # Build parts list with state summary (system prompt goes to config)
        parts = [types.Part.from_text(text=user_message)]
        
        # Track image info for logging
        image_info = None
        if image is not None:
            try:
                image_bytes = self._image_to_bytes(image, compress=False)  # Full resolution for current
                image_shape = list(image.shape) if hasattr(image, 'shape') else None
                image_info = {
                    "has_image": True,
                    "image_size_bytes": len(image_bytes),
                    "image_shape": image_shape
                }
                # Print resolution info (first time only or when it changes)
                if not hasattr(self, '_last_image_shape') or self._last_image_shape != image_shape:
                    if image_shape and len(image_shape) >= 2:
                        height, width = image_shape[0], image_shape[1]
                        print(f"  → Full resolution: {width}x{height} (current image, quality=95)")
                    self._last_image_shape = image_shape
                # Add image as Part
                parts.append(types.Part.from_bytes(
                    data=image_bytes,
                    mime_type="image/jpeg"
                ))
            except Exception as e:
                print(f"Warning: Failed to encode image: {e}")
                image_info = {"has_image": False, "error": str(e)}
        else:
            image_info = {"has_image": False}
        
        # Build conversation history: include previous messages + current message
        # This allows Gemini to understand the full context of the task execution
        # IMPORTANT: History messages contain COMPRESSED images (320x240, quality=70)
        #            Current message contains FULL RESOLUTION image (original size, quality=95)
        #            This reduces token usage while maintaining accuracy for current observation
        all_contents = []
        
        # Add previous conversation history (if any)
        # Note: History is already limited to max_history_messages in _update_conversation_history
        # History images are compressed (compress=True) to save tokens
        if self.messages:
            all_contents.extend(self.messages)
        
        # Add current message with FULL RESOLUTION image
        # Current image uses compress=False (full resolution) for maximum accuracy
        current_content = types.Content(parts=parts)
        all_contents.append(current_content)
        
        # Use all contents (history + current) for the API call
        contents = all_contents
        
        try:
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
            
            # Build config with system instruction
            config = types.GenerateContentConfig(
                temperature=0.3,
                systemInstruction=self.system_prompt,  # System prompt in config
                tools=tools if function_declarations else None,
                httpOptions=types.HttpOptions(timeout=120000)  # 120 seconds = 120000 milliseconds
            )
            
            # Prepare detailed prompt log
            full_prompt = f"{self.system_prompt}\n\n{user_message}"  # Combined for logging (includes history)
            prompt_log = {
                "model": self.model_name,
                "system_prompt": self.system_prompt,
                "state_summary": state_text,
                "history_context": history_context if history_context else None,
                "full_prompt": full_prompt,
                "num_history_messages": len(self.messages),
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
            
            # Extract response text (thinking process) and function calls
            # IMPORTANT: Extract ALL text parts first, then function calls
            # This ensures we capture the full reasoning process
            response_text = ""
            function_call = None
            
            # Method 1: Check candidates (most common path)
            if hasattr(response, 'candidates') and len(response.candidates) > 0:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and candidate.content:
                    parts = candidate.content.parts
                    # Process all parts to extract both text and function calls
                    for part in parts:
                        # Extract text (thinking process) - collect ALL text
                        if hasattr(part, 'text') and part.text:
                            if response_text:
                                response_text += "\n" + part.text
                            else:
                                response_text = part.text
                        # Extract function call (only the last one if multiple)
                        if hasattr(part, 'function_call') and part.function_call:
                            function_call = part.function_call
            
            # Method 2: Check for function calls directly in response (fallback)
            if not function_call and hasattr(response, 'function_calls') and response.function_calls:
                function_call = response.function_calls[0]
            
            # Method 3: Try to get text from response directly (additional fallback)
            if not response_text and hasattr(response, 'text') and response.text:
                response_text = response.text
            
            # Log response with thinking process
            # response_text contains the reasoning/thinking process
            # function_call contains the actual action to execute
            response_log = {
                "has_function_call": function_call is not None,
                "thinking_process": response_text if response_text else None,  # Reasoning/thinking process
                "response_text": response_text,  # Keep for backward compatibility
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
                
                # Build action plan
                # "why" and "thinking_process" fields contain the thinking process for debugging
                # Only the function call (action + params) will be executed
                action_plan = {
                    "action": action_name,  # Only this is executed
                    "params": params,  # Only this is executed
                    "phase": state_summary.get("phase", "unknown"),
                    "why": response_text or f"Gemini selected {action_name}",  # Thinking process for debugging
                    "thinking_process": response_text  # Explicit field for thinking process
                }
                
                # Update conversation history with current interaction
                self._update_conversation_history(
                    user_message=user_message,
                    image=image,
                    response_text=response_text,
                    function_call=function_call,
                    action_plan=action_plan,
                    action_result=last_action_result
                )
                
                return action_plan
            
            # Log response even if no function call
            self._log_response(response_log, state_summary.get("iteration", 0))
            
            # Try to parse function call from text if no actual function_call was returned
            # Sometimes Gemini describes the function call in text instead of using function calling
            parsed_action = None
            parsed_params = {}
            
            if response_text and not function_call:
                parsed_action, parsed_params = self._parse_function_call_from_text(response_text)
            
            if parsed_action:
                # Found function call in text, use it
                print(f"⚠️  Warning: Function call parsed from text (Gemini didn't use function calling): {parsed_action}")
                action_plan = {
                    "action": parsed_action,
                    "params": parsed_params,
                    "phase": state_summary.get("phase", "unknown"),
                    "why": response_text,
                    "thinking_process": response_text
                }
                
                # Update response log
                response_log["function_call"] = {
                    "name": parsed_action,
                    "params": parsed_params,
                    "parsed_from_text": True  # Flag to indicate this was parsed from text
                }
                self._log_response(response_log, state_summary.get("iteration", 0))
                
                # Update conversation history
                self._update_conversation_history(
                    user_message=user_message,
                    image=image,
                    response_text=response_text,
                    function_call=None,  # No actual function_call object
                    action_plan=action_plan,
                    action_result=last_action_result
                )
                
                return action_plan
            
            # No function call found (neither actual nor parsed from text)
            # First, try to parse function call from text
            parsed_action = None
            parsed_params = {}
            
            if response_text and not function_call:
                parsed_action, parsed_params = self._parse_function_call_from_text(response_text)
            
            if parsed_action:
                # Found function call in text, use it
                print(f"⚠️  Warning: Function call parsed from text (Gemini didn't use function calling): {parsed_action}")
                action_plan = {
                    "action": parsed_action,
                    "params": parsed_params,
                    "phase": state_summary.get("phase", "unknown"),
                    "why": response_text,
                    "thinking_process": response_text
                }
                
                # Update response log
                response_log["function_call"] = {
                    "name": parsed_action,
                    "params": parsed_params,
                    "parsed_from_text": True  # Flag to indicate this was parsed from text
                }
                self._log_response(response_log, state_summary.get("iteration", 0))
                
                # Update conversation history
                self._update_conversation_history(
                    user_message=user_message,
                    image=image,
                    response_text=response_text,
                    function_call=None,  # No actual function_call object
                    action_plan=action_plan,
                    action_result=last_action_result
                )
                
                return action_plan
            
            # No function call found - check if Gemini declared task completion
            # Check both response_text and thinking_process for completion keywords
            completion_text = response_text or ""
            # Also check thinking_process if available in response_log
            if response_log.get("thinking_process"):
                completion_text += " " + response_log["thinking_process"]
            
            if completion_text:
                completion_keywords = [
                    "task is complete", "task complete", "successfully completed",
                    "successfully grasped", "task \"", "mission accomplished",
                    "completed the task", "finished the task", "task has been completed",
                    "successfully picked up", "successfully grabbed"
                ]
                completion_lower = completion_text.lower()
                if any(keyword in completion_lower for keyword in completion_keywords):
                    # Gemini declared completion - return special action to signal completion
                    print(f"✓ Gemini declared task completion: {completion_text[:100]}...")
                    action_plan = {
                        "action": "task_complete",  # Special action to signal completion
                        "params": {},
                        "phase": "COMPLETE",
                        "why": response_text or completion_text,
                        "thinking_process": response_text or completion_text
                    }
                    
                    # Update response log
                    response_log["task_complete"] = True
                    self._log_response(response_log, state_summary.get("iteration", 0))
                    
                    # Update conversation history
                    self._update_conversation_history(
                        user_message=user_message,
                        image=image,
                        response_text=response_text,
                        function_call=None,
                        action_plan=action_plan,
                        action_result=last_action_result
                    )
                    
                    return action_plan
            
            # No function call and no completion declaration - return safe fallback action
            action_plan = {
                "action": "base_stop",  # Safe fallback action
                "params": {},
                "phase": state_summary.get("phase", "unknown"),
                "why": f"Gemini response: {response_text[:200] if response_text else 'No response'}",
                "thinking_process": response_text  # Full thinking process for debugging
            }
            
            # Update conversation history with current interaction
            self._update_conversation_history(
                user_message=user_message,
                image=image,
                response_text=response_text,
                function_call=None,
                action_plan=action_plan,
                action_result=last_action_result
            )
            
            return action_plan
        
        except Exception as e:
            error_msg = str(e)
            error_str = str(e)
            
            # Handle 429 RESOURCE_EXHAUSTED (quota exceeded) with retry
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "quota" in error_str.lower():
                print(f"⚠️  API quota exceeded (429). Extracting retry delay from error message...")
                
                # Extract retry delay from error message
                # Format: "Please retry in 14.408981893s" or "retryDelay": "14s"
                retry_delay = None
                import re
                import json
                
                # Method 1: Try to parse from error message text
                # Pattern: "Please retry in X.XXs" or "retry in X.XX s"
                delay_patterns = [
                    r'[Pp]lease retry in ([\d.]+)\s*s',
                    r'retry in ([\d.]+)\s*s',
                    r'retryDelay[:\s]+["\']?([\d.]+)s?["\']?',
                    r'(\d+\.?\d*)\s*seconds?',
                ]
                
                for pattern in delay_patterns:
                    match = re.search(pattern, error_str, re.IGNORECASE)
                    if match:
                        try:
                            retry_delay = float(match.group(1))
                            break
                        except:
                            continue
                
                # Method 2: Try to parse from JSON error details if available
                if retry_delay is None:
                    try:
                        # Try to extract JSON from error string
                        json_match = re.search(r'\{[^}]+\}', error_str)
                        if json_match:
                            error_json = json.loads(json_match.group(0))
                            if 'error' in error_json:
                                error_details = error_json['error']
                                # Check for retryDelay in details
                                if 'details' in error_details:
                                    for detail in error_details.get('details', []):
                                        if '@type' in detail and 'RetryInfo' in detail.get('@type', ''):
                                            if 'retryDelay' in detail:
                                                delay_str = str(detail['retryDelay'])
                                                # Extract number from "14s" or "14.4s"
                                                num_match = re.search(r'([\d.]+)', delay_str)
                                                if num_match:
                                                    retry_delay = float(num_match.group(1))
                                                    break
                    except:
                        pass
                
                # Default retry delay if not found
                if retry_delay is None:
                    retry_delay = 15.0  # Default 15 seconds
                    print(f"  → Could not extract retry delay from error, using default: {retry_delay}s")
                else:
                    print(f"  → Extracted retry delay: {retry_delay:.2f}s")
                
                # Wait for the specified retry delay
                import time
                print(f"  → Waiting {retry_delay:.2f}s before retry (as specified in error message)...")
                time.sleep(retry_delay)
                
                try:
                    # Retry with reduced history
                    print("  → Retrying API call with reduced history...")
                    response = self.client.models.generate_content(
                        model=self.model_name,
                        contents=contents,
                        config=config
                    )
                    
                    # If retry succeeds, continue with normal processing
                    # Extract response text and function calls (same as before)
                    response_text = ""
                    function_call = None
                    
                    if hasattr(response, 'candidates') and len(response.candidates) > 0:
                        candidate = response.candidates[0]
                        if hasattr(candidate, 'content') and candidate.content:
                            parts = candidate.content.parts
                            for part in parts:
                                if hasattr(part, 'text') and part.text:
                                    if response_text:
                                        response_text += "\n" + part.text
                                    else:
                                        response_text = part.text
                                if hasattr(part, 'function_call') and part.function_call:
                                    function_call = part.function_call
                    
                    if not function_call and hasattr(response, 'function_calls') and response.function_calls:
                        function_call = response.function_calls[0]
                    
                    if not response_text and hasattr(response, 'text') and response.text:
                        response_text = response.text
                    
                    # Process response (same logic as main path)
                    response_log = {
                        "has_function_call": function_call is not None,
                        "thinking_process": response_text if response_text else None,
                        "response_text": response_text,
                        "function_call": None
                    }
                    
                    if function_call:
                        action_name = function_call.name
                        params = {}
                        if hasattr(function_call, 'args') and function_call.args:
                            if isinstance(function_call.args, dict):
                                params = function_call.args
                            elif hasattr(function_call.args, '__dict__'):
                                params = dict(function_call.args)
                            else:
                                try:
                                    params = {k: v for k, v in function_call.args.items()}
                                except:
                                    params = {}
                        
                        response_log["function_call"] = {"name": action_name, "params": params}
                        self._log_response(response_log, state_summary.get("iteration", 0))
                        
                        action_plan = {
                            "action": action_name,
                            "params": params,
                            "phase": state_summary.get("phase", "unknown"),
                            "why": response_text or f"Gemini selected {action_name}",
                            "thinking_process": response_text
                        }
                        
                        self._update_conversation_history(
                            user_message=user_message,
                            image=image,
                            response_text=response_text,
                            function_call=function_call,
                            action_plan=action_plan,
                            action_result=last_action_result
                        )
                        
                        print("  ✓ Retry successful!")
                        return action_plan
                    else:
                        # No function call in retry response, try parsing from text
                        parsed_action, parsed_params = self._parse_function_call_from_text(response_text)
                        if parsed_action:
                            print(f"  → Parsed function call from text: {parsed_action}")
                            action_plan = {
                                "action": parsed_action,
                                "params": parsed_params,
                                "phase": state_summary.get("phase", "unknown"),
                                "why": response_text,
                                "thinking_process": response_text
                            }
                            response_log["function_call"] = {
                                "name": parsed_action,
                                "params": parsed_params,
                                "parsed_from_text": True
                            }
                            self._log_response(response_log, state_summary.get("iteration", 0))
                            self._update_conversation_history(
                                user_message=user_message,
                                image=image,
                                response_text=response_text,
                                function_call=None,
                                action_plan=action_plan,
                                action_result=last_action_result
                            )
                            print("  ✓ Retry successful (parsed from text)!")
                            return action_plan
                        else:
                            # No function call found
                            self._log_response(response_log, state_summary.get("iteration", 0))
                            action_plan = {
                                "action": "base_stop",
                                "params": {},
                                "phase": state_summary.get("phase", "unknown"),
                                "why": f"Gemini response (after retry): {response_text[:200] if response_text else 'No response'}",
                                "thinking_process": response_text
                            }
                            print("  ⚠️  Retry succeeded but no function call returned")
                            return action_plan
                        
                except Exception as retry_error:
                    retry_error_str = str(retry_error)
                    if "429" in retry_error_str or "RESOURCE_EXHAUSTED" in retry_error_str:
                        print(f"  ✗ Retry also failed with 429 error. Quota may be exhausted for longer period.")
                    else:
                        print(f"  ✗ Retry also failed: {retry_error}")
                    # Fall through to fallback logic below
            
            # Handle other errors
            if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                print(f"GenAI API timeout (this may be due to network issues)")
            else:
                # Only print full traceback for non-quota errors
                if "429" not in error_str and "RESOURCE_EXHAUSTED" not in error_str:
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
        # Don't clear current_log_dir here - it should be set by executor after reset
    
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
    
    def _build_history_context(self, state_summary: Dict[str, Any], last_action_result: Optional[Dict[str, Any]]) -> str:
        """
        Build history context from previous conversation messages.
        
        Returns a formatted string summarizing recent history, or empty string if no history.
        IMPORTANT: Keep this SHORT to avoid token limit. Only include essential recent information.
        """
        if not self.messages:
            return ""
        
        recent_messages = self.messages[-self.max_history_messages:] if len(self.messages) > self.max_history_messages else self.messages
        
        history_lines = ["--- Recent History (last 5 interactions) ---"]
        
        # Parse messages to extract ONLY essential information (keep it short!)
        # Messages alternate: user (observation + state) -> model (response + function call)
        for i, msg in enumerate(recent_messages):
            if hasattr(msg, 'parts'):
                parts = msg.parts
                for part in parts:
                    if hasattr(part, 'text') and part.text:
                        text = part.text
                        # Prefer function-call lines (they include params like angular_rate/duration)
                        # This makes oscillation patterns obvious to the model.
                        if "Function call:" in text:
                            for line in text.split("\n"):
                                line = line.strip()
                                if line.startswith("Function call:"):
                                    history_lines.append(f"  {line}")
                            continue

                        # Otherwise, extract just iteration markers from user state summaries.
                        if "Iteration:" in text:
                            for line in text.split("\n"):
                                line = line.strip()
                                if line.startswith("Iteration:"):
                                    history_lines.append(f"  {line}")
        
        if len(history_lines) == 1:
            return ""  # No useful history extracted
        
        # Limit total length to prevent token explosion
        result = "\n".join(history_lines)
        max_chars = 500  # Limit to ~125 tokens for history context
        if len(result) > max_chars:
            # Keep only the most recent lines
            lines = result.split('\n')
            result = "\n".join(lines[:1] + lines[-10:])  # Header + last 10 lines
        
        return result
    
    def _update_conversation_history(self,
                                    user_message: str,
                                    image: Optional[np.ndarray],
                                    response_text: str,
                                    function_call: Optional[Any],
                                    action_plan: Dict[str, Any],
                                    action_result: Optional[Dict[str, Any]]):
        """
        Update conversation history with current interaction.
        
        Stores user message (with image if available) and model response.
        """
        from google.genai import types
        
        # Build user message parts for history
        # IMPORTANT: History images are COMPRESSED (320x240, quality=70) to reduce token usage
        #            This is different from current images in plan() which use full resolution
        user_parts = [types.Part.from_text(text=user_message)]
        if image is not None:
            try:
                # Use compressed image for history to reduce token usage
                # compress=True: resize to 320x240, quality=70, optimized
                image_bytes = self._image_to_bytes(image, compress=True)
                original_size = image.shape[:2] if hasattr(image, 'shape') else None
                compressed_size = len(image_bytes)
                user_parts.append(types.Part.from_bytes(
                    data=image_bytes,
                    mime_type="image/jpeg"
                ))
                # Debug: log compression info
                if original_size:
                    print(f"  → History image compressed: {original_size[1]}x{original_size[0]} → {compressed_size} bytes")
            except Exception as e:
                print(f"Warning: Failed to encode image for history: {e}")
        
        # Add user message to history
        user_content = types.Content(parts=user_parts, role="user")
        self.messages.append(user_content)
        
        # Build model response
        model_parts = []
        if response_text:
            model_parts.append(types.Part.from_text(text=response_text))
        if function_call:
            # Add function call as text description for history
            # Include parameters so model can detect oscillation patterns (e.g., angular_rate alternating)
            func_text = f"Function call: {function_call.name}("
            if hasattr(function_call, 'args') and function_call.args:
                if isinstance(function_call.args, dict):
                    # Sort params for consistent display - this helps model see patterns
                    params_list = []
                    for k, v in sorted(function_call.args.items()):
                        params_list.append(f"{k}={v}")
                    params_str = ", ".join(params_list)
                else:
                    params_str = str(function_call.args)
                func_text += params_str
            func_text += ")"
            model_parts.append(types.Part.from_text(text=func_text))
        
        if model_parts:
            model_content = types.Content(parts=model_parts, role="model")
            self.messages.append(model_content)
        
        # Limit history size to avoid token limit
        # This is the ONLY place where we actually trim the messages list
        # All other code should use self.messages directly (it's already limited here)
        if len(self.messages) > self.max_history_messages:
            self.messages = self.messages[-self.max_history_messages:]
    
    def _parse_function_call_from_text(self, text: str) -> tuple[Optional[str], Dict[str, Any]]:
        """
        Parse function call from text when Gemini describes it instead of using function calling.
        
        Examples:
        - "Function call: default_api:base_step(velocity=50, direction=180, angular_rate=0, duration=0.4)"
        - "Function call: base_step(velocity=50, direction=180, angular_rate=0, duration=0.4)"
        - "base_step(velocity=50, direction=180, angular_rate=0, duration=0.4)"
        
        Returns:
            (action_name, params_dict) or (None, {}) if not found
        """
        import re
        
        if not text:
            return (None, {})
        
        # Pattern 1: "Function call: default_api:base_step(...)"
        # Pattern 2: "Function call: base_step(...)"
        # Pattern 3: "base_step(...)"
        patterns = [
            r'Function call:\s*(?:default_api:)?(\w+)\s*\(([^)]*)\)',
            r'(\w+)\s*\(([^)]*)\)',  # Direct function call pattern
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                action_name = match.group(1)
                params_str = match.group(2)
                
                # Parse parameters
                params = {}
                if params_str.strip():
                    # Split by comma, but handle nested structures
                    param_parts = []
                    current = ""
                    depth = 0
                    for char in params_str:
                        if char == '(':
                            depth += 1
                        elif char == ')':
                            depth -= 1
                        elif char == ',' and depth == 0:
                            param_parts.append(current.strip())
                            current = ""
                            continue
                        current += char
                    if current.strip():
                        param_parts.append(current.strip())
                    
                    # Parse each parameter
                    for part in param_parts:
                        if '=' in part:
                            key, value = part.split('=', 1)
                            key = key.strip()
                            value = value.strip()
                            
                            # Try to convert value to appropriate type
                            try:
                                # Try int
                                if value.isdigit() or (value.startswith('-') and value[1:].isdigit()):
                                    params[key] = int(value)
                                # Try float
                                elif '.' in value and value.replace('.', '').replace('-', '').isdigit():
                                    params[key] = float(value)
                                # Try bool
                                elif value.lower() in ('true', 'false'):
                                    params[key] = value.lower() == 'true'
                                # String (remove quotes if present)
                                else:
                                    params[key] = value.strip('"\'')
                            except:
                                params[key] = value
                
                # Validate action name (must be one of our tools)
                valid_actions = ['base_step', 'arm_move_xyz', 'arm_to_safe_pose', 'gripper_open', 'gripper_close']
                if action_name in valid_actions:
                    return (action_name, params)
        
        return (None, {})
