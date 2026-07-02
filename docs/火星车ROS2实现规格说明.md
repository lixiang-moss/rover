# MARS Rover ROS 2 高层控制实施方案与代码交接规格说明

> 本文档面向两个读者：
>
> 1. 项目组中负责 ROS 2 高层控制的软件成员。
> 2. 后续被要求根据本方案编写 ROS 2 代码的人或 AI。
>
> 文档目标不是提供具体代码，而是把系统事实、架构边界、节点职责、话题接口、消息字段、测试路径和未确认风险写清楚，避免后续实现时只依赖口头记忆或聊天上下文。

---

## 0. 文档状态与重要约束

### 0.1 本文档的性质

本文档是 **方案说明 + 实现规格 + 信息对齐文档**。

它应该被后续代码实现方当作“需求输入”使用，而不是当作已经完成的软件设计代码。

后续写代码时，应该优先保持本文定义的：

- 坐标系。
- 单位。
- 话题名称。
- 节点职责。
- 消息字段语义。
- Pi 与 STM32 的职责边界。
- 单轮组测试优先原则。
- 安全超时和急停优先原则。

### 0.2 本文档不包含的内容

本文档 **不写具体 ROS 2 代码、不写 STM32 固件代码、不写电机驱动器 Modbus 寄存器写入代码**。

原因：

- 当前阶段需要先把架构和接口理清楚。
- STM32 和电机驱动器的底层细节依赖实际硬件型号、寄存器手册、接线和驱动器参数。
- 四轮独立转向/独立驱动底盘的高层逻辑需要先通过仿真和单轮测试验证。

### 0.3 必须遵守的项目边界

- 机器人控制方案采用 **Raspberry Pi + STM32**。
- 机器人是 **四轮独立驱动 + 四轮独立转向**。
- 控制端电脑通过 **ROS 2 局域网通信** 控制树莓派。
- 树莓派负责 ROS 2 高层控制和运动学计算。
- STM32 负责实时低层控制和电机驱动器通信。
- 大功率电机不能由 STM32 直接驱动，必须通过电机驱动器。
- 重点是 **ROS 2 手动控制方案**。
- 后续开发必须支持 **只抽取一组车轮进行测试**。

---

## 1. 信息来源与已抽取事实

这一章是为了给后续 AI 或开发者对齐上下文。不要省略。

### 1.1 已阅读的本地文件

以下文件已经被读取并用于制定本方案：

1. `D:\Document\CESENDLESS\MWRS\2026SoSe_MWRS_2-1\2026SoSe_MWRS_2_1_Concept_Documentation.pdf`
2. `D:\Document\CESENDLESS\MWRS\2026SoSe_MWRS_2-1\2026SoSe_MWRS_2_1.pdf`
3. `D:\Document\CESENDLESS\MWRS\2026SoSe_MWRS_2-1\02_Documentation\01_given_Resources\Documentation MWRS rover-20260427\final_documentation_motor_control.pdf`
4. `D:\Document\CESENDLESS\MWRS\2026SoSe_MWRS_2-1\02_Documentation\03_Created_Diagramms\01_Hardware\02_Electrical\2026SoSe_MWRS_2-1_EPlan.xlsx`

### 1.2 从 2026 概念文档中抽取到的信息

项目目标：

- 继续开发 TU Berlin MARS Rover。
- 机械结构和底盘来自前期工作。
- 当前任务是补齐 Motor Control Unit / 控制系统。
- 需要通过 ROS 2 实现不同驱动模式和运动学。
- 至少需要一个 Drive Mode，多个 Drive Modes 是 bonus。

架构选择：

- 2026 概念文档比较了多个方案：
  - 继续使用 Raspberry Pi + STM32。
  - Raspberry Pi + 2 个 STM32。
  - Arduino Uno Q。
  - Raspberry Pi + Arduino Uno Q。
- 文档中的结论倾向：**最佳方案是使用已有的 Raspberry Pi + STM32**。
- 该方案延续上一届的高层/低层分离：
  - High Level Controller：Raspberry Pi / ROS 2。
  - Low Level Controller：STM32。

从前期工作学到的问题：

- 前一届采用非 ROS 2 的上层控制入口，并通过 Raspberry Pi + STM32 分层控制。
- 发现过一个重要问题：文档中 BLD305 与 BLD405 的型号存在不一致；当前已由用户确认实际 BLDC 驱动器为 **BLD-305S**。
- 8 个电机和步进驱动板是既定硬件。
- BLD-305S 是否已经在当前实物上稳定驱动 57BL04，仍需由 STM32 / 硬件负责人实测确认。

### 1.3 从上一届 final_documentation_motor_control.pdf 中抽取到的信息

底盘结构：

- 四个自定义驱动单元安装在铝型材车架上。
- 每个驱动单元包含：
  - 一个转向电机。
  - 一个驱动电机。
  - 对应减速器。
  - 对应电机驱动器。
- 机器人目标是支持全向/多模式运动。

已有硬件表：

| 类别 | 型号 / 参数 | 用途 |
|---|---|---|
| 转向电机 | NEMA 23，两相，1.8° 步距角 | 控制每个车轮的转向角 |
| 转向减速器 | NMRVS30，蜗轮蜗杆，30:1 | 转向减速和增矩 |
| 转向驱动器 | MKS SERVO57D | 数字步进驱动器 |
| 驱动电机 | 57BL04，三相 BLDC，69 W，3000 rpm | 车轮驱动 |
| 驱动减速器 | EG23-G20-D8 | 与 BLDC 电机配套 |
| BLDC 驱动器 | BLD-305S，Modbus interface | BLDC 电机控制 |
| 电池 | LiTime LiFePO4，24 V，25 Ah，50 A discharge | 电机电源 |

上一届选择的控制架构：

- Raspberry Pi 4：ROS 2 高层导航和中间控制。
- STM32G474RE（工程目标器件 STM32G474RET6）：低层实时电机控制。
- STM32 使用 STM32CubeIDE + HAL 开发。
- STM32 管理两条独立 RS-485 总线。

