"""审计链校验（`log` 域再导出）：实现已上移基座 `bms_core.audit.verifier`（06_02）。

06_02 把校验器上移到基座——`log` 域与 `audit` 域共用同一把尺子（同一 `canonical_record`、同一
`BaseHashChain`），链校验口径不会漂移；本模块只做再导出，保持 06_01 的调用面与测试导入不变。
"""

from bms_core.audit.verifier import LOG_TYPES, AuditChainVerifier, ChainVerifyOutcome

__all__ = ["LOG_TYPES", "AuditChainVerifier", "ChainVerifyOutcome"]
