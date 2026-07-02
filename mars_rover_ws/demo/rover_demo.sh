#!/usr/bin/env bash
set -Eeuo pipefail

IMAGE_NAME="${IMAGE_NAME:-mars-rover-jazzy}"
CONTAINER_NAME="${CONTAINER_NAME:-mars-rover-demo}"
WORKSPACE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST_UID="$(id -u)"
HOST_GID="$(id -g)"
HOST_USER="${USER:-$(id -un)}"
HOST_XAUTHORITY="${XAUTHORITY:-}"
HOST_XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-}"

ROS_SETUP='source /opt/ros/jazzy/setup.bash; source /workspace/mars_rover_ws/install/setup.bash'

BASE_DOCKER_ARGS=(
  --net=host
  -v "${WORKSPACE_DIR}:/workspace/mars_rover_ws"
  -w /workspace/mars_rover_ws
)

GUI_DOCKER_ARGS=(
  --user "${HOST_UID}:${HOST_GID}"
  -e "DISPLAY=${DISPLAY:-}"
  -e HOME=/tmp/rover-demo-home
  -e QT_X11_NO_MITSHM=1
  -e QT_QPA_PLATFORM=xcb
  -e LIBGL_ALWAYS_SOFTWARE=1
  -v /tmp/.X11-unix:/tmp/.X11-unix:rw
)

if [[ -n "${HOST_XAUTHORITY}" && -f "${HOST_XAUTHORITY}" ]]; then
  GUI_DOCKER_ARGS+=(
    -e "XAUTHORITY=${HOST_XAUTHORITY}"
    -v "${HOST_XAUTHORITY}:${HOST_XAUTHORITY}:ro"
  )
fi

if [[ -n "${HOST_XDG_RUNTIME_DIR}" && -d "${HOST_XDG_RUNTIME_DIR}" ]]; then
  GUI_DOCKER_ARGS+=(
    -e "XDG_RUNTIME_DIR=${HOST_XDG_RUNTIME_DIR}"
    -v "${HOST_XDG_RUNTIME_DIR}:${HOST_XDG_RUNTIME_DIR}:rw"
  )
else
  GUI_DOCKER_ARGS+=(-e XDG_RUNTIME_DIR=/tmp/rover-demo-runtime)
fi

usage() {
  cat <<EOF
Usage:
  ./demo/rover_demo.sh demo    Run dry-run + demo pose + RViz + keyboard control
  ./demo/rover_demo.sh verify  Run a headless movement check
  ./demo/rover_demo.sh stop    Stop the demo container
  ./demo/rover_demo.sh logs    Show dry-run/RViz/demo-pose logs

This demo does not modify the original ROS packages. It adds a temporary
odom -> base_link transform and a demo-only visual robot_description only inside
this demo container.
EOF
}

stop_demo() {
  docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
}

allow_gui() {
  if command -v xhost >/dev/null 2>&1; then
    xhost "+si:localuser:${HOST_USER}" >/dev/null 2>&1 || true
  fi
}

start_container() {
  stop_demo
  allow_gui
  docker run -d --name "${CONTAINER_NAME}" \
    "${BASE_DOCKER_ARGS[@]}" \
    "${GUI_DOCKER_ARGS[@]}" \
    "${IMAGE_NAME}" bash -lc \
    'mkdir -p "$HOME" "$XDG_RUNTIME_DIR"; chmod 700 "$HOME" "$XDG_RUNTIME_DIR"; sleep infinity' >/dev/null
}

demo_exec() {
  docker exec "${CONTAINER_NAME}" bash -lc "$1"
}

start_dry_run() {
  demo_exec "rm -f /tmp/rover_dry_run.log; (${ROS_SETUP}; ros2 launch mars_rover_bringup pi_bringup_dry_run.launch.py) >/tmp/rover_dry_run.log 2>&1 &"
  printf "Waiting for dry-run"
  for _ in {1..30}; do
    if demo_exec "grep -q 'STM32 bridge running in dry_run mode' /tmp/rover_dry_run.log 2>/dev/null"; then
      printf "\nDry-run is ready.\n"
      return 0
    fi
    printf "."
    sleep 1
  done
  printf "\nDry-run did not become ready:\n" >&2
  demo_exec "cat /tmp/rover_dry_run.log 2>/dev/null || true" >&2
  return 1
}

