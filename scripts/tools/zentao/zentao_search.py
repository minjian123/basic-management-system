# -*- coding: utf-8 -*-
"""禅道客户端过滤（scripts/tools/zentao/zentao_search.py）

禅道 22.5 任务已支持服务端过滤（GET /tasks?search=1，见 zentao_tasks.search_server），
但日期区间（deadline/est）、父任务（parent）维度服务端不支持，仍需"取全量 + 客户端筛选"。
本模块提供通用的 filter_items()，是这些维度的唯一途径：

支持维度（均为可选，传了就筛，不传不筛）：
    - name        名称模糊包含（匹配 name 或 title 字段，大小写不敏感）
    - assigned_to 指派人（精确，账号）
    - status      状态（精确，如 wait/doing/closed/finished）
    - pri         优先级（精确，1-4）
    - parent      父任务 ID（精确，>0 查子任务）
    - deadline_from / deadline_to   截止日期区间（YYYY-MM-DD，含边界）
    - est_from    / est_to          预计开始日期区间（YYYY-MM-DD，含边界）

用法：
    from zentao_search import filter_items
    items = client.fetch_all("/tasks")
    result = filter_items(items, name="接口", status="doing", assigned_to="minjian")
"""


def _norm(v):
    return str(v).lower() if v is not None else ""


def _assignee(it):
    """取指派人账号；API 里 assignedTo 可能是 dict（含 account/realname）或字符串。"""
    a = it.get("assignedTo")
    if isinstance(a, dict):
        return a.get("account") or a.get("realname") or ""
    return a or ""


def filter_items(items, name=None, assigned_to=None, status=None, pri=None,
                 parent=None, deadline_from=None, deadline_to=None,
                 est_from=None, est_to=None, **kw):
    """客户端过滤列表。返回满足全部已传条件的项（未传的条件不筛）。

    name 模糊包含（匹配 name 或 title）；assigned_to/status 精确（大小写不敏感）；
    pri/parent 数值精确；deadline/est 为日期区间（含边界）。"""
    out = []
    for it in items:
        if name and _norm(name) not in (_norm(it.get("name")) or _norm(it.get("title"))):
            continue
        if assigned_to is not None and _norm(_assignee(it)) != _norm(assigned_to):
            continue
        if status is not None and _norm(it.get("status")) != _norm(status):
            continue
        if pri is not None:
            try:
                if int(it.get("pri")) != int(pri):
                    continue
            except (TypeError, ValueError):
                pass
        if parent is not None:
            try:
                if int(it.get("parent")) != int(parent):
                    continue
            except (TypeError, ValueError):
                pass
        if deadline_from and _norm(it.get("deadline")) < _norm(deadline_from):
            continue
        if deadline_to and _norm(it.get("deadline")) > _norm(deadline_to):
            continue
        if est_from and _norm(it.get("estStarted")) < _norm(est_from):
            continue
        if est_to and _norm(it.get("estStarted")) > _norm(est_to):
            continue
        out.append(it)
    return out
