# MARS Rover ROS 2 部署后测试与硬件控制启动手册

> 文档用途：电脑端和 Raspberry Pi 端代码已经完成部署后，指导操作者逐级验证通信链路、ROS 2 控制链路、Pi 与 STM32 串口链路，以及单轮和四轮真实硬件控制。
>
> 适用代码：`mars_rover_ws` 当前实现，ROS 2 Jazzy。
>
> 电脑端：Ubuntu 26.04 宿主机中的 Ubuntu 24.04 / ROS 2 Jazzy Docker 容器；若电脑原生运行 Ubuntu 24.04 + Jazzy，可直接执行文中的“容器内命令”。
>
> Pi 端：Raspberry Pi 4、Ubuntu Server 24.04 arm64、原生 ROS 2 Jazzy，不使用 Docker。
>
> 控制范围：键盘手动控制，不包含 Nav2、自动驾驶或 `ros2_control`。

---

## 1. 如何使用本手册

本手册从“代码已经分别部署到电脑和 Pi”这一状态开始，不重复系统安装、ROS 2 安装和代码复制过程。需要按测试级别逐项执行，不能因为软件节点已经能启动，就跳过网络、串口、急停和单轮测试，直接让四轮落地运行。

完整流程分为四层：

1. **无硬件测试**：不连接 STM32，不给电机驱动器上电，验证电脑、Pi、DDS、节点、话题、运动学和超时停止。
2. **通信测试**：Pi 与 STM32 只验证 UART、协议、ACK、STATUS 和 watchdog，电机功率仍保持断开。
3. **单轮真实测试**：只测试一个轮组，默认 `front_left`，完成转向、驱动、停止和故障联锁。
4. **四轮真实测试**：先逐轮验证，再整车架空测试，最后才允许低速落地。

每一级都必须满足“通过标准”后才能进入下一级。某一级失败时，应停在当前级定位问题，不能用提高速度、取消急停或绕过安全门的方式继续。

---

## 2. 当前代码能力与必须知道的限制

### 2.1 已经具备的能力

当前工作区提供以下启动入口：

| 用途 | Pi 端 launch | 是否打开串口 | 是否可能控制电机 |
|---|---|---:|---:|
| 纯软件测试 | `pi_bringup_dry_run.launch.py` | 否 | 否 |
| Pi 与 STM32 串口联调 | `pi_bringup_serial_echo.launch.py` | 是 | 协议要求禁用输出，但仍必须断开电机功率 |
| 单轮真实控制 | `pi_bringup_real_single_wheel.launch.py` | 是 | 显式使能后可以 |
| 四轮真实控制 | `pi_bringup_real_full_vehicle.launch.py` | 是 | 显式使能后可以 |
| 电脑键盘控制 | `pc_teleop.launch.py` | 不适用 | 通过 Pi 间接控制 |

真实硬件 launch 均默认：

```text
hardware_enable=false
```

因此，仅启动 launch 不会发送可执行的 `enabled=true`。操作者必须在状态检查完成后，显式把 `/stm32_bridge` 的 `hardware_enable` 参数改为 `true`。

### 2.2 当前四种驱动模式

| 模式 | 编号 | 用途 | 允许在哪种真实输出策略中使用 |
|---|---:|---|---|
| `STOP` | 0 | 四轮停止 | `full_vehicle` |
| `CRAB` | 1 | 四轮同向平移 | `full_vehicle` |
| `SPIN_IN_PLACE` | 2 | 原地旋转 | `full_vehicle` |
| `RAW_WHEEL_TEST` | 3 | 单轮原始测试 | `single_wheel` |

`single_wheel` 与 `full_vehicle` 是真实硬件输出策略，不是两个独立工程：

- `single_wheel` 只允许 `RAW_WHEEL_TEST`，并且只允许配置的一个轮组启用。
- `full_vehicle` 允许 `STOP`、`CRAB` 和 `SPIN_IN_PLACE`，运动时允许四个轮组同时启用。
- 两种策略都使用相同的四轮消息和相同的 Pi 到 STM32 串口协议。

### 2.3 当前必须先处理的三个限制

#### 限制 A：当前 Pi 串口尚未满足真实联调条件

上一轮现场检查记录为：

```text
/dev/serial0: MISSING
kernel command line: console=serial0,115200
```

只要这个状态没有被修正，就只能执行本手册的无硬件测试，不能启动 `serial_echo` 或 `real_serial`。

进入串口测试前必须确认：

```bash
test -e /dev/serial0 && readlink -f /dev/serial0
grep -o 'console=serial0,[^ ]*' /boot/firmware/cmdline.txt || true
```

通过标准：

- `/dev/serial0` 存在。
- 内核命令行中没有 `console=serial0,115200`。
- 串口登录服务不再占用该 UART。
- 已完成 Pi UART 本地回环测试。

#### 限制 B：`/wheel_states` 目前不是真实反馈

当前 `/mars_rover/wheel_states` 是目标值回显：

```text
feedback_is_real=false
```

它只能证明 ROS 2 计算并发出了什么目标，不能证明：

- 电机实际转动了。
- 转向实际到达了目标角度。
- 电机速度与目标一致。
- 某个轮组没有机械卡滞。

真实硬件验收必须同时观察实物、驱动器状态和 STM32 返回状态，不能只看 `/wheel_states`。

#### 限制 C：当前整车倒车运动学不能直接用于硬件

当前 `CRAB` 实现使用速度模长计算轮速。正向前进和侧移的目标符合当前设计，但负 `linear.x` 不会直接生成普通的负轮速倒车目标。现有单元测试也没有覆盖整车倒车。

因此，在修正运动学并补充测试前：

- `RAW_WHEEL_TEST` 中的单轮正转、反转可以测试，因为该模式直接保留 `linear.x` 的正负号。
- `CRAB` 整车只允许先测试正向和侧向目标。
- 不得把逗号键产生的负 `linear.x` 当作已经验证的整车倒车功能。
- `SPIN_IN_PLACE` 的正负方向必须先在架空状态核对四轮角度和转向符号。
- 四轮落地测试前，必须补上负向 `CRAB`、两种旋转方向和转向角等价优化测试。

这不是操作限制可以解决的问题，而是当前代码需要修正的功能缺口。

---

## 3. 真实电机上电前的硬性条件

以下任意一项不满足时，只能做无硬件或无电机功率测试：

- [ ] 电池铭牌、标称电压、满充电压、BMS 持续电流和峰值电流已经确认。
- [ ] 电池正极附近已经安装合适的主保险。
- [ ] 已安装明确支持相应直流电压和直流电流的总隔离开关。
- [ ] 已安装物理急停和接触器，急停能够直接切断电机驱动器功率支路。
- [ ] Pi、STM32 和驱动器逻辑电源已经逐路测量，极性和电压正确。
- [ ] MKS SERVO57D 的供电支路实测不超过 `24 VDC`。
- [ ] 驱动器、电机、编码器/Hall、RS-485 和保护地接线已经由第二人复核。
- [ ] 机械架能够稳定架空车轮，测试时车轮不会接触地面、线缆或人员。
- [ ] 两名人员在场：一人操作电脑，另一人站在物理急停旁观察车辆。
- [ ] 原点开关已经选型、安装并由 STM32 负责人验证；否则禁止自动 homing。

