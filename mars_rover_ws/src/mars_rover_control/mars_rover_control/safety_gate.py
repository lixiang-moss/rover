"""速度命令安全门节点。

本节点位于 `/cmd_vel` 和运动学节点之间，用于在真实硬件或 dry-run 前
统一执行安全检查：命令超时、软件急停、STM32 在线状态检查、速度限幅。
它输出 `/mars_rover/safe_cmd_vel`，后续运动学节点只处理已经通过安全门的速度。
"""

import copy

from geometry_msgs.msg import Twist
import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String

from mars_rover_msgs.msg import Stm32Status


def _zero_twist() -> Twist:
    """生成一个所有速度分量都为 0 的 Twist，用于停止机器人。"""

    return Twist()


def _clamp(value: float, limit: float) -> float:
    """按正负对称限幅限制输入值，例如把速度限制在 [-limit, +limit]。"""

    return min(max(value, -limit), limit)


class SafetyGate(Node):
    """ROS 2 节点：过滤和限幅 `/cmd_vel`，发布安全后的速度命令。"""

    def __init__(self) -> None:
        """初始化安全参数、订阅器、发布器和周期性安全输出定时器。"""

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
        """接收控制端发布的原始 `/cmd_vel` 并记录接收时间。"""

        self._last_cmd = copy.deepcopy(message)
        self._last_cmd_time = self.get_clock().now()

    def _on_estop(self, message: Bool) -> None:
        """接收软件急停状态。为 true 时，后续输出必须强制为零速度。"""

        self._estop_active = bool(message.data)

    def _on_stm32_status(self, message: Stm32Status) -> None:
        """接收 STM32 bridge 状态，用于真实串口模式下判断底层是否在线。"""

        self._stm32_online = bool(message.online)

    def _command_timed_out(self) -> bool:
        """判断 `/cmd_vel` 是否超时。

        如果启动后从未收到命令，或者距离上次命令超过 cmd_timeout_sec，
        都认为控制输入已经失效。
        """

        if self._last_cmd_time is None:
            return True
        timeout = float(self.get_parameter("cmd_timeout_sec").value)
        age = (self.get_clock().now() - self._last_cmd_time).nanoseconds / 1e9
        return age > timeout

    def _publish_safe_command(self) -> None:
        """周期性发布安全后的速度命令和安全状态字符串。

        只有在未超时、未急停、底层在线检查通过时，才会把原始速度限幅后转发。
        否则发布零速度。
        """

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
    """ROS 2 可执行入口：启动 SafetyGate 并进入 spin 循环。"""

    rclpy.init(args=args)
    node = SafetyGate()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
