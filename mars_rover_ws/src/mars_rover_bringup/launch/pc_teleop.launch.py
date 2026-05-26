"""控制端电脑启动文件：键盘控制与可选 RViz。

该 launch 用于控制端电脑。它启动键盘 teleop 发布 `/cmd_vel`，
并可选择启动 robot_state_publisher 和 RViz 来观察机器人模型。
它不直接访问 STM32，也不直接控制电机。
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import Command, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch.substitutions import FindExecutable


def generate_launch_description():
    """生成控制端电脑的 launch 描述。

    `with_rviz` 为 true 时会同时启动 RViz 和 robot_state_publisher；
    为 false 时只启动键盘控制。
    """

    with_rviz = LaunchConfiguration("with_rviz")
    rviz_config = PathJoinSubstitution([FindPackageShare("mars_rover_bringup"), "rviz", "mars_rover.rviz"])
    xacro_file = PathJoinSubstitution(
        [FindPackageShare("mars_rover_description"), "urdf", "mars_rover.urdf.xacro"]
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument("with_rviz", default_value="true"),
            Node(
                package="teleop_twist_keyboard",
                executable="teleop_twist_keyboard",
                name="teleop_twist_keyboard",
                output="screen",
            ),
            Node(
                package="robot_state_publisher",
                executable="robot_state_publisher",
                name="pc_robot_state_publisher",
                output="screen",
                condition=IfCondition(with_rviz),
                parameters=[
                    {"robot_description": Command([FindExecutable(name="xacro"), " ", xacro_file])}
                ],
            ),
            Node(
                package="rviz2",
                executable="rviz2",
                name="rviz2",
                output="screen",
                condition=IfCondition(with_rviz),
                arguments=["-d", rviz_config],
            ),
        ]
    )