软件急停、键盘 `k`、停止发送 `/cmd_vel` 和 `Ctrl+C` 都不能替代物理急停。它们依赖软件、网络、Pi、STM32 和供电仍正常工作。

---

## 4. 终端分工与环境变量

建议同时准备四个终端：

| 终端 | 所在设备 | 用途 |
|---|---|---|
| PC-A | 电脑 ROS 2 容器 | 运行键盘控制，必须保持前台和 TTY |
| PC-B | 电脑 ROS 2 容器 | 切换模式、观察话题、发送软件急停 |
| PI-A | SSH 到 Pi | 启动 Pi bringup，持续观察节点日志 |
| PI-B | SSH 到 Pi | 检查参数、状态、串口和执行停机命令 |

### 4.1 Pi 每个新终端的初始化

当前 Pi 部署提供统一环境脚本：

```bash
source /home/rover/rover/env.sh
```

然后检查：

```bash
echo "$ROS_DISTRO"
echo "$ROS_DOMAIN_ID"
echo "$ROS_AUTOMATIC_DISCOVERY_RANGE"
ros2 pkg prefix mars_rover_bringup
```

期望：

```text
jazzy
42
SUBNET
```

如果后续 Pi 被重新部署到其他路径，应修改统一环境脚本，而不是每次手动猜测 `install/setup.bash` 的位置。

### 4.2 电脑 Docker 容器的启动

在 Ubuntu 电脑宿主机打开 PC-A：

```bash
cd ~/rover/mars_rover_ws
export PI_IP=<Pi当前局域网IP>

docker run --rm -it \
  --name mars-rover-pc \
  --network host \
  -e ROS_DOMAIN_ID=42 \
  -e ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET \
  -e ROS_STATIC_PEERS="$PI_IP" \
  -e ROS2CLI_NO_DAEMON=1 \
  -v "$PWD":/workspace/mars_rover_ws \
  -w /workspace/mars_rover_ws \
  mars-rover-jazzy:local \
  bash
```

`<Pi当前局域网IP>` 必须替换成真实 IP，不要保留尖括号。若局域网组播发现始终稳定，可以不设置 `ROS_STATIC_PEERS`；若使用，则 Pi 端也应把电脑 IP 设置为静态 peer。

进入容器后执行：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
echo "$ROS_DISTRO"
echo "$ROS_DOMAIN_ID"
ros2 pkg prefix mars_rover_bringup
```

在宿主机另开 PC-B，并进入同一个容器：

```bash
docker exec -it mars-rover-pc bash
```

进入后仍需执行：

```bash
source /opt/ros/jazzy/setup.bash
source /workspace/mars_rover_ws/install/setup.bash
export ROS_DOMAIN_ID=42
export ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET
export ROS2CLI_NO_DAEMON=1
```

### 4.3 如果电脑原生运行 Ubuntu 24.04 + Jazzy

不需要 Docker，直接在每个电脑终端执行：

```bash
source /opt/ros/jazzy/setup.bash
source ~/rover/mars_rover_ws/install/setup.bash
export ROS_DOMAIN_ID=42
export ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET
export ROS2CLI_NO_DAEMON=1
```

后续 ROS 2 命令完全相同。

---

## 5. 测试总表与进入条件

| 编号 | 测试 | 电机功率 | 前置条件 | 通过后允许进入 |
|---:|---|---|---|---|
| T0 | 两端版本、构建和单元测试 | 断开 | 代码已部署 | T1 |
| T1 | IP 与双向 DDS 基础测试 | 断开 | 同一路由器 | T2 |
| T2 | 跨主机项目 dry-run | 断开 | T1 通过 | T3 |
| T3 | 命令超时、软件急停、断网归零 | 断开 | T2 通过 | T4 |
| T4 | Pi UART 检查和回环 | 断开 | `/dev/serial0` 可用 | T5 |
| T5 | Pi 与 STM32 协议、ACK、STATUS | 断开 | STM32 通信固件完成 | T6 |
| T6 | 单轮 launch，硬件保持禁用 | 断开 | T5 通过 | T7 |
| T7 | 物理急停和接触器断电测试 | 可短时接通 | 全部电气门槛满足 | T8 |
| T8 | `front_left` 转向 homing 与小角度 | 接通单轮支路 | T7 通过 | T9 |
| T9 | `front_left` 行走正反转和停止 | 接通单轮支路 | T8 通过 | T10 |
| T10 | 串口断开、STM32 watchdog、驱动故障 | 接通单轮支路 | T9 通过 | T11 |
| T11 | 其余三个轮组逐轮重复 | 每次一个支路 | 单轮结果稳定 | T12 |
| T12 | 四轮架空 `STOP/CRAB/SPIN` | 四轮支路 | 运动学缺口修复并补测 | T13 |
| T13 | 四轮低速落地 | 四轮支路 | T12 全部通过 | 日常运行 |

任何测试失败都要记录实际现象、状态话题、节点日志和恢复方法。不能只记录“失败”。

---

## 6. T0：两端版本、构建和测试基线

### 6.1 电脑端

在电脑 ROS 2 环境中执行：

```bash
cd /workspace/mars_rover_ws
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
source install/setup.bash
colcon test
colcon test-result --verbose
```

原生电脑把路径替换为自己的工作区。

记录：

```bash
git rev-parse HEAD
git status --short
uname -m
printenv ROS_DISTRO
```

### 6.2 Pi 端

在 PI-B 执行：

```bash
source /home/rover/rover/env.sh
cd /home/rover/rover/current
colcon test
colcon test-result --verbose
uname -m
printenv ROS_DISTRO
```

### 6.3 通过标准

- 两端均为 ROS 2 Jazzy。
- 电脑构建产物来自电脑架构，Pi 构建产物来自 arm64 Pi，未交叉复制 `install/`。
- `colcon test-result --verbose` 没有失败项。
- 电脑和 Pi 部署的源码版本一致；若工作区有未提交修改，必须保存差异清单和部署包 SHA256。
- 两端的自定义消息接口一致，否则 DDS 能发现节点也可能无法正常交换项目消息。

---

## 7. T1：电脑与 Pi 的 IP 和双向 DDS 测试

### 7.1 检查 IP 连通性

电脑执行：

```bash
ip -brief address
ping -c 4 <Pi当前局域网IP>
```

Pi 执行：

```bash
ip -brief address
ping -c 4 <电脑当前局域网IP>
```

两个方向都必须成功。仅能 SSH 到 Pi 不等于 ROS 2 DDS 已经通过，因为 SSH 使用 TCP，而 DDS 发现和数据交换还依赖 UDP、组播或静态 peer。

### 7.2 电脑到 Pi

PI-B 先订阅：

```bash
source /home/rover/rover/env.sh
ros2 topic echo /pc_to_pi_test std_msgs/msg/String
```

PC-B 连续发布三条不同消息：

```bash
ros2 topic pub --once /pc_to_pi_test std_msgs/msg/String "{data: 'pc-message-1'}"
ros2 topic pub --once /pc_to_pi_test std_msgs/msg/String "{data: 'pc-message-2'}"
ros2 topic pub --once /pc_to_pi_test std_msgs/msg/String "{data: 'pc-message-3'}"
```

Pi 必须完整收到三条。

### 7.3 Pi 到电脑

PC-B 先订阅：

```bash
ros2 topic echo /pi_to_pc_test std_msgs/msg/String
```

PI-B 发布：

```bash
ros2 topic pub --once /pi_to_pc_test std_msgs/msg/String "{data: 'pi-message-1'}"
ros2 topic pub --once /pi_to_pc_test std_msgs/msg/String "{data: 'pi-message-2'}"
ros2 topic pub --once /pi_to_pc_test std_msgs/msg/String "{data: 'pi-message-3'}"
```

电脑必须完整收到三条。

### 7.4 失败时按此顺序定位

1. 两端确认 `ROS_DOMAIN_ID=42`。
2. 两端确认 `ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET`。
3. 确认电脑 Docker 使用 `--network host`。
4. 确认电脑和 Pi 不在访客网络或启用了客户端隔离的 Wi-Fi 中。
5. 暂时设置双方 `ROS_STATIC_PEERS` 为对方当前 IP。
6. 检查电脑和 Pi 防火墙，不要直接永久关闭；应为当前局域网范围配置 DDS UDP 规则。
7. 检查两端 RMW 实现：

```bash
echo "${RMW_IMPLEMENTATION:-default}"
ros2 doctor --report
```

8. 停止旧 ROS daemon 干扰：

```bash
ros2 daemon stop
```

本手册设置了 `ROS2CLI_NO_DAEMON=1`，正常情况下命令行工具不依赖旧 daemon 缓存。

### 7.5 通过标准

- 每个方向三条消息全部收到。
- 单条消息等待时间不超过 5 秒。
- 记录双方 IP、网络接口、Domain ID、RMW、静态 peer 和防火墙状态。

---

## 8. T2：跨主机项目 dry-run

该测试不会打开 `/dev/serial0`，不会向 STM32 或电机发送命令。

### 8.1 Pi 启动 dry-run

PI-A：

```bash
source /home/rover/rover/env.sh
ros2 launch mars_rover_bringup pi_bringup_dry_run.launch.py
```

保持 PI-A 前台运行，不要关闭。

PI-B 检查节点：

```bash
source /home/rover/rover/env.sh
ros2 node list | sort
```

应至少看到：

```text
/drive_mode_manager
/four_wheel_kinematics
/joint_state_republisher
/robot_state_publisher
/safety_gate
/stm32_bridge
```

### 8.2 电脑确认能看到 Pi 节点和话题

PC-B：

```bash
ros2 node list | sort
ros2 topic list | sort
```

重点话题应包括：

```text
/cmd_vel
/mars_rover/drive_mode_request
/mars_rover/drive_mode
/mars_rover/safety_state
/mars_rover/safe_cmd_vel
/mars_rover/wheel_setpoints
/mars_rover/wheel_states
/mars_rover/stm32/status
/joint_states
```

### 8.3 启动监视窗口

PC-B 可依次检查，正式测试时建议每次只在一个窗口观察一个重点话题：

```bash
ros2 topic echo /mars_rover/drive_mode
ros2 topic echo /mars_rover/safety_state std_msgs/msg/String
ros2 topic echo /mars_rover/wheel_setpoints mars_rover_msgs/msg/WheelSetpointArray
ros2 topic echo /mars_rover/wheel_states mars_rover_msgs/msg/WheelStateArray
ros2 topic echo /mars_rover/stm32/status mars_rover_msgs/msg/Stm32Status
```

检查频率：

```bash
ros2 topic hz /mars_rover/safe_cmd_vel
ros2 topic hz /mars_rover/wheel_setpoints
ros2 topic hz /mars_rover/stm32/status
```

### 8.4 切换到 CRAB

PC-B：

```bash
ros2 topic pub --once \
  /mars_rover/drive_mode_request \
  std_msgs/msg/String \
  "{data: 'CRAB'}"
