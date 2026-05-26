"""真实串口硬件输出策略。

本文件不依赖 ROS 2 节点运行时，用于判断 real_serial 模式下某组
WheelSetpoint 是否允许写入串口。这样策略可以被节点和单元测试共同使用。
"""

from mars_rover_control.constants import (
    MODE_CRAB,
    MODE_RAW_WHEEL_TEST,
    MODE_SPIN_IN_PLACE,
    MODE_STOP,
    WHEEL_ORDER,
)


FULL_VEHICLE_MODES = {MODE_STOP, MODE_CRAB, MODE_SPIN_IN_PLACE}


def _points_by_name(setpoints) -> dict:
    """把 setpoints 转换为按轮组名索引的字典，并要求四个轮组齐全且无重复。"""

    points = {}
    for point in setpoints:
        if point.name in points:
            return {}
        points[point.name] = point
    if set(points.keys()) != set(WHEEL_ORDER):
        return {}
    return points


def _drive_is_zero(point) -> bool:
    """判断轮组驱动速度是否为零，允许极小浮点误差。"""

    return abs(float(point.drive_velocity)) <= 1e-9


def real_serial_command_is_allowed(
    mode: int,
    setpoints,
    *,
    hardware_output_mode: str,
    active_test_wheel: str,
) -> bool:
    """判断 real_serial 下当前四轮目标是否符合硬件输出策略。

    hardware_output_mode:
    - single_wheel：只允许 RAW_WHEEL_TEST，且只启用 active_test_wheel。
    - full_vehicle：允许 STOP、CRAB、SPIN_IN_PLACE，并允许四轮正常启用。
    """

    output_mode = hardware_output_mode.strip().lower()
    points = _points_by_name(setpoints)
    if not points:
        return False

    if output_mode == "single_wheel":
        if int(mode) != MODE_RAW_WHEEL_TEST or active_test_wheel not in WHEEL_ORDER:
            return False
        for name in WHEEL_ORDER:
            point = points[name]
            if name == active_test_wheel:
                if not bool(point.enabled):
                    return False
            elif bool(point.enabled) or not _drive_is_zero(point):
                return False
        return True

    if output_mode == "full_vehicle":
        if int(mode) not in FULL_VEHICLE_MODES:
            return False
        if int(mode) == MODE_STOP:
            return all(_drive_is_zero(points[name]) for name in WHEEL_ORDER)
        return all(bool(points[name].enabled) for name in WHEEL_ORDER)

    return False
