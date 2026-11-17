"""帮助覆盖率台账服务（`menu_form` 域读面；08_04）。

- **数据面**：平台库元数据只读快照（复用 `list_help_anchors`），不读租户库；
- **判定面**：纯函数引擎 `bms_core.help.coverage`（命令行与接口共用，数字一致）；
- **豁免**：路径由 `[help_coverage].exemption_paths` 配置，缺省文件不存在视为空；
- **契约**：响应与命令行 `--format json` 同构。
"""

from datetime import date

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.help.coverage import (
    HelpCoverageScope,
    build_help_coverage_ledger,
    ledger_payload,
    load_help_coverage_exemptions,
)
from bms_core.repositories.help_coverage import load_help_coverage_snapshot
from bms_platform.domains.menu_form.schemas.coverage import (
    HelpCoverageCountsItem,
    HelpCoverageGroupReferenceItem,
    HelpCoverageReferenceItem,
    HelpCoverageResponse,
    HelpCoverageSummaryItem,
)

__all__ = ["HelpCoverageService"]


class HelpCoverageService(BaseFrameworkObject):
    """帮助覆盖率台账服务。"""

    def __init__(self, *, session: DbSession, exemption_paths: ConcurrentStableList[str]) -> None:
        """初始化。

        Args:
            session: 平台库只读会话（元数据 + 锚点）。
            exemption_paths: 豁免文件路径（部署配置）。
        """
        self._session = session
        self._exemption_paths = exemption_paths

    async def load(
        self,
        *,
        as_of: date,
        scope: HelpCoverageScope,
        include_reference: bool,
    ) -> HelpCoverageResponse:
        """生成覆盖率台账。

        Args:
            as_of: 判定日期。
            scope: 过滤范围。
            include_reference: 是否返回表单 / 字段参考统计。

        Returns:
            HelpCoverageResponse: 台账响应。

        Raises:
            HelpCoverageExemptionError: 豁免文件非法。
        """
        exemptions = load_help_coverage_exemptions(self._exemption_paths)
        snapshot = await load_help_coverage_snapshot(self._session)
        ledger = build_help_coverage_ledger(snapshot, as_of=as_of, exemptions=exemptions, scope=scope)
        response = HelpCoverageResponse.model_validate(ledger_payload(ledger))
        if include_reference:
            return response
        return _without_reference(response)


def _without_reference(response: HelpCoverageResponse) -> HelpCoverageResponse:
    """把参考统计置零（`include_reference=false` 时使用）。

    Args:
        response: 原响应。

    Returns:
        HelpCoverageResponse: 参考统计置零后的响应。
    """
    zero_counts = HelpCoverageCountsItem(
        total=0,
        covered=0,
        exempt=0,
        gap=0,
        coverage=1.0,
        effective_coverage=1.0,
    )
    zero_group_reference = HelpCoverageGroupReferenceItem(
        form_total=0,
        form_declared=0,
        field_total=0,
        field_declared=0,
    )
    groups = ConcurrentStableList(
        group.model_copy(update={"reference": zero_group_reference}) for group in response.groups
    )
    summary = HelpCoverageSummaryItem(
        action=response.summary.action,
        menu=response.summary.menu,
        reference=HelpCoverageReferenceItem(
            form=zero_counts,
            field=zero_counts.model_copy(),
            action_fallback=response.summary.reference.action_fallback.model_copy(
                update={"declared": 0, "total": 0, "gap": 0}
            ),
        ),
    )
    return response.model_copy(
        update={
            "summary": summary,
            "groups": ConcurrentStableList(groups),
        }
    )