```

确认：

```bash
ros2 topic echo --once /mars_rover/drive_mode mars_rover_msgs/msg/DriveMode
```

期望 `mode: 1`，并且 `reason` 表示请求已接受或当前已经是 `CRAB`。

### 8.5 启动电脑键盘

PC-A：

```bash
source /opt/ros/jazzy/setup.bash
source /workspace/mars_rover_ws/install/setup.bash
ros2 launch mars_rover_bringup pc_teleop.launch.py \
  with_rviz:=false \
  speed:=0.02 \
  turn:=0.05 \
  repeat_rate:=10.0 \
  key_timeout:=0.4
```

PC-A 必须是交互式 TTY。启动后先不要按键，确认界面显示官方 `teleop_twist_keyboard` 键位说明。

在 `CRAB` 模式下：

- 按 `i`：发送低速正向命令。
- 按 `k`：发送零速度。
- 按大写 `J` 或 `L`：发送横向平移命令，必须先在 dry-run 中观察转向角方向。
- 当前不要用逗号键测试整车倒车，原因见 2.3 限制 C。

### 8.6 dry-run 期望结果

按 `i` 时：

- `/cmd_vel.linear.x` 约为 `0.02`。
- `/mars_rover/safety_state.data` 为 `ok`。
- `/mars_rover/safe_cmd_vel.linear.x` 约为 `0.02`。
- `/mars_rover/wheel_setpoints` 中四个轮组顺序固定为 `front_left`、`front_right`、`rear_left`、`rear_right`。
- 四个轮组均 `enabled=true`。
- 四个轮组 `drive_velocity` 均约为 `0.02 m/s`。
- 正向 CRAB 时四个 `steering_angle` 应接近 `0 rad`。

按 `k` 时：

- `/cmd_vel` 归零。
- `/safe_cmd_vel` 归零。
- 四个轮组目标速度归零。

状态话题应满足：

- dry-run 中 `online=true` 是软件模拟在线，不代表 STM32 在线。
- `serial_connected=false`。
- `wheel_states.states[*].feedback_is_real=false`。
- Pi 不访问 `/dev/serial0`。

### 8.7 通过标准

- 电脑能够看到 Pi 上的六个节点。
- 电脑发送的模式和键盘命令能到达 Pi。
- Pi 计算出的模式、限幅命令、四轮目标和目标回显能返回电脑。
- 正向、停止、侧移的目标值符合预期。
- dry-run 全程没有打开串口。

---

## 9. T3：安全超时、软件急停和断网测试

### 9.1 命令超时归零

1. 保持 Pi dry-run 和电脑 teleop 运行。
2. 按 `i`，确认四轮目标速度非零。
3. 停止按键，或直接在 PC-A 按 `Ctrl+C` 结束 teleop。
4. 在 PC-B 或 PI-B 观察：

```bash
ros2 topic echo /mars_rover/safety_state std_msgs/msg/String
```

```bash
ros2 topic echo /mars_rover/wheel_setpoints mars_rover_msgs/msg/WheelSetpointArray
```

期望在最后一条有效 `/cmd_vel` 后约 `0.5 s` 内：

- `safety_state` 变为 `cmd_timeout`。
- `/safe_cmd_vel` 归零。
- 四轮 `drive_velocity` 归零。

建议通过带时间戳的录包或测试脚本测量，正式验收阈值为：

```text
目标值归零 <= 0.55 s
```

### 9.2 软件急停

PC-B 触发：

```bash
ros2 topic pub --once \
  /mars_rover/emergency_stop \
  std_msgs/msg/Bool \
  "{data: true}"
