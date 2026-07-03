"""四轮运动学纯函数的单元测试。

这些测试不启动 ROS 2 节点，只验证 `compute_wheel_targets` 在不同模式下
是否输出符合预期的轮组 enabled、转向角和驱动速度。
"""

import math

from mars_rover_control.constants import (
    MODE_CRAB,
    MODE_RAW_WHEEL_TEST,
    MODE_SPIN_IN_PLACE,
    MODE_STOP,
)
from mars_rover_control.kinematics import (
    compute_wheel_targets,
    default_wheel_positions,
    wheel_angular_velocity,
)


DEFAULTS = {
    "wheelbase": 0.706,
    "track_width": 0.288,
    "max_steering_angle": 1.5708,
    "max_drive_velocity": 0.10,
}


def by_name(targets):
    """把 WheelTarget 列表转换成按轮组名索引的字典，便于测试断言。"""

    return {target.name: target for target in targets}


def realized_vector(target):
    """由转向角和有符号轮速重构车轮接地点二维速度。"""

    return (
        target.drive_velocity * math.cos(target.steering_angle),
        target.drive_velocity * math.sin(target.steering_angle),
    )


def assert_vector_close(actual, expected, tolerance=1e-6):
    """逐分量比较二维轮速向量。"""

    assert math.isclose(actual[0], expected[0], abs_tol=tolerance)
    assert math.isclose(actual[1], expected[1], abs_tol=tolerance)


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
    assert all(
        math.isclose(target.steering_angle, math.pi / 2.0, abs_tol=1e-4)
        for target in targets
    )
    assert all(math.isclose(target.drive_velocity, 0.05) for target in targets)


def test_crab_diagonal_uses_common_angle():
    """验证 CRAB 斜向移动时四个轮子使用相同的斜向角。"""

    targets = compute_wheel_targets(MODE_CRAB, 0.05, 0.05, 0.0, **DEFAULTS)

    assert all(target.enabled for target in targets)
    assert all(
        math.isclose(target.steering_angle, math.pi / 4.0, abs_tol=1e-4)
        for target in targets
    )


def test_crab_reverse_uses_negative_wheel_speed_without_changing_direction():
    """反向 CRAB 必须实现 (-vx, 0)，不能被角度裁剪成侧移。"""

    targets = compute_wheel_targets(MODE_CRAB, -0.05, 0.0, 0.0, **DEFAULTS)

    for target in targets:
        assert_vector_close(realized_vector(target), (-0.05, 0.0))
        assert target.drive_velocity < 0.0


def test_spin_in_place_realizes_exact_tangential_vectors_in_both_directions():
    """正反旋转的四个轮速向量都必须与刚体切向速度一致。"""

    positions = default_wheel_positions(DEFAULTS["wheelbase"], DEFAULTS["track_width"])
    for wz in (0.20, -0.20):
        targets = by_name(
            compute_wheel_targets(MODE_SPIN_IN_PLACE, 0.0, 0.0, wz, **DEFAULTS)
        )
        for name, target in targets.items():
            x_pos, y_pos = positions[name]
            expected = (-wz * y_pos, wz * x_pos)
            assert target.enabled
            assert_vector_close(realized_vector(target), expected)


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


def test_wheel_linear_velocity_is_converted_to_joint_angular_velocity():
    """JointState 的驱动关节速度必须使用 rad/s。"""

    assert math.isclose(wheel_angular_velocity(0.09, 0.09), 1.0)
    assert math.isclose(wheel_angular_velocity(-0.045, 0.09), -0.5)
