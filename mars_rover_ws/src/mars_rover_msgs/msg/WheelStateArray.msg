# 四轮状态数组消息。
# 由 stm32_bridge 发布，供 joint_state_republisher、诊断工具和 RViz 链路使用。

# 状态生成时间。
builtin_interfaces/Time stamp
# 底层最近处理或回显的命令序号。
uint32 last_command_sequence_id
# 四个轮组状态，顺序固定为 front_left、front_right、rear_left、rear_right。
WheelState[4] states