当前通信架构：

| 接口 | 连接 | 功能 | 备注 |
|---|---|---|---|
| USB 虚拟串口 | Raspberry Pi USB Host ↔ STM32 开发板 USB | `/dev/mars-rover-stm32`，紧凑 JSON + CRC32 | CDC ACM/VCP；原始设备通常为 `/dev/ttyACM0` |
| USART1 + RS-485 | STM32 ↔ MKS SERVO57D，ID 1-4 | 转向电机 Modbus RTU 控制 | PC4/PC5，参数按实物确认 |
| USART3 + RS-485 | STM32 ↔ BLD-305S，ID 1-4 | 行走电机 Modbus RTU 控制 | PB10/PB11，BLD-305S 要求 115200 bps、8N1 |
| Shared GND | 所有电子设备 | 通信参考地 | 星形接地更稳妥 |
| 24 V Power Bus | 电池 → 电机驱动器 | 电机功率供电 | 急停切断驱动器电源 |
| 5 V DC Bus | DC-DC → Pi / STM32 | 逻辑电源 | 与电机供电隔离 |

上一届已经测试过的内容：

- 只测试过一个步进电机和一个 BLDC/DC 电机。
- MKS SERVO57D ID 1 通过 UART2 + RS-485 + MAX485 测试。
- 旧资料中记录 BLD-405S ID 5 通过 UART3 + RS-485 + MAX485 测试；当前实际型号已确认为 BLD-305S，需要按 BLD-305S 重新验证寄存器和通信参数。
- 从开发电脑或 Raspberry Pi 通过 UART 向 STM32 发高层命令。
- STM32 将高层命令转换为 Modbus register writes。
- run/stop、speed、direction 命令被验证过。
- 没有完成四轮完整集成。
- 没有完成多电机同步、负载下测试、整体运动学验证。
- 没有完成连续反馈轮询和 ROS 2 完整反馈集成。

上一届运动学模式：

- Drive mode 1：Holonomic / 所有车轮同向，可平移。
- Drive mode 2：Spin-in-place / 原地旋转。

上一届几何参数：

- 轴距 `L = 706 mm`。
- 轮距 `W = 288 mm`。

注意：这两个尺寸来自上一届文档，必须由机械组按当前实物确认。

### 1.4 从电气图表 xlsx 中抽取到的信息

`2026SoSe_MWRS_2-1_EPlan.xlsx` 中工作表包含：

- `01_Diagramm`
- `02_Functional_Blocks`

可抽取文本包括：

- `Steppermotor:`
- `Steppermotor Driver`
- `Brushless Direct Current Motor (BLDC-Motor)`
- `BLDC - Driver`

这与 PDF 中“每个轮组一个步进转向电机 + 一个 BLDC 驱动电机”的系统事实一致。

### 1.5 在线官方资料对齐

ROS 2 相关事实：

- ROS 2 通过 DDS 自动发现同一 ROS domain 内的节点。
- `ROS_DOMAIN_ID` 相同的节点可以在网络中互相发现和通信。
- ROS 2 Jazzy 支持 Ubuntu 24.04 的 amd64 和 arm64 deb 包。
- ROS 2 Humble 支持 Ubuntu 22.04 的 amd64 和 arm64 deb 包。
- Raspberry Pi 上推荐使用 64-bit Ubuntu 或 64-bit Raspberry Pi OS + Docker 来获得更好 ROS 2 支持。
- `teleop_twist_keyboard` 把键盘输入发布为 `geometry_msgs/msg/Twist`。

参考链接见文末。

---

## 2. 总体系统目标

### 2.1 当前版本目标

当前版本打通以下完整手动控制链路：

```text
控制端电脑
→ ROS 2 局域网话题
→ Raspberry Pi 高层控制节点
→ 四轮目标转向角和驱动速度
→ Pi 到 STM32 串口协议
→ STM32 解析
→ 单轮组测试或四轮目标输出
```

当前版本必须同时完成：

- 电脑和 Pi 的 ROS 2 局域网通信。
- `/cmd_vel` 控制命令发布和接收。
- 驱动模式选择。
- 四轮独立转向/独立驱动运动学解算。
- 每个轮子的目标转向角和目标驱动速度输出。
- Pi 与 STM32 的串口协议设计。
- `RAW_WHEEL_TEST` 单轮测试和 STOP/CRAB/SPIN_IN_PLACE 四轮软件输出。
- dry-run、serial_echo、real single wheel 和 real full vehicle 启动入口。
- 超时停车、软件急停、速度限制、STM32 fault/estop/timeout 联锁。
- 发布标准 `/joint_states`。
- 发布 `/wheel_states`，并明确当前内容是目标值回显。
- 可选 RViz 可视化。

### 2.2 实体测试边界

本次正式实体硬件验收只覆盖 `front_left` 单轮组。代码仍保留四轮输出能力。单轮、四轮悬空、低速落地是硬件风险递增的测试顺序，不是软件功能分期。

完成单轮验收后，实体硬件可以继续扩展：

- 更完整的四轮悬空联调。
- 更完整的四轮低速地面测试。
- 逐个增加 ID 2-4，并分别记录方向、零位、反馈和故障。
- 全部轮组单独通过后再执行四轮悬空和低速地面测试。

---

## 3. 控制职责划分

### 3.1 控制端电脑职责

控制端电脑负责：

- 运行键盘控制。
- 发布 `/cmd_vel`。
- 需要切换模式时发布 `/mars_rover/drive_mode_request`。
- 需要软件急停时发布 `/mars_rover/emergency_stop`。
- 可选运行 RViz 调试模型。
- 录制 rosbag。
- 不直接与 STM32 通信。
- 不直接控制电机驱动器。

### 3.2 Raspberry Pi 职责

Raspberry Pi 是 ROS 2 高层控制核心，负责：

