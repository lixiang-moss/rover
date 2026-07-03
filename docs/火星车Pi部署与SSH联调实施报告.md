# MARS Rover Pi 部署与 SSH 控制链路实施报告

## 1. 执行总结

本次工作已经把 `D:\rover\mars_rover_ws` 的当前本地源码部署到 Raspberry Pi，
并在 Pi 的原生 Ubuntu 24.04.4 arm64、ROS 2 Jazzy 环境中完成编译、测试和
无硬件 `dry_run` 联调。

最终结果如下：

| 项目 | 结果 | 说明 |
|---|---|---|
| Pi 原生部署 | 通过 | Pi 未安装、未运行 Docker |
| 部署包完整性 | 通过 | 电脑与 Pi 上的 SHA256 一致 |
| ROS 2 依赖检查 | 通过 | Pi 不使用的 RViz/GUI 依赖被明确跳过 |
| `colcon build` | 通过 | 5 个 ROS 2 包全部完成 |
| `colcon test` | 通过 | 51 项测试，0 错误、0 失败、0 跳过 |
| Pi dry-run 启动 | 通过 | 6 个预期节点全部启动 |
| 运动控制链路 | 通过 | CRAB、四轮目标、回显、停止和恢复均通过 |
| 命令超时归零 | 通过 | 最终版本实测约 0.476 秒 |
| SSH 键盘控制链路 | 通过 | 按键可形成四轮 `0.02 m/s` 目标并停止 |
| 节点正常关闭 | 通过 | 无 Traceback、RCLError、残留进程 |
| Windows Docker DDS | 未验收 | 用户取消 WSL，Docker 引擎不能运行 |
| Windows ROS 2 到 Pi 的跨主机 DDS | 未验收 | 当前电脑没有可运行的 ROS 2 环境 |
| Pi 到 STM32 串口 | 未测试 | 本次明确限定为无硬件 dry-run |

因此，当前可以确认的是：

1. Pi 上的 ROS 2 工程已经能够原生构建和运行。
2. PowerShell 可以通过 SSH 远程操作 Pi。
3. 通过 SSH 终端运行键盘节点时，Pi 内部的 ROS 2 高层控制链路能够完成
   `键盘输入 -> /cmd_vel -> safety_gate -> 四轮运动学 -> wheel_setpoints`。
4. 本次结果不能证明 Windows 上的 ROS 2 节点已经通过局域网 DDS 与 Pi 通信。

## 2. 本次工作的范围与边界

### 2.1 已执行范围

- 检查 Windows、Pi、网络和本地 Git 工作区状态。
- 安装 Windows Docker Desktop，但没有继续安装或启用 WSL。
- 使用当前本地未提交源码制作可追踪的部署包。
- 通过 SSH/SFTP 将源码部署到 Pi 的版本化目录。
- 修复 Pi 原生构建环境和 Ubuntu 软件源问题。
- 在 Pi 上执行依赖检查、构建、单元测试和 dry-run 集成测试。
- 修复部署过程中暴露的键盘终端和节点关闭问题。
- 执行 SSH 键盘控制到四轮目标的完整无硬件测试。

### 2.2 未执行范围

- 没有在 Pi 上安装或运行 Docker。
- 没有使用 `serial_echo` 或 `real_serial`。
- 没有打开任何 STM32 通信设备；最新方案已改为 USB 虚拟串口 `/dev/mars-rover-stm32`。
- 没有连接 STM32、电机驱动器或电机。
- 没有调用真实硬件 arm 服务。
- 没有配置 systemd 自动启动。
- 没有提交 Git、推送 GitHub或同步远程仓库。
- 没有完成 Windows ROS 2 到 Pi 的真实跨主机 DDS 测试。

## 3. 初始环境检查

### 3.1 Windows 电脑

检查到的环境：

- Windows 11 家庭中文版，64 位。
- CPU 虚拟化和 SLAT 已启用。
- 初始没有 Docker、原生 ROS 2、colcon 或可用的 WSL Linux 发行版。
- Windows OpenSSH、SCP 和 tar 可用。
- `mars-rover-pi.local` 能解析到 `192.168.137.171`。
- 当前网络配置为 Public，这对后续 DDS 防火墙配置不理想。

本地源码状态：

