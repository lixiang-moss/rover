# MARS Rover ROS 2 高层控制开发需求文档

> 版本：2026-05-23  
> 目标读者：后续负责编写 ROS 2 代码的人或 AI  
> 文档性质：需求规格，不是代码实现  
> 适用范围：控制端电脑 + Raspberry Pi 上的 ROS 2 高层控制工程  
> ROS 2 版本：Jazzy  
> 主要目标：键盘控制、局域网 ROS 2 通信、Pi 通过串口向 STM32 发送真实命令，并同时支持单轮测试和真实四轮手动控制

---

## 0. 本文档的边界

本文档根据前置方案文档和用户已确认需求整理而成，用来指导后续 ROS 2 代码工程开发。

本文档要求后续实现者做到：

- 搭建一个统一 ROS 2 workspace。
- 同一个工程同时包含控制端电脑可运行节点和 Raspberry Pi 可运行节点。
- 控制端电脑使用键盘控制。
- Raspberry Pi 运行高层运动学、串口桥接、安全门和状态发布。
- 可以通过 Pi 串口向 STM32 发送真实命令。
- 必须支持单轮组真实电机测试。
- 必须支持真实四轮手动控制。
- `/wheel_states` 和 `/joint_states` 当前使用目标值回显，必须设置 `feedback_is_real=false`。

---

## 1. 用户已确认需求

### 1.1 第一版开发目标

用户要求第一版不是只做 dry-run，而是要达到：

1. Pi 可以通过串口向 STM32 发送真实命令。
2. 系统可以支持单轮组真实电机测试。
3. 系统可以支持真实四轮手动控制。
4. 默认单轮组为 `front_left`。

因此需求文档中的 MVP 不应停留在纯仿真或纯 mock，而应同时支持：

- dry-run。
- STM32 echo/mock。
- Pi -> STM32 真实串口发送。
- `front_left` 单轮组真实电机测试。
- 四轮真实手动控制。

### 1.2 控制方式

当前版本控制端使用键盘控制。

要求：

- 使用 ROS 2 标准键盘 teleop 或项目内封装的键盘控制入口。
- 键盘控制最终发布 `/cmd_vel`。
- 键盘控制不直接控制 STM32。
- 键盘控制不直接发送 wheel setpoints。

### 1.3 开发电脑与 Docker 开发环境

用户当前开发电脑使用 Ubuntu 26。

ROS 2 Jazzy 匹配 Ubuntu 24.04，因此当前开发环境为：

- Ubuntu 26 作为宿主机。
- 在 Ubuntu 26 中使用 Docker。
- Docker 容器使用 Ubuntu 24.04。
- Docker 容器内安装 ROS 2 Jazzy。
- 在同一个 Docker 开发容器中开发整个统一 ROS 2 workspace。

Docker 使用结论：

- 当前版本采用 Docker 作为电脑端主要开发环境。
- Docker 的作用是让 Ubuntu 26 宿主机获得 Ubuntu 24.04 + ROS 2 Jazzy 的开发环境。
- 不把电脑端和 Pi 端拆成两个开发容器。
- 不把电脑端和 Pi 端拆成两个代码工程。
- 一个 Docker 容器中包含并编译完整 workspace。
- 电脑端 launch 和 Pi 端 launch 在同一 workspace 中分别维护。

开发阶段的基本结构应理解为：

```text
Ubuntu 26 宿主机
└── Docker 开发容器：Ubuntu 24.04 + ROS 2 Jazzy
    └── mars_rover_ws
        ├── 电脑端 teleop / RViz / 调试入口
        └── Pi 端 motion / safety / stm32_bridge / joint_state 入口
```

注意：

- 这里的 Docker 是开发环境选择。
- Pi 端最终部署方式暂不在本文档中收束。
- 后续如果要在 Pi 上用 Docker 部署，需要另写部署文档，特别处理 arm64 镜像、串口设备映射和 ROS 2 网络。

### 1.4 Raspberry Pi 系统建议

用户表示 Pi 已经有系统，但不确定是否合适。

当前文档暂不收束 Pi 端最终部署方式，但从 ROS 2 版本一致性的角度，后续仍应优先考虑：

- Raspberry Pi 4 或更高。
- Ubuntu Server 24.04 64-bit。
- ROS 2 Jazzy。

本文档当前只规定开发方式：

- 在 Ubuntu 26 电脑上，用一个 Ubuntu 24.04 + ROS 2 Jazzy Docker 容器开发完整代码工程。

本文档当前不规定：

- Pi 最终必须原生部署还是 Docker 部署。
- Pi 宿主系统是否必须重装。
- Pi 端 Docker 镜像如何构建。
- Pi 端容器如何映射 STM32 串口。

