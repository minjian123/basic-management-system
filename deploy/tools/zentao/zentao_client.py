# -*- coding: utf-8 -*-
"""禅道 API 客户端（BMS 项目 · deploy/tools/zentao/zentao_client.py）

禅道开源版 21.x REST API（/api.php/v1）核心客户端：
token 认证、通用请求封装、自动分页、.env 凭据读取。

用法：
    from zentao_client import ZentaoClient
    c = ZentaoClient()                      # 凭据默认从 deploy/.env 的 ZENTAO_API_* 读取
    c = ZentaoClient(account="minjian", password="xxx")   # 或显式传入（可覆盖）

凭据键（deploy/.env，.env 不入库）：
    ZENTAO_API_URL=http://192.168.0.107:8070
    ZENTAO_API_ACCOUNT=minjian
    ZENTAO_API_PASSWORD=<管理员密码>

API 要点（源码确认，禅道 21.x）：
    - 认证：POST /api.php/v1/tokens 获取 token，后续请求头 Token: <token>（不是 Bearer）
    - 错误：HTTP 4xx/5xx，响应体 JSON {"error": ...} 或 {"error": {字段: 文案}}
    - 分页：列表响应 {"page":1,"total":N,"limit":100,"<资源>":[...]}，limit 最大 100
    - 踩坑：迭代 project 走 URL 参数；任务必须走批量入口 batchCreate；
      estStarted/deadline/left 等字段必填（详见《禅道API使用说明.md》）
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API_VERSION = "v1"
_LIST_KEYS = ("tasks", "products", "projects", "executions", "stories", "users")


class ZentaoError(Exception):
    """禅道 API 调用错误（连接失败 / HTTP 错误 / 业务错误）。"""


def load_env():
    """读取 deploy/.env（脚本位于 deploy/tools/zentao/ 下，.env 在 ../../.env）。"""
    env = {}
    p = Path(__file__).resolve().parent.parent.parent / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            env[key.strip()] = val.strip()
    return env


class ZentaoClient:
    """禅道 API 客户端。线程不安全（token 懒获取并缓存），单次任务内使用即可。"""

    def __init__(self, url=None, account=None, password=None, token=None):
        env = load_env()
        self.url = (url or os.environ.get("ZENTAO_API_URL")
                    or env.get("ZENTAO_API_URL") or "http://127.0.0.1:8070").rstrip("/")
        self.account = account or os.environ.get("ZENTAO_API_ACCOUNT") or env.get("ZENTAO_API_ACCOUNT")
        self.password = password or os.environ.get("ZENTAO_API_PASSWORD") or env.get("ZENTAO_API_PASSWORD")
        self._token = token
        self.base = f"{self.url}/api.php/{API_VERSION}"

    # ---------- 认证 ----------

    def get_token(self, force=False):
        """获取（或刷新）token，结果缓存于实例。"""
        if self._token and not force:
            return self._token
        if not self.account or not self.password:
            raise ZentaoError(
                "缺少禅道账号凭据：请在 deploy/.env 配置 ZENTAO_API_ACCOUNT/ZENTAO_API_PASSWORD，"
                "或通过参数传入 account/password")
        _, body = self._raw("POST", "/tokens",
                            {"account": self.account, "password": self.password}, with_token=False)
        self._token = body.get("token")
        if not self._token:
            raise ZentaoError(f"获取禅道 token 失败：{body}")
        return self._token

    # ---------- 通用请求 ----------

    def request(self, method, path, body=None, params=None):
        """发请求并返回解析后的 JSON；HTTP/业务错误抛 ZentaoError。"""
        code, data = self._raw(method, path, body=body, params=params)
        if code >= 400 or (isinstance(data, dict) and data.get("error") is not None):
            raise ZentaoError(f"{method} {path} 失败 HTTP {code}: {json.dumps(data, ensure_ascii=False)[:400]}")
        return data

    def get(self, path, params=None):
        return self.request("GET", path, params=params)

    def post(self, path, body=None, params=None):
        return self.request("POST", path, body=body, params=params)

    def put(self, path, body=None, params=None):
        return self.request("PUT", path, body=body, params=params)

    def delete(self, path, params=None):
        return self.request("DELETE", path, params=params)

    def list_all(self, path, page_size=100, **params):
        """自动翻页拉取列表；响应非列表结构时原样返回。"""
        page = 1
        collected = []
        while True:
            p = dict(params, page=page, limit=page_size)
            data = self.get(path, params=p)
            items = None
            for key in _LIST_KEYS:
                if isinstance(data, dict) and isinstance(data.get(key), list):
                    items = data[key]
                    break
            if items is None:
                return data
            collected.extend(items)
            total = data.get("total")
            if total is None or page * page_size >= int(total):
                return collected
            page += 1

    # ---------- 内部 ----------

    def _endpoint(self, path):
        return self.base + (path if path.startswith("/") else "/" + path)

    def _raw(self, method, path, body=None, with_token=True, params=None):
        url = self._endpoint(path)
        if params:
            qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            if qs:
                url += ("&" if "?" in url else "?") + qs
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if with_token:
            req.add_header("Token", self.get_token())
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                text = resp.read().decode("utf-8")
                return resp.status, (json.loads(text) if text else None)
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8")
            try:
                return e.code, json.loads(text)
            except Exception:
                raise ZentaoError(f"HTTP {e.code}: {text[:400]}") from e
        except urllib.error.URLError as e:
            raise ZentaoError(f"连接禅道失败（{self.url}）：{e.reason}") from e
