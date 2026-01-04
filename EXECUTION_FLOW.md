# 执行流程详解：`python runtime/main.py --task "pick up red block" --policy gemini`

本文档详细解释当运行上述命令时，代码的完整执行流程。

## 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    main.py (入口点)                          │
│  - 解析命令行参数                                            │
│  - 加载 .env 配置                                            │
│  - 创建 Executor 并启动                                      │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                  Executor (主控制循环)                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Observe  │→ │  Plan    │→ │   Act    │→ │   Log    │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│       │              │              │              │        │
│       └──────────────┴──────────────┴──────────────┘        │
│                        (循环执行)                            │
└─────────────────────────────────────────────────────────────┘
         │              │              │              │
         ▼              ▼              ▼              ▼
    ┌────────┐    ┌──────────┐   ┌─────────┐   ┌──────────┐
    │ Camera │    │ Gemini   │   │ Skills  │   │ Logger   │
    │ +      │    │ Policy   │   │ (RPC    │   │          │
    │ Detect │    │          │   │ Wrapper)│   │          │
    └────────┘    └──────────┘   └─────────┘   └──────────┘
```

---

## 第一阶段：程序启动和初始化

### 步骤 1: `main.py` 入口

```python
# 1.1 加载环境变量
load_dotenv()  # 从 .env 读取 GEMINI_API_KEY, ROBOT_IP, RPC_PORT, CAMERA_PORT

# 1.2 解析命令行参数
args.task = "pick up red block"
args.policy = "gemini"
args.ip = os.getenv("ROBOT_IP")  # 从 .env 读取（必须设置）
args.rpc_port = 9030       # 从 .env 或默认值
args.camera_port = 8080    # 从 .env 或默认值

# 1.3 检查 Gemini API Key
if args.policy == "gemini":
    api_key = os.environ.get("GEMINI_API_KEY")  # 从 .env 读取
    if not api_key:
        print("Error: GEMINI_API_KEY not set")
        sys.exit(1)
```

### 步骤 2: 创建 Executor 对象

```python
executor = Executor(
    robot_ip=os.getenv("ROBOT_IP"),  # 从 .env 读取
    rpc_port=9030,
    camera_port=8080,
    policy_type="gemini",
    thresholds_path="config/thresholds.yaml"
)
```

**Executor 初始化过程：**

1. **创建 RPC 客户端** (`RPCClient`)
   - 连接到 `http://{ROBOT_IP}:9030/`（IP 从 .env 读取）
   - 准备发送 JSON-RPC 2.0 请求

2. **创建技能层** (`RobotSkills`)
   - 包装 RPC 调用为安全技能
   - 包含：`base_step()`, `arm_move_xyz()`, `gripper_open()`, `gripper_close()` 等

3. **创建相机对象** (`Camera`)
   - 准备连接 MJPEG 流：`http://{ROBOT_IP}:8080/`（IP 从 .env 读取）
   - 但此时**还未连接**（延迟连接）

4. **准备观察** (无需硬编码检测器 - Gemini 使用视觉理解)
   - 配置 HSV 颜色范围（红色：0-10 和 170-180）
   - 准备进行颜色检测

5. **加载配置文件**
   - 读取 `config/thresholds.yaml`（检测阈值、控制参数等）

6. **初始化 Gemini 策略** (`GeminiPolicy`)
   ```python
   # 6.1 从 .env 读取 API Key
   api_key = os.getenv("GEMINI_API_KEY")
   
   # 6.2 创建 GenAI 客户端
   self.client = genai.Client(api_key=api_key, http_options=...)
   
   # 6.3 设置模型名称
   self.model_name = "gemini-3-pro-preview"
   
   # 6.4 加载系统提示词和工具描述
   self.system_prompt = get_system_prompt()  # 包含机器人能力和规则
   ```

7. **创建日志器** (`Logger`)
   - 准备记录执行日志到 `logs/` 目录

### 步骤 3: 启动执行循环

```python
executor.run(task="pick up red block", max_iterations=500)
```

---

## 第二阶段：主执行循环（每次迭代）

### 迭代结构：`observe → plan → act → log`

每次迭代都遵循这个模式，让我们详细看第一次迭代：

---

### 迭代 1：第一次执行

#### 步骤 A: **Observe（观察）**

```python
obs_success, image, detection = self.observe()
```

**A.1 获取相机帧** (`camera.get_frame()`)

1. **连接 MJPEG 流**（如果未连接）
   ```
   URL: http://{ROBOT_IP}:8080/（从 .env 读取）
   方法: urllib.request.urlopen()
   ```