这些问题应在代码开发完成或进入硬件联调前单独确定。

### 1.5 ROS 2 版本

统一使用：

- ROS 2 Jazzy。

要求：

- 控制端电脑和 Pi 都使用 Jazzy。
- 不允许一端 Humble、一端 Jazzy 混用。
- 不允许控制端电脑和 Pi 使用不同 ROS 2 发行版混用。

### 1.6 可视化要求

RViz 是可选调试工具，不是实体单轮验收前置条件。

要求：

- 工程提供包含四个转向关节和四个驱动关节的 URDF。
- RViz 中应能看到机器人 base 和四个轮组。
- RViz 中应能看到 `front_left` 转向关节状态变化。
- RViz 当前显示目标状态，不是真实硬件反馈；消息中必须设置 `feedback_is_real=false`。

### 1.7 Pi 到 STM32 的数据单位

用户确认：

Pi 发给 STM32 的主要目标应为：

- 4 个转向角，单位 `rad`。
- 4 个车轮线速度，单位 `m/s`。

不应在 ROS 2 高层接口中使用：

- degree。
- mm。
- RPM。
- 驱动器寄存器原始单位。

底层如果需要 RPM、脉冲数或寄存器单位，应由 STM32 固件内部转换。

### 1.8 STM32 当前状态

STM32 使用当前 `STM32G474RET6/STM32G474RETx` CubeIDE 工程实现。ROS 2 工程支持三种 bridge 模式：

1. `dry_run`：不连接 STM32，只打印和发布目标。
2. `serial_echo`：连接 STM32，但 STM32 只回显或 ACK，不驱动电机。
3. `real_serial`：连接 STM32，发送真实轮组目标，用于单轮组测试或四轮手动控制。

### 1.9 第一版驱动模式

用户确认第一版需要：

- `STOP`
- `CRAB`
- `SPIN_IN_PLACE`
- `RAW_WHEEL_TEST`

### 1.10 安全需求

用户接受推荐安全需求。

当前版本必须包含：

- 命令超时停止。
- 速度限幅。
- 角度限幅。
- 软件急停 topic。
- STM32 offline 检测。
- dry-run 模式。
- 单轮测试模式默认只启用 `front_left`。
- 默认所有真实硬件输出都必须先经过 arm 授权。
- 实际授权使用带前置条件的 arm 服务，不再使用动态 enable 参数。
- 急停、故障、命令断流和 USB 断开在已 arm 时必须锁存 disarm；恢复后不得自动继续旧运动。

---

## 2. 工程总体结构需求

### 2.1 一个统一 workspace

需求：

项目必须是一个统一 ROS 2 workspace，同时包含电脑端和 Pi 端节点。

开发阶段必须在同一个 Ubuntu 24.04 + ROS 2 Jazzy Docker 容器中编译和测试整个 workspace。不要为电脑端和 Pi 端分别建立两个开发容器，也不要建立两个互相独立的 workspace。

推荐目录：

```text
mars_rover_ws/
  src/
    mars_rover_msgs/
    mars_rover_control/
    mars_rover_description/
    mars_rover_bringup/
    mars_rover_tests/
```

说明：

- 控制端电脑和 Pi 使用同一套源码。
- 哪些节点在哪台机器上运行，由 launch 文件和文档决定。
- 不要拆成两个完全独立的仓库。

### 2.2 包职责

| 包名 | 必须性 | 职责 |
|---|---|---|
| `mars_rover_msgs` | 必须 | 自定义消息，例如 wheel setpoint、wheel state、drive mode、STM32 status |
| `mars_rover_control` | 必须 | 高层控制节点、运动学节点、安全门、STM32 bridge |
| `mars_rover_description` | 必须 | 最小 URDF / Xacro，用于 RViz |
| `mars_rover_bringup` | 必须 | launch 文件、参数文件、运行组合 |
| `mars_rover_tests` | 推荐 | dry-run、单轮测试、launch 测试和测试说明 |

### 2.3 运行位置划分

控制端电脑运行：

- 键盘 teleop。
- 可选 RViz。
- 可选 rosbag。
- 可选 topic echo / debug 工具。

Raspberry Pi 运行：

- safety gate。
- drive mode manager。
- four wheel kinematics。
- STM32 bridge。
- joint state republisher。
- robot state publisher。

这些节点按当前代码保持独立，以便分别测试安全、模式、运动学和硬件通信。

---

## 3. 节点需求

### 3.1 控制端键盘节点

节点来源：

- 优先使用现成 ROS 2 键盘 teleop。
- 如果项目需要统一 launch，可在 bringup 中封装启动命令。

输入：

- 用户键盘。

输出：

- `/cmd_vel`

消息类型：

- `geometry_msgs/msg/Twist`

需求：

