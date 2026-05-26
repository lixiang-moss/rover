"""Pi 到 STM32 串口 JSON 帧编解码测试。

这些测试验证 ROS 2 侧生成的 SET_WHEEL_TARGETS 帧可以被 decode 回来，
并保持关键字段不丢失。
"""

from types import SimpleNamespace

from mars_rover_control.serial_codec import decode_ack_line, encode_setpoints_frame


def make_point(name, enabled):
    """构造一个简化的 WheelSetpoint-like 对象，用于测试编码函数。"""

    return SimpleNamespace(
        name=name,
        enabled=enabled,
        steering_angle=0.1,
        drive_velocity=0.02,
        steering_velocity_limit=0.3,
        drive_acceleration_limit=0.1,
    )


def test_setpoints_frame_round_trips_as_json_payload():
    """验证编码后的四轮目标帧能被正确解析回 payload 字典。"""

    frame = encode_setpoints_frame(
        7,
        3,
        enabled=False,
        estop=False,
        setpoints=[
            make_point("front_left", True),
            make_point("front_right", False),
            make_point("rear_left", False),
            make_point("rear_right", False),
        ],
    )

    payload = decode_ack_line(frame)

    assert payload["type"] == "SET_WHEEL_TARGETS"
    assert payload["sequence_id"] == 7
    assert payload["mode"] == "RAW_WHEEL_TEST"
    assert payload["enabled"] is False
    assert payload["estop"] is False
    assert payload["wheels"][0]["name"] == "front_left"
    assert payload["wheels"][0]["enabled"] is False
    assert payload["wheels"][1]["enabled"] is False


def test_setpoints_frame_preserves_estop_and_disabled_execution():
    """验证急停帧不会被编码成底层可执行状态。"""

    frame = encode_setpoints_frame(
        8,
        1,
        enabled=False,
        estop=True,
        setpoints=[
            make_point("front_left", True),
            make_point("front_right", True),
            make_point("rear_left", True),
            make_point("rear_right", True),
        ],
    )

    payload = decode_ack_line(frame)

    assert payload["mode"] == "CRAB"
    assert payload["enabled"] is False
    assert payload["estop"] is True
    assert all(not wheel["enabled"] for wheel in payload["wheels"])


def test_setpoints_frame_allows_wheel_enabled_only_when_global_enabled():
    """验证只有顶层 enabled=true 且无急停时，轮组 enabled 才可能为 true。"""

    frame = encode_setpoints_frame(
        9,
        1,
        enabled=True,
        estop=False,
        setpoints=[
            make_point("front_left", True),
            make_point("front_right", True),
            make_point("rear_left", True),
            make_point("rear_right", True),
        ],
    )

    payload = decode_ack_line(frame)

    assert payload["enabled"] is True
    assert all(wheel["enabled"] for wheel in payload["wheels"])
