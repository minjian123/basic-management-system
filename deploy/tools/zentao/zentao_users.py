# -*- coding: utf-8 -*-
"""禅道用户 API 操作（deploy/tools/zentao/zentao_users.py）

注意：禅道 21 的创建用户 API 需要配合会话 rand 做密码拼盐，不建议脚本调用；
日常建号请走 Web 界面（组织 → 用户 → 添加用户）。
"""
from zentao_client import ZentaoClient


def list_(client, **kw):
    return client.list_all("/users", **kw)


def get(client, user_id):
    return client.get(f"/users/{user_id}")


if __name__ == "__main__":  # 简单自测
    c = ZentaoClient()
    print(list_(c))
