"""Pi 与 STM32 之间的紧凑串口协议编解码工具。

每帧格式为 ``<紧凑 JSON>*<8 位大写十六进制 CRC32>\n``。CRC32 只覆盖
星号前的原始 UTF-8 JSON 字节。协议固定使用四轮顺序，避免两端因字段名或
轮组排序不同而把目标发送给错误的执行器。
"""

import json
import math
import zlib

from mars_rover_control.constants import WHEEL_ORDER


PROTOCOL_VERSION = 1
MAX_FRAME_BYTES = 512
UINT32_MAX = 0xFFFFFFFF
FRAME_TYPES = {"W", "A", "S"}


class SerialFrameBuffer:
    """把任意串口字节分片重组为以换行结束的完整帧。"""

    def __init__(self) -> None:
        """创建空接收缓冲区。"""

        self._buffer = bytearray()
        self._discarding_until_newline = False

    def feed(self, chunk: bytes) -> tuple[list[bytes], int]:
        """加入新字节，返回完整帧列表和被丢弃的超长帧数量。"""

        if not isinstance(chunk, bytes):
            raise ValueError("serial chunk must be bytes")
        self._buffer.extend(chunk)
        frames = []
        dropped = 0

        if self._discarding_until_newline:
            newline_index = self._buffer.find(b"\n")
            if newline_index < 0:
                self._buffer.clear()
                return frames, dropped
            del self._buffer[: newline_index + 1]
            self._discarding_until_newline = False

        while True:
            newline_index = self._buffer.find(b"\n")
            if newline_index < 0:
                break
            frame = bytes(self._buffer[: newline_index + 1])
            del self._buffer[: newline_index + 1]
            if len(frame) > MAX_FRAME_BYTES:
                dropped += 1
            else:
                frames.append(frame)

        if len(self._buffer) > MAX_FRAME_BYTES:
            self._buffer.clear()
            self._discarding_until_newline = True
            dropped += 1
        return frames, dropped


def _compact_json_bytes(payload: dict) -> bytes:
    """把字典编码成确定性的紧凑 UTF-8 JSON 字节。"""

    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def checksum_payload(payload: dict) -> int:
    """计算按本协议规范化编码后的 payload CRC32。"""

    return zlib.crc32(_compact_json_bytes(payload)) & UINT32_MAX


def _require_uint32(value, field_name: str) -> None:
    """检查字段是否为无符号 32 位整数。"""

    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= UINT32_MAX:
        raise ValueError(f"{field_name} must be an unsigned 32-bit integer")


def _require_binary(value, field_name: str) -> None:
    """检查协议布尔字段是否使用整数 0 或 1。"""

    if isinstance(value, bool) or not isinstance(value, int) or value not in (0, 1):
        raise ValueError(f"{field_name} must be 0 or 1")


def _require_finite_number(value, field_name: str) -> None:
    """拒绝布尔值、NaN 和无穷大，防止底层收到不可执行目标。"""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be numeric")
    if not math.isfinite(float(value)):
        raise ValueError(f"{field_name} must be finite")


def _validate_payload(payload: dict) -> None:
    """按帧类型严格校验字段集合、数据类型和轮组数量。"""

    if not isinstance(payload, dict):
        raise ValueError("serial frame payload must be a JSON object")
    if payload.get("v") != PROTOCOL_VERSION:
        raise ValueError("unsupported serial protocol version")

    frame_type = payload.get("t")
    if frame_type not in FRAME_TYPES:
        raise ValueError("unsupported serial frame type")
    _require_uint32(payload.get("q"), "q")

    if frame_type == "W":
        required = {"v", "t", "q", "m", "e", "s", "w"}
        if set(payload) != required:
            raise ValueError("W frame fields do not match protocol v1")
        if isinstance(payload["m"], bool) or not isinstance(payload["m"], int):
            raise ValueError("m must be an integer drive mode")
        if payload["m"] not in (0, 1, 2, 3):
            raise ValueError("m is not a supported drive mode")
        _require_binary(payload["e"], "e")
        _require_binary(payload["s"], "s")
        wheels = payload["w"]
        if not isinstance(wheels, list) or len(wheels) != len(WHEEL_ORDER):
            raise ValueError("w must contain exactly four wheel tuples")
        for wheel_index, wheel in enumerate(wheels):
            if not isinstance(wheel, list) or len(wheel) != 5:
                raise ValueError(f"w[{wheel_index}] must contain exactly five values")
            _require_binary(wheel[0], f"w[{wheel_index}][0]")
            for value_index in range(1, 5):
                _require_finite_number(wheel[value_index], f"w[{wheel_index}][{value_index}]")
            if wheel[3] < 0 or wheel[4] < 0:
                raise ValueError(f"w[{wheel_index}] limits must be non-negative")
        return

    if frame_type == "A":
        if set(payload) != {"v", "t", "q", "ok", "fc"}:
            raise ValueError("A frame fields do not match protocol v1")
        _require_binary(payload["ok"], "ok")
        _require_uint32(payload["fc"], "fc")
        return

    if set(payload) != {"v", "t", "q", "on", "es", "to", "fc"}:
        raise ValueError("S frame fields do not match protocol v1")
    _require_binary(payload["on"], "on")
    _require_binary(payload["es"], "es")
    _require_binary(payload["to"], "to")
    _require_uint32(payload["fc"], "fc")


