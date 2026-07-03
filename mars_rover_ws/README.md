# MARS Rover ROS 2 工作空间

这个工作空间实现了 `../docs` 中描述的 ROS 2 Jazzy 高层手动控制框架。

当前实现同时覆盖无硬件验证、STM32 串口联调、单轮测试和四轮真实手动控制入口：

- `dry_run` 不会打开真实串口。
- `/mars_rover/wheel_states` 和 `/joint_states` 是目标值回显，不是真实传感器反馈。
- `serial_echo` 会打开串口并等待 STM32 ACK，用于通信联调。
- `pi_bringup_real_single_wheel.launch.py` 使用 `real_serial + single_wheel`，用于单轮真实测试。
- `pi_bringup_real_full_vehicle.launch.py` 使用 `real_serial + full_vehicle`，用于四轮真实手动控制。
- 所有真实硬件 launch 都从 `STOP + disarmed` 启动；只有 `/mars_rover/set_armed` 服务通过安全前置检查后，才可能发送可执行的 `enabled=true`。
- Pi 与 STM32 通过 USB 虚拟串口连接，Pi 使用稳定别名 `/dev/mars-rover-stm32`，协议仍为 `紧凑JSON*CRC32\n`。
- 当前实体验收范围是 `front_left` 单轮组；四轮 launch 是软件能力，不表示实体四轮已通过测试。

完整部署和接线步骤见 `../docs/火星车硬件部署与联调操作手册.md`。

## Docker 开发

构建开发镜像：

```bash
docker build -t mars-rover-jazzy -f Dockerfile .
```

从 `/home/lx/rover/mars_rover_ws` 启动一个交互式容器：

```bash
docker run --rm -it --net=host \
  -e ROS_DOMAIN_ID=42 \
  -e ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET \
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
ros2 launch mars_rover_bringup pi_bringup_serial_echo.launch.py serial_port:=/dev/mars-rover-stm32
ros2 launch mars_rover_bringup pi_bringup_real_single_wheel.launch.py serial_port:=/dev/mars-rover-stm32
ros2 launch mars_rover_bringup pi_bringup_real_full_vehicle.launch.py serial_port:=/dev/mars-rover-stm32
ros2 launch mars_rover_bringup pc_teleop.launch.py with_rviz:=false
ros2 launch mars_rover_bringup pc_teleop.launch.py with_rviz:=false speed:=0.08 turn:=0.05
```

真实硬件 arm 和复位：

```bash
ros2 service call /mars_rover/set_armed std_srvs/srv/SetBool "{data: true}"
ros2 service call /mars_rover/set_armed std_srvs/srv/SetBool "{data: false}"
ros2 service call /mars_rover/reset_safety std_srvs/srv/Trigger "{}"
```

arm 只允许在 STOP、零命令、STM32 healthy 且无锁存时成功。急停、故障、命令断流或 USB 断开后必须显式 reset、重新 arm，并重新输入运动命令。

键盘控制必须从带 TTY 的交互终端启动，例如 `docker run -it`、
`docker exec -it` 或 `ssh -t`。项目的 `keyboard_teleop` 入口会把 launch 子进程
重新连接到该控制终端；在完全后台运行且没有 TTY 时会明确报错。
