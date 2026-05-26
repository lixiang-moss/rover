# MARS Rover ROS 2 工作空间

这个工作空间实现了 `../docs` 中描述的 ROS 2 Jazzy 高层手动控制框架。

当前实现同时覆盖无硬件验证、STM32 串口联调、单轮测试和四轮真实手动控制入口：

- `dry_run` 不会打开真实串口。
- `/mars_rover/wheel_states` 和 `/joint_states` 是目标值回显，不是真实传感器反馈。
- `serial_echo` 会打开串口并等待 STM32 ACK，用于通信联调。
- `pi_bringup_real_single_wheel.launch.py` 使用 `real_serial + single_wheel`，用于单轮真实测试。
- `pi_bringup_real_full_vehicle.launch.py` 使用 `real_serial + full_vehicle`，用于四轮真实手动控制。
- 所有真实硬件 launch 默认 `hardware_enable=false`，必须显式传参后才会发送可执行的 `enabled=true`。

## Docker 开发

构建开发镜像：

```bash
docker build -t mars-rover-jazzy -f Dockerfile .
```

从 `/home/lx/rover/mars_rover_ws` 启动一个交互式容器：

```bash
docker run --rm -it --net=host \
  -v "$PWD":/workspace/mars_rover_ws \
  -w /workspace/mars_rover_ws \
  mars-rover-jazzy
```

进入容器后执行：

```bash
colcon build
source install/setup.bash
colcon test
colcon test-result --verbose
ros2 launch mars_rover_bringup pi_bringup_dry_run.launch.py
```

常用 launch：

```bash
ros2 launch mars_rover_bringup pi_bringup_dry_run.launch.py
ros2 launch mars_rover_bringup pi_bringup_serial_echo.launch.py serial_port:=/dev/mars_stm32
ros2 launch mars_rover_bringup pi_bringup_real_single_wheel.launch.py serial_port:=/dev/mars_stm32 hardware_enable:=true
ros2 launch mars_rover_bringup pi_bringup_real_full_vehicle.launch.py serial_port:=/dev/mars_stm32 hardware_enable:=true
```
