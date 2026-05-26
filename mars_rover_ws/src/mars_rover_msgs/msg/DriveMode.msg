# 当前驱动模式消息。
# 由 drive_mode_manager 发布，供运动学节点判断应该使用哪种四轮控制逻辑。

# 模式枚举：停止。
uint8 STOP=0
# 模式枚举：四轮同向平移。
uint8 CRAB=1
# 模式枚举：原地旋转。
uint8 SPIN_IN_PLACE=2
# 模式枚举：单轮组/原始轮组测试。
uint8 RAW_WHEEL_TEST=3

# 本消息生成时间。
builtin_interfaces/Time stamp
# 当前模式编号，取上面枚举值。
uint8 mode
# 模式来源，例如 drive_mode_manager、keyboard、test。
string source
# 是否处于模式切换中；当前实现通常为 false。
bool transitioning
# 人可读原因，例如 startup default、accepted request。
string reason
