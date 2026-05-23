"""Drive mode manager node."""

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from std_msgs.msg import String

from mars_rover_control.constants import MODE_NAME_TO_VALUE, MODE_STOP, MODE_VALUE_TO_NAME
from mars_rover_msgs.msg import DriveMode


class DriveModeManager(Node):
    def __init__(self) -> None:
        super().__init__("drive_mode_manager")
        self.declare_parameter("default_mode", "STOP")
        self.declare_parameter("source", "drive_mode_manager")

        default_name = self.get_parameter("default_mode").value
        self._mode = MODE_NAME_TO_VALUE.get(str(default_name).upper(), MODE_STOP)
        self._source = str(self.get_parameter("source").value)

        qos = QoSProfile(depth=1)
        qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        self._publisher = self.create_publisher(DriveMode, "/mars_rover/drive_mode", qos)
        self.create_subscription(String, "/mars_rover/drive_mode_request", self._on_mode_request, 10)
        self.create_timer(1.0, self._publish_current)
        self._publish_current("startup default")

    def _on_mode_request(self, message: String) -> None:
        requested = message.data.strip().upper()
        if requested not in MODE_NAME_TO_VALUE:
            self.get_logger().warn(f"Rejected invalid drive mode request: {message.data!r}")
            self._publish_current(f"invalid request rejected: {message.data}")
            return

        next_mode = MODE_NAME_TO_VALUE[requested]
        if next_mode == self._mode:
            self._publish_current(f"already in {requested}")
            return

        self.get_logger().info(
            f"Switching drive mode from {MODE_VALUE_TO_NAME.get(self._mode)} to {requested}"
        )
        self._mode = next_mode
        self._publish_current(f"accepted request: {requested}")

    def _publish_current(self, reason: str = "periodic") -> None:
        message = DriveMode()
        message.stamp = self.get_clock().now().to_msg()
        message.mode = self._mode
        message.source = self._source
        message.transitioning = False
        message.reason = reason
        self._publisher.publish(message)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = DriveModeManager()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