- Git 基准提交：`70b00f5eaa4ef1aba962f88394f2f29842a1a14b`。
- `mars_rover_ws` 包含未提交修改和新增文件。
- GitHub 上的版本不包含全部本地最新改动，因此本次没有从 GitHub clone 到 Pi。
- 部署源明确选择当前 `D:\rover\mars_rover_ws` 工作树。

### 3.2 Raspberry Pi

Pi 初始状态：

- 主机名：`mars-rover-pi`。
- 系统：Ubuntu 24.04.4 LTS。
- 架构：arm64/aarch64。
- ROS 2：Jazzy，安装在 `/opt/ros/jazzy`。
- 内存约 3.7 GiB。
- 根分区约 29 GiB，初始可用约 25 GiB。
- Wi-Fi 地址：`192.168.137.171/24`。
- Git、Python 3.12 和 colcon 已安装。
- 初始没有 `/home/rover/rover` 项目目录。
- 用户属于 `dialout` 组。

历史检查中发现但本次未处理的 GPIO UART 状态：

- `/boot/firmware/config.txt` 已设置 `enable_uart=1`。
- Linux 启动参数仍包含 `console=serial0,115200`。
- 串口 getty 仍占用 UART。
- `/dev/serial0` 当时不能使用。该接口后来已被 USB 虚拟串口方案取代，不再作为整改目标。

该问题不影响 dry-run，但必须在 Pi 到 STM32 联调前处理。

## 4. Windows Docker 与 WSL 处理记录

### 4.1 Docker Desktop 安装

通过 winget 安装了：

```text
Docker Desktop 4.80.0
```

安装程序选择了 WSL2 Linux 容器后端。Docker CLI 安装成功，但 daemon 无法启动，
原因是 Windows 尚未安装 WSL。

### 4.2 WSL 安装被用户取消

曾启动 `wsl --install --no-distribution`，随后用户明确要求停止需要额外占用
C 盘的 WSL 方案。

采取的处理：

1. 终止当前安装等待任务。
2. 定位并终止提升权限的 PowerShell 和 WSL 子进程。
3. 再次执行 `wsl --status`，系统仍提示 WSL 未安装。
4. 停止全部 Docker Desktop 后台进程。
5. 不再配置 host networking、防火墙或 Windows 容器测试环境。

最终状态：

- 没有创建 WSL Linux 发行版或 WSL 虚拟磁盘。
- Docker Desktop 4.80.0 仍安装在 Windows，但当前未运行且不能用于 Linux 容器。
- 如果不再需要 Docker Desktop，应由用户通过 Windows“已安装的应用”手动卸载。
  本次没有自动卸载，因为卸载会批量删除程序文件。

## 5. 源码打包与版本化部署

### 5.1 打包规则

部署包包含当前 `mars_rover_ws`，并排除：

- `.git`
- `build`
- `install`
- `log`
- `__pycache__`
- `.pytest_cache`
- `*.pyc`

每个部署包同时记录：

- 创建时间。
- 本地源码路径。
- Git HEAD。
- 未提交文件清单。
- 压缩包文件名。
- SHA256。

### 5.2 最终活动版本

最终部署信息：

```text
活动路径：/home/rover/rover/releases/20260702T002051/mars_rover_ws
统一入口：/home/rover/rover/current
部署包：mars_rover_ws_20260702T002051.tar.gz
SHA256：eb6a56312a659a770d9f357c2afcee5da174cd3170478db19aca3109bdc7b451
Git HEAD：70b00f5eaa4ef1aba962f88394f2f29842a1a14b
```

电脑和 Pi 分别计算的 SHA256 完全一致。

Pi 上保留了各次尝试版本，没有批量删除：

| 版本 | 大小 | 说明 |
|---|---:|---|
| `20260701T235016` | 约 1.1 MB | 首次构建失败版本 |
| `20260701T235016-r2` | 约 13 MB | 安装编译器后的成功版本 |
| `20260702T000522` | 约 13 MB | 键盘终端修正版 |
| `20260702T001412` | 约 13 MB | 第一轮关闭修正版 |
| `20260702T001737` | 约 13 MB | rosdep 声明修正版 |
| `20260702T002051` | 约 13 MB | 最终活动版本 |

上传包目录约占 180 KB。旧版本总占用不大，但后续稳定后可由用户选择保留
最终版本和一个回退版本，其余目录由用户手动清理。

## 6. Pi 系统配置与依赖安装

### 6.1 新增软件包

