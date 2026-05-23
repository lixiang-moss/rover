"""Safety gate for incoming velocity commands."""

import copy

from geometry_msgs.msg import Twist
import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String

from mars_rover_msgs.msg import Stm32Status


def _zero_twist() -> Twist:
    return Twist()


def _clamp(value: float, limit: float) -> float:
    return min(max(value, -limit), limit)


class SafetyGate(Node):
    def __init__(self) -> None:
        super().__init__("safety_gate")
        self.declare_parameter("cmd_timeout_sec", 0.5)
        self.declare_parameter("max_linear_velocity", 0.10)
        self.declare_parameter("max_angular_velocity", 0.30)
        self.declare_parameter("bridge_mode", "dry_run")
        self.declare_parameter("require_stm32_online_for_real_serial", True)
        self.declare_parameter("publish_rate_hz", 20.0)

        self._last_cmd = _zero_twist()
        self._last_cmd_time = None
        self._estop_active = False
        self._stm32_online = False
        self._last_reason = "waiting for /cmd_vel"

        self._cmd_sub = self.create_subscription(Twist, "/cmd_vel", self._on_cmd_vel, 10)
        self._estop_sub = self.create_subscription(Bool, "/mars_rover/emergency_stop", self._on_estop, 10)
        self._status_sub = self.create_subscription(
            Stm32Status, "/mars_rover/stm32/status", self._on_stm32_status, 10
        )
        self._safe_pub = self.create_publisher(Twist, "/mars_rover/safe_cmd_vel", 10)
        self._state_pub = self.create_publisher(String, "/mars_rover/safety_state", 10)

        period = 1.0 / float(self.get_parameter("publish_rate_hz").value)
        self.create_timer(period, self._publish_safe_command)

    def _on_cmd_vel(self, message: Twist) -> None:
        self._last_cmd = copy.deepcopy(message)
        self._last_cmd_time = self.get_clock().now()

    def _on_estop(self, message: Bool) -> None:
        self._estop_active = bool(message.data)

    def _on_stm32_status(self, message: Stm32Status) -> None:
        self._stm32_online = bool(message.online)

    def _command_timed_out(self) -> bool:
        if self._last_cmd_time is None:
            return True
        timeout = float(self.get_parameter("cmd_timeout_sec").value)
        age = (self.get_clock().now() - self._last_cmd_time).nanoseconds / 1e9
        return age > timeout

    def _publish_safe_command(self) -> None:
        safe = _zero_twist()
        reason = "ok"
        bridge_mode = str(self.get_parameter("bridge_mode").value)

        if self._command_timed_out():
            reason = "cmd_timeout"
        elif self._estop_active:
            reason = "software_estop"
        elif (
            bridge_mode == "real_serial"
            and bool(self.get_parameter("require_stm32_online_for_real_serial").value)
            and not self._stm32_online
        ):
            reason = "stm32_offline"
        else:
            linear_limit = float(self.get_parameter("max_linear_velocity").value)
            angular_limit = float(self.get_parameter("max_angular_velocity").value)
            safe.linear.x = _clamp(self._last_cmd.linear.x, linear_limit)
            safe.linear.y = _clamp(self._last_cmd.linear.y, linear_limit)
            safe.linear.z = 0.0
            safe.angular.x = 0.0
            safe.angular.y = 0.0
            safe.angular.z = _clamp(self._last_cmd.angular.z, angular_limit)

        self._safe_pub.publish(safe)
        if reason != self._last_reason:
            self.get_logger().info(f"Safety state: {reason}")
            self._last_reason = reason
        self._state_pub.publish(String(data=reason))


def main(args=None) -> None:
    rclpy.init(args=args)
    node = SafetyGate()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
