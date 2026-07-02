# STM32 bridge 状态消息。
# 由 stm32_bridge 发布，供 safety_gate 和调试工具判断底层串口/STM32 是否可用。

# 状态生成时间。
builtin_interfaces/Time stamp
# STM32 是否被认为在线；dry_run 模式固定为 false。
bool online
# 距离上次收到 STM32 回传的时间，单位 s；无回传时可能为 inf。
float64 last_rx_age
# 最近一次 STM32 ACK 的命令序号。
uint32 last_ack_sequence_id
# Pi 最近实际写入串口的命令序号。
uint32 last_sent_sequence_id
# 最近一次 STM32 STATUS 携带的命令序号。
uint32 last_status_sequence_id
# Pi 侧串口是否成功打开。
bool serial_connected
# 是否超过 status_timeout_sec 未收到状态。
bool timeout
# Pi 软件急停或 STM32 上报的硬件急停是否处于激活状态。
bool estop_active
# STM32 是否上报底层故障，或最近一条 ACK 是否拒绝命令。
bool fault
# STM32 协议故障码；0 表示无底层故障。
uint32 fault_code
# 是否存在串口打开或读写错误。
bool serial_error
# 当前 bridge 运行模式：dry_run、serial_echo 或 real_serial。
string bridge_mode
# bridge 是否正在收到新鲜的 ControlState。
bool control_state_connected
# 人可读状态说明。
string message
