"""健康检查路由：/healthz 存活探针（契约细化归 02-4）。"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """存活检查端点。

    Returns:
        dict: 服务状态，固定返回 {"status": "ok"}。
    """
    return {"status": "ok"}
