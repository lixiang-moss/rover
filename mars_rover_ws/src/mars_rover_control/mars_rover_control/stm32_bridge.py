"""STM32 串口桥接节点。

本节点是 ROS 2 高层控制与 STM32 低层控制之间的边界：
它订阅 `/mars_rover/wheel_setpoints`，根据 bridge_mode 决定 dry-run、串口 echo
或真实串口发送，并发布 `/mars_rover/stm32/status` 与 `/mars_rover/wheel_states`。

重要安全原则：
- 默认 dry_run，不打开真实串口。
- real_serial 模式必须显式 hardware_enable。
- real_serial 可通过 hardware_output_mode 在单轮测试和四轮整车输出之间切换。
"""

import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool

from mars_rover_control.hardware_policy import real_serial_command_is_allowed
from mars_rover_control.serial_codec import decode_ack_line, encode_setpoints_frame
from mars_rover_msgs.msg import Stm32Status, WheelSetpointArray, WheelState, WheelStateArray

try:
    import serial
except ImportError:  # pragma: no cover - only happens outside the ROS Docker image.
    serial = None


class Stm32Bridge(Node):
    """ROS 2 节点：把四轮目标转换为 Pi->STM32 串口帧，并发布底层状态。"""

    def __init__(self) -> None:
        """初始化参数、订阅器、发布器、状态定时器，并按模式打开串口。"""

        super().__init__("stm32_bridge")
        self.declare_parameter("bridge_mode", "dry_run")
        self.declare_parameter("serial_port", "/dev/mars_stm32")
        self.declare_parameter("baud_rate", 115200)
        self.declare_parameter("status_timeout_sec", 1.0)
        self.declare_parameter("require_enable_for_real_serial", True)
        self.declare_parameter("hardware_enable", False)
        self.declare_parameter("hardware_output_mode", "single_wheel")
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
        """根据 bridge_mode 决定是否打开串口。

        dry_run 模式不访问硬件；serial_echo 和 real_serial 模式会尝试打开
        serial_port 指定的设备。
        """

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
        """接收软件急停状态，并在下一次发送帧时传给 STM32。"""

        self._estop_active = bool(message.data)

    def _on_setpoints(self, message: WheelSetpointArray) -> None:
        """处理新的四轮目标。

        dry_run 时只打印/回显；真实串口时先做安全策略检查，再编码并写入串口。
        无论是否真正发送，都会发布 wheel_states，便于 RViz 显示目标状态。
        """

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

        require_enable = bool(self.get_parameter("require_enable_for_real_serial").value)
        hardware_enable = bool(self.get_parameter("hardware_enable").value)
        command_enabled = (hardware_enable or not require_enable) and not self._estop_active
        frame = encode_setpoints_frame(
            message.sequence_id,
            message.mode,
            enabled=command_enabled,
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
        """检查 real_serial 模式下是否允许执行当前命令。

        single_wheel 用于真实单轮测试；full_vehicle 用于真实四轮手动控制。
        hardware_enable 只决定串口帧中的 enabled 字段是否为 true，不再把
        四轮 real_serial 命令锁死为单轮测试。
        """

        return real_serial_command_is_allowed(
            int(message.mode),
            message.setpoints,
            hardware_output_mode=str(self.get_parameter("hardware_output_mode").value),
            active_test_wheel=str(self.get_parameter("active_test_wheel").value),
        )

    def _read_available_lines(self) -> None:
        """在短时间窗口内读取 STM32 回传的 ACK/status 行。

        该函数不会长时间阻塞 ROS 2 节点，只读取当前串口缓冲区中已经到达的数据。
        """

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
        """把最新目标值回显为 WheelStateArray。

        这是 dry-run/未接真实反馈时的可视化方案。
        feedback_is_real=false 明确表示这些状态不是硬件真实反馈。
        """

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
        """周期性发布 STM32 bridge 状态。

        状态包括是否在线、最近 ACK 序号、串口是否连接、是否超时、是否急停等。
        """

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
        """根据当前 bridge 模式生成人可读状态说明。"""

        if mode == "dry_run":
            return "dry_run: no STM32 hardware connection required; wheel_states are target echoes"
        return self._last_status_message or "waiting for STM32 status"

    def destroy_node(self) -> bool:
        """节点销毁时关闭串口，避免设备句柄泄漏。"""

        if self._serial is not None:
            self._serial.close()
        return super().destroy_node()


def main(args=None) -> None:
    """ROS 2 可执行入口：启动 Stm32Bridge 并进入 spin 循环。"""

    rclpy.init(args=args)
    node = Stm32Bridge()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
