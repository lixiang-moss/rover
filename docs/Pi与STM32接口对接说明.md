# Pi 与 STM32 联调接口合同

> - 接收人：STM32、驱动器和电机负责人
> - 协议版本：`v=1`
> - 本次实体验收：`front_left` 单轮组
> - 完整部署步骤见 `docs/火星车硬件部署与联调操作手册.md`

## 1. 你需要交付的结果

请以当前项目中的 STM32CubeIDE 工程为基线实现以下能力。工程目标器件为 `STM32G474RET6/STM32G474RETx`，CubeMX 工程类型为 custom board。

1. 通过 USB 虚拟串口接收 Pi 的紧凑 JSON + CRC32 帧。
2. 每条有效命令返回 ACK，约 `5 Hz` 主动返回 STATUS。
3. 超过 `0.5 s` 未收到有效命令时停止全部执行输出。
4. 通过 USART1 + RS-485 控制 4 个 MKS SERVO57D。
5. 通过 USART3 + RS-485 控制 4 个 BLD-305S。
6. 把车轮转向角 rad 转换为转向电机轴坐标。
7. 把车轮线速度 m/s 转换为 57BL04 电机 rpm。
8. 上电、复位、通信错误、急停、超时和驱动故障时保持电机停止。
9. 首先完成 `front_left` 的 homing、小角度转向、正反转、停止和故障测试。

本项目不引用、复制或移植上一届 STM32 工程。允许使用 STM32 HAL、CubeIDE 自动生成代码以及驱动器厂商官方协议。

## 2. 已知硬件

| 类别 | 型号/暂定参数 | 当前测试对象 |
|---|---|---|
| STM32 控制器 | STM32G474RE，工程目标器件 STM32G474RET6 | 是 |
| 转向电机 | NEMA 23，资料写作 23HE22-2804S，1.8°、2.8 A/phase | front_left 一台 |
| 转向驱动器 | MKS SERVO57D RS-485 | ID 1 |
| 转向减速器 | NMRVS30，固定 30:1 | 已确认，STM32 单位换算必须使用该值 |
| 行走电机 | 57BL04，24 V、69 W、3000 rpm、4 极 | front_left 一台 |
| 行走驱动器 | BLD-305S | ID 1 |
| 行走减速比 | 暂按 20:1 | 实物复核 |
| 轮半径 | 暂按 0.09 m | 必须实测 |
| 收发器 | 两块 MAX485 或同类模块 | 芯片和逻辑电平必须核对 |

完整扩展时共有 4 个转向电机、4 个行走电机、4 个 SERVO57D 和 4 个 BLD-305S。

## 3. STM32G474RE 外设分配

| 用途 | 外设 | 引脚 | 固定参数 |
|---|---|---|---|
| Pi 正式协议 | USB 虚拟串口 | 开发板 USB 口 | Pi 侧呈现为 CDC ACM/VCP 设备，协议仍为紧凑 JSON + CRC32 |
| 调试日志 | 独立 UART、SWO 或其他独立通道 | 不得与 Pi 正式 USB 虚拟串口混用 | 避免日志污染协议帧 |
| 当前 Pi 协议内部入口 | LPUART1 | PC0 RX / PC1 TX | 当前代码使用；改用 USB 后必须确认 VCP 路由或替换为 USB CDC |
| SERVO57D 总线 | USART1 | PC4 TX / PC5 RX | 当前代码为 115200、偶校验；必须按驱动器实际要求确认 8N1/8E1 |
| BLD-305S 总线 | USART3 | PB10 TX / PB11 RX | 当前代码为 115200、偶校验；现行 BLD-305S 文档要求 8N1，需修正 |
| SERVO57D DE/RE | GPIO | PB0 | 默认低 |
| BLD-305S DE/RE | GPIO | PB1 | 默认低 |

请用 STM32G474RE 数据手册、当前控制板原理图和实际板卡丝印确认接口位置与引脚 5 V 容限。MAX485 的 RO 可能接近 5 V；不能在未核对的情况下接入 STM32 RX。

## 4. Pi 物理连接

全部断电后连接：

| Raspberry Pi 4 | STM32 开发板 |
|---|---|
| USB Host 接口 | 开发板 USB 数据接口 |

使用支持数据传输的 USB 线直接连接，不再连接 Pi GPIO14/15。Pi 侧原始设备通常为 `/dev/ttyACM0`，正式部署通过 udev 创建稳定别名 `/dev/mars-rover-stm32`，避免重新插拔后编号变化。

