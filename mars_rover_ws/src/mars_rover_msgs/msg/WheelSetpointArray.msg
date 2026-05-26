# 四轮目标数组消息。
# 这是 ROS 2 高层运动学和底层 bridge 之间的核心接口。

# 目标生成时间。
builtin_interfaces/Time stamp
# 递增命令序号，用于和 STM32 ACK/status 对齐。
uint32 sequence_id
# 当前驱动模式编号。
uint8 mode
# 四个轮组目标，顺序固定为 front_left、front_right、rear_left、rear_right。
WheelSetpoint[4] setpoints
