# MARS Rover ROS 2 第一阶段架构与使用说明

> 版本：2026-05-24  
> 适用代码：`mars_rover_ws`  
> ROS 2 版本：Jazzy  
> 当前阶段：无硬件 dry-run 开发与验证  

本文档说明当前 ROS 2 工程的整体架构、各个包和文件的作用、Docker 开发环境、常用启动方法、测试方法，以及当前无硬件阶段需要特别注意的安全边界。

---

## 1. 总体目标

当前工程实现的是 MARS Rover 第一阶段高层控制链路：

```text
控制端键盘 / /cmd_vel
  -> safety_gate
  -> /mars_rover/safe_cmd_vel
  -> four_wheel_kinematics
  -> /mars_rover/wheel_setpoints
  -> stm32_bridge
  -> /mars_rover/wheel_states
  -> joint_state_republisher
  -> /joint_states
  -> robot_state_publisher / RViz
```

当前没有真实硬件，因此默认运行模式是 `dry_run`：

- 不打开 STM32 串口。
- 不驱动任何电机。
- `/mars_rover/wheel_states` 是目标值回显，不是真实反馈。
- `/joint_states` 也是由目标值推导出来，主要用于 RViz 可视化。

工程已经保留 `serial_echo` 和 `real_serial` 的入口，但这两个模式还没有做硬件联调，不能视为真实硬件已验证。

---

## 2. Workspace 结构

工程位于：

```text
/home/lx/rover/mars_rover_ws
```

主要结构：

```text
mars_rover_ws/
  Dockerfile
  README.md
  src/
    mars_rover_msgs/
    mars_rover_control/
    mars_rover_description/
    mars_rover_bringup/
    mars_rover_tests/
```

`mars_rover_ws` 是一个独立 ROS 2 workspace。进入该目录后使用 `colcon build` 构建。

---

## 3. Docker 开发环境

宿主机是 Ubuntu 26.04，当前不依赖宿主机安装 ROS 2。ROS 2 Jazzy 开发、构建、测试都在 Docker 镜像中完成。

### 3.1 Dockerfile

文件：

```text
mars_rover_ws/Dockerfile
```

作用：

- 基于 `osrf/ros:jazzy-desktop`。
- 安装 `colcon`、`pytest`、`pyserial`。
- 安装 `robot_state_publisher`、`joint_state_publisher`、`xacro`、`teleop_twist_keyboard` 等第一阶段需要的软件包。

构建镜像：

```bash
cd /home/lx/rover/mars_rover_ws
docker build -t mars-rover-jazzy -f Dockerfile .
```

### 3.2 进入容器

推荐运行方式：

```bash
cd /home/lx/rover/mars_rover_ws
docker run --rm -it --net=host \
  -v "$PWD":/workspace/mars_rover_ws \
  -w /workspace/mars_rover_ws \
  mars-rover-jazzy
```

说明：

- `--rm`：容器退出后自动删除。
- `--net=host`：使用宿主机网络，方便 ROS 2 DDS 通信。
- `-v "$PWD":/workspace/mars_rover_ws`：把当前 workspace 挂载到容器中。
- `mars-rover-jazzy`：当前工程使用的 Docker 镜像名。

进入容器后先执行：

```bash
source /opt/ros/jazzy/setup.bash
```

构建完成后还需要执行：

```bash
source install/setup.bash
```

---

## 4. ROS 2 包说明

### 4.1 `mars_rover_msgs`

路径：

```text
mars_rover_ws/src/mars_rover_msgs
```

作用：

- 定义项目自定义消息。
- 让控制节点、bridge、测试工具使用统一接口。

主要消息：

```text
msg/DriveMode.msg
msg/WheelSetpoint.msg
msg/WheelSetpointArray.msg
msg/WheelState.msg
msg/WheelStateArray.msg
msg/Stm32Status.msg
```

消息含义：

- `DriveMode`：当前底盘模式，例如 `STOP`、`CRAB`、`SPIN_IN_PLACE`、`RAW_WHEEL_TEST`。
- `WheelSetpoint`：单个轮组目标，包含轮组名、是否启用、目标转向角、目标驱动速度。
- `WheelSetpointArray`：四个轮组目标，顺序固定为 `front_left`、`front_right`、`rear_left`、`rear_right`。
- `WheelState`：单个轮组状态。当前 dry-run 下是目标值回显，`feedback_is_real=false`。
- `WheelStateArray`：四个轮组状态。
- `Stm32Status`：STM32 串口连接、在线状态、ACK 序号和错误信息。

---

### 4.2 `mars_rover_control`

路径：

```text
mars_rover_ws/src/mars_rover_control
```

作用：

- 实现第一阶段高层控制节点。
- 实现无硬件 dry-run 链路。
- 保留 STM32 串口桥接入口。

主要文件：

