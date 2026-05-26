"""MARS Rover 控制栈的公共常量定义。

本文件集中维护驱动模式编号、轮组顺序和关节命名。
这样其他节点不需要各自硬编码字符串，避免话题、消息和 URDF 中的名称不一致。
"""

# 驱动模式编号：这些值会写入 DriveMode 消息和 WheelSetpointArray 消息。
MODE_STOP = 0
MODE_CRAB = 1
MODE_SPIN_IN_PLACE = 2
MODE_RAW_WHEEL_TEST = 3

# 驱动模式名称到编号的映射，用于把用户输入的字符串模式请求转换成内部整数。
MODE_NAME_TO_VALUE = {
    "STOP": MODE_STOP,
    "CRAB": MODE_CRAB,
    "SPIN_IN_PLACE": MODE_SPIN_IN_PLACE,
    "RAW_WHEEL_TEST": MODE_RAW_WHEEL_TEST,
}

# 驱动模式编号到名称的反向映射，用于日志输出和 Pi->STM32 串口帧编码。
MODE_VALUE_TO_NAME = {value: name for name, value in MODE_NAME_TO_VALUE.items()}

# 四个轮组的固定顺序。所有 wheel setpoints、wheel states 和串口帧都应保持此顺序。
WHEEL_ORDER = ("front_left", "front_right", "rear_left", "rear_right")

# URDF 和 /joint_states 中使用的 8 个关节名，按“每个轮组转向关节+驱动关节”的顺序排列。
JOINT_NAMES = (
    "front_left_steering_joint",
    "front_left_drive_joint",
    "front_right_steering_joint",
    "front_right_drive_joint",
    "rear_left_steering_joint",
    "rear_left_drive_joint",
    "rear_right_steering_joint",
    "rear_right_drive_joint",
)

# 轮组名到转向关节名的映射，用于把 WheelState 转换为标准 JointState。
STEERING_JOINT_BY_WHEEL = {
    "front_left": "front_left_steering_joint",
    "front_right": "front_right_steering_joint",
    "rear_left": "rear_left_steering_joint",
    "rear_right": "rear_right_steering_joint",
}

# 轮组名到驱动关节名的映射，用于把 WheelState 中的车轮速度写入标准 JointState。
DRIVE_JOINT_BY_WHEEL = {
    "front_left": "front_left_drive_joint",
    "front_right": "front_right_drive_joint",
    "rear_left": "rear_left_drive_joint",
    "rear_right": "rear_right_drive_joint",
}
