"""Republish rover wheel states as standard sensor_msgs/JointState."""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState

from mars_rover_control.constants import DRIVE_JOINT_BY_WHEEL, JOINT_NAMES, STEERING_JOINT_BY_WHEEL
from mars_rover_msgs.msg import WheelStateArray


class JointStateRepublisher(Node):
    def __init__(self) -> None:
        super().__init__("joint_state_republisher")
        self.declare_parameter("publish_rate_hz", 20.0)
        self._joint_positions = {name: 0.0 for name in JOINT_NAMES}
        self._joint_velocities = {name: 0.0 for name in JOINT_NAMES}
        self._last_publish_time = self.get_clock().now()

        self.create_subscription(WheelStateArray, "/mars_rover/wheel_states", self._on_wheel_states, 10)
        self._publisher = self.create_publisher(JointState, "/joint_states", 10)
        period = 1.0 / float(self.get_parameter("publish_rate_hz").value)
        self.create_timer(period, self._publish_joint_states)

        self.get_logger().warn(
            "Publishing /joint_states from wheel_states; feedback_is_real=false means RViz shows target echoes."
        )

    def _on_wheel_states(self, message: WheelStateArray) -> None:
        for state in message.states:
            steering_joint = STEERING_JOINT_BY_WHEEL.get(state.name)
            drive_joint = DRIVE_JOINT_BY_WHEEL.get(state.name)
            if steering_joint:
                self._joint_positions[steering_joint] = state.steering_angle
                self._joint_velocities[steering_joint] = 0.0
            if drive_joint:
                self._joint_velocities[drive_joint] = state.drive_velocity

    def _publish_joint_states(self) -> None:
        now = self.get_clock().now()
        dt = (now - self._last_publish_time).nanoseconds / 1e9
        self._last_publish_time = now
        for name in DRIVE_JOINT_BY_WHEEL.values():
            self._joint_positions[name] += self._joint_velocities[name] * dt

        message = JointState()
        message.header.stamp = now.to_msg()
        message.name = list(JOINT_NAMES)
        message.position = [self._joint_positions[name] for name in JOINT_NAMES]
        message.velocity = [self._joint_velocities[name] for name in JOINT_NAMES]
        message.effort = []
        self._publisher.publish(message)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = JointStateRepublisher()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