2. **读取流数据**
   - 从 HTTP 流中读取字节
   - 查找 JPEG 起始标记：`0xFF 0xD8`
   - 查找 JPEG 结束标记：`0xFF 0xD9`
   - 提取完整的 JPEG 帧

3. **解码图像**
   ```python
   image_array = np.frombuffer(jpg_data, dtype=np.uint8)
   image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
   # 结果: numpy array, shape (480, 640, 3), dtype uint8, BGR 格式
   ```

**A.2 检测红色木块** (`detector.detect(image)`)

1. **颜色空间转换**
   ```python
   hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
   ```

2. **创建红色掩码**
   ```python
   # 红色在 HSV 中有两个范围（因为色相是循环的）
   mask1 = cv2.inRange(hsv, [0, 50, 50], [10, 255, 255])    # 低红色
   mask2 = cv2.inRange(hsv, [170, 50, 50], [180, 255, 255]) # 高红色
   mask = cv2.bitwise_or(mask1, mask2)
   ```

3. **形态学操作**（去噪）
   ```python
   kernel = np.ones((5, 5), np.uint8)
   mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)   # 去除小噪点
   mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)  # 填充空洞
   ```

4. **查找轮廓**
   ```python
   contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
   largest_contour = max(contours, key=cv2.contourArea)  # 找最大轮廓
   ```

5. **计算检测结果**
   ```python
   x, y, w, h = cv2.boundingRect(largest_contour)
   bbox = (x, y, x+w, y+h)           # 边界框
   center = (x + w//2, y + h//2)     # 中心点
   area_ratio = area / image_area    # 面积比例
   confidence = ...                   # 置信度（基于形状和面积）
   ```

6. **返回检测结果**
   ```python
   detection = {
       "found": True,
       "bbox": (100, 50, 300, 250),
       "center": (200, 150),
       "area_ratio": 0.0951,  # 目标占图像 9.51%
       "confidence": 0.90
   }
   ```

**A.3 设置图像尺寸**（仅 FSM 策略需要，Gemini 策略兼容性）

```python
if isinstance(self.policy, FSMPolicy):
    self.policy.set_image_size(640, 480)
```

**Observe 返回：**
```python
return (True, image, detection)
```

---

#### 步骤 B: **Plan（规划）**

```python
action_plan = self.plan(image, detection)
```

**B.1 调用 Gemini 策略** (`gemini_policy.plan()`)

1. **格式化状态摘要**
   ```python
   state_text = format_state_summary({
       "task": "pick up red block",
       "phase": "PLANNING",
       "iteration": 1,
       "detection": {
           "found": True,
           "center": (200, 150),
           "area_ratio": 0.0951,
           "confidence": 0.90
       },
       "last_action": None,
       "last_action_success": None
   })
   # 结果: 多行文本描述当前状态
   ```

2. **构建提示词**
   ```python
   prompt = f"{system_prompt}\n\n{state_text}"
   # system_prompt 包含：
   # - 机器人能力描述
   # - 关键规则（短步、视觉反馈、单次工具调用等）
   ```

3. **准备图像数据**
   ```python
   # 转换 BGR → RGB
   image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
   
   # 转换为 PIL Image
   pil_image = Image.fromarray(image_rgb)
   
   # 转换为 JPEG 字节
   buffer = io.BytesIO()
   pil_image.save(buffer, format="JPEG")
   image_bytes = buffer.getvalue()
   ```

4. **构建 API 请求内容**
   ```python
   contents = [
       prompt,  # 文本提示
       genai.types.Part.from_bytes(
           data=image_bytes,
           mime_type="image/jpeg"
       )  # 图像
   ]
   ```

5. **准备工具定义**（函数调用）
   ```python
   # 从 prompts.py 获取工具描述
   tool_descs = get_tool_descriptions()
   # 包含 5 个工具：
   # - base_step(velocity, direction, angular_rate, duration)
   # - arm_move_xyz(x, y, z, pitch, roll, yaw, speed)
   # - arm_to_safe_pose()
   # - gripper_open()
   # - gripper_close()
   
   # 转换为 FunctionDeclaration
   function_declarations = []
   for tool_desc in tool_descs:
       func_decl = types.FunctionDeclaration(
           name=tool_desc["name"],
           description=tool_desc["description"],
           parametersJsonSchema=tool_desc["parameters"]
       )
       function_declarations.append(func_decl)
   
   # 包装为 Tool
   tools = [types.Tool(functionDeclarations=function_declarations)]
   ```