安装了：

```text
python3-rosdep 0.26.0-1
ros-jazzy-teleop-twist-keyboard 2.4.1
build-essential 12.10ubuntu1
bzip2 1.0.8-5.1build0.1
```

`build-essential` 及其编译器相关依赖增加约 57.3 MB 占用。

### 6.2 修复 Ubuntu 软件源

初始 Ubuntu 软件源只有：

```text
noble
noble-security
```

但 Pi 上的 `libbz2-1.0` 已经是 updates 版本，`bzip2` 只能从旧的 noble 基础源
获得，造成精确版本依赖无法满足。

修复方式：

1. 备份原文件为：

```text
/etc/apt/sources.list.d/ubuntu.sources.pre-rover-20260701T235016
```

2. 将标准 Ubuntu 更新套件加入现有源：

```text
Suites: noble noble-updates
Suites: noble-security
```

3. 执行 `apt-get update` 后，成功安装 `bzip2` 和 `build-essential`。

### 6.3 ROS 环境入口

创建了：

```text
/home/rover/rover/env.sh
```

内容负责：

- 加载 `/opt/ros/jazzy/setup.bash`。
- 加载 `/home/rover/rover/current/install/setup.bash`。
- 设置 `ROS_DOMAIN_ID=42`。
- 设置 `ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET`。

`/home/rover/.bashrc` 已增加一次幂等 source：

```bash
source /home/rover/rover/env.sh
```

没有把 Windows 当前 IP 写入 `ROS_STATIC_PEERS`，避免 DHCP 地址变化后留下错误配置。

## 7. 遇到的问题、原因与处理

### 7.1 Windows 没有可运行的 ROS 2 环境

**现象：** Windows 没有 Docker、WSL、ROS 2 或 colcon。

**影响：** 无法直接从 Windows 运行电脑端 ROS 2 节点。

**处理：** 安装 Docker Desktop，随后因用户取消 WSL 而停止该路线，改用计划中的
SSH 降级测试。

**结论：** SSH 测试能够验证远程操作和 Pi 内部 ROS 2 链路，但不能替代跨主机 DDS。

### 7.2 Windows Python 缺少 pytest

**现象：** `python -m pytest` 报告没有 pytest 模块。

**处理：** 没有继续向 Windows C 盘安装 Python 测试依赖。Windows 只执行语法编译，
完整测试改由 Pi 原生 Jazzy 环境执行。

### 7.3 Pi 缺少 rosdep

**现象：** Pi 执行 `rosdep` 时提示 command not found。

**处理：** 安装并初始化 `python3-rosdep`，执行 `rosdep update`。

### 7.4 rosdep 无法解析 `ament_python`

**现象：** `mars_rover_control` 报告找不到 `ament_python` rosdep 定义。

**原因：** 项目 `package.xml` 多写了 `<buildtool_depend>ament_python</buildtool_depend>`。
Pi 上使用 Jazzy 官方 `ros2 pkg create --build-type ament_python` 生成的模板不包含
该声明。

**处理：** 删除多余 buildtool 声明。最终执行 rosdep 检查时不再需要跳过该错误键。

### 7.5 Pi 不需要统一工作区中的 GUI 依赖

**现象：** rosdep 尝试在 Pi Server 上安装 RViz 和 `joint_state_publisher`。

**原因：** 电脑端和 Pi 端共用一个 bringup 包，包清单同时声明了电脑端 GUI 依赖。

**处理：** Pi 依赖检查明确跳过 `rviz2` 和 `joint_state_publisher`。本次 dry-run 使用
项目自己的 `joint_state_republisher`，不依赖 GUI。

### 7.6 Pi 缺少 C++ 编译器

**现象：** CMake 报告找不到 `CMAKE_CXX_COMPILER`。

**原因：** Ubuntu Server 安装了 ROS 运行环境和 colcon，但没有 `g++`/build-essential。

**处理：** 安装 `build-essential`。

### 7.7 build-essential 因软件源不完整而安装失败

**现象：** `bzip2` 需要旧版 `libbz2-1.0`，而系统准备安装 updates 版本。

**原因：** Pi 缺少标准 `noble-updates` 软件源，造成相关包版本不一致。

**处理：** 备份软件源文件，加入 `noble-updates`，刷新索引后安装成功。

### 7.8 `pc_teleop.launch.py` 不能读取键盘

