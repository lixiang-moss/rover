"""键盘控制终端适配入口。

``teleop_twist_keyboard`` 必须从真实终端读取按键。ROS 2 launch 默认不会把
父终端作为子进程的标准输入，因此本入口在启动官方键盘节点前，把控制终端
``/dev/tty`` 连接到标准输入。运动指令的生成仍完全由官方键盘包负责。
"""

import os


def attach_controlling_terminal(stdin_fd: int = 0) -> bool:
    """确保标准输入连接到当前 Linux 控制终端。

    返回 ``True`` 表示本函数完成了重定向；标准输入原本就是终端时返回
    ``False``。如果进程没有控制终端，则明确抛出异常，避免键盘节点静默失效。
    """

    if os.isatty(stdin_fd):
        return False

    try:
        terminal_fd = os.open("/dev/tty", os.O_RDONLY)
    except OSError as exc:
        raise RuntimeError(
            "Keyboard teleop requires an interactive terminal; start the launch "
            "command from docker run/exec -it or an SSH session with a TTY."
        ) from exc

    try:
        os.dup2(terminal_fd, stdin_fd)
    finally:
        os.close(terminal_fd)
    return True


def main() -> None:
    """连接控制终端并启动官方 ``teleop_twist_keyboard`` 节点。"""

    attach_controlling_terminal()

    # 延迟导入，确保官方节点读取 sys.stdin 前已经完成终端重定向。
    from teleop_twist_keyboard import main as teleop_main

    teleop_main()
