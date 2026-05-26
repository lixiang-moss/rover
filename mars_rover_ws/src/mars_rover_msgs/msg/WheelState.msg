# 单个轮组状态消息。
# 由 stm32_bridge 发布，用于描述一个轮组当前状态或目标回显状态。

# 轮组名，例如 front_left。
string name
# 该轮组底层是否在线。
bool online
# 该轮组当前是否被启用。
bool enabled
# 当前或回显的转向角，单位 rad。
float64 steering_angle
# 当前或回显的车轮线速度，单位 m/s。
float64 drive_velocity
# true 表示来自真实硬件反馈；false 表示只是目标值回显或估计。
bool feedback_is_real
# 该轮组是否存在故障。
bool fault
# 底层故障码；无故障时为 0。
int32 fault_code
