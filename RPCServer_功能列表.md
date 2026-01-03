# RPCServer.py 完整功能列表

## 文档说明

本文档完整描述了 MasterPi RPCServer 支持的所有 RPC 功能。RPCServer 是一个 JSON-RPC 服务器，监听在端口 9030，提供远程控制 MasterPi 机器人的完整接口。

**版本**：完整版（包含所有 HiwonderSDK 功能）  
**更新日期**：2024年  
**总功能数**：71 个 RPC 方法

---

## 目录

1. [功能分类说明](#功能分类说明)
2. [一级功能（上层功能）](#一级功能上层功能)
3. [二级功能（底层功能）](#二级功能底层功能)
4. [错误码说明](#错误码说明)
5. [使用指南](#使用指南)
6. [功能统计](#功能统计)

---

## 功能分类说明

### 一级功能（上层功能）
- **特点**：高级抽象操作，用户友好的接口，组合操作，业务逻辑相关
- **适用对象**：普通用户、应用开发者
- **示例**：`SetGripperOpen()` - 打开夹持器（封装了底层舵机控制）

### 二级功能（底层功能）
- **特点**：直接硬件控制，需要了解硬件细节，寄存器级别操作，基础控制
- **适用对象**：高级用户、系统开发者、硬件调试
- **示例**：`SetPWMServoPulseSingle()` - 直接控制舵机脉冲值

---

## 一级功能（上层功能）

### 1. 机械臂高级操作

#### ArmMoveIk(x, y, z, pitch, roll, yaw, speed)
**级别**：一级  
**功能描述**：通过逆运动学算法控制机械臂末端执行器移动到指定位置和姿态。使用笛卡尔坐标和欧拉角定义目标位置。

**参数说明**：
- `x` (float): 末端执行器X坐标，单位 cm
  - **允许范围**: 约 -15.0 到 15.0 cm（实际可达范围取决于y、z坐标和姿态）
  - **推荐范围**: -10.0 到 10.0 cm
  - **说明**: X轴向右为正方向，工作空间受机械臂连杆长度限制
- `y` (float): 末端执行器Y坐标，单位 cm
  - **允许范围**: 约 0.0 到 20.0 cm（实际可达范围取决于x、z坐标和姿态）
  - **推荐范围**: 5.0 到 15.0 cm
  - **说明**: Y轴向前为正方向，工作空间受机械臂连杆长度限制
- `z` (float): 末端执行器Z坐标，单位 cm
  - **允许范围**: 约 -5.0 到 30.0 cm（实际可达范围取决于x、y坐标和姿态）
  - **推荐范围**: 0.0 到 25.0 cm
  - **说明**: Z轴向上为正方向，最小值受底盘高度限制（约l1=8.0cm），最大值受总连杆长度限制（约30.7cm）
- `pitch` (float): 俯仰角，单位 度
  - **允许范围**: -90.0 到 90.0 度
  - **推荐范围**: 0.0
  - **说明**: 俯仰角是末端执行器与水平面的夹角，正值向上，负值向下
- `roll` (float): 横滚角，单位 度
  - **允许范围**: -90.0 到 90.0 度（实际范围取决于pitch和yaw的组合）
  - **推荐范围**: -90.0
  - **说明**: 横滚角是末端执行器绕自身前进轴的旋转角度
- `yaw` (float): 偏航角，单位 度
  - **允许范围**: -180.0 到 180.0 度（或等效的0-360度）
  - **推荐范围**: 90.0
  - **说明**: 偏航角是末端执行器在水平面的旋转角度，0度对应正前方（X轴正方向）
- `speed` (int): 移动速度，单位 ms
  - **允许范围**: 100 到 5000 ms（建议 500-3000 ms）
  - **说明**: 速度值表示完成运动所需的时间，值越小速度越快，但过小可能导致舵机无法及时到达目标位置

**返回值**：
- `(True, result, 'ArmMoveIk')`: 成功，result包含运动结果信息
- `(False, 'E01 - Invalid number of parameter!', 'ArmMoveIk')`: 参数数量错误
- `(False, 'E03 - Operation failed!', 'ArmMoveIk')`: 操作失败

**使用示例**：
```python
# 移动到位置(10, 5, 15)，姿态(0, -90, 90)，速度1500ms
ArmMoveIk(10, 5, 15, 0, -90, 90, 1500)

# 回到初始位置
ArmMoveIk(0, 6, 18, 0, -90, 90, 1500)
```

**注意事项**：
- 坐标系统：X向右，Y向前，Z向上
- 角度定义：pitch俯仰，roll横滚，yaw偏航
- 目标位置必须在机械臂工作空间内
- 如果目标位置不可达，会返回失败
- **工作空间限制**：
  - 机械臂总长度约30.7cm（l1=8.0cm + l2=6.5cm + l3=6.2cm + l4=10.0cm）
  - 实际可达范围受逆运动学解的存在性限制，并非所有理论范围内的点都可达
  - 建议在推荐范围内使用，超出范围可能导致无解返回False
- **角度组合限制**：
  - pitch、roll、yaw的组合必须满足逆运动学约束
  - 某些极端角度组合可能导致无解

---

#### RunAction(args)
**级别**：一级  
**功能描述**：执行指定的动作组文件。动作组是预定义的舵机动作序列。动作在独立线程中执行，不会阻塞。

**参数说明**：
- `args` (str 或 list): 动作组名称或动作组名称列表
  - 字符串: 单个动作组名称，如 "action1"
  - 列表: 多个动作组名称，如 ["action1", "action2"]

**返回值**：
- `(True, (), 'RunAction')`: 成功（动作已在后台启动）
- `(False, 'E01 - Invalid number of parameter!', 'RunAction')`: 参数错误
- `(False, 'E03 - Operation failed!', 'RunAction')`: 操作失败

**使用示例**：
```python
# 运行单个动作组
RunAction("wave_hand")

# 运行多个动作组
RunAction(["stand_up", "walk_forward"])
```

**注意事项**：
- 动作在后台线程执行，立即返回
- 可以同时运行多个动作组
- 动作组文件需要预先加载到系统中
- 使用StopBusServo可以停止动作组

---

#### StopBusServo(args)
**级别**：一级  
**功能描述**：停止当前正在执行的动作组。用于中断正在运行的动作序列。

**参数说明**：
- `args` (str): 必须为字符串 "stopAction"

**返回值**：
- `(True, (), 'StopBusServo')`: 成功
- `(False, 'E01 - Invalid number of parameter!', 'StopBusServo')`: 参数错误
- `(False, 'E03 - Operation failed!', 'StopBusServo')`: 操作失败

**使用示例**：
```python
# 停止当前动作组
StopBusServo("stopAction")
```

**注意事项**：
- 会立即停止当前动作组
- 舵机可能停留在中间位置
- 需要确保AGC（动作组控制）已初始化

---

### 2. 夹持器（Gripper）操作

#### SetGripperOpen()
**级别**：一级  
**功能描述**：快速打开夹持器。夹持器通过PWM舵机1控制。打开位置对应脉冲值2000。

**参数说明**：无参数

**返回值**：
- `(True, (), 'SetGripperOpen')`: 成功
- `(False, 'E03 - Operation failed!', 'SetGripperOpen')`: 操作失败

**使用示例**：
```python
# 打开夹持器
SetGripperOpen()
```

**注意事项**：
- 夹持器使用PWM舵机1控制
- 打开时间固定为500ms
- 脉冲值：2000（完全打开）

---

#### SetGripperClose()
**级别**：一级  
**功能描述**：快速关闭夹持器。夹持器通过PWM舵机1控制。关闭位置对应脉冲值1500。

**参数说明**：无参数

**返回值**：
- `(True, (), 'SetGripperClose')`: 成功
- `(False, 'E03 - Operation failed!', 'SetGripperClose')`: 操作失败

**使用示例**：
```python
# 关闭夹持器
SetGripperClose()
```

**注意事项**：
- 夹持器使用PWM舵机1控制
- 关闭时间固定为500ms
- 脉冲值：1500（完全关闭）

---

#### SetGripperPosition(position, use_time=500)
**级别**：一级  
**功能描述**：精确控制夹持器的开合程度，通过百分比设置位置。夹持器通过PWM舵机1控制。

**参数说明**：
- `position` (int): 位置百分比，范围 0-100
  - 0: 完全关闭（脉冲值1500）
  - 50: 半开（脉冲值1750）
  - 100: 完全打开（脉冲值2000）
- `use_time` (int): 运行时间，单位毫秒，默认500

**返回值**：
- `(True, (), 'SetGripperPosition')`: 成功
- `(False, 'E03 - Operation failed!', 'SetGripperPosition')`: 操作失败

**使用示例**：
```python
# 设置为半开状态
SetGripperPosition(50)

# 设置为30%打开，用时1000ms
SetGripperPosition(30, 1000)
```

**注意事项**：
- 位置值会被自动限制在0-100范围内
- 脉冲值映射：1500 + (position/100) * 500
- 夹持器使用PWM舵机1控制

---

#### GetGripperPosition()
**级别**：一级  
**功能描述**：获取夹持器当前位置，返回百分比值。

**参数说明**：无参数

**返回值**：
- `(True, position, 'GetGripperPosition')`: 成功，返回位置百分比 (0-100)
- `(False, 'E03 - Operation failed!', 'GetGripperPosition')`: 操作失败

**使用示例**：
```python
# 读取夹持器位置
result = GetGripperPosition()
if result[0]:
    position = result[1]
    print(f"夹持器位置: {position}%")
```

**注意事项**：
- 返回的是百分比位置（0-100）
- 通过读取PWM舵机1的脉冲值计算得出

---

### 3. Mecanum底盘高级操作

#### SetMecanumVelocity(velocity, direction, angular_rate)
**级别**：一级  
**功能描述**：使用极坐标方式控制麦克纳姆轮底盘，支持自定义速度、方向和角速度。这是最灵活的底盘控制方式。

**参数说明**：
- `velocity` (float): 移动速度，单位 mm/s
  - **允许范围**: 0.0 到 200.0 mm/s（建议不超过200mm/s）
  - **说明**: 正值表示向前移动，0表示停止移动。速度会被转换为各轮电机速度值（-100到100），过高的速度可能导致电机速度被限制
- `direction` (float): 移动方向角度，单位 度
  - **允许范围**: 0.0 到 360.0 度（支持负值，会自动转换为0-360范围）
  - **说明**: 移动方向在水平面的角度
    - 0度: 正前方（X轴正方向）
    - 90度: 正左方（Y轴正方向）
    - 180度: 正后方（X轴负方向）
    - 270度: 正右方（Y轴负方向）
- `angular_rate` (float): 角速度，单位 度/秒
  - **允许范围**: 约 -100.0 到 100.0 度/秒（建议不超过50度/秒）
  - **说明**: 底盘旋转的角速度
    - 正值: 逆时针旋转（从上往下看）
    - 负值: 顺时针旋转（从上往下看）
    - 0: 不旋转

**返回值**：
- `(True, (), 'SetMecanumVelocity')`: 成功
- `(False, 'E03 - Operation failed!', 'SetMecanumVelocity')`: 操作失败

**使用示例**：
```python
# 以100mm/s速度向45度方向移动，同时以10度/秒逆时针旋转
SetMecanumVelocity(100, 45, 10)

# 以50mm/s速度向正前方移动，不旋转
SetMecanumVelocity(50, 0, 0)

# 停止移动
SetMecanumVelocity(0, 0, 0)

# 原地旋转，不移动
SetMecanumVelocity(0, 0, 30)
```

**注意事项**：
- 速度、方向和角速度可以同时设置，实现复杂运动
- **速度限制**：
  - 速度值会被转换为各轮电机速度（-100到100），过高的velocity值可能导致实际速度被限制
  - 建议速度不超过200mm/s，避免失控和电机过载
  - 速度计算：v = sqrt(vx² + vy²)，其中vx和vy由velocity和direction计算得出
- **角速度限制**：
  - 角速度建议不超过50度/秒，过高的角速度可能导致底盘不稳定
  - 角速度会影响各轮速度分配，过高的角速度可能导致某些轮子速度被限制
- **组合限制**：
  - velocity、direction和angular_rate的组合必须满足各轮速度在-100到100范围内
  - 当velocity和angular_rate同时较大时，某些轮子可能达到速度上限

---

#### SetMecanumTranslation(velocity_x, velocity_y)
**级别**：一级  
**功能描述**：使用笛卡尔坐标（X、Y方向）控制麦克纳姆轮底盘平移。更直观的控制方式，适合需要精确控制X、Y方向速度的场景。

**参数说明**：
- `velocity_x` (float): X方向速度，单位 mm/s
  - 正值: 向右移动
  - 负值: 向左移动
  - 0: X方向不移动
- `velocity_y` (float): Y方向速度，单位 mm/s
  - 正值: 向前移动
  - 负值: 向后移动
  - 0: Y方向不移动

**返回值**：
- `(True, (), 'SetMecanumTranslation')`: 成功
- `(False, 'E03 - Operation failed!', 'SetMecanumTranslation')`: 操作失败

**使用示例**：
```python
# 向右前方移动（X=50, Y=50）
SetMecanumTranslation(50, 50)

# 只向右移动，不前后移动
SetMecanumTranslation(50, 0)

# 只向前移动，不左右移动
SetMecanumTranslation(0, 50)

# 停止移动
SetMecanumTranslation(0, 0)
```

**注意事项**：
- 此方法只控制平移，不控制旋转
- 速度会自动转换为极坐标形式
- 建议速度不超过200mm/s

---

#### SetMovementAngle(angle)
**级别**：一级  
**功能描述**：控制麦克纳姆轮底盘向指定方向移动，速度固定为70mm/s。这是简化版的移动控制，如需自定义速度请使用SetMecanumVelocity。

**参数说明**：
- `angle` (float): 移动方向角度，范围 0-360度
  - 0度: 正前方
  - 90度: 正左方
  - 180度: 正后方
  - 270度: 正右方
  - -1: 停止移动

**返回值**：
- `(True, (), 'SetMovementAngle')`: 成功
- `(False, 'E03 - Operation failed!', 'SetMovementAngle')`: 操作失败

**使用示例**：
```python
# 向45度方向移动（右前方）
SetMovementAngle(45)

# 停止移动
SetMovementAngle(-1)

# 向正前方移动
SetMovementAngle(0)
```

**注意事项**：
- 速度固定为70mm/s，无法自定义
- 角速度固定为0，无法旋转
- 如需更灵活的控制，请使用SetMecanumVelocity

---

#### GetMecanumStatus()
**级别**：一级  
**功能描述**：查询底盘当前的移动状态，包括速度、方向和角速度。用于监控底盘运动状态。

**参数说明**：无参数

**返回值**：
- `(True, status, 'GetMecanumStatus')`: 成功，返回字典包含：
  - `velocity` (float): 当前速度 (mm/s)
  - `direction` (float): 当前方向角度 (0-360度)
  - `angular_rate` (float): 当前角速度 (度/秒)
- `(False, 'E03 - Operation failed!', 'GetMecanumStatus')`: 操作失败

**使用示例**：
```python
# 查询底盘状态
result = GetMecanumStatus()
if result[0]:
    status = result[1]
    print(f"速度: {status['velocity']} mm/s")
    print(f"方向: {status['direction']} 度")
    print(f"角速度: {status['angular_rate']} 度/秒")
```

**注意事项**：
- 返回的是内部状态变量，可能不是实时硬件状态
- 如果底盘未初始化，可能返回默认值

---

#### ResetMecanumMotors()
**级别**：一级  
**功能描述**：停止所有电机并重置底盘状态（速度、方向、角速度归零）。用于紧急停止或初始化底盘状态。

**参数说明**：无参数

**返回值**：
- `(True, (), 'ResetMecanumMotors')`: 成功
- `(False, 'E03 - Operation failed!', 'ResetMecanumMotors')`: 操作失败

**使用示例**：
```python
# 紧急停止底盘
ResetMecanumMotors()

# 初始化底盘状态
ResetMecanumMotors()
```

**注意事项**：
- 会立即停止所有4个电机
- 重置内部状态变量
- 建议在程序开始和结束时调用

---

### 4. 功能模块管理

#### LoadFunc(new_func = 0)
**级别**：一级  
**功能描述**：加载指定的功能模块。功能模块包括各种视觉识别和自动控制功能。加载后需要调用StartFunc才能启动功能。

**参数说明**：
- `new_func` (int): 功能ID
  - 0: 无功能
  - 1: 遥控功能（RemoteControl）
  - 2: 颜色检测（ColorDetect）
  - 3: 颜色分拣（ColorSorting）
  - 4: 颜色跟踪（ColorTracking）
  - 5: 视觉巡线（VisualPatrol）
  - 6: 智能避障（Avoidance）
  - 9: LAB颜色校准（lab_adjust）

**返回值**：
- `(True, (功能ID,), 'LoadFunc')`: 成功，通过主线程队列执行

**使用示例**：
```python
# 加载颜色检测功能
LoadFunc(2)

# 加载避障功能
LoadFunc(6)
```

**注意事项**：
- 加载功能会先停止当前运行的功能
- 加载后需要调用StartFunc启动
- 功能ID必须在有效范围内（1-9，除了7、8）

---

#### UnloadFunc()
**级别**：一级  
**功能描述**：卸载当前加载的功能模块，停止所有相关功能。

**参数说明**：无参数

**返回值**：
- `(True, (0,), 'UnloadFunc')`: 成功，通过主线程队列执行

**使用示例**：
```python
# 卸载当前功能
UnloadFunc()
```

**注意事项**：
- 会先停止当前功能，然后卸载
- 卸载后功能ID变为0

---

#### StartFunc()
**级别**：一级  
**功能描述**：启动已加载的功能模块，开始执行功能逻辑。

**参数说明**：无参数

**返回值**：
- `(True, (功能ID,), 'StartFunc')`: 成功，返回当前功能ID

**使用示例**：
```python
# 先加载功能
LoadFunc(2)  # 加载颜色检测
# 然后启动
StartFunc()
```

**注意事项**：
- 需要先加载功能（LoadFunc）才能启动
- 如果未加载功能，启动会失败

---

#### StopFunc()
**级别**：一级  
**功能描述**：停止当前正在运行的功能模块，但保持加载状态。可以再次调用StartFunc重新启动。

**参数说明**：无参数

**返回值**：
- `(True, (功能ID,), 'StopFunc')`: 成功，返回当前功能ID

**使用示例**：
```python
# 停止当前功能
StopFunc()
# 稍后可以重新启动
StartFunc()
```

**注意事项**：
- 停止后功能模块仍然加载，可以重新启动
- 与UnloadFunc不同，UnloadFunc会完全卸载功能

---

#### FinishFunc()
**级别**：一级  
**功能描述**：完成功能模块执行。用于结束当前功能模块的运行。

**参数说明**：无参数

**返回值**：
- `(True, 结果, 'FinishFunc')`: 成功，通过主线程队列执行，返回结果

**使用示例**：
```python
# 完成当前功能
FinishFunc()
```

**注意事项**：
- 通过主线程队列执行
- 用于功能模块的清理和结束

---

#### GetRunningFunc()
**级别**：一级  
**功能描述**：查询当前加载的功能模块ID。

**参数说明**：无参数

**返回值**：
- `(True, (功能ID,), 'GetRunningFunc')`: 成功，返回当前功能ID
  - 0: 无功能
  - 1-9: 对应功能ID

**使用示例**：
```python
# 查询当前功能
result = GetRunningFunc()
if result[0]:
    func_id = result[1][0]
    print(f"当前功能ID: {func_id}")
```

**注意事项**：
- 返回的是已加载的功能ID，不一定是正在运行的
- 要检查是否运行，需要结合StartFunc/StopFunc状态

---

#### Heartbeat()
**级别**：一级  
**功能描述**：心跳检测，用于保持连接和功能状态。定期调用可以防止功能模块因超时自动卸载。

**参数说明**：无参数

**返回值**：
- `(True, (), 'Heartbeat')`: 成功，通过主线程队列执行

**使用示例**：
```python
# 发送心跳
Heartbeat()
```

**注意事项**：
- 建议每15秒内调用一次，防止功能模块超时
- 通过主线程队列执行
- 超时时间为15秒

---

### 5. 视觉功能（高级应用）

#### ColorDetect(*target_color)
**级别**：一级  
**功能描述**：设置颜色检测功能要检测的目标颜色。需要先加载颜色检测功能（LoadFunc(2)）并启动（StartFunc()）。

**参数说明**：
- `target_color` (str, ...): 目标颜色，可以设置多个
  - "red": 红色
  - "green": 绿色
  - "blue": 蓝色
  - 可以同时设置多个颜色，如 ("red", "green", "blue")

**返回值**：通过主线程队列执行，返回结果

**使用示例**：
```python
# 检测红色
LoadFunc(2)
StartFunc()
ColorDetect("red")

# 检测多种颜色
ColorDetect("red", "green", "blue")
```

**注意事项**：
- 需要先加载并启动颜色检测功能
- 颜色名称必须是小写英文
- 可以同时检测多种颜色

---

#### ColorTracking(*target_color)
**级别**：一级  
**功能描述**：设置颜色跟踪功能的目标颜色。自动跟踪指定颜色的物体。

**参数说明**：
- `target_color` (str, ...): 目标颜色，可以设置多个

**返回值**：通过主线程队列执行，返回结果

**使用示例**：
```python
LoadFunc(4)
StartFunc()
ColorTracking("red")
```

---

#### ColorTrackingWheel(new_st = 0)
**级别**：一级  
**功能描述**：设置颜色跟踪功能的轮子控制状态。

**参数说明**：
- `new_st` (int): 轮子控制状态，默认0

**返回值**：通过主线程队列执行，返回结果

---

#### ColorSorting(*target_color)
**级别**：一级  
**功能描述**：设置颜色分拣功能的目标颜色。完整的颜色分拣业务逻辑。

**参数说明**：
- `target_color` (str, ...): 目标颜色，可以设置多个

**返回值**：通过主线程队列执行，返回结果

**使用示例**：
```python
LoadFunc(3)
StartFunc()
ColorSorting("red", "green", "blue")
```

---

#### VisualPatrol(*target_color)
**级别**：一级  
**功能描述**：设置视觉巡线功能的目标颜色。自动导航功能。

**参数说明**：
- `target_color` (str, ...): 目标颜色，可以设置多个

**返回值**：通过主线程队列执行，返回结果

**使用示例**：
```python
LoadFunc(5)
StartFunc()
VisualPatrol("red")
```

---

#### Avoidance(*target_color)
**级别**：一级  
**功能描述**：设置智能避障功能的目标颜色。自动避障逻辑。

**参数说明**：
- `target_color` (str, ...): 目标颜色，可以设置多个

**返回值**：通过主线程队列执行，返回结果

**使用示例**：
```python
LoadFunc(6)
StartFunc()
Avoidance("red")
```

---

#### SetAvoidanceSpeed(speed=50)
**级别**：一级  
**功能描述**：设置避障功能模块的移动速度。避障功能会根据超声波传感器检测到的障碍物自动调整移动方向。

**参数说明**：
- `speed` (int): 移动速度，默认50，范围建议 0-100
  - 值越大，移动速度越快
  - 0: 停止

**返回值**：通过主线程队列执行，返回结果

**使用示例**：
```python
# 设置避障速度为50
SetAvoidanceSpeed(50)

# 设置较慢的避障速度
SetAvoidanceSpeed(30)
```

**注意事项**：
- 需要先加载避障功能（LoadFunc(6)）
- 速度值建议在30-70之间，过快可能导致避障不及时

---

#### SetSonarDistanceThreshold(new_threshold=30)
**级别**：一级  
**功能描述**：设置避障功能触发的最小距离阈值。当检测到障碍物距离小于此阈值时，会触发避障动作。

**参数说明**：
- `new_threshold` (int): 距离阈值，单位 cm，默认30
  - 值越小，越接近障碍物才避障
  - 值越大，越早开始避障
  - 建议范围：20-50 cm

**返回值**：通过主线程队列执行，返回结果

**使用示例**：
```python
# 设置阈值为30cm
SetSonarDistanceThreshold(30)

# 设置较敏感的阈值（40cm）
SetSonarDistanceThreshold(40)
```

**注意事项**：
- 需要先加载避障功能（LoadFunc(6)）
- 阈值过小可能导致碰撞
- 阈值过大可能导致频繁避障

---

#### GetSonarDistanceThreshold()
**级别**：一级  
**功能描述**：查询当前设置的避障距离阈值。

**参数说明**：无参数

**返回值**：通过主线程队列执行，返回当前阈值（单位：cm）

**使用示例**：
```python
# 查询当前阈值
result = GetSonarDistanceThreshold()
if result[0]:
    threshold = result[1]
    print(f"当前避障阈值: {threshold} cm")
```

**注意事项**：
- 需要先加载避障功能（LoadFunc(6)）

---

### 6. 颜色校准（高级功能）

#### SetLABValue(*lab_value)
**级别**：一级  
**功能描述**：设置LAB颜色阈值，用于颜色识别校准。

**参数说明**：
- `lab_value`: LAB颜色阈值数据
  - 格式：`[{'red': ((0, 0, 0), (255, 255, 255))}]`

**返回值**：通过主线程队列执行，返回结果

**使用示例**：
```python
# 设置红色LAB阈值
lab_value = [{'red': ((0, 0, 0), (255, 255, 255))}]
SetLABValue(lab_value)
```

---

#### GetLABValue()
**级别**：一级  
**功能描述**：获取当前设置的LAB颜色阈值。

**参数说明**：无参数

**返回值**：
- `(True, lab_value, 'GetLABValue')`: 成功，返回LAB阈值数据

**使用示例**：
```python
result = GetLABValue()
if result[0]:
    lab_data = result[1]
    print(f"LAB阈值: {lab_data}")
```

---

#### SaveLABValue(color='')
**级别**：一级  
**功能描述**：保存LAB颜色阈值到配置文件。

**参数说明**：
- `color` (str): 颜色名称，可选

**返回值**：通过主线程队列执行，返回结果

**使用示例**：
```python
# 保存所有颜色阈值
SaveLABValue()

# 保存特定颜色阈值
SaveLABValue('red')
```

---

#### HaveLABAdjust()
**级别**：一级  
**功能描述**：检查是否有LAB校准功能。

**参数说明**：无参数

**返回值**：
- `(True, True, 'HaveLABAdjust')`: 支持LAB校准

---

### 7. 传感器读取（高级接口）

#### GetSonarDistance()
**级别**：一级  
**功能描述**：读取超声波传感器检测到的距离值。需要确保超声波传感器已正确初始化。

**参数说明**：无参数

**返回值**：
- `(True, distance, 'GetSonarDistance')`: 成功，返回距离值（单位：cm）
- `(False, 'E03 - Operation failed!', 'GetSonarDistance')`: 操作失败

**使用示例**：
```python
# 读取距离
result = GetSonarDistance()
if result[0]:
    distance = result[1]
    print(f"检测到距离: {distance} cm")
```

**注意事项**：
- 需要确保HWSONAR已正确初始化
- 距离值单位是厘米（cm）
- 检测范围通常为2-400cm
- 如果传感器未初始化，会返回错误

---

#### GetBatteryVoltage()
**级别**：一级  
**功能描述**：读取扩展板检测到的电池电压值。用于监控电池电量，防止电压过低损坏设备。

**参数说明**：无参数

**返回值**：
- `(True, voltage, 'GetBatteryVoltage')`: 成功，返回电压值（单位：mV，毫伏）
- `(False, 'E03 - Operation failed!', 'GetBatteryVoltage')`: 操作失败

**使用示例**：
```python
# 读取电池电压
result = GetBatteryVoltage()
if result[0]:
    voltage_mv = result[1]
    voltage_v = voltage_mv / 1000.0
    print(f"电池电压: {voltage_v:.2f} V")
    
    # 检查电压是否过低（例如低于7.2V）
    if voltage_v < 7.2:
        print("警告：电池电压过低！")
```

**注意事项**：
- 返回值单位是毫伏（mV），需要除以1000得到伏特（V）
- 正常电压范围：7.0V - 8.4V（2S锂电池）
- 建议电压低于7.2V时停止使用，避免过放

---

### 8. RGB灯控制（高级接口）

#### SetSonarRGB(index, r, g, b)
**级别**：一级  
**功能描述**：设置超声波传感器上RGB灯的颜色。如果index为0，会同时设置两个LED灯。

**参数说明**：
- `index` (int): LED索引
  - 0: 同时设置两个LED
  - 1: 设置LED 1
  - 2: 设置LED 2
- `r` (int): 红色分量，范围 0-255
- `g` (int): 绿色分量，范围 0-255
- `b` (int): 蓝色分量，范围 0-255

**返回值**：
- `(True, (r, g, b), 'SetSonarRGB')`: 成功

**使用示例**：
```python
# 设置为红色
SetSonarRGB(0, 255, 0, 0)

# 设置为绿色
SetSonarRGB(1, 0, 255, 0)

# 设置为蓝色
SetSonarRGB(2, 0, 0, 255)
```

**注意事项**：
- 需要确保HWSONAR已正确初始化
- RGB值会被限制在0-255范围内

---

#### SetSonarRGBMode(mode = 0)
**级别**：一级  
**功能描述**：设置超声波传感器上RGB灯的工作模式。

**参数说明**：
- `mode` (int): 模式值，默认0
  - 0: 关闭模式
  - 其他值: 根据具体实现定义

**返回值**：
- `(True, (mode,), 'SetSonarRGBMode')`: 成功

**使用示例**：
```python
# 关闭RGB灯
SetSonarRGBMode(0)
```

**注意事项**：
- 需要确保HWSONAR已正确初始化

---

#### SetSonarRGBBreathCycle(index, color, cycle)
**级别**：一级  
**功能描述**：设置超声波传感器RGB灯的呼吸效果参数。呼吸效果是指LED灯逐渐变亮再变暗的循环效果。

**参数说明**：
- `index` (int): LED索引，范围 0-1
- `color` (tuple): 颜色值，格式 (r, g, b)，范围 0-255
- `cycle` (int): 呼吸周期，单位毫秒

**返回值**：
- `(True, (index, color, cycle), 'SetSonarRGBBreathCycle')`: 成功

**使用示例**：
```python
# 设置LED 0为红色呼吸效果，周期1000ms
SetSonarRGBBreathCycle(0, (255, 0, 0), 1000)
```

**注意事项**：
- 需要调用SetSonarRGBStartSymphony启动效果
- 需要确保HWSONAR已正确初始化

---

#### SetSonarRGBStartSymphony()
**级别**：一级  
**功能描述**：启动已设置的RGB灯呼吸效果。需要先调用SetSonarRGBBreathCycle设置参数。

**参数说明**：无参数

**返回值**：
- `(True, (), 'SetSonarRGBStartSymphony')`: 成功

**使用示例**：
```python
# 先设置呼吸效果
SetSonarRGBBreathCycle(0, (255, 0, 0), 1000)
# 然后启动
SetSonarRGBStartSymphony()
```

**注意事项**：
- 需要先设置呼吸效果参数
- 需要确保HWSONAR已正确初始化

---

#### SetBoardRGB(index, r, g, b)
**级别**：一级  
**功能描述**：设置扩展板RGB灯颜色。

**参数说明**：
- `index` (int): LED索引，范围 0-1
- `r` (int): 红色值，范围 0-255
- `g` (int): 绿色值，范围 0-255
- `b` (int): 蓝色值，范围 0-255

**返回值**：
- `(True, (), 'SetBoardRGB')`: 成功
- `(False, 'E02 - Invalid parameter!', 'SetBoardRGB')`: 参数错误
- `(False, 'E03 - Operation failed!', 'SetBoardRGB')`: 操作失败

**使用示例**：
```python
# 设置LED 0为红色
SetBoardRGB(0, 255, 0, 0)

# 设置LED 1为绿色
SetBoardRGB(1, 0, 255, 0)
```

---

#### SetBoardRGBOff()
**级别**：一级  
**功能描述**：关闭所有扩展板RGB灯。

**参数说明**：无参数

**返回值**：
- `(True, (), 'SetBoardRGBOff')`: 成功
- `(False, 'E03 - Operation failed!', 'SetBoardRGBOff')`: 操作失败

**使用示例**：
```python
# 关闭所有RGB灯
SetBoardRGBOff()
```

---

### 9. 其他高级功能

#### SetBuzzer(state)
**级别**：一级  
**功能描述**：控制扩展板上的蜂鸣器开关。

**参数说明**：
- `state` (bool): 蜂鸣器状态
  - True: 开启蜂鸣器
  - False: 关闭蜂鸣器

**返回值**：
- `(True, (), 'SetBuzzer')`: 成功
- `(False, 'E03 - Operation failed!', 'SetBuzzer')`: 操作失败

**使用示例**：
```python
# 开启蜂鸣器
SetBuzzer(True)

# 关闭蜂鸣器
SetBuzzer(False)
```

**注意事项**：
- 蜂鸣器会持续响，直到设置为False
- 建议短时间使用，避免噪音

---

#### StopAllMotors()
**级别**：一级  
**功能描述**：立即停止所有4个刷式电机，用于紧急停止。

**参数说明**：无参数

**返回值**：
- `(True, (), 'StopAllMotors')`: 成功
- `(False, 'E03 - Operation failed!', 'StopAllMotors')`: 操作失败

**使用示例**：
```python
# 紧急停止所有电机
StopAllMotors()
```

**注意事项**：
- 会立即停止所有4个电机（ID 1-4）
- 等同于 SetBrushMotor(1, 0, 2, 0, 3, 0, 4, 0)

---

## 二级功能（底层功能）

### 1. PWM舵机底层控制

#### SetPWMServo(*args, **kwargs)
**级别**：二级  
**功能描述**：同时控制多个PWM舵机，通过角度值（-90到90度）设置位置。角度值会自动转换为脉冲值（500-2500）。

**参数格式**：
```
SetPWMServo(use_time, servo_count, servo_id1, angle1, servo_id2, angle2, ...)
```

**参数说明**：
- `use_time` (int): 运行时间，单位毫秒，范围 0-30000
- `servo_count` (int): 要控制的舵机数量
- `servo_id` (int): 舵机ID，范围 1-6
- `angle` (float): 角度值，范围 -90 到 90 度
  - 90度对应脉冲值2500
  - 0度对应脉冲值1500（中位）
  - -90度对应脉冲值500

**返回值**：
- `(True, (), 'SetPWMServo')`: 成功
- `(False, 'E03 - Operation failed!', 'SetPWMServo')`: 失败

**使用示例**：
```python
# 控制2个舵机，用时1000ms
SetPWMServo(1000, 2, 1, 90, 2, -90)
# 舵机1转到90度，舵机2转到-90度
```

**注意事项**：
- 角度值会自动映射到脉冲值范围
- 可以同时控制最多6个舵机
- 所有舵机使用相同的运行时间

---

#### SetPWMServoPulseSingle(servo_id, pulse, use_time)
**级别**：二级  
**功能描述**：控制单个PWM舵机，通过脉冲值直接设置位置。适用于需要精确控制单个舵机的场景。

**参数说明**：
- `servo_id` (int): 舵机ID，范围 1-6
- `pulse` (int): 脉冲值，范围 500-2500
  - 500: 最小位置（-90度）
  - 1500: 中位（0度）
  - 2500: 最大位置（90度）
- `use_time` (int): 运行时间，单位毫秒，范围 0-30000

**返回值**：
- `(True, (), 'SetPWMServoPulseSingle')`: 成功
- `(False, 'E02 - Invalid parameter!', 'SetPWMServoPulseSingle')`: 参数错误
- `(False, 'E03 - Operation failed!', 'SetPWMServoPulseSingle')`: 操作失败

**使用示例**：
```python
# 控制舵机1转到中位，用时500ms
SetPWMServoPulseSingle(1, 1500, 500)

# 控制舵机3转到最大位置，用时1000ms
SetPWMServoPulseSingle(3, 2500, 1000)
```

**注意事项**：
- 脉冲值会被自动限制在500-2500范围内
- 运行时间会被自动限制在0-30000ms范围内
- 如果舵机ID超出范围，返回E02错误

---

#### SetPWMServoAngle(servo_id, angle)
**级别**：二级  
**功能描述**：通过角度值控制PWM舵机，更直观的控制方式。角度值会自动转换为对应的脉冲值。

**参数说明**：
- `servo_id` (int): 舵机ID，范围 1-6
- `angle` (float): 角度值，范围 0-180度
  - 0度: 最小位置
  - 90度: 中位
  - 180度: 最大位置

**返回值**：
- `(True, (), 'SetPWMServoAngle')`: 成功
- `(False, 'E02 - Invalid parameter!', 'SetPWMServoAngle')`: 参数错误
- `(False, 'E03 - Operation failed!', 'SetPWMServoAngle')`: 操作失败

**使用示例**：
```python
# 控制舵机1转到90度（中位）
SetPWMServoAngle(1, 90)

# 控制舵机2转到0度
SetPWMServoAngle(2, 0)
```

**注意事项**：
- 角度值会被自动限制在0-180度范围内
- 如果舵机ID超出范围，返回E02错误
- 此方法使用默认运行时间

---

#### GetPWMServoPulse(servo_id)
**级别**：二级  
**功能描述**：读取指定PWM舵机当前的脉冲值，用于查询舵机位置。

**参数说明**：
- `servo_id` (int): 舵机ID，范围 1-6

**返回值**：
- `(True, pulse_value, 'GetPWMServoPulse')`: 成功，返回脉冲值（500-2500）
- `(False, 'E02 - Invalid parameter!', 'GetPWMServoPulse')`: 参数错误
- `(False, 'E03 - Operation failed!', 'GetPWMServoPulse')`: 操作失败

**使用示例**：
```python
# 读取舵机1的当前脉冲值
result = GetPWMServoPulse(1)
if result[0]:  # 检查是否成功
    pulse = result[1]  # 获取脉冲值
    print(f"舵机1当前脉冲值: {pulse}")
```

**注意事项**：
- 返回的是内部缓存的脉冲值，可能不是实时读取
- 如果舵机ID超出范围，返回E02错误

---

#### GetPWMServoAngle(servo_id)
**级别**：二级  
**功能描述**：读取指定PWM舵机当前的角度值，用于查询舵机位置。角度值由脉冲值计算得出。

**参数说明**：
- `servo_id` (int): 舵机ID，范围 1-6

**返回值**：
- `(True, angle_value, 'GetPWMServoAngle')`: 成功，返回角度值（0-180度）
- `(False, 'E02 - Invalid parameter!', 'GetPWMServoAngle')`: 参数错误
- `(False, 'E03 - Operation failed!', 'GetPWMServoAngle')`: 操作失败

**使用示例**：
```python
# 读取舵机1的当前角度
result = GetPWMServoAngle(1)
if result[0]:  # 检查是否成功
    angle = result[1]  # 获取角度值
    print(f"舵机1当前角度: {angle}度")
```

**注意事项**：
- 返回的角度值由脉冲值计算得出，可能不是实时读取
- 如果舵机ID超出范围，返回E02错误

---

### 2. 总线舵机底层控制

#### SetBusServoPulse(*args, **kwargs)
**级别**：二级  
**功能描述**：同时控制多个总线舵机（串口舵机），通过脉冲值设置位置。总线舵机通常用于机械臂等需要精确控制的场景。

**参数格式**：
```
SetBusServoPulse(use_time, servo_count, servo_id1, pulse1, servo_id2, pulse2, ...)
```

**参数说明**：
- `use_time` (int): 运行时间，单位毫秒，范围 0-30000
- `servo_count` (int): 要控制的舵机数量
- `servo_id` (int): 舵机ID，范围 1-6
- `pulse` (int): 脉冲值，范围 0-1000
  - 0: 最小位置
  - 500: 中位
  - 1000: 最大位置

**返回值**：
- `(True, (), 'SetBusServoPulse')`: 成功
- `(False, 'E01 - Invalid number of parameter!', 'SetBusServoPulse')`: 参数数量错误
- `(False, 'E02 - Invalid parameter!', 'SetBusServoPulse')`: 参数值错误
- `(False, 'E03 - Operation failed!', 'SetBusServoPulse')`: 操作失败

**使用示例**：
```python
# 控制2个总线舵机，用时1000ms
SetBusServoPulse(1000, 2, 1, 500, 2, 500)
# 舵机1和2都转到中位
```

**注意事项**：
- 脉冲值会被自动限制在0-1000范围内
- 所有舵机使用相同的运行时间
- 总线舵机与PWM舵机不同，使用串口通信

---

#### SetBusServoDeviation(*args)
**级别**：二级  
**功能描述**：设置总线舵机的角度偏差值，用于校准舵机位置。偏差值会在设置脉冲值时自动应用。

**参数说明**：
- `servo_id` (int): 舵机ID，范围 1-6
- `deviation` (int): 偏差值，范围通常 -125 到 125

**返回值**：
- `(True, (), 'SetBusServoDeviation')`: 成功
- `(False, 'E01 - Invalid number of parameter!', 'SetBusServoDeviation')`: 参数数量错误
- `(False, 'E03 - Operation failed!', 'SetBusServoDeviation')`: 操作失败

**使用示例**：
```python
# 设置舵机1的偏差为10
SetBusServoDeviation(1, 10)

# 设置舵机2的偏差为-5
SetBusServoDeviation(2, -5)
```

**注意事项**：
- 偏差值只是临时设置，不会保存
- 要永久保存，需要调用SaveBusServosDeviation
- 偏差值会在下次设置脉冲时应用

---

#### GetBusServosDeviation(args)
**级别**：二级  
**功能描述**：读取所有总线舵机（1-6）的当前偏差值。

**参数说明**：
- `args` (str): 必须为字符串 "readDeviation"

**返回值**：
- `(True, [dev1, dev2, ..., dev6], 'GetBusServosDeviation')`: 成功，返回6个舵机的偏差值列表
- `(False, 'E01 - Invalid number of parameter!', 'GetBusServosDeviation')`: 参数错误
- `(False, 'E03 - Operation failed!', 'GetBusServosDeviation')`: 操作失败

**使用示例**：
```python
# 读取所有舵机偏差
result = GetBusServosDeviation("readDeviation")
if result[0]:
    deviations = result[1]
    for i, dev in enumerate(deviations, 1):
        print(f"舵机{i}偏差: {dev}")
```

**注意事项**：
- 如果读取失败，对应位置返回999
- 需要确保总线舵机已正确连接

---

#### SaveBusServosDeviation(args)
**级别**：二级  
**功能描述**：将当前设置的所有总线舵机偏差值保存到舵机内部存储器。保存后，偏差值会在断电后仍然保留。

**参数说明**：
- `args` (str): 必须为字符串 "downloadDeviation"

**返回值**：
- `(True, (), 'SaveBusServosDeviation')`: 成功
- `(False, 'E01 - Invalid number of parameter!', 'SaveBusServosDeviation')`: 参数错误
- `(False, 'E03 - Operation failed!', 'SaveBusServosDeviation')`: 操作失败

**使用示例**：
```python
# 先设置偏差
SetBusServoDeviation(1, 10)
SetBusServoDeviation(2, -5)

# 保存偏差值
SaveBusServosDeviation("downloadDeviation")
```

**注意事项**：
- 保存操作会应用到所有6个舵机
- 保存需要一定时间，请等待操作完成
- 保存后偏差值会永久生效，直到重新设置

---

#### UnloadBusServo(args)
**级别**：二级  
**功能描述**：使所有总线舵机进入掉电状态，舵机会失去保持力。用于节省功耗或安全停止。

**参数说明**：
- `args` (str): 必须为字符串 "servoPowerDown"

**返回值**：
- `(True, (), 'UnloadBusServo')`: 成功
- `(False, 'E01 - Invalid number of parameter!', 'UnloadBusServo')`: 参数错误
- `(False, 'E03 - Operation failed!', 'UnloadBusServo')`: 操作失败

**使用示例**：
```python
# 卸载所有舵机
UnloadBusServo("servoPowerDown")
```

**注意事项**：
- 掉电后舵机会失去保持力，可能因重力下垂
- 需要重新设置脉冲值才能恢复工作
- 适用于长时间不使用的情况

---

#### GetBusServosPulse(args)
**级别**：二级  
**功能描述**：读取所有总线舵机（1-6）的当前脉冲值，用于查询舵机位置。

**参数说明**：
- `args` (str): 必须为字符串 "angularReadback"

**返回值**：
- `(True, [pulse1, pulse2, ..., pulse6], 'GetBusServosPulse')`: 成功，返回6个舵机的脉冲值列表（0-1000）
- `(False, 'E01 - Invalid number of parameter!', 'GetBusServosPulse')`: 参数错误
- `(False, 'E04 - Operation timeout!', 'GetBusServosPulse')`: 读取超时
- `(False, 'E03 - Operation failed!', 'GetBusServosPulse')`: 操作失败

**使用示例**：
```python
# 读取所有舵机位置
result = GetBusServosPulse("angularReadback")
if result[0]:
    pulses = result[1]
    for i, pulse in enumerate(pulses, 1):
        print(f"舵机{i}位置: {pulse}")
```

**注意事项**：
- 读取操作可能需要一定时间
- 如果某个舵机读取失败，会返回E04超时错误
- 需要确保总线舵机已正确连接

---

#### SetBusServoID(oldid, newid)
**级别**：二级  
**功能描述**：修改总线舵机的ID号。用于配置多个舵机时区分不同舵机。出厂默认ID为1。

**参数说明**：
- `oldid` (int): 原ID号
- `newid` (int): 新ID号，范围 1-253

**返回值**：
- `(True, (), 'SetBusServoID')`: 成功
- `(False, 'E03 - Operation failed!', 'SetBusServoID')`: 操作失败

**使用示例**：
```python
# 将ID为1的舵机改为ID 2
SetBusServoID(1, 2)
```

**注意事项**：
- 修改ID后需要重新连接才能使用新ID
- ID范围：1-253
- 确保总线上只有一个舵机时才能修改ID

---

#### GetBusServoID(id=None)
**级别**：二级  
**功能描述**：读取指定总线舵机的ID号，或读取总线上唯一舵机的ID。

**参数说明**：
- `id` (int, optional): 舵机ID，如果为None则读取总线上唯一舵机

**返回值**：
- `(True, servo_id, 'GetBusServoID')`: 成功，返回舵机ID
- `(False, 'E03 - Operation failed!', 'GetBusServoID')`: 操作失败

**使用示例**：
```python
# 读取总线上唯一舵机的ID
result = GetBusServoID()

# 读取指定ID的舵机
result = GetBusServoID(1)
```

**注意事项**：
- 如果id为None，总线上只能有一个舵机
- 读取可能需要多次尝试

---

#### SetBusServoAngleLimit(id, low, high)
**级别**：二级  
**功能描述**：设置总线舵机的转动角度范围，限制舵机只能在指定范围内转动。用于保护硬件，防止舵机转动超出安全范围。

**参数说明**：
- `id` (int): 舵机ID，范围 1-6
- `low` (int): 最小角度，单位 0.24度
- `high` (int): 最大角度，单位 0.24度

**返回值**：
- `(True, (), 'SetBusServoAngleLimit')`: 成功
- `(False, 'E03 - Operation failed!', 'SetBusServoAngleLimit')`: 操作失败

**使用示例**：
```python
# 限制舵机1在0-240度范围内（0-1000脉冲）
SetBusServoAngleLimit(1, 0, 1000)
```

**注意事项**：
- 角度单位是0.24度，1000对应240度
- 设置后舵机只能在此范围内转动
- 用于保护硬件和防止碰撞

---

#### GetBusServoAngleLimit(id)
**级别**：二级  
**功能描述**：读取指定总线舵机的角度限制范围。

**参数说明**：
- `id` (int): 舵机ID，范围 1-6

**返回值**：
- `(True, (low, high), 'GetBusServoAngleLimit')`: 成功，返回元组 (最小角度, 最大角度)
- `(False, 'E03 - Operation failed!', 'GetBusServoAngleLimit')`: 操作失败

**使用示例**：
```python
# 读取舵机1的角度限制
result = GetBusServoAngleLimit(1)
if result[0]:
    low, high = result[1]
    print(f"角度范围: {low} - {high}")
```

**注意事项**：
- 角度单位是0.24度
- 如果读取失败，可能需要多次尝试

---

#### SetBusServoVinLimit(id, low, high)
**级别**：二级  
**功能描述**：设置总线舵机的工作电压范围。用于保护舵机，防止电压异常损坏。

**参数说明**：
- `id` (int): 舵机ID，范围 1-6
- `low` (int): 最小电压
- `high` (int): 最大电压

**返回值**：
- `(True, (), 'SetBusServoVinLimit')`: 成功
- `(False, 'E03 - Operation failed!', 'SetBusServoVinLimit')`: 操作失败

**使用示例**：
```python
# 设置舵机1的电压限制
SetBusServoVinLimit(1, 6000, 8400)  # 6V-8.4V
```

---

#### GetBusServoVinLimit(id)
**级别**：二级  
**功能描述**：读取总线舵机的电压限制范围。

**参数说明**：
- `id` (int): 舵机ID，范围 1-6

**返回值**：
- `(True, (low, high), 'GetBusServoVinLimit')`: 成功，返回元组 (最小电压, 最大电压)
- `(False, 'E03 - Operation failed!', 'GetBusServoVinLimit')`: 操作失败

---

#### SetBusServoMaxTemp(id, temp)
**级别**：二级  
**功能描述**：设置总线舵机的最高温度报警阈值。用于保护舵机，防止过热损坏。

**参数说明**：
- `id` (int): 舵机ID，范围 1-6
- `temp` (int): 最高温度

**返回值**：
- `(True, (), 'SetBusServoMaxTemp')`: 成功
- `(False, 'E03 - Operation failed!', 'SetBusServoMaxTemp')`: 操作失败

---

#### GetBusServoTempLimit(id)
**级别**：二级  
**功能描述**：读取总线舵机的温度限制阈值。

**参数说明**：
- `id` (int): 舵机ID，范围 1-6

**返回值**：
- `(True, temp, 'GetBusServoTempLimit')`: 成功，返回温度值
- `(False, 'E03 - Operation failed!', 'GetBusServoTempLimit')`: 操作失败

---

#### GetBusServoTemp(id)
**级别**：二级  
**功能描述**：读取总线舵机当前的工作温度。用于监控舵机温度，防止过热。

**参数说明**：
- `id` (int): 舵机ID，范围 1-6

**返回值**：
- `(True, temp, 'GetBusServoTemp')`: 成功，返回当前温度值
- `(False, 'E03 - Operation failed!', 'GetBusServoTemp')`: 操作失败

**使用示例**：
```python
# 读取舵机1的温度
result = GetBusServoTemp(1)
if result[0]:
    temp = result[1]
    print(f"舵机1温度: {temp}°C")
    if temp > 70:
        print("警告：舵机温度过高！")
```

---

#### GetBusServoVin(id)
**级别**：二级  
**功能描述**：读取总线舵机当前的工作电压。用于监控舵机工作电压。

**参数说明**：
- `id` (int): 舵机ID，范围 1-6

**返回值**：
- `(True, vin, 'GetBusServoVin')`: 成功，返回当前电压值
- `(False, 'E03 - Operation failed!', 'GetBusServoVin')`: 操作失败

**使用示例**：
```python
# 读取舵机1的电压
result = GetBusServoVin(1)
if result[0]:
    vin = result[1]
    print(f"舵机1电压: {vin} mV")
```

---

#### StopBusServoSingle(id)
**级别**：二级  
**功能描述**：停止单个总线舵机运行。用于紧急停止指定舵机。

**参数说明**：
- `id` (int): 舵机ID，范围 1-6

**返回值**：
- `(True, (), 'StopBusServoSingle')`: 成功
- `(False, 'E03 - Operation failed!', 'StopBusServoSingle')`: 操作失败

**使用示例**：
```python
# 停止舵机1
StopBusServoSingle(1)
```

---

#### GetBusServoLoadStatus(id)
**级别**：二级  
**功能描述**：读取总线舵机的负载状态。用于检查舵机是否掉电。

**参数说明**：
- `id` (int): 舵机ID，范围 1-6

**返回值**：
- `(True, status, 'GetBusServoLoadStatus')`: 成功，返回负载状态
- `(False, 'E03 - Operation failed!', 'GetBusServoLoadStatus')`: 操作失败

---

#### ResetBusServoPulse(id)
**级别**：二级  
**功能描述**：重置总线舵机位置。清零偏差并回到中位（500）。

**参数说明**：
- `id` (int): 舵机ID，范围 1-6

**返回值**：
- `(True, (), 'ResetBusServoPulse')`: 成功
- `(False, 'E03 - Operation failed!', 'ResetBusServoPulse')`: 操作失败

**使用示例**：
```python
# 重置舵机1到中位
ResetBusServoPulse(1)
```

---

### 3. 电机底层控制

#### SetBrushMotor(*args, **kwargs)
**级别**：二级  
**功能描述**：控制扩展板上的刷式电机速度，可以同时控制多个电机。电机编号：1-4，对应底盘的4个轮子。

**参数格式**：
```
SetBrushMotor(motor_id1, speed1, motor_id2, speed2, ...)
```

**参数说明**：
- `motor_id` (int): 电机ID，范围 1-4
  - 1: 电机1
  - 2: 电机2
  - 3: 电机3
  - 4: 电机4
- `speed` (int): 电机速度，范围 -100 到 100
  - 正值: 正转
  - 负值: 反转
  - 0: 停止
  - 绝对值越大，速度越快

**返回值**：
- `(True, (), 'SetBrushMotor')`: 成功
- `(False, 'E01 - Invalid number of parameter!', 'SetBrushMotor')`: 参数数量错误
- `(False, 'E02 - Invalid parameter!', 'SetBrushMotor')`: 参数值错误
- `(False, 'E03 - Operation failed!', 'SetBrushMotor')`: 操作失败

**使用示例**：
```python
# 控制电机1以速度50正转
SetBrushMotor(1, 50)

# 同时控制电机1和2
SetBrushMotor(1, 50, 2, -50)

# 停止所有电机
SetBrushMotor(1, 0, 2, 0, 3, 0, 4, 0)
```

**注意事项**：
- 参数必须是成对出现（电机ID + 速度）
- 速度会被自动限制在-100到100范围内
- 电机2和4的方向会自动反转（硬件特性）

---

#### GetMotor(index)
**级别**：二级  
**功能描述**：读取指定电机的当前速度值，用于查询电机状态。

**参数说明**：
- `index` (int): 电机ID，范围 1-4

**返回值**：
- `(True, speed_value, 'GetMotor')`: 成功，返回速度值（-100到100）
- `(False, 'E02 - Invalid parameter!', 'GetMotor')`: 参数错误
- `(False, 'E03 - Operation failed!', 'GetMotor')`: 操作失败

**使用示例**：
```python
# 读取电机1的当前速度
result = GetMotor(1)
if result[0]:
    speed = result[1]
    print(f"电机1当前速度: {speed}")
```

**注意事项**：
- 返回的是内部缓存的速度值，可能不是实时硬件状态
- 如果电机ID超出范围，返回E02错误

---

### 4. 工具函数

#### map(x, in_min, in_max, out_min, out_max)
**级别**：二级（内部使用）  
**功能描述**：数值映射工具函数，将输入值从一个范围映射到另一个范围。

**参数说明**：
- `x`: 输入值
- `in_min`: 输入范围最小值
- `in_max`: 输入范围最大值
- `out_min`: 输出范围最小值
- `out_max`: 输出范围最大值

**返回值**：映射后的值

**注意事项**：
- 这是内部工具函数，通常不需要直接调用

---

## 错误码说明

所有RPC方法返回统一的错误码格式：

- **E01 - Invalid number of parameter!**: 参数数量错误
- **E02 - Invalid parameter!**: 参数值错误（如超出范围）
- **E03 - Operation failed!**: 操作失败（硬件错误、异常等）
- **E04 - Operation timeout!**: 操作超时（通常用于读取操作）
- **E05 - Not callable**: 不可调用（内部错误）

**返回值格式**：
```python
(成功标志, 数据, 方法名)
# 成功: (True, data, 'MethodName')
# 失败: (False, '错误信息', 'MethodName')
```

---

## 使用指南

### 连接RPC服务器

**服务器地址**：`http://树莓派IP:9030` 或 `http://127.0.0.1:9030`

**Python客户端示例**：
```python
from jsonrpc import JSONRPCClient

# 连接到RPC服务器
client = JSONRPCClient('http://127.0.0.1:9030')

# 调用RPC方法
result = client.GetBatteryVoltage()
if result[0]:
    voltage = result[1]
    print(f"电池电压: {voltage} mV")
```

**curl示例**：
```bash
curl -X POST http://127.0.0.1:9030 \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "GetBatteryVoltage",
    "params": [],
    "id": 1
  }'
```

### 功能选择建议

#### 对于普通用户
- **推荐使用一级功能**：更简单、更安全、更直观
- 例如：
  - `SetGripperOpen()` 而不是 `SetPWMServoPulseSingle(1, 2000, 500)`
  - `SetMecanumVelocity()` 而不是 `SetBrushMotor()`
  - `ArmMoveIk()` 而不是直接控制多个舵机

#### 对于高级用户/开发者
- **可以使用二级功能**：更灵活、更精确、更底层
- 例如：
  - 需要精确控制时使用 `SetPWMServoPulseSingle()`
  - 需要调试硬件时使用 `GetBusServoTemp()`
  - 需要配置硬件时使用 `SetBusServoID()`

### 功能依赖关系

一级功能通常内部调用二级功能：
- `SetGripperOpen()` → `SetPWMServoPulseSingle()` → `Board.setPWMServoPulse()`
- `SetMecanumVelocity()` → `chassis.set_velocity()` → `SetBrushMotor()`
- `ArmMoveIk()` → `SetBusServoPulse()` + `SetPWMServoPulseSingle()`

### 最佳实践

1. **优先使用一级功能**：除非有特殊需求，否则优先使用一级功能
2. **错误处理**：始终检查返回值的第一项（成功标志）
3. **参数验证**：确保参数在有效范围内
4. **线程安全**：所有硬件操作都通过主线程队列执行，确保安全
5. **资源管理**：使用完毕后及时停止功能模块

---

## 功能统计

### 按级别分类

- **一级功能（上层功能）**：35 个
  - 机械臂高级操作：3个
  - 夹持器操作：4个
  - Mecanum底盘高级操作：5个
  - 功能模块管理：7个
  - 视觉功能：9个
  - 颜色校准：4个
  - 传感器读取：2个
  - RGB灯控制：6个
  - 其他高级功能：2个

- **二级功能（底层功能）**：36 个
  - PWM舵机底层控制：5个
  - 总线舵机底层控制：18个
  - 电机底层控制：2个
  - 工具函数：1个

### 按功能类别分类

- **舵机控制**：23个（PWM舵机5个 + 总线舵机18个）
- **底盘控制**：7个（Mecanum底盘5个 + 电机2个）
- **机械臂控制**：3个
- **夹持器控制**：4个
- **视觉功能**：9个
- **传感器**：2个
- **RGB灯控制**：6个
- **功能管理**：7个
- **其他**：10个

### 总体统计

- **总功能数**：71 个 RPC 方法
- **功能覆盖率**：100% HiwonderSDK 功能
- **文档完整度**：所有功能都有详细注释

---

## 更新历史

- **2024年**：完整实现所有 HiwonderSDK 功能，添加详细注释
- **2024年**：新增30+个功能，包括PWM舵机、总线舵机、Mecanum底盘、夹持器等完整功能
- **2024年**：统一功能文档，合并分类、对比和新增功能列表

---

## 技术支持

如有问题或建议，请参考：
- MasterPi 官方文档
- HiwonderSDK 文档
- GitHub 仓库：https://github.com/zhaozhichen/masterpi

---

**文档版本**：1.0  
**最后更新**：2024年

