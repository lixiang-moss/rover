"""Pi 与 STM32 紧凑串口协议的单元测试。"""

import json
from types import SimpleNamespace
import zlib

import pytest

from mars_rover_control.serial_codec import (
    MAX_FRAME_BYTES,
    SerialFrameBuffer,
    decode_ack_line,
    decode_protocol_frame,
    encode_protocol_frame,
    encode_safe_stop_frame,
    encode_setpoints_frame,
)


WHEEL_NAMES = ("front_left", "front_right", "rear_left", "rear_right")


def make_point(name, enabled=True, angle=0.1, velocity=0.02):
    """构造 WheelSetpoint-like 对象，避免测试依赖 ROS 消息运行时。"""

    return SimpleNamespace(
        name=name,
        enabled=enabled,
        steering_angle=angle,
        drive_velocity=velocity,
        steering_velocity_limit=0.15,
        drive_acceleration_limit=0.05,
    )


def make_points(enabled=True):
    """按协议固定顺序构造四个轮组目标。"""

    return [make_point(name, enabled=enabled) for name in WHEEL_NAMES]


def raw_frame(payload, *, uppercase=True):
    """直接构造带 CRC 的帧，用于测试解码器边界。"""

    raw_json = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    checksum = f"{zlib.crc32(raw_json) & 0xFFFFFFFF:08X}"
    if not uppercase:
        checksum = checksum.lower()
    return raw_json + b"*" + checksum.encode("ascii") + b"\n"


def test_setpoints_frame_round_trip_uses_compact_fixed_layout():
    """W 帧应只包含紧凑字段和四个固定顺序的五元素轮组数组。"""

    points = make_points(enabled=False)
    points[0].enabled = True
    payload = decode_protocol_frame(
        encode_setpoints_frame(42, 3, enabled=True, estop=False, setpoints=points)
    )

    assert payload == {
        "e": 1,
        "m": 3,
        "q": 42,
        "s": 0,
        "t": "W",
        "v": 1,
        "w": [
            [1, 0.1, 0.02, 0.15, 0.05],
            [0, 0.1, 0.02, 0.15, 0.05],
            [0, 0.1, 0.02, 0.15, 0.05],
            [0, 0.1, 0.02, 0.15, 0.05],
        ],
    }


def test_documented_single_wheel_crc_vector_is_stable():
    """接口文档中的固定 W 帧测试向量必须与编码器保持一致。"""

    points = [make_point("front_left", True, angle=0.1, velocity=0.08)]
    points.extend(make_point(name, False, angle=0.0, velocity=0.0) for name in WHEEL_NAMES[1:])
    expected = (
        b'{"e":1,"m":3,"q":42,"s":0,"t":"W","v":1,"w":'
        b'[[1,0.1,0.08,0.15,0.05],[0,0.0,0.0,0.15,0.05],'
        b'[0,0.0,0.0,0.15,0.05],[0,0.0,0.0,0.15,0.05]]}*58782C06\n'
    )

    assert encode_setpoints_frame(42, 3, True, False, points) == expected


def test_estop_forces_global_and_all_wheel_enable_flags_off():
    """急停激活时，任何上层使能都不能进入底层执行标志。"""

    payload = decode_protocol_frame(
        encode_setpoints_frame(8, 1, enabled=True, estop=True, setpoints=make_points())
    )

    assert payload["e"] == 0
    assert payload["s"] == 1
    assert all(wheel[0] == 0 for wheel in payload["w"])


def test_global_disable_forces_all_wheel_enable_flags_off():
    """ControlState 未授权时，每个轮组执行标志也必须为 0。"""

    payload = decode_protocol_frame(
        encode_setpoints_frame(9, 1, enabled=False, estop=False, setpoints=make_points())
    )

    assert payload["e"] == 0
    assert all(wheel[0] == 0 for wheel in payload["w"])


def test_safe_stop_frame_is_independent_of_upstream_setpoints():
    """策略拒绝时仍能生成固定四轮、全局禁用的 STOP 帧。"""

    payload = decode_protocol_frame(encode_safe_stop_frame(10, estop=True))
    assert payload["m"] == 0
    assert payload["e"] == 0
    assert payload["s"] == 1
    assert payload["q"] == 10
    assert payload["w"] == [[0, 0.0, 0.0, 0.0, 0.0]] * 4


def test_sequence_id_wraps_to_uint32():
    """长期运行后序号超过 uint32 时应无符号回绕。"""

    payload = decode_protocol_frame(
        encode_setpoints_frame(0x1_0000_0003, 0, False, False, make_points())
    )

    assert payload["q"] == 3


@pytest.mark.parametrize(
    "payload",
    [
        {"v": 1, "t": "A", "q": 42, "ok": 1, "fc": 0},
        {"v": 1, "t": "A", "q": 43, "ok": 0, "fc": 1001},
        {"v": 1, "t": "S", "q": 42, "on": 1, "es": 0, "to": 0, "fc": 0},
        {"v": 1, "t": "S", "q": 42, "on": 1, "es": 1, "to": 1, "fc": 3001},
    ],
)
def test_ack_and_status_round_trip(payload):
    """合法 ACK/STATUS 帧应能通过严格校验并保持字段值。"""

    assert decode_ack_line(encode_protocol_frame(payload)) == payload


def test_crc_corruption_is_rejected():
    """JSON 字节被改动但 CRC 未更新时必须拒绝整帧。"""

    frame = bytearray(encode_protocol_frame({"v": 1, "t": "A", "q": 7, "ok": 1, "fc": 0}))
    frame[frame.index(b"7")] = ord("8")

    with pytest.raises(ValueError, match="checksum mismatch"):
        decode_protocol_frame(bytes(frame))