**现象：** 官方键盘节点通过 ROS launch 启动时抛出：

```text
termios.error: (25, 'Inappropriate ioctl for device')
```

**原因：** ROS 2 launch 默认不给子进程提供可用于 termios 的标准输入终端。

**处理：**

- 新增 `mars_rover_control/keyboard_teleop.py`。
- 当 stdin 不是终端时，从 `/dev/tty` 恢复控制终端。
- 继续调用官方 `teleop_twist_keyboard`，不重写键盘映射逻辑。
- `pc_teleop.launch.py` 改为启动 `keyboard_teleop` 入口。
- 增加两项终端适配单元测试。
- README 明确要求使用 `docker -it`、`docker exec -it` 或 `ssh -t`。

**验证：** 按 `i` 后成功观察到 `/cmd_vel.linear.x=0.02`。

### 7.9 键盘自动测试过早发送按键

**现象：** 键盘节点已经创建，但前两次自动测试没有捕获 `/cmd_vel`。

**原因：** Pi 首次加载 Python ROS 依赖和 DDS 发现需要数秒，测试脚本只根据固定等待
时间发送按键，发送时节点仍在初始化。

**处理：** 读取进程状态，等待键盘进程进入 `S/Sl` 等待输入状态后再发送按键。

**结论：** 这是测试时序问题，不是最终键盘节点故障。

### 7.10 ROS 节点停止时重复 shutdown

**现象：** SIGINT 后出现 `rcl_shutdown already called`，节点退出码为 1。

**原因：** launch 已关闭 rclpy 上下文，节点 `finally` 又无条件调用一次
`rclpy.shutdown()`。

**处理：**

- 捕获 `KeyboardInterrupt` 和 `ExternalShutdownException`。
- 只在 `rclpy.ok()` 为真时调用 `rclpy.shutdown()`。

### 7.11 关闭瞬间定时器仍尝试发布

**现象：** 个别停止时刻出现 `publisher's context is invalid`。

**原因：** 上下文被关闭的同时，定时器回调恰好进入发布操作。

**处理：** 主循环只在上下文仍有效时重新抛出未知异常；上下文已经关闭时，将该异常
视为正常关闭竞态。正常运行期间的异常仍会继续抛出，不会被隐藏。

**最终验证：** SIGINT 后日志中没有 Traceback、RCLError、`process has died` 或残留节点。

## 8. 代码修改记录

本次部署过程中新增或调整了以下内容：

### 8.1 键盘控制

- 新增 `mars_rover_control/keyboard_teleop.py`。
- 新增 `test/test_keyboard_teleop.py`。
- `setup.py` 注册 `keyboard_teleop` console script。
- `pc_teleop.launch.py` 使用新的终端适配入口。
- `mars_rover_control/package.xml` 声明 `teleop_twist_keyboard` 运行依赖。
- README 增加 TTY 使用要求。

### 8.2 节点生命周期

以下节点增加正常外部关闭和关闭竞态处理：

- `drive_mode_manager`
- `safety_gate`
- `four_wheel_kinematics`
- `stm32_bridge`
- `joint_state_republisher`

### 8.3 包清单

- 删除非标准、会导致 rosdep 失败的 `ament_python` buildtool 声明。

上述改动没有改变 ROS topic 名称、消息类型、四轮顺序、串口协议或安全使能策略。

## 9. 测试过程与结果

### 9.1 静态检查

- Python `compileall`：通过。
- `git diff --check`：通过。
- 部署包排除规则：通过。
- 本地与 Pi SHA256：一致。

### 9.2 Pi 依赖检查

最终命令按 Pi 角色跳过两个 GUI 键：

```bash
rosdep check \
  --from-paths src \
  --ignore-src \
  --rosdistro jazzy \
  --skip-keys "rviz2 joint_state_publisher"
```

结果：

```text
All system dependencies have been satisfied
```

### 9.3 构建与单元测试

构建结果：

```text
Summary: 5 packages finished
```

测试结果：

```text
Summary: 51 tests, 0 errors, 0 failures, 0 skipped
```

覆盖的主要逻辑：

- 四轮运动学。
- 单轮/四轮真实输出策略。
- 串口紧凑 JSON + CRC32 编解码。
- 分片、粘包和超长帧处理。
- 安全策略优先级。
- 键盘终端适配。

### 9.4 dry-run 节点检查

