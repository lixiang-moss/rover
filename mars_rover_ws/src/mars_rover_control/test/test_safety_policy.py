"""安全门纯逻辑测试。"""

import pytest

from mars_rover_control.safety_policy import SafetyLatch, evaluate_safety_reason


BASE = {
    "bridge_mode": "real_serial",
    "command_timed_out": False,
    "software_estop": False,
    "stm32_estop": False,
    "stm32_fault": False,
    "stm32_timeout": False,
    "require_stm32_online": True,
    "stm32_online": True,
}


def reason(**overrides):
    """用默认安全状态调用判定函数。"""

    values = {**BASE, **overrides}
    return evaluate_safety_reason(**values)


def test_all_clear_allows_command():
    """所有联锁均正常时才返回 ok。"""

    assert reason() == "ok"


@pytest.mark.parametrize(
    "field, expected",
    [
        ("software_estop", "software_estop_latched"),
        ("stm32_estop", "stm32_estop"),
        ("stm32_fault", "stm32_fault"),
        ("stm32_timeout", "stm32_timeout"),
        ("command_timed_out", "cmd_timeout"),
    ],
)
def test_each_safety_condition_stops_real_serial(field, expected):
    """每个安全条件都必须产生非 ok 的停止原因。"""

    assert reason(**{field: True}) == expected


def test_offline_stops_when_online_is_required():
    """真实串口模式要求 STM32 在线时，离线必须阻止命令。"""

    assert reason(stm32_online=False) == "stm32_offline"


def test_dry_run_ignores_stm32_hardware_state_but_not_command_timeout():
    """dry-run 不依赖硬件状态，但仍执行 ROS 控制命令超时。"""

    assert reason(
        bridge_mode="dry_run",
        stm32_online=False,
        stm32_fault=True,
        stm32_estop=True,
        stm32_timeout=True,
    ) == "ok"
    assert reason(bridge_mode="dry_run", command_timed_out=True) == "cmd_timeout"


def test_estop_has_priority_over_fault_and_timeout():
    """同时出现多个条件时返回最紧急、最明确的原因。"""

    assert reason(
        software_estop=True,
        stm32_estop=True,
        stm32_fault=True,
        stm32_timeout=True,
        command_timed_out=True,
    ) == "software_estop_latched"


def test_arm_requires_real_serial_stop_zero_command_and_healthy_status():
    """arm 服务的所有前置条件必须同时满足。"""

    latch = SafetyLatch()
    success, _ = latch.set_armed(
        True,
        bridge_mode="real_serial",
        system_healthy=True,
        mode_is_stop=True,
        mode_transitioning=False,
        command_is_zero=True,
    )
    assert success
    assert latch.armed
    assert latch.fresh_command_required


def test_estop_release_does_not_clear_latch_or_restore_arm():
    """急停输入恢复 false 后仍必须显式 reset 和重新 arm。"""

    latch = SafetyLatch(armed=True)
    latch.trigger_estop()
    assert latch.estop_latched
    assert not latch.armed

    success, _ = latch.reset(
        estop_request_active=True,
        system_healthy=True,
        mode_is_stop=True,
        command_is_zero=True,
    )
    assert not success
    assert latch.estop_latched

    success, _ = latch.reset(
        estop_request_active=False,
        system_healthy=True,
        mode_is_stop=True,
        command_is_zero=True,
    )
    assert success
    assert not latch.estop_latched
    assert not latch.armed


def test_fault_recovery_requires_reset_rearm_and_new_zero_command():
    """通信恢复本身不能自动继续旧运动。"""

    latch = SafetyLatch(armed=True)
    latch.trigger_fault("USB disconnected")
    assert latch.fault_latched
    assert not latch.armed

    success, _ = latch.reset(
        estop_request_active=False,
        system_healthy=True,
        mode_is_stop=True,
        command_is_zero=True,
    )
    assert success
    success, _ = latch.set_armed(
        True,
        bridge_mode="real_serial",
        system_healthy=True,
        mode_is_stop=True,
        mode_transitioning=False,
        command_is_zero=True,
    )
    assert success
    assert latch.fresh_command_required
    latch.observe_zero_command()
    assert not latch.fresh_command_required


def test_mode_change_invalidates_previously_cached_command():
    """模式变化后必须先看到新的零命令。"""

    latch = SafetyLatch(armed=True)
    latch.require_fresh_command("drive mode changed")
    assert latch.fresh_command_required
    latch.observe_zero_command()
    assert not latch.fresh_command_required