```

即使 PC-A 持续发送运动命令，也应看到：

- `safety_state=software_estop`。
- `/safe_cmd_vel` 为零。
- 四轮目标速度为零。

解除软件急停：

```bash
ros2 topic pub --once \
  /mars_rover/emergency_stop \
  std_msgs/msg/Bool \
  "{data: false}"
```

解除后仍需重新发送有效键盘命令，不能因为清除急停而自行恢复旧运动。

### 9.3 电脑断链

1. 让 teleop 正在发送低速正向命令。
2. 停止电脑容器，或临时断开电脑网络。
3. 在 PI-B 本地观察 `/mars_rover/wheel_setpoints`。
4. 目标必须在约 `0.5 s` 内归零，Pi 节点继续运行。
5. 恢复网络和电脑容器。
6. 重新确认节点发现、重新发送驱动模式，再启动 teleop。

网络恢复本身不能使车辆自动恢复旧命令。

### 9.4 非法模式测试

PC-B：

```bash
ros2 topic pub --once \
  /mars_rover/drive_mode_request \
  std_msgs/msg/String \
  "{data: 'INVALID_MODE'}"
```

当前模式不应改变，Pi 日志应明确记录请求被拒绝。

### 9.5 通过标准

- 命令超时能归零。
- 软件急停优先于运动命令。
- 断网后 Pi 独立归零，不依赖电脑发送停止命令。
- 网络恢复后不会自动恢复旧运动。
- 非法模式不会进入未定义状态。

---

## 10. T4：Pi UART 准入检查和回环

这一阶段仍不连接 STM32，不给电机驱动器上电。

### 10.1 检查串口资源

PI-B：

```bash
test -e /dev/serial0 && ls -l /dev/serial0
readlink -f /dev/serial0
groups
systemctl status serial-getty@serial0.service --no-pager
grep -o 'console=serial0,[^ ]*' /boot/firmware/cmdline.txt || true
```

要求：

- `/dev/serial0` 存在。
- 当前用户具有串口访问权限，通常属于 `dialout` 组。
- `serial-getty@serial0.service` 未占用该串口。
- 内核命令行不包含串口控制台参数。

若不满足，先按《火星车硬件部署与联调操作手册》第 8 章修正并重启 Pi。

### 10.2 物理回环

1. Pi 关机。
2. 不连接 STM32。
3. 用短线连接 Pi GPIO14/TX 与 GPIO15/RX，并确认只连接正确针脚。
4. Pi 开机。
5. 使用串口工具发送固定字节串并确认原样接收。
6. 测试结束后关机并拆除回环线。

回环测试用于证明 Pi UART 本身、设备映射和权限正常，不证明 STM32 协议正常。

### 10.3 通过标准

- 发送和接收字节完全一致。
- 无乱码、丢字节或设备占用错误。
- 重启后 `/dev/serial0` 映射稳定。

---

## 11. T5：Pi 与 STM32 协议联调

### 11.1 接线和供电边界

Pi 关机、STM32 断电后连接：

| Pi | STM32 | 说明 |
|---|---|---|
| GPIO14 / 物理针脚 8 / TX | USART1 RX | Pi 发、STM32 收 |
| GPIO15 / 物理针脚 10 / RX | USART1 TX | Pi 收、STM32 发 |
| GND / 物理针脚 6 | GND | 通信参考地 |

不得连接两块板的 `5V` 或 `3.3V` 电源针脚。Pi GPIO 只允许 `3.3V` TTL 电平。

通信参数固定为：

```text
115200 baud
8 data bits
no parity
1 stop bit
no flow control
```

电机驱动器功率支路保持断开。STM32 固件必须处于“上电默认禁用”状态。

### 11.2 Pi 启动串口联调模式

先结束 dry-run，再在 PI-A 执行：

```bash
source /home/rover/rover/env.sh
ros2 launch mars_rover_bringup pi_bringup_serial_echo.launch.py \
  serial_port:=/dev/serial0
```

PC-B 观察：

```bash
ros2 topic echo /mars_rover/stm32/status mars_rover_msgs/msg/Stm32Status
```

同时检查频率：

```bash
ros2 topic hz /mars_rover/stm32/status
```

### 11.3 期望状态

STM32 固件按当前协议实现后，应看到：

- `serial_connected=true`。
- `online=true`。
- `timeout=false`。
- `estop_active=false`，前提是硬件急停状态允许。
- `fault=false`。
- `fault_code=0`。
- `last_rx_age` 持续刷新。
- `last_ack_sequence_id` 随命令更新。

Pi 应约 `20 Hz` 发送 W 命令，STM32 对每条有效命令返回 ACK，并约 `5 Hz` 返回 STATUS。

### 11.4 协议错误测试

该部分最好由 STM32 负责人配合，通过调试固件或串口注入工具完成：

- CRC 错误帧必须被拒绝。
- 超过 512 字节的帧必须被拒绝。
- JSON 字段缺失、版本错误或数值越界必须返回对应故障码。
- 超过 `0.5 s` 未收到有效命令时，STM32 必须停止全部输出并上报 timeout。
- 急停输入有效时，STM32 必须上报 `es=1`，并忽略运动使能。

### 11.5 通过标准

- 连续运行至少 10 分钟，无持续 CRC、解析、串口读写或序号错误。
- ACK 和 STATUS 均能被 Pi 正确解析。
- 拔掉 Pi TX 或停止 Pi 节点后，STM32 在 `0.5 s` 内进入停止状态。
- 电机功率尚未接通，测试期间没有电机动作。

---

## 12. T6：单轮真实 launch，但保持硬件禁用

### 12.1 启动顺序

结束 `serial_echo`。PI-A 执行：

```bash
source /home/rover/rover/env.sh
ros2 launch mars_rover_bringup pi_bringup_real_single_wheel.launch.py \
  serial_port:=/dev/serial0 \
  hardware_enable:=false
```

该 launch 默认：

```text
drive mode = RAW_WHEEL_TEST
hardware_output_mode = single_wheel
active_test_wheel = front_left
hardware_enable = false
```

### 12.2 检查参数

PI-B：

```bash
ros2 param get /stm32_bridge hardware_enable
ros2 param get /stm32_bridge hardware_output_mode
ros2 param get /stm32_bridge active_test_wheel
ros2 param get /four_wheel_kinematics active_test_wheel
ros2 topic echo --once /mars_rover/drive_mode mars_rover_msgs/msg/DriveMode
```

期望：

```text
false
single_wheel
front_left
front_left
mode: 3
```

### 12.3 发送测试目标，但不允许执行

PC-A 启动低速键盘：

```bash
ros2 launch mars_rover_bringup pc_teleop.launch.py \
  with_rviz:=false \
  speed:=0.02 \
  turn:=0.05 \
  repeat_rate:=10.0 \
  key_timeout:=0.4