```text
mars_rover_control/constants.py
mars_rover_control/kinematics.py
mars_rover_control/serial_codec.py
mars_rover_control/drive_mode_manager.py
mars_rover_control/safety_gate.py
mars_rover_control/four_wheel_kinematics.py
mars_rover_control/stm32_bridge.py
mars_rover_control/joint_state_republisher.py
```

#### `constants.py`

集中定义：

- drive mode 数值。
- 轮组顺序。
- 8 个关节名。
- wheel name 到 joint name 的映射。

这样可以避免不同节点各自写一份名字，导致拼写不一致。

#### `kinematics.py`

纯 Python 运动学模块，不依赖 ROS 2。

作用：

- 根据 drive mode 和速度命令计算四个轮组目标。
- 支持 `STOP`、`CRAB`、`SPIN_IN_PLACE`、`RAW_WHEEL_TEST`。
- 便于直接用 `pytest` 单元测试。

当前行为：

- `STOP`：所有轮组 disabled，速度为 0，转向角保持最后目标。
- `CRAB`：根据 `linear.x` 和 `linear.y` 计算四轮共同角度和速度。
- `SPIN_IN_PLACE`：根据 `angular.z` 和轮组位置计算切向方向。
- `RAW_WHEEL_TEST`：默认只启用 `front_left`。

#### `serial_codec.py`

STM32 串口帧编码/解码模块。

当前协议是第一版 ROS 侧临时协议：

- 行分隔 JSON。
- 包含 `sequence_id`。
- 包含 mode、enable、estop、四个轮组目标。
- 包含 CRC32 checksum。

该协议便于无硬件阶段调试。后续如果 STM32 负责人确定二进制协议，只需要替换这一层，ROS 2 topic 接口不需要整体重写。

#### `drive_mode_manager.py`

节点名：

```text
drive_mode_manager
```

输入：

```text
/mars_rover/drive_mode_request  std_msgs/msg/String
```

输出：

```text
/mars_rover/drive_mode  mars_rover_msgs/msg/DriveMode
```

作用：

- 管理当前 drive mode。
- 默认启动为 `STOP`。
- 拒绝非法模式请求。

合法请求：

```text
STOP
CRAB
SPIN_IN_PLACE
RAW_WHEEL_TEST
```

#### `safety_gate.py`

节点名：

```text
safety_gate
```

输入：

```text
/cmd_vel
/mars_rover/emergency_stop
/mars_rover/stm32/status
```

输出：

```text
/mars_rover/safe_cmd_vel
/mars_rover/safety_state
```

作用：

- 命令超时后输出零速度。
- 软件急停时输出零速度。
- 对线速度和角速度限幅。
- 在 `real_serial` 模式下可要求 STM32 online。

默认安全参数：

```text
cmd_timeout_sec: 0.5
max_linear_velocity: 0.10
max_angular_velocity: 0.30
```

#### `four_wheel_kinematics.py`

节点名：

```text
four_wheel_kinematics
```

输入：

```text
/mars_rover/safe_cmd_vel
/mars_rover/drive_mode
```

输出：

```text
/mars_rover/wheel_setpoints
```

作用：

- 把机器人整体速度转换成四个轮组目标。
- 输出单位保持 ROS 高层单位：
  - 转向角：rad。
  - 车轮线速度：m/s。

默认几何参数：

```text
wheelbase: 0.706
track_width: 0.288
```

这些参数来自前期文档，真实机器人上需要重新测量确认。

#### `stm32_bridge.py`

节点名：

```text
stm32_bridge
```

输入：

```text
/mars_rover/wheel_setpoints
/mars_rover/emergency_stop
```

输出：

```text
/mars_rover/stm32/status
/mars_rover/wheel_states
```

运行模式：

```text
dry_run
serial_echo
real_serial
```

当前状态：

- `dry_run`：已验证，不打开串口，只发布目标值回显。
- `serial_echo`：代码入口已实现，会尝试打开串口并等待 ACK，但没有硬件验证。
- `real_serial`：代码入口已实现，并带安全限制，但没有硬件验证。

`real_serial` 安全限制：

- `hardware_output_mode=single_wheel` 时，只允许 `RAW_WHEEL_TEST`，默认测试轮组为 `front_left`，其他轮组必须 disabled 且速度为 0。
- `hardware_output_mode=full_vehicle` 时，允许 `STOP`、`CRAB`、`SPIN_IN_PLACE`，并允许四个轮组同时启用。
- `hardware_enable=false` 或软件急停时，串口帧中的 `enabled` 必须为 `false`。
- 当前代码入口已经实现上述策略，但仍需要真实硬件联调验证。

#### `joint_state_republisher.py`

节点名：

```text
joint_state_republisher
```

输入：

```text
/mars_rover/wheel_states
```

输出：

```text
/joint_states
```

作用：

