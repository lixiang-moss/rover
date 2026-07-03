# STM32 负责人 USB 通信与协议修改交接说明

> 接收人：STM32、驱动器和电机负责人
> ROS 2 负责人边界：只维护 Pi/ROS 2 侧代码，不修改 STM32 固件
> STM32 工程：`D:\rover\STM32`
> 文档日期：2026-07-03

## 1. 已冻结的信息

| 项目 | 最终要求 |
|---|---|
| STM32 型号 | STM32G474RE，当前工程目标器件 STM32G474RET6/STM32G474RETx |
| Pi 与 STM32 物理连接 | USB 数据线 |
| Pi 设备名 | udev 稳定别名 `/dev/mars-rover-stm32`，原始设备通常为 `/dev/ttyACM0` |
| Pi 与 STM32 协议 | `v=1` 紧凑 JSON + CRC32，协议内容不因 USB 改变 |
| 转向减速器 | NMRVS30，固定 30:1 |
| 转向减速比归属 | 只在 STM32 的转向单位换算中使用，ROS 2 不乘 30 |
| 转向 RS-485 | 当前工程 USART1，PC4/PC5，DE/RE 为 PB0 |
| 行走 RS-485 | 当前工程 USART3，PB10/PB11，DE/RE 为 PB1 |

## 2. 当前 STM32 工程状态

当前工程已经选择 STM32G474RE，型号不需要再改回 F446RE。

但 Pi 通信仍然使用：

```text
PI_UART = LPUART1
RX = PC0
TX = PC1
```

当前工程中没有完成 MCU 原生 USB CDC ACM。现有收发逻辑仍调用 `HAL_UART_Receive()` 和 `HAL_UART_Transmit()`。

因此，STM32 负责人必须先确认 USB 线实际连接哪一个接口：

| USB 方案 | STM32 负责人需要确认的事项 |
|---|---|
| 开发板 ST-LINK VCP | 确认 ST-LINK VCP 是否物理连接到当前 LPUART1 PC0/PC1；如果不是，修改 UART 实例或板级连接 |
| MCU 原生 USB CDC | 在 CubeMX 中启用 USB Device CDC ACM，并把 Pi 协议收发从 UART 改到 CDC 接口 |

不能只因为 Pi 出现 `/dev/ttyACM0` 就假设 STM32 已经收到数据。必须通过固定测试帧和 ACK 验证完整链路。

## 3. 必须修改的 STM32 部分

### 3.1 USB 接收与发送

如果使用 ST-LINK VCP：

1. 确认 VCP 对应的 MCU UART 和引脚。
2. 该 UART 使用 115200、8N1、无流控。
3. 正式协议通道中不得输出调试日志。
4. USB 拔出后，STM32 watchdog 仍必须停止全部执行输出。

如果使用 MCU 原生 USB CDC：

1. 在 `STM32.ioc` 中启用 USB Device CDC ACM。
2. CDC 接收回调只负责把字节放入环形缓冲区，不能在中断/回调中解析 JSON 或阻塞控制。
3. 主循环从缓冲区取数据，按换行符完成切帧。
4. 使用 CDC 发送函数返回 ACK 和 STATUS。
5. 处理 USB 未配置、忙、断开和重新枚举状态。

### 3.2 Pi 协议必须改成当前 `v=1`

当前 `mwrs_control.c` 仍解析旧结构：

```text
payload / type / sequence_id / mode_value / wheels
```

ROS 2 实际发送的是紧凑 W 帧：

```text
{"e":1,"m":3,"q":42,"s":0,"t":"W","v":1,"w":[[1,0.1,0.08,0.15,0.05],[0,0.0,0.0,0.15,0.05],[0,0.0,0.0,0.15,0.05],[0,0.0,0.0,0.15,0.05]]}*58782C06

```

STM32 必须：

1. 以 `\n` 结束一帧，最大完整帧 512 bytes。
2. 按 `*` 分离 JSON 和 8 位大写十六进制 CRC32。
3. CRC32 只覆盖星号前的原始 JSON 字节。
4. CRC 算法与 Python `zlib.crc32()` 一致。
5. 严格验证 `v,t,q,m,e,s,w`，拒绝额外字段、NaN、Inf、错误轮组数量和越界数值。
6. 四轮数组固定顺序为 front_left、front_right、rear_left、rear_right。

