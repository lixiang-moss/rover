"""Pure kinematics helpers for four-wheel independent steering."""

from dataclasses import dataclass
import math

from mars_rover_control.constants import (
    MODE_CRAB,
    MODE_RAW_WHEEL_TEST,
    MODE_SPIN_IN_PLACE,
    MODE_STOP,
    WHEEL_ORDER,
)


@dataclass(frozen=True)
class WheelTarget:
    """A single wheel module target in ROS-level units."""

    name: str
    enabled: bool
    steering_angle: float
    drive_velocity: float


def clamp(value: float, lower: float, upper: float) -> float:
    return min(max(value, lower), upper)


def normalize_angle(angle: float) -> float:
    """Normalize an angle to [-pi, pi]."""

    return math.atan2(math.sin(angle), math.cos(angle))


def default_wheel_positions(wheelbase: float, track_width: float) -> dict[str, tuple[float, float]]:
    half_wheelbase = wheelbase / 2.0
    half_track = track_width / 2.0
    return {
        "front_left": (half_wheelbase, half_track),
        "front_right": (half_wheelbase, -half_track),
        "rear_left": (-half_wheelbase, half_track),
        "rear_right": (-half_wheelbase, -half_track),
    }


def zero_targets(last_angles: dict[str, float] | None = None, enabled: bool = False) -> list[WheelTarget]:
    last_angles = last_angles or {}
    return [
        WheelTarget(name=name, enabled=enabled, steering_angle=last_angles.get(name, 0.0), drive_velocity=0.0)
        for name in WHEEL_ORDER
    ]


def compute_wheel_targets(
    mode: int,
    vx: float,
    vy: float,
    wz: float,
    *,
    wheelbase: float,
    track_width: float,
    max_steering_angle: float,
    max_drive_velocity: float,
    active_test_wheel: str = "front_left",
    last_angles: dict[str, float] | None = None,
) -> list[WheelTarget]:
    """Compute wheel targets for the first-stage rover drive modes."""

    last_angles = last_angles or {}
    positions = default_wheel_positions(wheelbase, track_width)

    if mode == MODE_STOP:
        return zero_targets(last_angles, enabled=False)

    if mode == MODE_RAW_WHEEL_TEST:
        targets: list[WheelTarget] = []
        for name in WHEEL_ORDER:
            if name == active_test_wheel:
                targets.append(
                    WheelTarget(
                        name=name,
                        enabled=True,
                        steering_angle=clamp(wz, -max_steering_angle, max_steering_angle),
                        drive_velocity=clamp(vx, -max_drive_velocity, max_drive_velocity),
                    )
                )
            else:
                targets.append(
                    WheelTarget(
                        name=name,
                        enabled=False,
                        steering_angle=last_angles.get(name, 0.0),
                        drive_velocity=0.0,
                    )
                )
        return targets

    if mode == MODE_CRAB:
        speed = math.hypot(vx, vy)
        if speed <= 1e-9:
            return zero_targets(last_angles, enabled=True)
        angle = clamp(normalize_angle(math.atan2(vy, vx)), -max_steering_angle, max_steering_angle)
        drive = clamp(speed, -max_drive_velocity, max_drive_velocity)
        return [WheelTarget(name=name, enabled=True, steering_angle=angle, drive_velocity=drive) for name in WHEEL_ORDER]

    if mode == MODE_SPIN_IN_PLACE:
        if abs(wz) <= 1e-9:
            return zero_targets(last_angles, enabled=True)
        targets = []
        for name in WHEEL_ORDER:
            x_pos, y_pos = positions[name]
            wheel_vx = -wz * y_pos
            wheel_vy = wz * x_pos
            angle = clamp(normalize_angle(math.atan2(wheel_vy, wheel_vx)), -max_steering_angle, max_steering_angle)
            drive = clamp(math.hypot(wheel_vx, wheel_vy), -max_drive_velocity, max_drive_velocity)
            targets.append(WheelTarget(name=name, enabled=True, steering_angle=angle, drive_velocity=drive))
        return targets

    return zero_targets(last_angles, enabled=False)