USB 实现必须在固件冻结前确认：如果使用开发板 ST-LINK VCP，STM32 继续通过与 VCP 相连的 UART 收发；如果使用 MCU 原生 USB，则固件必须实现 USB CDC ACM。两种方式在 Pi 侧都按串口设备使用，但 STM32 内部实现不同。

## 5. 串口帧

### 5.1 固定参数

| 项目 | 值 |
|---|---|
| 速率 | 115200 |
| 格式 | 8N1，无流控 |
| Pi 命令频率 | 20 Hz |
| STATUS 频率 | 约 5 Hz |
| 最大完整帧 | 512 bytes |
| 命令 watchdog | 0.5 s |
| 协议版本 | 1 |

### 5.2 帧格式

```text
<紧凑JSON>*<8位大写十六进制CRC32>\n
```

- CRC32 覆盖 `*` 前的原始 UTF-8 JSON 字节。
- 算法与 Python `zlib.crc32()` 一致。
- CRC 固定 8 位大写十六进制，保留前导零。
- 不先解析/重排 JSON 再计算 CRC。
- 缓冲区达到 512 字节仍未收到换行时，丢弃整帧、停止输出并记录故障。

## 6. Pi 发来的 W 命令

### 6.1 字段

| 键 | 类型 | 含义 |
|---|---|---|
| `v` | integer | 固定为 1 |
| `t` | string | 固定为 `W` |
| `q` | uint32 | 命令序号，按 uint32 回绕 |
| `m` | integer | 0 STOP，1 CRAB，2 SPIN_IN_PLACE，3 RAW_WHEEL_TEST |
| `e` | 0/1 | 全局硬件执行使能 |
| `s` | 0/1 | 软件急停 |
| `w` | 4 个数组 | 四轮目标 |

四轮位置固定：

```text
w[0] = front_left
w[1] = front_right
w[2] = rear_left
w[3] = rear_right
```

每轮固定为：

```text
[enabled, angle_rad, velocity_mps, steering_limit_radps, acceleration_limit_mps2]
```

当前单轮测试示例：

```text
{"e":1,"m":3,"q":42,"s":0,"t":"W","v":1,"w":[[1,0.1,0.08,0.15,0.05],[0,0.0,0.0,0.15,0.05],[0,0.0,0.0,0.15,0.05],[0,0.0,0.0,0.15,0.05]]}*58782C06
```

这是固定测试向量；星号前字节的 CRC32 必须为 `0x58782C06`。

### 6.2 执行条件

只有以下条件全部成立，才能执行：

- CRC、JSON、版本、字段和范围检查通过。
- `e=1`。
- `s=0`。
- 当前轮组 `enabled=1`。
- 没有物理急停、watchdog、驱动故障。
- 转向 homing 已完成。

`e=0`、`s=1` 或任一安全条件失败时，无条件停止。不能让轮组局部 enabled 绕过顶层 e。

## 7. STM32 回 ACK

字段固定为：

```text
{"fc":0,"ok":1,"q":42,"t":"A","v":1}*88B875B3
```

| 字段 | 要求 |
|---|---|
| `q` | 回显本次 W 命令序号 |
| `ok=1,fc=0` | 命令已接受并更新 watchdog |
| `ok=0,fc!=0` | 命令可识别，但字段/范围/前置条件失败 |

CRC 已损坏的帧不能信任 q，不必对它 ACK；记录 1001，并在下一条 STATUS 中上报。

## 8. STM32 主动回 STATUS

字段固定为：

```text
{"es":0,"fc":0,"on":1,"q":42,"t":"S","to":0,"v":1}*F18BB4D1
```

| 字段 | 要求 |
|---|---|
| `q` | 最近接受的 W 序号 |
| `on` | 固件及当前测试需要的设备就绪；单轮阶段只要求 ID 1 |
| `es` | 硬件急停或软件急停激活 |
| `to` | 0.5 s Pi 命令 watchdog 超时 |
| `fc` | 当前最高优先级故障，0 为无故障 |

即使 Pi 暂时没有发 W，也要约 5 Hz 主动发送 STATUS，便于 ROS 2 在允许运动前确认 STM32 在线。

## 9. 故障码

| fc | 含义 |
|---:|---|
| 0 | 无故障 |
| 1001 | CRC32 错误 |
| 1002 | 超长帧或接收缓冲区溢出 |
| 1003 | UTF-8/JSON 解析错误 |
| 1004 | 协议版本、类型或字段错误 |
| 1005 | 数值非有限、越界、轮组数量错误 |
| 2001 | Pi 命令超过 0.5 s |
| 2002 | 硬件急停 |
| 2003 | homing 未完成 |
| 3101-3104 | 转向 ID 1-4 故障 |
| 4101-4104 | 行走 ID 1-4 故障 |

