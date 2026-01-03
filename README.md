# MasterPi Robotics Control System

A stepwise closed-loop robot control system for MasterPi that executes complex tasks using discrete small steps with visual feedback. The system supports both deterministic FSM-based planning and Gemini Robotics-ER 1.5 for high-level planning.

## Features

- **Discrete Small Steps**: Every action is 0.2-0.5s, followed by stop and re-observation
- **Visual Servoing**: Uses image feedback (centering, area ratio) instead of precise distance measurement
- **Safety First**: All parameters clamped, timeouts enforced, emergency stop available
- **Fail-Safe Recovery**: Multiple retry strategies, backtrack on failure
- **Comprehensive Logging**: Every step logged for debugging and improvement
- **Dual Policy Support**: FSM (deterministic) and Gemini (LLM-based) planning

## Architecture

```
┌─────────────┐
│  Executor   │  Main control loop: observe → plan → act → log
└──────┬──────┘
       │
       ├─── Perception Layer (Camera + Detection)
       ├─── Planning Layer (FSM or Gemini)
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

### Basic Usage (FSM Policy)

```bash
python runtime/main.py --task "pick up red block"
```

### With Custom Robot IP

```bash
python runtime/main.py --task "pick up red block" --ip 192.168.1.100
```

### Using Gemini Policy

```bash
export GEMINI_API_KEY=your_api_key
python runtime/main.py --task "pick up red block" --policy gemini
```

### Command Line Options

```
--task TEXT              Task description (default: "pick up red block")
--ip TEXT                Robot IP address (default: 192.168.86.60)
--rpc-port INTEGER       RPC server port (default: 9030)
--camera-port INTEGER    Camera stream port (default: 8080)
--policy [fsm|gemini]    Planning policy (default: fsm)
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
├── planner/              Planning policies (FSM, Gemini)
├── runtime/             Executor, logger, main entry
└── logs/                Execution logs (auto-generated)
```

## Development Phases

1. **Phase 1**: RPC Client and Skills Layer ✅
2. **Phase 2**: Perception Layer ✅
3. **Phase 3**: FSM Policy (MVP) ✅
4. **Phase 4**: Executor and Logging ✅
5. **Phase 5**: Gemini Robotics-ER Integration ✅

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

- All MasterPi interfaces are based strictly on `RPCServer_功能列表.md`
- Only Level 1 (high-level) RPC functions are used
- The system is designed for low-cost, high-error platforms
- Visual servoing compensates for lack of precise distance measurement
- The FSM policy should be tested first before using Gemini policy

## Troubleshooting

1. **Camera connection fails**: Check robot IP and camera port (default 8080)
2. **RPC calls fail**: Verify RPC server is running on port 9030
3. **Detection not working**: Adjust HSV ranges in `detect_red.py` or lighting
4. **Gemini API errors**: Verify `GEMINI_API_KEY` is set correctly

## License

See project license file.

