"""四轮独立转向/独立驱动底盘的纯运动学计算工具。

本文件不依赖 ROS 2 节点运行时，只负责把“机器人整体速度 + 驱动模式”
转换成四个轮组的目标转向角和目标驱动速度。这样运动学逻辑可以被节点、
单元测试和后续仿真代码复用。
"""

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
    """单个轮组的目标值。

    字段使用 ROS 高层单位：
    - steering_angle 使用 rad。
    - drive_velocity 使用 m/s。
    - enabled 表示该轮组是否允许执行目标。
    """

    name: str
    enabled: bool
    steering_angle: float
    drive_velocity: float


def clamp(value: float, lower: float, upper: float) -> float:
    """把输入值限制在 [lower, upper] 范围内，避免输出超过安全边界。"""

    return min(max(value, lower), upper)


def normalize_angle(angle: float) -> float:
    """把任意角度归一化到 [-pi, pi]。

    这样后续比较和限幅时不会因为 2*pi 周期导致角度跳变。
    """

    return math.atan2(math.sin(angle), math.cos(angle))


def default_wheel_positions(wheelbase: float, track_width: float) -> dict[str, tuple[float, float]]:
    """根据轴距和轮距生成四个轮组相对 base_link 中心的位置。

    坐标系约定：
    - +x 指向机器人前方。
    - +y 指向机器人左侧。
    - 原点位于机器人几何中心。
    """

    half_wheelbase = wheelbase / 2.0
    half_track = track_width / 2.0
    return {
        "front_left": (half_wheelbase, half_track),
        "front_right": (half_wheelbase, -half_track),
        "rear_left": (-half_wheelbase, half_track),
        "rear_right": (-half_wheelbase, -half_track),
    }


def zero_targets(last_angles: dict[str, float] | None = None, enabled: bool = False) -> list[WheelTarget]:
    """生成四个轮组的零速度目标。

    如果提供 last_angles，则保持每个轮组最近一次转向角；这可以避免停止时
    轮子无意义地回正或抖动。enabled 参数用于决定停止状态下轮组是否仍被认为启用。
    """

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
    """计算第一版支持的驱动模式下的四轮目标。

    输入：
    - mode：驱动模式编号。
    - vx/vy/wz：机器人整体速度，分别对应前后、左右、绕 z 轴旋转。
    - wheelbase/track_width：底盘几何尺寸。
    - max_steering_angle/max_drive_velocity：安全限幅。
    - active_test_wheel：RAW_WHEEL_TEST 模式下唯一启用的轮组。
    - last_angles：上一周期角度，用于停止时保持轮子方向。

    输出：
    - 固定顺序的四个 WheelTarget。
    """

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