```

按 `i`、`k`、`j`、`l`，观察 `/wheel_setpoints`：

- 只有 `front_left.enabled=true`。
- 其他三个轮组 `enabled=false`、速度为零。
- `i` 对应正 `drive_velocity`。
- 逗号键对应负 `drive_velocity`。
- `j/l` 对应正负 `steering_angle`，绝对值受 `0.35 rad` 限制。

由于 `hardware_enable=false`，Pi 发给 STM32 的可执行使能必须保持关闭，电机不得动作。

### 12.4 策略拒绝测试

保持 single-wheel launch，尝试请求 `CRAB`：

```bash
ros2 topic pub --once \
  /mars_rover/drive_mode_request \
  std_msgs/msg/String \
  "{data: 'CRAB'}"
```

模式管理器会接受模式字符串，但 `stm32_bridge` 的 `single_wheel` 硬件策略必须拒绝不符合策略的四轮可执行帧。PI-A 日志中应能看到策略拒绝信息，电机仍不得动作。

测试后把模式切回：

```bash
ros2 topic pub --once \
  /mars_rover/drive_mode_request \
  std_msgs/msg/String \
  "{data: 'RAW_WHEEL_TEST'}"
```

### 12.5 通过标准

- 串口和 STM32 状态正常。
- `hardware_enable=false` 被确认。
- 只有 `front_left` 产生单轮测试目标。
- 不合规的四轮模式不能变成可执行硬件帧。
- 全程无电机动作。

---

## 13. T7：物理急停与接触器测试

这一阶段首次涉及电机功率。必须两人操作，底盘架空，只接通 `front_left` 对应驱动器支路。

### 13.1 测试前状态

- 总隔离开关关闭。
- 物理急停按下。
- `hardware_enable=false`。
- 键盘停止，`/cmd_vel` 为零。
- `RAW_WHEEL_TEST` 模式。
- 只有 `front_left` 支路连接。

### 13.2 只验证断电链

1. 接通逻辑电源，让 Pi 和 STM32 正常启动。
2. 启动 real single-wheel launch，但保持 `hardware_enable=false`。
3. 确认 ROS 2 状态正常。
4. 接通总隔离开关和单轮驱动器支路。
5. 释放物理急停，使接触器吸合。
6. 不发送运动命令。
7. 按下物理急停。

必须确认：

- 接触器立即释放。
- 电机驱动器功率支路被物理切断。
- Pi 和 STM32 逻辑电源最好保持，以便记录故障状态。
- STM32 STATUS 上报 `estop_active=true`。
- ROS 2 `safety_state` 变为 `stm32_estop` 或等效状态。

物理急停如果只发送一个 GPIO 信号而没有切断驱动器功率，不满足本项目的硬件急停要求。

---

## 14. T8：front_left 转向 homing 与小角度测试

### 14.1 前置检查

- 原点开关已经验证，触发方向和有效电平已记录。
- STM32 homing 状态机已完成独立测试。
- 转向减速器、机械限位和线缆余量已检查。
- 行走电机驱动保持停止。
- 车轮架空。

### 14.2 启动并检查禁用状态

按第 12 章启动 single-wheel launch，保持：

```bash
ros2 param get /stm32_bridge hardware_enable
```

结果必须为 `false`。

### 14.3 使能前确认

PC-B 或 PI-B 持续观察：

```bash
ros2 topic echo /mars_rover/stm32/status mars_rover_msgs/msg/Stm32Status
```

必须同时满足：

- `online=true`
- `serial_connected=true`
- `timeout=false`
- `estop_active=false`
- `fault=false`
- `fault_code=0`

然后由急停旁人员口头确认“可以使能”，PI-B 执行：

```bash
ros2 param set /stm32_bridge hardware_enable true
ros2 param get /stm32_bridge hardware_enable
```

### 14.4 小角度测试

PC-A 中：

1. 按 `j`，目标角应为小的正值。
2. 立即按 `k`。
3. 观察车轮实际转向方向并记录。
4. 按 `l`，目标角应为小的负值。
5. 立即按 `k`。
6. 首次建议只使用 `turn:=0.05 rad`。

注意：在 `RAW_WHEEL_TEST` 中，`angular.z` 被解释为单轮目标转向角，不是整车角速度。

测试后立即禁用：

```bash
ros2 param set /stm32_bridge hardware_enable false
```

### 14.5 通过标准

- homing 只向预定方向低速运动。
- 原点开关触发后停止，不继续顶住机械限位。
- `+0.05 rad` 与 `-0.05 rad` 的实物方向和项目坐标定义一致。
- 停止后无持续爬行、振荡、丢步或报警。
- 软件目标与 STM32 内部目标一致；若没有真实角度反馈，不得声称角度精度已经验证。

---

## 15. T9：front_left 行走电机正反转与停止

### 15.1 测试方式

仍使用 `RAW_WHEEL_TEST`。单轮模式直接使用 `linear.x` 的正负号，因此适合验证驱动方向。

1. 底盘保持架空。
2. 转向角先保持接近 `0 rad`。
3. 确认急停人员就位。
4. 确认 STM32 状态无故障。
5. 将 `hardware_enable` 设为 `true`。
6. PC-A 按 `i`，只保持约 1 秒，然后按 `k`。
7. 确认只有 `front_left` 行走轮正向转动。
8. 等待轮子完全停止。
9. 按逗号键，只保持约 1 秒，然后按 `k`。
10. 确认同一车轮反向转动。
11. 将 `hardware_enable` 设为 `false`。

如果 BLD-305S 的最低稳定转速高于 `speed:=0.02 m/s` 对应转速，应由 STM32/驱动器负责人根据实测轮半径、减速比和驱动器最低转速计算测试值。不能通过盲目增加速度解决不转问题。

### 15.2 必须记录

| 项目 | 记录内容 |
|---|---|
| 正命令对应实物方向 | 车辆前进方向或相反 |
| 负命令对应实物方向 | 车辆后退方向或相反 |
| BLD-305S 目标 RPM | 实际发送值 |
| 实际 RPM | 若驱动器可读则记录 |
| 启停延迟 | 观察值 |
| 制动方式 | 自由停车、减速停车或制动 |
| 驱动器故障码 | 无故障写 0 |
| 电流和温升 | 实测值 |

### 15.3 立即停止条件

出现以下任一情况，急停人员立即按物理急停：

- 实际转动的不是 `front_left`。
- 正反方向与记录不一致且可能造成机械危险。
- 电机抖动、失速、异常噪声或线缆绞绕。
- 驱动器报警、冒烟、异味或温升异常。
- 按 `k` 或发布 STOP 后仍持续转动。
- ROS 2 已归零但实物未停止。

---

## 16. T10：故障、断链和 watchdog 验收

每个测试都从架空、低速、单轮开始。

### 16.1 软件急停

运动中发布：

```bash
ros2 topic pub --once \
  /mars_rover/emergency_stop \
  std_msgs/msg/Bool \
  "{data: true}"