start_demo_pose() {
  demo_exec "rm -f /tmp/rover_demo_pose.log; (${ROS_SETUP}; python3 /workspace/mars_rover_ws/demo/dry_run_pose_demo.py) >/tmp/rover_demo_pose.log 2>&1 &"
  printf "Waiting for odom -> base_link"
  for _ in {1..30}; do
    if demo_exec "${ROS_SETUP}; timeout 2s ros2 topic echo --once /tf 2>/dev/null | grep -q 'frame_id: odom'"; then
      printf "\nDemo pose is ready.\n"
      return 0
    fi
    printf "."
    sleep 1
  done
  printf "\nDemo pose did not become ready:\n" >&2
  demo_exec "cat /tmp/rover_demo_pose.log 2>/dev/null || true" >&2
  return 1
}

start_demo_description() {
  demo_exec "rm -f /tmp/rover_demo_description.log; (${ROS_SETUP}; python3 /workspace/mars_rover_ws/demo/demo_robot_description.py) >/tmp/rover_demo_description.log 2>&1 &"
  printf "Waiting for demo robot description"
  for _ in {1..30}; do
    if demo_exec "${ROS_SETUP}; timeout 2s ros2 topic echo --once --qos-durability transient_local /demo/robot_description >/dev/null 2>&1"; then
      printf "\nDemo visual model is ready.\n"
      return 0
    fi
    printf "."
    sleep 1
  done
  printf "\nDemo visual model did not become ready:\n" >&2
  demo_exec "cat /tmp/rover_demo_description.log 2>/dev/null || true" >&2
  return 1
}

start_rviz() {
  if [[ -z "${DISPLAY:-}" ]]; then
    printf "DISPLAY is empty, so RViz cannot open a GUI window.\n" >&2
    return 1
  fi
  demo_exec "rm -f /tmp/rover_rviz.log; (${ROS_SETUP}; rviz2 -d /workspace/mars_rover_ws/demo/rviz_demo.rviz) >/tmp/rover_rviz.log 2>&1 &"
  sleep 3
  if ! demo_exec "pgrep -x rviz2 >/dev/null"; then
    printf "RViz exited early:\n" >&2
    demo_exec "cat /tmp/rover_rviz.log 2>/dev/null || true" >&2
    return 1
  fi
  printf "RViz is running.\n"
}

start_teleop() {
  docker exec -it "${CONTAINER_NAME}" bash -lc \
    "${ROS_SETUP}; ros2 topic pub --once /mars_rover/drive_mode_request std_msgs/msg/String \"{data: CRAB}\"; ros2 run teleop_twist_keyboard teleop_twist_keyboard"
}

run_demo() {
  trap stop_demo EXIT
  start_container
  start_dry_run
  start_demo_pose
  start_demo_description
  start_rviz
  printf "\nKeyboard control uses this terminal. Press i, comma, j/l, or Shift+J/L. Ctrl+C stops the demo.\n\n"
  start_teleop
}

run_verify() {
  trap stop_demo EXIT
  start_container
  start_dry_run
  start_demo_pose
  start_demo_description
  demo_exec "${ROS_SETUP}; ros2 topic pub --once /mars_rover/drive_mode_request std_msgs/msg/String '{data: CRAB}' >/dev/null"
  demo_exec "${ROS_SETUP}; ros2 topic pub --rate 10 /cmd_vel geometry_msgs/msg/Twist '{linear: {x: 0.08, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}' >/tmp/rover_verify_cmd.log 2>&1 & pub_pid=\$!; sleep 2; kill \"\$pub_pid\" 2>/dev/null || true; wait \"\$pub_pid\" 2>/dev/null || true"
  printf "Sample odom -> base_link transform after forward command:\n"
  demo_exec "${ROS_SETUP}; timeout 5s ros2 topic echo --once /tf | sed -n '/child_frame_id: base_link/,+8p'"
}

show_logs() {
  docker exec "${CONTAINER_NAME}" bash -lc \
    "printf '%s\n' '--- dry-run ---'; cat /tmp/rover_dry_run.log 2>/dev/null || true; printf '%s\n' '--- demo pose ---'; cat /tmp/rover_demo_pose.log 2>/dev/null || true; printf '%s\n' '--- demo description ---'; cat /tmp/rover_demo_description.log 2>/dev/null || true; printf '%s\n' '--- rviz ---'; cat /tmp/rover_rviz.log 2>/dev/null || true" || true
}

case "${1:-}" in
  demo)
    run_demo
    ;;
  verify)
    run_verify
    ;;
  stop)
    stop_demo
    ;;
  logs)
    show_logs
    ;;
  ""|-h|--help|help)
    usage
    ;;
  *)
    printf "Unknown command: %s\n\n" "$1" >&2
    usage
    exit 2
    ;;
esac
