# -*- coding: utf-8 -*-
"""禅道任务 API 操作（scripts/zentao/zentao_tasks.py）

查询（22.5 实测）：
    - 服务端过滤用 search_server()：GET /tasks?search=1，支持
      pri/assignedTo(账号名)/status/id（均可逗号列表 IN）与 name（LIKE 模糊），
      分页 limit（无上限）/page/order，mergeChildren=1 子任务并入父任务。
    - 不带 search=1 的 GET /tasks 是「我的任务」分支，limit/page 仍失效（21.x 怪癖残留），
      取全量请走 search_server() 或 list_()（fetch_all）。
    - 客户端过滤 search()（取全 + filter_items）仍可用，且支持服务端不支持的
      日期区间（deadline/est）与父任务（parent）维度。

踩坑（源码确认）：
    - 创建任务必须走批量入口 /executions/{id}/tasks/batchCreate
      （/tasks/{id} 路由到单数 entry，无 POST 方法，请求返回 200 空体且不建任务）
    - 批量任务必填 estStarted、deadline；指派必填 left（预计剩余）
    - 完成任务必填 currentConsumed、realStarted、finishedDate
    - 子任务：父任务 ID 走 URL 参数 ?task={父id}，body 里写 parent 无效
      （taskBatchCreate entry 读 URL 参数 task 传给 controller，
        buildTasksForBatchCreate 内 $task->parent = $taskID 强制覆盖 body 的 parent）
    - 删除任务 API 有 bug：taskEntry::delete 调 $control->delete(0, $taskID, 'true')
      参数错位，controller 收到 $taskID=0，实际空操作却返回 success；
      删除请改用 web_delete()（经 Web 会话调 Web 端点，见 zentao_web.py）
"""
import datetime

from zentao_client import ZentaoClient


def list_(client, execution=None, **kw):
    """任务列表（取全）；传 execution 则取该迭代下的任务。"""
    path = f"/executions/{execution}/tasks" if execution else "/tasks"
    return client.fetch_all(path, **kw)


def get(client, task_id):
    return client.get(f"/tasks/{task_id}")


def search_server(client, name=None, assigned_to=None, status=None, pri=None,
                  ids=None, limit=10000, page=1, order="id_desc", merge_children=False):
    """服务端过滤查询任务（22.5 实测；GET /tasks?search=1，推荐优先用本函数）。

    过滤维度（均可选，传了就筛）：
        name        名称模糊（LIKE %name%）
        assigned_to 指派人账号（IN 列表，可逗号分隔多账号；注意是账号名不是用户 ID）
        status      状态（IN 列表，全集见文档 4.1：wait/doing/done/pause/cancel/closed）
        pri         优先级（IN 列表：1-4）
        ids         任务 ID（IN 列表，逗号分隔或 list）
    分页：limit（22.5 无上限，默认 10000 一次取全）/page（真页码）；order 如 id_desc/id_asc/pri_asc。
    merge_children=True 时子任务并入父任务 children（total 只计顶层）。
    返回原始响应 dict：{"total","page","limit","tasks":[...]}。

    不支持日期区间与父任务维度——那两种需求用 search()（客户端过滤）。"""
    params = {"search": "1", "limit": limit, "page": page, "order": order}
    if merge_children:
        params["mergeChildren"] = "1"
    for key, val in (("name", name), ("assignedTo", assigned_to),
                     ("status", status), ("pri", pri)):
        if val:
            if isinstance(val, (list, tuple)):
                val = ",".join(str(v) for v in val)
            params[key] = val
    if ids:
        if isinstance(ids, (list, tuple)):
            ids = ",".join(str(v) for v in ids)
        params["id"] = ids
    return client.get("/tasks", params=params)


def search(client, execution=None, **filters):
    """按条件查询任务（客户端过滤：取全 + 筛选）。

    22.5 起服务端过滤可用 search_server()（name/assigned_to/status/pri/ids）；
    本函数额外支持服务端没有的维度：parent（父任务）、deadline_from/deadline_to、
    est_from/est_to（日期区间）。execution 指定迭代（不传则全局）。
    filters 见 zentao_search.filter_items。返回满足条件的任务列表。"""
    from zentao_search import filter_items
    path = f"/executions/{execution}/tasks" if execution else "/tasks"
    return filter_items(client.fetch_all(path), **filters)


def batch_create(client, execution, tasks, parent=0):
    """批量创建任务（唯一创建入口）。

    tasks: [{"name": "任务名", "estimate": 16, "estStarted": "2026-08-24",
             "deadline": "2026-09-07", "pri": 2, "type": "devel", ...}, ...]
    每项至少 name/type；estStarted/deadline 必填（可用迭代起止日期）。
    parent: 父任务 ID（>0 时本次所建任务均挂为该父任务的子任务）；
      走 URL 参数 task（禅道 21.x 源码：body 里写 parent 会被 URL 参数覆盖，无效）。
    返回创建后的任务列表（统一为 list；禅道可能返回 {id: {...}} 的 dict）。
    """
    params = {"task": parent} if parent else None
    data = client.post(f"/executions/{execution}/tasks/batchCreate",
                       body={"tasks": list(tasks)}, params=params)
    result = (data or {}).get("task") or []
    if isinstance(result, dict):
        result = list(result.values())
    return result


