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
    return {target.name: target for target in targets}


def test_stop_disables_all_wheels_and_keeps_last_angles():
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
    targets = compute_wheel_targets(MODE_CRAB, 0.05, 0.0, 0.0, **DEFAULTS)

    assert all(target.enabled for target in targets)
    assert all(abs(target.steering_angle) < 1e-6 for target in targets)
    assert all(math.isclose(target.drive_velocity, 0.05) for target in targets)


def test_crab_left_points_all_wheels_left():
    targets = compute_wheel_targets(MODE_CRAB, 0.0, 0.05, 0.0, **DEFAULTS)

    assert all(target.enabled for target in targets)
    assert all(math.isclose(target.steering_angle, math.pi / 2.0, abs_tol=1e-4) for target in targets)
    assert all(math.isclose(target.drive_velocity, 0.05) for target in targets)


def test_crab_diagonal_uses_common_angle():
    targets = compute_wheel_targets(MODE_CRAB, 0.05, 0.05, 0.0, **DEFAULTS)

    assert all(target.enabled for target in targets)
    assert all(math.isclose(target.steering_angle, math.pi / 4.0, abs_tol=1e-4) for target in targets)


def test_spin_in_place_points_wheels_tangentially():
    targets = by_name(compute_wheel_targets(MODE_SPIN_IN_PLACE, 0.0, 0.0, 0.20, **DEFAULTS))

    assert targets["front_left"].enabled
    assert targets["front_left"].steering_angle > 0.0
    assert targets["front_right"].steering_angle > 0.0
    assert targets["rear_left"].steering_angle < 0.0
    assert targets["rear_right"].steering_angle < 0.0
    assert all(target.drive_velocity > 0.0 for target in targets.values())


def test_raw_wheel_test_only_enables_front_left():
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
