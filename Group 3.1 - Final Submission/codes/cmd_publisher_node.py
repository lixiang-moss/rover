import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
import subprocess
import re
import time
import sys

class CmdValPublisher(Node):
    def __init__(self):
        super().__init__('cmd_val_publisher')

        self.publisher_ = self.create_publisher(Twist, 'cmd_val', 10)
        self.timer_ = self.create_timer(0.1, self.timer_callback)

        #self.process = subprocess.Popen(
        #   ['python3', 'create_signals.py'],
        #    stdout=subprocess.PIPE,
        #    stderr=subprocess.PIPE,
        #    bufsize=1,
        #    text=True
        #)
        self.input_stream = sys.stdin

        self.latest_speed = 0.0
        self.latest_direction = 0
        self.latest_mode = 1
        self.prev_mode = 1
        self.mode_switch_time = None

    def timer_callback(self):
        line = self.input_stream.readline().strip()
        print(f"Received line: {line}")
        match = re.search(r'GET /update\?speed=(-?\d+)&direction=(-?\d+)/\?State=.*?/Mode_(\d)', line)
        if match:
            speed_raw = int(match.group(1))
            direction = int(match.group(2))
            mode = int(match.group(3))
            speed = float(speed_raw) / 100.0
            if mode != self.latest_mode:
                self.get_logger().info(f'Mode switch detected: {self.latest_mode} → {mode}')
                self.prev_mode = self.latest_mode
                self.latest_mode = mode
                self.mode_switch_time = time.time()
            self.latest_speed = speed
            self.latest_direction = direction

        msg = Twist()

        if self.mode_switch_time and (time.time() - self.mode_switch_time) < 10.0:
            msg.linear.x = 0.0
            msg.linear.y = float(self.latest_mode)
            msg.angular.z = 0.0
        else:
            msg.linear.x = self.latest_speed
            msg.linear.y = float(self.latest_mode)
            msg.angular.z = float(self.latest_direction)
            self.mode_switch_time = None

        self.publisher_.publish(msg)

def main(args=None):
    rclpy.init(args=args)
    node = CmdValPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.get_logger().info("Shutting down CmdValPublisher node.")
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