- 键盘控制只发布整体速度。
- 不允许键盘节点直接发布 wheel setpoints。
- 不允许键盘节点直接访问 STM32 串口。

### 3.2 `drive_mode_manager`

运行位置：

- Raspberry Pi。

功能：

- 管理当前 drive mode。
- 接收模式切换请求。
- 默认模式为 `STOP`。
- 支持 `STOP`、`CRAB`、`SPIN_IN_PLACE`、`RAW_WHEEL_TEST`。
- 模式切换时应短暂进入安全状态，避免旧速度命令残留。
- 每个 launch profile 只接受其允许模式；所有 profile 都必须接受 `STOP`。

输入话题：

- `/mars_rover/drive_mode_request`

输出话题：

- `/mars_rover/drive_mode`

需求：

- 模式请求非法时必须拒绝，并保持当前安全模式。
- 启动后必须处于 `STOP`。
- 没有明确 enable 时，不得进入真实硬件输出状态。

### 3.3 `safety_gate`

运行位置：

- Raspberry Pi。

功能：

- 接收 `/cmd_vel`。
- 检查命令是否超时。
- 检查软件急停。
- 检查 STM32 是否在线。
- 对速度进行限幅。
- 输出安全后的速度命令。
- 维护急停/故障锁存和 arm/disarm 状态。
- 发布结构化 `/mars_rover/control_state`。

输入话题：

- `/cmd_vel`
- `/mars_rover/emergency_stop`
- `/mars_rover/stm32/status`

输出话题：

- `/mars_rover/safe_cmd_vel`
- `/mars_rover/safety_state`
- `/mars_rover/control_state`

服务：

- `/mars_rover/set_armed`：`std_srvs/srv/SetBool`
- `/mars_rover/reset_safety`：`std_srvs/srv/Trigger`

必须参数：

| 参数 | 推荐初始值 | 说明 |
|---|---:|---|
| `cmd_timeout_sec` | `0.5` | 超过此时间未收到新 `/cmd_vel`，输出停止 |
| `max_linear_velocity` | `0.10` | 当前最大线速度，单位 m/s |
| `max_angular_velocity` | `0.30` | 当前最大角速度，单位 rad/s |
| `require_stm32_online_for_real_serial` | `true` | 真实串口模式下要求 STM32 在线 |

需求：

- 超时时输出零速度。
- 急停时输出零速度。
- STM32 offline 时真实输出必须禁止。
- dry-run 模式可以不要求 STM32 online。

### 3.4 `four_wheel_kinematics`

运行位置：

- Raspberry Pi。

功能：

- 订阅安全后的速度命令。
- 订阅当前 drive mode。
- 根据模式生成四个轮组目标。
- 输出 `/mars_rover/wheel_setpoints`。

输入话题：

- `/mars_rover/safe_cmd_vel`
- `/mars_rover/drive_mode`

输出话题：

- `/mars_rover/wheel_setpoints`

消息类型：

- `mars_rover_msgs/msg/WheelSetpointArray`

必须支持模式：

#### STOP

需求：

- 四个轮组 `drive_velocity = 0`。
- 四个轮组默认 `enabled = false`，或在 real_serial 下发送停止目标。
- 转向角保持当前目标或默认 0，具体由参数决定。

#### CRAB

需求：

- 用 `/cmd_vel.linear.x` 和 `/cmd_vel.linear.y` 计算四轮共同转向角。
- 四个轮子转向角相同。
- 四个轮子驱动速度相同或根据方向符号一致输出。
- `/cmd_vel.angular.z` 在此模式下可以忽略或要求为 0。

#### SPIN_IN_PLACE

需求：

- 使用 `/cmd_vel.angular.z` 控制原地旋转。
- 四个轮子的转向角应切向指向绕机器人中心旋转的方向。
- 四个轮子的速度方向必须能让机器人绕中心旋转。
- 实体测试按单轮架空、四轮架空、低速落地的顺序执行。

#### RAW_WHEEL_TEST

需求：

- 默认只启用 `front_left`。
- 其他轮组必须 `enabled=false` 且速度为 0。
- 支持给 `front_left` 设置小角度、小速度目标。
- 所有输出必须经过严格限幅。
- 此模式用于真实单轮组测试。

必须参数：

| 参数 | 推荐初始值 | 说明 |
|---|---:|---|
| `wheelbase` | `0.706` | 轴距，单位 m，来自前期文档，需实测确认 |
| `track_width` | `0.288` | 轮距，单位 m，来自前期文档，需实测确认 |
| `wheel_radius` | 待测 | 车轮半径，必须后续补充 |
| `max_steering_angle` | `1.5708` | 当前限制到 ±90 度 |
| `max_drive_velocity` | `0.10` | 当前整车目标上限，单位 m/s |
| `active_test_wheel` | `front_left` | 默认单轮测试轮组 |

