# -*- coding: utf-8 -*-
"""禅道需求 story API 操作（deploy/tools/zentao/zentao_stories.py）

创建必填：title、spec、pri（1-4）、category。
category 枚举（禅道 21）：feature 功能 / interface 接口 / performance 性能 /
safe 安全 / experience 体验 / improve 改进 / other 其他。
"""
from zentao_client import ZentaoClient

CATEGORIES = ("feature", "interface", "performance", "safe", "experience", "improve", "other")


def list_(client, product=None, **kw):
    """需求列表；传 product 则取该产品下的需求。"""
    if product:
        return client.list_all(f"/products/{product}/stories", **kw)
    return client.list_all("/stories", **kw)


def get(client, story_id):
    return client.get(f"/stories/{story_id}")


def create(client, product, title, pri=2, category="feature", spec="", **fields):
    """创建需求；product 走 URL 参数（body 亦可），title/spec/pri/category 必填。"""
    if category not in CATEGORIES:
        raise ValueError(f"category 取值应为 {CATEGORIES} 之一，实际 {category!r}")
    return client.post("/stories",
                       body={"title": title, "spec": spec or title, "pri": pri,
                             "category": category, **fields},
                       params={"product": product})


def update(client, story_id, **fields):
    return client.put(f"/stories/{story_id}", body=fields)


def delete(client, story_id):
    return client.delete(f"/stories/{story_id}")


if __name__ == "__main__":  # 简单自测
    c = ZentaoClient()
    print(list_(c, product=1))
