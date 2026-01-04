# Tool Call 到 RPC 调用的完整流程

本文档详细解释如何将 Gemini 返回的 tool call（例如 `arm_move_xyz`）转换成实际的树莓派 RPC 调用。

## 完整调用链

```
Gemini API 响应
    ↓
解析函数调用 (gemini_policy.py)
    ↓
返回 action_plan (executor.py)
    ↓
执行动作 (executor.act())
    ↓
调用技能层 (skills.py)
    ↓
参数验证和限幅 (safety.py)
    ↓
RPC 客户端 (rpc_client.py)
    ↓
JSON-RPC 2.0 请求
    ↓
树莓派 RPC Server
    ↓
执行硬件动作
```

---

## 详细步骤：以 `arm_move_xyz` 为例

### 步骤 1: Gemini 返回函数调用

**位置**: `planner/gemini_policy.py` - `plan()` 方法

```python
# Gemini API 返回响应
response = self.client.models.generate_content(...)

# 解析函数调用
if function_call:
    action_name = function_call.name  # "arm_move_xyz"
    params = function_call.args      # {"x": 5.0, "y": 10.0, "z": 15.0, ...}
    
    return {
        "action": "arm_move_xyz",
        "params": {
            "x": 5.0,
            "y": 10.0,
            "z": 15.0,
            "pitch": 0.0,
            "roll": -90.0,
            "yaw": 90.0,
            "speed": 1500
        },
        "phase": "PLANNING",
        "why": "Gemini selected arm_move_xyz"
    }
```

**关键点**:
- Gemini 返回的是函数名和参数字典
- 参数来自 Gemini 根据图像和任务描述做出的决策

---

### 步骤 2: Executor 接收 action_plan

**位置**: `runtime/executor.py` - `run()` 方法

```python
# 规划阶段
action_plan = self.plan(image, detection)
# action_plan = {
#     "action": "arm_move_xyz",
#     "params": {"x": 5.0, "y": 10.0, "z": 15.0, ...},
#     "why": "..."
# }

# 执行阶段
act_success, action_result, error = self.act(action_plan)
```

---

### 步骤 3: Executor 调用 act() 方法

**位置**: `runtime/executor.py` - `act()` 方法

```python
def act(self, action_plan: Dict[str, Any]) -> tuple[bool, Dict[str, Any], str]:
    action_name = action_plan.get("action")  # "arm_move_xyz"
    params = action_plan.get("params", {})   # {"x": 5.0, "y": 10.0, ...}
    
    # 根据动作名称分发到对应的技能
    if action_name == "arm_move_xyz":
        return self.skills.arm_move_xyz(
            params.get("x", 0.0),
            params.get("y", 6.0),
            params.get("z", 18.0),
            params.get("pitch", 0.0),
            params.get("roll", -90.0),
            params.get("yaw", 90.0),
            params.get("speed", 1500)
        )
```

**关键点**:
- Executor 作为路由器，将动作名称映射到对应的技能方法
- 从参数字典中提取各个参数，并提供默认值

---

### 步骤 4: Skills 层处理（参数验证和限幅）

**位置**: `masterpi_rpc/skills.py` - `arm_move_xyz()` 方法

```python
def arm_move_xyz(self, x: float, y: float, z: float, 
                pitch: float = 0.0, roll: float = -90.0, 
                yaw: float = 90.0, speed: int = 1500):
    # 4.1 参数限幅（安全保护）
    x = SafetyLimits.clamp_arm_x(x)      # 限制在 -10.0 到 10.0 cm
    y = SafetyLimits.clamp_arm_y(y)      # 限制在 5.0 到 15.0 cm
    z = SafetyLimits.clamp_arm_z(z)      # 限制在 0.0 到 25.0 cm
    speed = SafetyLimits.clamp_arm_speed(speed)  # 限制在 500 到 3000 ms
    
    # 4.2 参数验证
    is_valid, error_msg = SafetyLimits.validate_arm_params(x, y, z, speed)
    if not is_valid:
        return (False, {}, error_msg)
    
    # 4.3 调用 RPC 客户端
    self.timeout.start()
    success, result, error = self.rpc.arm_move_ik(x, y, z, pitch, roll, yaw, speed)
    
    # 4.4 返回结果
    if success:
        return (True, {
            "action": "arm_move_xyz",
            "x": x, "y": y, "z": z,
            "ik_success": True,
            "elapsed": elapsed
        }, "")
    else:
        return (False, {...}, error)
```

**关键点**:
- **安全限幅**: 确保所有参数在安全范围内
- **参数验证**: 检查参数组合是否有效
- **超时保护**: 使用 `ActionTimeout` 防止动作卡死

