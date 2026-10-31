"""雪花 ID 位段常量（无依赖模块，供生成器 / 存储类型 / 配置共用）。

- 位段：**48 时间 + 40 机器 + 38 序列 = 126 位**；
- 独立成模块的原因：`core/id.py` 经工厂链依赖 `core/logging` → `core/config`，
  配置需要 WorkerId 上界、模型类型需要 ID 上界，直接互引会形成循环导入；
- 本模块只放常量与派生掩码，不含逻辑（单一事实源）。
"""

EPOCH_MS = 1_600_000_000_000
"""自定义基点（约 2020-09-13 UTC），固定不变。"""

TIMESTAMP_BITS = 48
"""时间戳段位数（毫秒，约 8925 年）。"""

WORKER_BITS = 40
"""机器段位数（约 1.1 万亿个进程）。"""

SEQ_BITS = 38
"""序列段位数（约 2749 亿 ID/ms/进程）。"""

MAX_WORKER_ID = (1 << WORKER_BITS) - 1
"""WorkerId 上界（`0 ~ 2^40-1`）；配置与 WorkerId 注册共用。"""

MAX_ID = (1 << (TIMESTAMP_BITS + WORKER_BITS + SEQ_BITS)) - 1
"""雪花 ID 上界（`2^126-1`，38 位十进制）；存储类型与测试共用。"""

SEQ_MASK = (1 << SEQ_BITS) - 1
"""序列掩码（同毫秒自增回绕）。"""

WORKER_SHIFT = SEQ_BITS
"""机器段左移位数。"""

TIMESTAMP_SHIFT = SEQ_BITS + WORKER_BITS
"""时间戳段左移位数。"""

__all__ = [
    "EPOCH_MS",
    "MAX_ID",
    "MAX_WORKER_ID",
    "SEQ_BITS",
    "SEQ_MASK",
    "TIMESTAMP_BITS",
    "TIMESTAMP_SHIFT",
    "WORKER_BITS",
    "WORKER_SHIFT",
]
