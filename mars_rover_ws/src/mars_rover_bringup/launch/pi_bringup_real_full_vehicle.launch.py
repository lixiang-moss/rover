"""Pi 侧真实四轮手动控制启动文件。

该 launch 面向四轮实体车手动控制。它启动 Pi 侧完整控制链路，并把
`stm32_bridge` 置为 real_serial + full_vehicle 模式。
注意：系统始终从 STOP/disarmed 启动，必须通过 set_armed 服务授权。
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import Command, LaunchConfiguration, PathJoinSubstitution
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
    """生成真实四轮手动控制模式下的 Pi 侧启动描述。"""

    serial_port = LaunchConfiguration("serial_port")
    geometry = config_path("robot_geometry.yaml")
    safety = config_path("safety_limits.yaml")
    bridge = config_path("stm32_bridge.yaml")

    return LaunchDescription(
        [
            DeclareLaunchArgument("serial_port", default_value="/dev/mars-rover-stm32"),
            Node(
                package="mars_rover_control",
                executable="drive_mode_manager",
                name="drive_mode_manager",
                output="screen",
                parameters=[
                    {
                        "default_mode": "STOP",
                        "allowed_modes": ["STOP", "CRAB", "SPIN_IN_PLACE"],
                        "transition_hold_sec": 0.25,
                    }
                ],
            ),
            Node(
                package="mars_rover_control",
                executable="safety_gate",
                name="safety_gate",
                output="screen",
                parameters=[safety, {"bridge_mode": "real_serial"}],
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
                parameters=[
                    bridge,
                    {
                        "bridge_mode": "real_serial",
                        "serial_port": serial_port,
                        "hardware_output_mode": "full_vehicle",
                    },
                ],
            ),
            Node(
                package="mars_rover_control",
                executable="joint_state_republisher",
                name="joint_state_republisher",
                output="screen",
                parameters=[geometry],
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
