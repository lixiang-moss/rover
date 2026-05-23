"""Shared names and mode values for the rover control stack."""

MODE_STOP = 0
MODE_CRAB = 1
MODE_SPIN_IN_PLACE = 2
MODE_RAW_WHEEL_TEST = 3
MODE_DOUBLE_ACKERMANN = 4

MODE_NAME_TO_VALUE = {
    "STOP": MODE_STOP,
    "CRAB": MODE_CRAB,
    "SPIN_IN_PLACE": MODE_SPIN_IN_PLACE,
    "RAW_WHEEL_TEST": MODE_RAW_WHEEL_TEST,
    "DOUBLE_ACKERMANN": MODE_DOUBLE_ACKERMANN,
}

MODE_VALUE_TO_NAME = {value: name for name, value in MODE_NAME_TO_VALUE.items()}

WHEEL_ORDER = ("front_left", "front_right", "rear_left", "rear_right")

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

STEERING_JOINT_BY_WHEEL = {
    "front_left": "front_left_steering_joint",
    "front_right": "front_right_steering_joint",
    "rear_left": "rear_left_steering_joint",
    "rear_right": "rear_right_steering_joint",
}

DRIVE_JOINT_BY_WHEEL = {
    "front_left": "front_left_drive_joint",
    "front_right": "front_right_drive_joint",
    "rear_left": "rear_left_drive_joint",
    "rear_right": "rear_right_drive_joint",
}
