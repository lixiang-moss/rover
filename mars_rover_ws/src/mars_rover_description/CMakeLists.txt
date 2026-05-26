# mars_rover_description 包构建文件。
# 该包安装 URDF/Xacro 机器人描述文件，供 robot_state_publisher 和 RViz 使用。
cmake_minimum_required(VERSION 3.8)
project(mars_rover_description)

# description 是 ament_cmake 包。
find_package(ament_cmake REQUIRED)

# 安装 urdf 目录，使 launch 文件能通过 FindPackageShare 找到 xacro。
install(DIRECTORY urdf
  DESTINATION share/${PROJECT_NAME}
)

# 标准 ament 包结尾。
ament_package()