def create(client, execution, name, estimate=0, est_started=None, deadline=None,
           pri=2, type_="devel", parent=0, **fields):
    """创建单个任务（内部走批量入口）。est_started/deadline 建议传迭代起止日期。
    parent>0 时创建为该父任务的子任务。"""
    return batch_create(client, execution, [{
        "name": name, "type": type_, "pri": pri, "estimate": estimate,
        "estStarted": est_started, "deadline": deadline, **fields,
    }], parent=parent)


def update(client, task_id, **fields):
    """编辑任务（PUT /tasks/:id，可改 name/pri/estimate/left/assignedTo/estStarted/deadline/status 等）。"""
    return client.put(f"/tasks/{task_id}", body=fields)


def delete(client, task_id):
    """删除任务。注意：禅道 21.x 的 DELETE /tasks/:id 有参数错位 bug，
    实际删的是空操作（$taskID=0）却返回 success，任务不会被真正删除。
    本函数保留接口但不可靠，删除请改用 web_delete()。"""
    return client.delete(f"/tasks/{task_id}")


def web_delete(client, task_id):
    """经禅道 Web 会话删除任务（推荐；REST DELETE /tasks/:id 有 bug 不生效）。

    task_id: 单个 id 或 id 列表（批量时复用同一登录会话，只登录一次）。
    走 Web 端点 index.php?m=task&t=ajax&f=delete&taskID=X（普通 controller，
    参数正确、真正生效），并用 API 读回 deleted 确认。
    返回 {user, results:[{taskID, success, deleted, httpStatus, response}, ...]}。"""
    from zentao_web import delete_task
    return delete_task(client, task_id)


def assign(client, task_id, assigned_to, left=None):
    """指派任务；left（预计剩余）必填，默认取任务 estimate。"""
    task = get(client, task_id)
    body = {"assignedTo": assigned_to,
            "left": left if left is not None else (task.get("estimate") or 1)}
    return client.post(f"/tasks/{task_id}/assignto", body=body)


def start(client, task_id, real_started=None, left=None):
    """开始任务（wait -> doing）。

    注意：禅道 start 端点按「请求体里的 left」校验，不带 left 会被当 0，
    报「总计消耗和预计剩余不能同时为0」。故未传 left 时自动取任务 estimate。
    """
    body = {}
    if real_started:
        body["realStarted"] = real_started
    body["left"] = left if left is not None else (get(client, task_id).get("estimate") or 1)
    return client.post(f"/tasks/{task_id}/start", body=body)


def finish(client, task_id, consumed, real_started=None, finished_date=None):
    """完成任务；currentConsumed/realStarted/finishedDate 必填（默认今天当前时刻）。

    踩坑：real_started/finished_date 传纯日期（YYYY-MM-DD）会被服务端按东八区零点
    转 UTC 存储并与另一字段的解析值比较，触发「实际完成不能小于实际开始」HTTP 400；
    必须传完整时间戳 YYYY-MM-DD HH:MM:SS。
    """
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    body = {"currentConsumed": consumed,
            "realStarted": real_started or now,
            "finishedDate": finished_date or now}
    return client.post(f"/tasks/{task_id}/finish", body=body)


def close(client, task_id, closed_reason="done"):
    """关闭任务（done -> closed）。

    踩坑：body 为空时 REST 返回 200 任务对象但不生效（静默失败，与删除 API 同类问题）；
    必须 POST closedReason（枚举 done/cancel 等）；部分场景仅 closedReason 仍静默失败，
    建议同时带 comment 字段。"""
    return client.post(f"/tasks/{task_id}/close",
                       body={"closedReason": closed_reason, "comment": ""})


def active(client, task_id, left=None):
    """激活任务（closed -> doing，重新打开以继续处理）。

    踩坑：POST /tasks/:id/active 返回 200 但不生效（静默失败，与删除 API 同类）；
    禅道重开已关闭任务须 PUT /tasks/:id 更新 status，且 doing 态要求 left>0、
    须清空 closedReason（22.5 实测）。left 缺省取「预计-已耗」的最小 1 小时。
    """
    task = get(client, task_id)
    if task.get("status") != "closed":
        raise ValueError(f"任务 {task_id} 当前为 {task.get('status')} 态，仅 closed 态可激活")
    if left is None:
        try:
            left = max(float(task.get("estimate") or 0) - float(task.get("consumed") or 0), 1)
        except (TypeError, ValueError):
            left = 1
    return client.put(f"/tasks/{task_id}", body={"status": "doing", "left": left, "closedReason": ""})


if __name__ == "__main__":  # 简单自测
    c = ZentaoClient()
    print(list_(c, execution=3))