故障优先级：硬件急停 > watchdog > 转向 > 行走 > homing > 协议错误。

## 10. 两条 RS-485 总线

### 10.1 地址

| 轮组 | SERVO57D | BLD-305S |
|---|---:|---:|
| front_left | 1 | 1 |
| front_right | 2 | 2 |
| rear_left | 3 | 3 |
| rear_right | 4 | 4 |

### 10.2 DE/RE 时序

每次请求必须：拉高 DE/RE -> 发送 -> 等待 UART Transmission Complete -> 拉低 DE/RE -> 接收响应。请求超时要在有限时间内返回，不能让主循环阻塞到 Pi watchdog 失效。

总线采用菊花链；120 Ω 只放在物理两端；偏置只保留一组。接入多设备前逐台设置唯一地址。

## 11. SERVO57D 实现要求

单轮阶段使用 ID 1，115200 8N1，启用 Modbus RTU，进入串行闭环/绝对轴位置模式。电流按实际 23HE22-2804S 铭牌，暂按 2.8 A/phase。

设车轮输出目标角为 \(\theta_w\)，减速比 \(G_s=30\)，编码器每电机轴转一圈 \(N_e=16384\)，零位轴坐标 \(C_0\)，方向符号 \(s_s\)：

$$
C_{\mathrm{cmd}}=C_0+\operatorname{round}\left(s_s\frac{\theta_w}{2\pi}G_sN_e\right)
$$

命令必须使用 SERVO57D 协议支持的有符号多圈坐标，不能截断成 16 位单圈值。

原点开关型号尚未冻结。未安装并验证原点开关前：

- STATUS/通信可以联调。
- 可以做驱动器读取测试。
- 不能执行自动 homing。
- 不能接受正式非零转向命令，应返回 `fc=2003`。

## 12. BLD-305S 实现要求

项目原始手册：`Group 3.1 - Final Submission/Data Sheets/BLD-305S_Manual (1).pdf`。

| 寄存器 | 操作 | 含义 |
|---|---|---|
| `0x0056` | 写 0-4000 | 目标电机 rpm |
| `0x0066` | 写 0/1/2/3 | 停止/正转/反转/制动停止 |
| `0x0076` | 写 0 | 清故障 |
| `0x00A6` | 写 1-247 | 设备地址 |
| `0x00F6` | 写 0x07 | 115200 |
| `0x0116` | 写 2，待实物确认 | 57BL04 极对数 |
| `0x0136` | 写 1 | 内部/通信模式 |
| `0x005F` | 读 | 实际电机速度 |
| `0x0066` | 读 | 运行状态 |
| `0x0076` | 读 | 故障码 |
| `0x80FF` | 写 `0x55AA` | 保存配置参数 |

57BL04 项目资料写作 4 极，所以暂按 2 对极，必须核对铭牌或原始数据表。

设轮胎线速度 \(v\)、轮半径 \(r\)、减速比 \(G_d\)、方向符号 \(s_d\)：

$$
n_{\mathrm{motor}}=s_d\frac{60v}{2\pi r}G_d
$$

按 \(r=0.09\,\mathrm{m}\)、\(G_d=20\)，`0.08 m/s` 对应约 `170 rpm`。BLD-305S 手册标注闭环调速范围从约 `150 rpm` 开始，因此不要把 `0.03 m/s` 对应的约 `64 rpm` 当作必然可稳定执行的测试点。

方向切换时先停止，再切换正/反转。每次读出实际速度和 fault，并在 Hall、过流、欠压、过压、堵转等故障时停止。

## 13. 首次联合联调顺序

1. STM32G474RE 控制板只接逻辑电源或 USB，驱动器全部断电。
2. USB 虚拟串口连续接收 W，验证 ACK/STATUS/CRC/watchdog。
3. 转向 RS-485 只接 SERVO57D ID 1，验证读取和配置。
4. 行走 RS-485 只接 BLD-305S ID 1，验证读取和停止命令。
5. 硬件急停、保险、总开关和供电支路通过检查。
6. 安装并验证转向原点开关。
7. 只做 front_left homing 和 \(\pm0.05\,\mathrm{rad}\) 转向。
8. 只做 front_left 约 `170 rpm` 的 1-2 秒正反转。
9. 依次验证软件急停、物理急停、USB 断开和 0.5 s watchdog。
10. 填写验收记录后再讨论 ID 2-4。

