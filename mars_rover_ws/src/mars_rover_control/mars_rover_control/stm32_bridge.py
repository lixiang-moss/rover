"""STM32 serial bridge with safe dry-run behavior."""

import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool

from mars_rover_control.constants import MODE_RAW_WHEEL_TEST, WHEEL_ORDER
from mars_rover_control.serial_codec import decode_ack_line, encode_setpoints_frame
from mars_rover_msgs.msg import Stm32Status, WheelSetpointArray, WheelState, WheelStateArray

try:
    import serial
except ImportError:  # pragma: no cover - only happens outside the ROS Docker image.
    serial = None


class Stm32Bridge(Node):
    def __init__(self) -> None:
        super().__init__("stm32_bridge")
        self.declare_parameter("bridge_mode", "dry_run")
        self.declare_parameter("serial_port", "/dev/mars_stm32")
        self.declare_parameter("baud_rate", 115200)
        self.declare_parameter("status_timeout_sec", 1.0)
        self.declare_parameter("require_enable_for_real_serial", True)
        self.declare_parameter("hardware_enable", False)
        self.declare_parameter("active_test_wheel", "front_left")

        self._serial = None
        self._last_rx_time = None
        self._last_ack_sequence_id = 0
        self._estop_active = False
        self._last_setpoints = None
        self._last_status_message = ""

        self.create_subscription(WheelSetpointArray, "/mars_rover/wheel_setpoints", self._on_setpoints, 10)
        self.create_subscription(Bool, "/mars_rover/emergency_stop", self._on_estop, 10)
        self._status_pub = self.create_publisher(Stm32Status, "/mars_rover/stm32/status", 10)
        self._states_pub = self.create_publisher(WheelStateArray, "/mars_rover/wheel_states", 10)
        self.create_timer(0.2, self._publish_status)

        self._open_serial_if_needed()

    def _open_serial_if_needed(self) -> None:
        mode = str(self.get_parameter("bridge_mode").value)
        if mode == "dry_run":
            self.get_logger().info("STM32 bridge running in dry_run mode; serial port will not be opened.")
            return
        if serial is None:
            self._last_status_message = "pyserial is not available"
            self.get_logger().error(self._last_status_message)
            return
        try:
            self._serial = serial.Serial(
                port=str(self.get_parameter("serial_port").value),
                baudrate=int(self.get_parameter("baud_rate").value),
                timeout=0.0,
                write_timeout=0.05,
            )
            self._last_status_message = "serial connected"
            self.get_logger().info(
                f"Opened STM32 serial port {self.get_parameter('serial_port').value}"
            )
        except serial.SerialException as exc:
            self._serial = None
            self._last_status_message = f"serial open failed: {exc}"
            self.get_logger().error(self._last_status_message)

    def _on_estop(self, message: Bool) -> None:
        self._estop_active = bool(message.data)

    def _on_setpoints(self, message: WheelSetpointArray) -> None:
        self._last_setpoints = message
        mode = str(self.get_parameter("bridge_mode").value)

        if mode == "real_serial" and not self._real_serial_command_is_allowed(message):
            self._last_status_message = "real_serial command blocked by safety policy"
            self.get_logger().error(self._last_status_message)
            self._publish_echo_states(message)
            return

        if mode == "dry_run":
            frame = encode_setpoints_frame(
                message.sequence_id,
                message.mode,
                enabled=False,
                estop=self._estop_active,
                setpoints=message.setpoints,
            )
            self.get_logger().debug(frame.decode("utf-8").strip())
            self._last_ack_sequence_id = message.sequence_id
            self._publish_echo_states(message)
            return

        if self._serial is None:
            self._last_status_message = "serial unavailable"
            self._publish_echo_states(message)
            return

        hardware_enable = bool(self.get_parameter("hardware_enable").value)
        frame = encode_setpoints_frame(
            message.sequence_id,
            message.mode,
            enabled=hardware_enable and not self._estop_active,
            estop=self._estop_active,
            setpoints=message.setpoints,
        )
        try:
            self._serial.write(frame)
            self._read_available_lines()
        except serial.SerialException as exc:
            self._last_status_message = f"serial write/read failed: {exc}"
            self.get_logger().error(self._last_status_message)

        self._publish_echo_states(message)

    def _real_serial_command_is_allowed(self, message: WheelSetpointArray) -> bool:
        if bool(self.get_parameter("require_enable_for_real_serial").value) and not bool(
            self.get_parameter("hardware_enable").value
        ):
            return False
        if int(message.mode) != MODE_RAW_WHEEL_TEST:
            return False
        active_wheel = str(self.get_parameter("active_test_wheel").value)
        for point in message.setpoints:
            if point.name == active_wheel:
                if not point.enabled:
                    return False
            elif point.enabled or abs(point.drive_velocity) > 1e-9:
                return False
        return active_wheel == "front_left"

    def _read_available_lines(self) -> None:
        if self._serial is None:
            return
        deadline = time.monotonic() + 0.01
        while time.monotonic() < deadline and self._serial.in_waiting:
            line = self._serial.readline()
            if not line:
                break
            try:
                payload = decode_ack_line(line)
            except (ValueError, UnicodeDecodeError) as exc:
                self._last_status_message = f"invalid STM32 frame: {exc}"
                continue
            self._last_rx_time = self.get_clock().now()
            if "sequence_id" in payload:
                self._last_ack_sequence_id = int(payload["sequence_id"])
            elif "last_ack_sequence_id" in payload:
                self._last_ack_sequence_id = int(payload["last_ack_sequence_id"])
            self._last_status_message = str(payload.get("message", "ack"))

    def _publish_echo_states(self, setpoints: WheelSetpointArray) -> None:
        message = WheelStateArray()
        message.stamp = self.get_clock().now().to_msg()
        message.last_command_sequence_id = setpoints.sequence_id
        states = []
        for point in setpoints.setpoints:
            state = WheelState()
            state.name = point.name
            state.online = False
            state.enabled = point.enabled
            state.steering_angle = point.steering_angle
            state.drive_velocity = point.drive_velocity
            state.feedback_is_real = False
            state.fault = False
            state.fault_code = 0
            states.append(state)
        message.states = states
        self._states_pub.publish(message)

    def _publish_status(self) -> None:
        status = Stm32Status()
        status.stamp = self.get_clock().now().to_msg()
        mode = str(self.get_parameter("bridge_mode").value)
        now = self.get_clock().now()
        if self._last_rx_time is None:
            last_rx_age = float("inf")
        else:
            last_rx_age = (now - self._last_rx_time).nanoseconds / 1e9
        timeout = last_rx_age > float(self.get_parameter("status_timeout_sec").value)

        status.online = mode == "dry_run" or (self._serial is not None and not timeout)
        status.last_rx_age = last_rx_age
        status.last_ack_sequence_id = self._last_ack_sequence_id
        status.serial_connected = self._serial is not None
        status.timeout = False if mode == "dry_run" else timeout
        status.estop_active = self._estop_active
        status.serial_error = mode != "dry_run" and self._serial is None
        status.message = self._status_message(mode)
        self._status_pub.publish(status)

    def _status_message(self, mode: str) -> str:
        if mode == "dry_run":
            return "dry_run: no STM32 hardware connection required; wheel_states are target echoes"
        return self._last_status_message or "waiting for STM32 status"

    def destroy_node(self) -> bool:
        if self._serial is not None:
            self._serial.close()
        return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = Stm32Bridge()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