成功启动：

```text
/drive_mode_manager
/safety_gate
/four_wheel_kinematics
/stm32_bridge
/joint_state_republisher
/robot_state_publisher
```

启动日志明确显示：

```text
STM32 bridge running in dry_run mode; serial port will not be opened.
```

### 9.5 自动化控制链路测试

最终活动版本结果：

```json
{
  "crab_accepted": true,
  "dry_run_status": true,
  "echo_not_real": true,
  "four_nonzero": true,
  "recovery_nonzero": true,
  "timeout_zero": true,
  "timeout_zero_latency_sec": 0.476,
  "wheel_order": [
    "front_left",
    "front_right",
    "rear_left",
    "rear_right"
  ]
}
```

验证内容：

- dry-run 状态在线。
- `serial_connected=false`。
- CRAB 请求被接受。
- 四个轮组同时产生非零目标。
- 四轮顺序与协议约定一致。
- `/wheel_states` 为目标回显，`feedback_is_real=false`。
- 停止发送命令后约 0.476 秒归零。
- 恢复命令后重新产生非零目标。
- 最终 STOP 后保持零输出。

### 9.6 SSH 键盘到四轮目标测试

测试步骤：

1. Pi 原生启动 dry-run。
2. 通过 SSH 发布 `CRAB`。
3. 通过带 TTY 的 SSH 会话启动 `pc_teleop.launch.py`。
4. 发送 `i`。
5. 监视 `/cmd_vel` 和 `/mars_rover/wheel_setpoints`。
6. 停止键盘输入并验证归零。

最终结果：

```json
{
  "mode": 1,
  "cmd_nonzero": true,
  "wheels": {
    "order": [
      "front_left",
      "front_right",
      "rear_left",
      "rear_right"
    ],
    "velocities": [0.02, 0.02, 0.02, 0.02]
  },
  "zero_after": true
}
```

### 9.7 停止测试

- SIGINT 后所有节点退出。
- 没有残留 rover 进程。
- 日志中没有 Traceback、RCLError、`process has died` 或 ERROR。
- 测试结束后没有 ROS 控制节点运行。
- 没有串口或电机输出。

## 10. 手动复测方案

本方案只复测 SSH 降级链路，不代表跨主机 DDS。

### 10.1 会话一：启动 Pi dry-run

在 PowerShell 中运行：

```powershell
ssh rover@mars-rover-pi.local
```

进入 Pi 后：

```bash
source /home/rover/rover/env.sh
ros2 launch mars_rover_bringup pi_bringup_dry_run.launch.py
```

应看到六个节点启动，并看到串口不会打开的日志。

### 10.2 会话二：设置 CRAB 并启动键盘

再打开一个 PowerShell 窗口：

```powershell
ssh -t rover@mars-rover-pi.local
```

进入 Pi 后：

```bash
source /home/rover/rover/env.sh
ros2 topic pub --once \
  /mars_rover/drive_mode_request \
  std_msgs/msg/String \
  "{data: CRAB}"

ros2 launch mars_rover_bringup pc_teleop.launch.py with_rviz:=false
```

键盘节点完全启动后：

- `i`：前进。
- `k`：停止。
- `Ctrl+C`：退出键盘节点。

### 10.3 会话三：观察四轮目标

第三个 PowerShell/SSH 会话中：

```bash
source /home/rover/rover/env.sh
ros2 topic echo /mars_rover/wheel_setpoints
```

按 `i` 后应看到四个轮组：

- 名称顺序固定。
- `enabled=true`。
- `drive_velocity` 约为 `0.02`。

还可以检查：

```bash
ros2 topic echo /mars_rover/stm32/status
ros2 topic echo /mars_rover/wheel_states
ros2 topic echo /mars_rover/safety_state
```

### 10.4 测试结束

先在键盘窗口按 `k`，再按 `Ctrl+C`。随后发布 STOP：

```bash
ros2 topic pub --once \
  /mars_rover/drive_mode_request \
  std_msgs/msg/String \
  "{data: STOP}"
```

最后在 dry-run 窗口按 `Ctrl+C`。

## 11. 当前不能声称通过的内容

### 11.1 Windows 到 Pi 的 DDS

当前 Windows 没有运行 ROS 2。所有 ROS 2 发布者和订阅者实际都运行在 Pi，
PowerShell 只负责承载 SSH 终端和发送按键。

