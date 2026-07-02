"""带 profile 限制和 STOP 过渡的驱动模式管理节点。"""

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from std_msgs.msg import String

from mars_rover_control.constants import MODE_NAME_TO_VALUE, MODE_STOP, MODE_VALUE_TO_NAME
from mars_rover_msgs.msg import DriveMode


class DriveModeManager(Node):
    """接收模式请求，并通过 STOP 过渡发布实际生效模式。"""

    def __init__(self) -> None:
        """初始化允许模式、过渡定时器和 transient-local 模式发布器。"""

        super().__init__("drive_mode_manager")
        self.declare_parameter("default_mode", "STOP")
        self.declare_parameter("source", "drive_mode_manager")
        self.declare_parameter("allowed_modes", list(MODE_NAME_TO_VALUE.keys()))
        self.declare_parameter("transition_hold_sec", 0.25)

        allowed = {
            str(name).strip().upper()
            for name in self.get_parameter("allowed_modes").value
        }
        unknown = allowed - set(MODE_NAME_TO_VALUE)
        if unknown:
            raise ValueError(f"allowed_modes contains unsupported values: {sorted(unknown)}")
        if "STOP" not in allowed:
            raise ValueError("allowed_modes must always include STOP")
        transition_hold = float(self.get_parameter("transition_hold_sec").value)
        if transition_hold <= 0.0:
            raise ValueError("transition_hold_sec must be greater than zero")

        default_name = str(self.get_parameter("default_mode").value).upper()
        if default_name != "STOP":
            self.get_logger().warning(
                f"Ignoring unsafe startup default {default_name!r}; every profile starts in STOP."
            )
        self._allowed_modes = allowed
        self._transition_hold_sec = transition_hold
        self._source = str(self.get_parameter("source").value)
        self._mode = MODE_STOP
        self._pending_mode = None
        self._transition_started_at = None
        self._transitioning = False
        self._reason = "startup STOP"

        qos = QoSProfile(depth=1)
        qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        self._publisher = self.create_publisher(DriveMode, "/mars_rover/drive_mode", qos)
        self.create_subscription(
            String, "/mars_rover/drive_mode_request", self._on_mode_request, 10
        )
        self.create_timer(0.05, self._tick_transition)
        self.create_timer(1.0, self._publish_current)
        self._publish_current()

    def _on_mode_request(self, message: String) -> None:
        """校验 profile 权限，并启动或取消模式过渡。"""

        requested = message.data.strip().upper()
        if requested not in MODE_NAME_TO_VALUE:
            self.get_logger().warning(f"Rejected invalid drive mode request: {message.data!r}")
            self._reason = f"invalid request rejected: {message.data}"
            self._publish_current()
            return
        if requested not in self._allowed_modes:
            self.get_logger().warning(
                f"Rejected drive mode {requested}: not allowed by this launch profile"
            )
            self._reason = f"profile rejected: {requested}"
            self._publish_current()
            return

        requested_mode = MODE_NAME_TO_VALUE[requested]
        if requested_mode == MODE_STOP:
            self._mode = MODE_STOP
            self._pending_mode = None
            self._transition_started_at = None
            self._transitioning = False
            self._reason = "accepted request: STOP"
            self._publish_current()
            return
        if not self._transitioning and requested_mode == self._mode:
            self._reason = f"already in {requested}"
            self._publish_current()
            return
        if self._transitioning and requested_mode == self._pending_mode:
            self._reason = f"transition already pending: {requested}"
            self._publish_current()
            return

        previous = MODE_VALUE_TO_NAME.get(self._mode, "UNKNOWN")
        self._mode = MODE_STOP
        self._pending_mode = requested_mode
        self._transition_started_at = self.get_clock().now()
        self._transitioning = True
        self._reason = f"transition {previous} -> {requested}: holding STOP"
        self.get_logger().info(self._reason)
        self._publish_current()

    def _tick_transition(self) -> None:
        """STOP 保持时间结束后发布最终模式。"""

        if not self._transitioning or self._transition_started_at is None:
            return
        elapsed = (
            self.get_clock().now() - self._transition_started_at
        ).nanoseconds / 1e9
        if elapsed < self._transition_hold_sec:
            return

        target = self._pending_mode
        self._pending_mode = None
        self._transition_started_at = None
        self._transitioning = False
        self._mode = MODE_STOP if target is None else int(target)
        target_name = MODE_VALUE_TO_NAME.get(self._mode, "STOP")
        self._reason = f"transition complete: {target_name}; waiting for fresh command"
        self.get_logger().info(self._reason)
        self._publish_current()

    def _publish_current(self) -> None:
        """发布当前实际模式和过渡状态。"""

        message = DriveMode()
        message.stamp = self.get_clock().now().to_msg()
        message.mode = self._mode
        message.source = self._source
        message.transitioning = self._transitioning
        message.reason = self._reason
        self._publisher.publish(message)


def main(args=None) -> None:
    """启动 DriveModeManager 并进入 ROS 2 spin。"""

    rclpy.init(args=args)
    node = DriveModeManager()
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
