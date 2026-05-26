"""驱动模式管理节点。

本节点负责维护当前生效的 Drive Mode，并把模式发布到
`/mars_rover/drive_mode`。其他节点只需要订阅这个话题，不需要自己解析
用户输入的模式字符串。
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from std_msgs.msg import String

from mars_rover_control.constants import MODE_NAME_TO_VALUE, MODE_STOP, MODE_VALUE_TO_NAME
from mars_rover_msgs.msg import DriveMode


class DriveModeManager(Node):
    """ROS 2 节点：接收模式切换请求并发布当前驱动模式。"""

    def __init__(self) -> None:
        """初始化节点、参数、发布器、订阅器和周期性模式发布定时器。"""

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
        """处理 `/mars_rover/drive_mode_request` 中的模式切换请求。

        输入是字符串，例如 STOP、CRAB、SPIN_IN_PLACE、RAW_WHEEL_TEST。
        如果请求非法，则拒绝切换并重新发布当前模式。
        """

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
        """发布当前驱动模式。

        reason 字段用于给调试者解释本次发布的原因，例如启动默认值、周期发布、
        收到有效请求或拒绝非法请求。
        """

        message = DriveMode()
        message.stamp = self.get_clock().now().to_msg()
        message.mode = self._mode
        message.source = self._source
        message.transitioning = False
        message.reason = reason
        self._publisher.publish(message)


def main(args=None) -> None:
    """ROS 2 可执行入口：启动 DriveModeManager 并进入 spin 循环。"""

    rclpy.init(args=args)
    node = DriveModeManager()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