6. **调用 Gemini API**
   ```python
   response = self.client.models.generate_content(
       model="gemini-3-pro-preview",
       contents=contents,  # 文本 + 图像
       config=types.GenerateContentConfig(
           temperature=0.3,  # 较低温度 = 更确定性
           tools=tools       # 函数调用工具
       )
   )
   ```
   
   **API 请求内容：**
   - 系统提示：描述机器人能力和规则
   - 状态摘要：当前任务、迭代次数、检测结果
   - 图像：当前相机帧（JPEG）
   - 工具定义：5 个可用技能及其参数

7. **解析 API 响应**
   ```python
   # 检查函数调用
   if response.function_calls:
       function_call = response.function_calls[0]
       action_name = function_call.name  # 例如: "base_step"
       params = function_call.args       # 例如: {"velocity": 50.0, ...}
   ```

8. **返回动作计划**
   ```python
   return {
       "action": "base_step",
       "params": {
           "velocity": 50.0,
           "direction": 0.0,
           "angular_rate": 0.0,
           "duration": 0.3
       },
       "phase": "PLANNING",
       "why": "Gemini selected base_step"
   }
   ```

   **Gemini 的决策逻辑：**
   - 看到图像中有红色目标
   - 目标面积比例 0.0951（较小，说明距离较远）
   - 根据系统提示："如果目标在视野但太小（远）→ 底盘小步靠近"
   - 选择 `base_step` 向前移动

---

#### 步骤 C: **Act（执行）**

```python
act_success, action_result, error = self.act(action_plan)
```

**C.1 参数验证和限幅** (`safety.py`)

```python
# 从 action_plan 提取参数
velocity = 50.0
direction = 0.0
angular_rate = 0.0
duration = 0.3

# 安全限幅
velocity = clamp(50.0, 0.0, 200.0)      # → 50.0 ✓
angular_rate = clamp(0.0, -50.0, 50.0)  # → 0.0 ✓
duration = clamp(0.3, 0.2, 0.5)         # → 0.3 ✓
```

**C.2 执行技能** (`skills.base_step()`)

1. **发送 RPC 调用**
   ```python
   # JSON-RPC 2.0 请求
   POST http://{ROBOT_IP}:9030/（从 .env 读取）
   {
       "jsonrpc": "2.0",
       "method": "SetMecanumVelocity",
       "params": [50.0, 0.0, 0.0],  # velocity, direction, angular_rate
       "id": 1234567890
   }
   ```

2. **等待指定时长**
   ```python
   time.sleep(0.3)  # 等待 0.3 秒
   ```

3. **停止底盘**
   ```python
   # 发送停止命令
   POST http://{ROBOT_IP}:9030/（从 .env 读取）
   {
       "jsonrpc": "2.0",
       "method": "ResetMecanumMotors",
       "params": [],
       "id": 1234567891
   }
   ```

4. **返回执行结果**
   ```python
   return (True, {
       "action": "base_step",
       "velocity": 50.0,
       "direction": 0.0,
       "angular_rate": 0.0,
       "duration": 0.3,
       "elapsed": 0.3
   }, "")
   ```

**C.3 检查卡住状态**

```python
if action_name == self.last_action_name:
    self.stuck_counter += 1
    if self.stuck_counter >= 10:  # 阈值
        # 强制进入恢复模式
        return (False, {}, "Stuck: same action repeated")
```

---

#### 步骤 D: **Log（记录）**

```python
self.logger.log_iteration(
    image=image,
    detection=detection,
    state_summary=state_summary,
    action_plan=action_plan,
    action_result=action_result
)
```

**D.1 保存数据**

1. **保存图像**
   ```
   logs/20260103_102513_pick_up_red_block/images/iter_00000.jpg
   ```

2. **保存 JSON 数据**
   ```json
   logs/.../json/iter_00000.json
   {
       "iteration": 0,
       "timestamp": 1767453914.05,
       "detection": {
           "found": true,
           "bbox": [100, 50, 300, 250],
           "center": [200, 150],
           "area_ratio": 0.0951,
           "confidence": 0.90
       },
       "state_summary": {...},
       "action_plan": {
           "action": "base_step",
           "params": {...},
           "why": "Gemini selected base_step"
       },
       "action_result": {
           "success": true,
           "elapsed": 0.3
       }
   }
   ```

**D.2 等待观察延迟**

```python
time.sleep(0.2)  # 给系统时间稳定
```

---

### 迭代 2-N：重复循环

每次迭代都重复上述步骤：

1. **Observe**: 获取新图像 → 检测目标
2. **Plan**: Gemini 根据新状态决定下一步
3. **Act**: 执行动作（短步）
4. **Log**: 记录所有数据

**关键点：**
- 每次动作后**必须停止**并重新观察
- Gemini 看到**新的图像和状态**后决定下一步
- 如果 API 超时，使用 fallback 策略（基于检测结果的启发式）

---

## 第三阶段：典型执行序列示例

