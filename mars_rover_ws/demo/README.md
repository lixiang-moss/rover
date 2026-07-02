# Dry-run RViz Demo

This directory is a standalone demo layer. It does not change the original ROS
packages, launch files, URDF, or project RViz config.

Run:

```bash
cd /home/lx/rover/mars_rover_ws
./demo/rover_demo.sh demo
```

What it starts inside one Docker container:

- the original dry-run launch
- an external demo-only `odom -> base_link` transform publisher
- a demo-only visual robot description published on `/demo/robot_description`
- RViz with `demo/rviz_demo.rviz`
- keyboard teleop in the current terminal

The `odom -> base_link` transform is only for RViz demonstration. It is not real
odometry and must not be used as hardware feedback.

The demo visual model preserves the original link names, joint names, joint
origins, wheel geometry, and control interfaces. It only narrows the gray base
visual so the simplified body mesh does not cover the wheel modules in RViz.

Useful commands:

```bash
./demo/rover_demo.sh verify
./demo/rover_demo.sh logs
./demo/rover_demo.sh stop
```