### 3.5 `stm32_bridge`

运行位置：

- Raspberry Pi。

功能：

- 订阅 `/mars_rover/wheel_setpoints`。
- 根据运行模式决定是否打开串口。
- 将 wheel setpoints 转换为 Pi -> STM32 串口命令。
- 读取 STM32 回传 ACK/status。
- 发布 STM32 状态。
- 发布 wheel states。

输入话题：

- `/mars_rover/wheel_setpoints`
- `/mars_rover/emergency_stop`
- `/mars_rover/control_state`

输出话题：

- `/mars_rover/stm32/status`
- `/mars_rover/wheel_states`

运行模式：

| 模式 | 行为 |
|---|---|
| `dry_run` | 不打开串口，只打印将发送的目标 |
| `serial_echo` | 打开串口并回 ACK；代码层无条件强制 `enabled=false` |
| `real_serial` | 打开串口，发送真实命令；通过 `hardware_output_mode` 区分单轮测试和四轮手动控制 |

必须参数：

| 参数 | 推荐值 | 说明 |
|---|---|---|
| `serial_port` | `/dev/mars-rover-stm32` | USB 虚拟串口的 udev 稳定别名；原始设备通常为 `/dev/ttyACM0` |
| `baud_rate` | `115200` | 8N1，无流控 |
| `bridge_mode` | `dry_run` | 默认必须安全 |
| `status_timeout_sec` | `0.5` | 超过此时间无 STM32 ACK/STATUS 认为 timeout |
| `setpoint_timeout_sec` | `0.25` | 上游目标断流后主动发送禁用 STOP |
| `control_state_timeout_sec` | `0.25` | ControlState 断流后禁止真实输出 |
| `hardware_output_mode` | `single_wheel` | `single_wheel` 或 `full_vehicle` |
| `active_test_wheel` | `front_left` | 单轮测试模式下的目标轮组 |

需求：

- 默认不得以 `real_serial` 启动。
- `real_serial` 必须需要显式参数或 launch 文件选择。
- 串口断开时必须发布 STM32 offline。
- STM32 未 ACK 时不得假装成功。
- 未 arm、ControlState 不新鲜、软件急停或锁存故障时，串口帧顶层与各轮组 `enabled` 均不得为 `true`。
- 策略拒绝、目标断流或状态失效时主动发送全局禁用 STOP。
- 如果 `/wheel_states` 只是目标值回显，必须设置 `feedback_is_real=false`。

### 3.6 `joint_state_republisher`

运行位置：

- Raspberry Pi。

功能：

- 根据 `/mars_rover/wheel_states` 发布 `/joint_states`。
- 如果没有真实反馈，使用目标值回显。

输出话题：

- `/joint_states`

消息类型：

- `sensor_msgs/msg/JointState`

关节名必须为：

1. `front_left_steering_joint`
2. `front_left_drive_joint`
3. `front_right_steering_joint`
4. `front_right_drive_joint`
5. `rear_left_steering_joint`
6. `rear_left_drive_joint`
7. `rear_right_steering_joint`
8. `rear_right_drive_joint`

需求：

- `/joint_states` 必须能被 RViz 使用。
- 如果只是目标值回显，日志或状态话题必须说明不是真实反馈。

### 3.7 `robot_state_publisher`

运行位置：

- Raspberry Pi 或控制端电脑。

功能：

- 读取最小 URDF。
- 发布 TF。
- 支持 RViz 显示四轮转向。

需求：

- 当前 URDF 必须包含 8 个关节。
- 四个转向关节和四个驱动关节命名必须与 `/joint_states` 一致。

---

## 4. 消息需求

### 4.1 `DriveMode`

必须表达：

- 当前模式。
- 是否正在切换。
- 模式来源。
- 人可读原因。

枚举必须包含：

| 名称 | 值 |
|---|---:|
| `STOP` | 0 |
| `CRAB` | 1 |
| `SPIN_IN_PLACE` | 2 |
| `RAW_WHEEL_TEST` | 3 |

### 4.2 `WheelSetpoint`

必须字段：

| 字段 | 类型 | 单位 | 说明 |
|---|---|---|---|
| `name` | string | 无 | `front_left` 等 |
| `enabled` | bool | 无 | 是否启用该轮组 |
| `steering_angle` | float64 | rad | 目标转向角 |
| `drive_velocity` | float64 | m/s | 目标车轮线速度 |

推荐字段：

| 字段 | 类型 | 单位 | 说明 |
|---|---|---|---|
| `steering_velocity_limit` | float64 | rad/s | 转向限速 |
| `drive_acceleration_limit` | float64 | m/s^2 | 驱动加速度限制 |