```

要求：ROS 2 目标归零，串口帧取消使能，STM32 停止驱动。

### 16.2 物理急停

运动中按物理急停。要求：电机功率支路被硬件切断，停止不依赖 ROS 2。

### 16.3 停止电脑 teleop

运动中结束 PC-A teleop。要求：Pi 在约 `0.5 s` 内因 `cmd_timeout` 归零。

### 16.4 断开电脑网络

运动中断开电脑网络。要求：效果同上，Pi 节点继续运行。

### 16.5 停止 Pi bridge 或断开 Pi 到 STM32 UART

要求：STM32 自身 watchdog 在 `0.5 s` 内停止全部驱动输出。该测试不能依赖 Pi 再发送一条 STOP。

### 16.6 STM32 故障和驱动器故障

由 STM32 负责人使用可控方法模拟故障。要求：

- STM32 STATUS 中 `fault=true` 和正确 `fault_code`。
- ROS 2 `safety_state=stm32_fault`。
- `/safe_cmd_vel` 和轮速目标归零。
- 清除故障后不自动恢复旧运动，必须重新确认并重新发送命令。

### 16.7 每项测试后的恢复顺序

1. `hardware_enable=false`。
2. 键盘 `k` 或发布 STOP。
3. 确认实物停止。
4. 排查并清除故障源。
5. 确认 STATUS 恢复正常。
6. 清除软件急停时发布 `false`。
7. 重新取得两人确认后才能再次使能。

---

## 17. T11：其余三个轮组逐轮测试

不能因为 `front_left` 通过，就直接把四个支路全部接通。依次测试：

```text
front_right
rear_left
rear_right
```

每次只连接并启用一个轮组，重复 T8、T9 和 T10。

### 17.1 切换活动测试轮

当前 launch 默认 `front_left`。切换时，运动学节点和 bridge 的 `active_test_wheel` 必须保持一致：

```bash
ros2 param set /four_wheel_kinematics active_test_wheel front_right
ros2 param set /stm32_bridge active_test_wheel front_right
```

然后检查：

```bash
ros2 param get /four_wheel_kinematics active_test_wheel
ros2 param get /stm32_bridge active_test_wheel
```

切换前后都必须保持 `hardware_enable=false`。更稳妥的正式做法是为每个轮组提供经过审核的 launch 参数，而不是在带电状态临时修改两个参数。

### 17.2 每轮验收内容

- RS-485 地址与物理轮组对应。
- 转向正负方向一致。
- 行走正负方向一致。
- homing 与限位有效。
- STOP、软件急停、物理急停、超时和 watchdog 有效。
- 驱动器故障码能正确映射到轮组。

四轮方向记录必须使用同一车体坐标系，不能简单记录“电机顺时针/逆时针”，因为左右侧安装方向可能镜像。

---

## 18. T12：四轮架空测试

### 18.1 进入条件

执行四轮真实控制前，必须全部满足：

- 四个轮组分别通过 T8 至 T10。
- 四个转向零位和方向已经记录。
- 四个行走方向已经统一到车辆前进方向。
- 两条 RS-485 总线地址 1 至 4 无冲突。
- 保险、急停、接触器和分支保护完成。
- 车体稳定架空。
- 当前运动学已修正整车倒车问题。
- 已新增并通过负向 `CRAB`、正负 `SPIN_IN_PLACE` 和角度/轮速等价处理测试。

如果最后三项尚未完成，只能查看 dry-run 目标，不得执行四轮落地动作。

### 18.2 启动 full-vehicle launch

先结束 single-wheel launch。PI-A：

```bash
source /home/rover/rover/env.sh
ros2 launch mars_rover_bringup pi_bringup_real_full_vehicle.launch.py \
  serial_port:=/dev/serial0 \
  hardware_enable:=false
```

检查：

```bash
ros2 param get /stm32_bridge hardware_enable
ros2 param get /stm32_bridge hardware_output_mode
ros2 topic echo --once /mars_rover/drive_mode mars_rover_msgs/msg/DriveMode
```

期望：

```text
hardware_enable = false
hardware_output_mode = full_vehicle
drive mode = STOP
```

### 18.3 STOP 测试

发布：

```bash
ros2 topic pub --once \
  /mars_rover/drive_mode_request \
  std_msgs/msg/String \
  "{data: 'STOP'}"
```

在 `hardware_enable=false` 和 `true` 两种状态下，四轮速度都必须为零。使能状态下的 STOP 也不能产生行走动作。

### 18.4 正向 CRAB 架空测试

1. 发布 `CRAB`。
2. 确认四个轮子目标角接近 `0 rad`。
3. 确认 STATUS 无故障。
4. 急停旁人员确认后设置 `hardware_enable=true`。
5. PC-A 按 `i` 不超过 1 秒，然后按 `k`。
6. 确认四个轮子都向车辆前进方向转动。
7. 立即设置 `hardware_enable=false`。

### 18.5 侧向 CRAB 架空测试

使用大写 `J/L` 发送 `linear.y`。先观察转向过程，确保线缆不会缠绕。四轮应转到相同方向，再以极短时间低速驱动。

### 18.6 SPIN_IN_PLACE 架空测试

先发布模式：

```bash
ros2 topic pub --once \
  /mars_rover/drive_mode_request \
  std_msgs/msg/String \
  "{data: 'SPIN_IN_PLACE'}"
```

`j/l` 在该模式下用于发送正负 `angular.z`。首次只观察目标角，不使能硬件。确认四轮切向布局、正负方向和轮速符号都与预期一致后，才允许极短时间使能。

### 18.7 四轮架空通过标准

- STOP 始终保持零速度。
- CRAB 正向时四轮方向一致。
- 侧移时四个转向角一致且线缆安全。
- 正负 SPIN 都能形成正确切向布局和驱动方向。
- 任一轮故障都能使整车目标归零。
- 电脑断链、Pi 串口断链和物理急停均通过。
- 没有把目标回显误当成真实反馈。

---

## 19. T13：四轮低速落地测试

落地测试只能在 T12 通过后进行，并且需要封闭、平整、无人的测试区域。

### 19.1 第一次落地只做三件事

1. `STOP`：确认上电和使能后车辆静止。
2. `CRAB` 正向：以 `0.02 m/s` 发出不足 1 秒的短脉冲，然后停止。
3. 物理急停：低速运动中验证接触器断电和车辆停车距离。

不要在第一次落地同时测试高速、倒车、侧移和原地旋转。

### 19.2 逐步扩展

每次只增加一个变量：

1. 延长正向运行时间。
2. 验证直线偏差。
3. 验证侧向 CRAB。
4. 验证原地旋转。
5. 运动学倒车修复并通过架空测试后，再验证倒车。
6. 最后才逐步提高速度上限。

必须记录实际停车距离、电流、温升、轮胎打滑、转向误差和网络丢包情况。

---

## 20. 每次日常启动：无硬件 dry-run

这是修改代码、换网络或重新部署后应首先执行的启动方式。

### 20.1 Pi

```bash
ssh rover@mars-rover-pi.local
source /home/rover/rover/env.sh
ros2 launch mars_rover_bringup pi_bringup_dry_run.launch.py
```

### 20.2 电脑

启动 ROS 2 容器后：

```bash
source /opt/ros/jazzy/setup.bash
source /workspace/mars_rover_ws/install/setup.bash
ros2 launch mars_rover_bringup pc_teleop.launch.py \
  with_rviz:=false \
  speed:=0.02 \
  turn:=0.05