### 3.3 ACK 和 STATUS

每条有效 W 命令返回 ACK：

```text
{"fc":0,"ok":1,"q":42,"t":"A","v":1}*88B875B3
```

STM32 还需要约 5 Hz 主动返回 STATUS：

```text
{"es":0,"fc":0,"on":1,"q":42,"t":"S","to":0,"v":1}*F18BB4D1
```

要求：

- `on=1` 只能表示固件和当前测试所需设备已经就绪。
- `q` 是最近接受的命令序号。
- `es` 是软件或硬件急停。
- `to` 是 STM32 命令 watchdog 超时。
- `fc` 是当前最高优先级故障码。
- 不得在没有检查驱动器响应时固定返回 online=true。

### 3.4 Watchdog 和 USB 断线

超过 0.5 s 没有收到合法 W 帧时：

1. 停止全部行走输出。
2. 停止或安全终止正在执行的转向动作。
3. 禁止继续使用最后一条运动命令。
4. STATUS 设置 `to=1`。
5. USB 恢复后保持禁用，直到收到新的合法命令并满足安全条件。

### 3.5 转向减速比 30:1

当前代码已经包含：

```text
STEERING_GEAR_RATIO = 30.0
```

但必须检查换算方式是否符合 SERVO57D 的实际协议：

```text
执行器目标 = 机械零位 + 方向符号 × 车轮目标角 / (2π) × 30 × 执行器每圈坐标
```

要求：

- 30:1 只在 STM32 中应用一次。
- 每个轮组单独保存机械零位和方向符号。
- 使用 SERVO57D 支持的有符号多圈坐标。
- homing 完成前不得接受正式非零转向命令。
- 不能简单假设 200 步 × 16 细分就是 SERVO57D 的实际位置坐标。

### 3.6 两条 RS-485 总线

当前 G474 工程分配为：

| 用途 | UART | 引脚 | DE/RE |
|---|---|---|---|
| MKS SERVO57D | USART1 | PC4 TX / PC5 RX | PB0 |
| BLD-305S | USART3 | PB10 TX / PB11 RX | PB1 |

STM32 负责人需要：

1. 按驱动器实际协议修正 UART 校验位。BLD-305S 当前文档要求 115200、8N1。
2. 使用两条独立总线各自的 ID 1-4。
3. 每次 Modbus 请求后读取并校验响应和 CRC16。
4. 不得只发送写请求就向 Pi 报告成功。
5. 驱动器无响应、CRC 错误或 fault 时停止对应输出并上报故障码。

## 4. STM32 负责人验收顺序

1. 不连接驱动器，只连接 Pi 和 STM32 USB。
2. Pi 能识别 `/dev/mars-rover-stm32`。
3. 固定 W 测试向量通过 CRC32 校验。
4. STM32 返回可被 ROS 2 解析的 ACK。
5. STM32 在没有 W 命令时仍约 5 Hz 返回 STATUS。
6. 暂停 W 超过 0.5 s，STATUS 返回 `to=1`。
7. 拔掉 USB，确认全部执行输出保持停止。
8. USB 恢复后保持禁用，不自动恢复旧命令。
9. 再分别连接 SERVO57D ID 1 和 BLD-305S ID 1。
10. 完成单轮 homing、小角度转向、低速正反转、停止和故障测试。

## 5. 交付给 ROS 2 负责人的内容

STM32 负责人需要提供：

- 最终选择的 USB 方案：ST-LINK VCP 或 MCU 原生 USB CDC。
- USB 对应的 MCU 外设、引脚和控制板接口。
- CubeIDE 工程和可烧录文件。
- 固定 W/A/S 抓包和 CRC32 结果。
- 20 Hz W、逐帧 ACK、约 5 Hz STATUS 的连续测试记录。
- USB 拔出、重新插入和 watchdog 停止测试记录。
- 转向 30:1 换算公式、每轮零位和方向符号。
- 两条 RS-485 的 UART 参数、ID、寄存器和故障读取结果。

ROS 2 负责人不会修改 STM32 工程。若 STM32 侧需要调整协议字段，应先更新双方接口合同并通知 ROS 2 负责人，不能只改单侧代码。