因此不能声称以下链路已通过：

```text
Windows ROS 2 节点 -> 局域网 DDS -> Pi ROS 2 节点
```

后续要验收该链路，电脑端必须具备真正可运行的 ROS 2 Jazzy 环境。由于用户不希望
使用 WSL，推荐使用原生 Ubuntu，或使用另一台原生 Linux 电脑。

### 11.2 Pi 到 STM32

本次未连接 STM32，因此不能声称以下最新链路已通过：

```text
Pi stm32_bridge -> /dev/mars-rover-stm32 -> USB -> STM32G474RE
```

### 11.3 实体电机

没有执行真实单轮或四轮电机测试，没有验证转向、驱动、急停、故障反馈或 homing。

## 12. 改进意见

### 12.1 优先完成真正的跨主机 DDS 验收

推荐电脑端使用原生 Ubuntu + ROS 2 Jazzy。验收至少包括：

- 双向标准 String topic。
- 电脑发布 `/cmd_vel`，Pi 返回 `/wheel_setpoints`。
- 相同 `ROS_DOMAIN_ID=42`。
- 必要时双方设置 `ROS_STATIC_PEERS`。
- 电脑断网后 Pi 在约 0.5 秒内归零。

在完成该测试前，项目只能标记为“SSH 远程控制验证通过”。

### 12.2 将电脑端和 Pi 端依赖拆分

当前统一 bringup 包同时声明 RViz、键盘和 Pi 节点依赖，导致 Pi 的 rosdep 必须跳过
GUI 包。建议后续把电脑端可选依赖拆到单独包，或使用清晰的可选依赖安装说明。

### 12.3 提交当前本地源码

最终 Pi 部署来自未提交工作树。虽然部署清单和 SHA256 能追踪本次内容，但其他人
不能仅凭 Git commit 复现。

建议在确认本报告和代码后：

1. 审核本地 diff。
2. 提交 keyboard、shutdown、协议和安全策略修改。
3. 推送到团队仓库。
4. 使用提交哈希重新生成正式部署包。

### 12.4 在 STM32 联调前验证 USB 虚拟串口

需要单独完成：

- 连接支持数据传输的 USB 线。
- 验证 `/dev/ttyACM*` 和 `dialout` 权限。
- 创建 `/dev/mars-rover-stm32` udev 稳定别名。
- 验证重新插拔恢复。
- 先做通信固件 ACK/STATUS 测试，再连接驱动器。

### 12.5 保留正式部署与回退机制

当前版本化目录和 `current` 符号链接已经具备基本回退能力。建议：

- 保留最终版本和一个上一个稳定版本。
- 每次部署保存 SHA256、Git commit、测试结果。
- 只有全部测试通过后才更新 `current`。
- 不直接覆盖活动版本源码。

### 12.6 自动化集成测试

本次使用临时 Python 探针验证完整链路。建议将以下测试正式纳入仓库：

- dry-run 六节点 launch test。
- CRAB 四轮非零目标测试。
- 命令超时归零测试。
- 键盘 TTY smoke test。
- SIGINT 干净关闭测试。

### 12.7 systemd 应晚于真实串口联调

当前不建议立即配置自动启动。应先完成：

- UART 可用。
- STM32 ACK/STATUS 可用。
- 单轮硬件测试通过。
- 开机状态确保 `ControlState.armed=false`，禁止自动 arm。

之后再添加 systemd，并确保服务启动不等于电机使能。

### 12.8 Windows 磁盘与 Docker

Docker Desktop 已安装但不可用。如果后续仍不使用 WSL，应手动卸载 Docker Desktop
以回收 C 盘空间。如果未来改用原生 Ubuntu，则无需在 Windows 保留该安装。

## 13. 最终状态

截至本报告完成时：

- Pi 当前活动版本：`20260702T002051`。
- `/home/rover/rover/current` 指向最终版本。
- Pi 原生 ROS 2 Jazzy 构建通过。
- 51 项测试全部通过。
- SSH 键盘控制到四轮目标通过。
- dry-run 超时归零通过。
- 正常关闭通过。
- Pi 上没有 rover 控制进程残留。
- 没有访问串口、STM32或电机。
- Windows Docker Desktop 已停止。
- WSL 未安装。
- 跨主机 DDS 仍待原生 Linux 电脑端环境验收。
