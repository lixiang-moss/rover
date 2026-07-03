# Pi 侧统一控制状态。
# 由 safety_gate 发布，供 stm32_bridge 和调试工具判断当前是否允许真实运动。

uint8 SAFE_STOP=0
uint8 ARMED_IDLE=1
uint8 ACTIVE=2
uint8 TRANSITIONING=3
uint8 ESTOP_LATCHED=4
uint8 FAULT_LATCHED=5

builtin_interfaces/Time stamp
uint8 state
bool armed
bool motion_allowed
bool fresh_command_required
bool estop_latched
bool fault_latched
uint32 generation
string reason
