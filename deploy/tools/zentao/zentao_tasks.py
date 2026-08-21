# -*- coding: utf-8 -*-
"""禅道任务 API 操作（deploy/tools/zentao/zentao_tasks.py）

踩坑（源码确认，禅道 21.x）：
    - 创建任务必须走批量入口 /executions/{id}/tasks/batchCreate
      （/tasks/{id} 路由到单数 entry，无 POST 方法，请求返回 200 空体且不建任务）
    - 批量任务必填 estStarted、deadline；指派必填 left（预计剩余）
    - 完成任务必填 currentConsumed、realStarted、finishedDate
    - 子任务：父任务 ID 走 URL 参数 ?task={父id}，body 里写 parent 无效
      （taskBatchCreate entry 读 URL 参数 task 传给 controller，
        buildTasksForBatchCreate 内 $task->parent = $taskID 强制覆盖 body 的 parent）
    - 删除任务 API 有 bug：taskEntry::delete 调 $control->delete(0, $taskID, 'true')
      参数错位，controller 收到 $taskID=0，实际空操作却返回 success；
      删除请走 Web 界面
"""
import datetime

from zentao_client import ZentaoClient


def list_(client, execution=None, **kw):
    """任务列表；传 execution 则取该迭代下的任务。"""
    if execution:
        return client.list_all(f"/executions/{execution}/tasks", **kw)
    return client.list_all("/tasks", **kw)


def get(client, task_id):
    return client.get(f"/tasks/{task_id}")


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
    本函数保留接口但不可靠，删除请走禅道 Web 界面。"""
    return client.delete(f"/tasks/{task_id}")


def assign(client, task_id, assigned_to, left=None):
    """指派任务；left（预计剩余）必填，默认取任务 estimate。"""
    task = get(client, task_id)
    body = {"assignedTo": assigned_to,
            "left": left if left is not None else (task.get("estimate") or 1)}
    return client.post(f"/tasks/{task_id}/assignto", body=body)


def start(client, task_id, real_started=None):
    """开始任务（开始后状态 wait -> doing）。"""
    body = {}
    if real_started:
        body["realStarted"] = real_started
    return client.post(f"/tasks/{task_id}/start", body=body)


def finish(client, task_id, consumed, real_started=None, finished_date=None):
    """完成任务；currentConsumed/realStarted/finishedDate 必填（默认今天）。"""
    today = datetime.date.today().isoformat()
    body = {"currentConsumed": consumed, "realStarted": real_started or today,
            "finishedDate": finished_date or today}
    return client.post(f"/tasks/{task_id}/finish", body=body)


def close(client, task_id):
    return client.post(f"/tasks/{task_id}/close", body={})


def active(client, task_id):
    """激活任务（closed -> active）。"""
    return client.post(f"/tasks/{task_id}/active", body={})


if __name__ == "__main__":  # 简单自测
    c = ZentaoClient()
    print(list_(c, execution=3))
