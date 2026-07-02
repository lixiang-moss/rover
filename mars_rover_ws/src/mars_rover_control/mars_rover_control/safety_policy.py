"""不依赖 ROS 运行时的安全判定和锁存状态机。"""

from dataclasses import dataclass


@dataclass
class SafetyLatch:
    """保存 arm、急停/故障锁存以及新命令门槛。"""

    armed: bool = False
    estop_latched: bool = False
    fault_latched: bool = False
    fresh_command_required: bool = False
    generation: int = 0
    last_event_reason: str = "startup"

    def _advance(self, reason: str) -> None:
        """记录一次会使旧控制命令失效的状态变化。"""

        self.generation = (self.generation + 1) & 0xFFFFFFFF
        self.last_event_reason = reason

    def require_fresh_command(self, reason: str) -> None:
        """使此前缓存的非零控制命令失效，要求先看到零命令。"""

        if not self.fresh_command_required:
            self.fresh_command_required = True
            self._advance(reason)

    def observe_zero_command(self) -> None:
        """收到新的零命令后，允许后续新非零命令进入控制链。"""

        if self.fresh_command_required:
            self.fresh_command_required = False
            self._advance("fresh zero command observed")

    def disarm(self, reason: str) -> None:
        """关闭真实输出并使旧命令失效。"""

        changed = self.armed or not self.fresh_command_required
        self.armed = False
        self.fresh_command_required = True
        if changed:
            self._advance(reason)

    def trigger_estop(self, reason: str = "software estop") -> None:
        """锁存软件急停；解除输入不会自动清除锁存。"""

        changed = not self.estop_latched or self.armed or not self.fresh_command_required
        self.estop_latched = True
        self.armed = False
        self.fresh_command_required = True
        if changed:
            self._advance(reason)

    def trigger_fault(self, reason: str) -> None:
        """锁存通信、底层或输入故障，并关闭真实输出。"""

        changed = not self.fault_latched or self.armed or not self.fresh_command_required
        self.fault_latched = True
        self.armed = False
        self.fresh_command_required = True
        if changed:
            self._advance(reason)

    def reset(
        self,
        *,
        estop_request_active: bool,
        system_healthy: bool,
        mode_is_stop: bool,
        command_is_zero: bool,
    ) -> tuple[bool, str]:
        """在安全前置条件满足时清除锁存，但保持 disarmed。"""

        if estop_request_active:
            return False, "software estop request is still active"
        if not system_healthy:
            return False, "system health check failed"
        if not mode_is_stop:
            return False, "drive mode must be STOP before reset"
        if not command_is_zero:
            return False, "command must be zero before reset"

        self.estop_latched = False
        self.fault_latched = False
        self.armed = False
        self.fresh_command_required = True
        self._advance("safety latch reset")
        return True, "safety latch reset; system remains disarmed"

    def set_armed(
        self,
        enable: bool,
        *,
        bridge_mode: str,
        system_healthy: bool,
        mode_is_stop: bool,
        mode_transitioning: bool,
        command_is_zero: bool,
    ) -> tuple[bool, str]:
        """执行带前置条件的 arm/disarm 请求。"""

        if not enable:
            self.disarm("operator disarm")
            return True, "system disarmed"
        if bridge_mode != "real_serial":
            return False, "arm is only available in real_serial mode"
        if self.estop_latched:
            return False, "software estop is latched; reset safety first"
        if self.fault_latched:
            return False, "fault is latched; reset safety first"
        if not system_healthy:
            return False, "STM32 status is not healthy"
        if mode_transitioning or not mode_is_stop:
            return False, "drive mode must be stable STOP before arm"
        if not command_is_zero:
            return False, "command must be zero before arm"

        self.armed = True
        self.fresh_command_required = True
        self._advance("operator arm")
        return True, "system armed in STOP; release zero then send a new command"


def evaluate_safety_reason(
    *,
    bridge_mode: str,
    command_timed_out: bool,
    software_estop: bool,
    stm32_estop: bool,
    stm32_fault: bool,
    stm32_timeout: bool,
    require_stm32_online: bool,
    stm32_online: bool,
    estop_latched: bool = False,
    fault_latched: bool = False,
    invalid_command: bool = False,
    mode_transitioning: bool = False,
    armed: bool = True,
    fresh_command_required: bool = False,
    mode_is_stop: bool = False,
) -> str:
    """按固定优先级返回安全原因；只有 ``ok`` 允许运动。"""

    if software_estop or estop_latched:
        return "software_estop_latched"
    if fault_latched:
        return "fault_latched"
    if invalid_command:
        return "invalid_command"
    if bridge_mode == "real_serial" and stm32_estop:
        return "stm32_estop"
    if bridge_mode == "real_serial" and stm32_fault:
        return "stm32_fault"
    if bridge_mode == "real_serial" and stm32_timeout:
        return "stm32_timeout"
    if bridge_mode == "real_serial" and require_stm32_online and not stm32_online:
        return "stm32_offline"
    if command_timed_out:
        return "cmd_timeout"
    if mode_transitioning:
        return "mode_transitioning"
    if bridge_mode == "real_serial" and not armed:
        return "disarmed"
    if fresh_command_required:
        return "fresh_command_required"
    if mode_is_stop:
        return "stop_mode"
    return "ok"