```

另一个电脑终端切换模式：

```bash
ros2 topic pub --once \
  /mars_rover/drive_mode_request \
  std_msgs/msg/String \
  "{data: 'CRAB'}"
```

按 `i` 测试前进，按 `k` 停止。退出时先按 `k`，再分别 `Ctrl+C` 结束电脑和 Pi 节点。

---

## 21. 每次日常启动：真实单轮硬件控制

### 21.1 上电前

1. 底盘架空。
2. 总隔离开关关闭。
3. 物理急停按下。
4. 只连接计划测试的一个轮组支路。
5. 检查功率线、Hall/编码器线、RS-485 和机械固定。
6. 启动 Pi 与 STM32 逻辑电源。
7. 确认 `/dev/serial0` 存在。

### 21.2 Pi 启动

```bash
ssh rover@mars-rover-pi.local
source /home/rover/rover/env.sh
ros2 launch mars_rover_bringup pi_bringup_real_single_wheel.launch.py \
  serial_port:=/dev/serial0 \
  hardware_enable:=false
```

### 21.3 电脑启动

```bash
ros2 launch mars_rover_bringup pc_teleop.launch.py \
  with_rviz:=false \
  speed:=0.02 \
  turn:=0.05 \
  repeat_rate:=10.0 \
  key_timeout:=0.4
```

### 21.4 状态确认

```bash
ros2 topic echo --once /mars_rover/stm32/status mars_rover_msgs/msg/Stm32Status
ros2 param get /stm32_bridge hardware_enable
ros2 param get /stm32_bridge hardware_output_mode
ros2 param get /stm32_bridge active_test_wheel
```

只有在状态无故障、轮组名称正确且 `hardware_enable=false` 已确认后，才接通总隔离开关、释放物理急停并使接触器吸合。

### 21.5 显式使能

由急停人员确认后：

```bash
ros2 param set /stm32_bridge hardware_enable true
```

键盘：

| 键 | RAW_WHEEL_TEST 中的作用 |
|---|---|
| `i` | 单轮正向驱动，转向目标为 0 |
| `,` | 单轮反向驱动，转向目标为 0 |
| `j` | 正转向角，驱动速度为 0 |
| `l` | 负转向角，驱动速度为 0 |
| `u/o` | 正向驱动并带正/负转向角，首次硬件测试不建议使用 |
| `k` | 发送零速度和零转向输入 |

终端实际显示的官方键位表是最终依据。

### 21.6 每次动作结束

```bash
ros2 param set /stm32_bridge hardware_enable false
```

确认实物完全停止后，再进行下一项接线或测试。

---

## 22. 每次日常启动：真实四轮硬件控制

这一流程只适用于四轮架空验收已经通过、当前运动学缺口已经修正的版本。

### 22.1 上电顺序

1. 测试区域清场，必要时先架空。
2. 总隔离开关关闭，物理急停按下。
3. 检查四轮机械、线缆、分支保险和驱动器状态。
4. `hardware_enable` 必须保持 `false`。
5. 接通 Pi 和 STM32 逻辑电源。
6. 等待网络、ROS 2 和 STM32 启动。
7. Pi 启动 full-vehicle launch。
8. 检查 STM32 STATUS 和当前模式 `STOP`。
9. 接通总隔离开关和电机驱动器功率支路。
10. 释放物理急停。
11. 再次确认车辆仍处于 STOP。
12. 由急停人员允许后，才设置 `hardware_enable=true`。

### 22.2 Pi 启动命令

```bash
ssh rover@mars-rover-pi.local
source /home/rover/rover/env.sh
ros2 launch mars_rover_bringup pi_bringup_real_full_vehicle.launch.py \
  serial_port:=/dev/serial0 \
  hardware_enable:=false
```

### 22.3 电脑启动命令

```bash
ros2 launch mars_rover_bringup pc_teleop.launch.py \
  with_rviz:=false \
  speed:=0.02 \
  turn:=0.05 \
  repeat_rate:=10.0 \
  key_timeout:=0.4
```

### 22.4 模式选择

STOP：

```bash
ros2 topic pub --once /mars_rover/drive_mode_request \
  std_msgs/msg/String "{data: 'STOP'}"
```

CRAB：

```bash
ros2 topic pub --once /mars_rover/drive_mode_request \
  std_msgs/msg/String "{data: 'CRAB'}"
```

SPIN_IN_PLACE：

```bash
ros2 topic pub --once /mars_rover/drive_mode_request \
  std_msgs/msg/String "{data: 'SPIN_IN_PLACE'}"
```

模式切换后必须确认：

```bash
ros2 topic echo --once /mars_rover/drive_mode mars_rover_msgs/msg/DriveMode
```

### 22.5 使能和运行

```bash
ros2 param set /stm32_bridge hardware_enable true
```

先短按、低速运行；每次改变模式前先按 `k`，再切到 `STOP`，确认四轮停止后再请求新模式。

不要在车辆运动中直接从 `CRAB` 切换到 `SPIN_IN_PLACE`。

---

## 23. 正常停止、异常急停和关机

### 23.1 正常停止

1. PC-A 按 `k`。
2. 发布 `STOP`：

```bash
ros2 topic pub --once /mars_rover/drive_mode_request \
  std_msgs/msg/String "{data: 'STOP'}"
