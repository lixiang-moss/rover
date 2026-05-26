"""把轮组状态转换为标准 `/joint_states` 的节点。

RViz 和 robot_state_publisher 使用 `sensor_msgs/JointState` 来更新 URDF 中的关节。
本节点订阅 `/mars_rover/wheel_states`，把四个轮组的转向角和驱动速度转换为
8 个标准关节状态，用于可视化和后续调试。
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState

from mars_rover_control.constants import DRIVE_JOINT_BY_WHEEL, JOINT_NAMES, STEERING_JOINT_BY_WHEEL
from mars_rover_msgs.msg import WheelStateArray


class JointStateRepublisher(Node):
    """ROS 2 节点：从 WheelStateArray 生成标准 JointState。"""

    def __init__(self) -> None:
        """初始化关节状态缓存、订阅器、发布器和周期性发布定时器。"""

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
        """接收四个轮组状态并更新内部关节位置/速度缓存。

        转向关节的位置直接来自 steering_angle；驱动关节速度来自 drive_velocity。
        当前 dry-run 阶段这些值可能只是目标值回显，不一定是真实反馈。
        """

        for state in message.states:
            steering_joint = STEERING_JOINT_BY_WHEEL.get(state.name)
            drive_joint = DRIVE_JOINT_BY_WHEEL.get(state.name)
            if steering_joint:
                self._joint_positions[steering_joint] = state.steering_angle
                self._joint_velocities[steering_joint] = 0.0
            if drive_joint:
                self._joint_velocities[drive_joint] = state.drive_velocity

    def _publish_joint_states(self) -> None:
        """周期性发布 `/joint_states`。

        对驱动关节，使用上一周期速度积分出一个可视化位置，使 RViz 中轮子能够转动。
        该积分只用于显示，不应被当成真实里程计。
        """

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
    """ROS 2 可执行入口：启动 JointStateRepublisher 并进入 spin 循环。"""

    rclpy.init(args=args)
    node = JointStateRepublisher()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
