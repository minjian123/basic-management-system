# -*- coding: utf-8 -*-
"""禅道 Web 会话操作（deploy/tools/zentao/zentao_web.py）

当 REST API 某操作不可用时（如 21.x 的 DELETE /tasks/:id 参数错位 bug、
需求创建静默失败等），改用 Web 会话调对应 Web 端点完成操作。

踩坑（禅道 21.x 实测）：
    - Web 登录必须用 GET 参数（account/password 放 query string）才能拿到会话，
      返回 {"status":"success","token":...,"user":{...}}；
      用 POST body 提交会被返回登录页（登录未建立）。
    - 登录成功拿到会话 cookie（zentaosid）后，即可调 Web 端点执行操作，
      如删除任务：index.php?m=task&t=ajax&f=delete&taskID=X（响应含「保存成功」）。
    - Web 删除走的是普通 controller task::delete($taskID)，参数正确、真正生效
      （REST 的 taskEntry::delete 参数错位删 0，不生效）。
    - 删除后仍可用 API GET /tasks/{id} 读回，返回 deleted=True 确认已删。
"""
import http.cookiejar
import json
import urllib.parse
import urllib.request

from zentao_client import ZentaoClient, ZentaoError


class WebSession:
    """禅道 Web 会话：GET 登录 + 带 cookie 调 Web 端点。"""

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
        """GET 登录，成功后返回用户信息 dict；失败抛 ZentaoError。"""
        qs = urllib.parse.urlencode({"account": self.account, "password": self.password})
        url = self.base + "/index.php?m=user&t=json&f=login&" + qs
        req = urllib.request.Request(url, method="GET")
        resp = self.opener.open(req, timeout=30)
        j = json.loads(resp.read().decode("utf-8", "replace"))
        if "token" not in j:
            raise ZentaoError(f"禅道 Web 登录失败：{json.dumps(j, ensure_ascii=False)[:300]}")
        self.user = j.get("user") or {}
        return self.user

    def request(self, path):
        """带会话调 Web 端点（path 以 / 开头），返回 (http_status, 文本)。"""
        req = urllib.request.Request(self.base + path, method="GET")
        resp = self.opener.open(req, timeout=30)
        return resp.status, resp.read().decode("utf-8", "replace")


def delete_task(client, task_id):
    """经 Web 会话删除任务（绕过 REST DELETE /tasks/:id 的 bug）。

    返回 {taskID, user, httpStatus, response, deleted}：
      deleted 为 API 读回的 deleted 字段（True=已删）。
    """
    if not isinstance(client, ZentaoClient):
        client = ZentaoClient()
    ws = WebSession(client.url, client.account, client.password)
    user = ws.login()
    status, body = ws.request(f"/index.php?m=task&t=ajax&f=delete&taskID={int(task_id)}")
    ok = "保存成功" in body
    deleted = None
    try:
        deleted = (client.get(f"/tasks/{int(task_id)}") or {}).get("deleted")
    except ZentaoError:
        pass
    return {"taskID": int(task_id), "user": (user or {}).get("account"),
            "httpStatus": status, "response": body[:200],
            "success": ok, "deleted": deleted}
