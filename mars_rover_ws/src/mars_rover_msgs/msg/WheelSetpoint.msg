# 单个轮组目标消息。
# 该消息由 four_wheel_kinematics 生成，表示一个轮组要转到的角度和要执行的驱动速度。

# 轮组名，例如 front_left、front_right、rear_left、rear_right。
string name
# 该轮组是否启用。单轮测试时只有 active wheel 为 true。
bool enabled
# 目标转向角，单位 rad。
float64 steering_angle
# 目标车轮线速度，单位 m/s。
float64 drive_velocity
# 转向速度限制，单位 rad/s，供底层执行器参考。
float64 steering_velocity_limit
# 驱动加速度限制，单位 m/s^2，供底层执行器参考。
float64 drive_acceleration_limit