def test_missing_separator_is_rejected():
    """没有星号分隔符的行不是协议帧。"""

    with pytest.raises(ValueError, match="separator"):
        decode_protocol_frame(b'{"v":1,"t":"A","q":1,"ok":1,"fc":0}\n')


def test_crc_must_be_eight_uppercase_hex_digits():
    """CRC 文本格式固定，避免两端对可接受格式理解不一致。"""

    payload = {"v": 1, "t": "A", "q": 1, "ok": 1, "fc": 0}
    with pytest.raises(ValueError, match="uppercase hexadecimal"):
        decode_protocol_frame(raw_frame(payload, uppercase=False))

    valid = raw_frame(payload)
    with pytest.raises(ValueError, match="eight hex digits"):
        decode_protocol_frame(valid[:-3] + b"\n")


def test_oversized_frame_is_rejected_before_json_parsing():
    """超过 512 字节的输入必须立即拒绝。"""

    oversized = b"{" + b" " * MAX_FRAME_BYTES + b"}*00000000\n"
    with pytest.raises(ValueError, match="exceeds"):
        decode_protocol_frame(oversized)


@pytest.mark.parametrize(
    "payload, expected_error",
    [
        ({"v": 2, "t": "A", "q": 1, "ok": 1, "fc": 0}, "version"),
        ({"v": 1, "t": "A", "q": -1, "ok": 1, "fc": 0}, "unsigned"),
        ({"v": 1, "t": "A", "q": 1, "ok": 2, "fc": 0}, "0 or 1"),
        ({"v": 1, "t": "S", "q": 1, "on": 1, "es": 0, "to": 0}, "fields"),
    ],
)
def test_invalid_protocol_fields_are_rejected(payload, expected_error):
    """版本、范围或字段集合不符合合同的响应不能进入 bridge 状态。"""

    with pytest.raises(ValueError, match=expected_error):
        decode_protocol_frame(raw_frame(payload))


def test_non_finite_wheel_value_is_rejected():
    """NaN/Inf 不能被编码为电机目标。"""

    points = make_points()
    points[0].drive_velocity = float("nan")

    with pytest.raises(ValueError, match="finite|JSON"):
        encode_setpoints_frame(1, 3, True, False, points)


def test_wrong_wheel_order_is_rejected():
    """轮组顺序错误时必须报错，不能依赖 STM32 猜测名称。"""

    points = make_points()
    points[0], points[1] = points[1], points[0]

    with pytest.raises(ValueError, match="fixed wheel order"):
        encode_setpoints_frame(1, 3, True, False, points)


def test_command_frame_cannot_be_used_as_stm32_response():
    """bridge 响应入口只接受 A/S，不接受回送的 W 命令。"""

    frame = encode_setpoints_frame(1, 3, False, False, make_points())
    with pytest.raises(ValueError, match="ACK or STATUS"):
        decode_ack_line(frame)


def test_stream_buffer_reassembles_fragmented_frame():
    """UART 把一帧拆成多个 read 返回时，必须等待换行后再交给解码器。"""

    frame = encode_protocol_frame({"v": 1, "t": "A", "q": 11, "ok": 1, "fc": 0})
    buffer = SerialFrameBuffer()

    first, dropped_first = buffer.feed(frame[:7])
    second, dropped_second = buffer.feed(frame[7:19])
    third, dropped_third = buffer.feed(frame[19:])

    assert first == []
    assert second == []
    assert dropped_first + dropped_second + dropped_third == 0
    assert third == [frame]
    assert decode_ack_line(third[0])["q"] == 11


def test_stream_buffer_splits_multiple_frames_from_one_read():
    """一次 read 收到 ACK 和 STATUS 粘包时，应输出两条完整帧。"""

    ack = encode_protocol_frame({"v": 1, "t": "A", "q": 12, "ok": 1, "fc": 0})
    status = encode_protocol_frame(
        {"v": 1, "t": "S", "q": 12, "on": 1, "es": 0, "to": 0, "fc": 0}
    )
    frames, dropped = SerialFrameBuffer().feed(ack + status)

    assert frames == [ack, status]
    assert dropped == 0


def test_stream_buffer_drops_overlong_partial_frame_and_recovers():
    """无换行超长数据不能无限占用内存，清空后仍能接收下一条合法帧。"""

    buffer = SerialFrameBuffer()
    frames, dropped = buffer.feed(b"X" * (MAX_FRAME_BYTES + 1))
    assert frames == []
    assert dropped == 1

    ack = encode_protocol_frame({"v": 1, "t": "A", "q": 13, "ok": 1, "fc": 0})
    frames, dropped = buffer.feed(b"discarded-tail\n" + ack)
    assert frames == [ack]
    assert dropped == 0


@pytest.mark.parametrize(
    "mutator, expected_error",
    [
        (lambda payload: payload.update(m=99), "drive mode"),
        (lambda payload: payload["w"][0].__setitem__(3, -0.1), "non-negative"),
        (lambda payload: payload["w"][0].__setitem__(4, -0.1), "non-negative"),
    ],
)
def test_command_mode_and_limits_are_validated(mutator, expected_error):
    """不支持的模式和负限幅值必须在编码前被拒绝。"""

    payload = decode_protocol_frame(
        encode_setpoints_frame(14, 3, True, False, make_points())
    )
    mutator(payload)

    with pytest.raises(ValueError, match=expected_error):
        encode_protocol_frame(payload)
