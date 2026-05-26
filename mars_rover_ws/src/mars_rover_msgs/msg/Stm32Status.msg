# STM32 bridge 状态消息。
# 由 stm32_bridge 发布，供 safety_gate 和调试工具判断底层串口/STM32 是否可用。

# 状态生成时间。
builtin_interfaces/Time stamp
# STM32 是否被认为在线；dry_run 模式下可为 true。
bool online
# 距离上次收到 STM32 回传的时间，单位 s；无回传时可能为 inf。
float64 last_rx_age
# 最近一次 STM32 ACK 的命令序号。
uint32 last_ack_sequence_id
# Pi 侧串口是否成功打开。
bool serial_connected
# 是否超过 status_timeout_sec 未收到状态。
bool timeout
# 软件急停是否处于激活状态。
bool estop_active
# 是否存在串口打开或读写错误。
bool serial_error
# 人可读状态说明。
string message
