"""速度安全门、arm/disarm 服务和恢复锁存状态。"""

import copy
import math

from geometry_msgs.msg import Twist
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from std_msgs.msg import Bool, String
from std_srvs.srv import SetBool, Trigger

from mars_rover_control.constants import MODE_STOP
from mars_rover_control.safety_policy import SafetyLatch, evaluate_safety_reason
from mars_rover_msgs.msg import ControlState, DriveMode, Stm32Status


VALID_BRIDGE_MODES = {"dry_run", "serial_echo", "real_serial"}


def _zero_twist() -> Twist:
    """生成所有速度分量均为零的 Twist。"""

    return Twist()


def _clamp(value: float, limit: float) -> float:
    """把有限数值限制在正负对称边界内。"""

    return min(max(value, -limit), limit)


def _twist_is_finite(message: Twist) -> bool:
    """拒绝会传播到运动学和串口层的 NaN/Inf。"""

    values = (
        message.linear.x,
        message.linear.y,
        message.linear.z,
        message.angular.x,
        message.angular.y,
        message.angular.z,
    )
    return all(math.isfinite(float(value)) for value in values)


def _twist_is_zero(message: Twist, epsilon: float) -> bool:
    """判断与底盘运动相关的三个速度分量是否为零。"""

    return (
        abs(float(message.linear.x)) <= epsilon
        and abs(float(message.linear.y)) <= epsilon
        and abs(float(message.angular.z)) <= epsilon
    )


