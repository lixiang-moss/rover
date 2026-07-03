# mars_rover_msgs 消息包构建文件。
# 该包只负责生成自定义 ROS 2 消息，不包含运行节点。
cmake_minimum_required(VERSION 3.8)
project(mars_rover_msgs)

# 开启常见编译告警，帮助尽早发现 C++ 生成代码相关问题。
if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# 查找消息生成所需依赖。
find_package(ament_cmake REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(rosidl_default_generators REQUIRED)

# 声明需要生成的自定义消息接口。
rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/ControlState.msg"
  "msg/DriveMode.msg"
  "msg/WheelSetpoint.msg"
  "msg/WheelSetpointArray.msg"
  "msg/WheelState.msg"
  "msg/WheelStateArray.msg"
  "msg/Stm32Status.msg"
  DEPENDENCIES builtin_interfaces
)

# 导出运行时依赖，使其他包可以使用这些生成后的消息。
ament_export_dependencies(rosidl_default_runtime)

# 标准 ament 包结尾。
ament_package()