---

### 步骤 5: RPC 客户端构建 JSON-RPC 请求

**位置**: `masterpi_rpc/rpc_client.py` - `arm_move_ik()` 方法

```python
def arm_move_ik(self, x: float, y: float, z: float, 
                pitch: float = 0.0, roll: float = -90.0, 
                yaw: float = 90.0, speed: int = 1500):
    # 调用通用 RPC 方法
    return self._call("ArmMoveIk", [x, y, z, pitch, roll, yaw, speed])
```

**`_call()` 方法**:

```python
def _call(self, method_name: str, params: list) -> Tuple[bool, Any, str]:
    """
    通用 JSON-RPC 2.0 调用方法。
    
    Args:
        method_name: RPC 方法名（例如 "ArmMoveIk"）
        params: 参数列表（例如 [5.0, 10.0, 15.0, 0.0, -90.0, 90.0, 1500]）
    
    Returns:
        (success: bool, result: Any, error: str)
    """
    # 5.1 构建 JSON-RPC 2.0 请求
    request = {
        "jsonrpc": "2.0",
        "method": method_name,  # "ArmMoveIk"
        "params": params,        # [5.0, 10.0, 15.0, 0.0, -90.0, 90.0, 1500]
        "id": int(time.time() * 1000)  # 唯一请求 ID
    }
    
    # 5.2 发送 HTTP POST 请求
    try:
        response = requests.post(
            self.rpc_url,  # "http://192.168.86.60:9030/"
            json=request,
            timeout=self.timeout
        )
        response.raise_for_status()
        
        # 5.3 解析响应
        result = response.json()
        
        if "error" in result:
            return (False, None, result["error"].get("message", "Unknown error"))
        elif "result" in result:
            return (True, result["result"], "")
        else:
            return (False, None, "Invalid response format")
    
    except requests.exceptions.RequestException as e:
        return (False, None, str(e))
```

**关键点**:
- 使用 JSON-RPC 2.0 协议
- 方法名必须与 RPC Server 文档中的完全一致（例如 `"ArmMoveIk"`）
- 参数顺序必须与文档定义一致

---

### 步骤 6: 树莓派 RPC Server 执行

**位置**: 树莓派上的 RPCServer（不在本代码库中）

```python
# 树莓派端（伪代码）
def ArmMoveIk(x, y, z, pitch, roll, yaw, speed):
    # 6.1 接收参数
    # x=5.0, y=10.0, z=15.0, pitch=0.0, roll=-90.0, yaw=90.0, speed=1500
    
    # 6.2 调用逆运动学算法
    joint_angles = ik_solver.solve(x, y, z, pitch, roll, yaw)
    
    # 6.3 控制舵机
    servo1.set_angle(joint_angles[0], speed)
    servo2.set_angle(joint_angles[1], speed)
    servo3.set_angle(joint_angles[2], speed)
    servo4.set_angle(joint_angles[3], speed)
    servo5.set_angle(joint_angles[4], speed)
    servo6.set_angle(joint_angles[5], speed)
    
    # 6.4 返回结果
    return {"success": True, "message": "Arm moved successfully"}
```

---

## 完整数据流示例

### 示例：Gemini 决定移动机械臂

**1. Gemini 返回**:
```json
{
  "function_call": {
    "name": "arm_move_xyz",
    "args": {
      "x": 5.0,
      "y": 10.0,
      "z": 15.0,
      "pitch": 0.0,
      "roll": -90.0,
      "yaw": 90.0,
      "speed": 1500
    }
  }
}
```

**2. Gemini Policy 返回**:
```python
{
    "action": "arm_move_xyz",
    "params": {
        "x": 5.0, "y": 10.0, "z": 15.0,
        "pitch": 0.0, "roll": -90.0, "yaw": 90.0,
        "speed": 1500
    }
}
```

**3. Executor 调用**:
```python
self.skills.arm_move_xyz(
    x=5.0, y=10.0, z=15.0,
    pitch=0.0, roll=-90.0, yaw=90.0,
    speed=1500
)
```

**4. Skills 层处理**:
```python
# 限幅后（假设都在范围内）
x = 5.0, y = 10.0, z = 15.0, speed = 1500

# 调用 RPC
self.rpc.arm_move_ik(5.0, 10.0, 15.0, 0.0, -90.0, 90.0, 1500)
```

**5. RPC 客户端发送**:
```json
POST http://192.168.86.60:9030/
{
    "jsonrpc": "2.0",
    "method": "ArmMoveIk",
    "params": [5.0, 10.0, 15.0, 0.0, -90.0, 90.0, 1500],
    "id": 1704355200000
}
```