### 4.3 `WheelSetpointArray`

必须字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `stamp` | time | 生成时间 |
| `sequence_id` | uint32 | 递增序号 |
| `mode` | uint8 | 当前模式 |
| `setpoints` | WheelSetpoint[4] | 四个轮组目标 |

顺序必须固定：

1. `front_left`
2. `front_right`
3. `rear_left`
4. `rear_right`

### 4.4 `WheelState`

必须字段：

| 字段 | 类型 | 单位 | 说明 |
|---|---|---|---|
| `name` | string | 无 | 轮组名 |
| `online` | bool | 无 | 底层是否在线 |
| `enabled` | bool | 无 | 当前是否启用 |
| `steering_angle` | float64 | rad | 当前或回显转向角 |
| `drive_velocity` | float64 | m/s | 当前或回显速度 |
| `feedback_is_real` | bool | 无 | 是否真实反馈 |
| `fault` | bool | 无 | 是否故障 |
| `fault_code` | int32 | 无 | 故障码 |

当前 `/wheel_states` 为目标值回显，必须设置 `feedback_is_real=false`。

### 4.5 `Stm32Status`

必须字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `stamp` | `builtin_interfaces/Time` | 状态生成时间 |
| `online` | bool | STM32 是否在线 |
| `last_rx_age` | float64 | 距离上次有效 ACK/STATUS 的秒数 |
| `last_ack_sequence_id` | uint32 | 最近 ACK 的序号 |
| `last_sent_sequence_id` | uint32 | Pi 最近实际写入串口的序号 |
| `last_status_sequence_id` | uint32 | 最近 STATUS 携带的序号 |
| `serial_connected` | bool | 串口是否连接 |
| `timeout` | bool | STM32 是否报告超时 |
| `estop_active` | bool | 急停是否触发 |
| `fault` | bool | 底层故障或命令拒绝 |
| `fault_code` | uint32 | STM32 故障码 |
| `serial_error` | bool | 串口打开或读写错误 |
| `bridge_mode` | string | 当前 bridge 模式 |
| `control_state_connected` | bool | ControlState 是否新鲜 |
| `message` | string | 人可读状态 |

### 4.6 `ControlState`

必须表达：

- 当前安全状态枚举。
- 是否已经 arm。
- 是否允许真实运动。
- 是否仍要求新的零命令。
- 急停和故障是否锁存。
- 每次使旧命令失效时递增的 `generation`。
- 人可读原因。

---

## 5. 话题需求

| 话题 | 消息类型 | 说明 |
|---|---|---|
| `/cmd_vel` | `geometry_msgs/msg/Twist` | 键盘控制输出 |
| `/mars_rover/drive_mode_request` | 自定义或 `std_msgs/msg/String` | 请求切换模式 |
| `/mars_rover/drive_mode` | `mars_rover_msgs/msg/DriveMode` | 当前模式 |
| `/mars_rover/emergency_stop` | `std_msgs/msg/Bool` | 软件急停 |
| `/mars_rover/safe_cmd_vel` | `geometry_msgs/msg/Twist` | 经过安全门的速度 |
| `/mars_rover/control_state` | `mars_rover_msgs/msg/ControlState` | arm、运动许可、锁存和恢复代次 |
| `/mars_rover/wheel_setpoints` | `mars_rover_msgs/msg/WheelSetpointArray` | 四轮目标 |
| `/mars_rover/wheel_states` | `mars_rover_msgs/msg/WheelStateArray` | 四轮状态 |
| `/mars_rover/stm32/status` | `mars_rover_msgs/msg/Stm32Status` | STM32 状态 |
| `/joint_states` | `sensor_msgs/msg/JointState` | RViz 关节状态 |
| `/tf` | `tf2_msgs/msg/TFMessage` | TF |
| `/tf_static` | `tf2_msgs/msg/TFMessage` | 静态 TF |

---

## 6. Pi 到 STM32 串口协议需求

### 6.1 协议格式

```text
<紧凑JSON>*<8位大写十六进制CRC32>\n
```

- CRC32 覆盖星号前的原始 UTF-8 JSON 字节。
- 完整帧最大 512 字节。
- W 命令固定键：`v,t=W,q,m,e,s,w`。
- ACK 固定键：`v,t=A,q,ok,fc`。
- STATUS 固定键：`v,t=S,q,on,es,to,fc`。
- Pi 以 20 Hz 发送；STM32 每条有效命令回 ACK，并约 5 Hz 主动回 STATUS。
- STM32 超过 0.5 秒未收到有效命令时停止全部输出。

### 6.2 轮组顺序

串口协议中四个轮组顺序必须固定：

1. `front_left`
2. `front_right`
3. `rear_left`
4. `rear_right`

