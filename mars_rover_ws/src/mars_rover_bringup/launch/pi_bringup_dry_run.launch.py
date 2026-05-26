"""Pi 侧 dry-run 启动文件。

该 launch 启动完整的 Pi 侧高层控制链路，但 `stm32_bridge` 运行在 dry_run 模式，
不会打开串口，也不会控制真实硬件。它适合开发阶段验证 topic、运动学、RViz 和
JointState 链路。
"""

from launch import LaunchDescription
from launch.substitutions import Command, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch.substitutions import FindExecutable


def rover_robot_description():
    """生成 robot_state_publisher 所需的 robot_description 参数。"""

    xacro_file = PathJoinSubstitution(
        [FindPackageShare("mars_rover_description"), "urdf", "mars_rover.urdf.xacro"]
    )
    return {"robot_description": Command([FindExecutable(name="xacro"), " ", xacro_file])}


def config_path(name):
    """根据配置文件名生成 mars_rover_bringup 包内 config 路径。"""

    return PathJoinSubstitution([FindPackageShare("mars_rover_bringup"), "config", name])


def generate_launch_description():
    """生成 dry-run 模式下的 Pi 侧启动描述。"""

    geometry = config_path("robot_geometry.yaml")
    safety = config_path("safety_limits.yaml")
    bridge = config_path("stm32_bridge.yaml")

    return LaunchDescription(
        [
            Node(
                package="mars_rover_control",
                executable="drive_mode_manager",
                name="drive_mode_manager",
                output="screen",
                parameters=[{"default_mode": "STOP"}],
            ),
            Node(
                package="mars_rover_control",
                executable="safety_gate",
                name="safety_gate",
                output="screen",
                parameters=[safety, {"bridge_mode": "dry_run"}],
            ),
            Node(
                package="mars_rover_control",
                executable="four_wheel_kinematics",
                name="four_wheel_kinematics",
                output="screen",
                parameters=[geometry, safety],
            ),
            Node(
                package="mars_rover_control",
                executable="stm32_bridge",
                name="stm32_bridge",
                output="screen",
                parameters=[bridge, {"bridge_mode": "dry_run"}],
            ),
            Node(
                package="mars_rover_control",
                executable="joint_state_republisher",
                name="joint_state_republisher",
                output="screen",
            ),
            Node(
                package="robot_state_publisher",
                executable="robot_state_publisher",
                name="robot_state_publisher",
                output="screen",
                parameters=[rover_robot_description()],
            ),
        ]
    )