class SafetyGate(Node):
    """过滤速度并作为 Pi 侧真实输出授权的唯一状态来源。"""

    def __init__(self) -> None:
        """初始化参数、话题、服务以及锁存安全状态。"""

        super().__init__("safety_gate")
        self.declare_parameter("cmd_timeout_sec", 0.5)
        self.declare_parameter("max_linear_velocity", 0.10)
        self.declare_parameter("max_angular_velocity", 0.30)
        self.declare_parameter("bridge_mode", "dry_run")
        self.declare_parameter("require_stm32_online_for_real_serial", True)
        self.declare_parameter("stm32_status_timeout_sec", 0.5)
        self.declare_parameter("publish_rate_hz", 20.0)
        self.declare_parameter("zero_epsilon", 1e-6)
        self._validate_parameters()

        self._last_cmd = _zero_twist()
        self._last_cmd_time = None
        self._invalid_command = False
        self._estop_request_active = False
        self._stm32_online = False
        self._stm32_estop_active = False
        self._stm32_timeout = False
        self._stm32_fault = False
        self._stm32_serial_error = False
        self._last_stm32_status_rx_time = None
        self._mode = MODE_STOP
        self._mode_transitioning = False
        self._last_mode_signature = None
        self._latch = SafetyLatch()
        self._last_reason = "startup"

        self.create_subscription(Twist, "/cmd_vel", self._on_cmd_vel, 1)
        self.create_subscription(Bool, "/mars_rover/emergency_stop", self._on_estop, 10)
        self.create_subscription(
            Stm32Status, "/mars_rover/stm32/status", self._on_stm32_status, 10
        )
        mode_qos = QoSProfile(depth=1)
        mode_qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        self.create_subscription(
            DriveMode, "/mars_rover/drive_mode", self._on_drive_mode, mode_qos
        )

        self._safe_pub = self.create_publisher(Twist, "/mars_rover/safe_cmd_vel", 1)
        self._state_pub = self.create_publisher(String, "/mars_rover/safety_state", 10)
        self._control_state_pub = self.create_publisher(
            ControlState, "/mars_rover/control_state", 10
        )
        self.create_service(SetBool, "/mars_rover/set_armed", self._on_set_armed)
        self.create_service(Trigger, "/mars_rover/reset_safety", self._on_reset_safety)

        period = 1.0 / float(self.get_parameter("publish_rate_hz").value)
        self.create_timer(period, self._publish_safe_command)

    def _validate_parameters(self) -> None:
        """在启动时拒绝不可能安全运行的配置。"""

        bridge_mode = str(self.get_parameter("bridge_mode").value)
        if bridge_mode not in VALID_BRIDGE_MODES:
            raise ValueError(f"unsupported bridge_mode: {bridge_mode}")
        positive_parameters = (
            "cmd_timeout_sec",
            "max_linear_velocity",
            "max_angular_velocity",
            "stm32_status_timeout_sec",
            "publish_rate_hz",
            "zero_epsilon",
        )
        for name in positive_parameters:
            if float(self.get_parameter(name).value) <= 0.0:
                raise ValueError(f"{name} must be greater than zero")

    def _on_cmd_vel(self, message: Twist) -> None:
        """接收原始速度；非法数值会立即锁存故障并归零。"""

        now = self.get_clock().now()
        if not _twist_is_finite(message):
            self._invalid_command = True
            self._last_cmd = _zero_twist()
            self._last_cmd_time = now
            self._latch.trigger_fault("invalid non-finite /cmd_vel")
            return

        self._invalid_command = False
        self._last_cmd = copy.deepcopy(message)
        self._last_cmd_time = now
        if self._command_is_zero():
            self._latch.observe_zero_command()

    def _on_estop(self, message: Bool) -> None:
        """true 会锁存软件急停；false 只释放请求，不自动复位。"""

        self._estop_request_active = bool(message.data)
        if self._estop_request_active:
            self._latch.trigger_estop()

    def _on_stm32_status(self, message: Stm32Status) -> None:
        """更新底层健康状态；已 arm 时的异常会锁存并 disarm。"""

        self._last_stm32_status_rx_time = self.get_clock().now()
        self._stm32_online = bool(message.online)
        self._stm32_estop_active = bool(message.estop_active)
        self._stm32_timeout = bool(message.timeout)
        self._stm32_fault = bool(message.fault)
        self._stm32_serial_error = bool(message.serial_error)
        if self._latch.armed and not self._stm32_status_healthy():
            if self._stm32_estop_active:
                self._latch.trigger_estop("STM32 estop")
            else:
                self._latch.trigger_fault("STM32 status became unhealthy")

    def _on_drive_mode(self, message: DriveMode) -> None:
        """模式变化或过渡会使此前缓存的运动命令失效。"""

        signature = (int(message.mode), bool(message.transitioning))
        if self._last_mode_signature is not None and signature != self._last_mode_signature:
            self._latch.require_fresh_command("drive mode changed")
        self._last_mode_signature = signature
        self._mode = int(message.mode)
        self._mode_transitioning = bool(message.transitioning)

    def _command_timed_out(self) -> bool:
        """判断控制端速度流是否已经中断。"""

        if self._last_cmd_time is None:
            return True
        timeout = float(self.get_parameter("cmd_timeout_sec").value)
        age = (self.get_clock().now() - self._last_cmd_time).nanoseconds / 1e9
        return age > timeout

    def _command_is_zero(self) -> bool:
        """只有收到过明确零命令才满足 arm/reset 的零输入条件。"""

        if self._last_cmd_time is None:
            return False
        epsilon = float(self.get_parameter("zero_epsilon").value)
        return _twist_is_zero(self._last_cmd, epsilon)

    def _stm32_status_healthy(self) -> bool:
        """检查 ROS 状态消息新鲜度及底层所有联锁。"""

        if str(self.get_parameter("bridge_mode").value) != "real_serial":
            return True
        if self._last_stm32_status_rx_time is None:
            return False
        age = (
            self.get_clock().now() - self._last_stm32_status_rx_time
        ).nanoseconds / 1e9
        fresh = age <= float(self.get_parameter("stm32_status_timeout_sec").value)
        return (
            fresh
            and self._stm32_online
            and not self._stm32_estop_active
            and not self._stm32_timeout
            and not self._stm32_fault
            and not self._stm32_serial_error
        )

    def _on_set_armed(self, request: SetBool.Request, response: SetBool.Response):
        """处理带安全前置条件的 arm/disarm 请求。"""

        success, message = self._latch.set_armed(
            bool(request.data),
            bridge_mode=str(self.get_parameter("bridge_mode").value),
            system_healthy=self._stm32_status_healthy(),
            mode_is_stop=self._mode == MODE_STOP,
            mode_transitioning=self._mode_transitioning,
            command_is_zero=self._command_is_zero() and not self._command_timed_out(),
        )
        response.success = success
        response.message = message
        return response

    def _on_reset_safety(self, _request: Trigger.Request, response: Trigger.Response):
        """在 STOP、零命令和健康状态下清除锁存，保持 disarmed。"""

        success, message = self._latch.reset(
            estop_request_active=self._estop_request_active,
            system_healthy=self._stm32_status_healthy(),
            mode_is_stop=self._mode == MODE_STOP and not self._mode_transitioning,
            command_is_zero=self._command_is_zero() and not self._command_timed_out(),
        )
        response.success = success
        response.message = message
        return response

    def _publish_safe_command(self) -> None:
        """周期发布安全速度、文字原因和结构化 ControlState。"""

        bridge_mode = str(self.get_parameter("bridge_mode").value)
        command_timed_out = self._command_timed_out()
        if bridge_mode == "real_serial" and self._latch.armed:
            if command_timed_out:
                self._latch.trigger_fault("/cmd_vel stream timed out while armed")
            elif not self._stm32_status_healthy():
                self._latch.trigger_fault("STM32 status timed out while armed")

        reason = evaluate_safety_reason(
            bridge_mode=bridge_mode,
            command_timed_out=command_timed_out,
            software_estop=self._estop_request_active,
            stm32_estop=self._stm32_estop_active,
            stm32_fault=self._stm32_fault or self._stm32_serial_error,
            stm32_timeout=self._stm32_timeout,
            require_stm32_online=bool(
                self.get_parameter("require_stm32_online_for_real_serial").value
            ),
            stm32_online=self._stm32_status_healthy(),
            estop_latched=self._latch.estop_latched,
            fault_latched=self._latch.fault_latched,
            invalid_command=self._invalid_command,
            mode_transitioning=self._mode_transitioning,
            armed=self._latch.armed,
            fresh_command_required=self._latch.fresh_command_required,
            mode_is_stop=self._mode == MODE_STOP,
        )

        safe = _zero_twist()
        if reason == "ok":
            linear_limit = float(self.get_parameter("max_linear_velocity").value)
            angular_limit = float(self.get_parameter("max_angular_velocity").value)
            safe.linear.x = _clamp(self._last_cmd.linear.x, linear_limit)
            safe.linear.y = _clamp(self._last_cmd.linear.y, linear_limit)
            safe.angular.z = _clamp(self._last_cmd.angular.z, angular_limit)

        self._safe_pub.publish(safe)
        display_reason = reason
        if reason in {"fault_latched", "software_estop_latched"}:
            display_reason = f"{reason}: {self._latch.last_event_reason}"
        if display_reason != self._last_reason:
            self.get_logger().info(f"Safety state: {display_reason}")
            self._last_reason = display_reason
        self._state_pub.publish(String(data=display_reason))
        self._publish_control_state(reason, safe)

    def _publish_control_state(self, reason: str, safe: Twist) -> None:
        """把当前授权状态发布为 bridge 可直接消费的结构化消息。"""

        message = ControlState()
        message.stamp = self.get_clock().now().to_msg()
        message.armed = self._latch.armed
        message.motion_allowed = reason == "ok"
        message.fresh_command_required = self._latch.fresh_command_required
        message.estop_latched = self._latch.estop_latched
        message.fault_latched = self._latch.fault_latched
        message.generation = self._latch.generation
        message.reason = self._last_reason

        if self._latch.estop_latched:
            message.state = ControlState.ESTOP_LATCHED
        elif self._latch.fault_latched:
            message.state = ControlState.FAULT_LATCHED
        elif self._mode_transitioning:
            message.state = ControlState.TRANSITIONING
        elif reason == "ok" and not _twist_is_zero(
            safe, float(self.get_parameter("zero_epsilon").value)
        ):
            message.state = ControlState.ACTIVE
        elif self._latch.armed:
            message.state = ControlState.ARMED_IDLE
        else:
            message.state = ControlState.SAFE_STOP
        self._control_state_pub.publish(message)


def main(args=None) -> None:
    """启动 SafetyGate 并进入 ROS 2 spin。"""

    rclpy.init(args=args)
    node = SafetyGate()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    except Exception:
        if rclpy.ok():
            raise
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
