# MARS Rover ROS 2 Workspace

This workspace implements the first-stage ROS 2 Jazzy high-level control stack described in `../docs`.

The current implementation is designed for development without hardware:

- `dry_run` does not open a serial port.
- `/mars_rover/wheel_states` and `/joint_states` are target echoes, not real feedback.
- `serial_echo` and `real_serial` entry points exist, but hardware behavior is not validated here.

## Docker Development

Build the development image:

```bash
docker build -t mars-rover-jazzy -f Dockerfile .
```

Run an interactive container from `/home/lx/rover/mars_rover_ws`:

```bash
docker run --rm -it --net=host \
  -v "$PWD":/workspace/mars_rover_ws \
  -w /workspace/mars_rover_ws \
  mars-rover-jazzy
```

Inside the container:

```bash
colcon build
source install/setup.bash
colcon test
colcon test-result --verbose
ros2 launch mars_rover_bringup pi_bringup_dry_run.launch.py
```
