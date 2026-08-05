"""雪花 ID 生成器。

vendor 自 yitter/IdGenerator（MIT 许可，Python/source 源码保持原样，见 idregister.py 等文件）。
对外只暴露 DefaultIdGenerator 与 IdGeneratorOptions 两个类型；
worker_id 自动注册（Redis 分配）留待阶段八。
"""

from .generator import DefaultIdGenerator
from .options import IdGeneratorOptions

__all__ = ["DefaultIdGenerator", "IdGeneratorOptions"]
