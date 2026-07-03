"""控制端电脑启动文件：键盘控制与可选 RViz。

该 launch 用于控制端电脑。它启动键盘 teleop 发布 `/cmd_vel`，
并可选择启动 RViz 来观察 Pi 发布的机器人 TF。
它不直接访问 STM32，也不直接控制电机。
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    """生成控制端电脑的 launch 描述。

    `with_rviz` 为 true 时启动 RViz；robot_state_publisher 只在 Pi bringup 中运行；
    为 false 时只启动键盘控制。
    """

    with_rviz = LaunchConfiguration("with_rviz")
    speed = LaunchConfiguration("speed")
    turn = LaunchConfiguration("turn")
    repeat_rate = LaunchConfiguration("repeat_rate")
    key_timeout = LaunchConfiguration("key_timeout")
    rviz_config = PathJoinSubstitution(
        [FindPackageShare("mars_rover_bringup"), "rviz", "mars_rover.rviz"]
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument("with_rviz", default_value="false"),
            DeclareLaunchArgument("speed", default_value="0.02"),
            DeclareLaunchArgument("turn", default_value="0.05"),
            DeclareLaunchArgument("repeat_rate", default_value="10.0"),
            DeclareLaunchArgument("key_timeout", default_value="0.4"),
            Node(
                package="mars_rover_control",
                executable="keyboard_teleop",
                name="teleop_twist_keyboard",
                output="screen",
                parameters=[
                    {
                        "speed": ParameterValue(speed, value_type=float),
                        "turn": ParameterValue(turn, value_type=float),
                        "repeat_rate": ParameterValue(repeat_rate, value_type=float),
                        "key_timeout": ParameterValue(key_timeout, value_type=float),
                    }
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
