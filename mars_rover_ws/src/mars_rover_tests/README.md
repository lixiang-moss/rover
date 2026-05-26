# MARS Rover 测试说明

这个包用于记录 ROS 2 高层控制工程的验证流程。当前工程既保留无硬件 dry-run，也提供 STM32 echo、单轮真实测试和四轮真实手动控制入口。

建议在工作空间根目录执行：

```bash
colcon build
source install/setup.bash
colcon test
colcon test-result --verbose
ros2 launch mars_rover_bringup pi_bringup_dry_run.launch.py
```

常用的手动检查命令：

```bash
ros2 topic pub --once /mars_rover/drive_mode_request std_msgs/msg/String "{data: CRAB}"
ros2 topic pub --rate 5 /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.05, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"
ros2 topic echo /mars_rover/wheel_setpoints
ros2 topic echo /joint_states
```

在 `RAW_WHEEL_TEST` 模式下，`/cmd_vel.linear.x` 会被解释为当前测试轮组的驱动线速度，`/cmd_vel.angular.z` 会被解释为当前测试轮组的转向目标角。默认配置只启用 `front_left` 这一组轮子。

真实硬件相关 launch 默认都不会直接执行电机命令。只有显式设置 `hardware_enable:=true` 后，串口帧才允许顶层 `enabled=true` 和轮组 `enabled=true`。四轮真实手动控制使用：

```bash
ros2 launch mars_rover_bringup pi_bringup_real_full_vehicle.launch.py serial_port:=/dev/mars_stm32 hardware_enable:=true
```