- 运行 ROS 2 节点。
- 通过局域网接收控制端电脑的 ROS 2 话题。
- 管理驱动模式。
- 对 `/cmd_vel` 做限速、限加速度、超时检查。
- 根据机器人几何参数计算四个轮子的目标转向角和驱动速度。
- 执行转向角限制和反向优化。
- 把轮组目标命令通过串口发送给 STM32。
- 接收 STM32 状态并发布为 ROS 2 话题。
- 发布 `/joint_states` 供 RViz 和 robot_state_publisher 使用。
- 维护软件层安全状态。

Raspberry Pi 不负责：

- 直接输出 PWM 驱动大电机。
- 直接写电机驱动器 Modbus 寄存器。
- 做微秒级实时控制。
- 承担电机电流闭环。

### 3.3 STM32 职责

STM32 是低层实时控制器，负责：

- 接收 Pi 通过 USB 虚拟串口发送的轮组目标命令。
- 校验数据帧。
- 解析 4 个转向角和 4 个驱动速度。
- 通过 USART1 + RS-485 收发器控制 MKS SERVO57D 转向驱动器。
- 通过 USART3 + RS-485 控制 BLD-305S。
- 管理 Modbus RTU 通信。
- 执行低层安全超时。
- 在 Pi 通信中断时停止电机。
- 返回驱动器在线状态、故障状态和可用反馈。

STM32 不建议负责：

- ROS 2 话题通信。
- 复杂四轮运动学。
- 高层模式决策。
- 图形界面。

### 3.4 电机驱动器职责

电机驱动器负责：

- 承受 24 V 电源和电机电流。
- 实际驱动电机线圈或 BLDC 三相输出。
- 执行速度、方向、位置或启停命令。
- 提供故障码、状态寄存器、实际速度/位置反馈，如果驱动器支持。

STM32 只是命令发送者，不是功率驱动器。

---

## 4. 推荐软硬件基础配置

### 4.1 ROS 2 发行版建议

二选一，不要混用：

| 方案 | 系统 | ROS 2 | 适用情况 |
|---|---|---|---|
| 保守课程方案 | Ubuntu 22.04 64-bit | Humble | 如果课程资料、队友环境、上一届代码大量基于 Humble |
| 新装长期方案 | Ubuntu 24.04 64-bit | Jazzy | 如果当前从零搭建，希望较新且长期支持 |

建议你们全组统一一种版本。控制端电脑和 Pi 使用同一 ROS 2 发行版。

### 4.2 Raspberry Pi 初始准备

Pi 需要准备：

- 64-bit Ubuntu。
- ROS 2。
- `colcon`。
- `rosdep`。
- `geometry_msgs`。
- `sensor_msgs`。
- `std_msgs`。
- `diagnostic_msgs`。
- `nav_msgs`。
- `tf2_ros`。
- `robot_state_publisher`。
- 串口访问权限。
- 固定 IP 或 DHCP 绑定。

Pi 初期启动后应该能完成：

- `ros2 topic list`。
- 与控制端电脑互相发现 ROS 2 节点。
- 订阅电脑发布的 `/cmd_vel`。
- 打开连接 STM32 的串口设备。
- 打印将要发送给 STM32 的轮组命令。

### 4.3 控制端电脑初始准备

电脑需要准备：

- 在 Ubuntu 26 宿主机的 Ubuntu 24.04 Docker 镜像内运行 ROS 2 Jazzy。
- `teleop_twist_keyboard`。
- 可选 RViz。
- 设置与 Pi 相同的 `ROS_DOMAIN_ID`。
- 能 ping 通 Pi。

### 4.4 STM32 初始准备

STM32 需要准备：

- STM32CubeIDE 工程。
- USB CDC ACM 或开发板 ST-LINK VCP，用于 Pi ↔ STM32；具体实现必须在固件冻结前确认。
- USART1，用于转向驱动器 RS-485 总线。
- USART3，用于 BLDC 驱动器 RS-485 总线。
- 两个 MAX485 或同类 RS-485 收发器。
- Modbus RTU 主站逻辑。
- 命令解析和状态回传。
- 通信超时停车。
- 低层驱动器错误处理。

---

## 5. 局域网 ROS 2 通信架构

### 5.1 基本通信方式

ROS 2 使用 DDS 自动发现节点。同一局域网内，电脑和 Pi 满足以下条件时，ROS 2 节点应能互相发现：

- 同一网络。
- 同一 ROS 2 发行版。
- 相同 `ROS_DOMAIN_ID`。
- 防火墙未阻断 DDS 通信。
- 多网卡情况下没有错误走到其他网卡。

### 5.2 最小通信链路

```text
控制端电脑:
  teleop_twist_keyboard 发布 /cmd_vel
  必要时发布 /mars_rover/drive_mode_request 和 /mars_rover/emergency_stop

局域网:
  ROS 2 DDS 自动发现和传输话题

Raspberry Pi:
  接收 /cmd_vel 和模式/急停话题
  生成 /mars_rover/wheel_setpoints
  通过串口发给 STM32
```

### 5.3 不建议继续使用 HTTP 作为主控制链路

上一届使用 HTTP GET 控制方式，这适合快速演示，但不适合作为当前 ROS 2 主架构。

原因：

- HTTP GET 不适合高频连续控制。
- 状态反馈不自然。
- 与 ROS 2 生态割裂。
- 后续接入手柄、RViz 或 rosbag 时会绕路。

如果保留网页或手机控制界面，建议它只作为输入端，最终仍发布 ROS 2 话题。

---

## 6. 坐标系、单位和命名规范

### 6.1 机器人坐标系

采用 ROS 常用坐标习惯：

- `base_link` 原点：机器人几何中心。
- `x` 轴：车头方向，向前为正。
- `y` 轴：机器人左侧为正。
- `z` 轴：向上为正。
- 逆时针绕 `z` 轴旋转为正 `angular.z`。

### 6.2 四个轮组命名

| 缩写 | 名称 | 位置 |
|---|---|---|
| `fl` | front_left | 前左 |
| `fr` | front_right | 前右 |
| `rl` | rear_left | 后左 |
| `rr` | rear_right | 后右 |

### 6.3 关节命名

