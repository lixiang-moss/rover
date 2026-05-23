"""Four-wheel independent steering kinematics node."""

from geometry_msgs.msg import Twist
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile

from mars_rover_control.constants import MODE_STOP
from mars_rover_control.kinematics import compute_wheel_targets
from mars_rover_msgs.msg import DriveMode, WheelSetpoint, WheelSetpointArray


class FourWheelKinematics(Node):
    def __init__(self) -> None:
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
        self._mode = int(message.mode)

    def _on_safe_cmd_vel(self, message: Twist) -> None:
        self._safe_cmd = message

    def _publish_setpoints(self) -> None:
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
        message = WheelSetpoint()
        message.name = target.name
        message.enabled = target.enabled
        message.steering_angle = target.steering_angle
        message.drive_velocity = target.drive_velocity
        message.steering_velocity_limit = float(self.get_parameter("steering_velocity_limit").value)
        message.drive_acceleration_limit = float(self.get_parameter("drive_acceleration_limit").value)
        return message


def main(args=None) -> None:
    rclpy.init(args=args)
    node = FourWheelKinematics()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