def encode_protocol_frame(payload: dict) -> bytes:
    """校验并编码任意协议 v1 帧，主要供命令和测试使用。"""

    _validate_payload(payload)
    raw_json = _compact_json_bytes(payload)
    checksum = zlib.crc32(raw_json) & UINT32_MAX
    frame = raw_json + b"*" + f"{checksum:08X}".encode("ascii") + b"\n"
    if len(frame) > MAX_FRAME_BYTES:
        raise ValueError(f"serial frame exceeds {MAX_FRAME_BYTES} bytes")
    return frame


def encode_setpoints_frame(
    sequence_id: int, mode: int, enabled: bool, estop: bool, setpoints
) -> bytes:
    """把固定顺序的四轮目标编码成一条 W 命令帧。

    ``enabled`` 为假或急停激活时，顶层执行标志和每个轮组的执行标志都为 0。
    ``sequence_id`` 按 uint32 回绕，便于节点长期运行。
    """

    points = list(setpoints)
    if len(points) != len(WHEEL_ORDER):
        raise ValueError("setpoints must contain exactly four wheels")
    names = tuple(point.name for point in points)
    if names != WHEEL_ORDER:
        raise ValueError(f"setpoints must use fixed wheel order: {WHEEL_ORDER}")

    command_enabled = bool(enabled) and not bool(estop)
    wheels = []
    for point in points:
        wheels.append(
            [
                int(command_enabled and bool(point.enabled)),
                float(point.steering_angle),
                float(point.drive_velocity),
                float(point.steering_velocity_limit),
                float(point.drive_acceleration_limit),
            ]
        )

    payload = {
        "e": int(command_enabled),
        "m": int(mode),
        "q": int(sequence_id) & UINT32_MAX,
        "s": int(bool(estop)),
        "t": "W",
        "v": PROTOCOL_VERSION,
        "w": wheels,
    }
    return encode_protocol_frame(payload)


def encode_safe_stop_frame(sequence_id: int, *, estop: bool = False) -> bytes:
    """生成不依赖上游消息内容的全局禁用 STOP 帧。"""

    payload = {
        "e": 0,
        "m": 0,
        "q": int(sequence_id) & UINT32_MAX,
        "s": int(bool(estop)),
        "t": "W",
        "v": PROTOCOL_VERSION,
        "w": [[0, 0.0, 0.0, 0.0, 0.0] for _ in WHEEL_ORDER],
    }
    return encode_protocol_frame(payload)


def decode_protocol_frame(line: bytes) -> dict:
    """解析一条完整协议帧，校验长度、CRC32 和帧字段。"""

    if not isinstance(line, bytes):
        raise ValueError("serial frame must be bytes")
    if len(line) > MAX_FRAME_BYTES:
        raise ValueError(f"serial frame exceeds {MAX_FRAME_BYTES} bytes")

    stripped = line.rstrip(b"\r\n")
    try:
        raw_json, raw_checksum = stripped.rsplit(b"*", 1)
    except ValueError as exc:
        raise ValueError("serial frame separator is missing") from exc
    if not raw_json:
        raise ValueError("serial frame JSON is empty")
    if len(raw_checksum) != 8:
        raise ValueError("serial frame CRC32 must contain eight hex digits")
    if any(byte not in b"0123456789ABCDEF" for byte in raw_checksum):
        raise ValueError("serial frame CRC32 must use uppercase hexadecimal")
    try:
        expected_checksum = int(raw_checksum.decode("ascii"), 16)
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("serial frame CRC32 is not hexadecimal") from exc

    actual_checksum = zlib.crc32(raw_json) & UINT32_MAX
    if actual_checksum != expected_checksum:
        raise ValueError("serial frame checksum mismatch")

    payload = json.loads(raw_json.decode("utf-8"))
    _validate_payload(payload)
    return payload


def decode_ack_line(line: bytes) -> dict:
    """兼容现有 bridge 调用名，解析 ACK 或 STATUS 紧凑帧。"""

    payload = decode_protocol_frame(line)
    if payload["t"] not in {"A", "S"}:
        raise ValueError("STM32 response must be an ACK or STATUS frame")
    return payload
