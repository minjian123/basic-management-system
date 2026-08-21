# -*- coding: utf-8 -*-
"""禅道项目 API 操作（deploy/tools/zentao/zentao_projects.py）

项目类型 model：scrum（迭代式，默认）/ kanban / waterfall / waterfallplus。
创建必填：name、begin、end、products（关联产品 ID 数组，如 [1]）。
"""
from zentao_client import ZentaoClient


def list_(client, **kw):
    return client.list_all("/projects", **kw)


def get(client, project_id):
    return client.get(f"/projects/{project_id}")


def create(client, name, begin, end, products, model="scrum", code="", **fields):
    """创建项目；products 为产品 ID 列表（必填）。"""
    body = {"name": name, "begin": begin, "end": end,
            "products": list(products), "model": model}
    if code:
        body["code"] = code
    body.update(fields)
    return client.post("/projects", body=body)


def update(client, project_id, **fields):
    return client.put(f"/projects/{project_id}", body=fields)


def delete(client, project_id):
    return client.delete(f"/projects/{project_id}")


if __name__ == "__main__":  # 简单自测
    c = ZentaoClient()
    print(list_(c))
