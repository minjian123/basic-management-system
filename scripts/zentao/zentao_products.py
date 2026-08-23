# -*- coding: utf-8 -*-
"""禅道产品 API 操作（scripts/zentao/zentao_products.py）"""
from zentao_client import ZentaoClient


def list_(client, **kw):
    """产品列表（取全）。"""
    return client.fetch_all("/products", **kw)


def get(client, product_id):
    return client.get(f"/products/{product_id}")


def search(client, **filters):
    """按条件查询产品（客户端过滤）。
    filters 见 zentao_search.filter_items：name/assigned_to/status 等。"""
    from zentao_search import filter_items
    return filter_items(client.fetch_all("/products"), **filters)


def create(client, name, code="", **fields):
    """创建产品；name 必填（禅道 21 下 code 可能被清空，可省略）。"""
    body = {"name": name}
    if code:
        body["code"] = code
    body.update(fields)
    return client.post("/products", body=body)


def update(client, product_id, **fields):
    return client.put(f"/products/{product_id}", body=fields)


def delete(client, product_id):
    return client.delete(f"/products/{product_id}")


if __name__ == "__main__":  # 简单自测
    c = ZentaoClient()
    print(list_(c))