建议 URDF、`/joint_states` 和内部逻辑统一使用：

| 轮组 | 转向关节 | 驱动关节 |
|---|---|---|
| FL | `front_left_steering_joint` | `front_left_drive_joint` |
| FR | `front_right_steering_joint` | `front_right_drive_joint` |
| RL | `rear_left_steering_joint` | `rear_left_drive_joint` |
| RR | `rear_right_steering_joint` | `rear_right_drive_joint` |

### 6.4 单位规范

| 物理量 | 单位 |
|---|---|
| 线速度 | `m/s` |
| 角速度 | `rad/s` |
| 转向角 | `rad` |
| 车轮驱动角速度 | `rad/s` |
| 长度 | `m` |
| 时间 | `s` 或 `ms`，字段名必须明确 |
| 电压 | `V` |
| 电流 | `A` |

不要在 ROS 2 高层使用角度制作为内部单位。显示给人看时可以转换为度。

### 6.5 机器人几何初始参数

上一届文档给出：

- 轴距 `L = 706 mm = 0.706 m`。
- 轮距 `W = 288 mm = 0.288 m`。

这些只能作为初始值。代码参数必须可配置，不能写死。

后续必须由机械组确认：

- 当前实物轴距。
- 当前实物轮距。
- 车轮半径。
- 转向轴到轮胎接地点的偏置。
- 每个轮子的零位方向。

---

## 7. 驱动模式定义

### 7.1 模式总表

| mode id | 名称 | 必须支持 | 说明 |
|---|---|---|---|
| `0` | `STOP` | 是 | 速度为 0，禁止驱动输出或保持安全状态 |
| `1` | `CRAB` / `HOLONOMIC_TRANSLATION` | 是 | 四轮同向，支持前后、横移、斜向平移 |
| `2` | `SPIN_IN_PLACE` | 是 | 四轮指向绕中心旋转的切线方向，原地转向 |
| `3` | `RAW_WHEEL_TEST` | 是 | 单轮/单轮组调试，不用于正常驾驶 |

### 7.2 STOP 模式

行为：

- 所有驱动速度目标为 0。
- 转向角可以保持当前位置，也可以回到默认角度。
- 初期建议保持当前位置，避免急停时转向电机额外动作。
- 软件急停、命令超时、通信故障都应进入该模式。

### 7.3 CRAB / HOLONOMIC_TRANSLATION 模式

行为：

- 所有车轮转向角基本相同。
- 如果只给 `linear.x`，车轮朝前，机器人前进/后退。
- 如果只给 `linear.y`，车轮朝左/右，机器人横移。
- 如果同时给 `linear.x` 和 `linear.y`，车轮朝合成方向，机器人斜向移动。
- 该模式通常不处理 `angular.z`，或者只在后续扩展为通用 swerve 模式。

适合：

- 作物行之间平移。
- 狭窄空间横向调整。
- 单轮和低速手动调试。

### 7.4 SPIN_IN_PLACE 模式

行为：

- 机器人绕 `base_link` 原地旋转。
- 每个轮子的速度方向应为该轮位置绕中心旋转的切线方向。
- 轮速大小与该轮到中心距离和 `angular.z` 成正比。
- 如果 `angular.z = 0`，所有驱动速度为 0。

适合：

- 原地调头。
- 检查四轮转向方向是否正确。

### 7.5 RAW_WHEEL_TEST 模式

这是测试模式，不是驾驶模式。

行为：

- 只启用 `active_test_wheel` 参数指定的轮组。
- 可直接给某一轮组目标转向角和驱动速度。
- 其他未启用轮组强制速度为 0。
- 用于单轮、单轮组、悬空测试。

该模式和四轮真实手动控制并不冲突；它只是提供更细粒度的硬件测试入口。

---

## 8. 四轮运动学高层逻辑

### 8.1 通用思路

对于每个轮子，目标速度向量可以理解为：

```text
轮子接地点速度 = 机器人平移速度 + 机器人绕中心旋转在该轮位置产生的速度
```

设：

- 机器人期望速度为 `(vx, vy, wz)`。
- 某轮位置为 `(x_i, y_i)`。

则该轮目标速度方向由两部分组成：

- 平移分量：`(vx, vy)`。
- 旋转分量：绕中心旋转时，该点的切向速度。

最终：

- 目标转向角 = 该轮速度向量方向。
- ROS 2 目标驱动速度 = 该轮速度向量的有符号大小，单位保持 `m/s`；只有 `/joint_states` 显示和 STM32 底层换算需要除以轮半径。

本文不写具体代码，但后续实现必须使用以上物理含义。

### 8.2 转向角反向优化

四轮独立转向系统必须避免车轮为了达到目标角度而大幅旋转。

例如：

- 当前角度为 `10°`。
- 目标速度方向要求 `190°`。
- 与其让转向电机转到 `190°`，更好的方式是：
  - 转向目标设为 `10°` 附近的等效方向。
  - 驱动速度取反。

原则：

- 选择离当前转向角最近的等效角度。
- 如果角度差超过 90°，可以把目标角加/减 180°，同时驱动速度取反。
- 必须限制最终转向角在机械允许范围内。

这点非常关键，因为上一届文档提到转向角不应无限旋转，否则线缆可能被扭坏。

### 8.3 转向角限制

初始建议限制：

- 当前高层硬限制：`[-1.5708, +1.5708] rad`；最终值必须按机械实测确认。
- 实际机械限制必须由机械组确认。

如果未来安装滑环，才可以考虑无限旋转。但目前不要假设有滑环。

### 8.4 速度限制

需要参数化：

- 最大机器人线速度。
- 最大机器人角速度。
- 最大车轮驱动角速度。
- 最大驱动加速度。
- 最大转向角速度。
- 最大转向加速度。

参数初值保持保守，地面测试必须低速。

---

## 9. ROS 2 包与节点建议

### 9.1 推荐包划分

后续代码实现可按如下包划分：

