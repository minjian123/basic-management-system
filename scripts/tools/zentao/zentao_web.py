# -*- coding: utf-8 -*-
"""禅道 Web 会话操作（scripts/tools/zentao/zentao_web.py）

当 REST API 某操作不可用时（如 DELETE /tasks/:id 参数错位 bug，22.5 仍在），
改用 Web 会话调对应 Web 端点完成操作。story/user 的删除 REST 在 22.5 已可用，
本模块仅作 task 删除与 Web 端点备用通道。

踩坑（禅道 22.5 实测）：
    - Web 登录必须用 GET 参数（account/password 放 query string）才能拿到会话，
      返回 {"status":"success","token":...,"user":{...}}；
      用 POST body 提交会被返回登录页（登录未建立）。
    - 登录成功拿到会话 cookie（zentaosid）后，即可调 Web 端点执行操作，
      删除端点统一为：index.php?m={模块}&t=ajax&f=delete&{模块}ID={id}
      （task 已验证：响应含「保存成功」；其他资源同一约定，首次用建议先验证）。
    - Web 删除走的是普通 controller（task::delete($taskID)），参数正确、真正生效；
      REST 的 taskEntry::delete 参数错位删 0，不生效。
    - 删除后仍可用 API GET /tasks/{id} 读回，返回 deleted=True 确认已删。
    - story 的 Web 删除（story::delete）默认 confirm=no 只返回确认弹窗（result:fail），
      必须加 confirm=yes 参数才真正删除；task 的 delete 无此确认步骤。
    - 批量删除应复用同一次登录会话（web_delete_many），避免重复登录（也避免触发登录锁定）。
"""
import http.cookiejar
import json
import urllib.parse
import urllib.request

from zentao_client import ZentaoClient, ZentaoError


class WebSession:
    """禅道 Web 会话：GET 登录 + 带 cookie 调 Web 端点。登录一次可复用多次操作。"""

    def __init__(self, base, account, password):
        if not account or not password:
            raise ZentaoError("Web 会话需要账号密码（deploy/.env 的 ZENTAO_API_ACCOUNT/ZENTAO_API_PASSWORD）")
        self.base = base.rstrip("/")
        self.account = account
        self.password = password
        cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        self.opener.addheaders = [("User-Agent", "bms-zentao-tool/1.0")]
        self.user = None

    def login(self):
        """GET 登录，成功后返回用户信息 dict；失败抛 ZentaoError。成功后可复用多次 request。"""
        qs = urllib.parse.urlencode({"account": self.account, "password": self.password})
        url = self.base + "/index.php?m=user&t=json&f=login&" + qs
        req = urllib.request.Request(url, method="GET")
        resp = self.opener.open(req, timeout=30)
        j = json.loads(resp.read().decode("utf-8", "replace"))
        if "token" not in j:
            raise ZentaoError(f"禅道 Web 登录失败：{json.dumps(j, ensure_ascii=False)[:300]}")
        self.user = j.get("user") or {}
        return self.user

    def request(self, path, data=None):
        """带会话调 Web 端点（path 以 / 开头），返回 (http_status, 文本)。

        data 为 dict 时以 POST 表单提交（application/x-www-form-urlencoded）。"""
        body = urllib.parse.urlencode(data).encode() if isinstance(data, dict) else None
        req = urllib.request.Request(self.base + path, data=body, method="POST" if body else "GET")
        resp = self.opener.open(req, timeout=30)
        return resp.status, resp.read().decode("utf-8", "replace")


def _as_ids(v):
    """把 单个id / int / 逗号分隔串 / 列表 统一为 int 列表。"""
    if v is None:
        return []
    if isinstance(v, (int, float)):
        return [int(v)]
    if isinstance(v, str):
        return [int(x) for x in v.split(",") if x.strip()]
    return [int(x) for x in v]


def _open_session(client):
    if not isinstance(client, ZentaoClient):
        client = ZentaoClient()
    return WebSession(client.url, client.account, client.password), client


def _delete_url(module, id):
    return f"/index.php?m={module}&t=ajax&f=delete&{module}ID={int(id)}"


def web_delete(client, module, id):
    """通用 Web 删除（单个，任意资源：task/story/product/project/execution）。

    module: 禅道模块名（task/story/product/project/execution 等）。
    返回 {module, id, user, httpStatus, success, response}。"""
    ws, _ = _open_session(client)
    user = ws.login()
    status, body = ws.request(_delete_url(module, id))
    return {"module": module, "id": int(id), "user": (user or {}).get("account"),
            "httpStatus": status, "success": "保存成功" in body, "response": body[:200]}


def web_delete_many(client, module, ids):
    """通用 Web 批量删除（复用同一次登录会话，只登录一次）。

    ids: 单个 id 或 id 列表（也接受逗号分隔字符串）。
    返回 {module, user, results:[{id, httpStatus, success, response}, ...]}。"""
    ws, _ = _open_session(client)
    user = ws.login()
    results = []
    for i in _as_ids(ids):
        status, body = ws.request(_delete_url(module, i))
        results.append({"id": i, "httpStatus": status,
                        "success": "保存成功" in body, "response": body[:200]})
    return {"module": module, "user": (user or {}).get("account"), "results": results}


def web_close_task(client, task_id, reason="done"):
    """经 Web 表单关闭任务（REST POST /tasks/:id/close 返回 200 但不生效，改用此函数）。

    reason: 禅道 closedReason 枚举（done/cancel/done+closed 等常规用 done）。
    返回 {id, user, httpStatus, response}；调用后以 API 查询 status=closed 复核。"""
    ws, _ = _open_session(client)
    user = ws.login()
    status, body = ws.request(f"/task-close-{int(task_id)}.json", data={"closedReason": reason})
    return {"id": int(task_id), "user": (user or {}).get("account"),
            "httpStatus": status, "response": body[:200]}


def delete_task(client, task_id):
    """经 Web 会话删除任务（REST DELETE /tasks/:id 有 bug 不生效，改用此函数）。

    task_id: 单个 id 或 id 列表（批量时复用同一登录会话）。
    返回 {user, results:[{taskID, success, deleted, httpStatus, response}, ...]}，
    deleted 为 API 读回的 deleted 字段（True=已删）。"""
    c = client if isinstance(client, ZentaoClient) else ZentaoClient()
    r = web_delete_many(c, "task", task_id)
    for item in r["results"]:
        try:
            item["deleted"] = (c.get(f"/tasks/{item['id']}") or {}).get("deleted")
        except ZentaoError:
            item["deleted"] = None
        item["taskID"] = item.pop("id")
    return r
