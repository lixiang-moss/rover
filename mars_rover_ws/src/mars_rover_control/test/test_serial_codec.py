from types import SimpleNamespace

from mars_rover_control.serial_codec import decode_ack_line, encode_setpoints_frame


def make_point(name, enabled):
    return SimpleNamespace(
        name=name,
        enabled=enabled,
        steering_angle=0.1,
        drive_velocity=0.02,
        steering_velocity_limit=0.3,
        drive_acceleration_limit=0.1,
    )


def test_setpoints_frame_round_trips_as_json_payload():
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
    assert payload["wheels"][0]["name"] == "front_left"
    assert payload["wheels"][0]["enabled"] is True
    assert payload["wheels"][1]["enabled"] is False