| 包名 | 用途 |
|---|---|
| `mars_rover_description` | URDF / xacro / robot_state_publisher 相关 |
| `mars_rover_interfaces` | 自定义 msg / srv / action |
| `mars_rover_control` | 高层控制、运动学、限幅、安全 |
| `mars_rover_bridge` | Pi ↔ STM32 串口桥 |
| `mars_rover_bringup` | launch、参数文件、整机启动 |
| `mars_rover_tests` | 集成测试、仿真测试、单轮测试脚本 |

如果课程时间紧，可以先合并为更少的包，但接口包 `mars_rover_interfaces` 建议单独保留。

### 9.2 节点总表

| 节点 | 运行位置 | 功能 |
|---|---|---|
| `teleop_twist_keyboard` | 控制端电脑 | 键盘发布 `/cmd_vel` |
| `drive_mode_manager` | Pi | 接收模式字符串请求并发布当前 DriveMode |
| `safety_gate` | Pi | 命令超时、限速、软件急停和 STM32 状态联锁 |
| `four_wheel_kinematics` | Pi | 按当前模式计算并限幅四轮目标 |
| `stm32_bridge` | Pi | 输出策略检查、紧凑协议收发和目标值回显 |
| `joint_state_republisher` | Pi | 把 WheelStateArray 转成标准 `/joint_states` |
| `robot_state_publisher` | Pi | 根据 URDF 和 `/joint_states` 发布 TF |
| `rviz2` | 控制端电脑，可选 | 显示机器人模型和目标值回显 |

### 9.3 节点边界

上述节点是当前代码的实际结构。安全检查、模式管理、运动学和硬件桥分别测试，可以清楚定位哪个环节阻止了命令。

---

## 10. ROS 2 话题规格

### 10.1 主控制话题

| 话题 | 消息类型 | 发布者 | 订阅者 | 说明 |
|---|---|---|---|---|
| `/cmd_vel` | `geometry_msgs/msg/Twist` | 控制端 | `safety_gate` | 机器人期望速度 |
| `/mars_rover/drive_mode_request` | `std_msgs/msg/String` | 控制端/命令行 | `drive_mode_manager` | STOP、CRAB、SPIN_IN_PLACE、RAW_WHEEL_TEST |
| `/mars_rover/emergency_stop` | `std_msgs/msg/Bool` | 控制端/命令行 | `safety_gate`、`stm32_bridge` | 软件急停状态 |

### 10.2 中间控制话题

| 话题 | 消息类型 | 发布者 | 订阅者 | 说明 |
|---|---|---|---|---|
| `/mars_rover/safe_cmd_vel` | `geometry_msgs/msg/Twist` | `safety_gate` | `four_wheel_kinematics` | 安全检查后的速度 |
| `/mars_rover/drive_mode` | `mars_rover_msgs/msg/DriveMode` | `drive_mode_manager` | `four_wheel_kinematics` | 当前模式 |
| `/mars_rover/control_state` | `mars_rover_msgs/msg/ControlState` | `safety_gate` | `stm32_bridge`、调试工具 | arm、运动许可和锁存状态 |
| `/mars_rover/wheel_setpoints` | `mars_rover_msgs/msg/WheelSetpointArray` | `four_wheel_kinematics` | `stm32_bridge` | 最终四轮目标 |

### 10.3 状态反馈话题

| 话题 | 消息类型 | 发布者 | 订阅者 | 说明 |
|---|---|---|---|---|
| `/mars_rover/wheel_states` | `mars_rover_msgs/msg/WheelStateArray` | `stm32_bridge` | `joint_state_republisher`、调试工具 | 当前为目标回显 |
| `/mars_rover/stm32/status` | `mars_rover_msgs/msg/Stm32Status` | `stm32_bridge` | `safety_gate`、调试工具 | 在线、故障、急停、超时 |
| `/mars_rover/safety_state` | `std_msgs/msg/String` | `safety_gate` | 调试工具 | 当前安全门原因 |
| `/joint_states` | `sensor_msgs/msg/JointState` | `joint_state_republisher` | robot_state_publisher / RViz | 8 个关节目标状态 |
| `/tf`、`/tf_static` | `tf2_msgs/msg/TFMessage` | `robot_state_publisher` | RViz | 机器人坐标树 |

### 10.4 QoS 建议

| 话题类型 | QoS 建议 |
|---|---|
| 控制命令 | Reliable，Keep Last 1-5 |
| 高频状态 | Best Effort 或 Reliable，视网络稳定性决定 |
| `/joint_states` | 默认即可 |
| `/diagnostics` | Reliable，低频 |
| 静态配置 | 参数，不走高频话题 |

控制命令必须有超时保护，不能因为 Reliable 就假设永远安全。

---

## 11. 自定义消息规格

本章描述字段语义，不提供 `.msg` 代码。后续 AI 写代码时可据此创建接口包。

### 11.1 DriveMode

如果不用 `std_msgs/msg/UInt8`，建议自定义 `DriveMode`。

字段语义：

| 字段 | 类型建议 | 含义 |
|---|---|---|
| `mode` | `uint8` | 当前请求模式 |
| `label` | `string` | 可读名称，可选 |

枚举语义：

| 值 | 名称 |
|---|---|
| `0` | STOP |
| `1` | CRAB |
| `2` | SPIN_IN_PLACE |
| `3` | RAW_WHEEL_TEST |

### 11.2 WheelSetpoint

单个轮组目标。

字段语义：

| 字段 | 类型建议 | 单位 | 含义 |
|---|---|---|---|
| `name` | `string` | - | `front_left`、`front_right`、`rear_left`、`rear_right` |
| `enabled` | `bool` | - | 是否启用该轮组 |
| `steering_angle` | `float64` | rad | 目标转向角 |
| `drive_velocity` | `float64` | m/s | 目标车轮线速度 |
| `steering_velocity_limit` | `float64` | rad/s | 转向速度限制 |
| `drive_acceleration_limit` | `float64` | m/s^2 | 驱动加速度限制 |

### 11.3 WheelSetpointArray

四个轮组目标集合。

字段语义：