```

3. 确认车轮停止。
4. 关闭真实输出：

```bash
ros2 param set /stm32_bridge hardware_enable false
```

5. 再次确认参数为 `false`。

### 23.2 异常时

发生不受控运动、方向错误、机械干涉、通信异常或驱动器报警时：

1. 急停旁人员立即按下物理急停。
2. 操作者不要用手阻挡车轮或转向机构。
3. 在逻辑电源仍可用时保存 `/stm32/status`、`safety_state` 和 Pi 日志。
4. 设置 `hardware_enable=false`。
5. 关闭总隔离开关。
6. 等待母线放电后再检查接线。

### 23.3 正常关机

1. `STOP`，确认所有轮子停止。
2. `hardware_enable=false`。
3. 按下物理急停，切断电机功率支路。
4. 在电脑 teleop 终端按 `Ctrl+C`。
5. 在 Pi bringup 终端按 `Ctrl+C`，等待所有节点退出。
6. Pi 执行：

```bash
sudo poweroff
```

7. 等待 Pi 完全关机。
8. 关闭总隔离开关。
9. 需要改线时再断开电池。

不能直接拔掉 Pi 电源作为日常关机方式，否则可能损坏文件系统。

---

## 24. 常用诊断命令

### 24.1 节点与话题

```bash
ros2 node list
ros2 topic list
ros2 topic info /cmd_vel --verbose
ros2 topic info /mars_rover/wheel_setpoints --verbose
```

### 24.2 查看控制链

```bash
ros2 topic echo /cmd_vel geometry_msgs/msg/Twist
ros2 topic echo /mars_rover/safe_cmd_vel geometry_msgs/msg/Twist
ros2 topic echo /mars_rover/wheel_setpoints mars_rover_msgs/msg/WheelSetpointArray
ros2 topic echo /mars_rover/wheel_states mars_rover_msgs/msg/WheelStateArray
```

判断问题所在：

- `/cmd_vel` 没有数据：电脑键盘或 DDS 链路问题。
- `/cmd_vel` 有数据但 `/safe_cmd_vel` 为零：查看 `safety_state`。
- `/safe_cmd_vel` 有数据但轮组目标不对：模式或运动学问题。
- 轮组目标正确但串口不通：`stm32_bridge`、UART 或协议问题。
- 串口状态正常但电机不动：STM32、RS-485、驱动器、使能、单位换算或功率问题。

### 24.3 查看安全和底层状态

```bash
ros2 topic echo /mars_rover/safety_state std_msgs/msg/String
ros2 topic echo /mars_rover/stm32/status mars_rover_msgs/msg/Stm32Status
ros2 param get /stm32_bridge hardware_enable
ros2 param list /stm32_bridge
```

### 24.4 检查频率

```bash
ros2 topic hz /cmd_vel
ros2 topic hz /mars_rover/safe_cmd_vel
ros2 topic hz /mars_rover/wheel_setpoints
ros2 topic hz /mars_rover/stm32/status
```

### 24.5 保存测试数据

正式测试建议录制：

```bash
mkdir -p ~/rover_test_bags
cd ~/rover_test_bags
ros2 bag record \
  /cmd_vel \
  /mars_rover/drive_mode \
  /mars_rover/safety_state \
  /mars_rover/safe_cmd_vel \
  /mars_rover/wheel_setpoints \
  /mars_rover/wheel_states \
  /mars_rover/stm32/status
```

录包不包含驱动器内部寄存器、真实电流和机械角度，仍需 STM32 日志和人工记录配合。

---

## 25. 常见问题定位

| 现象 | 首先检查 | 常见原因 |
|---|---|---|
| 电脑看不到 Pi 节点 | T1 双向 String | Domain ID、Docker 网络、防火墙、Wi-Fi 隔离 |
| teleop 启动后不能读键盘 | PC-A 是否为 TTY | 容器未使用 `-it`，或从后台无终端启动 |
| `/cmd_vel` 有值但 `/safe_cmd_vel` 为零 | `/safety_state` | cmd 超时、软件急停、STM32 offline/fault/timeout |
| dry-run 中 `serial_connected=false` | 无需修复 | 这是预期状态 |
| `/wheel_states` 看起来正常但电机不动 | `feedback_is_real` | 当前只是目标回显 |
| `/dev/serial0` 不存在 | Pi UART 配置 | 串口未启用或仍被控制台占用 |
| `serial_connected=true` 但 `online=false` | ACK/STATUS | STM32 未回包、波特率或协议不一致 |
| `hardware_enable=true` 仍不动 | STATUS、模式、策略、急停 | STM32 offline、错误模式、物理急停、驱动器未上电 |
| single-wheel 请求 CRAB 后无输出 | bridge 日志 | `single_wheel` 策略按设计拒绝四轮模式 |
| 只有部分轮子动作 | 地址与分支状态 | RS-485 ID 冲突、支路故障、接线映射错误 |
| 整车倒车目标异常 | 运动学测试 | 当前负 `linear.x` 功能缺口，不能靠接线修复 |
| `Ctrl+C` 后电机仍转 | 物理急停 | STM32 watchdog 或驱动器停止链存在严重问题 |

---

## 26. 每次测试记录模板

```text
日期/时间：
地点：
操作者：
急停监护人：

电脑 Git SHA：
Pi Git SHA/部署包 SHA256：
STM32 固件版本：
ROS_DISTRO：
ROS_DOMAIN_ID：
电脑 IP：
Pi IP：
RMW 实现：

Pi launch：
电脑 launch：
bridge_mode：
hardware_output_mode：
active_test_wheel：
hardware_enable 初始值：

测试编号：
测试动作：
目标值：
实际现象：
STM32 STATUS：
驱动器状态/故障码：
停止时间：
是否通过：
失败原因：
恢复方法：
日志或 rosbag 路径：
```

---

## 27. 最终验收清单

### 27.1 电脑到 Pi

- [ ] 两端双向标准 ROS 2 消息各通过 3 次。
- [ ] 电脑能看到 Pi 节点和项目话题。
- [ ] 键盘 `/cmd_vel` 能到达 Pi。
- [ ] 模式请求能到达 Pi，模式状态能返回电脑。
- [ ] 断网后约 `0.5 s` 内归零。

### 27.2 Pi 高层控制

- [ ] dry-run 中 STOP、CRAB、SPIN 和 RAW 目标符合已定义行为。
- [ ] 软件急停、命令超时、STM32 fault/timeout 联锁通过。
- [ ] 四轮固定顺序正确。
- [ ] 速度和转向限幅正确。
- [ ] 明确记录 `feedback_is_real=false`。
- [ ] 整车负向运动学缺口已经修正并补测。

### 27.3 Pi 到 STM32

- [ ] `/dev/serial0` 可用且未被控制台占用。
- [ ] UART 回环通过。
- [ ] 115200 8N1、CRC32、ACK、STATUS 通过。
- [ ] STM32 `0.5 s` watchdog 通过。
- [ ] 急停、超时、故障码正确返回 ROS 2。

### 27.4 单轮真实硬件

- [ ] `front_left` homing 通过。
- [ ] `front_left` 正负小角度转向通过。
- [ ] `front_left` 低速正反转通过。
- [ ] STOP、软件急停、物理急停、断网、断串口均能停止。
- [ ] 实际方向、地址、速度换算和故障码已有记录。

### 27.5 四轮真实硬件

- [ ] 四个轮组分别完成单轮测试。
- [ ] 四轮架空 STOP 通过。
- [ ] 四轮架空正向/侧向 CRAB 通过。
- [ ] 四轮架空正负 SPIN 通过。
- [ ] 任一底层故障都能使整车停止。
- [ ] 低速落地测试通过。

---

## 28. 当前结论

部署完成后，不应直接把 `pi_bringup_real_full_vehicle.launch.py` 当作日常第一条命令。正确顺序是：先通过跨主机 DDS 和 dry-run，随后验证命令超时与软件急停，再打通 UART、STM32 ACK/STATUS 和 watchdog，最后从单轮开始接通真实功率。

当前代码已经提供 dry-run、串口联调、单轮真实控制和四轮真实控制入口，但“存在 launch 文件”不等于对应硬件已经验收。特别是：

1. 当前 Pi 的 `/dev/serial0` 状态必须先修正。
2. `/wheel_states` 仍是目标回显，不是真实反馈。
3. 当前整车负向 `CRAB` 运动学存在功能缺口，修正前不能执行整车倒车验收。
4. 没有主保险、DC 总隔离开关、物理急停和接触器时，不得给电机驱动器功率支路上电。

满足这些条件并按 T0 至 T13 留下完整记录后，才能把系统从“软件可运行”提升为“能够重复、安全地启动实体四轮车进行键盘手动控制”。