每轮固定为 `[enabled, angle_rad, velocity_mps, steering_limit_radps, acceleration_limit_mps2]`。

### 6.3 real_serial 硬件输出策略

`real_serial` 必须支持两种硬件输出策略：

| 策略 | 用途 | 允许的模式 |
|---|---|---|
| `single_wheel` | 单轮组真实测试 | `STOP`、`RAW_WHEEL_TEST` |
| `full_vehicle` | 真实四轮手动控制 | `STOP`、`CRAB`、`SPIN_IN_PLACE` |

在 `single_wheel` + `RAW_WHEEL_TEST` 下：

- 默认只启用 `front_left`。
- active wheel 应允许通过参数切换。
- 非 active wheel 的 drive velocity 必须为 0。

在 `full_vehicle` 下：

- `CRAB` 和 `SPIN_IN_PLACE` 允许四个轮组同时启用。
- `STOP` 必须让四个轮组驱动速度为 0。
- ControlState 未授权时不得发送 `enabled=true`。
- 软件急停时不得发送 `enabled=true`。

### 6.4 STM32 回传需求

STM32 至少应回传：

- 是否收到命令。
- 最近收到或执行的 sequence id。
- 是否处于 fault。
- 是否通信超时。

当前 `/mars_rover/wheel_states` 使用目标值回显，并明确 `feedback_is_real=false`。

---

## 7. Launch 与参数需求

### 7.1 必须提供的 launch

#### `pc_teleop.launch.py`

运行位置：

- 控制端电脑。

功能：

- 启动键盘 teleop。
- 可选启动 RViz。

#### `pi_bringup_dry_run.launch.py`

运行位置：

- Raspberry Pi 或开发电脑。

功能：

- 启动 Pi 侧全部核心节点。
- `stm32_bridge` 使用 `dry_run`。
- 不访问真实串口。

#### `pi_bringup_serial_echo.launch.py`

运行位置：

- Raspberry Pi。

功能：

- 启动 Pi 侧核心节点。
- `stm32_bridge` 使用 `serial_echo`。
- 连接 STM32，但不要求真实驱动电机。

#### `pi_bringup_real_single_wheel.launch.py`

运行位置：

- Raspberry Pi。

功能：

- 启动真实串口模式。
- drive mode 默认为 `STOP`，确认安全并 arm 后再请求 `RAW_WHEEL_TEST`。
- active wheel 为 `front_left`。
- 速度和角度限幅使用保守值。

要求：

- 该 launch 文件必须显式命名为 single wheel 或 real，避免误启动。
- 默认参数必须保守。

#### `pi_bringup_real_full_vehicle.launch.py`

运行位置：

- Raspberry Pi。

功能：

- 启动真实串口模式。
- `hardware_output_mode=full_vehicle`。
- drive mode 默认为 `STOP`。
- 允许后续切换到 `CRAB` 和 `SPIN_IN_PLACE` 做四轮手动控制。

要求：

- 默认 `STOP + disarmed`。
- 必须通过 `/mars_rover/set_armed` 服务的前置检查才允许真实硬件执行。
- 该 launch 文件用于四轮架空测试和低速手动控制测试；测试顺序是安全建议，不是功能限制。

### 7.2 参数文件

必须提供：

- `config/robot_geometry.yaml`
- `config/safety_limits.yaml`
- `config/stm32_bridge.yaml`
- `config/single_wheel_test.yaml`

---

## 8. RViz 与 URDF 需求

### 8.1 最小 URDF

最小 URDF 必须包含：

- `base_link`
- 四个 steering link。
- 四个 wheel link。
- 四个 steering joints。
- 四个 drive joints。

模型可以简化为盒子和圆柱，不要求精细 CAD。

### 8.2 RViz 验收

RViz 中必须能看到：

- 机器人底盘。
- 四个轮组位置。
- `front_left` 转向变化。
- `/tf` 正常。
- `/joint_states` 正常。

---

## 9. 安全需求

### 9.1 默认安全状态

系统启动后必须默认：

- drive mode 为 `STOP`。
- `stm32_bridge` 默认为 `dry_run`，除非 launch 明确指定。
- 所有 wheel setpoints 速度为 0。
- 真实串口启动时必须处于 disarmed；arm 只允许在 STOP、零命令和底层健康时成功。

### 9.2 超时停止

如果超过 `cmd_timeout_sec` 没有收到 `/cmd_vel`：

- `/mars_rover/safe_cmd_vel` 必须变成 0。
- `/mars_rover/wheel_setpoints` 中驱动速度必须变成 0。

### 9.3 软件急停

如果 `/mars_rover/emergency_stop=true`：

- 所有驱动速度必须为 0。
- `stm32_bridge` 必须把急停状态发送给 STM32。
- 状态话题必须显示急停。
- 急停必须锁存；发布 false 不得自动恢复，必须 reset、重新 arm 并收到新命令。