假设任务成功执行，典型的迭代序列：

### 迭代 1-5：搜索和接近阶段

```
Iter 1: Detection found=True, area=0.095 → Gemini: base_step(forward)
Iter 2: Detection found=True, area=0.12  → Gemini: base_step(forward)
Iter 3: Detection found=True, area=0.15  → Gemini: base_step(forward)
Iter 4: Detection found=True, area=0.18  → Gemini: base_step(forward)
Iter 5: Detection found=True, area=0.22  → Gemini: base_step(forward)
```

### 迭代 6-8：准备抓取阶段

```
Iter 6: Detection found=True, area=0.25 → Gemini: arm_to_safe_pose()
Iter 7: Detection found=True, area=0.25 → Gemini: arm_move_xyz(x, y, z)
Iter 8: Detection found=True, area=0.25 → Gemini: arm_move_xyz(微调)
```

### 迭代 9-12：抓取阶段

```
Iter 9:  Detection found=True → Gemini: gripper_open()
Iter 10: Detection found=True → Gemini: arm_move_xyz(下探)
Iter 11: Detection found=True → Gemini: gripper_close()
Iter 12: Detection found=True → Gemini: arm_move_xyz(抬起)
```

### 迭代 13：验证阶段

```
Iter 13: Detection found=False → Gemini: 任务完成（或继续验证）
```

---

## 关键设计原则

### 1. **离散小步闭环**

- ✅ 每个动作 0.2-0.5 秒
- ✅ 动作后立即停止
- ✅ 重新观察后再决策
- ❌ 不允许长时间连续动作

### 2. **视觉伺服**

- ✅ 使用图像反馈（目标大小、位置）
- ❌ 不依赖精确距离测量
- ✅ 迭代调整直到目标足够大且居中

### 3. **安全第一**

- ✅ 所有参数自动限幅
- ✅ 动作超时保护（2秒）
- ✅ 卡住检测（相同动作重复 10 次触发恢复）

### 4. **失败恢复**

- ✅ API 超时 → Fallback 策略
- ✅ 动作失败 → 记录并继续
- ✅ 目标丢失 → 重新搜索

---

## 数据流图

```
┌─────────────┐
│   Camera    │ → 图像 (BGR numpy array)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Detector   │ → detection {
│  (OpenCV)   │     found: bool
│             │     bbox: (x1,y1,x2,y2)
│             │     center: (cx, cy)
│             │     area_ratio: float
│             │     confidence: float
│             │   }
└──────┬──────┘
       │
       ├─────────────────┐
       │                 │
       ▼                 ▼
┌─────────────┐   ┌─────────────┐
│   Gemini    │   │   Logger    │
│   Policy    │   │             │
└──────┬──────┘   └─────────────┘
       │
       ▼
┌─────────────┐
│   Skills    │ → action_plan {
│             │     action: str
│             │     params: dict
│             │     why: str
│             │   }
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  RPC Client │ → HTTP POST to robot
│             │    JSON-RPC 2.0
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  MasterPi  │ → 执行动作（底盘移动/机械臂移动/夹爪）
│   Robot     │
└─────────────┘
```

---

## 错误处理流程

### 场景 1: API 超时

```
1. Gemini API 调用超时（网络问题）
2. 捕获异常
3. 使用 Fallback 策略：
   - 如果 found=True 且 area < 0.05 → base_step(forward)
   - 如果 found=True 且 area >= 0.05 → arm_to_safe_pose()
   - 如果 found=False → base_step(rotate)
4. 继续执行，不中断
```

### 场景 2: 相机连接失败

```
1. camera.get_frame() 返回失败
2. detection = {"found": False, "error": "Failed to capture frame"}
3. Gemini 看到 found=False
4. Gemini 选择搜索动作：base_step(rotate)
5. 继续尝试连接
```

### 场景 3: RPC 调用失败

```
1. RPC 调用返回 (False, None, "Connection error")
2. skills.base_step() 返回 (False, {}, "Failed to start base movement")
3. 记录错误
4. 下一迭代继续尝试
```

---

## 总结

执行 `python runtime/main.py --task "pick up red block" --policy gemini` 时：

1. **初始化**：加载配置、创建所有组件、连接机器人
2. **循环执行**：每次迭代执行 observe → plan → act → log
3. **Gemini 决策**：根据图像和状态，选择下一步动作
4. **安全执行**：所有动作都经过参数验证和限幅
5. **完整记录**：每一步都记录图像、状态、动作和结果
6. **错误恢复**：API 超时或动作失败时使用 fallback 策略

整个过程是**闭环的、安全的、可观测的**，适合在误差较大的廉价平台上运行。

