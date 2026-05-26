# mars_rover_tests 包构建文件。
# 当前测试主要在 mars_rover_control/test 中，这个包用于安装测试说明文档。
cmake_minimum_required(VERSION 3.8)
project(mars_rover_tests)

# tests 是 ament_cmake 包。
find_package(ament_cmake REQUIRED)

# 安装测试说明 README。
install(FILES README.md
  DESTINATION share/${PROJECT_NAME}
)

# 标准 ament 包结尾。
ament_package()