## 14. 交付给 Pi 负责人的资料

请提供：

- CubeIDE 工程使用的板卡和引脚表。
- 协议版本和故障码最终表。
- 一条真实 W、A、S 抓包及 CRC 校验结果。
- 20 Hz 命令持续 30 分钟的错误统计。
- 0.5 s watchdog 的示波器/日志时间证据。
- front_left 转向方向、零位、减速比和重复 homing 结果。
- front_left 行走方向、轮半径、减速比、极对数和实际 rpm。
- 两条 RS-485 的地址、终端、偏置和超时配置。
- 每项故障测试的 `fc`、停止行为和恢复条件。

## 15. 联调冻结记录

| 项目 | 最终值 | Pi 负责人 | STM32 负责人 | 日期 |
|---|---|---|---|---|
| USB 串口设备 | `/dev/mars-rover-stm32`，原始设备通常为 `/dev/ttyACM0` |  |  |  |
| 协议版本 | 1 |  |  |  |
| 最大帧长 | 512 bytes |  |  |  |
| Pi 频率 / STATUS 频率 | 20 Hz / 约 5 Hz |  |  |  |
| watchdog | 0.5 s |  |  |  |
| wheel order | FL, FR, RL, RR |  |  |  |
| 轮半径 |  |  |  |  |
| 转向减速比 | 固定 30:1 |  |  |  |
| 行走减速比 | 暂按 20:1，待实物确认 |  |  |  |
| 极对数 |  |  |  |  |
| 原点开关与输入逻辑 |  |  |  |  |
| front_left 方向符号 |  |  |  |  |

## 16. 因本次信息更新必须修改的代码

### 16.1 ROS 2 侧

以下文件的默认串口设备应从 `/dev/serial0` 改为 `/dev/mars-rover-stm32`：

- `mars_rover_bringup/config/stm32_bridge.yaml`
- `mars_rover_control/stm32_bridge.py`
- `pi_bringup_serial_echo.launch.py`
- `pi_bringup_real_single_wheel.launch.py`
- `pi_bringup_real_full_vehicle.launch.py`

`stm32_bridge` 仍使用 pyserial 和现有紧凑 JSON + CRC32 协议，不需要因为改成 USB 而重写 ROS 2 topic 或消息。需要补充 USB 断线后的自动重连：设备消失时发布 offline/serial_error，定时重新打开稳定别名，重新连接后先等待合法 STATUS，不能直接恢复旧运动命令。

ROS 2 侧已经取消动态 `hardware_enable` 参数。W 帧的 `e=1` 现在同时要求：arm 服务成功、`ControlState.motion_allowed=true`、ControlState 新鲜、STM32 STATUS 新鲜且无急停/超时/故障。USB 断线会锁存 fault；恢复后必须 STOP、零命令、reset、重新 arm，Pi 不会自动恢复旧运动。

转向减速比 `30:1` 不进入 ROS 2 运动学。ROS 2 继续发送车轮输出轴目标角 `rad`；减速比只在 STM32 把车轮角转换为转向执行器坐标时使用，避免两层重复乘以 30。

### 16.2 STM32 侧

当前工程型号已经是 STM32G474RE，无需再移植到 F446RE。但当前 Pi 链路仍使用 LPUART1：

- 如果实际 USB 连接使用 ST-LINK VCP，必须确认 VCP 硬件确实连接到当前 LPUART1 PC0/PC1；确认后 `PI_UART` 可以继续使用 LPUART1。
- 如果实际 USB 连接使用 MCU 原生 USB，必须在 CubeMX 中启用 USB Device CDC ACM，使用 CDC 接收回调和环形缓冲区替代 `HAL_UART_Receive(&PI_UART, ...)`，并使用 CDC 发送函数替代 `HAL_UART_Transmit(&PI_UART, ...)`。

无论选择哪种 USB 实现，协议逻辑都必须改为本文冻结的 `v=1`：解析紧凑 W 帧及 CRC32，返回带 CRC32 的 A/S 帧，约 5 Hz 主动发送 STATUS。当前旧版 `payload/type/sequence_id/wheels` JSON 不能与 ROS 2 代码衔接。

转向换算中的减速比固定为 `30.0`。当前代码已有 `STEERING_GEAR_RATIO 30.0f`，但仍需确认它只应用一次，并按 SERVO57D 的实际多圈坐标、机械零位和每轮方向符号完成换算。