| 字段 | 类型建议 | 含义 |
|---|---|---|
| `stamp` | `builtin_interfaces/Time` | 目标生成时间 |
| `sequence_id` | `uint32` | 与 STM32 ACK/STATUS 对齐的命令序号 |
| `mode` | `uint8` | 当前模式 |
| `setpoints` | `WheelSetpoint[4]` | 固定顺序 FL、FR、RL、RR 的四个轮组目标 |

全局真实运动授权由 `safety_gate` 发布的 `ControlState` 控制。操作者通过 `/mars_rover/set_armed` 服务请求 arm；单轮选择仍由 `active_test_wheel` 和每个 setpoint 的 `enabled` 字段表达。

### 11.4 WheelState

单个轮组的真实反馈或目标回显。

字段语义：

| 字段 | 类型建议 | 单位 | 含义 |
|---|---|---|---|
| `name` | `string` | - | 轮组名称 |
| `online` | `bool` | - | 该轮组底层是否在线 |
| `enabled` | `bool` | - | 当前串口帧是否允许该轮执行 |
| `steering_angle` | `float64` | rad | 当前或回显转向角 |
| `drive_velocity` | `float64` | m/s | 当前或回显车轮线速度 |
| `feedback_is_real` | `bool` | - | true 才能视为真实反馈 |
| `fault` | `bool` | - | 轮组故障状态 |
| `fault_code` | `int32` | - | 底层故障码 |

如果驱动器暂时无法反馈实际角度/速度，字段仍保留，但需要用状态标记说明是目标值回显还是实际反馈。

### 11.5 WheelStateArray

字段语义：

| 字段 | 类型建议 | 含义 |
|---|---|---|
| `stamp` | `builtin_interfaces/Time` | 时间戳 |
| `last_command_sequence_id` | `uint32` | 本次回显对应的目标序号 |
| `command_sent` | `bool` | 该目标是否实际写入串口 |
| `output_enabled` | `bool` | 写入时是否允许真实执行 |
| `states` | `WheelState[4]` | 四个轮组状态或回显 |

### 11.6 ControlState

由 `safety_gate` 发布，是 bridge 判断真实输出权限的唯一 ROS 2 状态：

- `state`：SAFE_STOP、ARMED_IDLE、ACTIVE、TRANSITIONING、ESTOP_LATCHED 或 FAULT_LATCHED。
- `armed`、`motion_allowed`。
- `fresh_command_required`。
- `estop_latched`、`fault_latched`。
- `generation` 和人可读 `reason`。

---

## 12. Pi 到 STM32 串口协议规格

### 12.1 通信物理层

- Pi 使用 USB Host 接口连接 STM32 开发板 USB 数据口，不再使用 GPIO14/15。
- Pi 侧通过 udev 稳定别名 `/dev/mars-rover-stm32` 访问设备，原始设备通常为 `/dev/ttyACM0`。
- 115200、8N1、无流控，双方均为 3.3 V TTL。
- 完整帧最大 512 字节，Pi 20 Hz 发送，STM32 约 5 Hz 主动回 STATUS。

### 12.2 Pi 发给 STM32 的命令语义

Pi 应发送“最终轮组目标”，而不是只发送 `/cmd_vel`。

W 帧使用固定键 `v,t=W,q,m,e,s,w`。`w` 的四轮顺序固定为 front_left、front_right、rear_left、rear_right。每个轮组固定为：

```text
[enabled, angle_rad, velocity_mps, steering_limit_radps, acceleration_limit_mps2]
```

线上格式：

```text
<紧凑JSON>*<8位大写十六进制CRC32>\n
```

CRC32 覆盖星号前的原始 UTF-8 JSON 字节。

### 12.3 STM32 回传给 Pi 的状态语义

STM32 回传两种帧：

- ACK：`v,t=A,q,ok,fc`。
- STATUS：`v,t=S,q,on,es,to,fc`。

`q` 为最近接受的命令序号；`on` 为就绪状态；`es` 为急停；`to` 为 STM32 watchdog 超时；`fc` 为故障码。当前 `/wheel_states` 仍是 Pi 侧目标回显，不由该 STATUS 冒充真实反馈。

### 12.4 发送频率

建议：

- Pi -> STM32：固定 20 Hz。
- STM32 -> Pi：每条有效命令回 ACK，另以约 5 Hz 回 STATUS。

### 12.5 安全规则

STM32 必须执行：

- 如果超过 0.5 秒未收到有效命令，所有执行输出停止。
- 如果 CRC 错误，丢弃该帧。
- 如果 `e=0`，所有执行输出停止。
- 如果某轮的 enabled 为 0，该轮组禁止执行。
- 如果收到急停状态，禁止驱动输出。

Pi 必须执行：

- `/cmd_vel` 超时后发布 STOP。
- 模式切换时由 `drive_mode_manager` 先发布 `STOP + transitioning=true`，保持短暂零输出后再进入目标模式；新模式必须等待新的零命令和后续人工输入。
- 限制速度和角速度。
- 对 STM32 状态异常进行报警。

---

## 13. STM32 到电机驱动器的低层说明

### 13.1 总体原则

STM32 不直接给电机供电。STM32 只通过 RS-485 / Modbus RTU 控制电机驱动器。

### 13.2 转向电机链路

```text
STM32
→ USART1
→ MAX485
→ RS-485 总线
→ MKS SERVO57D，ID 1-4
→ NEMA 23 转向电机
```

建议 ID：

| 轮组 | 转向驱动器 ID |
|---|---|
| FL | 1 |
| FR | 2 |
| RL | 3 |
| RR | 4 |

需要 STM32 同学确认：

- MKS SERVO57D 的 Modbus 寄存器表。
- 位置控制模式或速度控制模式如何设置。
- 是否能读取当前位置。
- 上电后是否需要 homing。
- 角度到驱动器内部单位的换算关系。
- NMRVS30 30:1 减速比是否已体现在驱动器参数中。

### 13.3 BLDC 驱动电机链路

```text
STM32
→ USART3
→ MAX485
→ RS-485 总线
→ BLD-305S，ID 1-4
→ 57BL04 BLDC 电机
```

