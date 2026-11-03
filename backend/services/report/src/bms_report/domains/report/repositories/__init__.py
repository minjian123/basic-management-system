"""报表域仓储：导出到域内的作业记录只读 + 产物标记（04_03）。"""

from bms_report.domains.report.repositories.job import JobArtifact, PrintJobRepository

__all__ = ["JobArtifact", "PrintJobRepository"]