### 9.4 角度和速度限幅

当前推荐限制：

- 最大线速度：`0.10 m/s`。
- 最大角速度：`0.30 rad/s`。
- 最大转向角：`±1.5708 rad`。

这些限制后续可以根据机械和 STM32 负责人反馈调整。

### 9.5 STM32 offline

如果 STM32 offline：

- 真实串口模式必须报错。
- 不得继续假装命令已执行。
- `/mars_rover/stm32/status.online=false`。
- 已 arm 时的 offline、fault、timeout 或串口错误必须锁存故障并 disarm。

---

## 10. 单轮组真实测试需求

### 10.1 默认测试对象

默认测试轮组：

- `front_left`

### 10.2 测试前提

真实单轮测试前必须满足：

- 机器人或该轮组安全架空。
- 有物理急停。
- 24 V 电机驱动电源可快速切断。
- Pi 与 STM32 串口通信已验证。
- STM32 echo 或 ACK 已验证。
- 只连接或只启用 `front_left`。
- 其他轮组禁用。

### 10.3 测试顺序

推荐顺序：

1. ROS 2 dry-run。
2. STM32 serial echo。
3. 单独测试 `front_left` 转向电机。
4. 单独测试 `front_left` 驱动电机。
5. 测试 `front_left` 转向 + 驱动组合。

### 10.4 单轮测试验收标准

必须满足：

- `/cmd_vel` 能从电脑端发到 Pi。
- Pi 能生成只启用 `front_left` 的 wheel setpoints。
- Pi 能通过串口发送给 STM32。
- STM32 能 ACK。
- 其他三个轮组目标禁用。
- STOP 后速度为 0。
- 超时后速度为 0。
- 急停后速度为 0。
- RViz 能显示 `front_left` 的目标状态。

---

## 11. STM32 负责人需要确认的实现信息

STM32 固件以当前 STM32G474RE CubeIDE 工程为基线。负责人需要确认：

### 11.1 新固件实现状态

1. USB 虚拟串口收发和 512 字节切帧是否完成？若使用 ST-LINK VCP，还需确认其对应 UART 参数；若使用原生 USB CDC，则不使用 MCU UART 波特率。
2. 紧凑 JSON、CRC32、字段校验、ACK/STATUS 是否完成？
3. 0.5 秒 watchdog 和上电默认禁用是否完成？
4. USART1/USART3 两条 RS-485 总线是否分别完成？
5. SERVO57D ID 1 和 BLD-305S ID 1 是否能读取、停止和上报故障？
6. 原点开关是否已选型、安装并验证输入电平？
7. front_left 的转向/行走方向符号、零位、减速比和轮半径是否记录？

### 11.2 Pi 到 STM32 已冻结通信合同

| 项目 | 固定值 |
|---|---|
| 物理接口 | Pi USB Host 到 STM32 开发板 USB 数据接口 |
| Pi 设备 | `/dev/mars-rover-stm32`，原始设备通常为 `/dev/ttyACM0` |
| 串口 | 115200，8N1，无流控 |
| 帧 | `<紧凑JSON>*<8位大写十六进制CRC32>\n` |
| 协议版本 | 1 |
| 命令序号 | uint32 `q`，回绕 |
| 返回 | 每条有效命令 ACK，约 5 Hz STATUS |
| STM32 超时停止 | 0.5 秒 |

字段、故障码和接线以 `Pi与STM32接口对接说明.md` 为准。

### 11.3 命令内容

1. STM32 是否接受 Pi 发送 4 个转向角，单位 `rad`？
2. STM32 是否接受 Pi 发送 4 个车轮线速度，单位 `m/s`？
3. STM32 是否愿意在固件里完成 `m/s` 到驱动器速度单位的转换？
4. STM32 是否需要 Pi 同时发送 enable、mode、estop？
5. STM32 是否支持只启用一个轮组？
6. disabled wheel 在 STM32 中应停止、保持，还是完全不发送驱动器命令？

### 11.4 反馈能力

1. STM32 能否回传当前转向角？
2. 当前转向角是来自真实反馈，还是来自命令估计？
3. STM32 能否回传当前驱动速度？
4. 当前驱动速度是来自真实反馈，还是来自命令估计？
5. STM32 能否读取 MKS SERVO57D fault？
6. STM32 能否读取 BLDC 驱动器 fault？
7. STM32 能否回传急停状态？
8. STM32 能否回传每个驱动器在线状态？

### 11.5 电机和驱动器映射

两类驱动器位于两条独立 RS-485 总线，因此都使用 ID 1-4：

