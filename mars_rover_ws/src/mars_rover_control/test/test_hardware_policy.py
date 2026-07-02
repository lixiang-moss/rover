"""真实串口硬件输出策略测试。

这些测试不启动 ROS 2 节点，只验证 real_serial 模式下 single_wheel 与
full_vehicle 两种硬件输出策略是否正确放行或拒绝四轮目标。
"""

from types import SimpleNamespace

from mars_rover_control.constants import (
    MODE_CRAB,
    MODE_RAW_WHEEL_TEST,
    MODE_SPIN_IN_PLACE,
    MODE_STOP,
)
from mars_rover_control.hardware_policy import (
    bridge_output_is_enabled,
    real_serial_command_is_allowed,
)


WHEELS = ("front_left", "front_right", "rear_left", "rear_right")


def test_serial_echo_can_never_enable_real_output():
    """即使其他条件全为 true，serial_echo 也必须强制 e=0。"""

    assert not bridge_output_is_enabled(
        bridge_mode="serial_echo",
        control_state_allows_output=True,
        stm32_status_allows_output=True,
        estop_active=False,
    )


def test_real_serial_requires_every_output_interlock():
    """真实输出必须同时通过 ControlState、STM32 状态和急停检查。"""

    assert bridge_output_is_enabled(
        bridge_mode="real_serial",
        control_state_allows_output=True,
        stm32_status_allows_output=True,
        estop_active=False,
    )
    assert not bridge_output_is_enabled(
        bridge_mode="real_serial",
        control_state_allows_output=False,
        stm32_status_allows_output=True,
        estop_active=False,
    )


def make_point(name, enabled, drive_velocity=0.02):
    """构造一个简化的 WheelSetpoint-like 对象。"""

    return SimpleNamespace(name=name, enabled=enabled, drive_velocity=drive_velocity)


def make_points(enabled_names, drive_velocity=0.02):
    """按固定轮组顺序构造四个测试 setpoints。"""

    return [
        make_point(
            name,
            name in enabled_names,
            drive_velocity if name in enabled_names else 0.0,
        )
        for name in WHEELS
    ]


def test_single_wheel_allows_only_raw_active_wheel():
    """single_wheel 策略只允许 RAW_WHEEL_TEST 中指定轮组启用。"""

    assert real_serial_command_is_allowed(
        MODE_RAW_WHEEL_TEST,
        make_points({"front_left"}),
        hardware_output_mode="single_wheel",
        active_test_wheel="front_left",
    )


def test_single_wheel_always_allows_disabled_stop():
    """STOP 是所有真实输出 profile 的共同安全模式。"""

    assert real_serial_command_is_allowed(
        MODE_STOP,
        make_points(set(), drive_velocity=0.0),
        hardware_output_mode="single_wheel",
        active_test_wheel="front_left",
    )


def test_single_wheel_allows_switching_active_test_wheel():
    """single_wheel 策略允许通过参数切换当前测试轮组。"""

    assert real_serial_command_is_allowed(
        MODE_RAW_WHEEL_TEST,
        make_points({"rear_right"}),
        hardware_output_mode="single_wheel",
        active_test_wheel="rear_right",
    )


def test_single_wheel_rejects_crab():
    """single_wheel 策略拒绝 CRAB 四轮输出。"""

    assert not real_serial_command_is_allowed(
        MODE_CRAB,
        make_points(set(WHEELS)),
        hardware_output_mode="single_wheel",
        active_test_wheel="front_left",
    )


def test_single_wheel_rejects_extra_enabled_wheel():
    """single_wheel 策略拒绝多个轮组同时启用。"""

    assert not real_serial_command_is_allowed(
        MODE_RAW_WHEEL_TEST,
        make_points({"front_left", "front_right"}),
        hardware_output_mode="single_wheel",
        active_test_wheel="front_left",
    )


def test_full_vehicle_allows_crab_and_spin_with_four_wheels_enabled():
    """full_vehicle 策略允许 CRAB 和 SPIN_IN_PLACE 四轮启用。"""

    points = make_points(set(WHEELS))
    assert real_serial_command_is_allowed(
        MODE_CRAB,
        points,
        hardware_output_mode="full_vehicle",
        active_test_wheel="front_left",
    )
    assert real_serial_command_is_allowed(
        MODE_SPIN_IN_PLACE,
        points,
        hardware_output_mode="full_vehicle",
        active_test_wheel="front_left",
    )


def test_full_vehicle_allows_stop_with_zero_drive_velocity():
    """full_vehicle 策略允许 STOP 零速度目标。"""

    assert real_serial_command_is_allowed(
        MODE_STOP,
        make_points(set(), drive_velocity=0.0),
        hardware_output_mode="full_vehicle",
        active_test_wheel="front_left",
    )


def test_full_vehicle_rejects_partial_enabled_motion():
    """full_vehicle 策略拒绝 CRAB/SPIN 中只有部分轮组启用。"""

    assert not real_serial_command_is_allowed(
        MODE_CRAB,
        make_points({"front_left", "front_right"}),
        hardware_output_mode="full_vehicle",
        active_test_wheel="front_left",
    )


def test_full_vehicle_rejects_raw_wheel_test():
    """full_vehicle 策略拒绝 RAW_WHEEL_TEST，避免把测试模式当整车驾驶模式。"""

    assert not real_serial_command_is_allowed(
        MODE_RAW_WHEEL_TEST,
        make_points({"front_left"}),
        hardware_output_mode="full_vehicle",
        active_test_wheel="front_left",
    )
