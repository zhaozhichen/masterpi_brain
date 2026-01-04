"""
Comprehensive logging for robot execution.

Logs each iteration with images, detection results, state, and actions.
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import cv2
import numpy as np


class Logger:
    """Logs robot execution data for analysis and replay."""
    
    def __init__(self, log_dir: str = "logs"):
        """
        Initialize logger.
        
        Args:
            log_dir: Base directory for logs
        """
        self.log_dir = Path(log_dir)
        self.session_dir: Optional[Path] = None
        self.iteration = 0
        self.log_data: list = []
    
    def start_session(self, task: str = "unknown"):
        """Start a new logging session."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir = self.log_dir / f"{timestamp}_{task.replace(' ', '_')}"
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.iteration = 0
        self.log_data = []
        
        # Create subdirectories
        (self.session_dir / "images").mkdir(exist_ok=True)
        (self.session_dir / "json").mkdir(exist_ok=True)
        
        print(f"Logging session started: {self.session_dir}")
    
    def log_iteration(self, 
                     image: Optional[np.ndarray],
                     detection: Dict[str, Any],
                     state_summary: Dict[str, Any],
                     action_plan: Dict[str, Any],
                     action_result: Optional[Dict[str, Any]] = None,
                     llm_input: Optional[Dict[str, Any]] = None,
                     llm_output: Optional[Dict[str, Any]] = None):
        """
        Log one iteration of execution.
        
        Args:
            image: Current camera frame
            detection: Detection results
            state_summary: Current state summary
            action_plan: Planned action
            action_result: Result of executed action
            llm_input: LLM input (if using Gemini)
            llm_output: LLM output (if using Gemini)
        """
        if self.session_dir is None:
            self.start_session()
        
        timestamp = time.time()
        iteration_data = {
            "iteration": self.iteration,
            "timestamp": timestamp,
            "detection": detection,
            "state_summary": state_summary,
            "action_plan": action_plan,
            "action_result": action_result,
            "llm_input": llm_input,
            "llm_output": llm_output
        }
        
        # Extract thinking process from action_plan if available
        if action_plan and "thinking_process" in action_plan:
            iteration_data["thinking_process"] = action_plan["thinking_process"]
        
        # Save image
        if image is not None:
            image_path = self.session_dir / "images" / f"iter_{self.iteration:05d}.jpg"
            cv2.imwrite(str(image_path), image)
            iteration_data["image_path"] = str(image_path.relative_to(self.session_dir))
        
        # Save JSON
        json_path = self.session_dir / "json" / f"iter_{self.iteration:05d}.json"
        with open(json_path, 'w') as f:
            json.dump(iteration_data, f, indent=2, default=str)
        
        # Append to log data
        self.log_data.append(iteration_data)
        
        self.iteration += 1
    
    def save_summary(self):
        """Save summary of entire session."""
        if self.session_dir is None:
            return
        
        summary = {
            "total_iterations": self.iteration,
            "session_dir": str(self.session_dir),
            "start_time": self.log_data[0]["timestamp"] if self.log_data else None,
            "end_time": self.log_data[-1]["timestamp"] if self.log_data else None,
            "iterations": self.log_data
        }
        
        summary_path = self.session_dir / "summary.json"
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        print(f"Session summary saved: {summary_path}")
    
    def get_session_dir(self) -> Optional[Path]:
        """Get current session directory."""
        return self.session_dir

