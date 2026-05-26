"""四轮独立转向/独立驱动运动学节点。

本节点订阅安全后的机器人整体速度 `/mars_rover/safe_cmd_vel` 和当前驱动模式
`/mars_rover/drive_mode`，调用纯运动学函数计算四个轮组的目标转向角和目标速度，
然后发布 `/mars_rover/wheel_setpoints` 给底层 bridge。
"""

from geometry_msgs.msg import Twist
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile

from mars_rover_control.constants import MODE_STOP
from mars_rover_control.kinematics import compute_wheel_targets
from mars_rover_msgs.msg import DriveMode, WheelSetpoint, WheelSetpointArray


class FourWheelKinematics(Node):
    """ROS 2 节点：把机器人整体速度转换为四个轮组目标。"""

    def __init__(self) -> None:
        """初始化几何参数、安全限幅、订阅器、发布器和周期性发布定时器。"""

        super().__init__("four_wheel_kinematics")
        self.declare_parameter("wheelbase", 0.706)
        self.declare_parameter("track_width", 0.288)
        self.declare_parameter("max_steering_angle", 1.5708)
        self.declare_parameter("max_drive_velocity", 0.10)
        self.declare_parameter("active_test_wheel", "front_left")
        self.declare_parameter("steering_velocity_limit", 0.30)
        self.declare_parameter("drive_acceleration_limit", 0.10)
        self.declare_parameter("publish_rate_hz", 20.0)

        self._mode = MODE_STOP
        self._safe_cmd = Twist()
        self._sequence_id = 0
        self._last_angles: dict[str, float] = {}

        mode_qos = QoSProfile(depth=1)
        mode_qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        self.create_subscription(DriveMode, "/mars_rover/drive_mode", self._on_drive_mode, mode_qos)
        self.create_subscription(Twist, "/mars_rover/safe_cmd_vel", self._on_safe_cmd_vel, 10)
        self._publisher = self.create_publisher(WheelSetpointArray, "/mars_rover/wheel_setpoints", 10)

        period = 1.0 / float(self.get_parameter("publish_rate_hz").value)
        self.create_timer(period, self._publish_setpoints)

    def _on_drive_mode(self, message: DriveMode) -> None:
        """接收当前驱动模式，并在下一次定时发布时使用该模式计算目标。"""

        self._mode = int(message.mode)

    def _on_safe_cmd_vel(self, message: Twist) -> None:
        """接收安全门输出的速度命令。该命令已完成超时、急停和限幅处理。"""

        self._safe_cmd = message

    def _publish_setpoints(self) -> None:
        """周期性计算并发布四个轮组的目标。

        输出消息包含 sequence_id，便于后续 STM32 bridge 或真实硬件 bridge
        将命令与 ACK/status 对齐。
        """

        targets = compute_wheel_targets(
            self._mode,
            self._safe_cmd.linear.x,
            self._safe_cmd.linear.y,
            self._safe_cmd.angular.z,
            wheelbase=float(self.get_parameter("wheelbase").value),
            track_width=float(self.get_parameter("track_width").value),
            max_steering_angle=float(self.get_parameter("max_steering_angle").value),
            max_drive_velocity=float(self.get_parameter("max_drive_velocity").value),
            active_test_wheel=str(self.get_parameter("active_test_wheel").value),
            last_angles=self._last_angles,
        )

        message = WheelSetpointArray()
        message.stamp = self.get_clock().now().to_msg()
        message.sequence_id = self._sequence_id
        message.mode = self._mode
        message.setpoints = [self._to_msg(target) for target in targets]
        self._publisher.publish(message)

        self._sequence_id = (self._sequence_id + 1) % (2**32)
        self._last_angles.update({target.name: target.steering_angle for target in targets})

    def _to_msg(self, target) -> WheelSetpoint:
        """把纯 Python WheelTarget 对象转换成 ROS 2 WheelSetpoint 消息。"""

        message = WheelSetpoint()
        message.name = target.name
        message.enabled = target.enabled
        message.steering_angle = target.steering_angle
        message.drive_velocity = target.drive_velocity
        message.steering_velocity_limit = float(self.get_parameter("steering_velocity_limit").value)
        message.drive_acceleration_limit = float(self.get_parameter("drive_acceleration_limit").value)
        return message


def main(args=None) -> None:
    """ROS 2 可执行入口：启动 FourWheelKinematics 并进入 spin 循环。"""

    rclpy.init(args=args)
    node = FourWheelKinematics()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
