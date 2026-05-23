FROM osrf/ros:jazzy-desktop

ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-c"]

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

RUN echo "source /opt/ros/jazzy/setup.bash" >> /root/.bashrc

WORKDIR /workspace/mars_rover_ws
