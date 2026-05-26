# mars_rover_bringup 包构建文件。
# 该包安装 launch、config 和 rviz 文件，不编译代码。
cmake_minimum_required(VERSION 3.8)
project(mars_rover_bringup)

# bringup 是 ament_cmake 包。
find_package(ament_cmake REQUIRED)

# 安装启动文件、参数配置和 RViz 配置，供 ros2 launch 使用。
install(DIRECTORY launch config rviz
  DESTINATION share/${PROJECT_NAME}
)

# 标准 ament 包结尾。
ament_package()
