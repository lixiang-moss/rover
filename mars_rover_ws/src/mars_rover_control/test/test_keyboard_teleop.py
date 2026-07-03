"""键盘控制终端适配函数测试。"""

from mars_rover_control import keyboard_teleop


def test_existing_terminal_is_kept(monkeypatch):
    """标准输入已经是终端时不应重复打开或替换文件描述符。"""

    monkeypatch.setattr(keyboard_teleop.os, "isatty", lambda _fd: True)

    assert keyboard_teleop.attach_controlling_terminal(7) is False


def test_non_terminal_stdin_is_attached_to_dev_tty(monkeypatch):
    """标准输入不是终端时应使用 /dev/tty 替换它并关闭临时描述符。"""

    calls = []
    monkeypatch.setattr(keyboard_teleop.os, "isatty", lambda _fd: False)
    monkeypatch.setattr(
        keyboard_teleop.os,
        "open",
        lambda path, flags: calls.append(("open", path, flags)) or 99,
    )
    monkeypatch.setattr(
        keyboard_teleop.os,
        "dup2",
        lambda source, target: calls.append(("dup2", source, target)),
    )
    monkeypatch.setattr(
        keyboard_teleop.os,
        "close",
        lambda fd: calls.append(("close", fd)),
    )

    assert keyboard_teleop.attach_controlling_terminal(7) is True
    assert calls == [
        ("open", "/dev/tty", keyboard_teleop.os.O_RDONLY),
        ("dup2", 99, 7),
        ("close", 99),
    ]
