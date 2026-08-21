# -*- coding: utf-8 -*-
"""禅道用户 user API 操作（deploy/tools/zentao/zentao_users.py）

创建（22.5 实测可用）：account、password、realname、role、gender 必填，
gender 不传会被 API 以「『性别』不能为空」拒绝；gender 取值 m（男）/ f（女）。
删除（22.5 实测可用）：REST DELETE /users/:id，响应 {"message": "success"}。
"""
from zentao_client import ZentaoClient


def list_(client, full=False, **kw):
    """用户列表（取全）。full=True 时加 full=1 返回全字段（22.5 支持：
    id/dept/role/email/joined 等；默认只返回 account/realname/role 等基础字段）。"""
    if full:
        kw["full"] = "1"
    return client.list_all("/users", **kw)


def get(client, user_id):
    return client.get(f"/users/{user_id}")


def create(client, account, password, realname, role="dev", gender=None, **fields):
    """创建用户；account/password/realname/gender 必填（gender 缺省会触发 API 校验错）。"""
    if not gender:
        raise ValueError("gender 必填：m（男）或 f（女）")
    return client.post("/users",
                       body={"account": account, "password": password,
                             "realname": realname, "role": role, "gender": gender, **fields})


def delete(client, user_id):
    """删除用户（REST DELETE，22.5 实测生效）。"""
    return client.delete(f"/users/{user_id}")


if __name__ == "__main__":  # 简单自测
    c = ZentaoClient()
    print(list_(c))
