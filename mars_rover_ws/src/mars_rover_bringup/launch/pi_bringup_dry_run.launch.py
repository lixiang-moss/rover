from launch import LaunchDescription
from launch.substitutions import Command, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch.substitutions import FindExecutable


def rover_robot_description():
    xacro_file = PathJoinSubstitution(
        [FindPackageShare("mars_rover_description"), "urdf", "mars_rover.urdf.xacro"]
    )
    return {"robot_description": Command([FindExecutable(name="xacro"), " ", xacro_file])}


def config_path(name):
    return PathJoinSubstitution([FindPackageShare("mars_rover_bringup"), "config", name])


def generate_launch_description():
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
