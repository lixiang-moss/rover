"""ROS 2 高层目标与 STM32 USB 串口之间的最终安全边界。"""

import math
import time

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import Bool

from mars_rover_control.constants import WHEEL_ORDER
from mars_rover_control.hardware_policy import (
    bridge_output_is_enabled,
    real_serial_command_is_allowed,
)
from mars_rover_control.serial_codec import (
    SerialFrameBuffer,
    decode_ack_line,
    encode_safe_stop_frame,
    encode_setpoints_frame,
)
from mars_rover_msgs.msg import (
    ControlState,
    Stm32Status,
    WheelSetpointArray,
    WheelState,
    WheelStateArray,
)

try:
    import serial
except ImportError:  # pragma: no cover - only happens outside the ROS runtime.
    serial = None


VALID_BRIDGE_MODES = {"dry_run", "serial_echo", "real_serial"}
VALID_HARDWARE_OUTPUT_MODES = {"single_wheel", "full_vehicle"}


class Stm32Bridge(Node):
    """编码四轮目标、强制最终联锁，并发布可审计的串口状态。"""

    def __init__(self) -> None:
        """初始化严格参数、串口状态、订阅器和监控定时器。"""

        super().__init__("stm32_bridge")
        self.declare_parameter("bridge_mode", "dry_run")
        self.declare_parameter("serial_port", "/dev/mars-rover-stm32")
        self.declare_parameter("baud_rate", 115200)
        self.declare_parameter("reconnect_interval_sec", 1.0)
        self.declare_parameter("status_timeout_sec", 0.5)
        self.declare_parameter("setpoint_timeout_sec", 0.25)
        self.declare_parameter("control_state_timeout_sec", 0.25)
        self.declare_parameter("hardware_output_mode", "single_wheel")
        self.declare_parameter("active_test_wheel", "front_left")
        self.declare_parameter("hard_max_steering_angle", 1.5708)
        self.declare_parameter("hard_max_drive_velocity", 0.10)
        self.declare_parameter("hard_max_steering_velocity", 0.30)
        self.declare_parameter("hard_max_drive_acceleration", 0.10)
        self._validate_parameters()

        self._serial = None
        self._last_rx_time = None
        self._last_status_rx_time = None
        self._last_setpoint_rx_time = None
        self._last_control_state_rx_time = None
        self._last_ack_sequence_id = 0
        self._last_sent_sequence_id = 0
        self._last_status_sequence_id = 0
        self._estop_active = False
        self._stm32_online_reported = False
        self._stm32_estop_active = False
        self._stm32_timeout = False
        self._stm32_ack_fault = False
        self._stm32_ack_fault_code = 0
        self._stm32_status_fault_code = 0
        self._serial_error = False
        self._rx_frame_buffer = SerialFrameBuffer()
        self._last_setpoints = None
        self._control_state = None
        self._last_status_message = ""
        self._last_reconnect_attempt = None
        self._failsafe_sent = False

        self.create_subscription(
            WheelSetpointArray, "/mars_rover/wheel_setpoints", self._on_setpoints, 1
        )
        self.create_subscription(Bool, "/mars_rover/emergency_stop", self._on_estop, 10)
        self.create_subscription(
            ControlState, "/mars_rover/control_state", self._on_control_state, 10
        )
        self._status_pub = self.create_publisher(
            Stm32Status, "/mars_rover/stm32/status", 10
        )
        self._states_pub = self.create_publisher(
            WheelStateArray, "/mars_rover/wheel_states", 10
        )
        self.create_timer(0.1, self._publish_status)
        self._open_serial_if_needed(force=True)

    def _validate_parameters(self) -> None:
        """启动时拒绝未知模式和无效安全边界。"""

        bridge_mode = str(self.get_parameter("bridge_mode").value)
        if bridge_mode not in VALID_BRIDGE_MODES:
            raise ValueError(f"unsupported bridge_mode: {bridge_mode}")
        output_mode = str(self.get_parameter("hardware_output_mode").value)
        if output_mode not in VALID_HARDWARE_OUTPUT_MODES:
            raise ValueError(f"unsupported hardware_output_mode: {output_mode}")
        if str(self.get_parameter("active_test_wheel").value) not in WHEEL_ORDER:
            raise ValueError("active_test_wheel is not a known wheel name")
        positive = (
            "baud_rate",
            "reconnect_interval_sec",
            "status_timeout_sec",
            "setpoint_timeout_sec",
            "control_state_timeout_sec",
            "hard_max_steering_angle",
            "hard_max_drive_velocity",
            "hard_max_steering_velocity",
            "hard_max_drive_acceleration",
        )
        for name in positive:
            if float(self.get_parameter(name).value) <= 0.0:
                raise ValueError(f"{name} must be greater than zero")

    def _open_serial_if_needed(self, *, force: bool = False) -> None:
        """按固定间隔打开或重新打开 USB 虚拟串口。"""

        mode = str(self.get_parameter("bridge_mode").value)
        if mode == "dry_run" or self._serial is not None:
            if mode == "dry_run" and force:
                self.get_logger().info("dry_run: serial port will not be opened")
            return
        if serial is None:
            self._serial_error = True
            self._set_status_message("pyserial is not available", level="error")
            return

        now = time.monotonic()
        interval = max(0.1, float(self.get_parameter("reconnect_interval_sec").value))
        if (
            not force
            and self._last_reconnect_attempt is not None
            and now - self._last_reconnect_attempt < interval
        ):
            return
        self._last_reconnect_attempt = now

        try:
            self._serial = serial.Serial(
                port=str(self.get_parameter("serial_port").value),
                baudrate=int(self.get_parameter("baud_rate").value),
                timeout=0.0,
                write_timeout=0.05,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False,
            )
            self._rx_frame_buffer = SerialFrameBuffer()
            self._last_rx_time = None
            self._last_status_rx_time = None
            self._stm32_online_reported = False
            self._stm32_estop_active = False
            self._stm32_timeout = False
            self._stm32_ack_fault = False
            self._stm32_ack_fault_code = 0
            self._stm32_status_fault_code = 0
            self._serial_error = False
            self._failsafe_sent = False
            self._last_status_message = "serial connected; waiting for STM32 status"
            self.get_logger().info(
                f"Opened STM32 serial port {self.get_parameter('serial_port').value}"
            )
        except (serial.SerialException, OSError) as exc:
            self._serial = None
            self._serial_error = True
            self._set_status_message(f"serial open failed: {exc}", level="warning")

    def _close_serial(self) -> None:
        """关闭当前串口句柄。"""

        connection = self._serial
        self._serial = None
        if connection is None:
            return
        try:
            connection.close()
        except (serial.SerialException, OSError):
            pass

    def _mark_serial_disconnected(self, message: str) -> None:
        """清除在线状态并等待定时重连。"""

        self._close_serial()
        self._serial_error = True
        self._stm32_online_reported = False
        self._last_status_rx_time = None
        self._failsafe_sent = False
        self._set_status_message(message, level="error")

    def _set_status_message(self, message: str, *, level: str = "none") -> None:
        """仅在文本变化时记录日志，避免 20 Hz 重复刷屏。"""

        changed = message != self._last_status_message
        self._last_status_message = message
        if not changed:
            return
        if level == "error":
            self.get_logger().error(message)
        elif level == "warning":
            self.get_logger().warning(message)
        elif level == "info":
            self.get_logger().info(message)

    def _on_estop(self, message: Bool) -> None:
        """直接急停通道；true 时不等待下一条轮组目标。"""

        self._estop_active = bool(message.data)
        if self._estop_active:
            self._send_safe_stop("software estop", estop=True)

    def _on_control_state(self, message: ControlState) -> None:
        """接收 safety_gate 的结构化授权状态。"""

        was_allowed = self._control_state_allows_output()
        self._control_state = message
        self._last_control_state_rx_time = self.get_clock().now()
        if was_allowed and not self._control_state_allows_output():
            self._send_safe_stop("ControlState revoked motion permission")

    def _on_setpoints(self, message: WheelSetpointArray) -> None:
        """验证、编码并发送一条四轮目标；任何拒绝都会主动发安全 STOP。"""

        self._last_setpoints = message
        self._last_setpoint_rx_time = self.get_clock().now()
        self._failsafe_sent = False
        if not self._setpoints_within_hard_limits(message):
            self._send_safe_stop("wheel setpoints rejected by hard limits")
            self._publish_echo_states(message, command_sent=False, output_enabled=False)
            return

        mode = str(self.get_parameter("bridge_mode").value)
        if mode == "real_serial" and not self._real_serial_command_is_allowed(message):
            self._send_safe_stop("wheel setpoints rejected by output profile")
            self._publish_echo_states(message, command_sent=False, output_enabled=False)
            return

        if mode == "dry_run":
            encode_setpoints_frame(
                message.sequence_id,
                message.mode,
                enabled=False,
                estop=self._estop_active,
                setpoints=message.setpoints,
            )
            self._publish_echo_states(message, command_sent=False, output_enabled=False)
            return

        if self._serial is None:
            self._open_serial_if_needed()
        if self._serial is None:
            self._publish_echo_states(message, command_sent=False, output_enabled=False)
            return

        output_enabled = bridge_output_is_enabled(
            bridge_mode=mode,
            control_state_allows_output=self._control_state_allows_output(),
            stm32_status_allows_output=self._stm32_status_allows_output(),
            estop_active=self._estop_active,
        )
        try:
            frame = encode_setpoints_frame(
                message.sequence_id,
                message.mode,
                enabled=output_enabled,
                estop=self._estop_active,
                setpoints=message.setpoints,
            )
            self._write_frame(frame, int(message.sequence_id))
            self._read_available_lines()
        except ValueError as exc:
            self._send_safe_stop(f"serial encoding rejected setpoints: {exc}")
            self._publish_echo_states(message, command_sent=False, output_enabled=False)
            return
        except (serial.SerialException, OSError) as exc:
            self._mark_serial_disconnected(f"serial write/read failed: {exc}")
            self._publish_echo_states(message, command_sent=False, output_enabled=False)
            return

        if mode == "serial_echo":
            self._set_status_message("serial_echo: command sent with output forcibly disabled")
        elif not output_enabled:
            self._set_status_message(
                "real_serial: command sent disabled; check arm, ControlState and STM32 status"
            )
        self._publish_echo_states(
            message, command_sent=True, output_enabled=output_enabled
        )

    def _write_frame(self, frame: bytes, sequence_id: int) -> None:
        """完整写入一帧并记录最后实际发送序号。"""

        written = self._serial.write(frame)
        if written != len(frame):
            raise serial.SerialTimeoutException(
                f"partial serial write: {written}/{len(frame)} bytes"
            )
        self._last_sent_sequence_id = int(sequence_id) & 0xFFFFFFFF

    def _send_safe_stop(self, reason: str, *, estop: bool = False) -> None:
        """发送独立于上游消息内容的全局禁用 STOP 帧。"""

        mode = str(self.get_parameter("bridge_mode").value)
        self._set_status_message(f"safe STOP: {reason}", level="warning")
        if mode == "dry_run":
            self._failsafe_sent = True
            return
        if self._serial is None:
            self._open_serial_if_needed()
        if self._serial is None:
            return
        sequence_id = (self._last_sent_sequence_id + 1) & 0xFFFFFFFF
        try:
            self._write_frame(
                encode_safe_stop_frame(sequence_id, estop=estop), sequence_id
            )
            self._failsafe_sent = True
        except (serial.SerialException, OSError) as exc:
            self._mark_serial_disconnected(f"safe STOP write failed: {exc}")

    def _setpoints_within_hard_limits(self, message: WheelSetpointArray) -> bool:
        """在串口边界重新检查轮序、有限值和绝对硬上限。"""

        points = list(message.setpoints)
        if tuple(point.name for point in points) != WHEEL_ORDER:
            return False
        angle_limit = float(self.get_parameter("hard_max_steering_angle").value)
        drive_limit = float(self.get_parameter("hard_max_drive_velocity").value)
        steering_velocity_limit = float(
            self.get_parameter("hard_max_steering_velocity").value
        )
        acceleration_limit = float(
            self.get_parameter("hard_max_drive_acceleration").value
        )
        for point in points:
            values = (
                point.steering_angle,
                point.drive_velocity,
                point.steering_velocity_limit,
                point.drive_acceleration_limit,
            )
            if not all(math.isfinite(float(value)) for value in values):
                return False
            if abs(float(point.steering_angle)) > angle_limit + 1e-9:
                return False
            if abs(float(point.drive_velocity)) > drive_limit + 1e-9:
                return False
            if not 0.0 <= float(point.steering_velocity_limit) <= steering_velocity_limit:
                return False
            if not 0.0 <= float(point.drive_acceleration_limit) <= acceleration_limit:
                return False
        return True

    def _real_serial_command_is_allowed(self, message: WheelSetpointArray) -> bool:
        """验证当前 launch profile 是否允许该模式和轮组组合。"""

        return real_serial_command_is_allowed(
            int(message.mode),
            message.setpoints,
            hardware_output_mode=str(self.get_parameter("hardware_output_mode").value),
            active_test_wheel=str(self.get_parameter("active_test_wheel").value),
        )

    def _control_state_is_fresh(self) -> bool:
        """判断 safety_gate 的结构化状态是否仍在更新。"""

        if self._last_control_state_rx_time is None:
            return False
        age = (
            self.get_clock().now() - self._last_control_state_rx_time
        ).nanoseconds / 1e9
        return age <= float(self.get_parameter("control_state_timeout_sec").value)

    def _control_state_allows_output(self) -> bool:
        """只有新鲜、已 arm 且明确允许运动的 ControlState 才能执行。"""

        return (
            self._control_state_is_fresh()
            and self._control_state is not None
            and bool(self._control_state.armed)
            and bool(self._control_state.motion_allowed)
            and not bool(self._control_state.estop_latched)
            and not bool(self._control_state.fault_latched)
        )

    def _read_available_lines(self) -> None:
        """在短时间窗口内读取并重组 ACK/STATUS 帧。"""

        if self._serial is None:
            return
        deadline = time.monotonic() + 0.01
        while time.monotonic() < deadline and self._serial.in_waiting:
            chunk = self._serial.read(self._serial.in_waiting)
            if not chunk:
                break
            lines, dropped = self._rx_frame_buffer.feed(chunk)
            if dropped:
                self._set_status_message(
                    f"discarded {dropped} STM32 frame(s) exceeding 512 bytes",
                    level="warning",
                )
            for line in lines:
                self._handle_response_line(line)

    def _stm32_status_allows_output(self) -> bool:
        """仅在新鲜、在线且无联锁的 STATUS 下允许真实输出。"""

        if self._last_status_rx_time is None or not self._stm32_online_reported:
            return False
        age = (self.get_clock().now() - self._last_status_rx_time).nanoseconds / 1e9
        status_is_fresh = age <= float(self.get_parameter("status_timeout_sec").value)
        status_has_fault = self._stm32_status_fault_code != 0 or self._stm32_ack_fault
        return (
            status_is_fresh
            and not self._stm32_estop_active
            and not self._stm32_timeout
            and not status_has_fault
        )

    def _handle_response_line(self, line: bytes) -> None:
        """严格解析一条 ACK 或 STATUS，并分别维护序号语义。"""

        try:
            payload = decode_ack_line(line)
        except (ValueError, UnicodeDecodeError) as exc:
            self._set_status_message(f"invalid STM32 frame: {exc}", level="warning")
            return
        self._last_rx_time = self.get_clock().now()
        self._serial_error = False
        if payload["t"] == "A":
            self._last_ack_sequence_id = int(payload["q"])
            self._stm32_ack_fault = payload["ok"] == 0 or payload["fc"] != 0
            self._stm32_ack_fault_code = int(payload["fc"])
            if self._stm32_ack_fault:
                self._set_status_message(
                    f"STM32 rejected q={payload['q']}, fc={payload['fc']}",
                    level="warning",
                )
            else:
                self._set_status_message(f"STM32 ACK q={payload['q']}")
        else:
            self._last_status_rx_time = self._last_rx_time
            self._last_status_sequence_id = int(payload["q"])
            self._stm32_online_reported = bool(payload["on"])
            self._stm32_estop_active = bool(payload["es"])
            self._stm32_timeout = bool(payload["to"])
            self._stm32_status_fault_code = int(payload["fc"])
            self._set_status_message(
                f"STM32 STATUS q={payload['q']}, on={payload['on']}, "
                f"es={payload['es']}, to={payload['to']}, fc={payload['fc']}"
            )

    def _publish_echo_states(
        self,
        setpoints: WheelSetpointArray,
        *,
        command_sent: bool,
        output_enabled: bool,
    ) -> None:
        """发布目标值回显，并明确区分是否发送和是否允许执行。"""

        message = WheelStateArray()
        message.stamp = self.get_clock().now().to_msg()
        message.last_command_sequence_id = setpoints.sequence_id
        message.command_sent = command_sent
        message.output_enabled = output_enabled
        states = []
        for point in setpoints.setpoints:
            state = WheelState()
            state.name = point.name
            state.online = False
            state.enabled = bool(output_enabled and point.enabled)
            state.steering_angle = point.steering_angle
            state.drive_velocity = point.drive_velocity
            state.feedback_is_real = False
            state.fault = False
            state.fault_code = 0
            states.append(state)
        message.states = states
        self._states_pub.publish(message)

    def _upstream_setpoints_are_fresh(self) -> bool:
        """检查运动学节点是否仍以预期频率提供目标。"""

        if self._last_setpoint_rx_time is None:
            return False
        age = (
            self.get_clock().now() - self._last_setpoint_rx_time
        ).nanoseconds / 1e9
        return age <= float(self.get_parameter("setpoint_timeout_sec").value)

    def _publish_status(self) -> None:
        """读取串口、执行上游断流保护并发布 bridge 状态。"""

        mode = str(self.get_parameter("bridge_mode").value)
        if mode != "dry_run":
            if self._serial is None:
                self._open_serial_if_needed()
            if self._serial is not None:
                try:
                    self._read_available_lines()
                except (serial.SerialException, OSError) as exc:
                    self._mark_serial_disconnected(f"serial read failed: {exc}")
            if not self._upstream_setpoints_are_fresh() and not self._failsafe_sent:
                self._send_safe_stop("wheel setpoint stream timed out")

        status = Stm32Status()
        status.stamp = self.get_clock().now().to_msg()
        now = self.get_clock().now()
        last_rx_age = (
            float("inf")
            if self._last_rx_time is None
            else (now - self._last_rx_time).nanoseconds / 1e9
        )
        last_status_age = (
            float("inf")
            if self._last_status_rx_time is None
            else (now - self._last_status_rx_time).nanoseconds / 1e9
        )
        pi_status_timeout = last_status_age > float(
            self.get_parameter("status_timeout_sec").value
        )
        timeout = pi_status_timeout or self._stm32_timeout
        fault_code = self._stm32_status_fault_code or self._stm32_ack_fault_code
        fault = self._stm32_status_fault_code != 0 or self._stm32_ack_fault

        status.online = mode != "dry_run" and (
            self._serial is not None
            and not pi_status_timeout
            and self._stm32_online_reported
        )
        status.last_rx_age = last_rx_age
        status.last_ack_sequence_id = self._last_ack_sequence_id
        status.last_sent_sequence_id = self._last_sent_sequence_id
        status.last_status_sequence_id = self._last_status_sequence_id
        status.serial_connected = self._serial is not None
        status.timeout = False if mode == "dry_run" else timeout
        status.estop_active = self._estop_active or self._stm32_estop_active
        status.fault = fault
        status.fault_code = fault_code
        status.serial_error = mode != "dry_run" and (
            self._serial is None or self._serial_error
        )
        status.bridge_mode = mode
        status.control_state_connected = self._control_state_is_fresh()
        status.message = self._status_message(mode)
        self._status_pub.publish(status)

    def _status_message(self, mode: str) -> str:
        """生成人可读状态文本。"""

        if mode == "dry_run":
            return "dry_run: no STM32 connection; wheel_states are target echoes"
        return self._last_status_message or "waiting for STM32 status"

    def destroy_node(self) -> bool:
        """节点退出前关闭串口。"""

        self._close_serial()
        return super().destroy_node()


def main(args=None) -> None:
    """启动 Stm32Bridge 并进入 ROS 2 spin。"""

    rclpy.init(args=args)
    node = Stm32Bridge()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    except Exception:
        if rclpy.ok():
            raise
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