- 把四个轮组状态转换成标准 `/joint_states`。
- 供 `robot_state_publisher` 和 RViz 使用。

注意：

当前 `/joint_states` 不是硬件真实反馈，而是根据目标值回显和积分得到的可视化状态。

---

### 4.3 `mars_rover_description`

路径：

```text
mars_rover_ws/src/mars_rover_description
```

作用：

- 提供最小 URDF/Xacro。
- 让 RViz 能显示底盘、四个 steering link、四个 wheel link。

主要文件：

```text
urdf/mars_rover.urdf.xacro
```

包含：

- `base_link`
- `front_left_steering_joint`
- `front_left_drive_joint`
- `front_right_steering_joint`
- `front_right_drive_joint`
- `rear_left_steering_joint`
- `rear_left_drive_joint`
- `rear_right_steering_joint`
- `rear_right_drive_joint`

模型目前是简化几何，不是 CAD 级模型。它的目的主要是验证 TF、关节命名和 RViz 可视化链路。

---

### 4.4 `mars_rover_bringup`

路径：

```text
mars_rover_ws/src/mars_rover_bringup
```

作用：

- 管理 launch 文件。
- 管理参数 YAML。
- 管理 RViz 配置。

#### Launch 文件

```text
launch/pi_bringup_dry_run.launch.py
launch/pi_bringup_serial_echo.launch.py
launch/pi_bringup_real_single_wheel.launch.py
launch/pc_teleop.launch.py
```

`pi_bringup_dry_run.launch.py`：

- 无硬件开发首选。
- 启动 Pi 侧核心节点。
- `stm32_bridge` 使用 `dry_run`。
- 不访问真实串口。

`pi_bringup_serial_echo.launch.py`：

- 用于未来 STM32 echo/ACK 测试。
- 会尝试打开串口。
- 不应连接真实电机驱动测试。

`pi_bringup_real_single_wheel.launch.py`：

- 用于未来真实单轮组测试。
- 默认 `RAW_WHEEL_TEST`。
- 默认 active wheel 为 `front_left`。
- 默认 `hardware_enable=false`，必须显式打开。

`pc_teleop.launch.py`：

- 启动 `teleop_twist_keyboard`。
- 可选启动 RViz。
- 用于控制端电脑。

#### 参数文件

```text
config/robot_geometry.yaml
config/safety_limits.yaml
config/stm32_bridge.yaml
config/single_wheel_test.yaml
```

`robot_geometry.yaml`：

- 轴距。
- 轮距。
- 车轮半径占位值。
- 默认测试轮组。

`safety_limits.yaml`：

- 命令超时。
- 最大线速度。
- 最大角速度。
- 最大转向角。
- 最大驱动速度。

`stm32_bridge.yaml`：

- 串口设备名。
- 波特率。
- bridge mode。
- STM32 状态超时。
- 是否要求真实输出 enable。

`single_wheel_test.yaml`：

- 单轮测试保守参数。
- 默认 `front_left`。
- 默认低速度、低角度范围。

---

### 4.5 `mars_rover_tests`

路径：

```text
mars_rover_ws/src/mars_rover_tests
```

作用：

- 放置无硬件测试说明。
- 当前主要是文档型测试包。

实际单元测试目前放在：

```text
mars_rover_ws/src/mars_rover_control/test
```

测试覆盖：

- `STOP` 禁用全部轮组。
- `CRAB` 前进、横移、斜向移动。
- `SPIN_IN_PLACE` 四轮切向布置。
- `RAW_WHEEL_TEST` 只启用 `front_left`。
- STM32 JSON-line frame codec 编码/校验。

---

## 5. 常用命令

### 5.1 构建

```bash
cd /home/lx/rover/mars_rover_ws
docker run --rm --net=host \
  -v "$PWD":/workspace/mars_rover_ws \
  -w /workspace/mars_rover_ws \
  mars-rover-jazzy \
  bash -lc "source /opt/ros/jazzy/setup.bash && colcon build"
```

### 5.2 测试

```bash
cd /home/lx/rover/mars_rover_ws
docker run --rm --net=host \
  -v "$PWD":/workspace/mars_rover_ws \
  -w /workspace/mars_rover_ws \
  mars-rover-jazzy \
  bash -lc "source /opt/ros/jazzy/setup.bash && source install/setup.bash && colcon test && colcon test-result --verbose"
```

当前验证结果：

```text
5 packages finished
7 tests, 0 errors, 0 failures, 0 skipped
```

### 5.3 启动 dry-run

进入容器后：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch mars_rover_bringup pi_bringup_dry_run.launch.py
```

该 launch 会启动：

- `drive_mode_manager`
- `safety_gate`
- `four_wheel_kinematics`
- `stm32_bridge`
- `joint_state_republisher`
- `robot_state_publisher`

### 5.4 切换模式

另开一个容器终端，并 source 环境：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
```

