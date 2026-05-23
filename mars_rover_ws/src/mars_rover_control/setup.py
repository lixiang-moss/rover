from glob import glob
from setuptools import find_packages, setup

package_name = "mars_rover_control"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (f"share/{package_name}/launch", glob("launch/*.launch.py")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="MARS Rover Team",
    maintainer_email="maintainer@example.com",
    description="MARS rover ROS 2 high-level control nodes.",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "drive_mode_manager = mars_rover_control.drive_mode_manager:main",
            "safety_gate = mars_rover_control.safety_gate:main",
            "four_wheel_kinematics = mars_rover_control.four_wheel_kinematics:main",
            "stm32_bridge = mars_rover_control.stm32_bridge:main",
            "joint_state_republisher = mars_rover_control.joint_state_republisher:main",
        ],
    },
)
