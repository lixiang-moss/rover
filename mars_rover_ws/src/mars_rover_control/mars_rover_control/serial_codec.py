"""Line-delimited JSON serial frame codec for the first ROS-side bridge."""

import json
import zlib

from mars_rover_control.constants import MODE_VALUE_TO_NAME


def checksum_payload(payload: dict) -> int:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return zlib.crc32(raw) & 0xFFFFFFFF


def encode_setpoints_frame(sequence_id: int, mode: int, enabled: bool, estop: bool, setpoints) -> bytes:
    payload = {
        "type": "SET_WHEEL_TARGETS",
        "sequence_id": int(sequence_id),
        "mode": MODE_VALUE_TO_NAME.get(int(mode), "UNKNOWN"),
        "mode_value": int(mode),
        "enabled": bool(enabled),
        "estop": bool(estop),
        "wheels": [
            {
                "name": point.name,
                "enabled": bool(point.enabled),
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
    decoded = json.loads(line.decode("utf-8").strip())
    payload = decoded.get("payload", decoded)
    checksum = decoded.get("checksum")
    if checksum is not None and checksum != checksum_payload(payload):
        raise ValueError("serial frame checksum mismatch")
    return payload