切换到 `CRAB`：

```bash
ros2 topic pub --once /mars_rover/drive_mode_request std_msgs/msg/String "{data: CRAB}"
```

切换到 `SPIN_IN_PLACE`：

```bash
ros2 topic pub --once /mars_rover/drive_mode_request std_msgs/msg/String "{data: SPIN_IN_PLACE}"
```

切换到 `RAW_WHEEL_TEST`：

```bash
ros2 topic pub --once /mars_rover/drive_mode_request std_msgs/msg/String "{data: RAW_WHEEL_TEST}"
```

回到 `STOP`：

```bash
ros2 topic pub --once /mars_rover/drive_mode_request std_msgs/msg/String "{data: STOP}"
```

### 5.5 发布速度命令

CRAB 前进：

```bash
ros2 topic pub --rate 10 /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.05, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"
```

CRAB 左横移：

```bash
ros2 topic pub --rate 10 /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.0, y: 0.05, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"
```

原地旋转：

```bash
ros2 topic pub --rate 10 /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.2}}"
```

RAW_WHEEL_TEST 中：

- `/cmd_vel.linear.x` 表示 active wheel 的驱动线速度。
- `/cmd_vel.angular.z` 表示 active wheel 的转向目标角。
- 默认 active wheel 是 `front_left`。

示例：

```bash
ros2 topic pub --rate 10 /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.02, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.15}}"
```

### 5.6 查看输出

查看安全速度：

```bash
ros2 topic echo /mars_rover/safe_cmd_vel
```

查看四轮目标：

```bash
ros2 topic echo /mars_rover/wheel_setpoints
```

查看 STM32 状态：

```bash
ros2 topic echo /mars_rover/stm32/status
```

查看 wheel states：

```bash
ros2 topic echo /mars_rover/wheel_states
```

查看 joint states：

```bash
ros2 topic echo /joint_states
```

---

## 6. RViz 使用

dry-run 启动后，可以在有图形界面的容器/环境中运行：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
rviz2 -d install/mars_rover_bringup/share/mars_rover_bringup/rviz/mars_rover.rviz
```

或者使用：

```bash
ros2 launch mars_rover_bringup pc_teleop.launch.py with_rviz:=true
```

RViz 中应能看到：

- 底盘。
- 四个轮组。
- TF。
- `/joint_states` 驱动的轮组转向变化。

注意：

当前 RViz 显示的是目标状态，不是真实硬件反馈。

---

## 7. 安全设计说明

默认安全策略：

- 启动默认 `STOP`。
- 默认 `dry_run`。
- 默认不打开串口。
- 默认不允许真实硬件输出。
- `/cmd_vel` 超时后输出零速度。
- `/mars_rover/emergency_stop=true` 时输出零速度。
- `real_serial` 默认 `hardware_enable=false`。
- `real_serial` 使用 `hardware_output_mode` 区分单轮测试和四轮真实手动控制。

未来硬件测试前必须确认：

- 机器人或轮组架空。
- 物理急停可用。
- 24 V 电机电源可快速切断。
- STM32 echo/ACK 已验证。
- STM32 自身有通信超时停止。
- STM32 可以正确拒绝非法或超限命令。

---

## 8. 当前已验证内容

已经在 Docker Jazzy 环境中验证：

- `colcon build` 通过。
- `colcon test` 通过。
- 7 个单元测试通过。
- `pi_bringup_dry_run.launch.py` 可以启动核心节点。
- 发送 `CRAB` 和 `/cmd_vel` 后，`/mars_rover/wheel_setpoints` 能输出四轮目标。
- `real_serial` 支持 single_wheel 和 full_vehicle 两种硬件输出策略。
- `/joint_states` 包含指定 8 个关节名。
- `stm32_bridge` 在 `dry_run` 下不打开串口，并发布目标值回显。

未验证内容：

- STM32 真实串口 ACK。
- STM32 echo 固件。
- 真实电机转向。
- 真实电机驱动。
- Pi 实机部署。
- 四轮架空测试。
- 地面低速测试。

---

## 9. 后续建议

建议下一步按这个顺序推进：

1. 在无硬件环境继续完善 launch test，自动验证 dry-run 数据流。
2. 和 STM32 负责人确认最终串口协议。
3. 用 `serial_echo` 连接 STM32，只验证 ACK，不接电机。
4. 准备 udev rule，把 STM32 固定为 `/dev/mars_stm32`。
5. 确认物理急停和架空测试条件。
6. 使用 `real_serial` 的 single_wheel 模式做单轮组测试。
7. 使用 `real_serial` 的 full_vehicle 模式做四轮架空和低速手动控制测试。

单轮测试和四轮真实控制都属于当前工程能力；单轮、架空、低速落地只是建议的硬件调试顺序。
