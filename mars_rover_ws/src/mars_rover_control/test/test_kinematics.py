"""四轮运动学纯函数的单元测试。

这些测试不启动 ROS 2 节点，只验证 `compute_wheel_targets` 在不同模式下
是否输出符合预期的轮组 enabled、转向角和驱动速度。
"""

import math

from mars_rover_control.constants import MODE_CRAB, MODE_RAW_WHEEL_TEST, MODE_SPIN_IN_PLACE, MODE_STOP
from mars_rover_control.kinematics import compute_wheel_targets


DEFAULTS = {
    "wheelbase": 0.706,
    "track_width": 0.288,
    "max_steering_angle": 1.5708,
    "max_drive_velocity": 0.10,
}


def by_name(targets):
    """把 WheelTarget 列表转换成按轮组名索引的字典，便于测试断言。"""

    return {target.name: target for target in targets}


def test_stop_disables_all_wheels_and_keeps_last_angles():
    """验证 STOP 模式会禁用所有轮组、速度归零，并保持已有转向角。"""

    targets = compute_wheel_targets(
        MODE_STOP,
        0.1,
        0.0,
        0.0,
        last_angles={"front_left": 0.42},
        **DEFAULTS,
    )

    assert all(not target.enabled for target in targets)
    assert all(target.drive_velocity == 0.0 for target in targets)
    assert by_name(targets)["front_left"].steering_angle == 0.42


def test_crab_forward_points_all_wheels_forward():
    """验证 CRAB 前进命令会让四个轮子都指向前方。"""

    targets = compute_wheel_targets(MODE_CRAB, 0.05, 0.0, 0.0, **DEFAULTS)

    assert all(target.enabled for target in targets)
    assert all(abs(target.steering_angle) < 1e-6 for target in targets)
    assert all(math.isclose(target.drive_velocity, 0.05) for target in targets)


def test_crab_left_points_all_wheels_left():
    """验证 CRAB 左移命令会让四个轮子都指向左侧。"""

    targets = compute_wheel_targets(MODE_CRAB, 0.0, 0.05, 0.0, **DEFAULTS)

    assert all(target.enabled for target in targets)
    assert all(math.isclose(target.steering_angle, math.pi / 2.0, abs_tol=1e-4) for target in targets)
    assert all(math.isclose(target.drive_velocity, 0.05) for target in targets)


def test_crab_diagonal_uses_common_angle():
    """验证 CRAB 斜向移动时四个轮子使用相同的斜向角。"""

    targets = compute_wheel_targets(MODE_CRAB, 0.05, 0.05, 0.0, **DEFAULTS)

    assert all(target.enabled for target in targets)
    assert all(math.isclose(target.steering_angle, math.pi / 4.0, abs_tol=1e-4) for target in targets)


def test_spin_in_place_points_wheels_tangentially():
    """验证原地旋转模式下四个轮子呈切向布置。"""

    targets = by_name(compute_wheel_targets(MODE_SPIN_IN_PLACE, 0.0, 0.0, 0.20, **DEFAULTS))

    assert targets["front_left"].enabled
    assert targets["front_left"].steering_angle > 0.0
    assert targets["front_right"].steering_angle > 0.0
    assert targets["rear_left"].steering_angle < 0.0
    assert targets["rear_right"].steering_angle < 0.0
    assert all(target.drive_velocity > 0.0 for target in targets.values())


def test_raw_wheel_test_only_enables_front_left():
    """验证 RAW_WHEEL_TEST 默认只启用 front_left，其余轮组禁用。"""

    targets = by_name(
        compute_wheel_targets(
            MODE_RAW_WHEEL_TEST,
            0.08,
            0.0,
            0.2,
            active_test_wheel="front_left",
            **DEFAULTS,
        )
    )

    assert targets["front_left"].enabled
    assert math.isclose(targets["front_left"].drive_velocity, 0.08)
    assert math.isclose(targets["front_left"].steering_angle, 0.2)
    for name in ("front_right", "rear_left", "rear_right"):
        assert not targets[name].enabled
        assert targets[name].drive_velocity == 0.0
