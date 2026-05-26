# Ubuntu 24.04 + ROS 2 Jazzy 开发容器。
# 宿主机可以是 Ubuntu 26，本 Dockerfile 用于提供与 Jazzy 匹配的开发环境。
FROM osrf/ros:jazzy-desktop

# 避免 apt 安装过程中出现交互式提示。
ENV DEBIAN_FRONTEND=noninteractive

# 使用 bash，方便后续 source ROS 环境。
SHELL ["/bin/bash", "-c"]

# 安装本工作区开发、测试、RViz、URDF/Xacro 和键盘控制所需依赖。
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-colcon-common-extensions \
    python3-pytest \
    python3-serial \
    ros-jazzy-ament-lint-auto \
    ros-jazzy-ament-lint-common \
    ros-jazzy-joint-state-publisher \
    ros-jazzy-robot-state-publisher \
    ros-jazzy-teleop-twist-keyboard \
    ros-jazzy-xacro \
    && rm -rf /var/lib/apt/lists/*

# 进入容器 shell 时自动加载 ROS 2 Jazzy 环境。
RUN echo "source /opt/ros/jazzy/setup.bash" >> /root/.bashrc

# 容器内默认工作目录，对应挂载进来的 mars_rover_ws。
WORKDIR /workspace/mars_rover_ws
