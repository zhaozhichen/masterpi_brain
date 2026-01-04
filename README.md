# MasterPi Robotics Control System

A stepwise closed-loop robot control system for MasterPi that executes complex tasks using discrete small steps with visual feedback. The system uses Gemini Robotics-ER 1.5 for high-level planning and Gemini 3 Flash Preview for fast task completion detection.

## Features

- **Discrete Small Steps**: Every action is 0.2-0.5s, followed by stop and re-observation
- **Visual Servoing**: Uses image feedback (centering, area ratio) instead of precise distance measurement
- **Safety First**: All parameters clamped, timeouts enforced, emergency stop available
- **Fail-Safe Recovery**: Multiple retry strategies, backtrack on failure
- **Comprehensive Logging**: Every step logged for debugging and improvement
- **LLM-Based Planning**: Uses Gemini Robotics-ER 1.5 for high-level planning and Gemini 3 Flash Preview for fast task completion detection

## Architecture

```
┌─────────────┐
│  Executor   │  Main control loop: observe → plan → act → log
└──────┬──────┘
       │
       ├─── Perception Layer (Camera + Detection)
       ├─── Planning Layer (Gemini Robotics-ER 1.5)
       ├─── Task Detection (Gemini 3 Flash Preview)
       ├─── Skills Layer (Short-step wrappers)
       └─── RPC Client (MasterPi interface)
```

## Installation

1. **Install dependencies**:
```bash
cd /home/tensor/projects/masterpi_brain
python -m venv venv
source venv/bin/activate  # On Linux/Mac
pip install -r requirements.txt
```

2. **Configure environment variables** (create `.env` file):
```bash
# Create .env file with your configuration
cat > .env << EOF
GEMINI_API_KEY=your_api_key_here
ROBOT_IP=192.168.86.60
RPC_PORT=9030
CAMERA_PORT=8080
EOF
```

Or manually edit `.env` file:
- `GEMINI_API_KEY`: Your Gemini API key (required for Gemini policy)
- `ROBOT_IP`: Robot IP address (required, no default)
- `RPC_PORT`: RPC server port (default: 9030)
- `CAMERA_PORT`: Camera stream port (default: 8080)

## Usage

### Basic Usage

```bash
python runtime/main.py --task "pick up red block"
```

### With Custom Robot IP

```bash
python runtime/main.py --task "pick up red block" --ip 192.168.1.100
```

### Setup

Make sure you have `GEMINI_API_KEY` set in your `.env` file (see Configuration section).

### Command Line Options

```
--task TEXT              Task description (default: "pick up red block")
--ip TEXT                Robot IP address (default: 192.168.86.60)
--rpc-port INTEGER       RPC server port (default: 9030)
--camera-port INTEGER    Camera stream port (default: 8080)
--thresholds TEXT        Path to thresholds config (default: config/thresholds.yaml)
--max-iterations INTEGER Maximum iterations (default: 500)
```

## Configuration

### Thresholds (`config/thresholds.yaml`)

Adjust detection and control thresholds based on real-world testing:
- Detection thresholds (confidence, area ratio)
- Base alignment (centering tolerance, search parameters)
- Approach phase (near threshold)
- Arm alignment (visual servoing parameters)
- Grasp phase (attempts, offsets)

### Robot Card (`config/robot_card.yaml`)

Describes robot capabilities and constraints:
- Sensor specifications
- Actuator limits
- Safety constraints
- Success criteria

## Project Structure

```
masterpi_brain/
├── config/              Configuration files
├── masterpi_rpc/        RPC client and skills
├── perception/          Camera and detection
├── planner/              Planning policy (Gemini)
├── runtime/             Executor, logger, main entry
└── logs/                Execution logs (auto-generated)
```

## Development Phases

1. **Phase 1**: RPC Client and Skills Layer ✅
2. **Phase 2**: Perception Layer ✅
3. **Phase 3**: Executor and Logging ✅
4. **Phase 4**: Gemini 3 Flash Integration ✅

## Logging

Each execution session creates a timestamped log directory:
```
logs/YYYYMMDD_HHMMSS_task_name/
├── images/          Camera frames (one per iteration)
├── json/            State and action data (one per iteration)
└── summary.json      Session summary
```

## Safety Features

- Parameter clamping (velocity, position, duration)
- Action timeouts (default 2.0s)
- Emergency stop capability
- Stuck detection (repeated actions trigger recovery)
- Maximum iteration limit

## Notes

- All MasterPi interfaces are based strictly on `RPCServer_methods.md`
- Only Level 1 (high-level) RPC functions are used
- The system is designed for low-cost, high-error platforms
- Visual servoing compensates for lack of precise distance measurement

## Troubleshooting

1. **Camera connection fails**: Check robot IP and camera port (default 8080)
2. **RPC calls fail**: Verify RPC server is running on port 9030
3. **General Purpose Design**: The system uses Gemini's visual understanding for object detection - no hardcoded color detection or task-specific logic.
4. **Gemini API errors**: Verify `GEMINI_API_KEY` is set correctly

## License

See project license file.