**6. 树莓派执行**:
- 接收 JSON-RPC 请求
- 解析参数：`x=5.0, y=10.0, z=15.0, pitch=0.0, roll=-90.0, yaw=90.0, speed=1500`
- 调用逆运动学算法计算关节角度
- 控制 6 个舵机移动到目标位置
- 返回成功响应

**7. 响应返回**:
```json
{
    "jsonrpc": "2.0",
    "result": {"success": true, "message": "Arm moved successfully"},
    "id": 1704355200000
}
```

**8. 结果传递回 Executor**:
```python
(True, {
    "action": "arm_move_xyz",
    "x": 5.0, "y": 10.0, "z": 15.0,
    "ik_success": True,
    "elapsed": 1.5
}, "")
```

---

## 工具到 RPC 方法的映射表

| Gemini Tool | Skills 方法 | RPC 方法 | 参数映射 |
|------------|------------|----------|----------|
| `base_step` | `skills.base_step()` | `SetMecanumVelocity` + `ResetMecanumMotors` | `velocity, direction, angular_rate` → `[velocity, direction, angular_rate]` |
| `arm_move_xyz` | `skills.arm_move_xyz()` | `ArmMoveIk` | `x, y, z, pitch, roll, yaw, speed` → `[x, y, z, pitch, roll, yaw, speed]` |
| `arm_to_safe_pose` | `skills.arm_to_safe_pose()` | `ArmMoveIk` | 固定参数 `[0.0, 10.0, 15.0, 0.0, -90.0, 90.0, 1500]` |
| `gripper_open` | `skills.gripper_open()` | `SetGripperOpen` | 无参数 → `[]` |
| `gripper_close` | `skills.gripper_close()` | `SetGripperClose` | 无参数 → `[]` |

---

## 关键设计点

### 1. **分层抽象**

```
高层（Gemini）: arm_move_xyz(x, y, z)  ← 语义化、任务导向
    ↓
中层（Skills）: 参数验证、限幅、超时保护
    ↓
底层（RPC）: ArmMoveIk(x, y, z, pitch, roll, yaw, speed)  ← 硬件接口
```

### 2. **安全保护**

- **参数限幅**: 所有参数在发送到 RPC 前都会被限幅到安全范围
- **参数验证**: 检查参数组合是否有效
- **超时保护**: 防止动作卡死
- **错误处理**: 捕获并返回详细的错误信息

### 3. **参数映射**

Gemini 返回的参数可能不完整（例如只有 `x, y, z`），Skills 层会：
- 使用默认值填充缺失参数（`pitch=0.0, roll=-90.0, yaw=90.0, speed=1500`）
- 确保所有必需参数都有值

### 4. **RPC 方法名映射**

Skills 层的方法名（如 `arm_move_xyz`）映射到 RPC 方法名（如 `ArmMoveIk`）：
- 映射关系硬编码在 `executor.act()` 中
- RPC 方法名必须与 `RPCServer_methods.md` 中的完全一致

---

## 代码位置总结

| 功能 | 文件 | 关键方法 |
|------|------|----------|
| 解析 Gemini 函数调用 | `planner/gemini_policy.py` | `plan()` → 提取 `function_call` |
| 动作分发 | `runtime/executor.py` | `act()` → 根据 `action_name` 调用对应技能 |
| 参数验证和限幅 | `masterpi_rpc/skills.py` | `arm_move_xyz()` → 调用 `safety.py` |
| 安全限幅 | `masterpi_rpc/safety.py` | `clamp_arm_x/y/z()`, `validate_arm_params()` |
| RPC 调用 | `masterpi_rpc/rpc_client.py` | `arm_move_ik()` → `_call("ArmMoveIk", [...])` |
| JSON-RPC 请求 | `masterpi_rpc/rpc_client.py` | `_call()` → `requests.post()` |

---

## 调试建议

如果 RPC 调用失败，按以下顺序检查：

1. **检查 Gemini 返回的参数**:
   ```bash
   cat logs/.../gemini_prompts/response_*.json
   ```

2. **检查 Executor 接收的 action_plan**:
   ```bash
   cat logs/.../json/iter_*.json | jq '.action_plan'
   ```

3. **检查 Skills 层的参数处理**:
   - 查看是否被限幅
   - 查看是否通过验证

4. **检查 RPC 请求**:
   - 查看 `rpc_client.py` 中的 `_call()` 方法
   - 确认方法名和参数顺序正确

5. **检查树莓派端**:
   - 确认 RPC Server 正在运行
   - 查看 RPC Server 日志

