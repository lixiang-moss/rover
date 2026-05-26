"""Pi 到 STM32 的行分隔 JSON 串口帧编解码工具。

当前 bridge 使用简单可读的 JSON 帧，便于新手调试和串口抓包。
本文件只负责把 ROS 2 wheel setpoints 编码成带 CRC32 校验的字节串，
以及把 STM32 回传的 ACK/status 行解析成 Python 字典。
"""

import json
import zlib

from mars_rover_control.constants import MODE_VALUE_TO_NAME


def checksum_payload(payload: dict) -> int:
    """计算 payload 的 CRC32 校验值。

    编码时对 JSON key 排序，保证同一个 payload 在不同运行环境下得到一致校验值。
    """

    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return zlib.crc32(raw) & 0xFFFFFFFF


def encode_setpoints_frame(sequence_id: int, mode: int, enabled: bool, estop: bool, setpoints) -> bytes:
    """把四轮目标编码成发送给 STM32 的一行 JSON 字节串。

    参数：
    - sequence_id：命令序号，用于和 STM32 ACK 对齐。
    - mode：当前驱动模式编号。
    - enabled：是否允许底层真正执行硬件命令。
    - estop：软件急停状态。
    - setpoints：四个 WheelSetpoint 消息。
    """

    command_enabled = bool(enabled) and not bool(estop)
    payload = {
        "type": "SET_WHEEL_TARGETS",
        "sequence_id": int(sequence_id),
        "mode": MODE_VALUE_TO_NAME.get(int(mode), "UNKNOWN"),
        "mode_value": int(mode),
        "enabled": command_enabled,
        "estop": bool(estop),
        "wheels": [
            {
                "name": point.name,
                # 顶层未使能或急停时，轮组执行标志也必须为 false。
                "enabled": command_enabled and bool(point.enabled),
                "steering_angle_rad": float(point.steering_angle),
                "drive_velocity_mps": float(point.drive_velocity),
                "steering_velocity_limit_radps": float(point.steering_velocity_limit),
                "drive_acceleration_limit_mps2": float(point.drive_acceleration_limit),
            }
            for point in setpoints
        ],
    }
    frame = {"payload": payload, "checksum": checksum_payload(payload)}
    return (json.dumps(frame, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def decode_ack_line(line: bytes) -> dict:
    """解析 STM32 回传的一行 JSON，并校验 checksum。

    兼容两种格式：
    - {"payload": ..., "checksum": ...}
    - 直接回传 payload 字典
    """

    decoded = json.loads(line.decode("utf-8").strip())
    payload = decoded.get("payload", decoded)
    checksum = decoded.get("checksum")
    if checksum is not None and checksum != checksum_payload(payload):
        raise ValueError("serial frame checksum mismatch")
    return payload
