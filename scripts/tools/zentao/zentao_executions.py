# -*- coding: utf-8 -*-
"""禅道迭代（执行 execution）API 操作（scripts/tools/zentao/zentao_executions.py）

踩坑（源码确认）：创建迭代时 project 必须走 URL 参数（body 里的 project 会被覆盖）。
"""
from zentao_client import ZentaoClient


def list_(client, project=None, **kw):
    """迭代列表；传 project 则过滤该项目下的迭代。

    注意：/projects/:id/executions 仅返回项目根执行（子迭代不出现），
    因此统一走 /executions?status=all 再按 project 过滤。
    """
    items = client.list_all("/executions", status="all", **kw)
    if project:
        items = [e for e in items if e.get("project") == project]
    return items


def get(client, execution_id):
    return client.get(f"/executions/{execution_id}")


def create(client, project, name, begin, end, **fields):
    """创建迭代；project 走 URL 参数，name/begin/end 必填。"""
    return client.post("/executions", body={"name": name, "begin": begin, "end": end, **fields},
                       params={"project": project})


def update(client, execution_id, **fields):
    return client.put(f"/executions/{execution_id}", body=fields)


def close(client, execution_id):
    """关闭迭代（doing -> closed）。

    踩坑：无专用 close 端点（POST /executions/:id/close 返回 404 not found），
    用 PUT /executions/:id 更新 status=closed 生效（22.5 实测）。"""
    return client.put(f"/executions/{execution_id}", body={"status": "closed"})


def delete(client, execution_id):
    return client.delete(f"/executions/{execution_id}")


if __name__ == "__main__":  # 简单自测
    c = ZentaoClient()
    print(list_(c, project=1))
