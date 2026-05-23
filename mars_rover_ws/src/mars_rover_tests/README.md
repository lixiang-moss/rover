# MARS Rover No-Hardware Test Notes

This package records the first-stage validation path for development without the rover hardware.

Recommended commands from the workspace root:

```bash
colcon build
source install/setup.bash
colcon test
colcon test-result --verbose
ros2 launch mars_rover_bringup pi_bringup_dry_run.launch.py
```

Useful manual checks:

```bash
ros2 topic pub --once /mars_rover/drive_mode_request std_msgs/msg/String "{data: CRAB}"
ros2 topic pub --rate 5 /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.05, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"
ros2 topic echo /mars_rover/wheel_setpoints
ros2 topic echo /joint_states
```

For `RAW_WHEEL_TEST`, `/cmd_vel.linear.x` is interpreted as the active wheel drive velocity and `/cmd_vel.angular.z` as the active wheel steering target. Defaults keep only `front_left` enabled.