建议 ID：

| 轮组 | BLDC 驱动器 ID |
|---|---|
| FL | 1 |
| FR | 2 |
| RL | 3 |
| RR | 4 |

需要 STM32 同学确认：

- BLD-305S 是否已经确认支持当前 57BL04。
- 速度命令寄存器。
- 方向命令寄存器。
- 使能/停止寄存器。
- 故障码寄存器。
- 速度单位是 RPM、内部单位还是百分比。

### 13.4 电源与急停

上一届文档建议：

- 电机驱动器直接使用 24 V 电池供电。
- Pi 和 STM32 通过 DC-DC 获得 5 V 逻辑电源。
- 急停切断所有电机驱动器的 24 V。
- Pi 和 STM32 保持供电，以便记录状态和安全恢复。

---

## 14. 单轮组测试方案

### 14.1 为什么必须单轮组测试

原因：

- 当前版本尚未完成四轮实体同步和负载验证。
- BLD-305S 虽已确认为实际驱动器，但仍需按当前实物验证寄存器、通信参数和 57BL04 兼容性。
- 四轮独立转向方向和速度符号容易出错。
- 一旦四轮同时误动作，机械和人员风险都较高。

### 14.2 推荐测试对象

优先测试前左轮组：

| 项 | 建议 |
|---|---|
| 轮组 | FL |
| 转向驱动器 | MKS SERVO57D ID 1 |
| 驱动器 | BLD-305S ID 1 |
| ROS wheel name | `front_left` |
| 转向关节 | `front_left_steering_joint` |
| 驱动关节 | `front_left_drive_joint` |
| W 帧轮组 | `w[0]` enabled=1，其余 enabled=0 |

### 14.3 单轮测试顺序

1. 不接电机，只测试 ROS 2 话题。
2. 不接电机，只测试 Pi 串口发帧。
3. 不接电机，只测试 STM32 解析并回 ACK。
4. 只接 MKS SERVO57D 和转向电机，低速转向。
5. 只接 BLDC 驱动器和驱动电机，悬空低速正反转。
6. 接完整 FL 轮组，悬空测试转向 + 驱动。
7. 四轮仍不启用，只确认未启用轮组不动作。

### 14.4 单轮测试验收标准

必须满足：

- `active_test_wheel=front_left` 时，只有 front_left 的 setpoint enabled 为 true。
- 命令超时后 FL 驱动速度变 0。
- 未 arm、ControlState 不新鲜或存在锁存时，W 帧顶层和所有轮组执行标志均为 0。
- 软件急停时电机不转。
- 转向角正负方向与 ROS 坐标定义一致。
- 驱动速度正负方向与车体前进定义一致。
- STM32 能回传至少 ACK、状态、故障标志。

---

## 15. ROS 2 高层实现任务拆分

### 15.1 当前版本必须同时具备的能力

当前代码应同时具备：

1. 完整 ROS 2 workspace 和自定义消息。
2. 独立的模式、安全、运动学、串口桥和 joint state 节点。
3. dry-run、serial_echo、真实单轮和真实四轮软件入口。
4. 紧凑 JSON + CRC32 协议以及 ACK/STATUS 解析。
5. 参数文件、launch 文件和自动测试。

dry-run 模式含义：

- 不打开真实串口。
- 打印将发送给 STM32 的命令。
- 发布模拟 `/wheel_states`。
- 方便没有硬件时测试 ROS 2 架构。

### 15.2 Pi 高层控制链需求

输入：

- `/cmd_vel`
- `/mars_rover/drive_mode_request`
- `/mars_rover/emergency_stop`

输出：

- `/mars_rover/wheel_setpoints`

参数：

- `wheelbase`
- `track_width`
- `wheel_radius`
- `max_drive_velocity`
- `max_steering_angle`
- `steering_velocity_limit`
- `drive_acceleration_limit`
- `active_test_wheel`

行为：

- 未使能时输出 STOP。
- 急停时输出 STOP。
- `/cmd_vel` 超时后输出 STOP。
- 根据当前模式计算四轮目标。
- 对目标角度和速度限幅。
- 支持只启用一个轮组。

### 15.3 `stm32_bridge_node` 需求

输入：

- `/mars_rover/wheel_setpoints`
- `/mars_rover/emergency_stop`

输出：

- `/mars_rover/wheel_states`
- `/mars_rover/stm32/status`

参数：

- `serial_port`
- `baud_rate`
- `bridge_mode`
- `status_timeout_sec`
- `setpoint_timeout_sec`
- `control_state_timeout_sec`
- `hardware_output_mode`
- `active_test_wheel`

行为：

- dry-run 时不打开串口，只打印/发布模拟状态。
- 非 dry-run 时打开串口。
- 每次收到 wheel setpoints 时编码并发送 W 帧。
- 解析 STM32 ACK/STATUS，发布在线、故障、急停和超时状态。
- 发布 `/mars_rover/wheel_states` 目标值回显并明确 `feedback_is_real=false`。
- `/joint_states` 由独立的 `joint_state_republisher` 发布。

### 15.4 `/joint_states` 发布规则

`sensor_msgs/msg/JointState` 中：

`name` 应包含：

- `front_left_steering_joint`
- `front_left_drive_joint`
- `front_right_steering_joint`
- `front_right_drive_joint`
- `rear_left_steering_joint`
- `rear_left_drive_joint`
- `rear_right_steering_joint`
- `rear_right_drive_joint`

`position`：

- 转向关节填转向角。
- 驱动关节如果没有累计位置，初期可填 0 或积分估计。

`velocity`：

- 转向关节可填实际转向角速度，暂时没有则填 0。
- 驱动关节填车轮驱动角速度，使用 `velocity_mps / wheel_radius` 转换为 `rad/s`。

注意：

- 如果只是目标回显而不是真实反馈，必须在文档、日志或诊断中标明。

---

## 16. 当前项目采用的方案

当前项目采用自定义 ROS 2 节点：

