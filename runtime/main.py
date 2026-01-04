#!/usr/bin/env python3
"""
Main entry point for MasterPi robot control system.

Usage:
    python runtime/main.py --task "pick up red block" [options]
"""

import argparse
import sys
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from runtime.executor import Executor


def main():
    """Main function with CLI argument parsing."""
    parser = argparse.ArgumentParser(
        description="MasterPi Robot Control System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python runtime/main.py --task "pick up red block"
  
  # Specify robot IP
  python runtime/main.py --task "pick up red block" --ip 192.168.1.100
  
  # Different task
  python runtime/main.py --task "move the blue cup to the table"
        """
    )
    
    parser.add_argument(
        "--task",
        type=str,
        required=True,
        help="Task description in natural language (e.g., 'pick up red block', 'move the blue cup to the table')"
    )
    
    parser.add_argument(
        "--ip",
        type=str,
        default=os.getenv("ROBOT_IP"),
        help="Robot IP address (default: from .env ROBOT_IP, must be set if not provided)"
    )
    
    parser.add_argument(
        "--rpc-port",
        type=int,
        default=int(os.getenv("RPC_PORT", "9030")),
        help=f"RPC server port (default: from .env RPC_PORT or 9030)"
    )
    
    parser.add_argument(
        "--camera-port",
        type=int,
        default=int(os.getenv("CAMERA_PORT", "8080")),
        help=f"Camera stream port (default: from .env CAMERA_PORT or 8080)"
    )
    
    parser.add_argument(
        "--thresholds",
        type=str,
        default="config/thresholds.yaml",
        help="Path to thresholds configuration file (default: config/thresholds.yaml)"
    )
    
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=500,
        help="Maximum iterations before timeout (default: 500)"
    )
    
    args = parser.parse_args()
    
    # Check for Gemini API key (required)
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable not set")
        print("Please set it in .env file or with: export GEMINI_API_KEY=your_api_key")
        sys.exit(1)
    
    # Create and run executor
    try:
        executor = Executor(
            robot_ip=args.ip,
            rpc_port=args.rpc_port,
            camera_port=args.camera_port,
            thresholds_path=args.thresholds
        )
        
        executor.run(
            task=args.task,
            max_iterations=args.max_iterations
        )
    
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