| 轮组 | SERVO57D ID | BLD-305S ID |
|---|---:|---:|
| `front_left` | 1 | 1 |
| `front_right` | 2 | 2 |
| `rear_left` | 3 | 3 |
| `rear_right` | 4 | 4 |

STM32 负责人逐台配置后必须读取地址并填写实测记录。

---

## 12. 验收标准

### 12.1 软件 dry-run 验收

必须满足：

- workspace 可以编译。
- workspace 可以在 Ubuntu 24.04 + ROS 2 Jazzy Docker 开发容器中编译。
- 控制端键盘可以发布 `/cmd_vel`。
- Pi 侧节点可以接收 `/cmd_vel`。
- 可以输出 `/mars_rover/wheel_setpoints`。
- `RAW_WHEEL_TEST` 中只有 `front_left.enabled=true`。
- `CRAB` 和 `SPIN_IN_PLACE` 中四个轮组都能生成 enabled 目标。
- RViz 能显示模型和 joint states。

### 12.2 STM32 echo 验收

必须满足：

- Pi 能打开串口。
- Pi 能发送带 sequence id 的命令。
- STM32 能回传 ACK。
- `/mars_rover/stm32/status.online=true`。
- 断开 STM32 后状态变为 offline。

### 12.3 单轮真实测试验收

必须满足：

- `front_left` 可以单独启用。
- 其他轮组禁用。
- 小角度转向命令能被发送到 STM32。
- 小速度驱动命令能被发送到 STM32。
- STOP、timeout、estop 都能让驱动速度归零。
- 如果反馈只是目标回显，状态中 `feedback_is_real=false`。

### 12.4 四轮真实手动控制验收

必须满足：

- real_serial 支持 `hardware_output_mode=full_vehicle`。
- `CRAB` 可以生成四轮 enabled 目标并通过串口发送给 STM32。
- `SPIN_IN_PLACE` 可以生成四轮 enabled 目标并通过串口发送给 STM32。
- `STOP`、timeout、estop 都能让驱动速度归零。
- 单轮 profile 接受 STOP；非法模式会触发主动禁用帧。
- 未 arm、锁存未复位或 ControlState 失效时不会发送 `enabled=true`。
- 反向 CRAB 和正反 SPIN 的四轮实际速度向量通过测试。
- 急停、故障和 USB 重连后不会自动恢复旧运动。
- 如果反馈只是目标回显，状态中 `feedback_is_real=false`。

---

## 14. 对后续代码生成 AI 的直接指令

如果把本文档交给另一个 AI 写代码，应要求它：

1. 创建统一 ROS 2 Jazzy workspace。
2. 现有高层节点使用 Python，新增实现保持同一语言和包结构。
3. 创建 `mars_rover_msgs` 自定义消息包。
4. 创建 `mars_rover_control` 节点包。
5. 创建 `mars_rover_description` 最小 URDF。
6. 创建 `mars_rover_bringup` launch 和参数文件。
7. 使用自定义 ROS 2 节点实现高层控制链路。
8. 保持键盘手动控制作为控制入口。
9. `stm32_bridge` 实现 Pi 到 STM32 紧凑串口协议。
10. 默认启动保持 `STOP + disarmed`，通过服务 arm，不使用动态使能参数。
11. 必须支持 dry-run、serial echo、real single wheel 和 real full vehicle。
12. 必须支持 `front_left` 单轮测试和四轮真实手动控制。
13. 必须发布 `/joint_states` 和 RViz 可视化所需 TF。
14. 必须在所有状态里区分真实反馈和目标值回显。

---

## 15. 最终需求摘要

当前版本交付一个 ROS 2 Jazzy 工程：

- 在 Ubuntu 26 宿主机上的 Ubuntu 24.04 + ROS 2 Jazzy Docker 开发容器中完成开发和基础测试。
- 在同一个统一 workspace 中同时维护电脑端和 Pi 端节点。
- 在 Raspberry Pi 上运行 ROS 2 高层控制节点。
- 电脑和 Pi 通过 ROS 2 局域网通信。
- Pi 根据 `/cmd_vel` 和 drive mode 计算四轮目标。
- Pi 通过串口向 STM32 发送 4 个转向角 `rad` 和 4 个车轮线速度 `m/s`。
- 系统支持 `STOP`、`CRAB`、`SPIN_IN_PLACE`、`RAW_WHEEL_TEST`。
- 真实硬件输出同时支持 `front_left` 单轮组测试和四轮手动控制。
- 工程具备安全超时、限幅、软件急停、STM32 fault/estop/timeout/offline 检测。
- 工程具备锁存复位、带条件 arm、模式 STOP 过渡和恢复后新命令门槛。
- Pi 端使用 Ubuntu Server 24.04 arm64 和原生 ROS 2 Jazzy，部署步骤见硬件部署联调手册。
