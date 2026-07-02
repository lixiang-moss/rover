#!/usr/bin/env python3
"""Publish the demo-only robot description with transient-local durability."""

import subprocess
from pathlib import Path

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from std_msgs.msg import String


class DemoRobotDescription(Node):
    def __init__(self) -> None:
        super().__init__("demo_robot_description")
        xacro_path = Path("/workspace/mars_rover_ws/demo/demo_rover.urdf.xacro")
        robot_xml = subprocess.check_output(["xacro", str(xacro_path)], text=True)

        qos = QoSProfile(depth=1)
        qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        self._publisher = self.create_publisher(String, "/demo/robot_description", qos)

        message = String()
        message.data = robot_xml
        self._publisher.publish(message)
        self.create_timer(1.0, lambda: self._publisher.publish(message))
        self.get_logger().info("Publishing demo visual robot_description on /demo/robot_description.")


def main() -> None:
    rclpy.init()
    node = DemoRobotDescription()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
