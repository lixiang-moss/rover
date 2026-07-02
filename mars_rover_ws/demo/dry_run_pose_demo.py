#!/usr/bin/env python3
"""RViz-only dry-run pose demo.

This script is deliberately outside the ROS packages. It subscribes to the
already-safe velocity command and publishes an odom -> base_link transform so
RViz can show the rover body moving during a no-hardware demo.
"""

import math

from geometry_msgs.msg import TransformStamped, Twist
import rclpy
from rclpy.node import Node
from tf2_ros import TransformBroadcaster


class DryRunPoseDemo(Node):
    def __init__(self) -> None:
        super().__init__("dry_run_pose_demo")
        self._x = 0.0
        self._y = 0.0
        self._yaw = 0.0
        self._cmd = Twist()
        self._last_time = self.get_clock().now()
        self._tf_broadcaster = TransformBroadcaster(self)

        self.create_subscription(Twist, "/mars_rover/safe_cmd_vel", self._on_cmd_vel, 10)
        self.create_timer(1.0 / 30.0, self._publish_transform)
        self.get_logger().info("Demo pose enabled: publishing odom -> base_link for RViz only.")

    def _on_cmd_vel(self, message: Twist) -> None:
        self._cmd = message

    def _publish_transform(self) -> None:
        now = self.get_clock().now()
        dt = (now - self._last_time).nanoseconds / 1e9
        self._last_time = now

        vx = float(self._cmd.linear.x)
        vy = float(self._cmd.linear.y)
        wz = float(self._cmd.angular.z)

        cos_yaw = math.cos(self._yaw)
        sin_yaw = math.sin(self._yaw)
        self._x += (cos_yaw * vx - sin_yaw * vy) * dt
        self._y += (sin_yaw * vx + cos_yaw * vy) * dt
        self._yaw = math.atan2(math.sin(self._yaw + wz * dt), math.cos(self._yaw + wz * dt))

        transform = TransformStamped()
        transform.header.stamp = now.to_msg()
        transform.header.frame_id = "odom"
        transform.child_frame_id = "base_link"
        transform.transform.translation.x = self._x
        transform.transform.translation.y = self._y
        transform.transform.translation.z = 0.0

        half_yaw = self._yaw / 2.0
        transform.transform.rotation.z = math.sin(half_yaw)
        transform.transform.rotation.w = math.cos(half_yaw)
        self._tf_broadcaster.sendTransform(transform)


def main() -> None:
    rclpy.init()
    node = DryRunPoseDemo()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