- 键盘 teleop 发布 `/cmd_vel`。
- safety gate 做超时、限幅和急停。
- kinematics 节点把 `/cmd_vel` 转成四轮目标。
- `stm32_bridge_node` 把四轮目标通过串口发给 STM32。
- `/joint_states` 用于 RViz 显示。

---

## 17. 可复用开源项目

| 项目 | 用途 | 建议 |
|---|---|---|
| `teleop_twist_keyboard` | 键盘控制，发布 Twist | 当前控制端直接使用 |
| RViz | TF / URDF / JointState 可视化 | 可选调试，不是实体测试前置条件 |

---

## 18. 关键风险与未确认问题

### 18.1 必须确认的硬件问题

1. BLD-305S 是否确认能稳定驱动 57BL04？
2. MKS SERVO57D 是否支持读取绝对/相对位置？
3. 转向电机有没有零位传感器、限位开关或 homing 机制？
4. 四个车轮当前机械零位如何定义？
5. 转向线缆允许的最大旋转范围是多少？
6. 是否有滑环？如果没有，不能允许无限旋转。
7. 车轮半径是多少？
8. 轴距和轮距是否仍为 `0.706 m` 和 `0.288 m`？
9. 急停是否已经切断电机驱动器 24 V？

### 18.2 必须确认的软件问题

1. 全组是否统一使用 ROS 2 Jazzy？
2. Pi 最终使用 Ubuntu 24.04 原生部署，还是后续单独设计 Docker 部署？
3. STM32 同学是否接受 Pi 发送“4 个转向角 + 4 个驱动速度”的协议？
4. STM32 状态帧能返回哪些真实反馈？

### 18.3 最大技术风险

最大风险不是 ROS 2 本身，而是：

- 转向零位不确定。
- 角度方向定义不一致。
- 驱动速度方向定义不一致。
- 一组轮子装反或驱动器方向参数相反。
- 线缆被转向电机扭坏。
- BLD-305S 寄存器、通信参数或能力与旧 BLD-405S 资料不一致。

因此测试顺序上应先单轮组测试，再做四轮架空测试和低速落地测试；这不是代码功能限制。

---

## 19. 当前版本验收矩阵

下面的能力属于同一版本。单轮、四轮悬空和低速落地只是硬件测试顺序，不是代码功能分期。

### 19.1 ROS 2 网络和 dry-run

验收：

- 电脑发布 `/cmd_vel`。
- Pi 接收 `/cmd_vel`。
- Pi 输出 `/mars_rover/wheel_setpoints`。
- dry-run bridge 发布模拟 `/wheel_states` 和 `/joint_states`。

### 19.2 运动学可视化验证

验收：

- CRAB 模式前进、横移、斜移方向正确。
- SPIN 模式四轮方向为切线方向。
- RViz 中 8 个关节状态能显示。

### 19.3 Pi ↔ STM32 串口通信

验收：

- STM32 能接收命令帧。
- STM32 能校验紧凑帧 CRC32。
- STM32 能逐条回 ACK，并约 5 Hz 回 STATUS。
- Pi 能发布 STM32 状态。

### 19.4 单转向电机测试

验收：

- 只启用 FL 转向。
- 能到目标角。
- 超时停止。
- 急停安全。

### 19.5 单驱动电机测试

验收：

- 只启用 FL 驱动。
- 能低速正转、反转、停止。
- 未启用轮组不动作。

### 19.6 单完整轮组测试

验收：

- FL 转向 + 驱动组合正常。
- 目标角和驱动方向一致。
- 角度反向优化不会造成突变。

### 19.7 四轮悬空测试

验收：

- 四个转向电机方向正确。
- 四个驱动电机方向正确。
- 四轮悬空低速运行。
- 任一通信中断都能停车。

---

## 20. 给后续代码编写 AI 的明确要求

如果把本文档交给其他 AI 写 ROS 2 代码，请要求它遵守：

1. ROS 2 代码和 STM32 固件分别实现，并严格按接口合同联调。
2. 同时保留 dry-run、单轮真实测试和四轮软件输出入口。
3. 单轮选择使用 `active_test_wheel` 和每轮 `enabled`，不增加位掩码字段。
4. 所有单位使用 SI 单位，角度用 rad。
5. 所有机器人几何参数写进参数文件，不要硬编码。
6. 必须有 `/cmd_vel` 超时停车。
7. 必须有锁存急停、reset、条件 arm 和 `/mars_rover/control_state` 逻辑。
8. 必须发布 `/joint_states`。
9. STM32 bridge 在没有真实硬件时必须能模拟状态。
10. 文档和日志必须明确“反馈是真实反馈还是目标回显”。
11. 第一版只需要完成高层 ROS 2 手动控制链路。

---

## 21. 参考资料

本节列出制定方案时参考过的在线资料，供后续开发者查阅最新接口。

- [ROS 2 Distributions](https://docs.ros.org/en/jazzy/Releases.html)
- [ROS 2 Jazzy Ubuntu deb packages](https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html)
- [ROS 2 on Raspberry Pi](https://docs.ros.org/en/jazzy/How-To-Guides/Installing-on-Raspberry-Pi.html)
- [ROS 2 Discovery](https://docs.ros.org/en/rolling/Concepts/Basic/About-Discovery.html)
- [teleop_twist_keyboard](https://index.ros.org/p/teleop_twist_keyboard/)

---

## 22. 最后结论

本项目当前最合理的软件实施路线是：

```text
先不用复杂网页控制

先做：
ROS 2 局域网控制
→ Pi 上四轮运动学
→ 标准化 wheel setpoints
→ Pi 到 STM32 串口桥
→ dry-run
→ 单轮组测试
→ 四轮悬空测试
→ 低速地面测试
```

核心接口应稳定为：

```text
/cmd_vel + /drive_mode
→ 四轮运动学
→ 4 个转向角 + 4 个驱动速度
→ STM32
→ 8 个电机驱动器
```

这条路线最符合当前新手背景、项目硬件现状、上一届工作基础和后续可扩展性。
